"""Runner protocol + local implementation (CONTRACTS section 7). Owner: A1. aws impl: bob/aws/runner.py (A5)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, runtime_checkable

RunMode = Literal["create", "resync"]
RunJob = Callable[[str, RunMode], Awaitable[None]]


class RunnerBusy(Exception):
    """BOB_MAX_WORKERS or BOB_MAX_ACTIVE_JOBS_PER_USER reached. The route maps it to HTTP 429."""


@runtime_checkable
class Runner(Protocol):
    async def start(self, job_id: str, mode: RunMode) -> None:
        """local: asyncio task running Orchestrator.run_job; aws: ecs.run_task. Raises RunnerBusy."""
        ...

    async def stop(self, job_id: str) -> None:
        """aws: ecs.stop_task (used 10 s after a cancel flag if the task still runs)."""
        ...

    async def is_running(self, job_id: str) -> bool:
        """local: the asyncio task exists and is not done; aws: META task_arn + ecs.describe_tasks."""
        ...


class LocalRunner:
    """Runs Orchestrator.run_job in an asyncio task in this process.

    The Orchestrator binds its run_job (and its store, for the owner check) with `bind()`; get_runner() takes
    no arguments. `stopped_reason(job_id)` (A1 addition, used by the watchdog) explains a task that ended.
    """

    def __init__(
        self,
        run_job: RunJob | None = None,
        *,
        max_workers: int | None = None,
        max_active_per_user: int | None = None,
    ) -> None:
        from bob.config import get_settings

        s = get_settings()
        self._run_job = run_job
        self.max_workers = max_workers if max_workers is not None else s.max_workers
        self.max_active_per_user = (
            max_active_per_user if max_active_per_user is not None else s.max_active_jobs_per_user
        )
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._owners: dict[str, str] = {}
        self._reasons: dict[str, str] = {}
        self._store = None

    def bind(self, run_job: RunJob, store=None) -> None:
        self._run_job = run_job
        if store is not None:
            self._store = store

    def stopped_reason(self, job_id: str) -> str | None:
        task = self._tasks.get(job_id)
        if task is None:
            return self._reasons.get(job_id, "no worker task in this process")
        if not task.done():
            return None
        return self._reasons.get(job_id, "worker task ended")

    def _done(self, job_id: str, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            self._reasons[job_id] = "worker task cancelled"
        elif task.exception() is not None:
            exc = task.exception()
            self._reasons[job_id] = f"worker task failed: {type(exc).__name__}: {exc}"
        else:
            self._reasons[job_id] = "worker task ended"

    def _active(self) -> dict[str, asyncio.Task[None]]:
        return {jid: t for jid, t in self._tasks.items() if not t.done()}

    async def check_capacity(self, owner_id: str) -> None:
        """A1 addition: raise RunnerBusy when a new job of `owner_id` would not fit (create_job calls it
        before it saves the job, so nothing is saved on HTTP 429)."""
        active = self._active()
        if len(active) >= self.max_workers:
            raise RunnerBusy("too many running jobs")
        if sum(1 for jid in active if self._owners.get(jid) == owner_id) >= self.max_active_per_user:
            raise RunnerBusy("too many running jobs")

    async def start(self, job_id: str, mode: RunMode) -> None:
        if self._run_job is None:
            raise RuntimeError("LocalRunner has no run_job; call bind(orchestrator.run_job) first")
        active = self._active()
        if job_id in active:
            raise RunnerBusy(f"job {job_id} already runs")
        if len(active) >= self.max_workers:
            raise RunnerBusy("too many running jobs")
        store = self._store
        if store is None:
            from bob.core.backends import get_store

            store = get_store()
        owner = (await store.get_job(job_id)).owner_id
        if sum(1 for jid in active if self._owners.get(jid) == owner) >= self.max_active_per_user:
            raise RunnerBusy("too many running jobs")
        self._owners[job_id] = owner
        task = asyncio.create_task(self._run_job(job_id, mode), name=f"bob-job-{job_id}")
        task.add_done_callback(lambda t, jid=job_id: self._done(jid, t))
        self._tasks[job_id] = task
        self._reasons.pop(job_id, None)

    async def stop(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def is_running(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()
