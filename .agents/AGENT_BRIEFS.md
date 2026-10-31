# Bob the Builder: Agent Briefs (v4)

> One brief per coding agent. Copy the whole brief (from its `##` heading to the next `##`) into a fresh agent session, together with this header section. `PLAN.md` and `CONTRACTS.md` are the source of truth. If a brief and those files disagree, the files win. Tell your builder about the conflict.

## How to use these briefs

1. Before T+0:00, Aaditya opens 5 agent sessions (A1-A5) and Gunbir opens 4 (G1-G4). Paste one brief into each session. Paste the "Shared ground rules" and the "Dependency map" with every brief. The project has 9 agents.
2. Each agent reads `CONTRACTS.md` and `PLAN.md` sections that its brief lists, before it writes code.
3. Each agent works only on its own files, on its builder's branch, and commits small.
4. At each checkpoint (T+1:30, T+2:50) the builders merge to `main`. All agents stop new work until the checkpoint passes. Checkpoint 2 passes only on the CloudFront URL (A5 deploys the merge).
5. Priorities (PLAN §8): **checkpoint 2 (T+2:50) = all P0**, including at least one gap round (round 2). **P1** (gap round 3, DPO, extra presets and formats, extra Composio toolkits, re-sync, spot-check) finishes in T+3:00-3:30. The definition of done at T+3:30 (PLAN §7) = P0 + P1. Each brief marks its P1 items.

## Shared ground rules (all 9 agents)

- **One owner per file** (CONTRACTS §1). Do not edit a file that you do not own. To ask for a change in another file, add one row to the table in `.agents/CHANGES_REQUESTED.md` (columns: Time, From, To (owner), File, Request, Status), then tell your builder. The owner sets Status to `done <commit hash>`.
- **Real calls only** (CONTRACTS §0 rule 2, §12). No mocks, no stubs, no fake responses, no hard-coded rows, no placeholder corpus. Tests use real calls on `demo/smoke/` with small sizes (for example `target_rows=20`). If a key fails, fix the key or use the documented real fallback. Never fake the call.
- **Disk cache is for real responses only** (`core/cache.py`). It never invents a response. `BOB_CACHE=0` turns it off.
- **Async everywhere.** External calls go through a client with a semaphore, 3 retries with exponential backoff, the disk cache, and a cost ledger entry.
- **Branches:** Aaditya's agents commit to `aaditya/<agent>` (for example `aaditya/a2-read`). Gunbir's agents commit to `gunbir/<agent>`. Merge to `main` at the checkpoints only.
- **Never commit `.env`** or any key. `runs/` is gitignored.
- **Cloud-safe code** (CONTRACTS §13, DECISIONS D25). The same code runs local (`BOB_ENV=local`, the default) and on AWS (`BOB_ENV=aws`).
  - Write files only under `settings.runs_dir`. Never hard-code `runs/`. In Lambda, `/tmp/runs` is the only writable path.
  - Keep durable data only through `Store`, `Blobs` and `EventLog` (get them from `core/backends.py`). Do not keep job state in module globals or local files only.
  - Do no background work in the API process. A task that starts after the response freezes in Lambda. Long work runs in the job worker (`Runner.start`).
  - Tests for the aws backends use real AWS (DynamoDB, S3, ECS). No moto, no LocalStack (D23).
- **Dependencies:** a new Python package goes into `backend/pyproject.toml` (owner A1); a new npm package goes into `frontend/package.json` (owner G3). Request it through `CHANGES_REQUESTED.md` and add it in the same commit as the code that needs it, after the owner agrees.
- **Models change only through A1.** If `core/models.py` changes, A1 posts the diff; G3 updates `types.ts` in the same hour.
- Python 3.12, pydantic v2, `ruff format`. TypeScript strict, React 18, Vite.

## Dependency map (who blocks whom)

```
 T+0:15  A1 core/models.py + config.py + orchestrator.py signatures ──► ALL 8 other agents
 T+0:15  A1 protocol stubs (Blobs, Store, EventLog, Runner + local impls, backends.py) + boto3 ──► A5 aws impls
 T+0:20  A5 BobData stack + resource names (table, buckets, secret) ──► A1 .env.example, all agents
 T+0:20  A2 clients/jev.py + clients/scaledown.py (real shapes confirmed) ──► A2 triage/evidence, A4 tier 2, A1 thin path
 T+0:20  G2 demo/smoke/*.md + demo/smoke/seeds.jsonl (real Firecrawl scrape) ──► A2, A3, A4 tests; A1 thin path
 T+0:20  A1 llm/bedrock.py (with A3) ──► A3 Writer/Planner, A2 topic names, A4 judge
 T+0:20  G3 frontend/src/api/types.ts ──► G4 components
 T+0:45  G1 POST /uploads + MD parser + POST /jobs + SSE route ──► A1 thin path end to end
 T+0:50  A1 THIN REAL PATH (smoke upload -> chunk -> Writer -> Jev -> rows -> SSE) ──► G1 + G4 live testing
 T+1:00  A2 chunk/topics/evidence/Retriever ──► A3 Planner + Writer context, A4 extract.names + numbers
 T+1:10  A3 generate() for 4 case types ──► A4 verify() on real candidates, A1 build loop
 T+1:15  A4 verify() + export openai-chat ──► A1 build loop, G4 row feed, checkpoint 1 download
 T+1:15  G2 firecrawl.py + composio.py (Notion) ──► G1 fetch_documents(), G3 connector buttons
 T+1:15  A5 CLOUD HEALTH: CloudFront URL serves the UI; /api/ping + /api/health work there ──► checkpoint 1
 T+1:30  CHECKPOINT 1 (merge; local pass test + cloud health check)
 T+2:00  A3 plan_gap_round() + A1 round 2 wiring (P0) ──► G4 round banner, checkpoint 2
 T+2:00  A5 CLOUD REAL JOB (create -> Fargate worker -> plan -> approve -> rows on SSE -> S3 download) ──► checkpoint 2
 T+2:30  A4 report + openai-chat/full exports (P0) ──► G4 Report screen
 T+2:30  G2 sync.py ──► A1 resync orchestration (P1)
 T+2:50  CHECKPOINT 2 (merge; all P0; pass test runs on the CloudFront URL)
 T+3:30  FREEZE (P0 + P1 done: round 3, DPO, presets, toolkits, resync, spot-check)
 T+3:30  A5 deploys the frozen main (tag `demo`) once; localhost stays the backup
```

Rule: if you are blocked, build against the contract shape with real inputs you already have (for example the smoke corpus), and connect the moment the dependency lands. Never fill the gap with fake data.

---

## A1 Core (Aaditya)

**Role:** Core platform and orchestrator owner.
**Mission:** Lock the shared models first so 8 agents can start. Then build the store, event bus, cost ledger, disk cache, Bedrock client and the orchestrator state machine with the full build loop. You also define the backend protocols (`Blobs`, `Store`, `EventLog`, `Runner`) and their local implementations, so A5 can write the AWS implementations. You deliver the thin real path by T+0:50; all other integration hangs on it. You are the only agent that wires A2, A3 and A4 stages together.

**Read first:** CONTRACTS §0, §1, §2 (all), §3 (GenContext and all signatures), §7, §8, §9, §10, §12, §13 (backend protocols, config, single event writer). PLAN §3, §5, §6, §10. DECISIONS D25.

**You own:** `backend/pyproject.toml`, `backend/bob/config.py`, `backend/bob/core/models.py`, `core/store.py`, `core/events.py`, `core/ledger.py`, `core/cache.py`, `core/blobs.py`, `core/runner.py`, `core/backends.py`, `backend/bob/llm/bedrock.py`, `backend/bob/orchestrator.py`, your tests in `backend/tests/`.
**Do not touch:** `clients/*`, `pipeline/*`, `export/*`, `connectors/*`, `api/*`, `frontend/*`, `demo/*`, `backend/bob/aws/*`, `backend/bob/worker.py`, `backend/Dockerfile`, `infra/*` (A5).

**You provide:** all models in CONTRACTS §2; `GenContext`; `Orchestrator` (all §7 methods, plus `run_job`); `bedrock.py` functions for Writer, Planner and Judge (publish the exact signatures in the first commit, for example `async def complete_json(role, system, messages, schema, cache_prefix) -> tuple[dict, usage]`); `cache.py` get/put; `ledger.record(job_id, key, in_tokens, out_tokens, usd)`; the event bus `emit(type, data)` and `subscribe()`; the protocols `Blobs`, `Store`, `EventLog`, `Runner` (CONTRACTS §13) with local implementations; `get_blobs()`, `get_store()`, `get_events()`, `get_runner()` in `core/backends.py`. Consumers: everyone; A5 for the protocols.
**You consume:** A2 stage functions, A3 `propose_plan/allocate_targets/generate/plan_gap_round`, A4 `verify/build_dpo_pairs/build_report/export`, G1 `fetch_documents()` and `read_upload()`, A5 resource names (T+0:20) and `bob/aws/*` implementations.

**Tasks**
1. **T+0:00-0:15:** Write `core/models.py` exactly as CONTRACTS §2 (call `Job.model_rebuild()` after `Report`). Add `GenContext` as a dataclass with string type hints for `EvidenceIndex` and `Retriever` (import under `TYPE_CHECKING` to avoid import cycles). `config.py`: pydantic-settings for every var in §9, including the new cloud vars (`BOB_ENV`, `BOB_RUNS_DIR`, `BOB_TABLE`, `BOB_BUCKET`, `BOB_SECRET_ARN`, `BOB_ECS_CLUSTER`, `BOB_TASK_DEF`, `BOB_SUBNETS`, `BOB_SECURITY_GROUP`, `BOB_CONTAINER_NAME`, `BOB_MAX_WORKERS`, `BOB_CONTROL_POLL_S`, `BOB_APPROVAL_WAIT_MINUTES`, `BOB_EVENT_POLL_MS`, `BOB_SSE_HEARTBEAT_S`, `BOB_SSE_MAX_S`, `BOB_PUBLIC_URL`, `BOB_EMBED_MODEL_PATH`). In aws mode, `config.py` calls A5's `bob/aws/secrets.py` to load the secret JSON into the environment before it reads Settings. `pyproject.toml`: anthropic, httpx, pydantic, pydantic-settings, fastapi, uvicorn, sse-starlette, model2vec, numpy, scikit-learn, rapidfuzz, pyarrow, pandas, firecrawl-py, composio, pypdf, python-docx, markdownify, tenacity, boto3. Empty `orchestrator.py` with the §7 signatures. Protocol stubs (CONTRACTS §13): `core/blobs.py` (`Blobs` + `LocalBlobs`), `Store`, `EventLog` and `Runner` protocols with local implementation stubs, and `core/backends.py` (pick by `BOB_ENV`; import `bob.aws.*` lazily). **Commit and push by T+0:15.** Tell all agents. Tell A5 that the protocols are ready.
2. **T+0:15-0:20:** `llm/bedrock.py` draft with A3: one real Haiku call and one real Sonnet call. Record the exact model IDs that work in `.env.example` (never `.env`). At T+0:20, add A5's table, bucket and secret names to `.env.example`.
3. **T+0:20-0:50: thin real path.** `create_job` on a `kind="upload"` spec of the smoke `.md` files (uploaded through G1 `/uploads`) -> `fetch_documents` -> A2 `chunk_documents` -> one real Writer call on one cell -> one real Jev check -> `Row` in the store -> `row` and `counts` SSE events. Crude code is fine; real calls are required. Announce at T+0:50.
4. **T+0:50-1:30:**
   - Write `store.py`, `events.py` and `cache.py` against the protocols (CONTRACTS §13). Write the local implementation here. A5 writes the aws implementation in `bob/aws/*`.
   - `store.py` (`LocalStore`): in-memory dict plus `settings.runs_dir/<job_id>/` on disk (`job.json`, `rows.jsonl`, `events.jsonl`, `docs/`, `chunks.jsonl`). Reload jobs on start. Add `set_control` and `get_control`.
   - `events.py` (`LocalEventLog`): per-job sequence ids; `append` returns the seq; persist every event; `read_after(job_id, seq)`; `subscribe(job_id, last_event_id)` replays events with `id > last_event_id`, then streams live. Keep the throttle above the backend: throttle `cell.update` to 5/s per cell (coalesce, keep the last value). Throttle `cost` and `counts` to 2/s per job.
   - `runner.py` (`LocalRunner`): `start(job_id, mode)` runs `Orchestrator.run_job` in an asyncio task; `stop(job_id)` cancels it.
   - `ledger.py`: price table from config, per-key `ModelCost` (keys: `writer`, `judge`, `planner`, `jev`, `scaledown`, `firecrawl`, `composio`), `total_usd`. `frontier_only_estimate_usd` = for every Writer and verify call, the same token counts priced at the judge model rate (Sonnet writes and judges every candidate). Use real token counts from responses; count thinking tokens as output.
   - `cache.py`: key = sha256(endpoint, model, canonical JSON body); store response JSON through `Blobs` under `cache/<sha256>.json`; skip when `BOB_CACHE=0`.
   - `run_job(job_id, mode)`: the whole job body. Both runners call it. `create_job` = save Job + append `job.status created` + `runner.start(job_id, "create")`; it returns at once (< 1 s).
   - Orchestrator pipeline in `run_job`: ingest (progress -> `stage.progress` fetch) -> read (A2 stages, each with `stage.progress`) -> plan (A3) -> `plan.ready` -> `awaiting_approval`. Then wait for approval: poll `store.get_control` every `BOB_CONTROL_POLL_S` (1 s), up to `BOB_APPROVAL_WAIT_MINUTES` (60).
   - Control flag flow: `approve_plan` = `store.set_control(job_id, "approved", plan)`, then return the Job. `cancel` = `set_control(job_id, "cancel")`; if no worker runs, set status `cancelled` and emit the event. `run_job` checks the flag for `cancel` between stages and before each Writer call.
   - `get_job`, `list_jobs`, `list_rows`, `get_row` become `async` (they read DynamoDB and S3 in aws mode). Tell G1 at once (CONTRACTS §7 signatures change).
   - After approval: `allocate_targets`, then round 1 with `asyncio.Semaphore(WRITER_CONCURRENCY)` per cell: `generate(cell, plan, ctx, ceil(target*OVERGEN))` in batches of `WRITER_BATCH` -> `verify` -> store -> update cell counters -> emit `row`, `cell.update`, `counts`, `cost`.
   - **Budget guard:** before each Writer call, stop if `cost.total_usd >= 0.95 * budget_usd`; emit `log` and move on to report.
   - Seeds: parse `seed_upload_id` (JSONL of `{messages}` or CSV `user,assistant`) into `list[list[Message]]`. Use G1's `await read_upload(upload_id)` helper (it returns `list[tuple[name, bytes]]`).
   - Single event writer: the API appends events only in `create_job` (and in `cancel` when no worker runs). The worker reads `last_seq` at start and is the only writer while it runs.
5. **T+1:30 checkpoint 1.** Run the pass test with Gunbir in the browser.
6. **T+1:40-2:50:** round 2 with `plan_gap_round()` is **P0** (must run at checkpoint 2); round 3 (up to MAX_ROUNDS) is P1. Emit `round` events; stop when targets met, budget hit or MAX_ROUNDS. Then `build_dpo_pairs -> build_report -> export(spec.preset, spec.formats)` -> `blobs.upload_tree(runs_dir/<job_id>/export, "runs/<job_id>/export")` (a no-op copy in local mode) -> `report.ready`, `files.ready`, `done`. `cancel()` sets the control flag; `run_job` stops at the next check and sets `cancelled` (the aws runner calls `stop()` after 10 s if the task still runs). Any stage exception sets `error`, emits `error` with the provider message, and never hangs. `spot_check()` updates the row and returns a rebuilt `Report`. Tune concurrency so 500 rows finish in under 10 minutes (watch Bedrock throttling). `resync()` per CONTRACTS §10 using G2 `sync.py` (P1).
7. **T+3:00-3:30:** fix checkpoint 2 bugs; run a full fresh job; profile slow stages.

**Definition of done:** P0 at T+2:50: a real job on `demo/corpus/` goes `created -> ... -> done` with 500+ kept rows and at least one gap round; P1 by T+3:30: round 3, resync, spot-check. Also: all §8 events in the event log, replay from any `Last-Event-ID` works, ledger total matches the sum of real call costs, budget guard stops a job with `budget_usd=0.2`, cancel stops within 5 s, a forced provider error ends in `error` or a fallback `log`, not a hang.

**Handoffs and sync points:** T+0:15 models to all; T+0:15 protocol stubs, config vars and `boto3` to A5; T+0:20 Bedrock signatures to A2/A3/A4; T+0:20 A5 resource names into `.env.example`; T+0:50 thin path to G1/G4; async getter signatures to G1 as soon as they change; T+1:30 and T+2:50 merges; any model change -> post diff to G3 at once.

**Pitfalls**
- Verify Bedrock model IDs and the client class before T+0:00. CONTRACTS §9 says `AsyncAnthropicBedrock`; newer SDKs also offer a Bedrock Mantle client. Use whichever works with your inference profile; record it.
- Haiku 5.5 and Sonnet 5.5 reject non-default `temperature`/`top_p`/`top_k` and assistant prefill. Get JSON through structured output (`output_config.format`) or a strict JSON instruction plus one retry. Check the current docs.
- Thinking is adaptive by default on these models and is billed as output. Set a low effort for the Writer; confirm cost in the ledger.
- Prompt caching only works above the model minimum prefix length. Check `usage.cache_read_input_tokens > 0` on the second call.
- Do not block the event loop: run model2vec and k-means in `asyncio.to_thread`.
- Do not let a single cell failure kill the job; log and continue.
- Do not change a protocol signature after T+0:15 without A5. A5 codes the aws implementations against it.
- Keep the in-memory read state (chunks, embeddings, `EvidenceIndex`, `Retriever`) inside `run_job`. The worker task lives across plan approval, so do not serialize these objects.
- Do not append events from the API while a worker runs. Two writers collide on the same seq (the aws EVT put is conditional and fails loudly).
- Never write outside `settings.runs_dir`. Lambda has a read-only disk except `/tmp`.
- `core/backends.py` must import `bob.aws.*` lazily. Local mode must run without AWS credentials.

---

## A2 Read (Aaditya)

**Role:** Reading pipeline and decision-model clients owner.
**Mission:** Build the Jev and ScaleDown clients with real calls and real fallbacks, then turn documents into clean chunks, topics with briefs, an evidence index with verbatim spans, and a retriever. Your evidence index is the ground truth that verification checks against, so span accuracy matters more than speed.

**Read first:** CONTRACTS §0, §2 (Document, Chunk, Evidence, Topic, CostSummary), §3 (A2 block), §4 (Jev questions and failure modes), §5 (all), §9, §12. PLAN §3, §4, §11.

**You own:** `backend/bob/clients/jev.py`, `clients/scaledown.py`, `backend/bob/pipeline/chunk.py`, `filters.py`, `embed.py`, `triage.py`, `topics.py`, `evidence.py`, your tests.
**Do not touch:** `core/*`, `llm/*`, `orchestrator.py`, other `pipeline/*` files, `connectors/*`, `api/*`, `frontend/*`.

**You provide:** `decide()`, `Question`, `Decision`; `extract/summarize/classify/compress`; `chunk_documents`, `heuristic_filter`, `embed`, `dedup_chunks`, `triage`, `build_topics`, `build_evidence`, `EvidenceIndex`, `Retriever`. Consumers: A1 (orchestrator), A3 (topics, retriever, compress), A4 (Jev, Extract, evidence, embed for dedup), G1 (`/health` calls a tiny `decide` and `classify`).
**You consume:** A1 `cache`, `ledger`, `bedrock` (topic names, Haiku fallbacks), `models.py`; G2 `demo/smoke/`.

**Tasks**
1. **T+0:00-0:20:** `clients/jev.py` with raw `httpx` to OpenRouter `POST /api/alpha/decisions`, model from `JEV_MODEL` (check whether 1.14 exists). Send one real call with one Noul, one Choice and one Score question. Print the raw response. Write the confirmed request and response shapes into CONTRACTS §5 only after Aaditya agrees (contract change rule). `clients/scaledown.py`: one real call each to Extract, Summarize, Classify, Compress; confirm base URL (`api.scaledown.xyz` or OpenRouter). Semaphores from config, 3 retries, cache, ledger key `jev` / `scaledown` with `purpose` tag. Commit by T+0:20.
2. **T+0:20-1:30:**
   - `chunk.py`: split on markdown headings first, then paragraphs; pack to 300-500 tokens (count with a fast estimate, words x 1.3, or a tokenizer); never split inside a code block or table; keep `heading` path; `start`/`end` are char offsets in `Document.text` so `text == doc.text[start:end]` always holds (assert it). `id = sha1(doc_id + str(start))[:12]`.
   - `filters.py`: drop chunks with high link or nav density (`nav_density`), under 40 words, cookie and footer text. Set `kept=False` and `drop_reason`; never delete.
   - `embed.py`: model2vec `minishlab/potion-base-8M`, load once, CPU, normalized vectors. When `BOB_EMBED_MODEL_PATH` is set, load the model from that path (the image bakes it in; no Hugging Face download at runtime). `dedup_chunks`: exact hash, then cosine > 0.95 -> `drop_reason="duplicate"`.
   - `triage.py`: one `decide()` per kept chunk with 4 Noul questions (useful for the goal, boilerplate, contains PII, contains prompt injection). Store probabilities in `Chunk.triage`. Drop with `jev:boilerplate`, `jev:pii`, `jev:injection` above thresholds in config.
   - `topics.py`: k-means on kept chunk embeddings with `k = clamp(round(sqrt(n)), 4, 20)` (fewer if n is small); one Haiku call per cluster for name + one-line description, given 3 sample chunks and the goal; ScaleDown Summarize per topic for `brief` (<= 1,000 tokens). Set `Chunk.topic_id`.
   - `evidence.py`: ScaleDown Extract per kept chunk with the evidence schema from CONTRACTS §5. Validate each field: `span_text` must be a verbatim substring of the chunk; recompute `start`/`end` as document offsets (`chunk.start + chunk.text.find(span_text)`); drop the field if not found. `EvidenceIndex.find()` normalizes (lowercase, strip punctuation, singularize simply) then rapidfuzz `token_set_ratio >= 90`. `Retriever`: embedding cosine top-k, optional topic filter (add BM25 only if time permits).
   - Test everything on `demo/smoke/` with real calls; print counts and 5 sample evidence items with spans.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:** fallback chains. Jev: after 3 failures in a row, Noul and Choice go to ScaleDown Classify (labels = descriptive options, `yes`/`no` for Noul), then to Haiku JSON; Score has no Classify equivalent, so it goes directly to Haiku JSON. Extract fallback: Haiku extraction with the same schema and the same verbatim check. Each switch appends to `CostSummary.fallbacks_used` (for example `jev->scaledown_classify`) and emits a `log` event. Test by forcing a failure (bad model name through an env override), with real fallback calls. Run the full `demo/corpus/`; read 20 dropped chunks and 20 evidence items; tune thresholds.
5. **T+3:00-3:30:** fix bugs; speed up evidence with batching under the semaphore.

**Definition of done:** On `demo/corpus/`, every stage runs with real calls; every `Evidence.span_text == doc.text[start:end]`; `Retriever.top_k` returns relevant chunks for 5 hand-written queries; topics have readable names and briefs; a forced Jev failure produces real Classify answers and a `fallbacks_used` entry.

**Handoffs and sync points:** T+0:20 client shapes to A4 and A1; T+1:00 topics, evidence and retriever to A3 and A4; tell G1 the cheapest real call for `/health`.

**Pitfalls**
- Jev follows option names. Use descriptive option names only (never `0/1`, `A/B`).
- Do not send `temperature` or `max_tokens` to Jev. No OpenAI SDK.
- Jev gives calibrated probabilities, no text. Do not ask it for explanations.
- Extract schema is guidance only. Validate types and verbatim spans in code.
- Offsets drift if you normalize whitespace after chunking. Chunk the final `Document.text` only.
- Keep the 4 triage questions in one call to save cost.
- Do not hard-code the model download in `embed.py`. In Lambda only `/tmp` is writable, so the cloud image must use `BOB_EMBED_MODEL_PATH`.

---

## A3 Plan + Write (Aaditya)

**Role:** Planner, Writer and gap controller owner.
**Mission:** Turn topics and the goal into a coverage map the user can edit, then write diverse, grounded candidates for every cell and case type, and steer later rounds to thin and hard cells. The Writer must produce rows that pass verification on the first try as often as possible.

**Read first:** CONTRACTS §0, §2 (Topic, Axis, Cell, Plan, Candidate, Message), §3 (A3 block, GenContext), §4 (so your rows pass), §9 (`OVERGEN`, `WRITER_BATCH`, caching note). PLAN §2, §4, §8, §9, §10, §11.

**You own:** `backend/bob/pipeline/planner.py`, `generate.py`, `gaps.py`, `backend/bob/pipeline/prompts/planner.md`, `prompts/writer*.md`, your tests.
**Do not touch:** `prompts/judge.md` (A4), `llm/bedrock.py` (A1; request changes), all other files.

**You provide:** `propose_plan`, `allocate_targets`, `generate`, `plan_gap_round`. Consumers: A1 (orchestrator), A4 (candidates), G3 (Plan shape and notes in the UI).
**You consume:** A1 `bedrock.py`, `GenContext`, ledger; A2 topics, `Retriever`, `EvidenceIndex`, `compress()`; G2 `demo/smoke/` and `seeds.jsonl`.

**Tasks**
1. **T+0:00-0:20:** With A1, get one real Haiku call through `llm/bedrock.py`. Write `prompts/writer.md` v1 and test it on one real smoke chunk as soon as G2 lands `demo/smoke/`.
2. **T+0:20-1:30:**
   - `planner.py`: one Sonnet call with goal, topic names + descriptions + brief excerpts, seed summary, target rows and budget. Output JSON: `system_prompt`, axes (`topic` from real topics, 3-5 `persona` values with descriptions, `case_type` = CASE_TYPES, `difficulty` = DIFFICULTIES), `notes`. Code builds the cross product of cells (`id = sha1(sorted coords)[:10]`) and computes seed coverage notes from real seeds (for example "Your seeds cover 4 of 14 topics"). Disable cells that cannot exist (for example `multi_doc` for a topic with chunks from one doc). `est_cost_usd` = cells x expected calls x real token averages x config prices.
   - `allocate_targets`: split `target_rows` across enabled cells by `weight`; default mix answerable 50%, partial 15%, unanswerable 20%, false_premise 15%; minimum 1 per enabled cell; integer rounding with remainder to the largest cells.
   - `generate.py`: per call ask for `WRITER_BATCH` (5) **different** candidates as JSON `{"rows": [...]}`. Context: topic brief + top-k retrieved chunks for the cell (multi_doc: chunks from at least 2 docs), shrunk with ScaleDown Compress; keep chunk ids in the prompt so the Writer cites them. Prompt caching: system prompt + topic brief form the stable prefix (cache breakpoint after them); the cell-specific part goes after. Persona and difficulty conditioning: describe the persona (role, vocabulary, what they care about) and the difficulty (`single_fact` = one fact; `multi_step` = a procedure or two linked facts; `multi_doc` = facts from two docs). Ask for varied openings, lengths and tones; include 2 real seeds as style examples when present.
   - Case-type prompts (`writer_answerable.md`, `writer_partial.md`, `writer_unanswerable.md`, `writer_false_premise.md`):
     - **answerable:** the question is fully answered by the passages; the reply uses only passage facts, no "according to the document".
     - **partial:** half of the question is in the passages, half is not; the reply answers the covered part, names the uncovered part, offers a human handoff.
     - **unanswerable:** the question is on-topic and plausible but not covered; the Writer must fill `absent_topic` (what is missing); the reply says the docs do not cover it and offers a handoff, with no invented details. Code checks with `Retriever.top_k` that the absent topic is not obviously present.
     - **false_premise:** pick one real Evidence item (setting, limit, number); the user assumes a wrong value; set `premise_evidence_id` to that item; the reply corrects it politely with the real value.
   - Parse JSON; on failure retry once, then drop. Each `Candidate` carries `chunk_ids`, `writer_model`, real `cost_usd`.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:** `gaps.py` `plan_gap_round` (**P0**: round 2 must run at checkpoint 2; round 3 is P1). Deliver to A1 by T+2:00. For each enabled cell, `deficit = target - kept`; skip if `deficit <= 0`; `n = ceil(deficit * OVERGEN)`; if the cell rejection rate `rejected / generated > 0.5`, multiply `weight` by 1.5 and `n` by 1.5 (hard cell) and switch to a stricter prompt variant; cap the total of `n` across cells so the estimated cost fits in the remaining budget (`0.95 * budget - total_usd`), scaling all cells down proportionally. Return `(cell, n)` sorted by deficit. At T+2:00 read 50 real kept rows across personas and difficulties; fix repeated openings, sameness and leaks; re-run.
5. **T+3:00-3:30:** prompt tuning on reject reasons from the report; multi-turn rows only if all else is green (stretch).

**Definition of done:** `propose_plan` on smoke and on the full corpus returns a valid `Plan` that the UI renders; `generate` returns 5 parsed, distinct candidates for each of the 4 case types with real calls; every unanswerable row has `absent_topic`, every false_premise row has a valid `premise_evidence_id`; cache reads are visible in usage on repeated cell calls; a gap round targets only thin and high-reject cells.

**Handoffs and sync points:** T+1:00 Plan shape to G3 (sample real plan JSON in a run folder); T+1:10 `generate` to A1 and A4; T+2:00 report the 50-row read to Aaditya.

**Pitfalls**
- No `temperature` on Haiku 5.5. Diversity comes from the prompt: persona, difficulty, "5 different rows", varied openers, and seeds.
- Any change in the cached prefix (timestamps, random order) kills the cache. Keep it byte-stable.
- Do not let the Writer copy passage sentences into the user turn; that fails `jev.realistic`.
- Do not put numbers in replies that are not in the passages; tier-1 `numbers` rejects them.
- The Planner must use real topic names from A2, not invent topics.

---

## A4 Verify + Ship (Aaditya)

**Role:** Verification cascade, report and export owner.
**Mission:** Decide which rows are kept, with proof. Implement the exact 3-tier cascade, routing and judge, then build DPO pairs, the data quality report and every export preset and format. Verification and the row inspector data are the product; never cut them.

**Read first:** CONTRACTS §0, §2 (Candidate, CheckResult, SpanRef, Row, DPOPair, Report), §3 (A4 block), §4 (all), §9 (thresholds, judge model), §11, §12. PLAN §2 steps 3-5, §4, §7, §9 steps 4-7.

**You own:** `backend/bob/pipeline/verify.py`, `report.py`, `probe.py` (stretch), `backend/bob/pipeline/prompts/judge.md`, `backend/bob/export/presets.py`, `formats.py`, `manifest.py`, your tests.
**Do not touch:** writer and planner prompts, clients, core, all Gunbir files.

**You provide:** `verify`, `build_dpo_pairs`, `build_report`, `export`; preset list for G1 `/presets`. Consumers: A1, G4 (Row, Report shapes), G1 (file paths).
**You consume:** A2 `decide`, `extract`, `EvidenceIndex`, `Retriever`, `embed`; A1 `bedrock` (judge), `GenContext`, ledger; A3 candidates.

**Tasks**
1. **T+0:00-0:20:** write `prompts/judge.md` (input: passages, case type, row, tier-2 results; output JSON `{"verdict": "keep"|"reject", "reason": "..."}`; strict rules per case type). Write preset functions in `presets.py` as pure code from CONTRACTS §11.
2. **T+0:20-1:30:** `verify.py`, per candidate, in this order, stop at the first hard fail:
   - Tier 1: `format`, `banned_phrases`, `dedup` (normalized user-turn hash, then embedding cosine > `DEDUP_COS` against kept rows in the same cell), `numbers` (every number in the reply appears in cited chunks or evidence values). Each check produces a `CheckResult` with a readable `detail`.
   - Tier 2: `extract.names` (Extract on the reply with `{features[], settings[], urls[], limits[]}`; each name must match `EvidenceIndex.find()`; detail `"Mentions 'X', which is not in the docs"`). Then one `decide()` call with exactly 5 questions: the 3 shared ones (`jev.cell` Choice, `jev.quality` Score, `jev.realistic` Noul) plus the 2 for the case type from the §4 table. `state` = `PASSAGES:` + `USER:` + `ASSISTANT:` labelled blocks. For unanswerable, passages = `Retriever.top_k(user, 5)`; for false_premise, the passage holding `premise_evidence_id`; else the cited chunks.
   - Pass rules come from the §4 table. `jev.not_in_docs` passes when `p <= 1 - KEEP_P` (0.1).
   - `confidence` = minimum **pass-direction** probability over the 2 case-type Noul checks only (not `jev.realistic`): `p` for checks that pass on yes, `1 - p` for `jev.not_in_docs`.
   - Routing (CONTRACTS §4): (1) any hard fail (tier 1, `extract.names`) -> rejected; (2) else `confidence < REJECT_P` -> rejected; (3) else all Jev checks pass -> kept; (4) else (any soft Jev fail, including `jev.cell`, `jev.quality`, `jev.realistic`) -> tier 3. Fill `Job.files` with keys `"<preset>/<split>.<format>"`. Send a random `AUDIT_RATE` of kept rows to tier 3 with `audited=True`. Judge concurrency from config; judge verdict is final.
   - Build `spans` from cited chunks and matched evidence (`SpanRef` with doc offsets); `reject_reason` = first failing check detail.
   - `export` for `openai-chat` in JSONL and Parquet (system prompt from `Plan.system_prompt` added at export), path `settings.runs_dir/<job_id>/export/<preset>/<split>/<split>.<ext>` (one data file per folder). Never hard-code `runs/`. A1 uploads the export tree to S3 after `export` returns.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:** First the P0 items: full `build_report`, and `openai-chat` + `full` in JSONL and Parquet with manifest and provenance. Then the P1 items (finish by T+3:30): DPO pairs, other presets and formats, spot-check accuracy. `build_dpo_pairs`: group rows by normalized user turn within a cell; pair each kept reply with a rejected reply to the same user turn (rejected for a content reason, not `format` or `dedup`). `build_report`: coverage per cell, pass rate per check, reject reasons by check name, duplicates removed, judge rate, judge agreement (tier-2 route vs judge verdict on routed + audited rows), 50 sample row ids stratified by cell, token stats, rounds; spot-check `jev_accuracy` = share of thumbs-up on kept rows (optionally show a Wilson 95% interval in `spot_check`). All presets and formats (`jsonl`, `json`, `csv`, `parquet`); stratified 95/5 train/eval split by cell (cells with 1 row go to train); one data file per folder: `settings.runs_dir/<job_id>/export/<preset>/<split>/<split>.<ext>` (for example `export/openai-chat/train/train.jsonl`); `bob_manifest.json` (job, plan, counts, cost, checks, model ids, created_at) and `provenance.parquet`.
5. **T+3:00-3:30:** stretch `probe.py` (ask the base model each kept question, mark cells where it fails, feed to the gap controller) only if checkpoint 2 is green.

**Definition of done:** On real smoke candidates, each case type yields kept and rejected rows with correct `CheckResult` lists; a hand-made candidate (written by you as a test input, sent through real calls) that mentions an invented feature fails `extract.names`; routing sends 3-15% to the judge; P0: `openai-chat` and `full` in JSONL + Parquet open in pandas at T+2:50; P1 by T+3:30: all 7 presets x required formats open, DPO file non-empty on a real job; report numbers match a recount from `rows.jsonl`.

**Handoffs and sync points:** T+0:20 confirm A2 client shapes; T+1:15 `verify` + JSONL to A1; T+2:30 Report shape example (real JSON from a run) to G4; tell G1 the preset list.

**Pitfalls**
- About 11.5% of Jev answers are wrong at >= 90% confidence. Answerable rows need both `jev.supported` and `extract.names`.
- Jev is weak at arithmetic and dates; keep `numbers` in code.
- Descriptive option names only for `jev.cell` (topic names) and `jev.quality` levels.
- Normalize numbers before matching (`1,000` == `1000`, `30-day` == `30 days`).
- Parquet: nested fields (`messages`, `spans`, `checks`) must have a stable schema; serialize to JSON strings if pyarrow complains.
- Write export files only under `settings.runs_dir` (`/tmp/runs` in the cloud). A write to `runs/` fails on the read-only Lambda disk.

---

## A5 Deploy (Aaditya)

**Role:** AWS deployment and cloud backends owner.
**Mission:** Deploy Bob to AWS serverless: a Lambda API behind CloudFront and one Fargate worker task per job. Write the aws implementations of A1's backend protocols, the worker entry, the image and the CDK stacks. Checkpoint 2 must pass on the CloudFront URL. Local mode stays the default; you add the cloud mode, you do not change the local behavior.

**Read first:** CONTRACTS §0, §1, §7, §8, §9, §12, §13 (all). DECISIONS D23, D25. PLAN §5, §6, §10, §11.

**You own:** `backend/bob/aws/blobs.py`, `aws/store.py`, `aws/events.py`, `aws/runner.py`, `aws/secrets.py`, `backend/bob/worker.py`, `backend/Dockerfile`, root `.dockerignore`, root `.gitignore` (write it first, before any commit: `.env`, `secrets.json`, `runs/`, `cdk.out/`, `infra/outputs.json`, `node_modules/`, `dist/`, `__pycache__/`), `infra/**` (`app.py`, `cdk.json`, `requirements.txt`, `bob_infra/data_stack.py`, `bob_infra/app_stack.py`, `deploy.sh`, `README.md`), your tests for the aws backends.
**Do not touch:** `core/*`, `config.py`, `orchestrator.py`, `backend/pyproject.toml` (A1; request `boto3` and other packages through A1), `pipeline/*`, `clients/*`, `export/*`, all Gunbir files.

**You provide:** `S3Blobs`, `DynamoStore`, `DynamoEventLog`, `EcsRunner` (they implement A1's protocols); `bob/aws/secrets.py` (load the `bob/keys` secret JSON into the environment); `python -m bob.worker <job_id> <mode>`; the image; the `BobData` and `BobApp` stacks; `infra/deploy.sh`; the CloudFront URL; the table, bucket and secret names. Consumers: A1 (`backends.py`, `config.py`), all agents (cloud URL), Gunbir (checkpoint 2 test on the cloud).
**You consume:** A1 protocols, config vars and `run_job` (T+0:15 stubs, T+1:30 real); G1 `/api/ping` and `/api/health`; G3 `npm run build` output; G2 `demo/` (copied into the image).

**Tasks**
1. **Before T+0:00 (pre-flight):** Choose the AWS account and the Bedrock region (it must have Haiku 5.5 and Sonnet 5.5). Run `cdk bootstrap aws://<account>/<region>`. Make sure Docker Desktop runs. Install Node 20 and `npm i -g aws-cdk`. Put the API keys in a local `secrets.json` (never committed).
2. **T+0:00-0:20:** CDK v2 app skeleton in Python (`infra/`). Deploy `BobData`: DynamoDB table `bob` (on-demand, `pk`/`sk` strings, TTL `expires_at` = 7 days), the data bucket, the frontend bucket, the secret `bob/keys`. Buckets use DESTROY + autoDeleteObjects. Set the secret value: `aws secretsmanager put-secret-value --secret-id bob/keys --secret-string file://secrets.json`. Post the table, bucket and secret names to all agents. A1 adds them to `.env.example`.
3. **T+0:20-1:30:**
   - `backend/Dockerfile`: build context = repo root, `python:3.12-slim`, linux/amd64, `pip install ./backend`, copy the Lambda Web Adapter extension (`public.ecr.aws/awsguru/aws-lambda-adapter`) to `/opt/extensions/`, bake the model2vec model to `/opt/models/potion-base-8M`, copy `demo/` to `/app/demo`. Default CMD = uvicorn `bob.api.app:app` on port 8080. Root `.dockerignore` (exclude `.env`, `runs/`, `node_modules/`, `cdk.out/`, `secrets.json`).
   - `bob/aws/*` against A1's protocols (CONTRACTS §13). Use boto3 inside `asyncio.to_thread` (no aioboto3). `DynamoStore`: `META`, `ROW#`, `JOBS` items; the full Job document goes to S3 `runs/<id>/job.json`. `DynamoEventLog`: `EVT#<seq:08d>` items with a conditional put (`attribute_not_exists(sk)`); `read_after` = Query with `sk > EVT#<seq>` and `begins_with EVT#`, ConsistentRead; `subscribe` polls `read_after` every `BOB_EVENT_POLL_MS`. `S3Blobs`: keys mirror the local `runs/` tree; `url()` returns a presigned GET (1 h). `EcsRunner`: `ecs.run_task` (public subnet, `assignPublicIp=ENABLED`); refuse a new job when `BOB_MAX_WORKERS` (2) tasks run; `stop()` = `ecs.stop_task`.
   - Test `bob/aws/*` on real DynamoDB and S3. No moto, no LocalStack (D23).
   - `bob/worker.py`: thin entry. Load secrets -> build Orchestrator -> `await run_job(job_id, mode)` -> exit code.
   - `BobApp` stack: image asset; API Lambda (2048 MB, timeout 900 s, x86_64, ephemeral storage 2048 MB, reserved concurrency 20) with a Function URL (invoke mode RESPONSE_STREAM); Lambda env `AWS_LWA_INVOKE_MODE=response_stream`, `AWS_LWA_PORT=8080`, `AWS_LWA_READINESS_CHECK_PATH=/api/ping`, `BOB_ENV=aws`, `BOB_RUNS_DIR=/tmp/runs`; ECS cluster and worker task def (2 vCPU / 4 GB, x86_64, CMD `python -m bob.worker`, logs to `/bob/worker`); default VPC, egress-only security group, no NAT; CloudFront with the S3 default behavior (CloudFront Function rewrites non-file paths to `/index.html`) and `/api/*` to the Function URL (CachingDisabled, AllViewerExceptHostHeader, all methods, origin read timeout 60 s); IAM roles per CONTRACTS §13.
   - `infra/deploy.sh`: `npm run build` -> `cdk deploy --all --require-approval never --outputs-file infra/outputs.json` -> print the CloudFront URL. It must work from a clean checkout in < 15 min.
   - **By T+1:15:** the CloudFront URL serves the UI, and `/api/ping` and `/api/health` work there with the current backend code. Tell all agents.
4. **T+1:30 checkpoint 1.** Local pass test as before, plus the cloud health check above.
5. **T+1:40-2:50:** Deploy the checkpoint-1 merge. Run a real job in the cloud: create -> Fargate worker -> plan -> approve -> rows on SSE through CloudFront -> file download from S3. Test SSE reconnect (set `BOB_SSE_MAX_S=60` for one test). Make sure cancel stops the job in 5 s. Measure the worker cold start (target: by T+2:00).
6. **T+2:50 checkpoint 2.** Deploy the merge. The pass test runs **on the CloudFront URL** (P0).
7. **T+3:00-3:30 (P1):** resync mode in the worker; origin-secret header (CloudFront adds `X-Bob-Origin`; API middleware rejects calls without it, so nobody can call the Function URL directly); AWS Budgets alarm; presigned uploads (`POST /uploads/presign`, with G1); a CloudWatch Logs Insights query for errors.
8. **T+3:30-4:00:** Deploy the frozen `main` (tag `demo`) once. Run the demo job once on the cloud URL. Keep localhost as the backup. After the event: `cdk destroy --all`.

**Definition of done:** P0 at T+2:50: both stacks deploy from a clean checkout with `infra/deploy.sh` in < 15 min; the aws backends pass their tests on real AWS; a real job runs on a Fargate worker; SSE streams through the Function URL and CloudFront and reconnects with `Last-Event-ID`; files download from S3; the checkpoint-2 pass test passes on the CloudFront URL. P1 by T+3:30: resync in the cloud, origin-secret header, budget alarm, presigned uploads, logs query. Cut line: if the cloud job path fails at T+3:30, demo on localhost and show the deployed UI and `/api/health`.

**Handoffs and sync points:** T+0:15 get A1's protocol stubs, config vars and `boto3`; T+0:20 post resource names to all agents (A1 puts them in `.env.example`); T+1:15 cloud health on the CloudFront URL to all; T+1:30 cloud health at checkpoint 1; T+2:00 cloud real job and worker cold start to Aaditya and Gunbir; T+2:50 checkpoint 2 on the CloudFront URL; T+3:30 deploy tag `demo`.

**Pitfalls**
- The SPA fallback must not be distribution-wide. Use a CloudFront Function on the default behavior only. Distribution-wide custom error pages turn API 404s into `index.html`.
- Bedrock IAM: give `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on the inference profile ARN and on the foundation model ARNs in all regions that the profile routes to. Check `/api/health` on the cloud URL at T+1:15; a call can work with your user profile and fail with the role.
- Build the image with `--platform linux/amd64`. Docker on Windows builds for the wrong platform without it.
- In Lambda, `/tmp` is the only writable path. Set `BOB_RUNS_DIR=/tmp/runs` and ephemeral storage 2 GB.
- CloudFront cuts an origin after 60 s idle. The SSE route must send `: ping` every `BOB_SSE_HEARTBEAT_S` (15 s) and end at `BOB_SSE_MAX_S` (840 s); the browser reconnects.
- Set the LWA readiness check to `/api/ping`, not `/health`. `/health` makes paid calls and must not run on each cold start.
- Never commit `secrets.json` or `infra/outputs.json`. Add both to `.gitignore` (request it through `CHANGES_REQUESTED.md` if you do not own the file).
- Add `cdk.out/` to `.gitignore`.
- Fargate cold start is 30-60 s before the plan shows. Keep the image small and start the demo job early.

---

## G1 API + Files (Gunbir)

**Role:** Web API, SSE and file ingestion owner.
**Mission:** Expose the orchestrator through every route in CONTRACTS §6, stream events over SSE with replay, accept uploads, parse files into `Document`, and dispatch `fetch_documents()` to the right connector. Make every provider error visible to the user.

**Read first:** CONTRACTS §0, §1, §2 (SourceSpec, Document, Job, Row, Report), §6 (all), §7, §8, §12, §13 (Lambda limits). PLAN §2, §5, §7 items 1 and 8. DECISIONS D25.

**Lambda limits that change your work** (the API runs in AWS Lambda in the cloud):
1. The API has no background work. A task that starts after the response freezes. Long work goes to the worker only (`Runner.start`).
2. Every route returns in < 25 s (CloudFront origin timeout). `POST /sources/preview` caps pages and time (for example 10 pages or 20 s) and says so in its response.
3. Request bodies are <= 6 MB. `POST /uploads` keeps multipart for P0 (demo files are small). P1: `POST /uploads/presign` returns a presigned S3 PUT for larger files.
4. No writes outside `BOB_RUNS_DIR` (`/tmp/runs` in Lambda). Store uploads through `Blobs.put("runs/uploads/<id>/<name>")`. The helper is `async def read_upload(upload_id) -> list[tuple[name, bytes]]`, not a disk path.
5. SSE: send `retry: 1000` at stream start, a `: ping` comment every `BOB_SSE_HEARTBEAT_S`, and the headers `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Close the stream after `BOB_SSE_MAX_S`. The browser reconnects with `Last-Event-ID` (replay is already in the contract).
6. `GET /jobs/{id}/files/{name}`: if `blobs.url()` returns a URL, reply 302 to it. Else stream the local file.
7. New route `GET /api/ping` -> `{ok: true}` with no external calls (Lambda readiness check). `/health` makes paid calls and must not run on each cold start.
8. Composio OAuth `redirect_url` = `BOB_PUBLIC_URL` in aws mode.

**You own:** `backend/bob/api/app.py`, `api/routes.py`, `api/sse.py`, `backend/bob/connectors/__init__.py`, `connectors/upload.py`, `connectors/parsers.py`, run script (`backend/run.sh` or `make dev`), your tests.
**Do not touch:** `connectors/firecrawl.py`, `composio.py`, `sync.py` (G2), all Aaditya files, `frontend/*`.

**You provide:** all HTTP routes, including `GET /api/ping`; `fetch_documents(spec, job_id, progress)`; upload storage through `Blobs` and a helper `async def read_upload(upload_id) -> list[tuple[name, bytes]]` for A1 seeds and the upload connector. Consumers: G3, G4 (HTTP), A1 (`fetch_documents`, `read_upload`), A5 (`/api/ping` readiness, `/api/health` cloud check).
**You consume:** A1 `Orchestrator` (`get_job`, `list_jobs`, `list_rows`, `get_row` are `async`: always `await` them), models, `get_blobs()`; G2 `firecrawl.fetch(...)`, `composio.fetch(...)`, `composio.connect/status/browse`; A2 clients for `/health`.

**Tasks**
1. **T+0:00-0:20:** FastAPI app, CORS for the Vite dev origin (and `BOB_PUBLIC_URL` in aws mode), `/api` prefix, run script. `GET /api/ping` -> `{ok: true}` with no external calls. `/health` makes one tiny real call per provider (Bedrock, Jev, ScaleDown, Firecrawl, Composio) in parallel with a timeout and returns `ok` or the error text.
2. **T+0:20-0:45:** `POST /uploads` (store through `Blobs.put("runs/uploads/<id>/<name>")`), `read_upload`, MD/TXT parser, `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/events`. This unblocks A1's thin path.
3. **T+0:45-1:30:**
   - `sse.py`: wire format `id: <seq>\nevent: <type>\ndata: <json>\n\n`; read `Last-Event-ID` header (and a `last_event_id` query param for EventSource reconnects); call `Orchestrator.subscribe()`; send `retry: 1000` at stream start; send a `: ping` comment every `BOB_SSE_HEARTBEAT_S` (15 s); set `Cache-Control: no-cache` and `X-Accel-Buffering: no`; close the stream after `BOB_SSE_MAX_S`.
   - All other §6 routes on the orchestrator. `GET /rows` with filters and paging. `POST /spot-check` and `POST /export` return HTTP 409 `{"error": "job is running"}` while a worker runs (CONTRACTS §7, single job writer). File download: if `blobs.url()` returns a URL, reply 302 to it; else stream the local file with a safe path check (only under `settings.runs_dir/<job_id>/export/`).
   - Parsers: PDF (pypdf), DOCX (python-docx, headings -> `#`), HTML (markdownify), MD, TXT, CSV (rows as markdown table or one section per row). Output normalized markdown, `id = sha1(uri)[:12]`, `content_hash = sha1(text)`.
   - `fetch_documents`: dispatch by `kind` to upload, `firecrawl`, `composio`; pass `progress(done, total, detail)`.
4. **T+1:30 checkpoint 1.**
5. **T+1:40-2:50:** error handling: map provider exceptions to JSON `{error, provider, detail}` with correct status; job errors appear in `Job.error` and SSE `error`; `/sources/preview` (cap pages and time, for example 10 pages or 20 s, and say so in the response); `GET /jobs` list with summary fields; connector routes on G2 functions; `/presets`.
6. **T+3:00-3:30:** fix bugs; `POST /uploads/presign` for larger files (P1, with A5); README run steps for the API.

**Definition of done:** Every §6 route works against a real job; disconnecting and reconnecting SSE with `Last-Event-ID` replays missed events with no gaps or duplicates; each of the 6 file types parses a real file; `/health` shows a real error when one key is wrong; the UI shows that error.

**Handoffs and sync points:** T+0:20 tell A5 that `/api/ping` and `/api/health` are live; T+0:45 tell A1 the thin-path routes are live; T+1:15 tell G3/G4 every route is live; T+1:15 check `/api/health` on the CloudFront URL with A5; agree on route errors format with G3.

**Pitfalls**
- Do not run long work inside the request, and do not start a background task in the API process (it freezes in Lambda). `create_job` starts the worker through the runner and returns at once.
- Every route returns in < 25 s. Request bodies are <= 6 MB.
- Never write outside `settings.runs_dir`. Store uploads through `Blobs`.
- `await` the async orchestrator getters. A missing `await` returns a coroutine, not a Job.
- SSE behind gzip middleware buffers; exclude the events route.
- `Last-Event-ID` is a string; parse to int safely.
- Never echo API keys in `/health` errors.

---

## G2 Connectors (Gunbir)

**Role:** External source connectors and demo data owner.
**Mission:** Fetch real content from websites (Firecrawl) and internal apps (Composio: Notion first, then Jira, Confluence, Google Drive) as `Document` objects with live progress. Produce the smoke corpus that all backend tests use, the cached demo corpus, and the re-sync diff.

**Read first:** CONTRACTS §0, §1, §2 (SourceSpec, Document), §6 (connector routes, `/sources/preview`), §7 (`fetch_documents`), §10, §12. PLAN §2, §6 (pre-start checklist), §9, §11.

**You own:** `backend/bob/connectors/firecrawl.py`, `connectors/composio.py`, `connectors/sync.py`, `demo/*` (`demo/smoke/`, `demo/corpus/`), your tests.
**Do not touch:** `connectors/__init__.py`, `upload.py`, `parsers.py` (G1), all Aaditya files, `frontend/*`.

**You provide:** `firecrawl.fetch(spec, job_id, progress) -> list[Document]`; `composio.connect(toolkit, redirect_url)`, `status(toolkit, connection_id)`, `browse(toolkit, account_id, q)`, `fetch(spec, job_id, progress)`; `sync.diff(old_docs, new_docs) -> {added, changed, removed}`; `demo/smoke/*.md`, `demo/smoke/seeds.jsonl`, `demo/corpus/`. Consumers: G1, A1 (resync), A2/A3/A4 (smoke tests).
**You consume:** A1 models, cache, ledger: `ledger.record(job_id, "firecrawl" | "composio", calls=..., usd=...)` (CONTRACTS §7). Config: `FIRECRAWL_API_KEY`, `COMPOSIO_API_KEY`, `COMPOSIO_USER_ID`, `COMPOSIO_DEMO_ACCOUNTS`. Commit the first real smoke page by T+0:10 so A3 can test the Writer.

**Tasks**
1. **T+0:00-0:20:** Real Firecrawl scrape of 3-5 demo doc pages -> `demo/smoke/<slug>.md` (markdown only, with source URL in a front-matter line). Write 10 real seed questions with real answers from those pages -> `demo/smoke/seeds.jsonl` (`{"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}`). These are real examples a support agent would see, based on the real pages. Commit and announce by T+0:20.
2. **T+0:20-1:30:**
   - `firecrawl.py`: use the Firecrawl SDK `start_crawl(url, limit=crawl_limit, scrape_options=markdown)` then poll `get_crawl_status(id)` every 2 s; call `progress(done, total, url)` per new page; convert each page to `Document` (`uri` = page URL, `title` from metadata). Check method names against the installed `firecrawl-py` version before coding. Cache by crawl request.
   - `composio.py`: Composio Python SDK. `connect`: create or reuse the auth config for the toolkit, initiate the connected account for one fixed `user_id` (for example `bob-demo`), return `{auth_url, connection_id}`. `status`: poll the connected account until `ACTIVE`. **Tool slugs:** do not invent them. At start, list the toolkit's tools through the SDK, print slugs and input schemas, pick the search/list and fetch/get-content tools for Notion, and verify each with one real call. Store the verified slugs in a constant with a comment of the date. `browse`: search pages; return `[{id, title, kind}]`. `fetch`: for each page id, fetch blocks/content, convert to markdown, `uri = notion://<page_id>`.
   - Full demo crawl (cap 25 pages) of the demo docs -> `demo/corpus/` (one `.md` per page plus `index.json` with uri, title, hash). Real fetched content only.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50 (P1 items; Notion stays P0 and must not break):** Jira (`jql` scope -> issues with summary, description, comments; `uri = jira://<key>`) and Confluence or Google Drive (same slug discovery rule). `sync.py`: re-fetch each `SourceSpec`, compare `content_hash` per `uri`, return `added`, `changed`, `removed`. Cache the real Notion demo pages to `demo/corpus/notion/`.
5. **T+3:00-3:30:** connect the demo accounts before the demo; put the connected account ids in `.env` (never committed); fix bugs.

**Definition of done:** A real crawl of the demo URL emits per-page progress and returns 20-25 `Document`s; a real Notion OAuth connect works from the UI popup; browse lists real pages; fetch returns their text; `demo/smoke/` and `demo/corpus/` contain only real fetched content; `sync.diff` reports a change after a real page edit.

**Handoffs and sync points:** T+0:20 smoke corpus to A2/A3/A4/A1; T+1:15 function signatures to G1; T+1:30 corpus cached; T+2:30 `sync.py` to A1.

**Pitfalls**
- Do not guess Composio tool slugs or argument names; list and verify them at runtime.
- Notion content comes as blocks; handle pagination and nested children.
- Firecrawl crawl is async and slow; never block a request on it; keep `crawl_limit` at 25.
- OAuth redirect URL must match the frontend route G3 uses; agree on it early.
- Do not fake or hand-edit the corpus. If a fetch fails, fix it and fetch again.
- In the cloud, Firecrawl and Composio fetch run inside the Fargate worker (no time limit), not in the API Lambda.
- The image copies `demo/` to `/app/demo`. Commit `demo/corpus/` before A5 deploys checkpoint 2.
- In aws mode the OAuth redirect URL is `BOB_PUBLIC_URL` (the CloudFront URL), not localhost.

---

## G3 UI: Setup + Plan (Gunbir)

**Role:** Frontend shell, API client, Setup and Plan screens owner.
**Mission:** Build the React app shell and typed API client, then the Setup screen where a user enters a goal and connects real sources, and the Plan screen where the user edits the real coverage map and starts the build.

**Read first:** CONTRACTS §0, §1, §2 (all; you mirror it), §6 (all routes), §8 (`plan.ready`, `job.status`, `stage.progress`). PLAN §2 steps 1-2, §7 items 1-2, §9 steps 2-3.

**You own:** `frontend/` scaffold (`package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`), `frontend/src/main.tsx`, `App.tsx`, router and layout (app shell), `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/screens/Setup*`, `frontend/src/screens/Plan*`, shared non-viz UI components you create.
**Do not touch:** `screens/Build*`, `Row*`, `Report*`, `components/viz/*` (G4), all backend files.

**You provide:** `types.ts` (exact mirror of CONTRACTS §2), `client.ts` (one typed function per §6 route, plus an SSE helper with reconnect that sends the last event id), routes `/`, `/jobs`, `/jobs/:id/plan`, `/jobs/:id/build`, `/jobs/:id/rows/:rowId`, `/jobs/:id/report`, `/oauth/callback`. Consumers: G4.
**You consume:** G1 routes; G2 connector flow; A3 Plan shape.

**Tasks**
1. **T+0:00-0:20:** Vite + React 18 + TS strict scaffold, router, layout, `types.ts` from CONTRACTS §2 (same names, fields, literal unions; `CASE_TYPES`, `DIFFICULTIES` as consts). Add the `capped: bool` field of the `/sources/preview` response (CONTRACTS §6) and show it on the Setup screen. Commit and tell G4 by T+0:20.
2. **T+0:20-1:30:**
   - `client.ts`: relative base `/api` (same origin through CloudFront); no hard-coded host. `vite.config.ts` proxies `/api` to `localhost:8000` in dev. Errors raise with the server `{error, provider, detail}`.
   - Setup screen: goal textarea; URL input with crawl limit; file upload (drag and drop, calls `/uploads`, shows names and sizes); connector buttons from `GET /connectors` (Notion first): click -> `POST /connect` -> open `auth_url` in a popup -> poll `/status` -> show connected; then a browse picker (`/browse`) to select pages; row count, budget, seed upload; Create -> `POST /jobs` -> navigate to a progress view driven by SSE `stage.progress` until `plan.ready`.
   - Plan screen: axes with value chips and descriptions (edit persona names and descriptions, remove values); topic x case_type grid with toggle per cell or per row/column, filtered by persona and difficulty; target per cell; notes panel; estimated cost vs budget; Start -> `PUT /jobs/{id}/plan` -> Build route.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:** Job list page (`GET /jobs`); Setup preview of fetched documents (`/sources/preview`, shows uri, title, chars); provider error banners and `/health` status chips; fallback badge from `log` events.
5. **T+3:00-3:30:** polish (empty states, loading states, keyboard focus).

**Definition of done:** A user creates a job from a real URL, a real uploaded file and a real Notion page in one job; the Plan screen renders the real Planner output; toggling cells and editing personas changes the plan sent to `PUT /plan` and therefore the build; `tsc --noEmit` passes; no hard-coded data anywhere.

**Handoffs and sync points:** T+0:20 `types.ts` to G4; agree on the OAuth redirect route with G2 and G1; update `types.ts` within the hour of any A1 model change.

**Pitfalls**
- Do not add fields to `types.ts` that are not in CONTRACTS §2.
- Never ship sample JSON or placeholder rows. Show an empty state until the API answers.
- Popup blockers: open the OAuth popup directly in the click handler.
- Disabling cells must keep `Cell.id` stable; edit fields, do not rebuild cells.
- Never hard-code `localhost` or a cloud host in the client. The same build runs on Vite dev and on CloudFront.
- `npm run build` must pass at all times. A5's `infra/deploy.sh` runs it.

---

## G4 UI: Build + Results (Gunbir)

**Role:** Live build view, row inspector and report owner.
**Mission:** Make the factory visible. Show the coverage map filling live, every row with its verdict, the proof behind each row (source spans and checks), and the final quality report with spot-check and downloads.

**Read first:** CONTRACTS §2 (Cell, Row, CheckResult, SpanRef, Report, CostSummary, DPOPair), §4 (check names, to label them), §6 (rows, spot-check, export, files), §8 (all events). PLAN §2 steps 3-5, §7 items 3-6, §9 steps 4-7.

**You own:** `frontend/src/screens/Build*`, `frontend/src/screens/Row*`, `frontend/src/screens/Report*`, `frontend/src/components/viz/*`.
**Do not touch:** `api/*`, `types.ts`, Setup/Plan screens, app shell (G3), all backend files.

**You provide:** Build, Row inspector and Report screens; heatgrid and chart components.
**You consume:** G3 `types.ts`, `client.ts`, SSE helper; G1 routes; A1 events; A4 Row and Report shapes.

**Tasks**
1. **T+0:00-0:20:** design the Build layout and the heatgrid against `types.ts` shapes (no sample data in the repo; render empty until events arrive).
2. **T+0:20-1:30 (live from T+0:50 on the thin path):**
   - Build screen on SSE: heatgrid of cells (rows = topics, columns = case types, small facets or a selector for persona and difficulty); cell color = `kept / target` (0 to 1 sequential scale, distinct color for disabled, outline for cells in the current gap round); tooltip with generated, kept, rejected, judged, target.
   - Counters (`counts`): generated, kept, rejected, judged, duplicates; status and stage line (`job.status`, `stage.progress`); cost meter (`cost.total_usd` vs budget, frontier-only estimate); fallback badge from `cost.fallbacks_used` and `log`.
   - Row feed from `row` events (newest first, cap 200 in memory): verdict badge, case type, `user_preview`, confidence, judge icon, reject reason; filter kept/rejected; click opens the row inspector.
   - Reject reasons summary (count by check name) from rows seen.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:**
   - Row inspector (`GET /rows/{id}`): messages; check list in tier order with pass/fail, score, detail; source panel showing each `SpanRef` text with the cited span highlighted (offsets relative to the span text); link to the source `uri`; badges for judged and audited; for unanswerable rows show `jev.not_in_docs` detail.
   - Report screen (`report.ready` or `GET /jobs/{id}`): coverage heatgrid (final), pass rate per check bar chart, reject reasons, judge rate and agreement, cost vs frontier-only, token stats, rounds table.
   - Order: row inspector and Report screen are P0 (checkpoint 2); spot-check panel and DPO/extra-preset downloads are P1 (by T+3:30).
   - Spot-check panel (P1): walk the 50 `sample_row_ids`, thumbs up/down -> `POST /spot-check` -> update the report with the returned `Report`.
   - Export panel: preset and format pickers from `/presets`, `POST /export`, download links from `Job.files`.
   - `round` events: banner "Round 2: N thin cells, M hard cells".
5. **T+3:00-3:30:** polish animation of cell fills; performance check with 1,000+ row events.

**Definition of done:** On a real job, the heatgrid fills live; reconnecting the page resumes from replay without double counts; any kept row opens to highlighted spans and passed checks; a rejected row shows its reason; the `round` banner shows round 2; `openai-chat` and `full` downloads open (P0). By T+3:30: spot-check updates the report numbers and the DPO download opens (P1).

**Handoffs and sync points:** T+0:50 start on the live thin path; T+2:30 get a real Report JSON from A4; report any missing field to A1 through `CHANGES_REQUESTED.md`.

**Pitfalls**
- Event replay sends old events again on reconnect; de-duplicate by event id.
- A closed SSE stream is normal (Lambda ends it after 14 min); `EventSource` reconnects. Close the stream only on `done`, `error`, or `job.status cancelled`.
- In the cloud, the plan can take 30-60 s more to show (Fargate cold start). Show the `stage.progress` "starting worker" line; do not treat the wait as an error.
- `cell.update` is throttled; never compute cell totals from `row` events alone.
- Do not render 1,000 DOM rows; virtualize or cap the feed.
- No hard-coded demo numbers in charts. Empty state until data arrives.
- Color is not the only signal: show the kept/target number in the tooltip and on hover.
