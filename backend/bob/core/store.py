"""Store protocol + local implementation (CONTRACTS section 7). Owner: A1. aws impl: bob/aws/store.py (A5).

LocalStore: in-memory dicts plus a disk copy under settings.runs_dir:
  <job_id>/job.json, <job_id>/rows.jsonl (append-only; a later line with the same row id wins),
  <job_id>/control.json, _users/<safe user id>.json.
Jobs, rows, controls and users reload from disk when the store starts.
Missing job / row: KeyError.

`put_job_if_status(job, expected)` (A1 addition, used by the watchdog): conditional write, False when the
stored status is not `expected` any more. aws (A5): a conditional update on META. The orchestrator falls
back to read-compare-write when a store does not have it.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from bob.core.models import Control, Job, JobStatus, Plan, Row, UserProfile


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


_JOB_ID = re.compile(r"[\w.-]+")


class LocalStore:
    def __init__(self, runs_dir: Path | None = None) -> None:
        if runs_dir is None:
            from bob.config import get_settings

            runs_dir = get_settings().runs_dir
        self.root = Path(runs_dir).resolve()
        self._jobs: dict[str, Job] = {}
        self._rows: dict[str, dict[str, Row]] = {}  # job_id -> row_id -> Row (dict keeps insert order)
        self._controls: dict[str, Control] = {}
        self._users: dict[str, UserProfile] = {}
        self._lock = asyncio.Lock()
        self._reload()

    # ---------- disk ----------
    def job_dir(self, job_id: str) -> Path:
        if not _JOB_ID.fullmatch(job_id) or job_id.startswith("."):
            raise ValueError(f"bad job id {job_id!r}")
        return self.root / job_id

    def _user_path(self, user_id: str) -> Path:
        safe = re.sub(r"[^\w.-]", "_", user_id)[:80]
        digest = hashlib.sha1(user_id.encode()).hexdigest()[:8]
        return self.root / "_users" / f"{safe}-{digest}.json"

    @staticmethod
    def _write_atomic(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _append_lines(path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in lines))

    def _reload(self) -> None:
        if not self.root.is_dir():
            return
        for jf in self.root.glob("*/job.json"):
            try:
                job = Job.model_validate_json(jf.read_text(encoding="utf-8"))
            except ValueError:
                continue
            self._jobs[job.id] = job
            rows: dict[str, Row] = {}
            rf = jf.parent / "rows.jsonl"
            if rf.is_file():
                for line in rf.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        r = Row.model_validate_json(line)
                    except ValueError:
                        continue  # a torn last line after a crash
                    rows[r.id] = r
            self._rows[job.id] = rows
            cf = jf.parent / "control.json"
            if cf.is_file():
                try:
                    self._controls[job.id] = Control.model_validate_json(cf.read_text(encoding="utf-8"))
                except ValueError:
                    pass
        for uf in (self.root / "_users").glob("*.json"):
            try:
                u = UserProfile.model_validate_json(uf.read_text(encoding="utf-8"))
            except ValueError:
                continue
            self._users[u.id] = u

    # ---------- jobs ----------
    async def put_job(self, job: Job) -> None:
        path = self.job_dir(job.id) / "job.json"
        async with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)
            await asyncio.to_thread(self._write_atomic, path, job.model_dump_json())

    async def put_job_if_status(self, job: Job, expected: JobStatus) -> bool:
        """Conditional write: only when the stored status is still `expected`."""
        path = self.job_dir(job.id) / "job.json"
        async with self._lock:
            cur = self._jobs.get(job.id)
            if cur is None or cur.status != expected:
                return False
            self._jobs[job.id] = job.model_copy(deep=True)
            await asyncio.to_thread(self._write_atomic, path, job.model_dump_json())
            return True

    async def get_job(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job.model_copy(deep=True)

    async def list_jobs(self, owner_id: str) -> list[Job]:
        jobs = [j for j in self._jobs.values() if j.owner_id == owner_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.model_copy(deep=True) for j in jobs]

    # ---------- rows ----------
    async def put_rows(self, job_id: str, rows: list[Row]) -> None:
        if not rows:
            return
        path = self.job_dir(job_id) / "rows.jsonl"
        async with self._lock:
            table = self._rows.setdefault(job_id, {})
            for r in rows:
                table[r.id] = r.model_copy(deep=True)
            await asyncio.to_thread(self._append_lines, path, [r.model_dump_json() for r in rows])

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

    # ---------- control ----------
    async def set_control(
        self, job_id: str, control: Literal["approved", "cancel"], plan: Plan | None = None
    ) -> None:
        path = self.job_dir(job_id) / "control.json"
        async with self._lock:
            prev = self._controls.get(job_id, Control())
            # cancel keeps an approved plan; approve sets the plan
            new_plan = plan if control == "approved" else prev.plan
            ctl = Control(state=control, plan=new_plan)
            self._controls[job_id] = ctl
            await asyncio.to_thread(self._write_atomic, path, ctl.model_dump_json())

    async def get_control(self, job_id: str) -> Control:
        return self._controls.get(job_id, Control()).model_copy(deep=True)

    # ---------- users ----------
    async def get_user(self, user_id: str) -> UserProfile | None:
        user = self._users.get(user_id)
        return user.model_copy(deep=True) if user else None

    async def put_user(self, user: UserProfile) -> None:
        path = self._user_path(user.id)
        async with self._lock:
            self._users[user.id] = user.model_copy(deep=True)
            await asyncio.to_thread(self._write_atomic, path, user.model_dump_json())
