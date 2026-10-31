"""Store protocol + local implementation (CONTRACTS section 7). Owner: A1. aws impl: bob/aws/store.py (A5).

LocalStore (wave 0) keeps everything in memory. Wave 1 adds the disk copy under settings.runs_dir/<job_id>/
(job.json, rows.jsonl) and users on disk, and reloads jobs on start.
Missing job / row: KeyError.
"""

from __future__ import annotations

import asyncio
from typing import Literal, Protocol, runtime_checkable

from bob.core.models import Control, Job, Plan, Row, UserProfile


@runtime_checkable
class Store(Protocol):
    async def put_job(self, job: Job) -> None:
        """Worker calls it on each status change and at most every 2 s."""
        ...

    async def get_job(self, job_id: str) -> Job: ...

    async def list_jobs(self, owner_id: str) -> list[Job]:
        """Only this user's jobs."""
        ...

    async def put_rows(self, job_id: str, rows: list[Row]) -> None: ...

    async def list_rows(
        self,
        job_id: str,
        verdict: Literal["kept", "rejected"] | None = None,
        cell_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[Row]]:
        """(total matching, page) in insert order."""
        ...

    async def get_row(self, job_id: str, row_id: str) -> Row: ...

    async def set_control(
        self, job_id: str, control: Literal["approved", "cancel"], plan: Plan | None = None
    ) -> None: ...

    async def get_control(self, job_id: str) -> Control:
        """State + approved plan (aws: META control + plan_key -> runs/<id>/approved_plan.json)."""
        ...

    async def get_user(self, user_id: str) -> UserProfile | None: ...

    async def put_user(self, user: UserProfile) -> None: ...


class LocalStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._rows: dict[str, dict[str, Row]] = {}  # job_id -> row_id -> Row (dict keeps insert order)
        self._controls: dict[str, Control] = {}
        self._users: dict[str, UserProfile] = {}
        self._lock = asyncio.Lock()

    async def put_job(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)

    async def get_job(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job.model_copy(deep=True)

    async def list_jobs(self, owner_id: str) -> list[Job]:
        jobs = [j for j in self._jobs.values() if j.owner_id == owner_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.model_copy(deep=True) for j in jobs]

    async def put_rows(self, job_id: str, rows: list[Row]) -> None:
        async with self._lock:
            table = self._rows.setdefault(job_id, {})
            for r in rows:
                table[r.id] = r.model_copy(deep=True)

    async def list_rows(
        self,
        job_id: str,
        verdict: Literal["kept", "rejected"] | None = None,
        cell_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[Row]]:
        rows = [
            r
            for r in self._rows.get(job_id, {}).values()
            if (verdict is None or r.verdict == verdict) and (cell_id is None or r.cell_id == cell_id)
        ]
        page = rows[offset : offset + limit]
        return len(rows), [r.model_copy(deep=True) for r in page]

    async def get_row(self, job_id: str, row_id: str) -> Row:
        row = self._rows.get(job_id, {}).get(row_id)
        if row is None:
            raise KeyError(row_id)
        return row.model_copy(deep=True)

    async def set_control(
        self, job_id: str, control: Literal["approved", "cancel"], plan: Plan | None = None
    ) -> None:
        async with self._lock:
            prev = self._controls.get(job_id, Control())
            # cancel keeps an approved plan; approve sets the plan
            new_plan = plan if control == "approved" else prev.plan
            self._controls[job_id] = Control(state=control, plan=new_plan)

    async def get_control(self, job_id: str) -> Control:
        return self._controls.get(job_id, Control()).model_copy(deep=True)

    async def get_user(self, user_id: str) -> UserProfile | None:
        user = self._users.get(user_id)
        return user.model_copy(deep=True) if user else None

    async def put_user(self, user: UserProfile) -> None:
        async with self._lock:
            self._users[user.id] = user.model_copy(deep=True)
