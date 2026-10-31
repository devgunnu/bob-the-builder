"""All shared pydantic models (CONTRACTS section 2). Owner: A1.

Any change here: A1 posts the diff, G3 updates frontend/src/api/types.ts in the same hour.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from bob.pipeline.evidence import EvidenceIndex, Retriever


# ---------- sources ----------
class SourceSpec(BaseModel):
    kind: Literal["upload", "url", "composio"]
    url: str | None = None  # kind=url
    crawl_limit: int = 25  # kind=url, Firecrawl page cap
    toolkit: Literal["notion", "confluence", "jira", "googledrive"] | None = None  # kind=composio
    connected_account_id: str | None = None  # kind=composio
    scope: dict = {}  # kind=composio, e.g. {"page_ids": [...]}, {"jql": "project = SUP"}
    upload_ids: list[str] = []  # kind=upload


class Document(BaseModel):
    id: str  # sha1(uri)[:12]
    source_kind: Literal["upload", "url", "composio"]
    uri: str  # https://..., notion://<page_id>, jira://LUM-123, upload://<name>
    title: str
    text: str  # normalized markdown
    content_hash: str  # sha1(text)
    metadata: dict = {}
    fetched_at: datetime


# ---------- reading ----------
class Chunk(BaseModel):
    id: str  # sha1(doc_id + start)[:12]
    doc_id: str
    uri: str
    heading: str | None = None
    text: str
    start: int  # char offset in Document.text
    end: int
    n_tokens: int
    kept: bool = True
    drop_reason: str | None = (
        None  # "nav_density", "duplicate", "jev:boilerplate", "jev:pii", "jev:injection"
    )
    triage: dict[
        str, float | str
    ] = {}  # {"useful": 0.93, "boilerplate": 0.02, "pii": 0.01, "injection": 0.0}
    topic_id: str | None = None


class Evidence(BaseModel):
    id: str
    chunk_id: str
    doc_id: str
    kind: Literal["feature", "setting", "number", "entity", "procedure", "limit", "definition", "url"]
    name: str  # e.g. "recurring invoices", "max_retries"
    value: str | None = None  # e.g. "30 days"
    span_text: str  # verbatim text from the chunk
    start: int  # offsets in Document.text
    end: int
    confidence: float


class Topic(BaseModel):
    id: str
    name: str  # short, human-readable, e.g. "Refunds"
    description: str
    chunk_ids: list[str]
    brief: str = ""  # ScaleDown Summarize output, <= 1,000 tokens


# ---------- plan / coverage map ----------
CASE_TYPES = ["answerable", "partial", "unanswerable", "false_premise"]
DIFFICULTIES = ["single_fact", "multi_step", "multi_doc"]


class Axis(BaseModel):
    name: Literal["topic", "persona", "case_type", "difficulty"]
    values: list[str]
    descriptions: dict[str, str] = {}  # value -> one line, shown in the UI
    role: Literal["cell", "mix"] = (
        "cell"  # "cell": the axis forms cells (CELL_AXES); "mix": values rotate inside each cell
    )
    weights: dict[str, float] = {}  # mix axes only: value -> share of rows


class Cell(BaseModel):
    id: str  # sha1(sorted coords)[:10]
    coords: dict[str, str]  # CELL_AXES keys only, e.g. {"topic": "Refunds", "case_type": "unanswerable"}
    enabled: bool = True
    target: int
    weight: float = 1.0  # gap controller multiplier
    generated: int = 0
    kept: int = 0
    rejected: int = 0
    judged: int = 0
    mix_weights: dict[str, dict[str, float]] = {}
    mix_kept: dict[str, dict[str, int]] = {}


class Plan(BaseModel):
    goal: str
    task_format: Literal["single_turn", "multi_turn"] = "single_turn"
    system_prompt: str  # system prompt that ships in every exported row
    axes: list[Axis]
    cells: list[Cell]
    notes: list[str] = []  # e.g. "Your seed examples cover 4 of 14 topics."
    target_rows: int
    est_cost_usd: float


class Control(BaseModel):  # Store.get_control return value (section 7)
    state: Literal["approved", "cancel"] | None = None
    plan: Plan | None = None  # set with "approved"


# ---------- models (D33, section 14) ----------
class ModelConfig(BaseModel):
    provider: Literal["bedrock", "openai_compatible"] = "bedrock"
    model_id: str  # Bedrock model id / inference profile id, or the endpoint's model name
    base_url: str | None = None  # openai_compatible only
    api_key_set: bool = False  # openai_compatible only; the encrypted key is stored separately, never here
    json_mode: Literal["auto", "tool", "native", "prompt"] = "auto"  # auto = from the registry
    cache: Literal["auto", "off"] = "auto"  # prompt caching where the model supports it
    price_in_per_m: float | None = None  # USD; None = registry value; unknown = shown as "unknown" in the UI
    price_out_per_m: float | None = None


class ModelRoles(BaseModel):
    writer: ModelConfig
    planner: ModelConfig
    judge: ModelConfig
    fallback: ModelConfig | None = None  # None = writer; used by the Jev and Extract fallback chains


# ---------- users + Bedrock access (section 14) ----------
class BedrockAccess(BaseModel):  # AWS access only; models are in ModelRoles
    mode: Literal["default", "assume_role"] = "default"
    role_arn: str | None = None
    external_id: str | None = None
    region: str


class UserProfile(BaseModel):
    id: str  # Cognito sub, or "local"
    email: str | None = None
    external_id: str  # uuid4, made once
    bedrock: BedrockAccess | None = None
    bedrock_verified_at: datetime | None = None  # set by POST /me/aws/verify; PUT /me/aws clears it
    models: ModelRoles  # defaults from config (BOB_DEFAULT_*_MODEL)
    models_verified_at: datetime | None = None  # set by POST /me/models/verify; PUT /me/models clears it
    created_at: datetime


# ---------- job ----------
class JobOptions(BaseModel):  # every field optional; None = use the config default (section 9)
    cell_axes: list[str] | None = None
    max_cells: int | None = None
    case_mix: dict[str, float] | None = None
    keep_p: float | None = None
    reject_p: float | None = None
    audit_rate: float | None = None
    max_rounds: int | None = None
    overgen: float | None = None
    dpo_mode: Literal["synthesize", "pair", "off"] | None = None
    dpo_rate: float | None = None
    numbers_allow_user: Literal["all", "false_premise", "none"] | None = None
    extract_exempt_absent: bool | None = None
    models: ModelRoles | None = None  # per-job model override (P1, Advanced panel)


class JobSpec(BaseModel):
    goal: str
    sources: list[SourceSpec]
    seed_upload_id: str | None = None  # optional JSONL/CSV of real examples
    target_rows: int = 1000
    budget_usd: float = 10.0
    preset: str = "openai-chat"
    formats: list[str] = ["jsonl"]
    probe_model: str | None = None  # STRETCH
    options: JobOptions = JobOptions()  # per-job overrides; read through settings_for(job)


class JobStatus(str, Enum):
    created = "created"
    ingesting = "ingesting"
    reading = "reading"  # chunk, filter, triage, topics, evidence
    planning = "planning"
    awaiting_approval = "awaiting_approval"
    building = "building"
    filling_gaps = "filling_gaps"
    reporting = "reporting"
    done = "done"
    error = "error"
    cancelled = "cancelled"


TERMINAL_STATUSES = {JobStatus.done, JobStatus.error, JobStatus.cancelled}


class ModelCost(BaseModel):
    calls: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    usd: float = 0.0


class CostSummary(BaseModel):
    # keys are role names: "writer", "judge", "planner", "fallback", "jev", "scaledown", "firecrawl", "composio"
    by_model: dict[str, ModelCost] = {}
    by_purpose: dict[str, ModelCost] = {}
    model_ids: dict[str, str] = {}  # role -> model id, e.g. {"writer": "global.anthropic.claude-haiku-5-5"}
    price_unknown: list[str] = []  # roles whose model has no known price (UI badge)
    total_usd: float = 0.0
    frontier_only_estimate_usd: float = 0.0  # same token counts priced at the judge role model price
    fallbacks_used: list[str] = []  # e.g. ["jev->scaledown_classify"]


class Job(BaseModel):
    id: str
    spec: JobSpec
    owner_id: str  # UserProfile.id; owner checks (section 6)
    bedrock: BedrockAccess | None = None  # snapshot of the owner's profile at create_job
    models: ModelRoles  # snapshot at create_job: spec.options.models, else the owner's UserProfile.models
    status: JobStatus = JobStatus.created
    stage_detail: str = ""
    plan: Plan | None = None
    round: int = 0
    # docs, chunks, chunks_kept, evidence, topics, candidates, kept, rejected, judged, duplicates, dpo_pairs
    counts: dict[str, int] = {}
    cost: CostSummary = CostSummary()
    # key = path relative to the job export folder, e.g. "openai-chat/train/train.jsonl" -> download path;
    # set by A1 from export()
    files: dict[str, str] = {}
    report: Report | None = None
    error: str | None = None
    heartbeat_at: datetime | None = None  # worker writes it every BOB_HEARTBEAT_S (section 7)
    created_at: datetime
    updated_at: datetime


# ---------- generation + verification ----------
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Candidate(BaseModel):
    id: str
    job_id: str
    cell_id: str
    round: int
    case_type: str
    coords: dict[str, str]  # all 4 axes (cell axes + the mix values of this candidate)
    messages: list[Message]  # user/assistant turns only; system added at export
    chunk_ids: list[str]  # chunks the Writer was given and claims to use
    premise_evidence_id: str | None = None  # false_premise: the fact the user's premise contradicts
    # unanswerable and partial: what the user asks about that is not documented (partial: the uncovered part)
    absent_topic: str | None = None
    writer_model: str  # model id of the writer role (Job.models.writer.model_id)
    cost_usd: float


class CheckResult(BaseModel):
    name: str  # see section 4
    tier: Literal[1, 2, 3]
    passed: bool
    score: float | None = None  # probability or 0..1 score
    detail: str  # human-readable, shown in the UI
    evidence_ids: list[str] = []


class SpanRef(BaseModel):
    doc_id: str
    uri: str
    title: str
    start: int
    end: int
    text: str


class Row(BaseModel):
    id: str  # == Candidate.id
    job_id: str
    cell_id: str
    coords: dict[str, str]  # all 4 axes (topic, persona, case_type, difficulty)
    case_type: str
    round: int
    messages: list[Message]
    chunk_ids: list[str] = []
    absent_topic: str | None = None
    premise_evidence_id: str | None = None
    spans: list[SpanRef]  # supporting source text
    checks: list[CheckResult]
    confidence: float  # min pass-direction prob of the 2 case-type Jev checks (section 4)
    verdict: Literal["kept", "rejected"]
    reject_reason: str | None = None  # first failing check's detail
    routed_to_judge: bool = False
    audited: bool = False  # random tier-3 audit of a kept row
    spot_check: bool | None = None  # human thumbs up/down
    cost_usd: float
    created_at: datetime


class DPOPair(BaseModel):
    id: str
    row_id: str  # the kept Row that gives prompt + chosen
    mode: Literal[
        "synthesized", "natural"
    ]  # synthesized: flawed twin from generate_flawed; natural: DPO_MODE=pair
    prompt: list[Message]
    chosen: str  # kept assistant reply
    rejected: str  # rejected reply for the same user turn
    rejection_reason: str
    rejected_checks: list[str]  # names of the content checks that rejected the reply


class Report(BaseModel):
    coverage: list[dict]  # [{cell_id, coords, target, kept, rejected}]
    # mix axis -> value -> kept rows, e.g. {"persona": {"Accountant": 240}, "difficulty": {...}}
    mix_coverage: dict[str, dict[str, int]]
    pass_rate_by_check: dict[str, float]
    reject_reasons: dict[str, int]  # check name -> count
    duplicates_removed: int
    judge_rate: float  # share of candidates sent to tier 3
    judge_agreement: float | None  # tier-2 vs tier-3 verdict agreement on routed + audited rows
    spot_check: dict  # {"n": 50, "up": 46, "down": 4, "jev_accuracy": 0.92}
    sample_row_ids: list[str]  # 50 kept rows, stratified by cell
    token_stats: dict  # {"p50": 210, "p95": 480, "max": 900}
    rounds: list[dict]  # [{"n": 1, "cells": 42, "kept": 812}, ...]


Job.model_rebuild()


# ---------- events (section 8) ----------
class Event(BaseModel):  # one SSE event; EventLog protocol type (section 7)
    id: int  # per-job sequence id (SSE "id:", Last-Event-ID)
    type: str  # section 8 event type, e.g. "job.status", "row", "cost"
    data: dict


# ---------- pipeline context (section 3) ----------
@dataclass
class GenContext:
    """Shared context object passed through the pipeline. Lives only inside run_job; never serialized."""

    job: Job
    docs: dict[str, Document]
    chunks: dict[str, Chunk]
    topics: dict[str, Topic]
    evidence: EvidenceIndex
    retriever: Retriever
    seeds: list[list[Message]]
    emit: Callable[[str, dict], Awaitable[None]]  # event bus publish for this job
    verify_state: Any = None  # A4 per-job verify state (dedup index, judge semaphore); never serialized
