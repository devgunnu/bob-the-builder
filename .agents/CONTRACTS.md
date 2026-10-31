# Bob the Builder: Contracts (v4.1, data factory)

> Source of truth for all 9 coding agents (A1 to A5, G1 to G4). Lock in the first 20 minutes (T+0:00 to T+0:20). Change only by agreement between Aaditya and Gunbir, and commit the change here first.
> v4 replaces v1 to v3. Templates, question programs, grammar banks and Architect-written generator code are retired (DECISIONS D18).
> v4.1 = v4 + review fixes + bring-your-own AWS for Bedrock (D26) + Cognito auth (D27) + model-agnostic LLM layer (D33). Each user connects their own AWS account, and Bedrock calls run and bill there (section 14). Users sign in through a Cognito user pool (section 14). Each LLM role (writer, planner, judge, fallback) can use any model; Haiku 5.5 and Sonnet 5.5 are only defaults (section 14).
> Bob deploys to AWS serverless: Lambda API + one Fargate worker task per job (DECISIONS D25). A5 Deploy owns it (section 13). Local mode stays the default.

## 0. Ground rules for every agent

1. **One owner per file.** Only edit files that your brief owns (section 1). If you need a change in another file, write a note in `.agents/CHANGES_REQUESTED.md` and tell your builder.
2. **No mocks, no fake data.** Every call to Bedrock, Jev, ScaleDown, Firecrawl and Composio is real, from the first line of code. Tests use real calls on small real inputs (the `demo/smoke/` corpus). If a key does not work, fix the key or switch to the documented real fallback (section 5); never stub the call. This rule covers AWS too: tests of the aws backends use real DynamoDB and real S3. No moto, no LocalStack (D23).
3. **Everything is async.** Pipeline functions are `async def`. External calls go through a client with a semaphore, retries (3, exponential backoff), the response cache (`core/cache.py`), and a cost ledger entry.
4. **Dependencies:** A1 owns `backend/pyproject.toml`, G3 owns `frontend/package.json`. To add a dependency, add a `CHANGES_REQUESTED.md` entry; the owner adds it within 10 minutes. In the first 20 minutes, A1 and G3 add every dependency named in this file up front.
5. **Python 3.12, pydantic v2, ruff format.** TypeScript strict, React 18, Vite.
6. **Commit small and often** to your builder's branch: `aaditya/*` or `gunbir/*`. Merge to `main` at each checkpoint.
7. **Storage and process rules (D25).** Code writes files only under `settings.runs_dir` (`BOB_RUNS_DIR`). Never hard-code `runs/`. Durable data goes only through `Store`, `Blobs` and `EventLog` (section 7). The API process never starts background work. Long work runs only in the job runner (local: asyncio task; aws: Fargate worker).
8. **Thresholds come from `settings_for(job)`.** Env vars give the defaults. A job can override them with `JobSpec.options` (`JobOptions`, section 2). A1 adds `settings_for(job) -> EffectiveSettings` in `config.py`. All pipeline code reads thresholds and limits through it, never directly from env or `settings`.
9. **Ownership (D27, sign-in removed 2026-10-31).** There is no sign-in: every caller is the built-in user `local` (G1 `current_user()`, section 6). Every job has an `owner_id`. A user sees and changes only their own jobs. A job of another user returns HTTP 404. Bedrock calls use the job's `BedrockAccess` snapshot, never Bob's own role in aws mode. LLM calls use the job's `Job.models` snapshot through `get_llm(job, role)` (section 14).

## 1. Repository layout and ownership

```
backend/
  pyproject.toml                    A1
  bob/
    config.py                       A1   settings from env (section 9)
    core/
      models.py                     A1   ALL shared pydantic models (section 2). Written first.
      store.py                      A1   Store protocol + local impl (in-memory + runs/<job_id>/ on disk); aws impl in bob/aws/store.py
      events.py                     A1   EventLog protocol + local impl (in-memory log + queues), SSE replay; aws impl in bob/aws/events.py
      blobs.py                      A1   Blobs protocol + local impl (files under settings.runs_dir); aws impl in bob/aws/blobs.py
      runner.py                     A1   Runner protocol + local impl (asyncio task); aws impl in bob/aws/runner.py
      backends.py                   A1   get_blobs() get_store() get_events() get_runner(): pick by BOB_ENV
      ledger.py                     A1   cost ledger + frontier-only estimate
      cache.py                      A1   real-response cache for all external calls, stored through Blobs (cache/<sha256>.json)
    llm/
      client.py                     A1   LLMClient protocol + get_llm(job, role) (D33, section 14). Pipeline code calls only this
      bedrock.py                    A1   LLMClient on the Bedrock Converse API (any Bedrock model); uses the job's BedrockAccess
      openai_compat.py              A1   P1: LLMClient on any OpenAI-compatible chat completions endpoint (raw httpx)
      registry.py registry.json     A1   model capabilities per model id prefix (json_mode, cache, prices, ...); path = BOB_MODEL_REGISTRY
      credentials.py                A1   BedrockAccess -> AWS credentials (default chain or STS AssumeRole + refresh), section 14
    clients/
      jev.py                        A2   Jev Decisions API client + fallback chain
      scaledown.py                  A2   Extract / Summarize / Classify / Compress
    pipeline/
      chunk.py filters.py embed.py  A2   chunking, heuristics, embeddings, dedup
      triage.py                     A2   Jev chunk triage
      topics.py                     A2   clustering, topic names, Summarize briefs
      evidence.py                   A2   Extract -> EvidenceIndex; Retriever
      planner.py                    A3   coverage map (Plan)
      generate.py                   A3   Writer: cell -> candidates
      gaps.py                       A3   gap-filling controller
      prompts/*.md                  A3 (planner.md, writer*.md incl. writer_flawed.md), A4 (judge.md)  -> path: backend/bob/pipeline/prompts/
      prompts/writer_flawed.md      A3   flawed replies for DPO pairs (section 4)
      verify.py                     A4   3-tier verification cascade
      report.py                     A4   data quality report
      probe.py                      A4   STRETCH: base-model probing
    export/
      presets.py formats.py manifest.py   A4
    orchestrator.py                 A1   job state machine; the only API the web layer calls
    worker.py                       A5   Fargate entry: load secrets -> build Orchestrator -> await run_job(job_id, mode) -> exit code
    aws/
      blobs.py store.py events.py   A5   aws impls of the section 7 protocols (S3, DynamoDB); boto3 in asyncio.to_thread
      runner.py                     A5   ecs.run_task / ecs.stop_task
      secrets.py                    A5   load the bob/keys secret JSON into the environment
    connectors/
      __init__.py                   G1   fetch_documents() dispatch
      upload.py parsers.py          G1   file upload + PDF/DOCX/MD/HTML/TXT/CSV -> Document
      firecrawl.py                  G2
      composio.py                   G2   Notion, Confluence, Jira, Google Drive
      sync.py                       G2   content hashes, diff for re-sync
    api/
      app.py routes.py sse.py       G1   FastAPI app, routes (section 6), SSE
      auth.py                       G1   current_user() dependency: the built-in "local" user (no sign-in, section 14)
  tests/                            each owner tests their own modules
  Dockerfile                        A5   one image for the API Lambda and the Fargate worker (section 13)
frontend/                           G3 (shell, setup, plan screens, package.json), G4 (build, rows, report screens, src/components/viz/*)
  src/api/client.ts types.ts        G3 owns; types.ts mirrors section 2 exactly; client.ts adds the auth header
  src/screens/Account*              G3   Account screen, route /account: "AWS access" panel + "Models" panel (section 14)
demo/                               G2: smoke/ (small real corpus for tests), corpus/ (cached real crawl of the demo docs)
runs/                               gitignored job outputs (local mode; path = BOB_RUNS_DIR)
infra/                              A5   AWS CDK v2 app (Python)
  app.py cdk.json requirements.txt  A5   requirements.txt = aws-cdk-lib, constructs (A5 owns it)
  bob_infra/data_stack.py           A5   stack BobData: table, data bucket, frontend bucket, secret
  bob_infra/app_stack.py            A5   stack BobApp: image, Lambda + Function URL, ECS cluster + task def, CloudFront, IAM
  deploy.sh README.md               A5   one-command deploy; how to deploy and tear down
  templates/bedrock-role.yaml       A5   CloudFormation template: role BobBedrockAccess in the user's account (section 14)
.dockerignore                       A5   root; the Docker build context is the repo root
.gitignore                          A5   root; .env, secrets.json, runs/, cdk.out/, infra/outputs.json, node_modules/, dist/, __pycache__/
.env.example                        A1   root; every env var of section 9 with its default
README.md                           A5   root; setup, deploy, BYO AWS steps. Other agents send text through CHANGES_REQUESTED.md
```

A5 asks A1 for `boto3` in `backend/pyproject.toml`. A1 adds it up front at T+0:15. A1 also adds `pyjwt[crypto]`. The `anthropic` package is not a required dependency (D33): Bedrock calls go through boto3 Converse. G3 adds `aws-amplify`, `@aws-amplify/ui-react` and `@microsoft/fetch-event-source` to `frontend/package.json`.

## 2. Core models (`backend/bob/core/models.py`)

```python
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

# ---------- sources ----------
class SourceSpec(BaseModel):
    kind: Literal["upload", "url", "composio"]
    url: str | None = None                  # kind=url
    crawl_limit: int = 25                   # kind=url, Firecrawl page cap
    toolkit: Literal["notion", "confluence", "jira", "googledrive"] | None = None  # kind=composio
    connected_account_id: str | None = None # kind=composio
    scope: dict = {}                        # kind=composio, e.g. {"page_ids": [...]}, {"jql": "project = SUP"}
    upload_ids: list[str] = []              # kind=upload

class Document(BaseModel):
    id: str                                 # sha1(uri)[:12]
    source_kind: Literal["upload", "url", "composio"]
    uri: str                                # https://..., notion://<page_id>, jira://LUM-123, upload://<name>
    title: str
    text: str                               # normalized markdown
    content_hash: str                       # sha1(text)
    metadata: dict = {}
    fetched_at: datetime

# ---------- reading ----------
class Chunk(BaseModel):
    id: str                                 # sha1(doc_id + start)[:12]
    doc_id: str
    uri: str
    heading: str | None = None
    text: str
    start: int                              # char offset in Document.text
    end: int
    n_tokens: int
    kept: bool = True
    drop_reason: str | None = None          # "nav_density", "duplicate", "jev:boilerplate", "jev:pii", "jev:injection"
    triage: dict[str, float | str] = {}     # {"useful": 0.93, "boilerplate": 0.02, "pii": 0.01, "injection": 0.0}
    topic_id: str | None = None

class Evidence(BaseModel):
    id: str
    chunk_id: str
    doc_id: str
    kind: Literal["feature", "setting", "number", "entity", "procedure", "limit", "definition", "url"]
    name: str                               # e.g. "recurring invoices", "max_retries"
    value: str | None = None                # e.g. "30 days"
    span_text: str                          # verbatim text from the chunk
    start: int                              # offsets in Document.text
    end: int
    confidence: float

class Topic(BaseModel):
    id: str
    name: str                               # short, human-readable, e.g. "Refunds"
    description: str
    chunk_ids: list[str]
    brief: str = ""                         # ScaleDown Summarize output, <= 1,000 tokens

# ---------- plan / coverage map ----------
CASE_TYPES = ["answerable", "partial", "unanswerable", "false_premise"]
DIFFICULTIES = ["single_fact", "multi_step", "multi_doc"]

class Axis(BaseModel):
    name: Literal["topic", "persona", "case_type", "difficulty"]
    values: list[str]
    descriptions: dict[str, str] = {}       # value -> one line, shown in the UI
    role: Literal["cell", "mix"] = "cell"   # "cell": the axis forms cells (CELL_AXES); "mix": values rotate inside each cell
    weights: dict[str, float] = {}          # mix axes only: value -> share of rows

class Cell(BaseModel):
    id: str                                 # sha1(sorted coords)[:10]
    coords: dict[str, str]                  # CELL_AXES keys only, e.g. {"topic": "Refunds", "case_type": "unanswerable"}
    enabled: bool = True
    target: int
    weight: float = 1.0                     # gap controller multiplier
    generated: int = 0
    kept: int = 0
    rejected: int = 0
    judged: int = 0
    mix_weights: dict[str, dict[str, float]] = {}  # per-cell overrides; empty uses axis weights
    mix_kept: dict[str, dict[str, int]] = {}        # kept rows per mix value

class Plan(BaseModel):
    goal: str
    task_format: Literal["single_turn", "multi_turn"] = "single_turn"
    system_prompt: str                      # system prompt that ships in every exported row
    axes: list[Axis]
    cells: list[Cell]
    notes: list[str] = []                   # e.g. "Your seed examples cover 4 of 14 topics."
    target_rows: int
    est_cost_usd: float

class Control(BaseModel):                   # Store.get_control return value (section 7)
    state: Literal["approved", "cancel"] | None = None
    plan: Plan | None = None                # set with "approved"

# ---------- models (D33, section 14) ----------
class ModelConfig(BaseModel):
    provider: Literal["bedrock", "openai_compatible"] = "bedrock"
    model_id: str                           # Bedrock model id / inference profile id, or the endpoint's model name
    base_url: str | None = None             # openai_compatible only
    api_key_set: bool = False               # openai_compatible only; the encrypted key is stored separately, never in this model
    json_mode: Literal["auto", "tool", "native", "prompt"] = "auto"   # auto = from the registry
    cache: Literal["auto", "off"] = "auto"  # prompt caching where the model supports it
    price_in_per_m: float | None = None     # USD; None = registry value; unknown = shown as "unknown" in the UI
    price_out_per_m: float | None = None

class ModelRoles(BaseModel):
    writer: ModelConfig
    planner: ModelConfig
    judge: ModelConfig
    fallback: ModelConfig | None = None     # None = writer; used by the Jev and Extract fallback chains

# ---------- users + Bedrock access (section 14) ----------
class BedrockAccess(BaseModel):             # AWS access only; models are in ModelRoles
    mode: Literal["default", "assume_role"] = "default"
    role_arn: str | None = None
    external_id: str | None = None
    region: str

class UserProfile(BaseModel):
    id: str                                 # Cognito sub, or "local"
    email: str | None = None
    external_id: str                        # uuid4, made once
    bedrock: BedrockAccess | None = None
    bedrock_verified_at: datetime | None = None   # set by POST /me/aws/verify; PUT /me/aws clears it
    models: ModelRoles                      # defaults from config (BOB_DEFAULT_*_MODEL)
    models_verified_at: datetime | None = None    # set by POST /me/models/verify; PUT /me/models clears it
    created_at: datetime

# ---------- job ----------
class JobOptions(BaseModel):                # every field optional; None = use the config default (section 9)
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
    models: ModelRoles | None = None        # per-job model override (P1, Advanced panel)

class JobSpec(BaseModel):
    goal: str
    sources: list[SourceSpec]
    seed_upload_id: str | None = None       # optional JSONL/CSV of real examples
    target_rows: int = 1000
    budget_usd: float = 10.0
    preset: str = "openai-chat"
    formats: list[str] = ["jsonl"]
    probe_model: str | None = None          # STRETCH
    options: JobOptions = JobOptions()      # per-job overrides; read through settings_for(job)

class JobStatus(str, Enum):
    created = "created"
    ingesting = "ingesting"
    reading = "reading"                     # chunk, filter, triage, topics, evidence
    planning = "planning"
    awaiting_approval = "awaiting_approval"
    building = "building"
    filling_gaps = "filling_gaps"
    reporting = "reporting"
    done = "done"
    error = "error"
    cancelled = "cancelled"

class ModelCost(BaseModel):
    calls: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    usd: float = 0.0

class CostSummary(BaseModel):
    by_model: dict[str, ModelCost] = {}     # keys are role names: "writer", "judge", "planner", "fallback", "jev", "scaledown", "firecrawl", "composio"
    model_ids: dict[str, str] = {}          # role -> model id, e.g. {"writer": "global.anthropic.claude-haiku-5-5"}
    price_unknown: list[str] = []           # roles whose model has no known price (UI badge)
    total_usd: float = 0.0
    frontier_only_estimate_usd: float = 0.0 # same token counts priced at the judge role model price
    fallbacks_used: list[str] = []          # e.g. ["jev->scaledown_classify"]

class Job(BaseModel):
    id: str
    spec: JobSpec
    owner_id: str                           # UserProfile.id; owner checks (section 6)
    bedrock: BedrockAccess | None = None    # snapshot of the owner's profile at create_job
    models: ModelRoles                      # snapshot at create_job: spec.options.models, else the owner's UserProfile.models
    status: JobStatus = JobStatus.created
    stage_detail: str = ""
    plan: Plan | None = None
    round: int = 0
    counts: dict[str, int] = {}             # docs, chunks, chunks_kept, evidence, topics, candidates, kept, rejected, judged, duplicates, dpo_pairs
    cost: CostSummary = CostSummary()
    files: dict[str, str] = {}              # key = path relative to the job export folder, e.g. "openai-chat/train/train.jsonl" -> download path; set by A1 from export()
    report: "Report | None" = None
    error: str | None = None
    heartbeat_at: datetime | None = None    # worker writes it every BOB_HEARTBEAT_S (section 7)
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
    coords: dict[str, str]                  # all 4 axes (cell axes + the mix values of this candidate)
    messages: list[Message]                 # user/assistant turns only; system added at export
    chunk_ids: list[str]                    # chunks the Writer was given and claims to use
    premise_evidence_id: str | None = None  # false_premise: the fact the user's premise contradicts
    absent_topic: str | None = None         # unanswerable and partial: what the user asks about that is not documented (partial: the uncovered part)
    writer_model: str                       # model id of the writer role (Job.models.writer.model_id)
    cost_usd: float

class CheckResult(BaseModel):
    name: str                               # see section 4
    tier: Literal[1, 2, 3]
    passed: bool
    score: float | None = None              # probability or 0..1 score
    detail: str                             # human-readable, shown in the UI
    evidence_ids: list[str] = []

class SpanRef(BaseModel):
    doc_id: str
    uri: str
    title: str
    start: int
    end: int
    text: str

class Row(BaseModel):
    id: str                                 # == Candidate.id
    job_id: str
    cell_id: str
    coords: dict[str, str]                  # all 4 axes (topic, persona, case_type, difficulty)
    case_type: str
    round: int
    messages: list[Message]
    chunk_ids: list[str] = []
    absent_topic: str | None = None
    premise_evidence_id: str | None = None
    spans: list[SpanRef]                    # supporting source text
    checks: list[CheckResult]
    confidence: float                       # min pass-direction prob of the 2 case-type Noul checks (section 4)
    verdict: Literal["kept", "rejected"]
    reject_reason: str | None = None        # first failing check's detail
    routed_to_judge: bool = False
    audited: bool = False                   # random tier-3 audit of a kept row
    spot_check: bool | None = None          # human thumbs up/down
    cost_usd: float
    created_at: datetime

class DPOPair(BaseModel):
    id: str
    row_id: str                             # the kept Row that gives prompt + chosen
    mode: Literal["synthesized", "natural"] # synthesized: flawed twin from generate_flawed; natural: DPO_MODE=pair
    prompt: list[Message]
    chosen: str                             # kept assistant reply
    rejected: str                           # rejected reply for the same user turn
    rejection_reason: str
    rejected_checks: list[str]              # names of the content checks that rejected the reply

class Report(BaseModel):
    coverage: list[dict]                    # [{cell_id, coords, target, kept, rejected}]
    mix_coverage: dict[str, dict[str, int]] # mix axis -> value -> kept rows, e.g. {"persona": {"Accountant": 240}, "difficulty": {...}}
    pass_rate_by_check: dict[str, float]
    reject_reasons: dict[str, int]          # check name -> count
    duplicates_removed: int
    judge_rate: float                       # share of candidates sent to tier 3
    judge_agreement: float | None           # tier-2 vs tier-3 verdict agreement on routed + audited rows
    spot_check: dict                        # {"n": 50, "up": 46, "down": 4, "jev_accuracy": 0.92}
    sample_row_ids: list[str]               # 50 kept rows, stratified by cell
    token_stats: dict                       # {"p50": 210, "p95": 480, "max": 900}
    rounds: list[dict]                      # [{"n": 1, "cells": 42, "kept": 812}, ...]
```

`frontend/src/api/types.ts` mirrors these names and fields exactly (G3 owns it). If a model changes, A1 posts the diff and G3 updates `types.ts` in the same hour.

## 3. Stage signatures (Aaditya's modules)

```python
# A2: reading
def chunk_documents(docs: list[Document]) -> list[Chunk]            # heading-aware, 300-500 tokens, keeps offsets
def heuristic_filter(chunks: list[Chunk]) -> list[Chunk]            # sets kept / drop_reason; free
def embed(texts: list[str]) -> "np.ndarray"                         # model2vec potion-base-8M, CPU; loads from BOB_EMBED_MODEL_PATH when set
def dedup_chunks(chunks: list[Chunk]) -> list[Chunk]                # exact hash + cosine > 0.95
async def triage(chunks: list[Chunk]) -> list[Chunk]                # one Jev call per chunk, 4 questions
async def build_topics(chunks: list[Chunk], goal: str) -> list[Topic]   # k-means (k = clamp(sqrt(n), 4, 20)),
                                                                    # names via Writer, briefs via Summarize
async def build_evidence(chunks: list[Chunk]) -> "EvidenceIndex"

class EvidenceIndex:
    items: list[Evidence]
    def find(self, name: str) -> list[Evidence]                     # normalized + fuzzy (rapidfuzz >= 90)
    def by_chunk(self, chunk_id: str) -> list[Evidence]
    def names(self, kinds: set[str] | None = None) -> set[str]

class Retriever:
    def __init__(self, chunks: list[Chunk]): ...
    def top_k(self, query: str, k: int = 5, topic_id: str | None = None) -> list[Chunk]

# A3: plan + generate + gaps
async def propose_plan(goal: str, topics: list[Topic], seeds: list[list[Message]],
                       target_rows: int, budget_usd: float, *, job: Job | None = None,
                       chunks: dict[str, Chunk] | None = None) -> Plan
                                                                    # cells = CELL_AXES only (default topic x case_type);
                                                                    # other axes get role="mix" + weights; at most MAX_TOPICS topics;
                                                                    # merges the smallest topics until enabled cells <= MAX_CELLS
def allocate_targets(plan: Plan, *, job: Job | None = None) -> Plan                            # split target_rows across enabled cells by CASE_MIX;
                                                                    # each enabled cell gets at least MIN_CELL_TARGET
async def generate(cell: Cell, plan: Plan, ctx: "GenContext", n: int) -> list[Candidate]
                                                                    # each batch of WRITER_BATCH rotates mix values by weight;
                                                                    # sets Candidate.coords (all 4 axes) and absent_topic
async def generate_flawed(row: Row, ctx: "GenContext") -> Candidate # DPO: one flawed reply to the SAME user turn (section 4);
                                                                    # batched 5 per call, prompts/writer_flawed.md, ledger bucket writer, purpose dpo
def plan_gap_round(job: Job, cells: list[Cell]) -> list[tuple[Cell, int]]   # which cells, how many more; also boosts
                                                                    # under-covered mix values (deficit vs weight) in a cell's next batches

# A4: verify + report + export
async def verify(cands: list[Candidate], ctx: "GenContext") -> list[Row]
async def build_dpo_pairs(rows: list[Row], ctx: "GenContext") -> list[DPOPair]   # calls A3 generate_flawed + A4 tier 1+2 (section 4)
def build_report(job: Job, rows: list[Row]) -> Report              # fills coverage per cell + mix_coverage per mix axis
def export(job: Job, rows: list[Row], pairs: list[DPOPair], preset: str,
           formats: list[str], out_dir: "Path") -> dict[str, str]   # out_dir is under settings.runs_dir (section 11)

# A1: shared context object passed through the pipeline. Lives in core/models.py
# (plain class, imports EvidenceIndex / Retriever under TYPE_CHECKING only).
class GenContext:
    job: Job
    docs: dict[str, Document]
    chunks: dict[str, Chunk]
    topics: dict[str, Topic]
    evidence: EvidenceIndex
    retriever: Retriever
    seeds: list[list[Message]]
    emit: "Callable[[str, dict], Awaitable[None]]"                  # event bus publish for this job

# A1: model-agnostic LLM layer (D33). llm/client.py
Role = Literal["writer", "planner", "judge", "fallback"]
class LLMClient(Protocol):
    async def complete_json(self, role: Role, system: str, messages: list[Message], schema: dict,
                            cache_prefix: str | None = None) -> tuple[dict, "Usage"]
    async def complete_text(self, role: Role, system: str, messages: list[Message],
                            cache_prefix: str | None = None) -> tuple[str, "Usage"]
def get_llm(job: Job, role: Role) -> LLMClient                     # reads job.models[role] (fallback None -> writer);
                                                                    # bedrock -> llm/bedrock.py (Converse); openai_compatible -> llm/openai_compat.py (P1)
```

LLM rules (D33):
- Pipeline code calls `get_llm(job, role)`: A2 topic names (`writer`), A3 planner (`planner`) and Writer (`writer`), A4 judge (`judge`), the Jev and Extract fallbacks (`fallback`). It never names a vendor model.
- All prompts are model-neutral: no prefill, no vendor-only tags. JSON parse failure: retry once, then drop.
- `llm/registry.py` reads `llm/registry.json` (`BOB_MODEL_REGISTRY`). It gives capabilities per model id prefix:
  - `json_mode`: `tool` (Converse `toolConfig` with a forced tool whose `inputSchema` is the JSON schema), `native` (`response_format` json_schema), `prompt` (strict JSON instruction + parse + one retry). `ModelConfig.json_mode="auto"` uses the registry value.
  - `cache` support (Converse `cachePoint` for Claude and Nova) and `min_cache_tokens`.
  - `allows_temperature` (Claude 5.5: no).
  - `extra_fields` (Converse `additionalModelRequestFields`, for example a low thinking effort for the writer).
  - default prices.
- An unknown model gets safe defaults: `prompt` JSON mode, no cache, price unknown (role goes to `CostSummary.price_unknown`).

## 4. Verification cascade (A4)

Run per candidate. All thresholds come from `settings_for(job)` (config defaults + `JobSpec.options`). Every threshold and switch in this section is configurable (section 9). **Hard checks** (all of tier 1, and `extract.names`) stop the cascade on the first failure: the row is rejected. **Soft checks** (all Jev questions) run together in one call; their failures do not stop the cascade and are resolved by routing below.

### Tier 1: code (free)
| Check | Rule |
|---|---|
| `format` | Valid roles; user then assistant; non-empty; user 5 to 300 words; assistant 10 to 400 words |
| `banned_phrases` | Reject "according to the (text\|passage\|document)", "as an AI", "in the provided context" |
| `dedup` | Exact hash of normalized user turn, then embedding cosine > `DEDUP_COS` (0.92) against kept rows in the same cell |
| `numbers` | Every number in the assistant reply appears in the cited chunks or in the evidence index (code, not Jev). Numbers in the USER turn are also allowed, by `NUMBERS_ALLOW_USER`: `all` (default, every case type), `false_premise` (only that case type), `none`. A good correction repeats the user's wrong number ("It is 30 days, not 60"). Tier-2 `jev.corrects` still catches a reply that accepts the wrong value. |

### Tier 2: Jev + ScaleDown (about $0.0001 per row)
**`extract.names`**: runs only for the case types in `EXTRACT_NAMES_CASE_TYPES` (default all 4). ScaleDown Extract on the assistant reply with schema `{features[], settings[], urls[], limits[]}`. Each extracted name must match `EvidenceIndex.find()`. A name with no match is an invented feature: reject with detail `"Mentions 'bulk PDF export', which is not in the docs"`.
- Absent-topic exemption (`EXTRACT_EXEMPT_ABSENT=true`): for unanswerable and partial rows only, a name is exempt when rapidfuzz `token_set_ratio(name, absent_topic) >= ABSENT_MATCH` (85). A correct reply names the missing feature ("The docs do not cover bulk PDF export"). The check detail lists the exempt names: `"Exempt: 'bulk PDF export' is the absent topic"`.
- No exemption for answerable or false_premise. An invented name there is the hallucination that this check catches.
- A3 keeps its code check: `Retriever.top_k(absent_topic)` must not obviously contain the absent topic.

**Jev**: one Decisions call per candidate. `state` = passages + USER + ASSISTANT, clearly labelled. Questions by case type (descriptive option names only, never `0/1`):

| Case type | Check name | Type | Question | Pass |
|---|---|---|---|---|
| all | `jev.cell` | Choice | Which topic is the USER message about? options = topic names | top option == cell topic |
| all | `jev.quality` | Score | Rate the ASSISTANT reply as a support answer: `unusable, poor, acceptable, good, excellent` | >= 0.6 |
| all | `jev.realistic` | Noul | The USER message reads like a real person, not a test question | p >= 0.5 |
| answerable | `jev.supported` | Noul | Every factual claim in the ASSISTANT reply is stated in the PASSAGES | p >= KEEP_P |
| answerable | `jev.answers` | Noul | The ASSISTANT reply directly resolves what the USER asked | p >= KEEP_P |
| partial | `jev.supported` | Noul | as above | p >= KEEP_P |
| partial | `jev.flags_gap` | Noul | The ASSISTANT reply says which part the docs do not cover and offers a human handoff | p >= KEEP_P |
| unanswerable | `jev.not_in_docs` | Noul | The PASSAGES (top-5 retrieved for the USER message) contain the answer to the USER question | p <= 1 - KEEP_P (0.1); pass-direction prob = 1 - p |
| unanswerable | `jev.abstains` | Noul | The ASSISTANT reply says the docs do not cover this, offers a human handoff, and invents no details | p >= KEEP_P |
| false_premise | `jev.contradicted` | Noul | The PASSAGE contradicts the assumption in the USER message | p >= KEEP_P |
| false_premise | `jev.corrects` | Noul | The ASSISTANT reply politely corrects the wrong assumption using the PASSAGE | p >= KEEP_P |

`confidence` = minimum **pass-direction** probability across the **2 case-type Noul checks** only (not `jev.realistic`, `jev.cell` or `jev.quality`). Pass-direction is `p` for checks that pass on yes, and `1 - p` for checks that pass on no (`jev.not_in_docs`). So a row that passes every check always has `confidence >= KEEP_P`.

### Routing
1. Any hard fail: **rejected** (`reject_reason` = that check's detail).
2. Else `confidence < REJECT_P` (0.3): **rejected** (reason = the lowest Jev check).
3. Else all Jev checks pass (so `confidence >= KEEP_P`): **kept**.
4. Else (some Jev check failed, including `jev.cell`, `jev.quality` or `jev.realistic`, which are not part of `confidence`): **tier 3**.
- Also send a random `AUDIT_RATE` (2%) of kept rows to tier 3 (`audited = true`).

### Tier 3: judge model (default Sonnet 5.5)
The judge role model, through `get_llm(job, "judge")` (D33). Prompt in `prompts/judge.md`. Input: passages, case type, the row, and the tier-2 results. Output JSON `{"verdict": "keep" | "reject", "reason": "..."}`. The judge verdict is final. Tier-2 vs tier-3 agreement goes into `Report.judge_agreement`.

### Jev failure modes and guards
- About 11.5% wrong at >= 90% confidence: every kept answerable row needs both `jev.supported` and `extract.names`; tier-3 audit measures the real error rate.
- Follows option names: use descriptive names only.
- Weak at arithmetic and dates: tier-1 `numbers` covers this in code.

### DPO pairs (A4 `build_dpo_pairs`, A3 `generate_flawed`)
`DPO_MODE` picks the method: `synthesize` (default) | `pair` | `off`. It runs after the build loop, before the report. The budget guard applies.
- **`synthesize`**: sample a `DPO_RATE` (0.3) share of kept rows. For each, A3 `generate_flawed(row, ctx)` asks the Writer for one flawed reply to the SAME user turn, by case type:
  - answerable: add one plausible detail that is not in the passages;
  - partial: also answer the uncovered part with invented details;
  - unanswerable: answer confidently instead of abstaining;
  - false_premise: accept the wrong premise.
- A4 runs the flawed candidate through **tier 1 + tier 2 only** (no judge, no audit). Keep the pair only if a **content check** rejects the flawed reply (not `format` or `dedup`). Else drop it. So every pair has proof. `DPOPair.mode = "synthesized"`, `rejected_checks` = the failing content checks.
- **`pair`**: the old natural pairing. A kept reply and a rejected reply with the same normalized user turn in one cell. `DPOPair.mode = "natural"`.
- **`off`**: no DPO pairs.

## 5. Jev and ScaleDown clients (A2)

```python
# clients/jev.py
class Question(BaseModel):
    id: str
    type: Literal["noul", "choice", "score"]
    prompt: str
    options: list[str] | None = None        # choice: <= 255 descriptive names
    levels: list[str] | None = None         # score: 2-10 ordered levels

class Decision(BaseModel):
    value: str | bool | float
    prob: float                             # noul: P(yes); choice: P(top); score: normalized 0..1
    probs: dict[str, float] = {}

async def decide(state: str, questions: list[Question], purpose: str, *, job: Job) -> dict[str, Decision]
```
- Endpoint: the **direct Jev API** (not OpenRouter, D34), base URL `JEV_BASE_URL`, key `JEV_API_KEY` (Jev API console key), model `JEV_MODEL` (default `typesafe/jev-1.13-20260917`; check 1.14 and the model name form that the direct API uses). Raw `httpx`, no OpenAI SDK, no `temperature` / `max_tokens`. `JEV_BASE_URL` has no default (empty): **A2 confirms the base URL, the path, the auth header and the request/response shape at the first real call (by T+0:20)**, then sets the value in `.env` and sends it to A1 for `.env.example` and the `config.py` default. Until then, the Question/Decision shape above stays the contract.
- Fallback chain on 3 failures in a row: Noul and Choice -> ScaleDown Classify -> fallback model JSON answer. Score has no Classify equivalent, so Score goes straight to the fallback model JSON answer. The fallback model = `get_llm(job, "fallback")` (default: the writer model). Log to `CostSummary.fallbacks_used` and emit a `log` event; the UI shows a badge.
- `purpose` is a ledger tag: `triage`, `verify`, `probe`.

```python
# clients/scaledown.py
class ExtractField(BaseModel):
    name: str
    value: str
    confidence: float
    start: int
    end: int
    span_text: str

async def extract(text: str, schema: dict, purpose: str, *, job: Job) -> list[ExtractField]   # chat completions + response_format
async def summarize(text: str, purpose: str, instructions: str | None = None, *, job: Job) -> str
async def classify(text: str, labels: list[str], purpose: str, *, job: Job) -> dict[str, float]
async def compress(text: str, rate: str | float = "auto", *, job: Job) -> str
# `job` (keyword-only, all 5 functions): used for get_llm(job, "fallback") and ledger.record(job.id, ...). All callers pass it. /health uses A1 `health_job(user)`, a small system Job for the caller.
```
- Base URL `api.scaledown.xyz` or OpenRouter `scaledown/extract`, `scaledown/summarize`, `scaledown/classify-1`. **Research at first use (owner A2, by T+0:20; default `api.scaledown.xyz`).**
- Extract schema is guidance only. Code validates types and checks that `span_text` is a verbatim substring of the input; drop fields that fail.
- Extract fallback: fallback model extraction (`get_llm(job, "fallback")`) with the same schema, then the same verbatim-span check.
- Evidence schema for chunks: `{features[], settings[{name, value}], limits[{name, value}], procedures[], definitions[{term, meaning}], urls[]}`.

## 6. HTTP API (G1 builds on the orchestrator, section 7)

Base `/api`. JSON unless stated.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/ping` | | `{ok: true}` (no external calls; Lambda readiness check; no auth) |
| GET | `/me` | | `UserProfile` (made on first call) |
| GET | `/me/aws/setup` | | `{bob_account_id, external_id, template_url: "/api/me/aws/template", cli_command}` (`bob_account_id: null` when neither `BOB_ACCOUNT_ID` nor STS can tell) |
| GET | `/me/aws/template` | | the YAML file `bedrock-role.yaml` (read from `/app/infra/templates/`) |
| PUT | `/me/aws` | `BedrockAccess` | `UserProfile` (mode forced to `assume_role` in aws mode; clears `bedrock_verified_at`) |
| POST | `/me/aws/verify` | | `{ok, error?}` (AWS access only: `sts:AssumeRole`; sets `bedrock_verified_at`) |
| PUT | `/me/models` | `ModelRoles` (+ optional `api_keys: {role: key}` for openai_compatible, P1) | `UserProfile` (clears `models_verified_at`; never returns a key, only `api_key_set: true`) |
| POST | `/me/models/verify` | | `{ok, roles: {writer: "ok" \| error, planner: ..., judge: ..., fallback: ...}}` (one tiny real call per configured role, all providers; sets `models_verified_at`) |
| GET | `/me/models/available` | | `{region, models: [{id, name, provider, kind: "inference_profile" \| "foundation_model", on_demand}]}`: Bedrock foundation models and inference profiles in the user's region (`bedrock:ListFoundationModels`, `bedrock:ListInferenceProfiles` through the assumed role) |
| POST | `/uploads` | multipart files (body <= 6 MB) | `{upload_ids: [...], files: [{id, name, bytes}]}` |
| POST | `/uploads/presign` | `{name, bytes, content_type?}` | `{upload_id, put_url, method: "PUT", headers, name, bytes}`: files over 5 MB. aws: presigned S3 PUT (15 min); local: `PUT /api/uploads/{upload_id}/content` on this API |
| PUT | `/uploads/{id}/content` | raw bytes | `{id, name, bytes}` (local mode only; 409 in aws mode, 400 on a size mismatch) |
| GET | `/connectors` | | `[{toolkit, connected: bool, account_id?}]` |
| POST | `/connectors/{toolkit}/connect` | `{redirect_url}` | `{auth_url, connection_id}` (Composio OAuth) |
| GET | `/connectors/{toolkit}/status` | `?connection_id=` | `{connected, account_id}` |
| GET | `/connectors/{toolkit}/browse` | `?account_id=&q=` | `[{id, title, kind}]` (pages, spaces, projects) |
| POST | `/sources/preview` | `SourceSpec` | `{documents: [{uri, title, chars}], capped: bool}` (fetch only, no job; max 10 pages or 20 s) |
| POST | `/jobs` | `JobSpec` | `Job` (status moves to `awaiting_approval` when the plan is ready). 412 if AWS access or models are not verified; 429 if capacity is full |
| GET | `/jobs` | | `[Job]` (summary fields; only the caller's jobs) |
| GET | `/jobs/{id}` | | `Job` |
| PUT | `/jobs/{id}/plan` | `Plan` (edited) | `Job` (sets the `approved` control flag; the runner starts the build) |
| POST | `/jobs/{id}/cancel` | | `Job` |
| GET | `/jobs/{id}/events` | header `Last-Event-ID` | SSE stream (section 8) |
| GET | `/jobs/{id}/rows` | `?verdict=&cell_id=&offset=&limit=` | `{total, rows: [Row]}` |
| GET | `/jobs/{id}/rows/{row_id}` | | `Row` |
| POST | `/jobs/{id}/rows/{row_id}/spot-check` | `{ok: bool}` | `Report` |
| POST | `/jobs/{id}/export` | `{preset, formats}` | `{files: {...}}` |
| GET | `/jobs/{id}/files/{name:path}` | | file download (aws: 302 to a presigned S3 URL). `name` = a `Job.files` key, e.g. `openai-chat/train/train.jsonl` |
| GET | `/jobs/{id}/files/{name:path}/url` | | `{url}` (aws: presigned S3 GET, 1 h; local: `/api/jobs/{id}/files/{name}`) |
| POST | `/jobs/{id}/resync` | | `Job` (section 10; 409 unless the job is done with a plan) |
| GET | `/presets` | | `[{name, formats, description}]` |
| GET | `/health` | | `{keys: {bedrock, jev, scaledown, firecrawl, composio}}` (each key: a real test call result, `ok` or the error). `bedrock` uses the caller's profile, or `"not connected"`. Needs a signed-in user |

Route rules (D25, G1):
- Every route returns in < 25 s (CloudFront origin timeout). The SSE route is the only long response.
- A route never starts background work. A task that starts after the response freezes in Lambda. Long work goes to the runner (section 7).
- Request bodies are <= 6 MB (Lambda limit). `POST /uploads` keeps multipart for P0. The demo files are small.
- `POST /uploads` stores each file through `Blobs.put("runs/uploads/<upload_id>/<name>")`. It writes nothing outside `settings.runs_dir`.
- `POST /sources/preview` stops at 10 pages or 20 s. It sets `capped: true` when it stops early.
- `GET /jobs/{id}/files/{name:path}`: if `blobs.url(key, filename)` returns a URL, reply 302 to it. Else stream the local file.
- The frontend downloads through the `/url` route. A plain link cannot send the auth header.
- `GET /ping` makes no external calls. `/health` makes paid calls, so it must not run on each cold start.
- Composio OAuth `redirect_url` = `BOB_PUBLIC_URL + BOB_OAUTH_CALLBACK_PATH` (`/oauth/callback`). G3 serves this route.
- The frontend calls the relative base `/api` (same origin through CloudFront). The Vite dev server proxies `/api` to `localhost:8000`. No hard-coded host (G3).

Ownership and status rules (D27, G1):
- No sign-in: every route acts as the built-in user `local` through G1 `api/auth.py` `current_user()` (section 14). Routes still take the user from that dependency, so the owner rules below hold and tests can act as another user.
- Every `/jobs/{id}/*` route returns HTTP 404 when `Job.owner_id` is not the caller's id. Do not tell the caller that the job exists.
- `POST /jobs` returns HTTP 412 `{"error": "connect AWS first"}` when `bedrock_verified_at` is not set, and HTTP 412 `{"error": "verify models first"}` when `models_verified_at` is not set. Local mode applies the same rule: A1 runs `verify_bedrock` and `verify_models` once for the `local` user (real calls on the default chain) before the first local job.
- `POST /jobs` returns HTTP 429 `{"error": "too many running jobs"}` when the runner is busy (section 7). Nothing is saved.

## 7. Orchestrator (A1) and connector (G1/G2) interfaces

```python
# bob/orchestrator.py: the only backend API the web layer calls
class Orchestrator:
    async def create_job(self, spec: JobSpec, user: UserProfile) -> Job
                                                                # 1. bedrock_verified_at or models_verified_at not set -> 412; 2. capacity check -> RunnerBusy -> 429 (nothing saved);
                                                                # 3. save Job (owner_id = user.id, bedrock = snapshot of user.bedrock,
                                                                #    models = spec.options.models or user.models)
                                                                # + emit job.status created + runner.start(id, "create"); returns at once (< 1 s)
    async def run_job(self, job_id: str, mode: Literal["create", "resync"]) -> None
                                                                # the whole job body; both runners call it:
                                                                # ingest -> read -> plan -> wait for approval -> build -> fill gaps -> report -> export -> done
    async def approve_plan(self, job_id: str, plan: Plan) -> Job  # store.set_control(id, "approved", plan); returns the Job
    async def cancel(self, job_id: str) -> Job                  # store.set_control(id, "cancel"); see the rules below
    async def get_job(self, job_id: str) -> Job                 # async: reads DynamoDB / S3 in aws mode; runs the watchdog
    async def list_jobs(self, owner_id: str) -> list[Job]       # only this user's jobs
    async def list_rows(self, job_id, verdict=None, cell_id=None, offset=0, limit=50) -> tuple[int, list[Row]]
    async def get_row(self, job_id, row_id) -> Row
    async def spot_check(self, job_id, row_id, ok: bool) -> Report
    async def export(self, job_id, preset, formats) -> dict[str, str]
    async def resync(self, job_id) -> Job                       # P1: runner.start(id, "resync")
    def subscribe(self, job_id, last_event_id: int | None) -> AsyncIterator["Event"]   # runs the watchdog in the SSE loop
    # users + Bedrock access (section 14)
    async def get_or_create_user(self, user_id: str, email: str | None) -> UserProfile   # new profile: random external_id (uuid4)
    async def update_bedrock(self, user_id: str, access: BedrockAccess) -> UserProfile
                                                                # clears bedrock_verified_at
    async def verify_bedrock(self, user_id: str) -> dict        # AWS access only: sts:AssumeRole; < 25 s;
                                                                # sets bedrock_verified_at on success; returns the /me/aws/verify shape
    # models (D33)
    async def update_models(self, user_id: str, models: ModelRoles,
                            api_keys: dict[str, str] | None = None) -> UserProfile   # clears models_verified_at; api_keys P1 (KMS-encrypted)
    async def verify_models(self, user_id: str) -> dict         # one tiny real call per configured role (all providers), checks JSON output; < 25 s;
                                                                # sets models_verified_at on success; returns the /me/models/verify shape
    def health_job(self, user: UserProfile) -> Job              # small system Job (not saved) with the caller's bedrock + models; /health and verify calls pass it as `job`

# bob/connectors/__init__.py: the only connector API the orchestrator calls
async def fetch_documents(spec: SourceSpec, job_id: str,
                          progress: Callable[[int, int, str], Awaitable[None]],
                          *, user_id: str) -> list[Document]
# user_id = Job.owner_id. G1 passes it to the G2 Composio functions, which use COMPOSIO_USER_PREFIX + user_id.
# G2 Composio functions: connect(toolkit, redirect_url, *, user_id), status(toolkit, connection_id, *, user_id),
# browse(toolkit, account_id, q, *, user_id), fetch(spec, job_id, progress, *, user_id). The connector routes pass current_user().id.

# bob/connectors/upload.py (G1): read an upload through Blobs, not from a disk path
async def read_upload(upload_id: str) -> list[tuple[str, bytes]]   # [(name, data)] from "runs/uploads/<upload_id>/"
```

Job lifecycle rules (A1):
- `run_job` waits for approval. It polls `store.get_control` every `BOB_CONTROL_POLL_S` (1 s), up to `BOB_APPROVAL_WAIT_MINUTES` (60). When `Control.state == "approved"`, it builds from `Control.plan` (the approved plan). Then it runs the build loop.
- `run_job` checks the control flag for `cancel` between stages and before each Writer call.
- `cancel`: if no worker runs (`runner.is_running(id)` is false), set status `cancelled` and emit the event. The aws runner calls `stop()` after 10 s if the task still runs.
- The worker calls `store.put_job` on each status change and at most every 2 s.
- **Heartbeat.** The worker writes `Job.heartbeat_at` every `BOB_HEARTBEAT_S` (10 s), also while it waits for approval.
- **Watchdog** (A1, in `get_job` and in the SSE loop of `subscribe`): if the status is not terminal (`done`, `error`, `cancelled`), and `now - heartbeat_at > BOB_HEARTBEAT_TIMEOUT_S` (90 s; covers the Fargate cold start; before the first heartbeat use `created_at`), and `runner.is_running(id)` is false: set status `error`, set `Job.error = "worker stopped: <stoppedReason>"`, and append one `error` event. Use a conditional update on META (`status` unchanged), so two API instances do not both write. This keeps the single event writer rule: no worker runs.
- **Capacity.** `Runner.start` raises `RunnerBusy` when `BOB_MAX_WORKERS` tasks run, or when the user already has `BOB_MAX_ACTIVE_JOBS_PER_USER` (1) active jobs. `create_job` checks capacity **before** it saves the job. The route returns HTTP 429. Nothing is saved.
- `Job.files` is set by A1 from the return value of `export()`. `verify` does not set it.
- **Single event writer.** The API appends events only in `create_job`, in `cancel` when no worker runs, and in the watchdog when no worker runs. The worker reads `last_seq` at start. While it runs, it is the only writer.
- **Single job writer.** While a worker runs, only the worker writes the job, rows and events. `spot_check` and `export` run in the API process and write rows, the report and files. They are allowed only when the job status is `done`, `cancelled` or `error` and `runner.is_running(id)` is false (no worker runs). Otherwise the route returns HTTP 409 with `{"error": "job is running"}`. They do not emit events. They must finish in less than 25 s.
- The API emits the `stage.progress` event `{stage: "fetch", done: 0, total: 0, detail: "starting worker"}` in `create_job`, before `runner.start`. This shows the Fargate cold start in the UI.
- After export, the orchestrator calls `blobs.upload_tree(runs_dir/<job_id>/export, "runs/<job_id>/export")`. In local mode this is a no-op.
- Fargate keeps one worker task per job across the plan approval. So the read state (chunks, embeddings, EvidenceIndex, Retriever) stays in the process. Nothing serializes these objects.

### Backend protocols (A1 defines them and the local impls by T+0:15; A5 writes the aws impls)
```python
# core/blobs.py (A1)  keys are relative paths that mirror the local runs/ tree, e.g. "runs/<job_id>/export/openai-chat/train/train.jsonl"
class Blobs(Protocol):
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None
    async def get(self, key: str) -> bytes
    async def exists(self, key: str) -> bool
    async def list(self, prefix: str) -> list[str]
    async def upload_tree(self, local_dir: Path, prefix: str) -> list[str]
    async def url(self, key: str, filename: str | None = None) -> str | None   # aws: presigned GET (1 h); local: None (route streams the file)

# core/store.py (A1)
class Store(Protocol):
    async def put_job(self, job: Job) -> None          # worker calls it on each status change and at most every 2 s
    async def get_job(self, job_id: str) -> Job
    async def list_jobs(self, owner_id: str) -> list[Job]   # only this user's jobs
    async def put_rows(self, job_id: str, rows: list[Row]) -> None
    async def list_rows(self, job_id, verdict=None, cell_id=None, offset=0, limit=50) -> tuple[int, list[Row]]
    async def get_row(self, job_id: str, row_id: str) -> Row
    async def set_control(self, job_id: str, control: Literal["approved", "cancel"], plan: Plan | None = None) -> None
    async def get_control(self, job_id: str) -> Control   # state + approved plan (aws: META control + plan_key -> runs/<id>/approved_plan.json)
    async def get_user(self, user_id: str) -> UserProfile | None   # aws: USER#<sub> / PROFILE; encrypted API keys (P1) live in the same item, never in UserProfile
    async def put_user(self, user: UserProfile) -> None

# core/events.py (A1)  throttling (cell.update 5/s per cell, cost + counts 2/s per job) stays above the backend
class EventLog(Protocol):
    async def append(self, job_id: str, type: str, data: dict) -> int     # returns seq
    async def read_after(self, job_id: str, seq: int) -> list[Event]
    def subscribe(self, job_id: str, last_event_id: int | None) -> AsyncIterator[Event]   # local: queue; aws: poll read_after every BOB_EVENT_POLL_MS

# core/runner.py (A1)
class Runner(Protocol):
    async def start(self, job_id: str, mode: Literal["create", "resync"]) -> None   # local: asyncio task running Orchestrator.run_job; aws: ecs.run_task
                                                                                    # raises RunnerBusy (BOB_MAX_WORKERS or BOB_MAX_ACTIVE_JOBS_PER_USER reached)
    async def stop(self, job_id: str) -> None                                       # aws: ecs.stop_task (used 10 s after a cancel flag if the task still runs)
    async def is_running(self, job_id: str) -> bool                                 # local: asyncio task exists and not done;
                                                                                    # aws: META task_arn + ecs.describe_tasks, running unless lastStatus == STOPPED
                                                                                    # used by cancel, the HTTP 409 rule and the watchdog

class RunnerBusy(Exception): ...                                                    # core/runner.py; the route maps it to HTTP 429

# core/backends.py (A1): get_blobs(), get_store(), get_events(), get_runner() pick by BOB_ENV; import bob.aws.* lazily.
# core/cache.py (A1): real-response cache stored through Blobs under "cache/<sha256>.json".
```
`BOB_ENV=local` (default) keeps in-memory state + `runs/` on disk, the in-process asyncio runner and the in-memory event log. `BOB_ENV=aws` switches every backend at once through `core/backends.py`. The orchestrator code is the same in both modes. All checkpoint-1 work and all tests run in local mode first. The aws impls use boto3 inside `asyncio.to_thread` (no aioboto3).

Build loop inside `run_job`, after approval (A1 writes it, calling A3/A4):
```
round 1: for each enabled cell (concurrency WRITER_CONCURRENCY): generate(target * OVERGEN) -> verify -> store rows -> emit
round 2..MAX_ROUNDS: plan_gap_round() -> generate -> verify     (stop when targets met, budget hit, or MAX_ROUNDS)
then: await build_dpo_pairs(rows, ctx) -> build_report -> export(spec.preset, spec.formats) -> job.files = export() result -> done
budget guard: stop new writer calls when cost.total_usd >= 0.95 * budget_usd (also for generate_flawed)
thresholds: OVERGEN, MAX_ROUNDS and the others come from settings_for(job)
```

### Ledger and seeds (A1)
```python
# core/ledger.py: every external call records here (G2 uses it for Firecrawl and Composio). bucket = role name or service name.
# usd=None -> price from ModelConfig.price_*_per_m, else the registry; no price -> role goes to CostSummary.price_unknown
def record(job_id: str, bucket: str, *, calls: int = 1, in_tokens: int = 0, out_tokens: int = 0,
           usd: float | None = None, model: str | None = None) -> None   # usd=None -> computed from config prices
def frontier_only_estimate(job_id: str) -> float                  # same token counts priced at the judge role model price

# orchestrator: seed parsing (A1). G1 stores the upload; A1 parses it.
def load_seeds(data: bytes, name: str) -> list[list[Message]]   # JSONL {"messages": [...]} or {"user","assistant"}; CSV columns user,assistant
```
`load_seeds` takes bytes, not a path. The seed file lives in Blobs (S3 in aws mode), so no local path exists. The caller gets the bytes from `read_upload(spec.seed_upload_id)`. `name` gives the file extension, which picks the JSONL or CSV parser. A pure function on bytes is also simple to test.

## 8. SSE events (A1 emits, G4 renders)

Wire format: `id: <seq>\nevent: <type>\ndata: <json>\n\n`. The store keeps every event per job, so a client that reconnects with `Last-Event-ID` gets a replay.

Wire rules (D25; G1 sends, G4 reads):
- Stream: G3's SSE helper uses `@microsoft/fetch-event-source` and sends `Last-Event-ID` itself on each reconnect. It closes on a terminal event only when `GET /jobs/{id}` says the job is finished now (a re-synced job replays an older `done`). The SSE route checks the owner like every `/jobs/{id}/*` route.
- At stream start, send `retry: 1000`.
- Send a `: ping` comment every `BOB_SSE_HEARTBEAT_S` (15 s). CloudFront cuts an idle stream.
- Headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- The server closes the stream after `BOB_SSE_MAX_S` (840 s). The browser reconnects with `Last-Event-ID` and gets the replay. A closed stream is normal.
- The client closes the stream only on `done`, `error`, or `job.status cancelled`.
- In aws mode the SSE route polls `read_after` every `BOB_EVENT_POLL_MS` (500 ms).
- Single event writer (section 7). Each event item uses a conditional put (`attribute_not_exists(sk)`), so a seq collision fails loudly.
- The SSE loop runs the watchdog (section 7). When the worker stopped, the stream gets one `error` event `{message: "worker stopped: <stoppedReason>"}`, and the client closes the stream.

| Event | Data |
|---|---|
| `job.status` | `{status, detail}` |
| `stage.progress` | `{stage, done, total, detail}` (stage: fetch, chunk, triage, topics, evidence, plan, generate, verify, export) |
| `counts` | `Job.counts` |
| `cost` | `CostSummary` |
| `plan.ready` | `Plan` |
| `cell.update` | `{cell_id, generated, kept, rejected, judged, target}` (throttle: max 5/s per cell) |
| `row` | `{id, cell_id, verdict, reject_reason, case_type, user_preview, confidence, routed_to_judge}` |
| `round` | `{n, reason, cells: [cell_id], planned: int}` |
| `report.ready` | `Report` |
| `files.ready` | `{files}` |
| `log` | `{level, message}` (fallbacks, warnings) |
| `error` | `{message}` |

## 9. Config (`backend/bob/config.py`, env vars)

```
AWS_REGION, AWS_PROFILE or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY    # Bob's own AWS (hosting); Bedrock only when BOB_BEDROCK_AUTH=default
# model defaults for new profiles (D33); format <provider>:<model_id>; they replace BOB_WRITER_MODEL / BOB_JUDGE_MODEL / BOB_PLANNER_MODEL
BOB_DEFAULT_WRITER_MODEL=bedrock:global.anthropic.claude-haiku-5-5     # research the exact id at first use (owner A1, first Bedrock call T+0:20)
BOB_DEFAULT_PLANNER_MODEL=bedrock:global.anthropic.claude-sonnet-5-5
BOB_DEFAULT_JUDGE_MODEL=bedrock:global.anthropic.claude-sonnet-5-5
BOB_DEFAULT_FALLBACK_MODEL=                             # empty = the writer model
BOB_MODEL_REGISTRY=bob/llm/registry.json                # model capabilities + default prices
BOB_KMS_KEY_ID                                          # aws: KMS key (alias/bob-user-keys) that encrypts user API keys (P1)
JEV_API_KEY                                            # Jev API console key; Jev is called through its direct API (D34)
JEV_BASE_URL=                                          # no default; A2 confirms the base URL at the first real call
JEV_MODEL=typesafe/jev-1.13-20260917
OPENROUTER_API_KEY=                                    # optional: only for ScaleDown via OpenRouter (section 5); not used by Jev
SCALEDOWN_API_KEY, SCALEDOWN_BASE_URL=https://api.scaledown.xyz
FIRECRAWL_API_KEY
COMPOSIO_API_KEY
COMPOSIO_USER_PREFIX=bob-                               # Composio user_id = COMPOSIO_USER_PREFIX + UserProfile.id (replaces COMPOSIO_USER_ID)
COMPOSIO_DEMO_ACCOUNTS=notion:<connected_account_id>   # pre-connected demo accounts, comma-separated; demo user only
KEEP_P=0.9  REJECT_P=0.3  AUDIT_RATE=0.02  DEDUP_COS=0.92
OVERGEN=1.6  MAX_ROUNDS=3  WRITER_BATCH=5
WRITER_CONCURRENCY=16  JEV_CONCURRENCY=32  SCALEDOWN_CONCURRENCY=16  JUDGE_CONCURRENCY=4
PRICES: LLM prices come from the registry per model id (ModelConfig.price_* overrides); default models: writer $0.10/$0.50, judge+planner $2/$10 per M tokens; jev $0.042/M in, scaledown $0.04/M in   # research at first use (owner A1, by T+1:30)

# verification and data (section 4); a job can override the starred ones with JobSpec.options (* = JobOptions field)
EXTRACT_NAMES_CASE_TYPES=answerable,partial,unanswerable,false_premise   # case types that run extract.names
EXTRACT_EXEMPT_ABSENT=true  ABSENT_MATCH=85             # * extract_exempt_absent; rapidfuzz token_set_ratio vs absent_topic
NUMBERS_ALLOW_USER=all                                  # * all | false_premise | none
DPO_MODE=synthesize  DPO_RATE=0.3                       # * synthesize | pair | off; share of kept rows that get a flawed twin
CELL_AXES=topic,case_type                               # * axes that form cells; the other axes are mix axes
MAX_CELLS=120  MAX_TOPICS=20  MIN_CELL_TARGET=3         # * max_cells
CASE_MIX=answerable:0.5,partial:0.15,unanswerable:0.2,false_premise:0.15   # * case_mix
# also JobOptions: keep_p, reject_p, audit_rate, max_rounds, overgen, models

# accounts and BYO AWS (section 14)
BOB_AUTH=none                       # none | cognito; aws deploy sets cognito
BOB_COGNITO_REGION, BOB_COGNITO_USER_POOL_ID, BOB_COGNITO_CLIENT_ID, BOB_COGNITO_DOMAIN
BOB_SIGNUP=invite                   # open | invite (CDK selfSignUpEnabled)
BOB_BEDROCK_AUTH=default            # default | assume_role; aws deploy sets assume_role
BOB_ACCOUNT_ID                      # Bob's hosting AWS account id, shown on the Account screen
BOB_CRED_REFRESH_S=300              # refresh assumed-role credentials this many seconds before expiry
BOB_BEDROCK_DEFAULT_REGION=us-east-1   # default Bedrock region for new profiles
BOB_MAX_ACTIVE_JOBS_PER_USER=1
BOB_HEARTBEAT_S=10  BOB_HEARTBEAT_TIMEOUT_S=90
BOB_OAUTH_CALLBACK_PATH=/oauth/callback

# deployment (D25; A1 adds them to config.py at T+0:15)
BOB_ENV=local                       # local | aws
BOB_RUNS_DIR=runs                   # aws: /tmp/runs (Lambda /tmp is the only writable path; ephemeral storage 2 GB)
BOB_TABLE=bob  BOB_BUCKET=<data bucket>  BOB_SECRET_ARN=<arn of bob/keys>
BOB_ECS_CLUSTER, BOB_TASK_DEF, BOB_SUBNETS (comma list), BOB_SECURITY_GROUP, BOB_CONTAINER_NAME=worker
BOB_MAX_WORKERS=2                   # aws runner refuses a new job when 2 tasks run (protects the budget)
BOB_CONTROL_POLL_S=1  BOB_APPROVAL_WAIT_MINUTES=60
BOB_EVENT_POLL_MS=500  BOB_SSE_HEARTBEAT_S=15  BOB_SSE_MAX_S=840
BOB_PUBLIC_URL=<CloudFront URL>     # OAuth redirect = BOB_PUBLIC_URL + BOB_OAUTH_CALLBACK_PATH; CORS
BOB_EMBED_MODEL_PATH=/opt/models/potion-base-8M   # baked into the image; no Hugging Face download at runtime
# Lambda only (set by CDK): AWS_LWA_INVOKE_MODE=response_stream, AWS_LWA_PORT=8080, AWS_LWA_READINESS_CHECK_PATH=/api/ping
```

In aws mode, `config.py` loads the secret JSON from `BOB_SECRET_ARN` into the environment before it reads Settings (helper `bob/aws/secrets.py`, A5). The secret `bob/keys` holds JEV_API_KEY, SCALEDOWN_API_KEY, FIRECRAWL_API_KEY, COMPOSIO_API_KEY and the other keys. Bedrock uses no stored keys: in aws mode it assumes the user's `BobBedrockAccess` role (section 14).

`settings_for(job) -> EffectiveSettings` (A1, `config.py`): the env defaults above, with each non-None `JobSpec.options` field on top. All pipeline code reads thresholds through it. The manifest records the effective values (section 11).

LLM client (D33): pipeline code calls `get_llm(job, role)` (section 3). The `bedrock` provider uses the Bedrock **Converse API** (`bedrock-runtime` `converse`) through boto3 in `asyncio.to_thread`. Credentials come from the job's `BedrockAccess` through `llm/credentials.py` (botocore `RefreshableCredentials`). No Anthropic SDK in the request path. Use prompt caching (Converse `cachePoint`) on the Writer system prompt + topic brief (same per cell) when the registry says the model supports it. Request structured JSON output by the registry `json_mode`; on parse failure, retry once, then drop.

## 10. Re-sync (P1, G2 + A1; built 2026-10-31)
0. `POST /jobs/{id}/resync` works on a `done` job with a plan (else 409; 429 at capacity). The UI link is "Check the sources again" on the Report screen. No change in the sources: the job goes back to `done` at once.
1. `sync.py` re-fetches each `SourceSpec` and compares `Document.content_hash` per `uri`: `added`, `changed`, `removed` (`refetch_diff(job, old_docs, progress) -> (new_docs, diff, stale_doc_ids)`; the orchestrator keeps each fetch in `runs/<job>/docs/` + `docs.json`).
2. The orchestrator reads the current documents again (all of them, so evidence and retrieval cover the whole corpus).
3. Kept rows whose `spans` point to changed or removed docs are verified again (tier 1 + tier 2). Rows that fail become `rejected` with reason `stale: source changed`.
4. Affected cells get a gap round. Emit `round` with `reason: "resync"`.

## 11. Export (A4)

Canonical rows -> preset -> format. One data file per folder (ModelForge rule, D9): `runs/<job_id>/export/<preset>/<split>/<split>.<ext>`, for example `export/openai-chat/train/train.jsonl` and `export/openai-chat/eval/eval.jsonl`. Always write `bob_manifest.json` and `provenance.parquet` (row id, cell, coords, spans, checks, confidence) next to the data. The manifest records the effective settings of the job (`settings_for(job)`: defaults + `JobSpec.options`).

`export()` returns a dict. Each key is the file path relative to the job export folder, the same as the disk path, for example `openai-chat/train/train.jsonl`. A1 copies this dict into `Job.files`. The file routes use the same key as `{name:path}` (section 6).

Export writes files only under `settings.runs_dir` (`<runs_dir>/<job_id>/export/...`), never a hard-coded `runs/`. In aws mode the orchestrator then uploads the export tree to S3 with `blobs.upload_tree` (section 7). A4 does not call S3.

| Preset | Row shape |
|---|---|
| `openai-chat` (default) | `{"messages": [system, user, assistant, ...]}` |
| `sharegpt` | `{"conversations": [{"from": "system"/"human"/"gpt", "value": ...}]}` |
| `alpaca` | `{"instruction": user, "input": "", "output": assistant}` (single turn only) |
| `modelforge-chat` | `{"messages": [...]}` canonical columns only |
| `modelforge-sft` | `{"prompt": user, "completion": assistant}` (single turn only) |
| `dpo` | `{"prompt": [...messages], "chosen": str, "rejected": str}` from `DPOPair` (section 4; `row_id`, `mode` and `rejected_checks` go to provenance). Empty when `DPO_MODE=off` |
| `full` | whole `Row` including provenance |

Formats: `jsonl` (required), `json`, `csv`, `parquet` (required). Splits: `train` 95%, `eval` 5%, stratified by cell.

## 12. Real-only development contract
- **No mock clients, no fake responses, no fake corpus.** A failing external call fails loudly with the provider's error in a `log` event and in `/health`.
- `core/cache.py` stores **real** responses through Blobs (`cache/<sha256>.json`; local: disk, aws: S3), keyed by sha256 of (endpoint, model, request body). It saves money and time on re-runs. It never invents a response. `BOB_CACHE=0` turns it off for the final demo run if needed.
- `demo/smoke/`: 3 to 5 real pages (Firecrawl scrape of the demo docs, saved as markdown) plus 10 real seed questions, written to disk by G2 at T+0:20. All backend tests run on this corpus with real calls and small sizes (for example `target_rows=20`).
- `demo/corpus/`: the full real crawl of the demo docs, cached by G2 by T+1:30.
- Frontend agents build against the real API. Until a route exists, they build the component against the `types.ts` shapes, then connect it the moment the route lands. They never ship hard-coded data.
- G1 ships `POST /uploads`, `POST /jobs` and the MD parser by T+0:45. A1 delivers a **thin real path** by T+0:50: `POST /jobs` with `SourceSpec(kind="upload")` pointing at the uploaded `demo/smoke/` files -> real chunk -> real Writer -> real Jev check -> rows in the store -> SSE events. All other work hangs on this path. Local mode and the thin path use `BOB_AUTH=none` (user `local`) and `BOB_BEDROCK_AUTH=default` (default boto3 chain). Auth and BYO AWS do not block the thin path or checkpoint 1.
- **Cloud thin path (A5).** By T+1:15: the CloudFront URL serves the UI, and `/api/ping` and `/api/health` work there with the current backend code. Checkpoint 1 (T+1:30) includes this cloud health check, and sign-in works on the CloudFront URL and `/me` returns the profile. By T+2:00: one real job runs in the cloud with the demo user's assume-role Bedrock access: create -> Fargate worker -> plan -> approve -> rows on SSE through CloudFront -> file download from S3. Measure the worker cold start here.
- `demo/` is copied into the image. G2 commits `demo/corpus/` before the checkpoint-2 deploy. Checkpoint 2 (T+2:50) runs the pass test on the CloudFront URL (P0): sign in -> Connect AWS (verified) -> job -> rows -> download.

## 13. AWS deployment (A5)

Local mode (`BOB_ENV=local`) stays the default. `BOB_ENV=aws` switches every backend at once (section 7). Decision D25.

### Architecture
```
 Browser ──► CloudFront (one domain)
               ├─ default  ──► S3 frontend bucket (React build; CloudFront Function rewrites non-file paths to /index.html)
               └─ /api/*   ──► Lambda Function URL (invoke mode RESPONSE_STREAM)
                               API Lambda = FastAPI container + AWS Lambda Web Adapter (short routes + SSE)
                                  │ create_job / resync ──► ecs.run_task ──► Fargate worker task (one per job)
                                  │ approve / cancel    ──► control flag in DynamoDB (worker polls it every 1 s)
                                  └ SSE ◄── polls DynamoDB events every 500 ms
 Fargate worker = same image, CMD `python -m bob.worker <job_id> <mode>`: ingest -> read -> plan -> wait for approval -> build loop -> report -> export -> done -> exit
 State:   DynamoDB table `bob` (job summary + control, events, rows)  +  S3 data bucket (job.json, docs, chunks, exports, uploads, cache)
 Secrets: one Secrets Manager secret `bob/keys` (JSON: JEV_API_KEY, SCALEDOWN_API_KEY, FIRECRAWL_API_KEY, COMPOSIO_API_KEY, ...). Bedrock uses no stored keys: STS AssumeRole into each user's BobBedrockAccess role.
 Auth:    Cognito user pool (stack BobData). The API checks the access token (api/auth.py).
 KMS:     one KMS key (stack BobData, alias alias/bob-user-keys) encrypts user API keys for openai_compatible models (P1).
 Bedrock: runs in the USER's AWS account and region (section 14). Bob's hosting region (Lambda, Fargate, DynamoDB, S3, Cognito) is separate.
 Network: default VPC, public subnets, assignPublicIp=ENABLED, egress-only security group (no NAT cost). Lambda outside the VPC.
 IaC:     AWS CDK v2 in Python, `infra/`. Two stacks: `BobData` (table, data bucket, frontend bucket, secret, Cognito user pool, KMS key) and `BobApp` (image, Lambda + URL, ECS cluster + task def, CloudFront, IAM).
```

### Cognito user pool (stack `BobData`)
- Email sign-in. App client without a secret, PKCE. Managed login domain.
- `BOB_SIGNUP=invite` sets CDK `selfSignUpEnabled=false`; `open` sets it to true. The team creates the demo user with `aws cognito-idp admin-create-user`.
- A5 posts the pool id, client id and domain with the other names after `BobData` deploys (T+0:00 to T+0:20). They go to `BOB_COGNITO_*` (section 9).
- The Lambda Function URL stays `AuthType NONE` behind CloudFront. The API checks the token. The origin-secret header stays P1.

### DynamoDB table `bob`
On-demand. `pk` and `sk` are strings. TTL attribute `expires_at` = 7 days, on `JOB#` items only. `USER#` items (profile and job list) have no TTL.

| pk | sk | attributes |
|---|---|---|
| `JOB#<id>` | `META` | status, counts (JSON), cost_usd, control, plan_key, task_arn, last_seq, owner_id, heartbeat_at, updated_at |
| `JOB#<id>` | `EVT#<seq:08d>` | type, data (JSON string) |
| `JOB#<id>` | `ROW#<row_id>` | n (insert order), verdict, cell_id, body (Row JSON string) |
| `USER#<sub>` | `PROFILE` | UserProfile JSON; P1: `api_keys` (KMS-encrypted per role, never sent to the client) |
| `USER#<sub>` | `JOB#<created_at>#<id>` | summary for `GET /jobs` (only this user's jobs; replaces `JOBS` / `<created_at>#<id>`) |

- The full Job document (plan, cells, report) lives in S3 `runs/<id>/job.json`. It can pass the 400 KB item limit.
- META `control` + `plan_key`: `approve_plan` writes the approved plan JSON to S3 `runs/<id>/approved_plan.json` and sets `plan_key`. `get_control` returns `Control(state, plan)`.
- The watchdog writes META with a condition: `status` is unchanged (section 7).- `read_after` = Query with `sk > EVT#<seq>` and `begins_with EVT#`, ConsistentRead.
- `EVT#` puts use `attribute_not_exists(sk)` (single event writer, section 7).

### S3 data bucket layout (mirrors local `runs/`)
```
runs/uploads/<upload_id>/<file>
runs/<job_id>/job.json
runs/<job_id>/approved_plan.json
runs/<job_id>/docs/
runs/<job_id>/chunks.jsonl
runs/<job_id>/export/<preset>/<split>/...    + bob_manifest.json, provenance.parquet
cache/<sha256>.json
```

### Runtime sizes
| Part | Size |
|---|---|
| API Lambda | 2048 MB, timeout 900 s, x86_64, ephemeral storage 2048 MB, reserved concurrency 20 |
| Worker task | Fargate 2 vCPU / 4 GB, x86_64, logs to CloudWatch `/bob/worker` |
| Max workers | `BOB_MAX_WORKERS=2` running tasks |

### IAM
| Role | Permissions |
|---|---|
| `BobApiRole` (Lambda role) | DynamoDB + S3 (data bucket) + `ecs:RunTask/StopTask/DescribeTasks` + `iam:PassRole` (task + execution roles) + `secretsmanager:GetSecretValue` + `sts:AssumeRole` on `arn:aws:iam::*:role/BobBedrockAccess*` (for `/me/aws/verify`, `/me/models/verify`, `/health` and spot-check) + `kms:Encrypt`, `kms:Decrypt` on the BobData KMS key |
| `BobWorkerTaskRole` (worker task role) | DynamoDB + S3 + secret + `sts:AssumeRole` on `arn:aws:iam::*:role/BobBedrockAccess*` + `kms:Decrypt` only on the BobData KMS key |
| Both, only if `BOB_BEDROCK_AUTH=default` in aws (team tests) | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` on the inference profiles and the foundation models they route to (all routed regions). With `assume_role` (the aws default), Bob's roles do not get these. |

- The role names are fixed (CDK `roleName`): `BobApiRole` and `BobWorkerTaskRole`. The trust policy in each user's account names them, so the names must not change across deploys.

### BYO Bedrock template (`infra/templates/bedrock-role.yaml`, A5)
- CloudFormation template. The user deploys it in their own account. It makes the role `BobBedrockAccess`. Parameters: `BobAccountId`, `ExternalId`. Output: the role ARN.
- Trust policy: principal `arn:aws:iam::<BobAccountId>:root`. Conditions: `sts:ExternalId = <ExternalId>`, and `aws:PrincipalArn` in [`arn:aws:iam::<BobAccountId>:role/BobApiRole`, `arn:aws:iam::<BobAccountId>:role/BobWorkerTaskRole`].
- Permissions (D33, all model providers, not only `anthropic.*`): `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` on `arn:aws:bedrock:*::foundation-model/*` and `arn:aws:bedrock:*:*:inference-profile/*`; plus `bedrock:ListFoundationModels`, `bedrock:ListInferenceProfiles`. Nothing else.
- Some Bedrock marketplace / third-party models need `aws-marketplace:ViewSubscriptions` and `aws-marketplace:Subscribe` on first use. Research at first use (owner A5).
- The API serves the file at `GET /me/aws/template` (section 6).

### CloudFront behaviors
| Behavior | Origin | Settings |
|---|---|---|
| default | S3 frontend bucket | CloudFront Function rewrites non-file paths to `/index.html`. Use this function on the default behavior only. Never use distribution-wide custom error pages (they turn API 404s into index.html). |
| `/api/*` | Lambda Function URL | CachingDisabled, origin request policy AllViewerExceptHostHeader, all methods, origin read timeout 60 s |

### Image (`backend/Dockerfile`)
- One image for the API Lambda and the worker. Build context = repo root. Root `.dockerignore`.
- `python:3.12-slim`, linux/amd64 (build with `--platform linux/amd64`, also on Windows).
- `pip install ./backend`.
- Copy the Lambda Web Adapter extension (`public.ecr.aws/awsguru/aws-lambda-adapter`) to `/opt/extensions/`.
- Bake the model2vec model into `/opt/models/potion-base-8M` (`BOB_EMBED_MODEL_PATH`).
- Copy `demo/` to `/app/demo`.
- Copy `infra/templates/` to `/app/infra/templates/` (G1 serves `bedrock-role.yaml` from there).
- Default CMD = uvicorn `bob.api.app:app` on port 8080. Fargate overrides CMD to `python -m bob.worker <job_id> <mode>`.

### Deploy and teardown
```
# once, before T+0:00
cdk bootstrap aws://<account>/<region>              # Bob's hosting account + region (default us-east-1); Bedrock region is per user
aws secretsmanager put-secret-value --secret-id bob/keys --secret-string file://secrets.json   # secrets.json is never committed

# each deploy (from a clean checkout in < 15 min)
infra/deploy.sh      # npm run build -> cdk deploy --all --require-approval never --outputs-file infra/outputs.json -> print the CloudFront URL

# after the event
cdk destroy --all    # buckets use DESTROY + autoDeleteObjects
```
A5 posts the table, bucket, secret and Cognito names (pool id, client id, domain) to all agents after `BobData` deploys. A1 adds them to `.env.example`.

### Limits (Lambda and CloudFront)
1. The API Lambda has no background work. A task started after the response freezes. Long work goes to the worker only.
2. Every route returns in < 25 s (CloudFront origin timeout).
3. Request bodies are <= 6 MB (Lambda limit). P1: `POST /uploads/presign` gives a presigned S3 PUT.
4. Only `/tmp` is writable in Lambda. No writes outside `BOB_RUNS_DIR` (`/tmp/runs`).
5. A Lambda response stream ends at 900 s. SSE closes at `BOB_SSE_MAX_S` (840 s) and the browser reconnects.
6. CloudFront cuts an idle origin connection after the 60 s read timeout. SSE sends `: ping` every 15 s.
7. A DynamoDB item is <= 400 KB. The full Job document goes to S3.
8. The Lambda readiness check calls `/api/ping`. It makes no external calls.
9. Firecrawl and Composio fetch run inside the worker. The worker has no time limit.

### P1 (A5)
Resync in the worker; CloudFormation quick-create link for `bedrock-role.yaml` (needs a public S3 template URL; research); self sign-up; origin-secret header (CloudFront adds `X-Bob-Origin`, API middleware rejects calls without it, so nobody can call the Function URL directly); AWS Budgets alarm; presigned uploads; a CloudWatch Logs Insights query for errors.
Cut line: if the cloud job path fails at T+3:30, demo on localhost and show the deployed UI + `/api/health`.

## 14. Accounts and bring-your-own AWS (D26, D27, D33)

There is no sign-in for the demo (2026-10-31): every caller is the built-in user `local`. Each user connects their own AWS account for Bedrock (D26). Each user picks the model for each LLM role (D33). Bedrock calls (writer, planner, judge and fallback models) run in the user's account and bill there. Bob's own keys still pay for Jev, ScaleDown, Firecrawl and Composio. Bob stores no long-lived user keys.

### Who is calling (D27, sign-in removed 2026-10-31)
1. No sign-in screen, no tokens. `client.ts` sends no `Authorization` header.
2. G1 `api/auth.py` `current_user()` returns `Orchestrator.get_or_create_user("local", None)`. Owner checks (404 for another user's job, upload or connection) stay in code.
3. Cognito resources may remain in the infra stack, unused. `BOB_AUTH`, `BOB_COGNITO_*` and `BOB_SIGNUP` are gone; `GET /config/public` is gone.

### Connect AWS (D26), Account screen (G3, `/account`)
1. On first sign-in, Bob makes a `UserProfile` with a random `external_id` (uuid4). It never changes.
2. The Account screen ("Connect AWS") reads `GET /me/aws/setup`. It shows Bob's AWS account id (`BOB_ACCOUNT_ID`), the external id, a download of `bedrock-role.yaml` (`GET /me/aws/template`) and one CLI command:
   `aws cloudformation deploy --template-file bedrock-role.yaml --stack-name BobBedrockAccess --capabilities CAPABILITY_NAMED_IAM --parameter-overrides BobAccountId=<id> ExternalId=<ext>`
   P1: a CloudFormation quick-create link.
3. The template makes the role `BobBedrockAccess` in the user's account (trust and permissions: section 13).
4. "AWS access" panel: the user pastes the role ARN and picks the Bedrock region (default `BOB_BEDROCK_DEFAULT_REGION`). `PUT /me/aws` saves it and clears `bedrock_verified_at`. In aws mode the API sets `mode = "assume_role"`.
5. `POST /me/aws/verify` (`verify_bedrock`): `sts:AssumeRole` only, in < 25 s. On success it sets `bedrock_verified_at`. On failure it shows the exact STS error.
6. "Models" panel (D33): per role (`writer`, `planner`, `judge`, `fallback`): provider, model id (free text P0; picker from `GET /me/models/available` P1), base URL + key for `openai_compatible` (P1), JSON mode and cache (advanced fields), price overrides. Defaults: `BOB_DEFAULT_*_MODEL`. `PUT /me/models` saves it and clears `models_verified_at`.
7. `POST /me/models/verify` (`verify_models`): one tiny real call per configured role (all providers), with a JSON output check, in < 25 s. On success it sets `models_verified_at`. On failure it shows the exact error per role, for example "model access not enabled in us-east-1".
8. A job cannot start until both checks pass (`bedrock_verified_at` and `models_verified_at` are set). `POST /jobs` returns HTTP 412 `{"error": "connect AWS first"}` or `{"error": "verify models first"}`.
9. `create_job` copies snapshots into `Job.bedrock` and `Job.models` (`spec.options.models` if set, else `UserProfile.models`). Later profile edits do not change a running job. The Setup "Advanced" panel (P1) can override the models per job.

### Credentials and refresh (A1, `llm/credentials.py`)
- `mode="default"`: the default boto3 chain (local dev, `AWS_PROFILE`).
- `mode="assume_role"`: STS AssumeRole with the external id and session name `bob-<job_id>`. Refresh the credentials `BOB_CRED_REFRESH_S` (300 s) before expiry. Role chaining limits a session to 1 h, and a job can wait 60 min for approval, so the refresh is required.
- `llm/bedrock.py` takes the job's `BedrockAccess`. It calls the Converse API through boto3 with botocore `RefreshableCredentials`, so the credentials refresh `BOB_CRED_REFRESH_S` before expiry. Research the exact setup at first use (A1, T+1:00).
- The ledger prices LLM calls from `ModelConfig.price_*_per_m`, else the registry, keyed by model id. An unknown price shows as "unknown" (`CostSummary.price_unknown`); the user can set it in the Models panel. The UI shows the Bedrock cost as "billed to your AWS account". The per-job budget guard still covers all buckets.

### Security rules
- No long-lived user AWS keys. Only the role ARN, the region, the model settings and the external id are stored.
- P1 `openai_compatible` API keys: encrypted with the KMS key (`alias/bob-user-keys`, `BOB_KMS_KEY_ID`) and stored in the user's PROFILE item. Only `BobApiRole` and `BobWorkerTaskRole` can decrypt. The API never returns a key to the client; it shows `api_key_set: true`.
- The external id is made by Bob, one per user, and never changes. The user's trust policy requires it.
- The user's trust policy accepts only Bob's two fixed roles, `BobApiRole` and `BobWorkerTaskRole`. Do not rename them.
- The `BobBedrockAccess` role can only invoke and list Bedrock models and inference profiles (all providers). Nothing else.
- Data ownership: `Job.owner_id` = `UserProfile.id`. `GET /jobs` lists only the caller's jobs. Every `/jobs/{id}/*` route returns HTTP 404 when `owner_id` differs. `/health` needs a signed-in user.
- Composio: `user_id` = `COMPOSIO_USER_PREFIX + UserProfile.id` (`bob-<id>`), so each user's Notion and Jira connections are private. `COMPOSIO_DEMO_ACCOUNTS` applies to the demo user only.
- Capacity per user: `BOB_MAX_ACTIVE_JOBS_PER_USER` (1). More gives HTTP 429.
- Sign-up: `BOB_SIGNUP=invite` (default). The team creates users with `aws cognito-idp admin-create-user`. Self sign-up is P1.

### Model-agnostic LLM layer (D33)
- Every LLM role is configurable: `writer`, `planner`, `judge`, `fallback` (the model of the Jev and Extract fallback chains; default = the writer model). D33 supersedes D22; the defaults stay.
- Defaults only: Claude Haiku 5.5 (writer, fallback) and Claude Sonnet 5.5 (planner, judge). Any model works.
- Providers:
  - `bedrock` (P0): any Bedrock model or inference profile in the user's own AWS account (Anthropic, Amazon Nova, Meta Llama, Mistral, DeepSeek, Qwen, OpenAI gpt-oss, ...). Converse API through boto3, with the user's assumed-role credentials.
  - `openai_compatible` (P1): any OpenAI-compatible chat completions endpoint (OpenAI, OpenRouter, Together, Groq, a self-hosted vLLM, ...). Raw `httpx`. The user gives `base_url` and an API key. The key is KMS-encrypted (security rules above).
- Code rules: section 3 (`LLMClient`, `get_llm(job, role)`, registry). Pipeline code never names a vendor model. Prompts are model-neutral.
- Frontier-only estimate = the same token counts priced at the judge role model price (whatever model it is).
- The UI warns when the judge model is the same as the writer model.
- P0: configurable models on Bedrock (any provider family) through Converse + registry + verify per role. P1: `openai_compatible` with encrypted keys, the model picker (`/me/models/available`), the per-job model override in the Advanced panel.

### Risks (D33)
| Risk | Mitigation |
|---|---|
| A model does not support forced tool use or JSON output | registry `json_mode`; `prompt` mode + one retry; verify call checks JSON output per role |
| No prompt caching on the chosen model | cost estimate uses registry `cache`; the plan estimate shows the higher cost |
| A weak judge model lowers quality | judge agreement and the spot-check are in the report; the UI warns when judge == writer model |
| Marketplace models need a subscription | verify shows the exact AccessDenied text; research the marketplace permissions |
| Unknown prices | `price_unknown` badge; user can set prices in the Models panel |

### Demo
- The demo user is pre-created and pre-connected to the team's own AWS account through the same template (same-account assume role works).
- Test the cross-account path with a second AWS account if one is available (owner A5, T+2:00; default: same-account role).
- The demo starts signed in as the demo user, with AWS already connected and the default models verified.
