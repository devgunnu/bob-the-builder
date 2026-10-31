"""Server-sent events for one job (G1, CONTRACTS §8).

Wire format: `id: <seq>\\nevent: <type>\\ndata: <json>\\n\\n`.
- `retry: 1000` at stream start.
- `: ping` comment after BOB_SSE_HEARTBEAT_S without an event (CloudFront cuts idle streams).
- The stream closes after BOB_SSE_MAX_S; the browser reconnects with Last-Event-ID
  and the orchestrator replays every event with a higher seq.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from pydantic_core import to_json
from starlette.requests import Request
from starlette.responses import StreamingResponse

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
RETRY_MS = 1000


def event_parts(event: Any) -> tuple[int, str, Any]:
    """(seq, type, data) of one `Event(id, type, data)` from Orchestrator.subscribe."""
    return int(event.id), str(event.type), event.data


def parse_last_event_id(request: Request) -> int | None:
    """Header Last-Event-ID, else the last_event_id query param. Bad values replay from start."""
    raw = request.headers.get("Last-Event-ID") or request.query_params.get("last_event_id")
    if raw is None:
        return None
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    return value if value >= 0 else None


def format_event(seq: int, type_: str, data: Any) -> str:
    payload = to_json(data).decode()
    return f"id: {seq}\nevent: {type_}\ndata: {payload}\n\n"


async def event_stream(events: AsyncIterator[Any], *, heartbeat_s: float, max_s: float) -> AsyncIterator[str]:
    """Turn orchestrator events into SSE text, with heartbeats and a max lifetime."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_s
    iterator = aiter(events)
    pending: asyncio.Future[Any] | None = None
    yield f"retry: {RETRY_MS}\n\n"
    try:
        while (remaining := deadline - loop.time()) > 0:
            if pending is None:
                pending = asyncio.ensure_future(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=min(heartbeat_s, remaining))
            if not done:
                yield ": ping\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            finally:
                pending = None
            yield format_event(*event_parts(event))
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            with suppress(Exception):
                await aclose()


def sse_response(events: AsyncIterator[Any], *, heartbeat_s: float, max_s: float) -> StreamingResponse:
    return StreamingResponse(
        event_stream(events, heartbeat_s=heartbeat_s, max_s=max_s),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
