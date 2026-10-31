"""Connector dispatch (G1): the only connector API the orchestrator calls (CONTRACTS §7)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # parsers stay importable without the core models
    from bob.core.models import Document, SourceSpec


async def fetch_documents(
    spec: SourceSpec,
    job_id: str,
    progress: Callable[[int, int, str], Awaitable[None]],
    *,
    user_id: str,
) -> list[Document]:
    """Fetch one source as Documents. `user_id` is Job.owner_id (private Composio connections)."""
    if spec.kind == "upload":
        from bob.connectors import upload

        return await upload.fetch(spec, job_id, progress)
    if spec.kind == "url":
        from bob.connectors import firecrawl

        return await firecrawl.fetch(spec, job_id, progress)
    if spec.kind == "composio":
        from bob.connectors import composio

        return await composio.fetch(spec, job_id, progress, user_id=user_id)
    raise ValueError(f"unknown source kind {spec.kind!r}")
