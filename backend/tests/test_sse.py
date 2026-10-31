"""SSE stream tests: wire format, heartbeat, max lifetime, Last-Event-ID parsing.

Events come from an in-process asyncio queue, the same mechanism as A1's local
EventLog. No external service is involved.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from starlette.requests import Request

from bob.api.sse import event_stream, format_event, parse_last_event_id


@dataclass
class Event:
    id: int
    type: str
    data: dict[str, Any] = field(default_factory=dict)


async def from_queue(queue: asyncio.Queue[Event | None]) -> AsyncIterator[Event]:
    while (event := await queue.get()) is not None:
        yield event


async def collect(stream: AsyncIterator[str], limit: int = 50) -> list[str]:
    out = []
    async for chunk in stream:
        out.append(chunk)
        if len(out) >= limit:
            break
    return out


def request_with(headers: dict[str, str] | None = None, query: str = "") -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw_headers, "query_string": query.encode()})


def test_format_event_matches_contract_wire_format():
    text = format_event(7, "job.status", {"status": "reading", "detail": "chunking 5 docs"})
    lines = text.split("\n")
    assert lines[0] == "id: 7"
    assert lines[1] == "event: job.status"
    assert json.loads(lines[2].removeprefix("data: ")) == {
        "status": "reading",
        "detail": "chunking 5 docs",
    }
    assert text.endswith("\n\n")


@pytest.mark.asyncio
async def test_stream_starts_with_retry_then_events_then_ends():
    queue: asyncio.Queue[Event | None] = asyncio.Queue()
    for item in (
        Event(1, "job.status", {"status": "created"}),
        Event(2, "counts", {"docs": 5}),
        None,
    ):
        queue.put_nowait(item)
    chunks = await collect(event_stream(from_queue(queue), heartbeat_s=5, max_s=5))
    assert chunks[0] == "retry: 1000\n\n"
    assert chunks[1].startswith("id: 1\nevent: job.status\n")
    assert chunks[2].startswith("id: 2\nevent: counts\n")
    assert len(chunks) == 3


@pytest.mark.asyncio
async def test_heartbeat_when_idle_and_close_at_max_lifetime():
    queue: asyncio.Queue[Event | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    start = loop.time()
    chunks = await collect(event_stream(from_queue(queue), heartbeat_s=0.05, max_s=0.23))
    elapsed = loop.time() - start
    assert chunks[0] == "retry: 1000\n\n"
    pings = [c for c in chunks if c == ": ping\n\n"]
    assert 3 <= len(pings) <= 5
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_event_after_heartbeat_is_not_lost():
    queue: asyncio.Queue[Event | None] = asyncio.Queue()

    async def produce() -> None:
        await asyncio.sleep(0.12)
        queue.put_nowait(Event(3, "row", {"id": "r1", "verdict": "kept"}))
        queue.put_nowait(None)

    producer = asyncio.create_task(produce())
    chunks = await collect(event_stream(from_queue(queue), heartbeat_s=0.05, max_s=2))
    await producer
    assert ": ping\n\n" in chunks
    assert chunks[-1].startswith("id: 3\nevent: row\n")


@pytest.mark.asyncio
async def test_client_disconnect_closes_source_iterator():
    closed = asyncio.Event()

    async def source() -> AsyncIterator[Event]:
        try:
            yield Event(1, "log", {"level": "info", "message": "hi"})
            await asyncio.sleep(10)
        finally:
            closed.set()

    stream = event_stream(source(), heartbeat_s=5, max_s=5)
    assert await anext(stream) == "retry: 1000\n\n"
    assert (await anext(stream)).startswith("id: 1\n")
    pending = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0.05)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await stream.aclose()
    assert closed.is_set()


@pytest.mark.parametrize(
    ("headers", "query", "expected"),
    [
        ({"Last-Event-ID": "42"}, "", 42),
        ({"Last-Event-ID": " 9 "}, "", 9),
        ({}, "last_event_id=12", 12),
        ({"Last-Event-ID": "5"}, "last_event_id=12", 5),
        ({"Last-Event-ID": "abc"}, "", None),
        ({"Last-Event-ID": "-3"}, "", None),
        ({}, "", None),
    ],
)
def test_parse_last_event_id(headers, query, expected):
    assert parse_last_event_id(request_with(headers, query)) == expected
