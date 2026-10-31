"""Data quality report (CONTRACTS sections 2 and 4). Owner: A4.

`build_report(job, rows)` is a pure recount from the rows (and the job's plan), so the numbers always match
a recount from rows.jsonl. `rows` = every verified candidate (kept and rejected).
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict

from bob.core.models import Job, Report, Row

SAMPLE_SIZE = 50


def wilson_interval(up: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson 95% interval for the share up/n."""
    if n <= 0:
        return None
    p = up / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def reject_check(row: Row) -> str:
    """Name of the check that rejected the row (the judge, or the check whose detail is the reject reason)."""
    for c in row.checks:
        if c.name == "judge" and not c.passed:
            return "judge"
    for c in row.checks:
        if not c.passed and c.detail == row.reject_reason:
            return c.name
    failed = [c for c in row.checks if not c.passed]
    return failed[0].name if failed else "unknown"


def _tokens(row: Row) -> int:
    return round(sum(len(m.content.split()) for m in row.messages) * 1.3)  # words x 1.3 (A2 estimate)


def _pct(values: list[int], q: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(q * len(s)) - 1))
    return s[k]


def sample_ids(rows: list[Row], n: int = SAMPLE_SIZE) -> list[str]:
    """n kept rows, stratified by cell: round-robin over cells, stable order inside each cell."""
    by_cell: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.verdict == "kept":
            by_cell[r.cell_id].append(r)
    queues = [
        sorted(rs, key=lambda r: hashlib.sha1(f"sample:{r.id}".encode()).hexdigest())
        for _, rs in sorted(by_cell.items())
    ]
    out: list[str] = []
    depth = 0
    while len(out) < n and any(depth < len(q) for q in queues):
        for q in queues:
            if depth < len(q) and len(out) < n:
                out.append(q[depth].id)
        depth += 1
    return out


def judge_agreement(rows: list[Row]) -> float | None:
    """Tier-2 route vs judge verdict on routed + audited rows. Audited rows: tier 2 said keep. Routed rows:
    tier 2 did not keep (a soft check failed), so agreement = the judge rejects."""
    n = agree = 0
    for r in rows:
        j = next((c for c in r.checks if c.name == "judge"), None)
        if j is None or not (r.routed_to_judge or r.audited) or j.detail.startswith("Judge call failed"):
            continue
        tier2_keep = r.audited and not r.routed_to_judge
        n += 1
        agree += int(j.passed == tier2_keep)
    return round(agree / n, 4) if n else None


def build_report(job: Job, rows: list[Row]) -> Report:
    kept = [r for r in rows if r.verdict == "kept"]
    rejected = [r for r in rows if r.verdict == "rejected"]

    # coverage per cell (plan cells first, then any other cell seen in rows)
    kept_by_cell = Counter(r.cell_id for r in kept)
    rej_by_cell = Counter(r.cell_id for r in rejected)
    coverage: list[dict] = []
    seen: set[str] = set()
    cell_axes: set[str] = set()
    if job.plan:
        for c in job.plan.cells:
            seen.add(c.id)
            cell_axes |= set(c.coords)
            coverage.append(
                {
                    "cell_id": c.id,
                    "coords": dict(c.coords),
                    "target": c.target,
                    "enabled": c.enabled,
                    "kept": kept_by_cell[c.id],
                    "rejected": rej_by_cell[c.id],
                }
            )
    for r in rows:
        if r.cell_id not in seen:
            seen.add(r.cell_id)
            coverage.append(
                {
                    "cell_id": r.cell_id,
                    "coords": {k: v for k, v in r.coords.items() if k in cell_axes or not cell_axes},
                    "target": 0,
                    "enabled": True,
                    "kept": kept_by_cell[r.cell_id],
                    "rejected": rej_by_cell[r.cell_id],
                }
            )

    # mix coverage: kept rows per value of each mix axis
    mix_coverage: dict[str, dict[str, int]] = {}
    mix_axes = [a for a in job.plan.axes if a.role == "mix"] if job.plan else []
    for a in mix_axes:
        mix_coverage[a.name] = {v: 0 for v in a.values}
    if not mix_axes:
        for name in ("persona", "difficulty"):
            if name not in cell_axes:
                mix_coverage[name] = {}
    for r in kept:
        for axis, counts in mix_coverage.items():
            v = r.coords.get(axis)
            if v is not None:
                counts[v] = counts.get(v, 0) + 1

    # checks
    ran: Counter[str] = Counter()
    passed: Counter[str] = Counter()
    for r in rows:
        for c in r.checks:
            ran[c.name] += 1
            passed[c.name] += int(c.passed)
    pass_rate = {k: round(passed[k] / ran[k], 4) for k in sorted(ran)}
    reject_reasons = dict(Counter(reject_check(r) for r in rejected).most_common())
    duplicates = sum(1 for r in rejected if reject_check(r) == "dedup")

    to_judge = sum(1 for r in rows if r.routed_to_judge or r.audited)

    spot = [r for r in kept if r.spot_check is not None]
    up = sum(1 for r in spot if r.spot_check)
    spot_check: dict = {
        "n": len(spot),
        "up": up,
        "down": len(spot) - up,
        "jev_accuracy": round(up / len(spot), 4) if spot else None,
        "wilson95": list(wilson_interval(up, len(spot)) or []) or None,
    }

    toks = [_tokens(r) for r in kept]
    token_stats = {"p50": _pct(toks, 0.5), "p95": _pct(toks, 0.95), "max": max(toks) if toks else 0}

    by_round: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        by_round[r.round].append(r)
    rounds = [
        {
            "n": n,
            "cells": len({r.cell_id for r in rs}),
            "generated": len(rs),
            "kept": sum(1 for r in rs if r.verdict == "kept"),
            "rejected": sum(1 for r in rs if r.verdict == "rejected"),
        }
        for n, rs in sorted(by_round.items())
    ]

    return Report(
        coverage=coverage,
        mix_coverage=mix_coverage,
        pass_rate_by_check=pass_rate,
        reject_reasons=reject_reasons,
        duplicates_removed=duplicates,
        judge_rate=round(to_judge / len(rows), 4) if rows else 0.0,
        judge_agreement=judge_agreement(rows),
        spot_check=spot_check,
        sample_row_ids=sample_ids(rows),
        token_stats=token_stats,
        rounds=rounds,
    )
