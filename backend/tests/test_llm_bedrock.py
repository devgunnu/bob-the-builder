"""Real Bedrock Converse calls on the default models (BOB_BEDROCK_AUTH=default, the default AWS chain)."""

from datetime import UTC, datetime

import pytest

from bob.config import default_bedrock_access, default_model_roles
from bob.core import ledger
from bob.core.models import Job, JobSpec, Message, ModelConfig, ModelRoles
from bob.llm.client import LLMClient, get_llm
from bob.llm.registry import caps_for, caps_for_id, strip_region

SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}, "country": {"type": "string"}},
    "required": ["city", "country"],
    "additionalProperties": False,
}
ASK = [Message(role="user", content="Name the capital city of France and its country.")]


def _job(models: ModelRoles | None = None, job_id: str | None = None) -> Job:
    now = datetime.now(UTC)
    return Job(
        id=job_id or f"t-llm-{now.timestamp():.0f}",
        spec=JobSpec(goal="llm test", sources=[]),
        owner_id="local",
        bedrock=default_bedrock_access(),
        models=models or default_model_roles(),
        created_at=now,
        updated_at=now,
    )


def test_registry_rules():
    assert strip_region("global.anthropic.claude-haiku-5-5") == "anthropic.claude-haiku-5-5"
    haiku = caps_for_id("global.anthropic.claude-haiku-5-5")
    assert haiku.json_mode == "native" and haiku.cache and not haiku.allows_temperature
    assert haiku.price_in_per_m == 0.10 and haiku.price_out_per_m == 0.50
    assert caps_for_id("us.amazon.nova-2-lite-v1:0").json_mode == "tool"
    unknown = caps_for_id("some.vendor-model-v9")
    assert unknown.json_mode == "prompt" and not unknown.cache and not unknown.price_known
    over = caps_for(
        ModelConfig(model_id="global.anthropic.claude-haiku-5-5", json_mode="prompt", cache="off")
    )
    assert over.json_mode == "prompt" and not over.cache


@pytest.mark.parametrize("role", ["writer", "planner"])
async def test_default_models_real_json(role, monkeypatch):
    monkeypatch.setenv("BOB_CACHE", "0")
    from bob.config import get_settings

    get_settings.cache_clear()
    job = _job()
    llm = get_llm(job, role)
    assert isinstance(llm, LLMClient)
    val, usage = await llm.complete_json(role, "You answer geography questions.", ASK, SCHEMA)
    assert "paris" in val["city"].lower()
    assert usage.in_tokens > 0 and usage.out_tokens > 0
    assert usage.model_id == getattr(job.models, role).model_id
    cost = ledger.summary(job.id)
    assert cost.by_model[role].calls == 1 and cost.by_model[role].usd > 0
    get_settings.cache_clear()


async def test_text_and_cache_point_real():
    job = _job()
    llm = get_llm(job, "writer")
    prefix = "Reference facts. " + " ".join(f"Item {i} costs {i * 7} credits." for i in range(400))
    usages = []
    for _ in range(2):
        text, usage = await llm.complete_text(
            "writer",
            "Answer from the reference facts in one short line.",
            [Message(role="user", content=f"What does item 12 cost? ({job.id})")],
            cache_prefix=prefix,
        )
        usages.append(usage)
    assert "84" in text
    # first call writes the prompt cache or reads it; the second reads it or comes from the disk cache
    assert usages[0].cache_write_tokens + usages[0].cache_read_tokens > 0


async def test_nova_tool_mode_real(monkeypatch):
    """A non-Anthropic model through the registry (tool JSON mode)."""
    monkeypatch.setenv("BOB_CACHE", "0")
    from bob.config import get_settings

    get_settings.cache_clear()
    base = default_model_roles()
    models = base.model_copy(update={"writer": ModelConfig(model_id="us.amazon.nova-2-lite-v1:0")})
    job = _job(models)
    val, usage = await get_llm(job, "writer").complete_json(
        "writer", "You answer geography questions.", ASK, SCHEMA
    )
    assert "paris" in val["city"].lower()
    assert "writer" in ledger.price_unknown(job.id)  # no registry price for Nova: never guessed
    get_settings.cache_clear()


def test_nested_schema_objects_are_strict_without_mutation():
    from bob.llm.bedrock import _strip_schema

    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"name": {"type": "string"}}},
            }
        },
    }
    result = _strip_schema(schema)
    assert result["additionalProperties"] is False
    assert result["properties"]["items"]["items"]["additionalProperties"] is False
    assert "additionalProperties" not in schema
