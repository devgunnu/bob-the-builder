"""EventLog protocol + local implementation (CONTRACTS sections 7, 8). Owner: A1. aws impl: bob/aws/events.py (A5).

Per-job sequence ids start at 1. `subscribe(job_id, last_event_id)` replays events with id > last_event_id,
then streams live events. Throttling (cell.update 5/s per cell, cost + counts 2/s per job) stays above the
backend (wave 1). LocalEventLog (wave 0) is in memory; wave 1 persists every event to
settings.runs_dir/<job_id>/events.jsonl.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from bob.core.models import Event

__all__ = ["Event", "EventLog", "LocalEventLog"]


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
    def __init__(self) -> None:
        self._events: dict[str, list[Event]] = {}
        self._subs: dict[str, set[asyncio.Queue[Event]]] = {}
        self._lock = asyncio.Lock()

    async def append(self, job_id: str, type: str, data: dict) -> int:
        async with self._lock:
            log = self._events.setdefault(job_id, [])
            seq = len(log) + 1
            ev = Event(id=seq, type=type, data=data)
            log.append(ev)
            for q in self._subs.get(job_id, ()):
                q.put_nowait(ev)
        return seq

    async def read_after(self, job_id: str, seq: int) -> list[Event]:
        return list(self._events.get(job_id, [])[max(seq, 0) :])

    async def subscribe(self, job_id: str, last_event_id: int | None) -> AsyncIterator[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        async with self._lock:  # register + snapshot under the lock: no gap, no duplicate
            self._subs.setdefault(job_id, set()).add(q)
            backlog = list(self._events.get(job_id, [])[max(last_event_id or 0, 0) :])
        try:
            last = last_event_id or 0
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
