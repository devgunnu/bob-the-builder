"""A4: tier-3 judge with real calls to the judge role model (Bedrock Converse, default AWS chain).

Hand-written passages and rows go through the real judge prompt and the real model. Nothing is faked.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bob.config import default_bedrock_access, default_model_roles
from bob.core.models import Candidate, Chunk, GenContext, Job, JobSpec, Message
from bob.pipeline.verify import _DedupIndex, _Outcome, _VerifyState, judge

PASSAGE = (
    "Rate limits. The free plan allows 10 scrape requests per minute and 1 concurrent crawl job. "
    "The Hobby plan allows 100 scrape requests per minute and 5 concurrent crawl jobs. When you pass the limit, "
    "the API returns HTTP 429 with a Retry-After header."
)


def _ctx() -> GenContext:
    now = datetime.now(UTC)
    job = Job(
        id=f"t-a4-judge-{now:%Y%m%d}",
        spec=JobSpec(goal="Firecrawl first-reply support", sources=[]),
        owner_id="local",
        bedrock=default_bedrock_access(),
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )

    async def emit(_t: str, _d: dict) -> None:
        return None

    return GenContext(
        job=job,
        docs={},
        chunks={},
        topics={},
        evidence=None,
        retriever=None,
        seeds=[],
        emit=emit,  # type: ignore[arg-type]
    )


def _cand(reply: str, case: str = "answerable", absent: str | None = None) -> Candidate:
    return Candidate(
        id=f"c-{abs(hash(reply)) % 10**8}",
        job_id="t",
        cell_id="c1",
        round=1,
        case_type=case,
        coords={
            "topic": "Rate limits",
            "case_type": case,
            "persona": "Developer",
            "difficulty": "single_fact",
        },
        messages=[
            Message(
                role="user", content="hey, how many scrape requests per minute do I get on the free plan?"
            ),
            Message(role="assistant", content=reply),
        ],
        chunk_ids=["k1"],
        absent_topic=absent,
        writer_model="test",
        cost_usd=0.0,
    )


def _outcome() -> _Outcome:
    o = _Outcome()
    o.passages = [
        Chunk(
            id="k1", doc_id="d1", uri="upload://rl.md", text=PASSAGE, start=0, end=len(PASSAGE), n_tokens=60
        )
    ]
    return o


async def test_judge_keeps_a_grounded_reply_and_rejects_an_invented_one():
    import asyncio

    ctx = _ctx()
    st = _VerifyState(dedup=_DedupIndex(), judge_sem=asyncio.Semaphore(2))
    good = _cand(
        "On the free plan you get 10 scrape requests per minute. If you go over, the API answers with HTTP 429 "
        "and a Retry-After header, so wait that long before you retry."
    )
    bad = _cand(
        "On the free plan you get 10 scrape requests per minute, and you can turn on burst mode in the dashboard "
        "to get 50 per minute for short periods at no extra cost."
    )
    keep, reject = await asyncio.gather(judge(good, _outcome(), ctx, st), judge(bad, _outcome(), ctx, st))
    print(keep.detail, "|", reject.detail)
    assert keep.name == "judge" and keep.tier == 3
    assert keep.passed, keep.detail
    assert not reject.passed, reject.detail
    assert reject.detail.startswith("Judge: reject.")
