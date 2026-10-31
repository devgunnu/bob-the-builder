# Bob the Builder: Contracts (v4, data factory)

> Source of truth for all 8 coding agents. Lock in the first 20 minutes (T+0:00 to T+0:20). Change only by agreement between Aaditya and Gunbir, and commit the change here first.
> v4 replaces v1 to v3. Templates, question programs, grammar banks and Architect-written generator code are retired (DECISIONS D18).

## 0. Ground rules for every agent

1. **One owner per file.** Only edit files that your brief owns (section 1). If you need a change in another file, write a note in `.agents/CHANGES_REQUESTED.md` and tell your builder.
2. **No mocks, no fake data.** Every call to Bedrock, Jev, ScaleDown, Firecrawl and Composio is real, from the first line of code. Tests use real calls on small real inputs (the `demo/smoke/` corpus). If a key does not work, fix the key or switch to the documented real fallback (section 5); never stub the call.
3. **Everything is async.** Pipeline functions are `async def`. External calls go through a client with a semaphore, retries (3, exponential backoff), a disk cache, and a cost ledger entry.
4. **Dependencies:** A1 owns `backend/pyproject.toml`, G3 owns `frontend/package.json`. To add a dependency, add a `CHANGES_REQUESTED.md` entry; the owner adds it within 10 minutes. In the first 20 minutes, A1 and G3 add every dependency named in this file up front.
5. **Python 3.12, pydantic v2, ruff format.** TypeScript strict, React 18, Vite.
6. **Commit small and often** to your builder's branch: `aaditya/*` or `gunbir/*`. Merge to `main` at each checkpoint.

## 1. Repository layout and ownership

```
backend/
  pyproject.toml                    A1
  bob/
    config.py                       A1   settings from env (section 9)
    core/
      models.py                     A1   ALL shared pydantic models (section 2). Written first.
      store.py                      A1   job store: in-memory + runs/<job_id>/ on disk
      events.py                     A1   event bus, SSE event log, replay
      ledger.py                     A1   cost ledger + frontier-only estimate
      cache.py                      A1   disk cache for all external calls
    llm/
      bedrock.py                    A1   Writer / Judge / Planner client (Anthropic on Bedrock)
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
      prompts/*.md                  A3 (planner.md, writer*.md), A4 (judge.md)  -> path: backend/bob/pipeline/prompts/
      verify.py                     A4   3-tier verification cascade
      report.py                     A4   data quality report
      probe.py                      A4   STRETCH: base-model probing
    export/
      presets.py formats.py manifest.py   A4
    orchestrator.py                 A1   job state machine; the only API the web layer calls
    connectors/
      __init__.py                   G1   fetch_documents() dispatch
      upload.py parsers.py          G1   file upload + PDF/DOCX/MD/HTML/TXT/CSV -> Document
      firecrawl.py                  G2
      composio.py                   G2   Notion, Confluence, Jira, Google Drive
      sync.py                       G2   content hashes, diff for re-sync
    api/
      app.py routes.py sse.py       G1   FastAPI app, routes (section 6), SSE
  tests/                            each owner tests their own modules
frontend/                           G3 (shell, setup, plan screens, package.json), G4 (build, rows, report screens, src/components/viz/*)
  src/api/client.ts types.ts        G3 owns; types.ts mirrors section 2 exactly
demo/                               G2: smoke/ (small real corpus for tests), corpus/ (cached real crawl of the demo docs)
runs/                               gitignored job outputs
```

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

class Cell(BaseModel):
    id: str                                 # sha1(sorted coords)[:10]
    coords: dict[str, str]                  # {"topic": "Refunds", "persona": "Accountant", "case_type": "unanswerable", "difficulty": "multi_step"}
    enabled: bool = True
    target: int
    weight: float = 1.0                     # gap controller multiplier
    generated: int = 0
    kept: int = 0
    rejected: int = 0
    judged: int = 0

class Plan(BaseModel):
    goal: str
    task_format: Literal["single_turn", "multi_turn"] = "single_turn"
    system_prompt: str                      # system prompt that ships in every exported row
    axes: list[Axis]
    cells: list[Cell]
    notes: list[str] = []                   # e.g. "Your seed examples cover 4 of 14 topics."
    target_rows: int
    est_cost_usd: float

# ---------- job ----------
class JobSpec(BaseModel):
    goal: str
    sources: list[SourceSpec]
    seed_upload_id: str | None = None       # optional JSONL/CSV of real examples
    target_rows: int = 1000
    budget_usd: float = 10.0
    preset: str = "openai-chat"
    formats: list[str] = ["jsonl"]
    probe_model: str | None = None          # STRETCH

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
    by_model: dict[str, ModelCost] = {}     # keys: "writer", "judge", "planner", "jev", "scaledown", "firecrawl", "composio"
    total_usd: float = 0.0
    frontier_only_estimate_usd: float = 0.0 # same candidates written AND judged by the judge model
    fallbacks_used: list[str] = []          # e.g. ["jev->scaledown_classify"]

class Job(BaseModel):
    id: str
    spec: JobSpec
    status: JobStatus = JobStatus.created
    stage_detail: str = ""
    plan: Plan | None = None
    round: int = 0
    counts: dict[str, int] = {}             # docs, chunks, chunks_kept, evidence, topics, candidates, kept, rejected, judged, duplicates, dpo_pairs
    cost: CostSummary = CostSummary()
    files: dict[str, str] = {}              # "<preset>/<split>.<format>" -> download path, e.g. "openai-chat/train.jsonl"
    report: "Report | None" = None
    error: str | None = None
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
    messages: list[Message]                 # user/assistant turns only; system added at export
    chunk_ids: list[str]                    # chunks the Writer was given and claims to use
    premise_evidence_id: str | None = None  # false_premise: the fact the user's premise contradicts
    absent_topic: str | None = None         # unanswerable: what the user asks about that is not documented
    writer_model: str
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
    coords: dict[str, str]
    case_type: str
    round: int
    messages: list[Message]
    spans: list[SpanRef]                    # supporting source text
    checks: list[CheckResult]
    confidence: float                       # min pass-direction prob of tier-2 Noul checks (section 4)
    verdict: Literal["kept", "rejected"]
    reject_reason: str | None = None        # first failing check's detail
    routed_to_judge: bool = False
    audited: bool = False                   # random tier-3 audit of a kept row
    spot_check: bool | None = None          # human thumbs up/down
    cost_usd: float
    created_at: datetime

class DPOPair(BaseModel):
    id: str
    prompt: list[Message]
    chosen: str                             # kept assistant reply
    rejected: str                           # rejected reply for the same user turn
    rejection_reason: str

class Report(BaseModel):
    coverage: list[dict]                    # [{cell_id, coords, target, kept, rejected}]
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
def embed(texts: list[str]) -> "np.ndarray"                         # model2vec potion-base-8M, CPU
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
                       target_rows: int, budget_usd: float) -> Plan
def allocate_targets(plan: Plan) -> Plan                            # split target_rows across enabled cells
async def generate(cell: Cell, plan: Plan, ctx: "GenContext", n: int) -> list[Candidate]
def plan_gap_round(job: Job, cells: list[Cell]) -> list[tuple[Cell, int]]   # which cells, how many more

# A4: verify + report + export
async def verify(cands: list[Candidate], ctx: "GenContext") -> list[Row]
def build_dpo_pairs(rows: list[Row]) -> list[DPOPair]
def build_report(job: Job, rows: list[Row]) -> Report
def export(job: Job, rows: list[Row], pairs: list[DPOPair], preset: str,
           formats: list[str], out_dir: "Path") -> dict[str, str]

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
```

## 4. Verification cascade (A4)

Run per candidate. All thresholds come from `config.py`. **Hard checks** (all of tier 1, and `extract.names`) stop the cascade on the first failure: the row is rejected. **Soft checks** (all Jev questions) run together in one call; their failures do not stop the cascade and are resolved by routing below.

### Tier 1: code (free)
| Check | Rule |
|---|---|
| `format` | Valid roles; user then assistant; non-empty; user 5 to 300 words; assistant 10 to 400 words |
| `banned_phrases` | Reject "according to the (text\|passage\|document)", "as an AI", "in the provided context" |
| `dedup` | Exact hash of normalized user turn, then embedding cosine > `DEDUP_COS` (0.92) against kept rows in the same cell |
| `numbers` | Every number in the assistant reply appears in the cited chunks or in the evidence index (code, not Jev) |

### Tier 2: Jev + ScaleDown (about $0.0001 per row)
**`extract.names`**: ScaleDown Extract on the assistant reply with schema `{features[], settings[], urls[], limits[]}`. Each extracted name must match `EvidenceIndex.find()`. A name with no match is an invented feature: reject with detail `"Mentions 'bulk PDF export', which is not in the docs"`.

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

`confidence` = minimum **pass-direction** probability across tier-2 Noul checks. Pass-direction is `p` for checks that pass on yes, and `1 - p` for checks that pass on no (`jev.not_in_docs`). So a row that passes every check always has `confidence >= KEEP_P`.

### Routing
1. Any hard fail: **rejected** (`reject_reason` = that check's detail).
2. Else `confidence < REJECT_P` (0.3): **rejected** (reason = the lowest Jev check).
3. Else all Jev checks pass (so `confidence >= KEEP_P`): **kept**.
4. Else (some Jev check failed, including `jev.cell`, `jev.quality` or `jev.realistic`, which are not part of `confidence`): **tier 3**.
- Also send a random `AUDIT_RATE` (2%) of kept rows to tier 3 (`audited = true`).

### Tier 3: judge (Sonnet 5.5 on Bedrock)
Prompt in `prompts/judge.md`. Input: passages, case type, the row, and the tier-2 results. Output JSON `{"verdict": "keep" | "reject", "reason": "..."}`. The judge verdict is final. Tier-2 vs tier-3 agreement goes into `Report.judge_agreement`.

### Jev failure modes and guards
- About 11.5% wrong at >= 90% confidence: every kept answerable row needs both `jev.supported` and `extract.names`; tier-3 audit measures the real error rate.
- Follows option names: use descriptive names only.
- Weak at arithmetic and dates: tier-1 `numbers` covers this in code.

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

async def decide(state: str, questions: list[Question], purpose: str) -> dict[str, Decision]
```
- Endpoint: OpenRouter `POST /api/alpha/decisions`, model `typesafe/jev-1.13-20260917` (check 1.14). Raw `httpx`, no OpenAI SDK, no `temperature` / `max_tokens`. **Check the request shape at T+0:00.**
- Fallback chain on 3 failures in a row: Noul and Choice -> ScaleDown Classify -> Bedrock Haiku JSON answer. Score has no Classify equivalent, so Score goes straight to Bedrock Haiku JSON answer. Log to `CostSummary.fallbacks_used` and emit a `log` event; the UI shows a badge.
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

async def extract(text: str, schema: dict, purpose: str) -> list[ExtractField]   # chat completions + response_format
async def summarize(text: str, purpose: str, instructions: str | None = None) -> str
async def classify(text: str, labels: list[str], purpose: str) -> dict[str, float]
async def compress(text: str, rate: str | float = "auto") -> str
```
- Base URL `api.scaledown.xyz` or OpenRouter `scaledown/extract`, `scaledown/summarize`, `scaledown/classify-1`. **Check at T+0:00.**
- Extract schema is guidance only. Code validates types and checks that `span_text` is a verbatim substring of the input; drop fields that fail.
- Extract fallback: Bedrock Haiku extraction with the same schema, then the same verbatim-span check.
- Evidence schema for chunks: `{features[], settings[{name, value}], limits[{name, value}], procedures[], definitions[{term, meaning}], urls[]}`.

## 6. HTTP API (G1 builds on the orchestrator, section 7)

Base `/api`. JSON unless stated.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/uploads` | multipart files | `{upload_ids: [...], files: [{id, name, bytes}]}` |
| GET | `/connectors` | | `[{toolkit, connected: bool, account_id?}]` |
| POST | `/connectors/{toolkit}/connect` | `{redirect_url}` | `{auth_url, connection_id}` (Composio OAuth) |
| GET | `/connectors/{toolkit}/status` | `?connection_id=` | `{connected, account_id}` |
| GET | `/connectors/{toolkit}/browse` | `?account_id=&q=` | `[{id, title, kind}]` (pages, spaces, projects) |
| POST | `/sources/preview` | `SourceSpec` | `{documents: [{uri, title, chars}]}` (fetch only, no job) |
| POST | `/jobs` | `JobSpec` | `Job` (status moves to `awaiting_approval` when the plan is ready) |
| GET | `/jobs` | | `[Job]` (summary fields) |
| GET | `/jobs/{id}` | | `Job` |
| PUT | `/jobs/{id}/plan` | `Plan` (edited) | `Job` (starts the build) |
| POST | `/jobs/{id}/cancel` | | `Job` |
| GET | `/jobs/{id}/events` | header `Last-Event-ID` | SSE stream (section 8) |
| GET | `/jobs/{id}/rows` | `?verdict=&cell_id=&offset=&limit=` | `{total, rows: [Row]}` |
| GET | `/jobs/{id}/rows/{row_id}` | | `Row` |
| POST | `/jobs/{id}/rows/{row_id}/spot-check` | `{ok: bool}` | `Report` |
| POST | `/jobs/{id}/export` | `{preset, formats}` | `{files: {...}}` |
| GET | `/jobs/{id}/files/{name}` | | file download |
| POST | `/jobs/{id}/resync` | | `Job` (P1, section 10) |
| GET | `/presets` | | `[{name, formats, description}]` |
| GET | `/health` | | `{keys: {bedrock, jev, scaledown, firecrawl, composio}}` (each key: a real test call result, `ok` or the error) |

## 7. Orchestrator (A1) and connector (G1/G2) interfaces

```python
# bob/orchestrator.py: the only backend API the web layer calls
class Orchestrator:
    async def create_job(self, spec: JobSpec) -> Job            # background: ingest -> read -> plan -> awaiting_approval
    async def approve_plan(self, job_id: str, plan: Plan) -> Job  # background: build -> fill gaps -> report -> export -> done
    async def cancel(self, job_id: str) -> Job
    def get_job(self, job_id: str) -> Job
    def list_jobs(self) -> list[Job]
    def list_rows(self, job_id, verdict=None, cell_id=None, offset=0, limit=50) -> tuple[int, list[Row]]
    def get_row(self, job_id, row_id) -> Row
    async def spot_check(self, job_id, row_id, ok: bool) -> Report
    async def export(self, job_id, preset, formats) -> dict[str, str]
    async def resync(self, job_id) -> Job                       # P1
    def subscribe(self, job_id, last_event_id: int | None) -> AsyncIterator["Event"]

# bob/connectors/__init__.py: the only connector API the orchestrator calls
async def fetch_documents(spec: SourceSpec, job_id: str,
                          progress: Callable[[int, int, str], Awaitable[None]]) -> list[Document]
```

Build loop inside `approve_plan` (A1 writes it, calling A3/A4):
```
round 1: for each enabled cell (concurrency WRITER_CONCURRENCY): generate(target * OVERGEN) -> verify -> store rows -> emit
round 2..MAX_ROUNDS: plan_gap_round() -> generate -> verify     (stop when targets met, budget hit, or MAX_ROUNDS)
then: build_dpo_pairs -> build_report -> export(spec.preset, spec.formats) -> done
budget guard: stop new writer calls when cost.total_usd >= 0.95 * budget_usd
```

### Ledger and seeds (A1)
```python
# core/ledger.py: every external call records here (G2 uses it for Firecrawl and Composio)
def record(job_id: str, bucket: str, *, calls: int = 1, in_tokens: int = 0, out_tokens: int = 0,
           usd: float | None = None, model: str | None = None) -> None   # usd=None -> computed from config prices
def frontier_only_estimate(job_id: str) -> float

# orchestrator: seed parsing (A1). G1 stores the upload; A1 parses it.
def load_seeds(upload_path: Path) -> list[list[Message]]   # JSONL {"messages": [...]} or {"user","assistant"}; CSV columns user,assistant
```

## 8. SSE events (A1 emits, G4 renders)

Wire format: `id: <seq>\nevent: <type>\ndata: <json>\n\n`. The store keeps every event per job, so a client that reconnects with `Last-Event-ID` gets a replay.

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
AWS_REGION, AWS_PROFILE or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY    # Bedrock
BOB_WRITER_MODEL=global.anthropic.claude-haiku-5-5     # check the exact Bedrock ID / inference profile at T+0:00
BOB_JUDGE_MODEL=global.anthropic.claude-sonnet-5-5
BOB_PLANNER_MODEL=global.anthropic.claude-sonnet-5-5
OPENROUTER_API_KEY                                     # Jev (and ScaleDown via OpenRouter)
JEV_MODEL=typesafe/jev-1.13-20260917
SCALEDOWN_API_KEY, SCALEDOWN_BASE_URL=https://api.scaledown.xyz
FIRECRAWL_API_KEY
COMPOSIO_API_KEY
COMPOSIO_USER_ID=bob-demo                               # Composio entity / user id for connected accounts
COMPOSIO_DEMO_ACCOUNTS=notion:<connected_account_id>   # pre-connected demo accounts, comma-separated
KEEP_P=0.9  REJECT_P=0.3  AUDIT_RATE=0.02  DEDUP_COS=0.92
OVERGEN=1.6  MAX_ROUNDS=3  WRITER_BATCH=5
WRITER_CONCURRENCY=16  JEV_CONCURRENCY=32  SCALEDOWN_CONCURRENCY=16  JUDGE_CONCURRENCY=4
PRICES: writer $0.10/$0.50, judge+planner $2/$10 per M tokens, jev $0.042/M in, scaledown $0.04/M in   # check at T+0:00
```

Bedrock client: `anthropic.AsyncAnthropicBedrock(aws_region=...)`. Use prompt caching on the Writer system prompt + topic brief (same per cell). Request structured JSON output; on parse failure, retry once, then drop.

## 10. Re-sync (P1, G2 + A1)
1. `sync.py` re-fetches each `SourceSpec` and compares `Document.content_hash` per `uri`: `added`, `changed`, `removed`.
2. The orchestrator re-runs reading only on added and changed docs, and marks topics that contain changed chunks as affected.
3. Kept rows whose `spans` point to changed or removed docs are verified again (tier 1 + tier 2). Rows that fail become `rejected` with reason `stale: source changed`.
4. Affected cells get a gap round. Emit `round` with `reason: "resync"`.

## 11. Export (A4)

Canonical rows -> preset -> format. One data file per folder (ModelForge rule, D9): `runs/<job_id>/export/<preset>/<split>/<split>.<ext>`, for example `export/openai-chat/train/train.jsonl` and `export/openai-chat/eval/eval.jsonl`. Always write `bob_manifest.json` and `provenance.parquet` (row id, cell, coords, spans, checks, confidence) next to the data.

| Preset | Row shape |
|---|---|
| `openai-chat` (default) | `{"messages": [system, user, assistant, ...]}` |
| `sharegpt` | `{"conversations": [{"from": "system"/"human"/"gpt", "value": ...}]}` |
| `alpaca` | `{"instruction": user, "input": "", "output": assistant}` (single turn only) |
| `modelforge-chat` | `{"messages": [...]}` canonical columns only |
| `modelforge-sft` | `{"prompt": user, "completion": assistant}` (single turn only) |
| `dpo` | `{"prompt": [...messages], "chosen": str, "rejected": str}` from `DPOPair` |
| `full` | whole `Row` including provenance |

Formats: `jsonl` (required), `json`, `csv`, `parquet` (required). Splits: `train` 95%, `eval` 5%, stratified by cell.

## 12. Real-only development contract
- **No mock clients, no fake responses, no fake corpus.** A failing external call fails loudly with the provider's error in a `log` event and in `/health`.
- `core/cache.py` stores **real** responses on disk, keyed by sha256 of (endpoint, model, request body). It saves money and time on re-runs. It never invents a response. `BOB_CACHE=0` turns it off for the final demo run if needed.
- `demo/smoke/`: 3 to 5 real pages (Firecrawl scrape of the demo docs, saved as markdown) plus 10 real seed questions, written to disk by G2 at T+0:20. All backend tests run on this corpus with real calls and small sizes (for example `target_rows=20`).
- `demo/corpus/`: the full real crawl of the demo docs, cached by G2 by T+1:30.
- Frontend agents build against the real API. Until a route exists, they build the component against the `types.ts` shapes, then connect it the moment the route lands. They never ship hard-coded data.
- G1 ships `POST /uploads`, `POST /jobs` and the MD parser by T+0:45. A1 delivers a **thin real path** by T+0:50: `POST /jobs` with `SourceSpec(kind="upload")` pointing at the uploaded `demo/smoke/` files -> real chunk -> real Writer -> real Jev check -> rows in the store -> SSE events. All other work hangs on this path.
