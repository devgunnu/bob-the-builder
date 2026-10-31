"""A2 fallback chains with forced real failures (env overrides) and real fallback calls. No mocks.

- Jev with an unknown model (real HTTP 400) -> Noul/Choice by ScaleDown Classify, Score by the fallback model.
- Jev and ScaleDown both with bad credentials (real HTTP 400/401) -> everything by the fallback model.
- ScaleDown Extract with a bad key (real HTTP 401) -> fallback model extraction + the verbatim-span check.
"""

import a2_support
import pytest

from bob.clients import scaledown
from bob.clients.jev import Question, decide, dumps_state
from bob.config import get_settings
from bob.core import ledger

STATE = dumps_state(
    USER="How do I get a refund for an annual plan?",
    ASSISTANT="Go to Billing > Plans and click Request refund within 30 days of purchase.",
)
QS = [
    Question(id="answers", type="noul", prompt="The ASSISTANT reply directly resolves what the USER asked"),
    Question(
        id="topic",
        type="choice",
        prompt="Which topic is the USER message about?",
        options=["refunds and billing", "account login", "api errors"],
    ),
    Question(
        id="quality",
        type="score",
        prompt="Rate the ASSISTANT reply as a support answer",
        levels=["unusable", "poor", "acceptable", "good", "excellent"],
    ),
]
TEXT = (
    "Refunds. Annual plans can be refunded within 30 days of purchase. Go to Billing > Plans and click "
    "Request refund. The setting max_retries defaults to 5. See https://example.com/docs/refunds for details."
)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("BOB_CACHE", "0")  # every call is a fresh real call
    yield monkeypatch
    monkeypatch.undo()
    get_settings.cache_clear()


def _job(name):
    get_settings.cache_clear()
    j = a2_support.make_job(name)
    ledger.register_job(j)
    return j


async def test_jev_failure_uses_classify_then_fallback_model(env):
    env.setenv("JEV_MODEL", "jev-does-not-exist")
    job = _job("a2-fb-1")
    out = await decide(STATE, QS, "probe", job=job)
    print("DECIDE via fallbacks:", {k: v.model_dump() for k, v in out.items()})
    print("fallbacks_used:", ledger.summary(job.id).fallbacks_used)
    assert out["topic"].value == "refunds and billing"
    assert isinstance(out["answers"].value, bool)
    assert out["quality"].value in QS[2].levels
    used = ledger.summary(job.id).fallbacks_used
    assert "jev->scaledown_classify" in used and "jev->fallback_model" in used
    assert ledger.summary(job.id).by_model["scaledown"].calls == 2  # Classify for Noul + Choice
    assert ledger.summary(job.id).by_model["fallback"].calls == 1  # Score


async def test_jev_and_classify_failure_use_fallback_model(env):
    env.setenv("JEV_MODEL", "jev-does-not-exist")
    env.setenv("SCALEDOWN_API_KEY", "bad-key")
    job = _job("a2-fb-2")
    out = await decide(STATE, QS, "probe", job=job)
    print("DECIDE via model:", {k: v.model_dump() for k, v in out.items()})
    used = ledger.summary(job.id).fallbacks_used
    print("fallbacks_used:", used)
    assert "scaledown_classify->fallback_model" in used
    assert out["topic"].value == "refunds and billing"
    assert out["answers"].prob > 0.5


async def test_extract_failure_uses_fallback_model(env):
    env.setenv("SCALEDOWN_API_KEY", "bad-key")
    job = _job("a2-fb-3")
    from bob.pipeline.evidence import EVIDENCE_SCHEMA

    fields = await scaledown.extract(TEXT, EVIDENCE_SCHEMA, "probe", job=job)
    print("EXTRACT via model:", [f.model_dump() for f in fields])
    assert "scaledown_extract->fallback_model" in ledger.summary(job.id).fallbacks_used
    assert fields
    for f in fields:
        assert TEXT[f.start : f.end] == f.span_text
