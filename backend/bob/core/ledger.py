"""Cost ledger (CONTRACTS section 7, D26, D33). Owner: A1.

Every external call records here. Buckets are role names (`writer`, `judge`, `planner`, `fallback`) or
service names (`jev`, `scaledown`, `firecrawl`, `composio`). The only call form:

    record(job_id, bucket, *, calls=1, in_tokens=0, out_tokens=0, usd=None, model=None)

`usd=None`: the price comes from the job's ModelConfig override for that role (when the model matches), else
the registry (by `model`), else the config table (jev, scaledown: per M input tokens). No price -> the bucket
goes to `CostSummary.price_unknown`; no price is guessed. The LLM clients pass `usd` themselves (they price
cache read/write tokens), and `in_tokens` there includes the cache tokens.

Bedrock buckets (BEDROCK_BUCKETS) are billed to the user's AWS account (D26); the budget guard still covers
all buckets. `frontier_only_estimate_usd` = the token counts of every Writer and verify call (writer, judge,
fallback, jev, scaledown) priced at the judge role model price.

State lives in this process (the worker owns a job while it runs). `register_job(job)` binds the job's
model snapshot; `load(job_id, cost)` restores a saved CostSummary (resync / restart).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from bob.core.models import CostSummary, Job, ModelCost, ModelRoles

BEDROCK_BUCKETS = ("writer", "planner", "judge", "fallback")  # "billed to your AWS account"
FRONTIER_BUCKETS = ("writer", "judge", "fallback", "jev", "scaledown")
_ROLES = BEDROCK_BUCKETS


@dataclass
class _JobLedger:
    models: ModelRoles | None = None
    by_bucket: dict[str, ModelCost] = field(default_factory=dict)
    model_ids: dict[str, str] = field(default_factory=dict)
    price_unknown: set[str] = field(default_factory=set)
    fallbacks_used: list[str] = field(default_factory=list)


_lock = threading.Lock()
_jobs: dict[str, _JobLedger] = {}


def _get(job_id: str) -> _JobLedger:
    led = _jobs.get(job_id)
    if led is None:
        led = _jobs[job_id] = _JobLedger()
    return led


def register_job(job: Job) -> None:
    """Bind the job's model snapshot (role -> model id, price overrides, judge price)."""
    with _lock:
        led = _get(job.id)
        led.models = job.models
        for role in _ROLES:
            cfg = getattr(job.models, role) or job.models.writer
            led.model_ids.setdefault(role, cfg.model_id)


def load(job_id: str, cost: CostSummary) -> None:
    """Restore a saved CostSummary into the ledger (keeps the bound models)."""
    with _lock:
        led = _get(job_id)
        led.by_bucket = {k: v.model_copy() for k, v in cost.by_model.items()}
        led.model_ids.update(cost.model_ids)
        led.price_unknown = set(cost.price_unknown)
        led.fallbacks_used = list(cost.fallbacks_used)


def forget(job_id: str) -> None:
    with _lock:
        _jobs.pop(job_id, None)


def _price(led: _JobLedger, bucket: str, model: str | None) -> tuple[float, float] | None:
    """(in, out) USD per M tokens for a bucket, or None."""
    from bob.llm.registry import caps_for, caps_for_id

    if led.models is not None and bucket in _ROLES:
        cfg = getattr(led.models, bucket) or led.models.writer
        if model is None or model == cfg.model_id:
            caps = caps_for(cfg)
            return (caps.price_in_per_m, caps.price_out_per_m) if caps.price_known else None
    if bucket in ("jev", "scaledown"):
        from bob.config import get_settings

        s = get_settings()
        return (s.jev_price_in_per_m if bucket == "jev" else s.scaledown_price_in_per_m, 0.0)
    if model:
        caps = caps_for_id(model)
        return (caps.price_in_per_m, caps.price_out_per_m) if caps.price_known else None
    return None


def record(
    job_id: str,
    bucket: str,
    *,
    calls: int = 1,
    in_tokens: int = 0,
    out_tokens: int = 0,
    usd: float | None = None,
    model: str | None = None,
) -> None:
    with _lock:
        led = _get(job_id)
        if usd is None:
            price = _price(led, bucket, model)
            if price is None:
                led.price_unknown.add(bucket)
                usd = 0.0
            else:
                usd = (in_tokens * price[0] + out_tokens * price[1]) / 1_000_000
        mc = led.by_bucket.setdefault(bucket, ModelCost())
        mc.calls += calls
        mc.in_tokens += in_tokens
        mc.out_tokens += out_tokens
        mc.usd += usd
        if model and bucket in _ROLES:
            led.model_ids[bucket] = model


def mark_price_unknown(job_id: str, bucket: str) -> None:
    with _lock:
        _get(job_id).price_unknown.add(bucket)


def add_fallback(job_id: str, name: str) -> None:
    """Record a used fallback, e.g. "jev->scaledown_classify" (once per name)."""
    with _lock:
        led = _get(job_id)
        if name not in led.fallbacks_used:
            led.fallbacks_used.append(name)


def total_usd(job_id: str) -> float:
    with _lock:
        return sum(mc.usd for mc in _get(job_id).by_bucket.values())


def model_ids(job_id: str) -> dict[str, str]:
    with _lock:
        return dict(_get(job_id).model_ids)


def price_unknown(job_id: str) -> list[str]:
    with _lock:
        return sorted(_get(job_id).price_unknown)


def frontier_only_estimate_usd(job_id: str) -> float:
    """Writer + verify token counts priced at the judge role model price (0.0 when that price is unknown)."""
    with _lock:
        led = _get(job_id)
        price = _price(led, "judge", None) if led.models is not None else None
        if price is None:
            return 0.0
        tin = sum(led.by_bucket[b].in_tokens for b in FRONTIER_BUCKETS if b in led.by_bucket)
        tout = sum(led.by_bucket[b].out_tokens for b in FRONTIER_BUCKETS if b in led.by_bucket)
        return (tin * price[0] + tout * price[1]) / 1_000_000


frontier_only_estimate = frontier_only_estimate_usd  # CONTRACTS section 7 name


def summary(job_id: str) -> CostSummary:
    total = total_usd(job_id)
    frontier = frontier_only_estimate_usd(job_id)
    with _lock:
        led = _get(job_id)
        return CostSummary(
            by_model={k: v.model_copy() for k, v in led.by_bucket.items()},
            model_ids=dict(led.model_ids),
            price_unknown=sorted(led.price_unknown),
            total_usd=round(total, 6),
            frontier_only_estimate_usd=round(frontier, 6),
            fallbacks_used=list(led.fallbacks_used),
        )
