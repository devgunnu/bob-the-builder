"""core/cache.py and core/ledger.py (local blobs on disk under BOB_RUNS_DIR)."""

from datetime import UTC, datetime

from bob.config import default_model_roles, get_settings
from bob.core import cache, ledger
from bob.core.models import CostSummary, Job, JobSpec, ModelConfig


def _job(job_id: str, models=None) -> Job:
    now = datetime.now(UTC)
    return Job(
        id=job_id,
        spec=JobSpec(goal="g", sources=[]),
        owner_id="local",
        models=models or default_model_roles(),
        created_at=now,
        updated_at=now,
    )


async def test_cache_roundtrip_and_off(monkeypatch):
    body = {"b": 1, "a": [1, 2]}
    assert cache.cache_key("e", "m", body) == cache.cache_key("e", "m", {"a": [1, 2], "b": 1})
    assert await cache.get("e", "m", {"x": "miss"}) is None
    await cache.put("e", "m", body, {"output": "real"})
    assert await cache.get("e", "m", body) == {"output": "real"}
    p = get_settings().runs_dir / "_blobs" / "cache" / f"{cache.cache_key('e', 'm', body)}.json"
    assert p.resolve().is_file()
    monkeypatch.setenv("BOB_CACHE", "0")
    get_settings.cache_clear()
    try:
        assert await cache.get("e", "m", body) is None
    finally:
        get_settings.cache_clear()


def test_ledger_prices_and_frontier():
    job = _job("led-1")
    ledger.register_job(job)
    ledger.record(job.id, "writer", in_tokens=1_000_000, out_tokens=1_000_000)  # haiku 0.10 + 0.50
    ledger.record(job.id, "jev", in_tokens=1_000_000)  # 0.042
    ledger.record(job.id, "firecrawl", usd=0.01)
    ledger.record(job.id, "composio")  # no price -> unknown, never guessed
    s = ledger.summary(job.id)
    assert abs(s.by_model["writer"].usd - 0.60) < 1e-9
    assert abs(s.by_model["jev"].usd - 0.042) < 1e-9
    assert abs(s.total_usd - 0.652) < 1e-6
    assert s.price_unknown == ["composio"]
    assert s.model_ids["writer"] == job.models.writer.model_id
    # frontier: writer + jev tokens at the judge (sonnet 2/10) price = 2*2 + 10*1
    assert abs(s.frontier_only_estimate_usd - 14.0) < 1e-6
    assert ledger.frontier_only_estimate(job.id) == ledger.frontier_only_estimate_usd(job.id)


def test_ledger_override_and_unknown_model():
    models = default_model_roles().model_copy(
        update={"writer": ModelConfig(model_id="vendor.unknown-1", price_in_per_m=1.0, price_out_per_m=2.0)}
    )
    job = _job("led-2", models)
    ledger.register_job(job)
    ledger.record(job.id, "writer", in_tokens=1_000_000, out_tokens=0, model="vendor.unknown-1")
    ledger.record(job.id, "planner", in_tokens=10, model="vendor.other-2")  # model not in the snapshot
    assert abs(ledger.total_usd(job.id) - 1.0) < 1e-9
    assert ledger.price_unknown(job.id) == ["planner"]
    ledger.load(job.id, CostSummary())
    assert ledger.total_usd(job.id) == 0.0
