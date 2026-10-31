"""A2 reading stages with real calls (Jev, ScaleDown, Bedrock writer) on real local text.

Corpus: the repo's own `.agents/*.md` docs (real text) until G2's `demo/smoke/` exists. Small sizes.
Run with `pytest -s` to see counts, topics and 5 evidence samples.
"""

from collections import Counter

import a2_support
import pytest

from bob.core import ledger
from bob.pipeline.chunk import chunk_documents
from bob.pipeline.embed import dedup_chunks
from bob.pipeline.evidence import EvidenceIndex, Retriever, build_evidence
from bob.pipeline.filters import heuristic_filter
from bob.pipeline.topics import build_topics
from bob.pipeline.triage import triage

N_CHUNKS = 12


@pytest.fixture
def job():
    j = a2_support.make_job(
        "a2-read", goal="a support assistant that answers questions about the Bob the Builder project plan"
    )
    ledger.register_job(j)
    return j


def _sample_chunks():
    docs = a2_support.agents_documents()
    chunks = dedup_chunks(heuristic_filter(chunk_documents(docs)))
    kept = [c for c in chunks if c.kept]
    step = max(1, len(kept) // N_CHUNKS)
    return {d.id: d for d in docs}, kept[::step][:N_CHUNKS]


async def test_triage_topics_evidence_retriever(job):
    docs, chunks = _sample_chunks()

    triaged = await triage(chunks, job=job)
    print("triage:", Counter(c.drop_reason for c in triaged))
    for c in triaged[:3]:
        print("  ", c.id, c.heading, c.triage)
    assert all(set(c.triage) >= {"useful", "boilerplate", "pii", "injection"} for c in triaged)
    kept = [c for c in triaged if c.kept]
    assert kept

    topics = await build_topics(kept, job.spec.goal, job=job)
    print(f"topics: {len(topics)}")
    for t in topics:
        print(
            f"  {t.name!r}: {t.description} | {len(t.chunk_ids)} chunks | brief {len(t.brief.split())} words"
        )
    assert 1 <= len(topics) <= len(kept)
    assert all(c.topic_id for c in kept)
    assert sum(len(t.chunk_ids) for t in topics) == len(kept)

    index = await build_evidence(kept, job=job)
    print(f"evidence: {len(index.items)} items, kinds {Counter(e.kind for e in index.items)}")
    for e in index.items[:5]:
        print(
            f"  [{e.kind}] {e.name!r} = {e.value!r} span={e.span_text!r} ({e.start}-{e.end}) conf={e.confidence}"
        )
    assert index.items
    for e in index.items:
        assert docs[e.doc_id].text[e.start : e.end] == e.span_text
    first = index.items[0]
    assert first in index.find(first.name)
    assert index.by_chunk(first.chunk_id)

    r = Retriever(kept)
    hit = r.top_k(kept[0].text[:300], k=3)
    assert hit[0].id == kept[0].id
    assert r.top_k("anything", k=2, topic_id=kept[0].topic_id)[0].topic_id == kept[0].topic_id

    print("ledger:", ledger.summary(job.id).model_dump())


def test_evidence_index_find():
    from bob.core.models import Evidence

    items = [
        Evidence(
            id="1",
            chunk_id="c",
            doc_id="d",
            kind="feature",
            name="Recurring invoices",
            span_text="Recurring invoices",
            start=0,
            end=18,
            confidence=1.0,
        ),
        Evidence(
            id="2",
            chunk_id="c",
            doc_id="d",
            kind="setting",
            name="max_retries",
            span_text="max_retries",
            start=20,
            end=31,
            confidence=1.0,
        ),
    ]
    idx = EvidenceIndex(items)
    assert [e.id for e in idx.find("recurring invoice")] == ["1"]
    assert [e.id for e in idx.find("Max retries")] == ["2"]
    assert idx.find("bulk PDF export") == []
    assert idx.names({"setting"}) == {"max_retries"}
