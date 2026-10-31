"""Re-sync diff (G2, CONTRACTS §10): what changed in the sources since the last fetch.

The orchestrator (A1) re-fetches each SourceSpec with `fetch_documents`, then calls
`diff(old_docs, new_docs)`. Documents match by `uri`; a document changed when its
`content_hash` differs. `stale_doc_ids` names the old document ids whose rows must be
verified again (changed or removed), since `Row.spans` point at document ids.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from bob.core.models import Document


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
