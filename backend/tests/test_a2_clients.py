"""A2 client tests: real Jev and ScaleDown calls (no mocks). Raw responses are printed (`pytest -s`)."""

import json

import a2_support
import pytest

from bob.clients import jev, scaledown
from bob.clients.jev import Question, decide
from bob.config import get_settings

TEXT = (
    "Refunds. Annual plans can be refunded within 30 days of purchase. Go to Billing > Plans and click "
    "Request refund. The setting max_retries defaults to 5. See https://example.com/docs/refunds for details."
)

QUESTIONS = [
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


@pytest.fixture
def job():
    s = get_settings()
    if not s.jev_api_key or not s.scaledown_api_key:
        pytest.fail("JEV_API_KEY and SCALEDOWN_API_KEY must be set (real calls only)")
    return a2_support.make_job()


async def test_jev_raw_and_decide(job):
    s = get_settings()
    state = "USER: How do I get a refund?\nASSISTANT: Click Request refund."
    body = jev.build_request(s.jev_model, state, QUESTIONS)
    raw, _ = await jev.post_json(
        "jev",
        s.jev_base_url + jev.JEV_PATH,
        {"Authorization": f"Bearer {s.jev_api_key}"},
        body,
        model=s.jev_model,
        concurrency=2,
        timeout=60,
    )
    print("JEV RAW:", json.dumps(raw))
    assert set(raw["answers"]) == {"answers", "topic", "quality"}

    state = jev.dumps_state(
        USER="How do I get a refund for an annual plan?",
        ASSISTANT="Go to Billing > Plans and click Request refund within 30 days of purchase.",
    )
    out = await decide(state, QUESTIONS, "probe", job=job)
    print("JEV DECIDE:", {k: v.model_dump() for k, v in out.items()})
    assert isinstance(out["answers"].value, bool) and 0 <= out["answers"].prob <= 1
    assert out["topic"].value == "refunds and billing"
    assert out["quality"].value in QUESTIONS[2].levels and 0 <= out["quality"].prob <= 1
    assert job.cost.fallbacks_used == []


async def test_scaledown_extract(job):
    schema = {
        "type": "object",
        "properties": {
            "features": {"type": "array", "items": {"type": "string"}, "description": "product features"},
            "settings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                },
                "description": "configuration settings with their values",
            },
            "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs"},
        },
    }
    fields = await scaledown.extract(TEXT, schema, "probe", job=job)
    print("EXTRACT:", [f.model_dump() for f in fields])
    assert job.cost.fallbacks_used == [], job.cost.fallbacks_used
    assert fields, "Extract returned no verbatim fields"
    for f in fields:
        assert TEXT[f.start : f.end] == f.span_text
    assert any("example.com/docs/refunds" in f.span_text for f in fields)


async def test_scaledown_summarize_classify_compress(job):
    summary = await scaledown.summarize(TEXT, "probe", "One sentence.", job=job)
    print("SUMMARY:", summary)
    assert summary

    scores = await scaledown.classify(TEXT, ["refunds", "login problems"], "probe", job=job)
    print("CLASSIFY:", scores)
    assert max(scores, key=scores.get) == "refunds"
    assert abs(sum(scores.values()) - 1.0) < 0.01

    small = await scaledown.compress(TEXT * 3, job=job, prompt="How do refunds work?")
    print("COMPRESS:", small)
    assert small
