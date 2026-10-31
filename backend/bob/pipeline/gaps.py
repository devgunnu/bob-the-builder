"""Gap controller: which cells get more rows in the next round, and how many (CONTRACTS section 3). Owner: A3.

Rules (A3 brief): deficit = target - kept; skip deficit <= 0; n = ceil(deficit * OVERGEN). A hard cell
(rejected / generated > 0.5) gets weight x 1.5 and n x 1.5; generate() then uses the strict prompt for it.
Under-covered mix values get more of the cell's next batches (Cell.mix_weights, when the model has it).
The total is capped so the estimated cost fits in 0.95 * budget - total_usd (all cells scaled down).
"""

from __future__ import annotations

import math

from bob.config import settings_for
from bob.core.models import Cell, Job
from bob.pipeline.generate import is_hard
from bob.pipeline.planner import normalize_weights

HARD_BOOST = 1.5
BUDGET_SHARE = 0.95


def boosted_mix_weights(job: Job, cell: Cell) -> dict[str, dict[str, float]]:
    """Next-batch shares per mix axis: proportional to each value's deficit (weight x target - kept).

    Needs the kept count per mix value of the cell (`Cell.mix_kept`, A1 fills it). Without it, or when no value
    is behind, the plan weights stay (empty result)."""
    kept = getattr(cell, "mix_kept", None) or {}
    plan = job.plan
    if not plan or not kept:
        return {}
    out: dict[str, dict[str, float]] = {}
    for axis in plan.axes:
        if axis.role != "mix" or axis.name in cell.coords:
            continue
        w = normalize_weights(axis.values, axis.weights)
        counts = kept.get(axis.name, {})
        deficit = {v: max(0.0, w[v] * cell.target - counts.get(v, 0)) for v in axis.values}
        if sum(deficit.values()) <= 0:
            continue
        out[axis.name] = normalize_weights(axis.values, deficit)
    return out


def cost_per_candidate(job: Job) -> float | None:
    """Real average cost per candidate so far (all buckets), or None before the first candidate."""
    n = job.counts.get("candidates", 0)
    if n <= 0 or job.cost.total_usd <= 0:
        return None
    return job.cost.total_usd / n


def plan_gap_round(job: Job, cells: list[Cell]) -> list[tuple[Cell, int]]:
    """(cell, n) for the next round, largest deficit first. The returned cells are copies with the new weight
    (and mix weights); the caller stores them."""
    s = settings_for(job)
    picks: list[tuple[Cell, int, int]] = []
    for c in cells:
        if not c.enabled:
            continue
        deficit = c.target - c.kept
        if deficit <= 0:
            continue
        n = math.ceil(deficit * s.overgen)
        upd: dict = {}
        if is_hard(c):
            upd["weight"] = c.weight * HARD_BOOST
            n = math.ceil(n * HARD_BOOST)
        if "mix_weights" in type(c).model_fields:
            upd["mix_weights"] = boosted_mix_weights(job, c)
        picks.append((c.model_copy(update=upd), n, deficit))

    remaining = BUDGET_SHARE * job.spec.budget_usd - job.cost.total_usd
    if remaining <= 0:
        return []
    per = cost_per_candidate(job)
    total_n = sum(n for _, n, _ in picks)
    if per is not None and total_n * per > remaining:
        scale = remaining / (total_n * per)
        picks = [(c, math.floor(n * scale), d) for c, n, d in picks]
        picks = [p for p in picks if p[1] > 0]
    picks.sort(key=lambda p: (-p[2], p[0].id))
    return [(c, n) for c, n, _ in picks]
