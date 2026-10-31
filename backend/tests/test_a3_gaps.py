"""A3 gap controller math on real model objects (no LLM call)."""

from datetime import UTC, datetime

from bob.config import default_model_roles
from bob.core.models import Cell, CostSummary, Job, JobSpec, Plan
from bob.pipeline.gaps import boosted_mix_weights, plan_gap_round
from tests.test_a3_generate import _demo_plan


def _job(budget: float = 10.0, total_usd: float = 0.0, candidates: int = 0, plan: Plan | None = None) -> Job:
    now = datetime.now(UTC)
    return Job(
        id="t-a3-gaps",
        spec=JobSpec(goal="g", sources=[], budget_usd=budget),
        owner_id="local",
        models=default_model_roles(),
        plan=plan,
        counts={"candidates": candidates},
        cost=CostSummary(total_usd=total_usd),
        created_at=now,
        updated_at=now,
    )


def _cell(
    i: int, target: int, kept: int, generated: int = 0, rejected: int = 0, enabled: bool = True
) -> Cell:
    return Cell(
        id=f"c{i}",
        coords={"topic": f"T{i}", "case_type": "answerable"},
        target=target,
        kept=kept,
        generated=generated,
        rejected=rejected,
        enabled=enabled,
    )


def test_gap_round_targets_thin_and_hard_cells():
    cells = [
        _cell(0, 20, 20, 30, 10),  # full: skipped
        _cell(1, 20, 15, 30, 5),  # thin: deficit 5 -> ceil(5 * 1.6) = 8
        _cell(2, 20, 4, 32, 28),  # hard: deficit 16 -> 26 -> ceil(26 * 1.5) = 39, weight 1.5
        _cell(3, 20, 0, enabled=False),  # disabled: skipped
    ]
    out = plan_gap_round(_job(), cells)
    assert [(c.id, n) for c, n in out] == [("c2", 39), ("c1", 8)]
    assert out[0][0].weight == 1.5 and out[1][0].weight == 1.0
    assert out[0][0] is cells[2]  # updated in place, so job.plan.cells keep the weight


def test_gap_round_budget_cap_scales_down():
    cells = [_cell(1, 20, 10), _cell(2, 20, 0)]  # n = 16 and 32
    # 0.95 * 2.0 - 1.5 = 0.4 left; 0.01 per candidate -> 40 of 48 fit -> scale 0.8333
    out = plan_gap_round(_job(budget=2.0, total_usd=1.5, candidates=150), cells)
    assert [(c.id, n) for c, n in out] == [("c2", 26), ("c1", 13)]
    assert plan_gap_round(_job(budget=1.0, total_usd=0.96, candidates=10), cells) == []


def test_mix_boost_follows_deficit():
    plan = _demo_plan()
    cell = plan.cells[0].model_copy(update={"target": 20})
    if "mix_kept" not in type(cell).model_fields:
        assert boosted_mix_weights(_job(plan=plan), cell) == {}
        return
    cell.mix_kept = {"persona": {"P0": 5, "P1": 5, "P2": 5, "P3": 0}}
    w = boosted_mix_weights(_job(plan=plan), cell)
    assert w["persona"] == {"P0": 0.0, "P1": 0.0, "P2": 0.0, "P3": 1.0}


def test_writer_rows_with_repeated_slot_numbers_fill_the_free_slots():
    # Some models number every row 1. Each row must still become a candidate, not just the first.
    from datetime import UTC, datetime

    from bob.config import default_model_roles
    from bob.core.models import Cell, GenContext, Job, JobSpec
    from bob.pipeline.generate import BatchResult, Slot, TopicContext, build_candidates

    now = datetime.now(UTC)
    job = Job(
        id="slots",
        spec=JobSpec(goal="g", sources=[]),
        owner_id="local",
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )

    async def emit(t, d):
        return None

    ctx = GenContext(
        job=job, docs={}, chunks={}, topics={}, evidence=None, retriever=None, seeds=[], emit=emit
    )
    cell = Cell(id="c1", coords={"topic": "Billing", "case_type": "answerable"}, target=3)
    coords = {"topic": "Billing", "case_type": "answerable", "persona": "p", "difficulty": "single_fact"}
    slots = [Slot(coords=coords, focus=["k1"]) for _ in range(3)]
    tc = TopicContext(value="Billing", prefix="", pool=["k1"], doc_of={"k1": "d1"})
    questions = ["Where do I see my invoices?", "Can I pay yearly instead?", "Why was my card charged twice?"]
    rows = [{"slot": 1, "user": q, "assistant": "Here is how.", "chunk_ids": ["k1"]} for q in questions]
    out = build_candidates(ctx, cell, "answerable", slots, BatchResult(rows=rows, cost_usd=0.3), tc, set(), 1)
    assert [c.messages[0].content for c in out] == questions
