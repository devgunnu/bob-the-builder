"""EventLog protocol + local implementation (CONTRACTS sections 7, 8). Owner: A1. aws impl: bob/aws/events.py (A5).

Per-job sequence ids start at 1. `subscribe(job_id, last_event_id)` replays events with id > last_event_id,
then streams live events. LocalEventLog keeps events in memory and persists every event to
settings.runs_dir/<job_id>/events.jsonl; a new LocalEventLog reloads a job's events from that file on first
use, so `Last-Event-ID` replay works after a restart.

Throttling stays above the backend, in `JobEmitter` (the `emit` of one job): `cell.update` max 5/s per cell,
`cost` and `counts` max 2/s per job. Throttled events coalesce: the last value is sent when the window ends.
`flush()` sends every pending value at once (call it before terminal events).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from bob.core.models import Event

__all__ = ["Event", "EventLog", "JobEmitter", "LocalEventLog"]


@runtime_checkable
class EventLog(Protocol):
    async def append(self, job_id: str, type: str, data: dict) -> int:
        """Append one event; returns its seq."""
        ...

    async def read_after(self, job_id: str, seq: int) -> list[Event]:
        """Events with id > seq, in order."""
        ...

    def subscribe(self, job_id: str, last_event_id: int | None) -> AsyncIterator[Event]:
        """Replay id > last_event_id (None = from the start), then live. local: queue; aws: poll read_after."""
        ...


class LocalEventLog:
    def __init__(self, runs_dir: Path | None = None) -> None:
        if runs_dir is None:
            from bob.config import get_settings

            runs_dir = get_settings().runs_dir
        self.root = Path(runs_dir).resolve()
        self._events: dict[str, list[Event]] = {}
        self._subs: dict[str, set[asyncio.Queue[Event]]] = {}
        self._lock = asyncio.Lock()

    def _path(self, job_id: str) -> Path:
        return self.root / job_id / "events.jsonl"

    def _log(self, job_id: str) -> list[Event]:
        """The job's events; loads events.jsonl on first use."""
        log = self._events.get(job_id)
        if log is None:
            log = []
            p = self._path(job_id)
            if p.is_file():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            log.append(Event.model_validate_json(line))
                        except ValueError:
                            break  # a torn last line after a crash
            self._events[job_id] = log
        return log

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    async def append(self, job_id: str, type: str, data: dict) -> int:
        async with self._lock:
            log = self._log(job_id)
            seq = (log[-1].id if log else 0) + 1
            ev = Event(id=seq, type=type, data=json.loads(json.dumps(data, default=str)))
            # memory first: a cancelled await still lets the worker thread finish the file write
            log.append(ev)
            for q in self._subs.get(job_id, ()):
                q.put_nowait(ev)
            await asyncio.to_thread(self._append_line, self._path(job_id), ev.model_dump_json())
        return seq

    async def read_after(self, job_id: str, seq: int) -> list[Event]:
        log = self._log(job_id)
        return [e for e in log if e.id > seq]

    async def last_seq(self, job_id: str) -> int:
        log = self._log(job_id)
        return log[-1].id if log else 0

    async def subscribe(self, job_id: str, last_event_id: int | None) -> AsyncIterator[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        async with self._lock:  # register + snapshot under the lock: no gap, no duplicate
            self._subs.setdefault(job_id, set()).add(q)
            last = last_event_id or 0
            backlog = [e for e in self._log(job_id) if e.id > last]
        try:
            for ev in backlog:
                last = ev.id
                yield ev
            while True:
                ev = await q.get()
                if ev.id > last:
                    last = ev.id
                    yield ev
        finally:
            self._subs.get(job_id, set()).discard(q)


# ---------- throttled per-job emitter (above the backend) ----------
_JOB_THROTTLE = {"cost": 0.5, "counts": 0.5}  # seconds between events of this type per job (2/s)
_CELL_INTERVAL = 0.2  # cell.update: 5/s per cell


class JobEmitter:
    """`emit(type, data)` for one job: appends to the EventLog with the section 8 throttles."""

    def __init__(self, log: EventLog, job_id: str) -> None:
        self.log = log
        self.job_id = job_id
        self._last: dict[str, float] = {}
        self._pending: dict[str, tuple[str, dict]] = {}
        self._timers: dict[str, asyncio.Task[None]] = {}

    @staticmethod
    def _key(type: str, data: dict) -> tuple[str, float] | None:
        if type == "cell.update":
            return f"cell.update:{data.get('cell_id')}", _CELL_INTERVAL
        if type in _JOB_THROTTLE:
            return type, _JOB_THROTTLE[type]
        return None

    async def __call__(self, type: str, data: dict) -> None:
        await self.emit(type, data)

    async def emit(self, type: str, data: dict) -> None:
        kw = self._key(type, data)
        if kw is None:
            await self.log.append(self.job_id, type, data)
            return
        key, interval = kw
        now = time.monotonic()
        wait = self._last.get(key, 0.0) + interval - now
        if wait <= 0 and key not in self._pending:
            self._last[key] = now
            await self.log.append(self.job_id, type, data)
            return
        self._pending[key] = (type, data)  # coalesce: keep the last value
        if key not in self._timers or self._timers[key].done():
            self._timers[key] = asyncio.create_task(self._later(key, max(wait, 0.0)))

    async def _later(self, key: str, wait: float) -> None:
        await asyncio.sleep(wait)
        item = self._pending.pop(key, None)
        if item is not None:
            self._last[key] = time.monotonic()
            await asyncio.shield(self.log.append(self.job_id, item[0], item[1]))

    async def flush(self) -> None:
        """Send every pending throttled event now (before done / error / cancelled)."""
        for t in self._timers.values():
            if not t.done():
                t.cancel()
        self._timers.clear()
        pending, self._pending = self._pending, {}
        for key, (type, data) in pending.items():
            self._last[key] = time.monotonic()
            await self.log.append(self.job_id, type, data)
