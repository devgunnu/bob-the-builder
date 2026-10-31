"""Model-agnostic LLM layer (D33, CONTRACTS sections 3, 14). Owner: A1.

Pipeline code calls only `get_llm(job, role)` and never names a vendor model. Prompts are model-neutral:
no assistant prefill, no vendor-only tags. JSON parse failure: the client retries once, then raises.
"""

from __future__ import annotations

from contextvars import ContextVar
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


# The job that the current pipeline stage runs for. run_job sets it, so stage functions whose CONTRACTS
# section 3 signature has no `job` (triage, build_topics, build_evidence, propose_plan) can call
# get_llm(current_job(), role). asyncio tasks and asyncio.to_thread copy it.
CURRENT_JOB: ContextVar[Job | None] = ContextVar("bob_current_job", default=None)


def current_job() -> Job:
    """The Job of the running pipeline stage. Raises RuntimeError outside run_job."""
    job = CURRENT_JOB.get()
    if job is None:
        raise RuntimeError("no current job: call this inside Orchestrator.run_job (or set CURRENT_JOB)")
    return job


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
    if cfg.provider == "bedrock":
        from bob.llm.bedrock import BedrockClient

        return BedrockClient(job, role, cfg)
    raise NotImplementedError(f"provider {cfg.provider!r} is P1 (llm/openai_compat.py)")
