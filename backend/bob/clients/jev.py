"""Jev decision client (CONTRACTS section 5, D34). Owner: A2.

Direct Jev API (typesafe.ai), raw httpx, no OpenAI SDK, no temperature / max_tokens.
Confirmed at the first real call (2026-10-30):
  POST {JEV_BASE_URL}/v1/systemone   JEV_BASE_URL = https://api.typesafe.ai
  Authorization: Bearer <JEV_API_KEY>
  request  {"model", "state", "questions": {<id>: {"type": "noul"|"choice"|"score", "instructions", "criteria"}}}
           choice criteria = {option: description}; score criteria = [level0, level1, ...] (ordered)
  response {"model": "jev-1.14.0", "answers": {<id>: ...}, "usage": {"input_tokens", "output_tokens"}}
           noul   {"type": "noul", "noul": p_yes}
           choice {"type": "choice", "choice": name, "confidence", "probabilities": {name: p}}
           score  {"type": "score", "score": 0..n-1 (expected level), "confidence", "legend", "probabilities"}
  models: jev-1.14.0, jev-1.13.0, aliases jev-latest / jev-preview. The OpenRouter form
  "typesafe/jev-1.13-20260917" is rejected (400 Unknown model).

This module also holds the shared HTTP helper (`post_json`: semaphore, 3 tries with exponential backoff,
real-response cache, ledger) that `clients/scaledown.py` uses.

Fallback chain (CONTRACTS section 5): when the Jev call fails after its 3 tries, Noul and Choice questions
go to ScaleDown Classify, then to the fallback model JSON answer (`get_llm(job, "fallback")`). Score has no
Classify equivalent and goes straight to the fallback model. Each switch is added to
`job.cost.fallbacks_used` and emitted as a `log` event.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from bob.config import settings_for
from bob.core import cache, ledger
from bob.core.models import Job, Message

log = logging.getLogger(__name__)

JEV_PATH = "/v1/systemone"
JEV_TIMEOUT_S = 60.0
TRIES = 3
BACKOFF_S = 0.5


# ---------------------------------------------------------------- models
class Question(BaseModel):
    id: str
    type: Literal["noul", "choice", "score"]
    prompt: str
    options: list[str] | None = None  # choice: <= 255 descriptive names
    levels: list[str] | None = None  # score: 2-10 ordered levels


class Decision(BaseModel):
    value: str | bool | float  # noul: bool (p >= 0.5); choice: top option; score: nearest level name
    prob: float  # noul: P(yes); choice: P(top); score: normalized 0..1
    probs: dict[str, float] = {}  # noul: {"yes", "no"}; choice: option -> p; score: level -> p


class ClientError(RuntimeError):
    """A real call failed after its tries. `status` is the HTTP status (None = transport error)."""

    def __init__(self, service: str, status: int | None, message: str):
        super().__init__(f"{service}: {status if status is not None else 'transport'}: {message}")
        self.service = service
        self.status = status


# ---------------------------------------------------------------- shared HTTP helper
_sems: dict[tuple[int, str], asyncio.Semaphore] = {}
_clients: dict[int, httpx.AsyncClient] = {}


def _semaphore(service: str, limit: int) -> asyncio.Semaphore:
    key = (id(asyncio.get_running_loop()), service)
    sem = _sems.get(key)
    if sem is None:
        sem = _sems[key] = asyncio.Semaphore(limit)
    return sem


def _client() -> httpx.AsyncClient:
    key = id(asyncio.get_running_loop())
    c = _clients.get(key)
    if c is None or c.is_closed:
        c = _clients[key] = httpx.AsyncClient(limits=httpx.Limits(max_connections=64))
    return c


def record_cost(
    job: Job, bucket: str, *, in_tokens: int = 0, out_tokens: int = 0, usd: float | None, model: str
) -> None:
    """Ledger entry for one real call (A1 `core/ledger.py`, CONTRACTS section 7). Cache hits cost nothing."""
    ledger.record(job.id, bucket, calls=1, in_tokens=in_tokens, out_tokens=out_tokens, usd=usd, model=model)


def _retryable(status: int) -> bool:
    return status in (408, 409, 425, 429) or status >= 500


async def post_json(
    service: str,
    url: str,
    headers: dict[str, str],
    body: dict,
    *,
    model: str,
    concurrency: int,
    timeout: float,
) -> tuple[dict, bool]:
    """POST JSON with the service semaphore, 3 tries (exponential backoff + jitter) and the real-response cache.

    Returns (response JSON, from_cache). Non-retryable 4xx fails at once. Raises ClientError on failure.
    """
    cached = await cache.get(url, model, body)
    if cached is not None:
        return cached, True
    last: ClientError | None = None
    for attempt in range(TRIES):
        if attempt:
            await asyncio.sleep(BACKOFF_S * 2 ** (attempt - 1) * (1 + random.random()))
        try:
            async with _semaphore(service, concurrency):
                r = await _client().post(url, headers=headers, json=body, timeout=timeout)
        except httpx.HTTPError as e:
            last = ClientError(service, None, f"{type(e).__name__}: {e}")
            continue
        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError:
                last = ClientError(service, 200, f"not JSON: {r.text[:300]}")
                continue
            await cache.put(url, model, body, data)
            return data, False
        last = ClientError(service, r.status_code, r.text[:500])
        if not _retryable(r.status_code):
            break
    assert last is not None
    raise last


async def emit_log(job: Job, level: str, message: str) -> None:
    """`log` SSE event (CONTRACTS section 8) for the job."""
    from bob.core.backends import get_events

    try:
        await get_events().append(job.id, "log", {"level": level, "message": message})
    except Exception as e:  # the event log must never break a pipeline call
        log.warning("log event failed: %s", e)


async def note_fallback(job: Job, tag: str, reason: str) -> None:
    """Add `tag` (for example "jev->scaledown_classify") to the job's fallbacks_used; log the first switch."""
    ledger.add_fallback(job.id, tag)  # the ledger is the source of CostSummary.fallbacks_used
    if tag in job.cost.fallbacks_used:
        return
    job.cost.fallbacks_used.append(tag)
    log.warning("fallback %s for job %s: %s", tag, job.id, reason)
    await emit_log(job, "warn", f"fallback {tag}: {reason}")


# ---------------------------------------------------------------- Jev request / response
def _criteria(q: Question) -> Any:
    if q.type == "choice":
        if not q.options:
            raise ValueError(f"choice question {q.id!r} needs options")
        return {o: o for o in q.options}
    if q.type == "score":
        if not q.levels or len(q.levels) < 2:
            raise ValueError(f"score question {q.id!r} needs 2-10 levels")
        return list(q.levels)
    return None


def build_request(model: str, state: str, questions: list[Question]) -> dict:
    qs: dict[str, dict] = {}
    for q in questions:
        item: dict[str, Any] = {"type": q.type, "instructions": q.prompt}
        crit = _criteria(q)
        if crit is not None:
            item["criteria"] = crit
        qs[q.id] = item
    return {"model": model, "state": state, "questions": qs}


def parse_answers(questions: list[Question], data: dict) -> dict[str, Decision]:
    answers = data.get("answers") or {}
    out: dict[str, Decision] = {}
    for q in questions:
        a = answers.get(q.id)
        if a is None:
            raise ValueError(f"Jev answer missing for {q.id!r}")
        if q.type == "noul":
            p = float(a["noul"])
            out[q.id] = Decision(value=p >= 0.5, prob=p, probs={"yes": p, "no": 1.0 - p})
        elif q.type == "choice":
            probs = {k: float(v) for k, v in (a.get("probabilities") or {}).items()}
            top = a["choice"]
            out[q.id] = Decision(value=top, prob=probs.get(top, float(a.get("confidence", 0.0))), probs=probs)
        else:
            levels = q.levels or []
            n = len(levels)
            s = float(a["score"])
            raw = a.get("probabilities") or {}
            probs = {levels[int(k)]: float(v) for k, v in raw.items() if k.isdigit() and int(k) < n}
            idx = min(max(round(s), 0), n - 1)
            out[q.id] = Decision(value=levels[idx], prob=s / (n - 1), probs=probs)
    return out


async def _jev_call(state: str, questions: list[Question], *, job: Job) -> dict[str, Decision]:
    s = settings_for(job)
    if not s.jev_api_key or not s.jev_base_url:
        raise ClientError("jev", None, "JEV_API_KEY or JEV_BASE_URL is not set")
    body = build_request(s.jev_model, state, questions)
    url = s.jev_base_url.rstrip("/") + JEV_PATH
    data, cached = await post_json(
        "jev",
        url,
        {"Authorization": f"Bearer {s.jev_api_key}"},
        body,
        model=s.jev_model,
        concurrency=s.jev_concurrency,
        timeout=JEV_TIMEOUT_S,
    )
    if not cached:
        usage = data.get("usage") or {}
        tin = int(usage.get("input_tokens", 0))
        record_cost(
            job,
            "jev",
            in_tokens=tin,
            out_tokens=int(usage.get("output_tokens", 0)),
            usd=tin * s.jev_price_in_per_m / 1e6,  # output tokens are free (Jev pricing)
            model=str(data.get("model") or s.jev_model),
        )
    return parse_answers(questions, data)


# ---------------------------------------------------------------- fallbacks
async def _classify_fallback(state: str, q: Question, purpose: str, *, job: Job) -> Decision:
    from bob.clients import scaledown

    if q.type == "noul":
        labels = ["yes", "no"]
        rubrics = {"yes": f"True: {q.prompt}", "no": f"False: {q.prompt}"}
    else:
        labels = list(q.options or [])
        rubrics = {o: o for o in labels}
    scores = await scaledown.classify(
        f"QUESTION: {q.prompt}\n\n{state}", labels, purpose, job=job, rubrics=rubrics
    )
    if q.type == "noul":
        p = float(scores.get("yes", 0.0))
        return Decision(value=p >= 0.5, prob=p, probs={"yes": p, "no": 1.0 - p})
    top = max(scores, key=scores.get)
    return Decision(value=top, prob=float(scores[top]), probs=scores)


_LLM_SYSTEM = (
    "You answer questions about a piece of text. Read the TEXT, then answer every question in the JSON "
    "format that is asked for. For a yes/no question give the probability (0 to 1) that the answer is yes. "
    "For a choice or a rating, give exactly one of the listed names and your confidence (0 to 1)."
)


def _llm_schema(questions: list[Question]) -> dict:
    props: dict[str, Any] = {}
    for q in questions:
        if q.type == "noul":
            props[q.id] = {"type": "number", "minimum": 0, "maximum": 1}
        else:
            names = q.options if q.type == "choice" else q.levels
            props[q.id] = {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "enum": list(names or [])},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["answer", "confidence"],
            }
    return {"type": "object", "properties": props, "required": [q.id for q in questions]}


def _llm_prompt(state: str, questions: list[Question]) -> str:
    lines = ["TEXT:", state, "", "QUESTIONS:"]
    for q in questions:
        if q.type == "noul":
            lines.append(f"- {q.id} (yes/no; probability of yes): {q.prompt}")
        elif q.type == "choice":
            lines.append(f"- {q.id} (choose one of: {', '.join(q.options or [])}): {q.prompt}")
        else:
            lines.append(
                f"- {q.id} (rate with one of, from lowest to highest: {', '.join(q.levels or [])}): {q.prompt}"
            )
    return "\n".join(lines)


async def _llm_fallback(state: str, questions: list[Question], *, job: Job) -> dict[str, Decision]:
    from bob.llm.client import get_llm

    llm = get_llm(job, "fallback")
    msg = [Message(role="user", content=_llm_prompt(state, questions))]
    data, _usage = await llm.complete_json("fallback", _LLM_SYSTEM, msg, _llm_schema(questions))
    out: dict[str, Decision] = {}
    for q in questions:
        a = data[q.id]
        if q.type == "noul":
            p = min(max(float(a), 0.0), 1.0)
            out[q.id] = Decision(value=p >= 0.5, prob=p, probs={"yes": p, "no": 1.0 - p})
            continue
        names = list((q.options if q.type == "choice" else q.levels) or [])
        ans = str(a["answer"])
        if ans not in names:
            raise ValueError(f"fallback model gave {ans!r} for {q.id!r}, not one of {names}")
        conf = min(max(float(a.get("confidence", 0.0)), 0.0), 1.0)
        if q.type == "choice":
            out[q.id] = Decision(value=ans, prob=conf, probs={ans: conf})
        else:
            out[q.id] = Decision(value=ans, prob=names.index(ans) / (len(names) - 1), probs={ans: conf})
    return out


async def _fallback(
    state: str, questions: list[Question], purpose: str, err: Exception, *, job: Job
) -> dict[str, Decision]:
    out: dict[str, Decision] = {}
    classifiable = [
        q for q in questions if q.type == "noul" or (q.type == "choice" and len(q.options or []) <= 20)
    ]
    direct = [q for q in questions if q not in classifiable]  # score (and very long choice lists)
    failed: list[Question] = []
    if classifiable:
        await note_fallback(job, "jev->scaledown_classify", str(err))
        results = await asyncio.gather(
            *(_classify_fallback(state, q, purpose, job=job) for q in classifiable), return_exceptions=True
        )
        for q, r in zip(classifiable, results, strict=True):
            if isinstance(r, BaseException):
                failed.append(q)
                await note_fallback(job, "scaledown_classify->fallback_model", str(r))
            else:
                out[q.id] = r
    if direct:
        await note_fallback(job, "jev->fallback_model", str(err))
    if direct or failed:
        out.update(await _llm_fallback(state, direct + failed, job=job))
    return out


# ---------------------------------------------------------------- public API
async def decide(state: str, questions: list[Question], purpose: str, *, job: Job) -> dict[str, Decision]:
    """One Jev call for all `questions` on `state`. `purpose` is a ledger tag (triage, verify, probe).

    Returns question id -> Decision. On Jev failure (after 3 tries) it uses the real fallback chain.
    """
    if not questions:
        return {}
    try:
        return await _jev_call(state, questions, job=job)
    except (ClientError, ValueError, KeyError, TypeError) as e:
        if isinstance(e, ValueError) and "needs" in str(e):
            raise  # caller bug (bad question), not a Jev failure
        return await _fallback(state, questions, purpose, e, job=job)


def dumps_state(**parts: str) -> str:
    """Helper: clearly labelled state text, for example dumps_state(PASSAGES=..., USER=..., ASSISTANT=...)."""
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items())


__all__ = ["ClientError", "Decision", "Question", "decide", "dumps_state"]
