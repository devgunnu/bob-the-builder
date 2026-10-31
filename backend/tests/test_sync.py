"""G2 re-sync diff on real smoke documents (parsed from demo/smoke uploads, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.connectors import sync
from bob.connectors.parsers import parse_file
from bob.core.models import Document

SMOKE = Path(__file__).resolve().parents[2] / "demo" / "smoke"


def smoke_docs(*names: str) -> list[Document]:
    import hashlib
    from datetime import UTC, datetime

    docs = []
    for name in names:
        parsed = parse_file(name, (SMOKE / name).read_bytes())
        title, text, meta = parsed.title, parsed.text, dict(parsed.metadata)
        uri = meta.get("source_url") or f"upload://{name}"
        docs.append(
            Document(
                id=hashlib.sha1(uri.encode()).hexdigest()[:12],
                source_kind="upload",
                uri=uri,
                title=title,
                text=text,
                content_hash=hashlib.sha1(text.encode()).hexdigest(),
                metadata=meta,
                fetched_at=datetime.now(UTC),
            )
        )
    return docs


def edited(doc: Document, text: str) -> Document:
    import hashlib

    return doc.model_copy(update={"text": text, "content_hash": hashlib.sha1(text.encode()).hexdigest()})


def test_diff_finds_added_changed_removed():
    billing, limits, hooks = smoke_docs("billing.md", "rate-limits.md", "webhooks-overview.md")
    security = smoke_docs("webhooks-security.md")[0]
    old = [billing, limits, hooks]
    new = [billing, edited(limits, limits.text.replace("per minute", "per second", 1)), security]
    result = sync.diff(old, new)
    assert [d.uri for d in result["added"]] == [security.uri]
    assert [d.uri for d in result["changed"]] == [limits.uri]
    assert result["changed"][0].content_hash != limits.content_hash
    assert [d.uri for d in result["removed"]] == [hooks.uri]
    assert sync.stale_doc_ids(old, result) == {limits.id, hooks.id}


def test_same_fetch_is_a_no_op():
    docs = smoke_docs("billing.md", "rate-limits.md")
    assert sync.diff(docs, list(reversed(docs))) == {"added": [], "changed": [], "removed": []}


def test_conflicting_uri_is_an_error():
    billing = smoke_docs("billing.md")[0]
    with pytest.raises(ValueError, match="share the uri"):
        sync.diff([billing, edited(billing, "other text")], [])
