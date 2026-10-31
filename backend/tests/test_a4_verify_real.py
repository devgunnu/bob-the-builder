"""A4: verify() end to end with real ScaleDown Extract, real Jev and the real judge model.

Waits on A2 (`bob.clients.jev`, `bob.clients.scaledown`, `bob.pipeline.evidence`, `bob.pipeline.embed`,
`bob.pipeline.chunk`). Skips until they exist. Inputs are hand-written candidates (CONTRACTS definition of
done) sent through real code and real calls; the document is a hand-written real text.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

pytest.importorskip("bob.clients.jev")
pytest.importorskip("bob.clients.scaledown")
pytest.importorskip("bob.pipeline.evidence")
pytest.importorskip("bob.pipeline.embed")
pytest.importorskip("bob.pipeline.chunk")

from bob.config import default_bedrock_access, default_model_roles  # noqa: E402
from bob.core import ledger  # noqa: E402
from bob.core.models import Candidate, Document, GenContext, Job, JobSpec, Message, Topic  # noqa: E402
from bob.pipeline.verify import verify  # noqa: E402

DOC = """# Rate limits

Every plan has a limit on scrape requests per minute. The free plan allows 10 scrape requests per minute
and 1 concurrent crawl job. The Hobby plan allows 100 scrape requests per minute and 5 concurrent crawl jobs.
When you pass the limit, the API returns HTTP 429 with a Retry-After header that tells you how many seconds to
wait before the next request.

# Refunds

You can ask for a refund within 30 days of payment. Send the request to billing support from the dashboard.
Refunds go back to the original payment method in 5 to 10 business days.
"""


async def _ctx() -> GenContext:
    from bob.pipeline.chunk import chunk_documents  # A2
    from bob.pipeline.evidence import Retriever, build_evidence  # A2

    now = datetime.now(UTC)
    job = Job(
        id=f"t-a4-verify-{now:%Y%m%d}",
        spec=JobSpec(goal="First-reply support assistant", sources=[]),
        owner_id="local",
        bedrock=default_bedrock_access(),
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )
    ledger.register_job(job)
    doc = Document(
        id="doca4",
        source_kind="upload",
        uri="upload://a4-docs.md",
        title="A4 docs",
        text=DOC,
        content_hash="x",
        fetched_at=now,
    )
    chunks = chunk_documents([doc])
    kw = {"job": job} if "job" in inspect.signature(build_evidence).parameters else {}
    evidence = await build_evidence(chunks, **kw)
    topics = {"t1": Topic(id="t1", name="Rate limits", description="", chunk_ids=[c.id for c in chunks])}
    topics["t2"] = Topic(id="t2", name="Refunds", description="", chunk_ids=[c.id for c in chunks])

    async def emit(_t: str, _d: dict) -> None:
        return None

    return GenContext(
        job=job,
        docs={doc.id: doc},
        chunks={c.id: c for c in chunks},
        topics=topics,
        evidence=evidence,
        retriever=Retriever(chunks),
        seeds=[],
        emit=emit,
    )


def _cand(cid: str, ctx: GenContext, case: str, topic: str, user: str, reply: str, **kw) -> Candidate:
    return Candidate(
        id=cid,
        job_id=ctx.job.id,
        cell_id=f"{topic}-{case}",
        round=1,
        case_type=case,
        coords={"topic": topic, "case_type": case, "persona": "Developer", "difficulty": "single_fact"},
        messages=[Message(role="user", content=user), Message(role="assistant", content=reply)],
        chunk_ids=list(ctx.chunks),
        writer_model="hand-written",
        cost_usd=0.0,
        **kw,
    )


async def test_verify_real_cases():
    ctx = await _ctx()
    ev_30 = next((e for e in ctx.evidence.items if "30" in (e.value or "") + e.span_text), None)
    cands = [
        _cand(
            "inv",
            ctx,
            "answerable",
            "Rate limits",
            "hey, how many scrape requests per minute do I get on the free plan?",
            "The free plan gives you 10 scrape requests per minute. You can also switch on burst mode in the "
            "dashboard to go past that for short spikes.",
        ),
        _cand(
            "abs",
            ctx,
            "unanswerable",
            "Refunds",
            "Can I get my refund paid out as store credit instead of back to my card?",
            "Our docs do not cover refunds as store credit, so I cannot confirm that option. I can hand this to "
            "our billing team, and a person will reply to you.",
            absent_topic="refunds as store credit",
        ),
        _cand(
            "fp",
            ctx,
            "false_premise",
            "Refunds",
            "I read that I have 60 days to ask for a refund, so I can wait until next month, right?",
            "The refund window is 30 days from payment, not 60. Please send the request from the dashboard to "
            "billing support before the 30 days end.",
            premise_evidence_id=ev_30.id if ev_30 else None,
        ),
    ]
    rows = {r.id: r for r in await verify(cands, ctx)}
    for r in rows.values():
        print(r.id, r.verdict, r.reject_reason, [(c.name, c.passed, c.detail) for c in r.checks])
    inv = rows["inv"]
    assert inv.verdict == "rejected"
    names = next(c for c in inv.checks if c.name == "extract.names")
    assert not names.passed and "which is not in the docs" in names.detail
    abs_names = next(c for c in rows["abs"].checks if c.name == "extract.names")
    assert abs_names.passed
    fp_numbers = next(c for c in rows["fp"].checks if c.name == "numbers")
    assert fp_numbers.passed, fp_numbers.detail
    for r in rows.values():
        assert r.coords["persona"] == "Developer" and r.spans
