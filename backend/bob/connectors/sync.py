"""Re-sync diff (G2, CONTRACTS §10): what changed in the sources since the last fetch.

The orchestrator (A1) re-fetches the job's sources with `refetch(job)` (each SourceSpec
through `fetch_documents`, as the job owner), then calls `diff(old_docs, new_docs)`, or
does both at once with `refetch_diff(job, old_docs)`. Documents match by `uri`; a document changed when its
`content_hash` differs. `stale_doc_ids` names the old document ids whose rows must be
verified again (changed or removed), since `Row.spans` point at document ids.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from bob.core.models import Document, Job

Progress = Callable[[int, int, str], Awaitable[None]]


class SyncDiff(TypedDict):
    added: list[Document]  # new uri
    changed: list[Document]  # same uri, new content_hash (the new Document)
    removed: list[Document]  # uri gone (the old Document)


def _by_uri(docs: Iterable[Document]) -> dict[str, Document]:
    out: dict[str, Document] = {}
    for doc in docs:
        if doc.uri in out and out[doc.uri].content_hash != doc.content_hash:
            raise ValueError(f"two different documents share the uri {doc.uri!r}")
        out[doc.uri] = doc
    return out


def diff(old_docs: Iterable[Document], new_docs: Iterable[Document]) -> SyncDiff:
    """Compare two fetches of the same sources. Order follows the new fetch, then the old one."""
    old = _by_uri(old_docs)
    new = _by_uri(new_docs)
    return {
        "added": [d for uri, d in new.items() if uri not in old],
        "changed": [d for uri, d in new.items() if uri in old and old[uri].content_hash != d.content_hash],
        "removed": [d for uri, d in old.items() if uri not in new],
    }


def stale_doc_ids(old_docs: Iterable[Document], result: SyncDiff) -> set[str]:
    """Old document ids whose rows need a re-check: the changed and the removed ones."""
    changed_uris = {d.uri for d in result["changed"]} | {d.uri for d in result["removed"]}
    return {d.id for d in old_docs if d.uri in changed_uris}


async def _no_progress(done: int, total: int, detail: str) -> None:
    return None


async def refetch(job: Job, progress: Progress | None = None) -> list[Document]:
    """Fetch every SourceSpec of `job` again, as its owner. Same rules as the first ingest:
    sources in order, one Document per id (a later source wins), real provider errors raised."""
    from bob.connectors import fetch_documents

    report = progress or _no_progress
    docs: dict[str, Document] = {}
    n = len(job.spec.sources)
    for i, spec in enumerate(job.spec.sources):

        async def step(done: int, total: int, detail: str, _i: int = i) -> None:
            await report(done, total, f"source {_i + 1}/{n}: {detail}")

        for doc in await fetch_documents(spec, job.id, step, user_id=job.owner_id):
            docs[doc.id] = doc
    return list(docs.values())


async def refetch_diff(
    job: Job, old_docs: Iterable[Document], progress: Progress | None = None
) -> tuple[list[Document], SyncDiff, set[str]]:
    """`refetch(job)`, then `diff(old_docs, new_docs)` and `stale_doc_ids`: (new_docs, diff, stale ids)."""
    old = list(old_docs)
    new = await refetch(job, progress)
    result = diff(old, new)
    return new, result, stale_doc_ids(old, result)
