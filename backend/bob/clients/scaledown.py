"""ScaleDown client: Extract, Summarize, Classify, Compress (CONTRACTS section 5). Owner: A2.

Confirmed at the first real calls (2026-10-30), base URL https://api.scaledown.xyz, header `x-api-key: <key>`:
  extract   POST /v1/chat/completions {"model": "extract", "messages": [...], "response_format":
            {"type": "json_schema", "json_schema": {"name", "schema"}}}
            -> choices[0].message.content = JSON string {"entities": [...], "structured_result": {...}, "input_tokens"}
            (no confidence and no offsets in structured_result; an `entities` map request gives typed spans with
            start/end/confidence instead, and then structured_result is null)
  summarize POST /v1/chat/completions {"model": "summarize", "messages": [...], "instructions"?}
            -> content = JSON string {"summary", "input_tokens", "finish_reason", ...}; usage.prompt_tokens
  classify  POST /classify {"text", "labels": [{"name", "rubric"}]} (1-20 labels)
            -> {"top_label", "scores": {name: p} (softmax, sums to 1), "reasoning", "input_tokens", ...}
  compress  POST /compress/raw/ {"context", "prompt", "scaledown": {"rate": "auto" | 0..1}}
            -> {"results": {"compressed_prompt", ...}, "input_tokens", "model_used", ...}

Every function takes keyword-only `job: Job` (ledger + the fallback model). Extract schema is guidance only:
code validates each field and keeps it only when its span is a verbatim substring of the input.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from bob.clients.jev import ClientError, note_fallback, post_json, record_cost, strict_schema
from bob.config import settings_for
from bob.core.models import Job, Message

TIMEOUT_S = 45.0  # real latency is about 1 s; a hung request is retried
MAX_LABELS = 20


class ExtractField(BaseModel):
    name: str
    value: str
    confidence: (
        float  # entities mode: ScaleDown confidence; schema mode: 1.0 exact span, 0.9 case-insensitive span
    )
    start: int  # char offsets in the `text` given to extract()
    end: int
    span_text: str  # == text[start:end], verbatim
    key: str = ""  # schema property the field came from, for example "settings" (A2 addition)


# ---------------------------------------------------------------- helpers
async def _post(path: str, body: dict, model: str, *, job: Job, purpose: str | None = None) -> dict:
    s = settings_for(job)
    if not s.scaledown_api_key:
        raise ClientError("scaledown", None, "SCALEDOWN_API_KEY is not set")
    url = s.scaledown_base_url.rstrip("/") + path
    data, cached = await post_json(
        "scaledown",
        url,
        {"x-api-key": s.scaledown_api_key},
        body,
        model=model,
        concurrency=s.scaledown_concurrency,
        timeout=TIMEOUT_S,
    )
    if not cached:
        tin = _input_tokens(data)
        record_cost(
            job,
            "scaledown",
            in_tokens=tin,
            usd=tin * s.scaledown_price_in_per_m / 1e6,
            model=model,
            purpose=purpose,
        )
    return data


def _input_tokens(data: dict) -> int:
    usage = data.get("usage") or {}
    for v in (usage.get("prompt_tokens"), data.get("input_tokens")):
        if isinstance(v, int | float):
            return int(v)
    return 0


def _content(data: dict) -> dict:
    raw = data["choices"][0]["message"]["content"]
    return json.loads(raw) if isinstance(raw, str) else raw


def find_span(text: str, needle: str, start_at: int = 0) -> tuple[int, int, float] | None:
    """Verbatim location of `needle` in `text`: exact (1.0), else case-insensitive (0.9). None if absent."""
    needle = needle.strip()
    if not needle:
        return None
    i = text.find(needle, start_at)
    if i < 0 and start_at:
        i = text.find(needle)
    if i >= 0:
        return i, i + len(needle), 1.0
    m = re.search(re.escape(needle), text, flags=re.IGNORECASE)
    if m:
        return m.start(), m.end(), 0.9
    return None


def _item_name_value(key: str, item: Any) -> tuple[str, str] | None:
    if item is None:
        return None
    if isinstance(item, str | int | float):
        return str(item), ""
    if isinstance(item, dict):
        name = item.get("name") or item.get("term") or item.get("title")
        value = item.get("value") if item.get("value") is not None else item.get("meaning")
        if name is None:
            strs = [v for v in item.values() if isinstance(v, str) and v.strip()]
            if not strs:
                return None
            name = strs[0]
        return str(name), "" if value is None else str(value)
    return None


def fields_from_result(text: str, result: dict | None, entities: list | None = None) -> list[ExtractField]:
    """Flatten an Extract result to ExtractField rows; keep only fields with a verbatim span in `text`."""
    out: list[ExtractField] = []
    seen: set[tuple[str, int, int]] = set()

    def add(key: str, name: str, value: str, start: int, end: int, conf: float) -> None:
        if (key, start, end) in seen or text[start:end] == "":
            return
        seen.add((key, start, end))
        out.append(
            ExtractField(
                name=name.strip(),
                value=value.strip(),
                confidence=conf,
                start=start,
                end=end,
                span_text=text[start:end],
                key=key,
            )
        )

    for key, val in (result or {}).items():
        items = val if isinstance(val, list) else [val]
        for item in items:
            nv = _item_name_value(key, item)
            if nv is None:
                continue
            name, value = nv
            if not isinstance(val, list) and isinstance(item, str):
                name, value = key, item  # scalar property: the value is the span
                span = find_span(text, value)
            else:
                span = find_span(text, name) or (find_span(text, value) if value else None)
            if span is None:
                continue  # not verbatim in the input: drop (schema is guidance only)
            if value and find_span(text, value) is None:
                value = ""  # a value that is not in the text is invented (seen: "max_retries_span_anchor")
            add(key, name, value, *span)
    for ent in entities or []:
        try:
            et, s0, e0 = str(ent["text"]), int(ent["start"]), int(ent["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if text[s0:e0] != et:
            span = find_span(text, et)
            if span is None:
                continue
            s0, e0 = span[0], span[1]
        add(str(ent.get("type", "")), et, "", s0, e0, float(ent.get("confidence", 0.0)))
    return out


def is_entities_map(schema: dict) -> bool:
    """True for a flat ScaleDown `entities` map ({type: description}), False for a JSON Schema."""
    return (
        "properties" not in schema
        and "type" not in schema
        and all(isinstance(v, str | dict) for v in schema.values())
    )


def normalize_schema(schema: dict) -> dict:
    """Work around a real ScaleDown behaviour (2026-10-30): a schema that mixes arrays of strings with arrays
    of objects never returns (read timeout). Arrays of strings become arrays of {"name": string}; the
    flattener reads `name` back, so callers see the same fields.
    """
    props = schema.get("properties") or {}

    def is_obj_array(p: Any) -> bool:
        return (
            isinstance(p, dict)
            and p.get("type") == "array"
            and (p.get("items") or {}).get("type") == "object"
        )

    def is_str_array(p: Any) -> bool:
        return (
            isinstance(p, dict)
            and p.get("type") == "array"
            and (p.get("items") or {}).get("type") == "string"
        )

    if not (any(is_obj_array(p) for p in props.values()) and any(is_str_array(p) for p in props.values())):
        return schema
    new_props = {}
    for k, p in props.items():
        if is_str_array(p):
            p = {**p, "items": {"type": "object", "properties": {"name": {"type": "string"}}}}
        new_props[k] = p
    return {**schema, "properties": new_props}


# ---------------------------------------------------------------- public API
async def extract(text: str, schema: dict, purpose: str, *, job: Job) -> list[ExtractField]:
    """ScaleDown Extract. `schema`: a JSON Schema (sent as response_format json_schema), or a flat ScaleDown
    `entities` map {type: description} (A2 addition: typed verbatim spans with ScaleDown confidence).
    `purpose`: ledger tag.

    Fallback on failure: the fallback model (`get_llm(job, "fallback")`) with the same schema and the same
    verbatim-span check.
    """
    body: dict[str, Any] = {"model": "extract", "messages": [{"role": "user", "content": text}]}
    if is_entities_map(schema):
        body["entities"] = schema
    else:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "extract", "schema": normalize_schema(schema)},
        }
    try:
        content = _content(await _post("/v1/chat/completions", body, "extract", job=job, purpose=purpose))
        return fields_from_result(text, content.get("structured_result"), content.get("entities"))
    except (ClientError, KeyError, IndexError, ValueError, TypeError) as e:
        await note_fallback(job, "scaledown_extract->fallback_model", str(e))
        return await _extract_llm(text, schema, job=job)


_EXTRACT_SYSTEM = (
    "You extract facts from a text into JSON that follows the given schema. Copy every name and value "
    "exactly as it is written in the text, character for character. Do not paraphrase. Do not add anything "
    "that is not in the text. Use empty lists when nothing fits."
)


async def _extract_llm(text: str, schema: dict, *, job: Job) -> list[ExtractField]:
    from bob.llm.client import get_llm

    llm = get_llm(job, "fallback")
    if is_entities_map(schema):  # the fallback model needs a JSON schema: one string list per entity type
        schema = {
            "type": "object",
            "properties": {
                k: {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": v if isinstance(v, str) else "",
                }
                for k, v in schema.items()
            },
        }
    data, _usage = await llm.complete_json(
        "fallback", _EXTRACT_SYSTEM, [Message(role="user", content=f"TEXT:\n{text}")], strict_schema(schema)
    )
    return fields_from_result(text, data)


async def summarize(text: str, purpose: str, instructions: str | None = None, *, job: Job) -> str:
    body: dict[str, Any] = {"model": "summarize", "messages": [{"role": "user", "content": text}]}
    if instructions:
        body["instructions"] = instructions
    content = _content(await _post("/v1/chat/completions", body, "summarize", job=job, purpose=purpose))
    return str(content.get("summary") or "").strip()


async def classify(
    text: str, labels: list[str], purpose: str, *, job: Job, rubrics: dict[str, str] | None = None
) -> dict[str, float]:
    """Single-label classification. Returns label -> probability (softmax, sums to 1).

    `rubrics` (A2 addition, optional): label -> description; default = the label itself.
    """
    if not 1 <= len(labels) <= MAX_LABELS:
        raise ValueError(f"classify needs 1-{MAX_LABELS} labels, got {len(labels)}")
    rubrics = rubrics or {}
    body = {"text": text, "labels": [{"name": n, "rubric": rubrics.get(n, n)} for n in labels]}
    data = await _post("/classify", body, "classify", job=job, purpose=purpose)
    scores = {str(k): float(v) for k, v in (data.get("scores") or {}).items()}
    missing = [n for n in labels if n not in scores]
    if missing:
        raise ClientError("scaledown", 200, f"classify scores miss labels {missing}")
    return {n: scores[n] for n in labels}


async def compress(text: str, rate: str | float = "auto", *, job: Job, prompt: str = "") -> str:
    """Compress `text` (the context). `prompt` (A2 addition, optional): what the context is for."""
    body = {"context": text, "prompt": prompt, "scaledown": {"rate": rate}}
    data = await _post("/compress/raw/", body, "compress", job=job)
    res = data.get("results") or {}
    if not res.get("success", True) or "compressed_prompt" not in res:
        raise ClientError("scaledown", 200, f"compress failed: {str(data)[:300]}")
    return str(res["compressed_prompt"])


__all__ = ["ExtractField", "classify", "compress", "extract", "fields_from_result", "find_span", "summarize"]
