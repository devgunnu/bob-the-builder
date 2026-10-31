"""Bedrock Converse LLM client (D26, D33, CONTRACTS sections 3, 9, 14). Owner: A1.

boto3 `bedrock-runtime` `converse` inside `asyncio.to_thread`, with the job's BedrockAccess credentials
(llm/credentials.py) in the access region, and the model id of the role's ModelConfig in Job.models.

Per call: a semaphore per role (WRITER/JUDGE concurrency), the real-response disk cache (core/cache.py),
3 retries with exponential backoff on throttling / 5xx / timeouts, and one ledger entry with the real token
counts (thinking tokens are part of Converse outputTokens; cache read/write tokens are priced by the registry).

Registry rules (llm/registry.py): JSON mode `native` (outputConfig.textFormat json_schema), `tool` (forced
tool whose inputSchema is the schema) or `prompt` (JSON instruction + parse); a JSON parse failure retries
once, then raises LLMOutputError (the caller drops the item). `cachePoint` only where the registry allows it
and only above min_cache_tokens. No temperature where `allows_temperature` is false. No assistant prefill.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

from bob.core import cache, ledger
from bob.core.models import BedrockAccess, Job, Message, ModelConfig
from bob.llm.client import Role, Usage
from bob.llm.credentials import bedrock_runtime
from bob.llm.registry import ModelCaps, caps_for

TOOL_NAME = "emit_json"
WRITER_TEMPERATURE = 1.0
RETRIES = 3
_RETRY_CODES = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
    "ServiceQuotaExceededException",
    "TooManyRequestsException",
}
_PROMPT_JSON = (
    "Reply with exactly one JSON object that matches this JSON Schema. "
    "Output only the JSON object: no prose, no markdown, no code fences.\nJSON Schema:\n{schema}"
)
_PROMPT_JSON_RETRY = (
    "Your last reply was not one valid JSON object for the schema. Reply again with only the JSON object."
)

_sems: dict[tuple[int, str], asyncio.Semaphore] = {}


class LLMError(RuntimeError):
    """A provider error after the retries (the message is the exact provider error)."""


class LLMOutputError(ValueError):
    """The model output could not be parsed as the requested JSON after one retry. The caller drops it."""


def _semaphore(role: str) -> asyncio.Semaphore:
    from bob.config import get_settings

    loop = asyncio.get_running_loop()
    key = (id(loop), role)
    sem = _sems.get(key)
    if sem is None:
        s = get_settings()
        n = {
            "writer": s.writer_concurrency,
            "fallback": s.writer_concurrency,
            "judge": s.judge_concurrency,
            "planner": max(2, s.judge_concurrency),
        }.get(role, 4)
        sem = _sems[key] = asyncio.Semaphore(n)
    return sem


def _est_tokens(text: str) -> int:
    return len(text) // 4


def _messages(messages: list[Message]) -> tuple[list[dict], list[str]]:
    """Message list -> Converse messages (consecutive same-role turns merged) + extra system texts."""
    out: list[dict] = []
    extra_system: list[str] = []
    for m in messages:
        if m.role == "system":
            extra_system.append(m.content)
            continue
        if out and out[-1]["role"] == m.role:
            out[-1]["content"].append({"text": m.content})
        else:
            out.append({"role": m.role, "content": [{"text": m.content}]})
    if not out or out[0]["role"] != "user":
        raise ValueError("Converse needs the first message from the user")
    return out, extra_system


def _strip_schema(schema: dict) -> dict:
    """Schema without JSON Schema keys that Converse json_schema output rejects at the top level."""

    def strict(node):
        if isinstance(node, list):
            return [strict(v) for v in node]
        if not isinstance(node, dict):
            return node
        out = {k: strict(v) for k, v in node.items() if k not in ("$schema", "$id")}
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
        return out

    return strict(schema)


def parse_json_text(text: str) -> dict:
    """First JSON object in a model reply (code fences and prose around it are removed). Raises ValueError."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        val = json.loads(t)
    except ValueError:
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object in the reply") from None
        val = json.loads(t[start : end + 1])
    if not isinstance(val, dict):
        raise ValueError("the reply is JSON but not an object")
    return val


def _check_required(val: dict, schema: dict) -> None:
    missing = [k for k in schema.get("required", []) if k not in val]
    if missing:
        raise ValueError(f"missing required keys {missing}")


class BedrockClient:
    """LLMClient for one job + role on Bedrock Converse."""

    def __init__(self, job: Job, role: Role, cfg: ModelConfig, *, use_cache: bool = True):
        self.use_cache = use_cache  # False: always a real call (verify / health checks)
        self.job = job
        self.role = role
        self.cfg = cfg
        self.caps: ModelCaps = caps_for(cfg)
        self.access: BedrockAccess = job.bedrock or _default_access()
        self.endpoint = f"bedrock:converse:{self.access.region}"

    # ---------- request building ----------
    def _request(
        self,
        system: str,
        messages: list[Message],
        cache_prefix: str | None,
        json_schema: dict | None,
        mode: str | None,
    ) -> dict[str, Any]:
        msgs, extra_sys = _messages(messages)
        sys_texts = [system] if system else []
        if mode == "prompt" and json_schema is not None:
            sys_texts.append(_PROMPT_JSON.format(schema=json.dumps(json_schema, sort_keys=True)))
        sys_blocks: list[dict] = [{"text": t} for t in sys_texts]
        if cache_prefix:
            sys_blocks.append({"text": cache_prefix})
        if (
            cache_prefix is not None
            and self.caps.cache
            and self.caps.min_cache_tokens is not None
            and _est_tokens("".join(sys_texts) + (cache_prefix or "")) >= self.caps.min_cache_tokens
        ):
            sys_blocks.append({"cachePoint": {"type": "default"}})
        sys_blocks += [{"text": t} for t in extra_sys]

        req: dict[str, Any] = {
            "modelId": self.cfg.model_id,
            "messages": msgs,
            "inferenceConfig": {"maxTokens": self.caps.max_tokens},
        }
        if self.role == "writer" and self.caps.allows_temperature:
            # the Writer must vary its rows; some models (Nova) default to a low temperature
            req["inferenceConfig"]["temperature"] = WRITER_TEMPERATURE
        if sys_blocks:
            req["system"] = sys_blocks
        fields = self.caps.fields_for(self.role)
        if fields:
            req["additionalModelRequestFields"] = fields
        if json_schema is not None and mode == "native":
            req["outputConfig"] = {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {"schema": json.dumps(_strip_schema(json_schema)), "name": "output"}
                    },
                }
            }
        elif json_schema is not None and mode == "tool":
            req["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": TOOL_NAME,
                            "description": "Return the answer as this JSON object.",
                            "inputSchema": {"json": _strip_schema(json_schema)},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": TOOL_NAME}},
            }
        return req

    # ---------- transport ----------
    async def _converse(self, req: dict[str, Any], *, use_cache: bool = True) -> tuple[dict, bool]:
        """(response subset, from_cache). Real call with retries; stores the real response in the cache."""
        if use_cache and self.use_cache:
            hit = await cache.get(self.endpoint, self.cfg.model_id, req)
            if hit is not None:
                return hit, True
        client = await asyncio.to_thread(bedrock_runtime, self.access, self.job.id)
        last: Exception | None = None
        async with _semaphore(self.role):
            for attempt in range(RETRIES + 1):
                try:
                    resp = await asyncio.to_thread(client.converse, **req)
                    break
                except Exception as e:  # botocore ClientError / connection errors
                    code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
                    retryable = code in _RETRY_CODES or type(e).__name__ in (
                        "ReadTimeoutError",
                        "ConnectTimeoutError",
                        "EndpointConnectionError",
                        "ConnectionClosedError",
                    )
                    last = e
                    if not retryable or attempt == RETRIES:
                        raise LLMError(
                            f"bedrock {self.cfg.model_id} in {self.access.region} ({self.role}): {e}"
                        ) from e
                    await asyncio.sleep(min(20.0, 1.5 * 2**attempt) + random.random())
            else:  # pragma: no cover
                raise LLMError(str(last))
        out = {
            "output": resp.get("output", {}),
            "stopReason": resp.get("stopReason"),
            "usage": resp.get("usage", {}),
        }
        self._record(out["usage"])
        return out, False

    async def _cache_put(self, req: dict, resp: dict) -> None:
        if self.use_cache:
            await cache.put(self.endpoint, self.cfg.model_id, req, resp)

    def _usage(self, raw: dict) -> Usage:
        return Usage(
            in_tokens=int(raw.get("inputTokens", 0)),
            out_tokens=int(raw.get("outputTokens", 0)),
            cache_read_tokens=int(raw.get("cacheReadInputTokens", 0) or 0),
            cache_write_tokens=int(raw.get("cacheWriteInputTokens", 0) or 0),
            model_id=self.cfg.model_id,
        )

    def _record(self, raw: dict) -> None:
        u = self._usage(raw)
        usd = self.caps.usd(u.in_tokens, u.out_tokens, u.cache_read_tokens, u.cache_write_tokens)
        if usd is None:
            ledger.mark_price_unknown(self.job.id, self.role)
        ledger.record(
            self.job.id,
            self.role,
            in_tokens=u.in_tokens + u.cache_read_tokens + u.cache_write_tokens,
            out_tokens=u.out_tokens,
            usd=usd if usd is not None else 0.0,
            model=self.cfg.model_id,
        )

    @staticmethod
    def _text(resp: dict) -> str:
        blocks = resp.get("output", {}).get("message", {}).get("content", [])
        return "".join(b.get("text", "") for b in blocks if "text" in b)

    @staticmethod
    def _tool_input(resp: dict) -> dict | None:
        for b in resp.get("output", {}).get("message", {}).get("content", []):
            tu = b.get("toolUse")
            if tu and tu.get("name") == TOOL_NAME and isinstance(tu.get("input"), dict):
                return tu["input"]
        return None

    def _parse(self, resp: dict, mode: str, schema: dict) -> dict:
        if mode == "tool":
            val = self._tool_input(resp)
            if val is None:
                val = parse_json_text(self._text(resp))
        else:
            val = parse_json_text(self._text(resp))
        _check_required(val, schema)
        return val

    # ---------- LLMClient ----------
    async def complete_json(
        self,
        role: Role,
        system: str,
        messages: list[Message],
        schema: dict,
        cache_prefix: str | None = None,
    ) -> tuple[dict, Usage]:
        mode = self.caps.json_mode
        req = self._request(system, messages, cache_prefix, schema, mode)
        resp, cached = await self._converse(req)
        try:
            val = self._parse(resp, mode, schema)
        except ValueError as e1:
            # retry once: prompt mode gets a correction turn; the other modes ask again (no cache)
            if mode == "prompt":
                retry_msgs = [
                    *messages,
                    Message(role="assistant", content=self._text(resp) or "(empty)"),
                    Message(role="user", content=_PROMPT_JSON_RETRY),
                ]
                req2 = self._request(system, retry_msgs, cache_prefix, schema, mode)
            else:
                req2 = req
            resp, _ = await self._converse(req2, use_cache=False)
            try:
                val = self._parse(resp, mode, schema)
            except ValueError as e2:
                raise LLMOutputError(
                    f"{self.cfg.model_id} ({self.role}, json_mode={mode}): no valid JSON after one retry: {e2}"
                ) from e1
            await self._cache_put(req, resp)
            return val, self._usage(resp.get("usage", {}))
        if not cached:
            await self._cache_put(req, resp)
        return val, self._usage(resp.get("usage", {})).model_copy(update={"cached": cached})

    async def complete_text(
        self,
        role: Role,
        system: str,
        messages: list[Message],
        cache_prefix: str | None = None,
    ) -> tuple[str, Usage]:
        req = self._request(system, messages, cache_prefix, None, None)
        resp, cached = await self._converse(req)
        if not cached:
            await self._cache_put(req, resp)
        return self._text(resp), self._usage(resp.get("usage", {})).model_copy(update={"cached": cached})


def _default_access() -> BedrockAccess:
    from bob.config import default_bedrock_access

    return default_bedrock_access()
