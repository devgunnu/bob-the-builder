"""A4: build_report recount + DPO pair rules (pure code on hand-written rows)."""

from __future__ import annotations

from collections import Counter

from a4_inputs import make_job, make_row, make_rows

from bob.core.models import Candidate, CheckResult, GenContext, JobOptions, Message
from bob.pipeline.report import build_report, judge_agreement, reject_check, sample_ids, wilson_interval
from bob.pipeline.verify import build_dpo_pairs, natural_pairs, synthesized_pair


def test_report_matches_recount():
    job = make_job()
    rows = make_rows()
    rep = build_report(job, rows)
    kept = [r for r in rows if r.verdict == "kept"]
    assert sum(c["kept"] for c in rep.coverage) == len(kept)
    assert sum(c["rejected"] for c in rep.coverage) == len(rows) - len(kept)
    assert {c["cell_id"] for c in rep.coverage} == {c.id for c in job.plan.cells}
    assert rep.mix_coverage["persona"] == dict(Counter(r.coords["persona"] for r in kept))
    assert rep.mix_coverage["difficulty"] == {"single_fact": len(kept), "multi_step": 0}
    assert rep.reject_reasons == {"dedup": 1, "extract.names": 1, "judge": 1}
    assert rep.duplicates_removed == 1
    assert rep.judge_rate == round(3 / len(rows), 4)
    # routed+rejected agrees, routed+kept disagrees, audited+kept agrees -> 2/3
    assert rep.judge_agreement == round(2 / 3, 4)
    assert rep.pass_rate_by_check["format"] == 1.0
    assert rep.rounds[0]["n"] == 1 and sum(r["generated"] for r in rep.rounds) == len(rows)
    assert len(rep.sample_row_ids) == len(kept) and set(rep.sample_row_ids) <= {r.id for r in kept}
    assert rep.spot_check["n"] == 0 and rep.spot_check["jev_accuracy"] is None
    assert rep.token_stats["p50"] > 0
    assert build_report(job, []).judge_rate == 0.0


def test_spot_check_and_wilson():
    job = make_job()
    rows = make_rows()
    kept = [r for r in rows if r.verdict == "kept"]
    for i, r in enumerate(kept[:10]):
        r.spot_check = i != 0
    rep = build_report(job, rows)
    assert rep.spot_check["n"] == 10 and rep.spot_check["up"] == 9 and rep.spot_check["jev_accuracy"] == 0.9
    lo, hi = rep.spot_check["wilson95"]
    assert lo < 0.9 < hi and (lo, hi) == wilson_interval(9, 10)
    assert wilson_interval(0, 0) is None


def test_sample_is_stratified_by_cell():
    rows = [make_row(i, t, "answerable") for i, t in enumerate(["Rate limits"] * 60 + ["Crawling"] * 3)]
    ids = sample_ids(rows, 50)
    assert len(ids) == 50
    crawl = {r.id for r in rows if r.coords["topic"] == "Crawling"}
    assert crawl <= set(ids)  # the small cell is fully in the sample


def test_reject_check_and_agreement_edge():
    r = make_row(1, "Crawling", "unanswerable", "rejected", reject_check="numbers")
    assert reject_check(r) == "numbers"
    assert judge_agreement([make_row(2, "Crawling", "answerable")]) is None


def test_natural_pairs():
    good = make_row(1, "Crawling", "answerable")
    bad = make_row(2, "Crawling", "answerable", "rejected", reject_check="extract.names")
    dup = make_row(3, "Crawling", "answerable", "rejected", reject_check="dedup")
    bad.messages[0] = good.messages[0]
    dup.messages[0] = good.messages[0]
    pairs = natural_pairs([good, bad, dup])
    assert len(pairs) == 1
    p = pairs[0]
    assert p.mode == "natural" and p.row_id == good.id and p.rejected_checks == ["extract.names"]
    assert [m.role for m in p.prompt] == ["user"]


def _flawed(row) -> Candidate:
    return Candidate(
        id="f1",
        job_id=row.job_id,
        cell_id=row.cell_id,
        round=row.round,
        case_type=row.case_type,
        coords=row.coords,
        messages=[row.messages[0], Message(role="assistant", content="Free plan: 500 pages per minute.")],
        chunk_ids=[],
        writer_model="x",
        cost_usd=0.0,
    )


def test_synthesized_pair_needs_a_content_check():
    row = make_row(1, "Crawling", "answerable")
    fl = _flawed(row)
    ok = CheckResult(name="format", tier=1, passed=True, detail="ok")
    nums = CheckResult(
        name="numbers", tier=1, passed=False, detail="Number '500' is not in the cited passages"
    )
    p = synthesized_pair(row, fl, [ok, nums])
    assert p is not None and p.mode == "synthesized" and p.rejected_checks == ["numbers"]
    assert p.rejection_reason.startswith("Number '500'")
    assert synthesized_pair(row, fl, [CheckResult(name="format", tier=1, passed=False, detail="x")]) is None
    assert synthesized_pair(row, fl, [ok]) is None  # nothing caught the flaw
    err = CheckResult(name="provider_error", tier=2, passed=False, detail="Jev failed")
    assert synthesized_pair(row, fl, [ok, err]) is None


async def test_dpo_off_and_pair_modes():
    async def emit(_t: str, _d: dict) -> None:
        return None

    def ctx(mode: str) -> GenContext:
        return GenContext(
            job=make_job(JobOptions(dpo_mode=mode)),
            docs={},
            chunks={},
            topics={},
            evidence=None,  # type: ignore[arg-type]
            retriever=None,  # type: ignore[arg-type]
            seeds=[],
            emit=emit,
        )

    rows = make_rows()
    assert await build_dpo_pairs(rows, ctx("off")) == []
    assert await build_dpo_pairs(rows, ctx("pair")) == natural_pairs(rows)
