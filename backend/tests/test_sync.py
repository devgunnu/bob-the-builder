"""G2 re-sync diff on real smoke documents (parsed from demo/smoke uploads, no network)."""

from __future__ import annotations

import os
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


# ---------- refetch: the job's sources again, through fetch_documents, as the owner ----------


def make_job(sources, owner_id: str = "local"):
    import uuid
    from datetime import UTC, datetime

    from bob.config import default_model_roles
    from bob.core.models import Job, JobSpec

    now = datetime.now(UTC)
    return Job(
        id=f"sync-{uuid.uuid4().hex[:8]}",
        spec=JobSpec(goal="support bot", sources=sources),
        owner_id=owner_id,
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_refetch_uploads_is_a_no_op_and_owner_scoped():
    from bob.connectors.upload import UploadNotFound, save_uploads
    from bob.core.models import SourceSpec

    names = ("billing.md", "rate-limits.md")
    saved = await save_uploads([(n, (SMOKE / n).read_bytes()) for n in names], owner_id="local")
    job = make_job([SourceSpec(kind="upload", upload_ids=[f.id for f in saved])])
    events: list[tuple[int, int, str]] = []

    async def progress(done: int, total: int, detail: str) -> None:
        events.append((done, total, detail))

    first = await sync.refetch(job, progress)
    assert sorted(d.metadata["filename"] for d in first) == sorted(names)
    assert events and all(e[2].startswith("source 1/1: ") for e in events)
    new, result, stale = await sync.refetch_diff(job, first)
    assert {d.id for d in new} == {d.id for d in first}
    assert result == {"added": [], "changed": [], "removed": []}
    assert stale == set()
    # Another user's job cannot re-read these uploads.
    with pytest.raises(UploadNotFound):
        await sync.refetch(make_job(job.spec.sources, owner_id="someone-else"))


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("COMPOSIO_API_KEY"), reason="needs COMPOSIO_API_KEY")
async def test_real_notion_refetch_of_the_demo_wiki_has_no_changes():
    from bob.connectors import composio as cz
    from bob.core.models import SourceSpec

    listed = cz.client().connected_accounts.list(
        user_ids=[cz.composio_user_id("local")], toolkit_slugs=["notion"]
    )
    if not listed.items:
        pytest.skip("no Notion connection for bob-local yet")
    account_id = str(listed.items[0].id)
    pages = await cz.browse("notion", account_id, "", user_id="local")
    page_ids = [p["id"] for p in pages if p["kind"] == "page"]
    assert page_ids, "the demo connection sees no pages"
    job = make_job(
        [
            SourceSpec(
                kind="composio",
                toolkit="notion",
                connected_account_id=account_id,
                scope={"page_ids": page_ids},
            )
        ]
    )
    first = await sync.refetch(job)
    assert first and all(d.uri.startswith("notion://") for d in first)
    new, result, stale = await sync.refetch_diff(job, first)
    assert result == {"added": [], "changed": [], "removed": []}, {
        k: [d.uri for d in v] for k, v in result.items()
    }
    assert stale == set()
    assert {d.content_hash for d in new} == {d.content_hash for d in first}


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("FIRECRAWL_API_KEY"), reason="needs FIRECRAWL_API_KEY")
async def test_real_firecrawl_refetch_two_pages():
    from bob.core.models import SourceSpec

    # One real crawl (2 pages, free plan friendly), compared with an older copy of the same pages.
    job = make_job(
        [SourceSpec(kind="url", url="https://docs.firecrawl.dev/webhooks/overview", crawl_limit=2)]
    )
    new = await sync.refetch(job)
    assert 1 <= len(new) <= 2
    assert all(d.uri.startswith("https://docs.firecrawl.dev/") for d in new)
    older = [edited(new[0], new[0].text + "\n\nA line the site removed since."), *new[1:]]
    gone = edited(new[0], "a page the site dropped").model_copy(
        update={"id": "gone0000000", "uri": "https://docs.firecrawl.dev/removed-page"}
    )
    result = sync.diff([*older, gone], new)
    assert result["added"] == []
    assert [d.uri for d in result["changed"]] == [new[0].uri]
    assert [d.uri for d in result["removed"]] == [gone.uri]
    assert sync.stale_doc_ids([*older, gone], result) == {new[0].id, gone.id}
