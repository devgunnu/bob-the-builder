"""Model-agnostic LLM layer (D33, CONTRACTS sections 3, 14). Owner: A1.

Pipeline code calls only `get_llm(job, role)` and never names a vendor model. Prompts are model-neutral:
no assistant prefill, no vendor-only tags. JSON parse failure: the client retries once, then raises.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from bob.core.models import Job, Message, ModelConfig

Role = Literal["writer", "planner", "judge", "fallback"]
ROLES: tuple[Role, ...] = ("writer", "planner", "judge", "fallback")


class Usage(BaseModel):
    """Real token counts from one model response (thinking tokens count as output)."""

    in_tokens: int = 0
    out_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model_id: str


@runtime_checkable
class LLMClient(Protocol):
    async def complete_json(
        self,
        role: Role,
        system: str,
        messages: list[Message],
        schema: dict,
        cache_prefix: str | None = None,
    ) -> tuple[dict, Usage]:
        """JSON object that matches `schema` (JSON Schema), by the registry json_mode (tool | native | prompt).

        `cache_prefix`: stable text placed before the varying part and marked for prompt caching where the
        model supports it (registry `cache`, above `min_cache_tokens`). The client records the ledger entry.
        """
        ...

    async def complete_text(
        self,
        role: Role,
        system: str,
        messages: list[Message],
        cache_prefix: str | None = None,
    ) -> tuple[str, Usage]:
        """Plain text reply. Same caching and ledger rules as complete_json."""
        ...


def model_for(job: Job, role: Role) -> ModelConfig:
    """The job's ModelConfig for a role: Job.models.<role>; fallback None -> writer."""
    if role not in ROLES:
        raise ValueError(f"unknown LLM role {role!r}")
    cfg = getattr(job.models, role)
    return cfg if cfg is not None else job.models.writer


def get_llm(job: Job, role: Role) -> LLMClient:
    """LLMClient for `role` on the job's Job.models snapshot.

    bedrock -> llm/bedrock.py (Converse, the job's BedrockAccess); openai_compatible -> llm/openai_compat.py (P1).
    """
    cfg = model_for(job, role)
    raise NotImplementedError(f"A1 wave 1: LLM client for provider {cfg.provider!r}")
