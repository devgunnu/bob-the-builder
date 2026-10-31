# Bob the Builder: Agent Briefs (v4.1)

> One brief per coding agent. Copy the whole brief (from its `##` heading to the next `##`) into a fresh agent session, together with this header section. `PLAN.md` and `CONTRACTS.md` are the source of truth. If a brief and those files disagree, the files win. Tell your builder about the conflict.
>
> v4.1 = v4 + review fixes + bring-your-own AWS for Bedrock (DECISIONS D26) + Cognito auth (DECISIONS D27) + model-agnostic LLM layer (DECISIONS D33; it supersedes D22). Claude Haiku 5.5 (writer, fallback) and Claude Sonnet 5.5 (planner, judge) are only **defaults**. Any model works.

## How to use these briefs

1. Before T+0:00, Aaditya opens 5 agent sessions (A1-A5) and Gunbir opens 4 (G1-G4). Paste one brief into each session. Paste the "Shared ground rules" and the "Dependency map" with every brief. The project has 9 agents.
2. Each agent reads `CONTRACTS.md` and `PLAN.md` sections that its brief lists, before it writes code.
3. Each agent works only on its own files, on its builder's branch, and commits small.
4. At each checkpoint (T+1:30, T+2:50) the builders merge to `main`. All agents stop new work until the checkpoint passes. Checkpoint 2 passes only on the CloudFront URL (A5 deploys the merge).
5. Priorities (PLAN §8): **checkpoint 2 (T+2:50) = all P0**, including at least one gap round (round 2), Cognito sign-in, owner checks, BYO Bedrock through assume role with refresh, configurable models on Bedrock (any provider family) through Converse + registry + verify per role, and the Account screen (template download, CLI command, AWS verify, Models panel with free-text model ids). **P1** (gap round 3, DPO, extra presets and formats, extra Composio toolkits, re-sync, spot-check, Advanced options panel with per-job model override, `openai_compatible` provider with encrypted keys, model picker, CloudFormation quick-create link, self sign-up) finishes in T+3:00-3:30. The definition of done at T+3:30 (PLAN §7) = P0 + P1. Each brief marks its P1 items.

## Shared ground rules (all 9 agents)

- **One owner per file** (CONTRACTS §1). Do not edit a file that you do not own. To ask for a change in another file, add one row to the table in `.agents/CHANGES_REQUESTED.md` (columns: Time, From, To (owner), File, Request, Status), then tell your builder. The owner sets Status to `done <commit hash>`.
- **Real calls only** (CONTRACTS §0 rule 2, §12). No mocks, no stubs, no fake responses, no hard-coded rows, no placeholder corpus. Tests use real calls on `demo/smoke/` with small sizes (for example `target_rows=20`). If a key fails, fix the key or use the documented real fallback. Never fake the call.
- **Disk cache is for real responses only** (`core/cache.py`). It never invents a response. `BOB_CACHE=0` turns it off.
- **Async everywhere.** External calls go through a client with a semaphore, 3 retries with exponential backoff, the disk cache, and a cost ledger entry.
- **Thresholds come from `settings_for(job)`** (A1, `config.py`). It returns `EffectiveSettings`: the env defaults with the job's `JobSpec.options` (`JobOptions`) on top. Pipeline code reads every threshold and mode through it (`KEEP_P`, `REJECT_P`, `AUDIT_RATE`, `MAX_ROUNDS`, `OVERGEN`, `CELL_AXES`, `MAX_CELLS`, `CASE_MIX`, `DPO_MODE`, `DPO_RATE`, `NUMBERS_ALLOW_USER`, `EXTRACT_EXEMPT_ABSENT` and the others). Never read them directly from env.
- **Auth and owners** (D27). Every route needs a signed-in user, except `/ping` and `/config/public`. G1's `current_user()` dependency gives the user. A missing or bad token gives HTTP 401 `{"error": "sign in required"}`. Every job has `Job.owner_id`. `GET /jobs` lists only the user's jobs. Every `/jobs/{id}/*` route returns 404 when `owner_id` differs.
- **LLM calls are model-agnostic** (D33). Pipeline code calls `get_llm(job, role)` (A1) with a role: `writer`, `planner`, `judge` or `fallback` (the model of the Jev and Extract fallback chains; default = the writer model). Never name a vendor model in pipeline code. Prompts are model-neutral: no assistant prefill, no vendor-only tags. Each job has a snapshot `Job.models: ModelRoles`.
- **Bedrock runs in the user's AWS account** (D26). Each job has a snapshot `Job.bedrock: BedrockAccess` (role, region). All Bedrock calls use it. Bob's own keys still pay for Jev, ScaleDown, Firecrawl and Composio.
- **A job needs a verified profile.** `UserProfile.bedrock_verified_at` and `UserProfile.models_verified_at` must both be set, else `POST /jobs` gives HTTP 412: `{"error": "connect AWS first"}` when `bedrock_verified_at` is missing, `{"error": "verify models first"}` when `models_verified_at` is missing. `PUT /me/aws` clears `bedrock_verified_at`. `PUT /me/models` clears `models_verified_at`.
- **Never return a user's API key** to the client. The API shows only `api_key_set: true`.
- **Local mode needs no Cognito and no assume role.** Local defaults: `BOB_AUTH=none` (user id `local`) and `BOB_BEDROCK_AUTH=default` (default boto3 chain, `AWS_PROFILE`). The aws deploy sets `BOB_AUTH=cognito` and `BOB_BEDROCK_AUTH=assume_role`.
- **Research at first use.** Open provider questions are not pre-start checks. Each owner researches its items as its first task, with a deadline and a default until confirmed (PLAN, open questions table). The pre-start checklist keeps only accounts, API keys, Docker, Node and `cdk bootstrap`.
- **Branches:** Aaditya's agents commit to `aaditya/<agent>` (for example `aaditya/a2-read`). Gunbir's agents commit to `gunbir/<agent>`. Merge to `main` at the checkpoints only.
- **Never commit `.env`** or any key. `runs/` is gitignored.
- **Cloud-safe code** (CONTRACTS §13, DECISIONS D25). The same code runs local (`BOB_ENV=local`, the default) and on AWS (`BOB_ENV=aws`).
  - Write files only under `settings.runs_dir`. Never hard-code `runs/`. In Lambda, `/tmp/runs` is the only writable path.
  - Keep durable data only through `Store`, `Blobs` and `EventLog` (get them from `core/backends.py`). Do not keep job state in module globals or local files only.
  - Do no background work in the API process. A task that starts after the response freezes in Lambda. Long work runs in the job worker (`Runner.start`).
  - Tests for the aws backends use real AWS (DynamoDB, S3, ECS). No moto, no LocalStack (D23).
- **Dependencies:** a new Python package goes into `backend/pyproject.toml` (owner A1); a new npm package goes into `frontend/package.json` (owner G3). Request it through `CHANGES_REQUESTED.md` and add it in the same commit as the code that needs it, after the owner agrees.
- **Models change only through A1.** If `core/models.py` changes, A1 posts the diff; G3 updates `types.ts` in the same hour.
- **Shared text files:** `.env.example` = A1. Root `README.md` = A5 (setup, deploy, BYO AWS steps). Other agents send text for them through `CHANGES_REQUESTED.md`.
- Python 3.12, pydantic v2, `ruff format`. TypeScript strict, React 18, Vite.

## Dependency map (who blocks whom)

```
 T+0:15  A1 core/models.py (incl. UserProfile, BedrockAccess, ModelConfig, ModelRoles, Control,
         JobOptions) + config.py (incl. settings_for) + orchestrator.py signatures ──► ALL 8 other agents
 T+0:15  A1 protocol stubs (Blobs, Store, EventLog, Runner + local impls, backends.py, RunnerBusy,
         Runner.is_running, Store.get_user/put_user) + boto3 ──► A5 aws impls
 T+0:20  A5 BobData stack + resource names (table, buckets, secret, Cognito pool id, client id,
         domain) ──► A1 .env.example, G1 api/auth.py, G3 auth wrapper, all agents
 T+0:20  A2 clients/jev.py + clients/scaledown.py (real shapes confirmed) ──► A2 triage/evidence, A4 tier 2, A1 thin path
 T+0:20  G2 demo/smoke/*.md + demo/smoke/seeds.jsonl (real Firecrawl scrape) ──► A2, A3, A4 tests; A1 thin path
 T+0:20  A1 llm/client.py (get_llm) + llm/bedrock.py (Converse) + llm/registry.json (with A3; default
         model ids confirmed) ──► A3 Writer/Planner, A2 topic names + fallbacks, A4 judge
 T+0:20  G3 frontend/src/api/types.ts ──► G4 components
 T+0:45  G1 POST /uploads + MD parser + POST /jobs + SSE route ──► A1 thin path end to end
 T+0:45  G2 Composio toolkits + tool slugs confirmed ──► G2 composio.py, G3 connector buttons
 T+0:50  A1 THIN REAL PATH (smoke upload -> chunk -> Writer -> Jev -> rows -> SSE) ──► G1 + G4 live testing
 T+1:00  A1 llm/credentials.py (assume role + RefreshableCredentials) ──► A1 bedrock.py, A5 cloud job
 T+1:00  A2 chunk/topics/evidence/Retriever ──► A3 Planner + Writer context, A4 extract.names + numbers
 T+1:10  A3 generate() for 4 case types ──► A4 verify() on real candidates, A1 build loop
 T+1:15  A4 verify() + export openai-chat ──► A1 build loop, G4 row feed, checkpoint 1 download
 T+1:15  G2 firecrawl.py + composio.py (Notion) ──► G1 fetch_documents(), G3 connector buttons
 T+1:15  A5 CLOUD HEALTH: CloudFront URL serves the UI; /api/ping + /api/health work there ──► checkpoint 1
 T+1:30  G1 api/auth.py + /config/public + /me* routes (incl. /me/models, /me/models/verify)
         ──► G3 Account screen, checkpoint 1
 T+1:30  G3 auth wrapper (Amplify) + Account screen (/account: AWS access + Models panels)
         ──► checkpoint 1 cloud sign-in
 T+1:30  A5 bedrock-role.yaml template + fixed role names + sts:AssumeRole + KMS key
         ──► G1 /me/aws/template, demo user connect
 T+1:30  CHECKPOINT 1 (merge; local pass test + cloud health check + sign-in works on the CloudFront
         URL and /me returns the profile)
 T+2:00  A3 plan_gap_round() + A1 round 2 wiring (P0) ──► G4 round banner, checkpoint 2
 T+2:00  A5 CLOUD REAL JOB with the demo user's assume-role Bedrock access (create -> Fargate worker
         -> plan -> approve -> rows on SSE -> S3 download) ──► checkpoint 2
 T+2:30  A4 report + openai-chat/full exports (P0) ──► G4 Report screen
 T+2:30  G2 sync.py ──► A1 resync orchestration (P1)
 T+2:50  CHECKPOINT 2 (merge; all P0; pass test runs on the CloudFront URL: sign in -> Connect AWS
         (verified) -> models verified -> job -> rows -> download)
 T+3:30  FREEZE (P0 + P1 done: round 3, DPO, presets, toolkits, resync, spot-check, Advanced panel)
 T+3:30  A5 deploys the frozen main (tag `demo`) once; localhost stays the backup
```

Rule: if you are blocked, build against the contract shape with real inputs you already have (for example the smoke corpus), and connect the moment the dependency lands. Never fill the gap with fake data.

---

## A1 Core (Aaditya)

**Role:** Core platform and orchestrator owner.
**Mission:** Lock the shared models first so 8 agents can start. Then build the store, event bus, cost ledger, disk cache, the model-agnostic LLM layer (client protocol, Bedrock Converse, model registry), Bedrock credentials and the orchestrator state machine with the full build loop. You also define the backend protocols (`Blobs`, `Store`, `EventLog`, `Runner`) and their local implementations, so A5 can write the AWS implementations. You deliver the thin real path by T+0:50; all other integration hangs on it. You are the only agent that wires A2, A3 and A4 stages together.

**Read first:** CONTRACTS §0, §1, §2 (all), §3 (GenContext and all signatures), §7, §8, §9, §10, §12, §13 (backend protocols, config, single event writer). PLAN §3, §5, §6, §10. DECISIONS D25, D26, D27, D33.

**You own:** `backend/pyproject.toml`, `backend/bob/config.py`, `.env.example`, `backend/bob/core/models.py`, `core/store.py`, `core/events.py`, `core/ledger.py`, `core/cache.py`, `core/blobs.py`, `core/runner.py`, `core/backends.py`, `backend/bob/llm/client.py`, `llm/bedrock.py`, `llm/openai_compat.py` (P1), `llm/registry.py`, `llm/registry.json`, `llm/credentials.py`, `backend/bob/orchestrator.py`, your tests in `backend/tests/`.
**Do not touch:** `clients/*`, `pipeline/*`, `export/*`, `connectors/*`, `api/*` (including `api/auth.py`, G1), `frontend/*`, `demo/*`, `backend/bob/aws/*`, `backend/bob/worker.py`, `backend/Dockerfile`, `infra/*` (A5), root `README.md` (A5).

**You provide:** all models in CONTRACTS §2, including `BedrockAccess`, `ModelConfig`, `ModelRoles`, `UserProfile`, `Control`, `JobOptions`; `GenContext`; `settings_for(job) -> EffectiveSettings` in `config.py`; `Orchestrator` (all §7 methods, plus `run_job`, `get_or_create_user`, `update_bedrock`, `verify_bedrock`, `update_models`, `verify_models`, `health_job(user)` (a small system job context for G1 `/health`)); the `LLMClient` protocol in `llm/client.py` (`async def complete_json(role, system, messages, schema, cache_prefix=None) -> tuple[dict, Usage]` and `async def complete_text(...)`) and `get_llm(job, role) -> LLMClient` (publish the exact signatures in the first commit); `credentials.py`; the model registry; `cache.py` get/put; `ledger.record(job_id, bucket, *, calls=1, in_tokens=0, out_tokens=0, usd=None, model=None)` (CONTRACTS §7; this is the only form); the event bus `emit(type, data)` and `subscribe()`; the protocols `Blobs`, `Store`, `EventLog`, `Runner` (CONTRACTS §13) with local implementations, and the `RunnerBusy` exception; `get_blobs()`, `get_store()`, `get_events()`, `get_runner()` in `core/backends.py`. Consumers: everyone; A5 for the protocols; G1 for the user methods.
**You consume:** A2 stage functions, A3 `propose_plan/allocate_targets/generate/generate_flawed/plan_gap_round`, A4 `verify/build_dpo_pairs/build_report/export`, G1 `fetch_documents()` and `read_upload()`, A5 resource names (T+0:20) and `bob/aws/*` implementations.

**Research at first use** (your first tasks; use the default until you confirm):

| Item | When | Default until confirmed |
|---|---|---|
| Default Bedrock model IDs / inference profiles | first Bedrock call (T+0:20) | `global.anthropic.claude-haiku-5-5`, `global.anthropic.claude-sonnet-5-5` |
| Converse with session credentials (botocore `RefreshableCredentials` on the boto3 client) | T+1:00 | assumed-role keys + session token through `RefreshableCredentials` |
| Registry capabilities per model family (`json_mode`, `cachePoint`, `min_cache_tokens`, `allows_temperature`, `extra_fields`) | first call per family | unknown model: `prompt` JSON mode, no cache, price unknown |
| Prices (default models, Jev, ScaleDown) | T+1:30 | registry / config table values |

**Tasks**
1. **T+0:00-0:15:** Write `core/models.py` exactly as CONTRACTS §2 (call `Job.model_rebuild()` after `Report`).
   - New models: `BedrockAccess` (AWS access only: `mode`, `role_arn`, `external_id`, `region`; no model fields), `ModelConfig` (`provider: "bedrock" | "openai_compatible"`, `model_id`, `base_url`, `api_key_set` (the encrypted key is stored separately, never in this model), `json_mode: "auto" | "tool" | "native" | "prompt"`, `cache: "auto" | "off"`, `price_in_per_m`, `price_out_per_m`), `ModelRoles` (`writer`, `planner`, `judge`, `fallback: ModelConfig | None` (None = writer)), `UserProfile` (`id` = Cognito sub or `"local"`, `email`, `external_id` (uuid4, made once), `bedrock`, `bedrock_verified_at`, `models: ModelRoles` (defaults from config), `models_verified_at`, `created_at`), `Control` (`state: "approved" | "cancel" | None`, `plan: Plan | None`), `JobOptions` (every field optional; `None` = config default; includes `models: ModelRoles | None` for a per-job override).
   - Field changes: `JobSpec.options: JobOptions = JobOptions()`; `Job.owner_id: str`; `Job.bedrock: BedrockAccess | None`; `Job.models: ModelRoles` (snapshot); `Job.heartbeat_at: datetime | None = None`; `CostSummary.by_model` keys stay role names (`writer`, `judge`, `planner`, `fallback`, `jev`, `scaledown`, `firecrawl`, `composio`); add `CostSummary.model_ids: dict[str, str]` (role -> model id) and `CostSummary.price_unknown: list[str]`; `Axis.role: "cell" | "mix" = "cell"` and `Axis.weights: dict[str, float] = {}`; `Candidate.coords: dict[str, str]`; `Candidate.absent_topic` (comment: "unanswerable and partial"); `DPOPair.row_id`, `DPOPair.mode: "synthesized" | "natural"`, `DPOPair.rejected_checks: list[str]`; `Report.mix_coverage: dict[str, dict[str, int]]`; `Row.coords` (comment: "all 4 axes").
   - Add `GenContext` as a dataclass with string type hints for `EvidenceIndex` and `Retriever` (import under `TYPE_CHECKING` to avoid import cycles).
   - `config.py`: pydantic-settings for every var in §9, including the cloud vars (`BOB_ENV`, `BOB_RUNS_DIR`, `BOB_TABLE`, `BOB_BUCKET`, `BOB_SECRET_ARN`, `BOB_ECS_CLUSTER`, `BOB_TASK_DEF`, `BOB_SUBNETS`, `BOB_SECURITY_GROUP`, `BOB_CONTAINER_NAME`, `BOB_MAX_WORKERS`, `BOB_CONTROL_POLL_S`, `BOB_APPROVAL_WAIT_MINUTES`, `BOB_EVENT_POLL_MS`, `BOB_SSE_HEARTBEAT_S`, `BOB_SSE_MAX_S`, `BOB_PUBLIC_URL`, `BOB_OAUTH_CALLBACK_PATH`, `BOB_EMBED_MODEL_PATH`, `BOB_HEARTBEAT_S`, `BOB_HEARTBEAT_TIMEOUT_S`), the auth and BYO AWS vars (`BOB_AUTH`, `BOB_COGNITO_REGION`, `BOB_COGNITO_USER_POOL_ID`, `BOB_COGNITO_CLIENT_ID`, `BOB_COGNITO_DOMAIN`, `BOB_SIGNUP`, `BOB_MAX_ACTIVE_JOBS_PER_USER`, `BOB_BEDROCK_AUTH`, `BOB_ACCOUNT_ID`, `BOB_CRED_REFRESH_S`, `BOB_BEDROCK_DEFAULT_REGION`, `BOB_KMS_KEY_ID` (aws), `COMPOSIO_USER_PREFIX`), the model vars (`BOB_DEFAULT_WRITER_MODEL=bedrock:global.anthropic.claude-haiku-5-5`, `BOB_DEFAULT_PLANNER_MODEL=bedrock:global.anthropic.claude-sonnet-5-5`, `BOB_DEFAULT_JUDGE_MODEL=bedrock:global.anthropic.claude-sonnet-5-5`, `BOB_DEFAULT_FALLBACK_MODEL=` (empty = writer), format `<provider>:<model_id>`; they replace `BOB_WRITER_MODEL` / `BOB_JUDGE_MODEL` / `BOB_PLANNER_MODEL`; `BOB_MODEL_REGISTRY=bob/llm/registry.json`), and the pipeline vars (`CELL_AXES`, `MAX_CELLS`, `MAX_TOPICS`, `MIN_CELL_TARGET`, `CASE_MIX`, `EXTRACT_NAMES_CASE_TYPES`, `EXTRACT_EXEMPT_ABSENT`, `ABSENT_MATCH`, `NUMBERS_ALLOW_USER`, `DPO_MODE`, `DPO_RATE`). The default model vars are **defaults** for new profiles only.
   - `settings_for(job) -> EffectiveSettings`: start from Settings, apply each non-`None` field of `job.spec.options`. All pipeline code reads thresholds through it.
   - In aws mode, `config.py` calls A5's `bob/aws/secrets.py` to load the secret JSON into the environment before it reads Settings.
   - `pyproject.toml` (no `anthropic` package; the request path uses boto3 Converse and raw `httpx`): httpx, pydantic, pydantic-settings, fastapi, uvicorn, sse-starlette, model2vec, numpy, scikit-learn, rapidfuzz, pyarrow, pandas, firecrawl-py, composio, pypdf, python-docx, markdownify, tenacity, boto3, `pyjwt[crypto]` (for G1 `api/auth.py`).
   - Empty `orchestrator.py` with the §7 signatures, including `create_job(spec, user: UserProfile) -> Job`, `list_jobs(owner_id)`, `get_or_create_user(user_id, email) -> UserProfile`, `update_bedrock(user_id, access: BedrockAccess) -> UserProfile`, `verify_bedrock(user_id) -> dict`, `update_models(user_id, roles: ModelRoles, ...) -> UserProfile`, `verify_models(user_id) -> dict`, `health_job(user) -> Job` (a small system job context, not saved, so `/health` can call clients that need a `job`).
   - Protocol stubs (CONTRACTS §13): `core/blobs.py` (`Blobs` + `LocalBlobs`), `Store` (`get_control -> Control`, `list_jobs(owner_id: str)`, `get_user(user_id) -> UserProfile | None`, `put_user(user)`), `EventLog`, and `Runner` (`start` raises `RunnerBusy`; new `is_running(job_id) -> bool`) with local implementation stubs, and `core/backends.py` (pick by `BOB_ENV`; import `bob.aws.*` lazily).
   - **Commit and push by T+0:15.** Tell all agents. Tell A5 that the protocols are ready.
2. **T+0:15-0:20:** `llm/client.py` (`LLMClient` protocol, `get_llm(job, role)`), `llm/bedrock.py` (Converse: boto3 `bedrock-runtime` `converse` in `asyncio.to_thread`), and `llm/registry.py` + `llm/registry.json` draft, with A3. One real call on the default writer model and one on the default planner model, with `BOB_BEDROCK_AUTH=default`. This is the research item for model IDs: record the IDs that work in `.env.example` (never `.env`). At T+0:20, add A5's table, bucket, secret and Cognito names to `.env.example`.
3. **T+0:20-0:50: thin real path.** `create_job` on a `kind="upload"` spec of the smoke `.md` files (uploaded through G1 `/uploads`, user `local`) -> `fetch_documents` -> A2 `chunk_documents` -> one real Writer call on one cell -> one real Jev check -> `Row` in the store -> `row` and `counts` SSE events. Crude code is fine; real calls are required. Announce at T+0:50.
4. **T+0:50-1:30:**
   - Write `store.py`, `events.py` and `cache.py` against the protocols (CONTRACTS §13). Write the local implementation here. A5 writes the aws implementation in `bob/aws/*`.
   - `store.py` (`LocalStore`): in-memory dict plus `settings.runs_dir/<job_id>/` on disk (`job.json`, `rows.jsonl`, `events.jsonl`, `docs/`, `chunks.jsonl`). Reload jobs on start. Add `set_control(job_id, state, plan=None)` and `get_control(job_id) -> Control`. Add `get_user` / `put_user` (users on disk under `settings.runs_dir`). `list_jobs(owner_id)` returns only that user's jobs.
   - `events.py` (`LocalEventLog`): per-job sequence ids; `append` returns the seq; persist every event; `read_after(job_id, seq)`; `subscribe(job_id, last_event_id)` replays events with `id > last_event_id`, then streams live. Keep the throttle above the backend: throttle `cell.update` to 5/s per cell (coalesce, keep the last value). Throttle `cost` and `counts` to 2/s per job.
   - `runner.py` (`LocalRunner`): `start(job_id, mode)` runs `Orchestrator.run_job` in an asyncio task; raises `RunnerBusy` when `BOB_MAX_WORKERS` tasks run or the user already has `BOB_MAX_ACTIVE_JOBS_PER_USER` (1) active jobs; `stop(job_id)` cancels it; `is_running(job_id)` = the task exists and is not done.
   - `llm/credentials.py` (**by T+1:00**): from a `BedrockAccess` make credentials. `mode="default"`: default boto3 chain (local dev, `AWS_PROFILE`). `mode="assume_role"`: STS AssumeRole with the external id, session name `bob-<job_id>`, wrapped in botocore `RefreshableCredentials` that refresh `BOB_CRED_REFRESH_S` (300 s) before expiry. `bedrock.py` builds the boto3 `bedrock-runtime` client in the job's `BedrockAccess.region` with these credentials, and takes the model id from the role's `ModelConfig` in `Job.models`. No Anthropic SDK in the request path.
   - `llm/registry.py` + `llm/registry.json`: capabilities per model id prefix. `json_mode`: `tool` = Converse `toolConfig` with a forced tool whose `inputSchema` is the JSON schema; `native` = `response_format` json_schema; `prompt` = strict JSON instruction + parse + one retry. `cache` support (Converse `cachePoint` for Claude and Nova), `min_cache_tokens`, `allows_temperature` (Claude 5.5: no), `extra_fields` (Converse `additionalModelRequestFields`, for example a low thinking effort for the writer), default prices. Unknown models get safe defaults: `prompt` JSON mode, no cache, price unknown. `ModelConfig.json_mode` / `cache` = `auto` reads the registry; other values override it. JSON parse failure -> retry once -> drop.
   - `get_llm(job, role)`: pick `Job.models.<role>` (`fallback` = writer when `None`); return the Bedrock client, or the `openai_compatible` client (P1).
   - `llm/openai_compat.py` (P1): raw `httpx` to any OpenAI-compatible chat completions endpoint (`base_url` + the user's API key). The API encrypts the key with the KMS key `BOB_KMS_KEY_ID` (A5, `alias/bob-user-keys`) and stores it in the user's PROFILE item. Only the API role and the worker role can decrypt it.
   - `ledger.py`: prices per model id from the `ModelConfig` override, else the registry, else the config table; per-bucket `ModelCost` (buckets = role names: `writer`, `judge`, `planner`, `fallback`, `jev`, `scaledown`, `firecrawl`, `composio`), `total_usd`. Fill `CostSummary.model_ids` (role -> model id) and `CostSummary.price_unknown` (roles with no known price). The only call form is `record(job_id, bucket, *, calls=1, in_tokens=0, out_tokens=0, usd=None, model=None)`. Mark Bedrock buckets as "billed to your AWS account". `frontier_only_estimate_usd` = for every Writer and verify call, the same token counts priced at the **judge role** model price (whatever model it is). Use real token counts from responses; count thinking tokens as output. The budget guard covers all buckets.
   - `cache.py`: key = sha256(endpoint, model, canonical JSON body); store response JSON through `Blobs` under `cache/<sha256>.json`; skip when `BOB_CACHE=0`.
   - User methods: `get_or_create_user(user_id, email)` makes a `UserProfile` with a random `external_id` (uuid4) and default `models` from config on first sign-in; it never changes `external_id`. `update_bedrock(user_id, access)` saves the access and clears `bedrock_verified_at`. `verify_bedrock(user_id)`: AssumeRole only, in < 25 s; return the exact STS error on failure; set `bedrock_verified_at` on success. `update_models` (for `PUT /me/models`): save the `ModelRoles` (and P1 encrypted keys) and clear `models_verified_at`. `verify_models` (for `POST /me/models/verify`): one tiny real call per configured role (all providers) that checks the JSON output, in < 25 s; return `{ok, roles: {writer: "ok"/error, ...}}` with the exact error (for example "model access not enabled in us-east-1", or the AccessDenied text for a marketplace model); set `models_verified_at` on success.
   - `create_job(spec, user)`: (1) if `bedrock_verified_at` is not set, raise the 412 error `{"error": "connect AWS first"}`; else if `models_verified_at` is not set, raise the 412 error `{"error": "verify models first"}`; (2) check capacity **before** you save the job; on `RunnerBusy` the route returns 429 `{"error": "too many running jobs"}` and nothing is saved; (3) set `Job.owner_id = user.id`, copy a snapshot `Job.bedrock` from the profile, and copy a snapshot `Job.models` = `JobOptions.models` if set, else `UserProfile.models` (later profile edits do not change a running job); (4) save Job + append `job.status created` + `runner.start(job_id, "create")`; return at once (< 1 s). In local mode (`BOB_BEDROCK_AUTH=default`), the `local` user gets a default `BedrockAccess` and default `models` from config. Run `verify_bedrock` and `verify_models` once for `local` (real calls on the default chain) before the first local job.
   - `run_job(job_id, mode)`: the whole job body. Both runners call it. Write `Job.heartbeat_at` every `BOB_HEARTBEAT_S` (10 s) for the whole run, also while it waits for approval.
   - Orchestrator pipeline in `run_job`: ingest (progress -> `stage.progress` fetch) -> read (A2 stages, each with `stage.progress`) -> plan (A3) -> `plan.ready` -> `awaiting_approval`. Then wait for approval: poll `store.get_control` every `BOB_CONTROL_POLL_S` (1 s), up to `BOB_APPROVAL_WAIT_MINUTES` (60). On `Control.state == "approved"`, use `Control.plan` (the approved plan from the user), not the proposed plan.
   - Control flag flow: `approve_plan` = `store.set_control(job_id, "approved", plan)`, then return the Job. `cancel` = `set_control(job_id, "cancel")`; if `runner.is_running(job_id)` is false, set status `cancelled` and emit the event. `run_job` checks the flag for `cancel` between stages and before each Writer call.
   - Watchdog in `get_job` and in `subscribe`: if status is not terminal (`done`, `error`, `cancelled`) and `now - heartbeat_at > BOB_HEARTBEAT_TIMEOUT_S` (90 s; before the first heartbeat use `created_at`) and `runner.is_running()` is false: set status `error`, `Job.error = "worker stopped: <stoppedReason>"`, append one `error` event. Use a conditional update (status unchanged), so two API instances do not both write.
   - `get_job`, `list_jobs`, `list_rows`, `get_row` become `async` (they read DynamoDB and S3 in aws mode). Tell G1 at once (CONTRACTS §7 signatures change).
   - After approval: `allocate_targets`, then round 1 with `asyncio.Semaphore(WRITER_CONCURRENCY)` per cell: `generate(cell, plan, ctx, ceil(target*OVERGEN))` in batches of `WRITER_BATCH` -> `verify` -> store -> update cell counters -> emit `row`, `cell.update`, `counts`, `cost`.
   - **Budget guard:** before each Writer call, stop if `cost.total_usd >= 0.95 * budget_usd`; emit `log` and move on to report.
   - Seeds: parse `seed_upload_id` (JSONL of `{messages}` or CSV `user,assistant`) into `list[list[Message]]`. Use G1's `await read_upload(upload_id)` helper (it returns `list[tuple[name, bytes]]`).
   - Single event writer: the API appends events only in `create_job`, in `cancel` when no worker runs, and in the watchdog (also no worker runs). The worker reads `last_seq` at start and is the only writer while it runs.
5. **T+1:30 checkpoint 1.** Run the pass test with Gunbir in the browser. Confirm prices in the ledger table (research item).
6. **T+1:40-2:50:** round 2 with `plan_gap_round()` is **P0** (must run at checkpoint 2); round 3 (up to MAX_ROUNDS) is P1. Emit `round` events; stop when targets met, budget hit or MAX_ROUNDS. Then `await build_dpo_pairs(rows, ctx)` (after the build loop, before report; the budget guard applies; skip when `DPO_MODE=off`) -> `build_report` -> `export(spec.preset, spec.formats)` -> set `Job.files` from the return value of `export()` (keys are paths relative to the job export folder, for example `openai-chat/train/train.jsonl`) -> `blobs.upload_tree(runs_dir/<job_id>/export, "runs/<job_id>/export")` (a no-op copy in local mode) -> `report.ready`, `files.ready`, `done`. `cancel()` sets the control flag; `run_job` stops at the next check and sets `cancelled` (the aws runner calls `stop()` after 10 s if the task still runs). Any stage exception sets `error`, emits `error` with the provider message, and never hangs. `spot_check()` updates the row and returns a rebuilt `Report`. Tune concurrency so 500 rows finish in under 10 minutes (watch Bedrock throttling in the user's account). `resync()` per CONTRACTS §10 using G2 `sync.py` (P1).
7. **T+3:00-3:30:** fix checkpoint 2 bugs; run a full fresh job; profile slow stages.

**Definition of done:** P0 at T+2:50: a real job on `demo/corpus/` goes `created -> ... -> done` with 500+ kept rows and at least one gap round; in aws mode the job's Bedrock calls run through Converse with assume role and refresh; a job runs with a non-Anthropic Bedrock model in one role (for example Amazon Nova as writer) through the registry; a job without verified AWS access or verified models gets 412; a second active job of the same user gets 429 and nothing is saved; a killed worker ends in `error` through the watchdog, not a hang. P1 by T+3:30: round 3, resync, spot-check. Also: all §8 events in the event log, replay from any `Last-Event-ID` works, ledger total matches the sum of real call costs, budget guard stops a job with `budget_usd=0.2`, cancel stops within 5 s, a forced provider error ends in `error` or a fallback `log`, not a hang.

**Handoffs and sync points:** T+0:15 models (incl. `UserProfile`, `BedrockAccess`, `ModelConfig`, `ModelRoles`, `Control`, `JobOptions`) and `settings_for` to all; T+0:15 protocol stubs (incl. `RunnerBusy`, `is_running`, `get_user`/`put_user`), config vars and `boto3` to A5; T+0:20 `get_llm(job, role)` and `LLMClient` signatures to A2/A3/A4; T+0:20 A5 resource and Cognito names into `.env.example`; T+0:50 thin path to G1/G4; T+1:00 `credentials.py` to A5 for the cloud job; user methods and async getter signatures to G1 as soon as they change; T+1:30 and T+2:50 merges; any model change -> post diff to G3 at once.

**Pitfalls**
- Research the default Bedrock model IDs at the first Bedrock call (T+0:20), not before T+0:00. Record them in `.env.example` and `registry.json`.
- Role chaining limits an assumed-role session to 1 h, and a job can wait 60 min for approval. Use `RefreshableCredentials` that refresh `BOB_CRED_REFRESH_S` (300 s) before expiry. Never keep a client with fixed old credentials.
- AssumeRole can fail (wrong external id, trust policy, role name), or model access may be off in the user's region. The verify methods must return the exact STS or model error, and name the model and the region.
- Put model rules in the registry, not in code paths. Registry rules: Claude 5.5 has `allows_temperature: false` (it rejects non-default `temperature`/`top_p`/`top_k`); send `cachePoint` only where the registry says the model supports it (Claude, Nova), and only above `min_cache_tokens`; pick the JSON mode per model (`tool`, `native` or `prompt` + one retry); put a low thinking effort for the Claude writer in `extra_fields` (thinking is billed as output; confirm cost in the ledger).
- A model can lack forced tool use or JSON output. Fall back to `prompt` JSON mode + one retry; the models verify call checks the JSON output per role.
- Prompt caching only works above the model minimum prefix length. Check the Converse usage for cache read tokens > 0 on the second call. The plan estimate must use the registry `cache` value, so a model with no cache shows the higher cost.
- No assistant prefill and no vendor-only tags in any prompt. Prompts must work on any model.
- An unknown model has no price. Put its role in `CostSummary.price_unknown`; never guess a price.
- Do not block the event loop: run model2vec and k-means in `asyncio.to_thread`.
- Do not let a single cell failure kill the job; log and continue.
- Do not change a protocol signature after T+0:15 without A5. A5 codes the aws implementations against it.
- Keep the in-memory read state (chunks, embeddings, `EvidenceIndex`, `Retriever`) inside `run_job`. The worker task lives across plan approval, so do not serialize these objects.
- Do not append events from the API while a worker runs. Two writers collide on the same seq (the aws EVT put is conditional and fails loudly). The watchdog writes only when `is_running()` is false.
- Never write outside `settings.runs_dir`. Lambda has a read-only disk except `/tmp`.
- `core/backends.py` must import `bob.aws.*` lazily. Local mode must run without AWS credentials for Bob's backends.
- Do not read thresholds from env in pipeline code. Use `settings_for(job)`, so per-job options work.

---

## A2 Read (Aaditya)

**Role:** Reading pipeline and decision-model clients owner.
**Mission:** Build the Jev and ScaleDown clients with real calls and real fallbacks, then turn documents into clean chunks, topics with briefs, an evidence index with verbatim spans, and a retriever. Your evidence index is the ground truth that verification checks against, so span accuracy matters more than speed.

**Read first:** CONTRACTS §0, §2 (Document, Chunk, Evidence, Topic, CostSummary), §3 (A2 block), §4 (Jev questions and failure modes), §5 (all), §9, §12. PLAN §3, §4, §11. DECISIONS D33.

**You own:** `backend/bob/clients/jev.py`, `clients/scaledown.py`, `backend/bob/pipeline/chunk.py`, `filters.py`, `embed.py`, `triage.py`, `topics.py`, `evidence.py`, your tests.
**Do not touch:** `core/*`, `llm/*`, `orchestrator.py`, other `pipeline/*` files, `connectors/*`, `api/*`, `frontend/*`.

**You provide:** `decide()`, `Question`, `Decision`; `extract/summarize/classify/compress`. All 5 client functions (`decide`, `extract`, `summarize`, `classify`, `compress`) take a keyword-only `job: Job` parameter; they use it for `get_llm(job, "fallback")` and `ledger.record(job.id, ...)`. Also `chunk_documents`, `heuristic_filter`, `embed`, `dedup_chunks`, `triage`, `build_topics`, `build_evidence`, `EvidenceIndex`, `Retriever`. Consumers: A1 (orchestrator), A3 (topics, retriever, compress), A4 (Jev, Extract, evidence, embed for dedup), G1 (`/health` calls a tiny `decide` and `classify` with the job from A1 `health_job(user)`).
**You consume:** A1 `cache`, `ledger`, `get_llm(job, role)` (topic names; the `fallback` role for the Jev and Extract fallbacks), `settings_for(job)`, `models.py`; G2 `demo/smoke/`.

**Research at first use** (your first tasks; use the default until you confirm):

| Item | When | Default until confirmed |
|---|---|---|
| Jev request/response shape, model version | T+0:20 | CONTRACTS §5 shape, `jev-1.13` |
| ScaleDown endpoint + Extract schema format | T+0:20 | `api.scaledown.xyz` |

**Tasks**
1. **T+0:00-0:20 (research tasks):** `clients/jev.py` with raw `httpx` to OpenRouter `POST /api/alpha/decisions`, model from `JEV_MODEL` (default `jev-1.13`; check whether a newer version exists). Send one real call with one Noul, one Choice and one Score question. Print the raw response. Write the confirmed request and response shapes into CONTRACTS §5 only after Aaditya agrees (contract change rule). `clients/scaledown.py`: one real call each to Extract, Summarize, Classify, Compress; confirm the base URL (default `api.scaledown.xyz`; else OpenRouter) and the Extract schema format. Semaphores from config, 3 retries, cache, ledger bucket `jev` / `scaledown` with `purpose` tag. Every client function takes keyword-only `job: Job`. Your own stages pass it on every call. Commit by T+0:20.
2. **T+0:20-1:30:**
   - `chunk.py`: split on markdown headings first, then paragraphs; pack to 300-500 tokens (count with a fast estimate, words x 1.3, or a tokenizer); never split inside a code block or table; keep `heading` path; `start`/`end` are char offsets in `Document.text` so `text == doc.text[start:end]` always holds (assert it). `id = sha1(doc_id + str(start))[:12]`.
   - `filters.py`: drop chunks with high link or nav density (`nav_density`), under 40 words, cookie and footer text. Set `kept=False` and `drop_reason`; never delete.
   - `embed.py`: model2vec `minishlab/potion-base-8M`, load once, CPU, normalized vectors. When `BOB_EMBED_MODEL_PATH` is set, load the model from that path (the image bakes it in; no Hugging Face download at runtime). `dedup_chunks`: exact hash, then cosine > 0.95 -> `drop_reason="duplicate"`.
   - `triage.py`: one `decide()` per kept chunk with 4 Noul questions (useful for the goal, boilerplate, contains PII, contains prompt injection). Store probabilities in `Chunk.triage`. Drop with `jev:boilerplate`, `jev:pii`, `jev:injection` above thresholds in config.
   - `topics.py`: k-means on kept chunk embeddings with `k = clamp(round(sqrt(n)), 4, MAX_TOPICS)` (`MAX_TOPICS` = 20; fewer if n is small); one `get_llm(job, "writer")` call per cluster for name + one-line description, given 3 sample chunks and the goal; ScaleDown Summarize per topic for `brief` (<= 1,000 tokens). Set `Chunk.topic_id`.
   - `evidence.py`: ScaleDown Extract per kept chunk with the evidence schema from CONTRACTS §5. Validate each field: `span_text` must be a verbatim substring of the chunk; recompute `start`/`end` as document offsets (`chunk.start + chunk.text.find(span_text)`); drop the field if not found. `EvidenceIndex.find()` normalizes (lowercase, strip punctuation, singularize simply) then rapidfuzz `token_set_ratio >= 90`. `Retriever`: embedding cosine top-k, optional topic filter (add BM25 only if time permits).
   - Test everything on `demo/smoke/` with real calls; print counts and 5 sample evidence items with spans.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:** fallback chains. Jev: after 3 failures in a row, Noul and Choice go to ScaleDown Classify (labels = descriptive options, `yes`/`no` for Noul), then to fallback model JSON (`get_llm(job, "fallback")`); Score has no Classify equivalent, so it goes directly to fallback model JSON. Extract fallback: fallback model extraction with the same schema and the same verbatim check. Each switch appends to `CostSummary.fallbacks_used` (for example `jev->scaledown_classify`) and emits a `log` event. Test by forcing a failure (bad model name through an env override), with real fallback calls. Run the full `demo/corpus/`; read 20 dropped chunks and 20 evidence items; tune thresholds.
5. **T+3:00-3:30:** fix bugs; speed up evidence with batching under the semaphore.

**Definition of done:** On `demo/corpus/`, every stage runs with real calls; every `Evidence.span_text == doc.text[start:end]`; `Retriever.top_k` returns relevant chunks for 5 hand-written queries; topics have readable names and briefs; a forced Jev failure produces real Classify answers and a `fallbacks_used` entry.

**Handoffs and sync points:** T+0:20 confirmed client shapes (or "default kept") to A4 and A1; T+1:00 topics, evidence and retriever to A3 and A4; tell G1 the cheapest real call for `/health`.

**Pitfalls**
- Jev follows option names. Use descriptive option names only (never `0/1`, `A/B`).
- Do not send `temperature` or `max_tokens` to Jev. No OpenAI SDK.
- Jev gives calibrated probabilities, no text. Do not ask it for explanations.
- Extract schema is guidance only. Validate types and verbatim spans in code.
- Offsets drift if you normalize whitespace after chunking. Chunk the final `Document.text` only.
- Keep the 4 triage questions in one call to save cost.
- Do not hard-code the model download in `embed.py`. In Lambda only `/tmp` is writable, so the cloud image must use `BOB_EMBED_MODEL_PATH`.
- Never name a vendor model in your code. Call `get_llm(job, role)`. The fallback model runs in the user's account (or the user's endpoint); never call an LLM with Bob's own credentials in aws mode.
- Keep fallback prompts model-neutral (no prefill, no vendor-only tags). The fallback model can be any model.
- Do not drop the `job` keyword in a client signature. Without it, the fallback cannot find the job's models and the ledger cannot charge the job.

---

## A3 Plan + Write (Aaditya)

**Role:** Planner, Writer and gap controller owner.
**Mission:** Turn topics and the goal into a coverage map the user can edit, then write diverse, grounded candidates for every cell and case type, and steer later rounds to thin and hard cells. The Writer must produce rows that pass verification on the first try as often as possible.

**Read first:** CONTRACTS §0, §2 (Topic, Axis, Cell, Plan, Candidate, Message), §3 (A3 block, GenContext), §4 (so your rows pass), §9 (`OVERGEN`, `WRITER_BATCH`, `CELL_AXES`, `MAX_CELLS`, `MAX_TOPICS`, `MIN_CELL_TARGET`, `CASE_MIX`, `DPO_RATE`, caching note). PLAN §2, §4, §8, §9, §10, §11. DECISIONS D33.

**You own:** `backend/bob/pipeline/planner.py`, `generate.py` (including `generate_flawed()`), `gaps.py`, `backend/bob/pipeline/prompts/planner.md`, `prompts/writer*.md` (including `prompts/writer_flawed.md`), your tests.
**Do not touch:** `prompts/judge.md` (A4), `llm/*` (A1; request changes), all other files.

**You provide:** `propose_plan`, `allocate_targets`, `generate`, `generate_flawed(row, ctx) -> Candidate`, `plan_gap_round`. Consumers: A1 (orchestrator), A4 (candidates, flawed candidates for DPO), G3 (Plan shape and notes in the UI).
**You consume:** A1 `get_llm(job, role)` (roles `planner` and `writer`), `GenContext`, `settings_for(job)`, ledger; A2 topics, `Retriever`, `EvidenceIndex`, `compress(..., job=job)` (pass the keyword-only `job`); G2 `demo/smoke/` and `seeds.jsonl`.

**Map shape (v4.1):** cells = `CELL_AXES` (default `topic,case_type`). The other axes (`persona`, `difficulty`) are **mix axes** (`Axis.role = "mix"`, `Axis.weights` = share of rows per value). `Cell.coords` has only the `CELL_AXES` keys. `Candidate.coords` and `Row.coords` carry all 4 axis values. Demo numbers: 12 topics x 4 case types = 48 cells; 4 personas and 3 difficulty levels mixed in each cell; 1,000 rows -> about 20 per cell.

**Tasks**
1. **T+0:00-0:20:** With A1, get one real call through `get_llm(job, "writer")` (default writer model). Write `prompts/writer.md` v1 and test it on one real smoke chunk as soon as G2 lands `demo/smoke/`.
2. **T+0:20-1:30:**
   - `planner.py`: one `get_llm(job, "planner")` call (planner model, default Sonnet 5.5) with goal, topic names + descriptions + brief excerpts, seed summary, target rows and budget. Output JSON: `system_prompt`, axes (`topic` from real topics, 3-5 `persona` values with descriptions, `case_type` = CASE_TYPES, `difficulty` = DIFFICULTIES), `notes`. Code sets `Axis.role` from `CELL_AXES` (cell axes) and gives each mix axis default `weights` (equal shares unless the Planner proposes others). Code builds the cross product of the cell axes only (`id = sha1(sorted coords)[:10]`) and computes seed coverage notes from real seeds (for example "Your seeds cover 4 of 14 topics"). Keep at most `MAX_TOPICS` (20) topics. Merge the smallest topics until enabled cells <= `MAX_CELLS` (120). `multi_doc` is a mix value now: do not pick it for a topic with chunks from one doc. `est_cost_usd` = cells x expected calls x real token averages x prices of the job's models (registry or override; use the registry `cache` value, so a model with no cache shows the higher cost).
   - `allocate_targets`: split `target_rows` across enabled cells by `weight`; case-type mix from `CASE_MIX` (default `answerable:0.5,partial:0.15,unanswerable:0.2,false_premise:0.15`; no hard-coded mix); minimum `MIN_CELL_TARGET` (3) per enabled cell; integer rounding with remainder to the largest cells. Read all values through `settings_for(job)`.
   - `generate.py`: per call ask for `WRITER_BATCH` (5) **different** candidates as JSON `{"rows": [...]}`. Each batch of 5 rotates the mix values (persona, difficulty) by their weights. Each `Candidate.coords` records all 4 axis values. Context: topic brief + top-k retrieved chunks for the cell (multi_doc rows: chunks from at least 2 docs), shrunk with ScaleDown Compress; keep chunk ids in the prompt so the Writer cites them. Prompt caching: system prompt + topic brief form the stable prefix (cache breakpoint after them); the cell- and mix-specific part goes after. Persona and difficulty conditioning: describe the persona (role, vocabulary, what they care about) and the difficulty (`single_fact` = one fact; `multi_step` = a procedure or two linked facts; `multi_doc` = facts from two docs) per row in the batch. Ask for varied openings, lengths and tones; include 2 real seeds as style examples when present.
   - Case-type prompts (`writer_answerable.md`, `writer_partial.md`, `writer_unanswerable.md`, `writer_false_premise.md`):
     - **answerable:** the question is fully answered by the passages; the reply uses only passage facts, no "according to the document".
     - **partial:** half of the question is in the passages, half is not; the reply answers the covered part, names the uncovered part, offers a human handoff. The Writer must fill `absent_topic` with the uncovered part.
     - **unanswerable:** the question is on-topic and plausible but not covered; the Writer must fill `absent_topic` (what is missing); the reply says the docs do not cover it and offers a handoff, with no invented details. Code checks with `Retriever.top_k(absent_topic)` that the absent topic is not obviously present.
     - **false_premise:** pick one real Evidence item (setting, limit, number); the user assumes a wrong value; set `premise_evidence_id` to that item; the reply corrects it politely with the real value.
   - Parse JSON; on failure retry once, then drop. Each `Candidate` carries `chunk_ids`, `coords`, `writer_model`, real `cost_usd`.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:**
   - `gaps.py` `plan_gap_round` (**P0**: round 2 must run at checkpoint 2; round 3 is P1). Deliver to A1 by T+2:00. For each enabled cell, `deficit = target - kept`; skip if `deficit <= 0`; `n = ceil(deficit * OVERGEN)`; if the cell rejection rate `rejected / generated > 0.5`, multiply `weight` by 1.5 and `n` by 1.5 (hard cell) and switch to a stricter prompt variant; also boost under-covered mix values (deficit vs weight) inside the cell's next batches; cap the total of `n` across cells so the estimated cost fits in the remaining budget (`0.95 * budget - total_usd`), scaling all cells down proportionally. Return `(cell, n)` sorted by deficit. At T+2:00 read 50 real kept rows across personas and difficulties; fix repeated openings, sameness and leaks; re-run.
   - `generate_flawed(row, ctx) -> Candidate` (P1, for A4 DPO `synthesize` mode): ask the Writer for one flawed reply to the SAME user turn, by case type: answerable = add one plausible detail that is not in the passages; partial = also answer the uncovered part with invented details; unanswerable = answer confidently instead of abstaining; false_premise = accept the wrong premise. Prompt file `prompts/writer_flawed.md`. Batch 5 flawed replies per call, prompt-cached, ledger bucket `writer`, purpose `dpo`.
5. **T+3:00-3:30:** prompt tuning on reject reasons from the report; multi-turn rows only if all else is green (stretch).

**Definition of done:** `propose_plan` on smoke and on the full corpus returns a valid `Plan` (cells = topic x case_type, enabled cells <= `MAX_CELLS`) that the UI renders; `generate` returns 5 parsed, distinct candidates for each of the 4 case types with real calls, with mix values rotated and all 4 coords set; every unanswerable and partial row has `absent_topic`, every false_premise row has a valid `premise_evidence_id`; cache reads are visible in usage on repeated cell calls; a gap round targets only thin and high-reject cells and boosts under-covered mix values; P1: `generate_flawed` returns flawed twins for all 4 case types.

**Handoffs and sync points:** T+1:00 Plan shape to G3 (sample real plan JSON in a run folder, with mix axes and weights); T+1:10 `generate` to A1 and A4; T+2:00 report the 50-row read to Aaditya; `generate_flawed` to A4 when DPO work starts.

**Pitfalls**
- Never name a vendor model in your code; call `get_llm(job, role)`. Keep all prompts model-neutral: no assistant prefill, no vendor-only tags. They must work on any model.
- Do not rely on `temperature` (the registry blocks it for Claude 5.5 and other models). Diversity comes from the prompt: persona, difficulty, "5 different rows", varied openers, and seeds.
- Any change in the cached prefix (timestamps, random order) kills the cache. Keep it byte-stable. Put the mix values after the cache breakpoint.
- Do not let the Writer copy passage sentences into the user turn; that fails `jev.realistic`.
- Do not put numbers in replies that are not in the passages; tier-1 `numbers` rejects them (numbers from the user turn are allowed only per `NUMBERS_ALLOW_USER`).
- The Planner must use real topic names from A2, not invent topics. Merged topics keep real names.
- A missing `absent_topic` on a partial or unanswerable row makes `extract.names` reject a correct reply. Always fill it.
- Do not build cells over persona or difficulty. With 576 cells, coverage 100% is not reachable.

---

## A4 Verify + Ship (Aaditya)

**Role:** Verification cascade, report and export owner.
**Mission:** Decide which rows are kept, with proof. Implement the exact 3-tier cascade, routing and judge, then build DPO pairs, the data quality report and every export preset and format. Verification and the row inspector data are the product; never cut them.

**Read first:** CONTRACTS §0, §2 (Candidate, CheckResult, SpanRef, Row, DPOPair, Report), §3 (A4 block), §4 (all), §9 (thresholds, judge model, `EXTRACT_NAMES_CASE_TYPES`, `EXTRACT_EXEMPT_ABSENT`, `ABSENT_MATCH`, `NUMBERS_ALLOW_USER`, `DPO_MODE`, `DPO_RATE`), §11, §12. PLAN §2 steps 3-5, §4, §7, §9 steps 4-7. DECISIONS D33.

**You own:** `backend/bob/pipeline/verify.py`, `report.py`, `probe.py` (stretch), `backend/bob/pipeline/prompts/judge.md`, `backend/bob/export/presets.py`, `formats.py`, `manifest.py`, your tests.
**Do not touch:** writer and planner prompts, clients, core, all Gunbir files.

**You provide:** `verify`, `async def build_dpo_pairs(rows: list[Row], ctx: GenContext) -> list[DPOPair]`, `build_report`, `export` (it returns the file keys for `Job.files`); preset list for G1 `/presets`. Consumers: A1, G4 (Row, Report shapes), G1 (file paths).
**You consume:** A2 `decide`, `extract` (pass the keyword-only `job: Job` on every call), `EvidenceIndex`, `Retriever`, `embed`; A1 `get_llm(job, "judge")` (judge model, default Sonnet 5.5), `GenContext`, `settings_for(job)`, ledger; A3 candidates and `generate_flawed`.

**Tasks**
1. **T+0:00-0:20:** write `prompts/judge.md` (input: passages, case type, row, tier-2 results; output JSON `{"verdict": "keep"|"reject", "reason": "..."}`; strict rules per case type; model-neutral: no prefill, no vendor-only tags). Write preset functions in `presets.py` as pure code from CONTRACTS §11.
2. **T+0:20-1:30:** `verify.py`, per candidate, in this order, stop at the first hard fail. Read every threshold and mode through `settings_for(job)`.
   - Tier 1: `format`, `banned_phrases`, `dedup` (normalized user-turn hash, then embedding cosine > `DEDUP_COS` against kept rows in the same cell), `numbers` (every number in the reply appears in cited chunks or evidence values; numbers that appear in the USER turn are also allowed per `NUMBERS_ALLOW_USER`: `all` (default) | `false_premise` | `none`). Each check produces a `CheckResult` with a readable `detail`.
   - Tier 2: `extract.names`, only for case types in `EXTRACT_NAMES_CASE_TYPES` (default all 4). Extract on the reply with `{features[], settings[], urls[], limits[]}`; each name must match `EvidenceIndex.find()`; detail `"Mentions 'X', which is not in the docs"`. Exemption (`EXTRACT_EXEMPT_ABSENT=true`): for unanswerable and partial only, a name is exempt when rapidfuzz `token_set_ratio(name, absent_topic) >= ABSENT_MATCH` (85); list exempt names in the detail ("Exempt: 'bulk PDF export' is the absent topic"). Never exempt names for answerable or false_premise. Then one `decide()` call with exactly 5 questions: the 3 shared ones (`jev.cell` Choice, `jev.quality` Score, `jev.realistic` Noul) plus the 2 for the case type from the §4 table. `state` = `PASSAGES:` + `USER:` + `ASSISTANT:` labelled blocks. For unanswerable, passages = `Retriever.top_k(user, 5)`; for false_premise, the passage holding `premise_evidence_id`; else the cited chunks.
   - Pass rules come from the §4 table. `jev.not_in_docs` passes when `p <= 1 - KEEP_P` (0.1).
   - `confidence` = minimum **pass-direction** probability over the 2 case-type Noul checks only (not `jev.realistic`): `p` for checks that pass on yes, `1 - p` for `jev.not_in_docs`.
   - Routing (CONTRACTS §4): (1) any hard fail (tier 1, `extract.names`) -> rejected; (2) else `confidence < REJECT_P` -> rejected; (3) else all Jev checks pass -> kept; (4) else (any soft Jev fail, including `jev.cell`, `jev.quality`, `jev.realistic`) -> tier 3. Send a random `AUDIT_RATE` of kept rows to tier 3 with `audited=True`. Judge concurrency from config; judge verdict is final.
   - Build `spans` from cited chunks and matched evidence (`SpanRef` with doc offsets); `reject_reason` = first failing check detail. Copy `Candidate.coords` (all 4 axes) to `Row.coords`.
   - `export` for `openai-chat` in JSONL and Parquet (system prompt from `Plan.system_prompt` added at export), path `settings.runs_dir/<job_id>/export/<preset>/<split>/<split>.<ext>` (one data file per folder). Never hard-code `runs/`. `export()` returns the file keys as paths relative to the job export folder, the same as the disk path (for example `openai-chat/train/train.jsonl`). A1 sets `Job.files` from that return value and uploads the export tree to S3.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:** First the P0 items: full `build_report`, and `openai-chat` + `full` in JSONL and Parquet with manifest and provenance. Then the P1 items (finish by T+3:30): DPO pairs, other presets and formats, spot-check accuracy.
   - `build_dpo_pairs(rows, ctx)` by `DPO_MODE`:
     - `synthesize` (default): sample `DPO_RATE` (0.3) of kept rows; call A3 `generate_flawed(row, ctx)`; run the flawed candidate through tier 1 + tier 2 only (no judge). Keep the pair only if the flawed reply is **rejected by a content check** (not `format` or `dedup`); else drop it. Pair fields: `row_id`, `mode="synthesized"`, `rejected_checks` (the failing check names).
     - `pair`: the old natural pairing; within a cell, pair a kept reply with a rejected reply to the same normalized user turn (rejected for a content reason, not `format` or `dedup`); `mode="natural"`.
     - `off`: return `[]`.
   - `build_report`: coverage per cell, plus `mix_coverage` (kept rows per persona value and per difficulty value, from `Row.coords`), pass rate per check, reject reasons by check name, duplicates removed, judge rate, judge agreement (tier-2 route vs judge verdict on routed + audited rows), 50 sample row ids stratified by cell, token stats, rounds; spot-check `jev_accuracy` = share of thumbs-up on kept rows (optionally show a Wilson 95% interval in `spot_check`).
   - All presets and formats (`jsonl`, `json`, `csv`, `parquet`); stratified 95/5 train/eval split by cell (cells with 1 row go to train); one data file per folder: `settings.runs_dir/<job_id>/export/<preset>/<split>/<split>.<ext>` (for example `export/openai-chat/train/train.jsonl`, key `openai-chat/train/train.jsonl`); `bob_manifest.json` (job, plan, counts, cost, checks, the model id per role from `Job.models`, the effective settings from `settings_for(job)`, created_at) and `provenance.parquet`.
5. **T+3:00-3:30:** stretch `probe.py` (ask the base model each kept question, mark cells where it fails, feed to the gap controller) only if checkpoint 2 is green.

**Definition of done:** On real smoke candidates, each case type yields kept and rejected rows with correct `CheckResult` lists; a hand-made candidate (written by you as a test input, sent through real calls) that mentions an invented feature fails `extract.names`; a correct unanswerable reply that names the absent topic passes `extract.names` with an "Exempt" detail; a correct false-premise reply that repeats the user's wrong number passes `numbers`; routing sends 3-15% to the judge; P0: `openai-chat` and `full` in JSONL + Parquet open in pandas at T+2:50, and the manifest lists the effective settings; P1 by T+3:30: all 7 presets x required formats open, DPO file non-empty on a real job with `mode` and `rejected_checks` set on every pair; report numbers (incl. `mix_coverage`) match a recount from `rows.jsonl`.

**Handoffs and sync points:** T+0:20 confirm A2 client shapes; T+1:15 `verify` + JSONL to A1; T+2:30 Report shape example (real JSON from a run, with `mix_coverage`) to G4; tell G1 the preset list and the file key form.

**Pitfalls**
- About 11.5% of Jev answers are wrong at >= 90% confidence. Answerable rows need both `jev.supported` and `extract.names`.
- Jev is weak at arithmetic and dates; keep `numbers` in code.
- Descriptive option names only for `jev.cell` (topic names) and `jev.quality` levels.
- Normalize numbers before matching (`1,000` == `1000`, `30-day` == `30 days`).
- The absent-topic exemption is for unanswerable and partial only. An invented name in an answerable or false_premise reply is exactly the hallucination we catch.
- `NUMBERS_ALLOW_USER` does not make a false-premise reply safe by itself. Tier-2 `jev.corrects` still catches a reply that accepts the wrong value.
- A flawed DPO reply that fails only `format` or `dedup` is not proof. Drop that pair.
- Parquet: nested fields (`messages`, `spans`, `checks`) must have a stable schema; serialize to JSON strings if pyarrow complains.
- Write export files only under `settings.runs_dir` (`/tmp/runs` in the cloud). A write to `runs/` fails on the read-only Lambda disk.
- Do not write `Job.files` in `verify`. A1 sets it from the `export()` return value.
- Never name a vendor model in your code; call `get_llm(job, "judge")`. The judge can be any model.
- A weak judge model lowers quality. Keep judge agreement and the spot-check in the report, so the user sees it. The UI warns when judge == writer model.

---

## A5 Deploy (Aaditya)

**Role:** AWS deployment, auth infrastructure and cloud backends owner.
**Mission:** Deploy Bob to AWS serverless: a Lambda API behind CloudFront and one Fargate worker task per job, with a Cognito user pool for sign-in and a cross-account role template so each user runs Bedrock in their own AWS account. Write the aws implementations of A1's backend protocols, the worker entry, the image and the CDK stacks. Checkpoint 2 must pass on the CloudFront URL. Local mode stays the default; you add the cloud mode, you do not change the local behavior.

**Read first:** CONTRACTS §0, §1, §7, §8, §9, §12, §13 (all). DECISIONS D23, D25, D26, D27, D33. PLAN §5, §6, §10, §11.

**You own:** `backend/bob/aws/blobs.py`, `aws/store.py`, `aws/events.py`, `aws/runner.py`, `aws/secrets.py`, `backend/bob/worker.py`, `backend/Dockerfile`, root `.dockerignore`, root `.gitignore` (write it first, before any commit: `.env`, `secrets.json`, `runs/`, `cdk.out/`, `infra/outputs.json`, `node_modules/`, `dist/`, `__pycache__/`), root `README.md` (setup, deploy, BYO AWS steps; other agents send text through `CHANGES_REQUESTED.md`), `infra/**` (`app.py`, `cdk.json`, `requirements.txt`, `bob_infra/data_stack.py`, `bob_infra/app_stack.py`, `deploy.sh`, `README.md`, `infra/templates/bedrock-role.yaml`), your tests for the aws backends.
**Do not touch:** `core/*`, `config.py`, `.env.example` (A1), `orchestrator.py`, `llm/*`, `backend/pyproject.toml` (A1; request `boto3` and other packages through A1), `pipeline/*`, `clients/*`, `export/*`, all Gunbir files.

**You provide:** `S3Blobs`, `DynamoStore`, `DynamoEventLog`, `EcsRunner` (they implement A1's protocols, including `get_user`/`put_user`, `get_control -> Control`, `is_running`, `RunnerBusy`); `bob/aws/secrets.py` (load the `bob/keys` secret JSON into the environment); `python -m bob.worker <job_id> <mode>`; the image (with `infra/templates/` at `/app/infra/templates/`); the `BobData` stack (with the Cognito user pool) and the `BobApp` stack; `infra/templates/bedrock-role.yaml`; `infra/deploy.sh`; the CloudFront URL; the table, bucket, secret and Cognito names (pool id, client id, domain); the demo user, connected to the team's own AWS account. Consumers: A1 (`backends.py`, `config.py`, `.env.example`), G1 (Cognito ids for `api/auth.py`, the template file), G3 (Cognito ids for `/config/public`), all agents (cloud URL), Gunbir (checkpoint 2 test on the cloud).
**You consume:** A1 protocols, config vars, `credentials.py` and `run_job` (T+0:15 stubs, T+1:00 credentials, T+1:30 real); G1 `/api/ping`, `/api/health`, `/api/config/public`, `/api/me*`; G3 `npm run build` output; G2 `demo/` (copied into the image).

**Research at first use** (your items; use the default until you confirm):

| Item | When | Default until confirmed |
|---|---|---|
| Bob hosting AWS account + region | T+0:00 | us-east-1 |
| CloudFormation quick-create template URL | P1 | CLI command only |
| Cross-account test account | T+2:00 | same-account role |

**Tasks**
1. **Before T+0:00 (pre-flight):** Make sure the hosting AWS account exists and you can sign in. Run `cdk bootstrap aws://<account>/<region>` (default region us-east-1). Make sure Docker Desktop runs. Install Node 20 and `npm i -g aws-cdk`. Put the API keys in a local `secrets.json` (never committed). Bob's hosting region (Lambda, Fargate, DynamoDB, S3, Cognito) is separate from each user's Bedrock region.
2. **T+0:00-0:20:** Confirm the hosting account and region (research item). CDK v2 app skeleton in Python (`infra/`). Deploy `BobData`: DynamoDB table `bob` (on-demand, `pk`/`sk` strings, TTL attribute `expires_at`; only job items get `expires_at` = 7 days; `USER#` profile items have no TTL), the data bucket, the frontend bucket, the secret `bob/keys`, a KMS key with alias `alias/bob-user-keys` (for the users' encrypted API keys; `BobApiRole`: `kms:Encrypt` + `kms:Decrypt`; `BobWorkerTaskRole`: `kms:Decrypt` only), and a **Cognito User Pool** (email sign-in, app client without secret, PKCE, managed login domain; `selfSignUpEnabled` from `BOB_SIGNUP`, default `invite` = off). Buckets use DESTROY + autoDeleteObjects. Set the secret value: `aws secretsmanager put-secret-value --secret-id bob/keys --secret-string file://secrets.json`. Post the table, bucket, secret, KMS key id, pool id, client id and domain to all agents. A1 adds them to `.env.example`.
3. **T+0:20-1:30:**
   - `backend/Dockerfile`: build context = repo root, `python:3.12-slim`, linux/amd64, `pip install ./backend`, copy the Lambda Web Adapter extension (`public.ecr.aws/awsguru/aws-lambda-adapter`) to `/opt/extensions/`, bake the model2vec model to `/opt/models/potion-base-8M`, copy `demo/` to `/app/demo`, copy `infra/templates/` to `/app/infra/templates/`. Default CMD = uvicorn `bob.api.app:app` on port 8080. Root `.dockerignore` (exclude `.env`, `runs/`, `node_modules/`, `cdk.out/`, `secrets.json`; keep `infra/templates/`).
   - `bob/aws/*` against A1's protocols (CONTRACTS §13). Use boto3 inside `asyncio.to_thread` (no aioboto3).
     - `DynamoStore`: `META`, `ROW#` and user items; the full Job document goes to S3 `runs/<id>/job.json`. User profile: `USER#<sub>` / `PROFILE` (UserProfile JSON, plus the KMS-encrypted API keys for `openai_compatible` roles (P1), never in the UserProfile model); no `expires_at` on it; `get_user` / `put_user`. Job list key moves from `JOBS` / `<created_at>#<id>` to `USER#<sub>` / `JOB#<created_at>#<id>`; `list_jobs(owner_id)` queries it. META gains `owner_id`, `heartbeat_at`, `control` and `plan_key`; `set_control(job_id, "approved", plan)` writes the approved plan JSON to S3 `runs/<id>/approved_plan.json`; `get_control` returns a `Control` with the plan loaded. Support the watchdog's conditional update on META (`status` unchanged).
     - `DynamoEventLog`: `EVT#<seq:08d>` items with a conditional put (`attribute_not_exists(sk)`); `read_after` = Query with `sk > EVT#<seq>` and `begins_with EVT#`, ConsistentRead; `subscribe` polls `read_after` every `BOB_EVENT_POLL_MS`.
     - `S3Blobs`: keys mirror the local `runs/` tree; `url()` returns a presigned GET (1 h).
     - `EcsRunner`: `ecs.run_task` (public subnet, `assignPublicIp=ENABLED`); store `task_arn` in META; raise `RunnerBusy` when `BOB_MAX_WORKERS` (2) tasks run or the user already has `BOB_MAX_ACTIVE_JOBS_PER_USER` (1) active jobs; `is_running(job_id)` = META `task_arn` + `ecs.describe_tasks`, running unless `lastStatus == STOPPED` (return the `stoppedReason` for the watchdog); `stop()` = `ecs.stop_task`.
   - Test `bob/aws/*` on real DynamoDB and S3. No moto, no LocalStack (D23).
   - `bob/worker.py`: thin entry. Load secrets -> build Orchestrator -> `await run_job(job_id, mode)` -> exit code.
   - `BobApp` stack: image asset; API Lambda (2048 MB, timeout 900 s, x86_64, ephemeral storage 2048 MB, reserved concurrency 20) with a Function URL (invoke mode RESPONSE_STREAM, `AuthType NONE` behind CloudFront); Lambda env `AWS_LWA_INVOKE_MODE=response_stream`, `AWS_LWA_PORT=8080`, `AWS_LWA_READINESS_CHECK_PATH=/api/ping`, `BOB_ENV=aws`, `BOB_RUNS_DIR=/tmp/runs`, `BOB_AUTH=cognito`, `BOB_BEDROCK_AUTH=assume_role`, `BOB_ACCOUNT_ID`, `BOB_KMS_KEY_ID`, `BOB_COGNITO_REGION`, `BOB_COGNITO_USER_POOL_ID`, `BOB_COGNITO_CLIENT_ID`, `BOB_COGNITO_DOMAIN` (the worker task gets the same auth vars); ECS cluster and worker task def (2 vCPU / 4 GB, x86_64, CMD `python -m bob.worker`, logs to `/bob/worker`); default VPC, egress-only security group, no NAT; CloudFront with the S3 default behavior (CloudFront Function rewrites non-file paths to `/index.html`) and `/api/*` to the Function URL (CachingDisabled, AllViewerExceptHostHeader, all methods, origin read timeout 60 s); IAM roles per CONTRACTS §13.
   - IAM roles with **fixed names** `BobApiRole` and `BobWorkerTaskRole` (CDK `roleName`), so the user's trust policy stays valid across deploys. Both roles get `sts:AssumeRole` on `arn:aws:iam::*:role/BobBedrockAccess*`. In aws mode Bob's roles do not need `bedrock:InvokeModel*`; keep it only if `BOB_BEDROCK_AUTH=default` in aws (for the team's own tests).
   - `infra/templates/bedrock-role.yaml` (CloudFormation): parameters `BobAccountId`, `ExternalId`; role `BobBedrockAccess`. Trust: principal `arn:aws:iam::<BobAccountId>:root` with conditions `sts:ExternalId = <ExternalId>` and `aws:PrincipalArn` in [`arn:aws:iam::<BobAccountId>:role/BobApiRole`, `arn:aws:iam::<BobAccountId>:role/BobWorkerTaskRole`]. Permissions: `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` on `arn:aws:bedrock:*::foundation-model/*` and `arn:aws:bedrock:*:*:inference-profile/*` (all providers, not only Anthropic), plus `bedrock:ListFoundationModels` and `bedrock:ListInferenceProfiles`. Research: some Bedrock marketplace / third-party models need `aws-marketplace:ViewSubscriptions` and `aws-marketplace:Subscribe` on first use; add them if the research confirms it. Output: the role ARN. Test it with `aws cloudformation deploy --template-file bedrock-role.yaml --stack-name BobBedrockAccess --capabilities CAPABILITY_NAMED_IAM --parameter-overrides BobAccountId=<id> ExternalId=<ext>`.
   - `infra/deploy.sh`: `npm run build` -> `cdk deploy --all --require-approval never --outputs-file infra/outputs.json` -> print the CloudFront URL. It must work from a clean checkout in < 15 min.
   - **By T+1:15:** the CloudFront URL serves the UI, and `/api/ping` and `/api/health` work there with the current backend code. Tell all agents.
   - **By T+1:30:** template, fixed role names and `sts:AssumeRole` deployed. Create the demo user with `aws cognito-idp admin-create-user`. Sign in once so the profile exists; deploy the template in the team's own AWS account with the demo user's external id (same-account assume role works); put the role ARN on the Account screen; run AWS Verify and Models Verify.
4. **T+1:30 checkpoint 1.** Local pass test as before, plus the cloud health check above, plus: sign-in works on the CloudFront URL and `/api/me` returns the profile.
5. **T+1:40-2:50:** Deploy the checkpoint-1 merge. Run a real job in the cloud as the demo user with assume-role Bedrock access: create -> Fargate worker -> plan -> approve -> rows on SSE through CloudFront -> file download from S3. Test SSE reconnect (set `BOB_SSE_MAX_S=60` for one test). Make sure cancel stops the job in 5 s. Kill one worker task and check that the watchdog sets `error`. Measure the worker cold start (target: by T+2:00). Research item: test the cross-account path with a second AWS account if one is available (by T+2:00); else keep the same-account role.
6. **T+2:50 checkpoint 2.** Deploy the merge. The pass test runs **on the CloudFront URL** (P0): sign in -> Connect AWS (verified) -> job -> rows -> download.
7. **T+3:00-3:30 (P1):** resync mode in the worker; CloudFormation quick-create link (needs a public S3 template URL; research); origin-secret header (CloudFront adds `X-Bob-Origin`; API middleware rejects calls without it, so nobody can call the Function URL directly); AWS Budgets alarm; presigned uploads (`POST /uploads/presign`, with G1); a CloudWatch Logs Insights query for errors. Root `README.md`: setup, deploy and BYO AWS steps.
8. **T+3:30-4:00:** Deploy the frozen `main` (tag `demo`) once. Run the demo job once on the cloud URL, signed in as the demo user with AWS already connected. Keep localhost as the backup. After the event: `cdk destroy --all`.

**Definition of done:** P0 at T+2:50: both stacks deploy from a clean checkout with `infra/deploy.sh` in < 15 min; the aws backends pass their tests on real AWS; Cognito sign-in works on the CloudFront URL; the demo user is connected and verified through `bedrock-role.yaml`; a real job runs on a Fargate worker with assume-role Bedrock; SSE streams through the Function URL and CloudFront and reconnects with `Last-Event-ID`; files download from S3; the checkpoint-2 pass test passes on the CloudFront URL. P1 by T+3:30: resync in the cloud, quick-create link, origin-secret header, budget alarm, presigned uploads, logs query, root README. Cut line: if the cloud job path fails at T+3:30, demo on localhost and show the deployed UI and `/api/health`.

**Handoffs and sync points:** T+0:15 get A1's protocol stubs, config vars and `boto3`; T+0:20 post resource and Cognito names to all agents (A1 puts them in `.env.example`); T+1:00 get A1 `credentials.py`; T+1:15 cloud health on the CloudFront URL to all; T+1:30 template + role names to G1 (template file path) and cloud health + sign-in at checkpoint 1; T+2:00 cloud real job and worker cold start to Aaditya and Gunbir; T+2:50 checkpoint 2 on the CloudFront URL; T+3:30 deploy tag `demo`.

**Pitfalls**
- The SPA fallback must not be distribution-wide. Use a CloudFront Function on the default behavior only. Distribution-wide custom error pages turn API 404s into `index.html`.
- Bob's role names must not change between deploys. The user's trust policy names `BobApiRole` and `BobWorkerTaskRole`. A CDK-generated name breaks every connected user.
- AssumeRole fails on a wrong external id, trust policy or role name. `/me/aws/verify` shows the exact STS error; check it first.
- Model access may be off in the demo account's Bedrock region, or the region may lack a chosen model. Models Verify makes one real call per role; fix model access before the demo.
- Marketplace / third-party Bedrock models can need a subscription. Verify shows the exact AccessDenied text; research the marketplace permissions for the template.
- Profile items must not expire. Never set `expires_at` on `USER#` items. A lost profile makes a new external id, and the user's trust policy stops working.
- KMS grants: `BobApiRole` gets `kms:Encrypt` + `kms:Decrypt`; `BobWorkerTaskRole` gets `kms:Decrypt` only. No other principal uses the key. Never return a decrypted key from any route.
- The cross-account path is not tested with the same-account demo. Test with a second AWS account if one is available.
- Build the image with `--platform linux/amd64`. Docker on Windows builds for the wrong platform without it.
- In Lambda, `/tmp` is the only writable path. Set `BOB_RUNS_DIR=/tmp/runs` and ephemeral storage 2 GB.
- CloudFront cuts an origin after 60 s idle. The SSE route must send `: ping` every `BOB_SSE_HEARTBEAT_S` (15 s) and end at `BOB_SSE_MAX_S` (840 s); the browser reconnects.
- Set the LWA readiness check to `/api/ping`, not `/health`. `/health` makes paid calls and needs a signed-in user.
- Never commit `secrets.json` or `infra/outputs.json`. Add both to `.gitignore` (request it through `CHANGES_REQUESTED.md` if you do not own the file).
- Add `cdk.out/` to `.gitignore`.
- Fargate cold start is 30-60 s before the plan shows. Keep the image small and start the demo job early. `BOB_HEARTBEAT_TIMEOUT_S` (90 s) covers the cold start.
- Do not exclude `infra/templates/` in `.dockerignore`. G1 serves the template from `/app/infra/templates/`.

---

## G1 API + Files (Gunbir)

**Role:** Web API, auth, SSE and file ingestion owner.
**Mission:** Expose the orchestrator through every route in CONTRACTS §6, check the signed-in user and the job owner on every route, stream events over SSE with replay, accept uploads, parse files into `Document`, and dispatch `fetch_documents()` to the right connector. Make every provider error visible to the user.

**Read first:** CONTRACTS §0, §1, §2 (SourceSpec, Document, Job, Row, Report, UserProfile, BedrockAccess, ModelConfig, ModelRoles), §6 (all), §7, §8, §12, §13 (Lambda limits). PLAN §2, §5, §7 items 1 and 8. DECISIONS D25, D26, D27, D33.

**Lambda limits that change your work** (the API runs in AWS Lambda in the cloud):
1. The API has no background work. A task that starts after the response freezes. Long work goes to the worker only (`Runner.start`).
2. Every route returns in < 25 s (CloudFront origin timeout). `POST /sources/preview` caps pages and time (for example 10 pages or 20 s) and says so in its response. `POST /me/aws/verify` and `POST /me/models/verify` also stay under 25 s.
3. Request bodies are <= 6 MB. `POST /uploads` keeps multipart for P0 (demo files are small). P1: `POST /uploads/presign` returns a presigned S3 PUT for larger files.
4. No writes outside `BOB_RUNS_DIR` (`/tmp/runs` in Lambda). Store uploads through `Blobs.put("runs/uploads/<id>/<name>")`. The helper is `async def read_upload(upload_id) -> list[tuple[name, bytes]]`, not a disk path.
5. SSE: send `retry: 1000` at stream start, a `: ping` comment every `BOB_SSE_HEARTBEAT_S`, and the headers `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Close the stream after `BOB_SSE_MAX_S`. The browser reconnects with `Last-Event-ID` (replay is already in the contract).
6. `GET /jobs/{id}/files/{name:path}`: `name` is a path relative to the job export folder (for example `openai-chat/train/train.jsonl`). If `blobs.url()` returns a URL, reply 302 to it. Else stream the local file. `GET /jobs/{id}/files/{name:path}/url` -> `{url}` (aws: presigned S3 GET, 1 h; local: `/api/jobs/{id}/files/{name}`). The frontend downloads through the `/url` route, because a plain link cannot send the auth header.
7. New route `GET /api/ping` -> `{ok: true}` with no external calls and no auth (Lambda readiness check). `/health` makes paid calls, needs a signed-in user, and must not run on each cold start.
8. Composio OAuth `redirect_url` = `BOB_PUBLIC_URL + BOB_OAUTH_CALLBACK_PATH` (`/oauth/callback`), the same route G3 serves.

**You own:** `backend/bob/api/app.py`, `api/routes.py`, `api/sse.py`, `api/auth.py`, `backend/bob/connectors/__init__.py`, `connectors/upload.py`, `connectors/parsers.py`, run script (`backend/run.sh` or `make dev`), your tests.
**Do not touch:** `connectors/firecrawl.py`, `composio.py`, `sync.py` (G2), all Aaditya files (including `infra/templates/bedrock-role.yaml`, A5), `frontend/*`.

**You provide:** all HTTP routes, including `GET /api/ping`, `GET /config/public` and the `/me*` routes; `current_user()` dependency; `fetch_documents(spec, job_id, progress)`; upload storage through `Blobs` and a helper `async def read_upload(upload_id) -> list[tuple[name, bytes]]` for A1 seeds and the upload connector. Consumers: G3, G4 (HTTP), A1 (`fetch_documents`, `read_upload`), A5 (`/api/ping` readiness, `/api/health` cloud check, sign-in check).
**You consume:** A1 `Orchestrator` (`get_job`, `list_jobs`, `list_rows`, `get_row` are `async`: always `await` them; `create_job(spec, user)`, `get_or_create_user`, `update_bedrock`, `verify_bedrock`, `update_models`, `verify_models`, `health_job(user)`), models, `get_blobs()`, `pyjwt[crypto]` (A1 adds it); A5 Cognito ids and the template file; G2 `firecrawl.fetch(...)`, `composio.fetch(...)`, `composio.connect/status/browse`; A2 clients for `/health`.

**New HTTP routes (v4.1)**

| Method | Path | Returns |
|---|---|---|
| GET | `/config/public` | `{auth, cognito?}` (no auth) |
| GET | `/me` | `UserProfile` |
| GET | `/me/aws/setup` | `{bob_account_id, external_id, template_url: "/api/me/aws/template", cli_command}` |
| GET | `/me/aws/template` | the YAML file |
| PUT | `/me/aws` | body `BedrockAccess` (mode forced to `assume_role` in aws mode) -> `UserProfile`; clears `bedrock_verified_at` |
| POST | `/me/aws/verify` | AssumeRole only: `{ok, error?}` |
| PUT | `/me/models` | body `ModelRoles` (+ optional `api_keys: {role: key}` for `openai_compatible`, P1) -> `UserProfile`; clears `models_verified_at` |
| POST | `/me/models/verify` | one tiny real call per configured role: `{ok, roles: {writer: "ok"/error, ...}}` |
| GET | `/me/models/available` (P1) | Bedrock foundation models and inference profiles in the user's region (through the assumed role) |
| GET | `/jobs/{id}/files/{name:path}/url` | `{url}` |

Changed: `POST /jobs` -> 412 / 429 rules; `/jobs/*` owner check -> 404; `/health` key `bedrock` uses the caller's profile (or `"not connected"`). No route ever returns a user's API key; `ModelConfig.api_key_set: true` is the only sign that a key exists.

**Tasks**
1. **T+0:00-0:20:** FastAPI app, CORS for the Vite dev origin (and `BOB_PUBLIC_URL` in aws mode; allow the `Authorization` header), `/api` prefix, run script. `GET /api/ping` -> `{ok: true}` with no external calls. `/health` makes one tiny real call per provider (Bedrock, Jev, ScaleDown, Firecrawl, Composio) in parallel with a timeout and returns `ok` or the error text. Client calls take the job from A1 `health_job(user)`.
2. **T+0:20-0:45:** `POST /uploads` (store through `Blobs.put("runs/uploads/<id>/<name>")`), `read_upload`, MD/TXT parser, `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/events`. This unblocks A1's thin path (with `BOB_AUTH=none`, user `local`).
3. **T+0:45-1:30:**
   - `api/auth.py` (**by T+1:30**): FastAPI dependency `current_user()`. `BOB_AUTH=cognito`: verify the access token (`Authorization: Bearer`) with the pool JWKS (PyJWT[crypto]; check issuer, `token_use=access`, `client_id`, expiry); cache the JWKS. `BOB_AUTH=none` (local default): user id `local`. A missing or bad token gives HTTP 401 `{"error": "sign in required"}`. Then `await get_or_create_user(user_id, email)`. Open routes: `/ping`, `/config/public`. `/oauth/callback` handling is frontend only. All other routes need a user.
   - `/config/public` -> `{auth: "none" | "cognito", cognito?: {region, user_pool_id, client_id, domain}}` from the `BOB_COGNITO_*` vars. `/me`, `/me/aws/setup` (`cli_command` = `aws cloudformation deploy --template-file bedrock-role.yaml --stack-name BobBedrockAccess --capabilities CAPABILITY_NAMED_IAM --parameter-overrides BobAccountId=<BOB_ACCOUNT_ID> ExternalId=<external_id>`), `/me/aws/template` (read the file baked in the image at `/app/infra/templates/bedrock-role.yaml`; in local mode the repo copy `infra/templates/bedrock-role.yaml`), `PUT /me/aws` (`update_bedrock`; clears `bedrock_verified_at`), `POST /me/aws/verify` (`verify_bedrock`, AssumeRole only; show the exact STS error text), `PUT /me/models` (`update_models`; clears `models_verified_at`), `POST /me/models/verify` (`verify_models`; one tiny real call per role; show the exact error per role). P1: `GET /me/models/available` (`bedrock:ListFoundationModels` and `bedrock:ListInferenceProfiles` through the assumed role) and the `api_keys` field of `PUT /me/models`. Never return a key; return `api_key_set: true`.
   - Owner check: every `/jobs/{id}/*` route loads the job and returns 404 when `job.owner_id != user.id`. `GET /jobs` calls `list_jobs(user.id)`.
   - `POST /jobs`: call `create_job(spec, user)`; map a missing `bedrock_verified_at` to HTTP 412 `{"error": "connect AWS first"}`, a missing `models_verified_at` to HTTP 412 `{"error": "verify models first"}`, and `RunnerBusy` to HTTP 429 `{"error": "too many running jobs"}`.
   - `sse.py`: wire format `id: <seq>\nevent: <type>\ndata: <json>\n\n`; read `Last-Event-ID` header (and a `last_event_id` query param as a fallback); check the user and the owner before the stream starts; call `Orchestrator.subscribe()`; send `retry: 1000` at stream start; send a `: ping` comment every `BOB_SSE_HEARTBEAT_S` (15 s); set `Cache-Control: no-cache` and `X-Accel-Buffering: no`; close the stream after `BOB_SSE_MAX_S`.
   - All other §6 routes on the orchestrator. `GET /rows` with filters and paging. `POST /spot-check` and `POST /export` return HTTP 409 `{"error": "job is running"}` while a worker runs (`runner.is_running`; CONTRACTS §7, single job writer). File download on `{name:path}`: if `blobs.url()` returns a URL, reply 302 to it; else stream the local file with a safe path check (only under `settings.runs_dir/<job_id>/export/`). Add the `/url` route.
   - Parsers: PDF (pypdf), DOCX (python-docx, headings -> `#`), HTML (markdownify), MD, TXT, CSV (rows as markdown table or one section per row). Output normalized markdown, `id = sha1(uri)[:12]`, `content_hash = sha1(text)`.
   - `fetch_documents`: dispatch by `kind` to upload, `firecrawl`, `composio`; pass `progress(done, total, detail)`; pass the job owner to Composio (G2 builds the Composio `user_id` from it).
4. **T+1:30 checkpoint 1.** Sign-in on the CloudFront URL and `/api/me` must work.
5. **T+1:40-2:50:** error handling: map provider exceptions to JSON `{error, provider, detail}` with correct status; job errors appear in `Job.error` and SSE `error`; `/sources/preview` (cap pages and time, for example 10 pages or 20 s, and say so in the response); `GET /jobs` list with summary fields; connector routes on G2 functions (OAuth redirect = `BOB_PUBLIC_URL + BOB_OAUTH_CALLBACK_PATH`); `/presets`; `/health` `bedrock` key from the caller's profile (or `"not connected"`).
6. **T+3:00-3:30:** fix bugs; `POST /uploads/presign` for larger files (P1, with A5); send README run steps for the API to A5 through `CHANGES_REQUESTED.md`.

**Definition of done:** Every §6 route works against a real job; a request without a valid token gets 401 `{"error": "sign in required"}` in cognito mode; another user's job returns 404; `POST /jobs` returns 412 `connect AWS first` before AWS verify, 412 `verify models first` before models verify, and 429 for a second active job; `/me/aws/verify` shows the real STS error on a bad role ARN; `/me/models/verify` shows the real error per role on a bad model id; no response contains an API key; disconnecting and reconnecting SSE with `Last-Event-ID` replays missed events with no gaps or duplicates; each of the 6 file types parses a real file; `/health` shows a real error when one key is wrong; the UI shows that error; a file downloads through the `/url` route.

**Handoffs and sync points:** T+0:20 tell A5 that `/api/ping` and `/api/health` are live; T+0:45 tell A1 the thin-path routes are live; T+1:15 tell G3/G4 every route is live; T+1:15 check `/api/health` on the CloudFront URL with A5; T+1:30 tell G3 that `/config/public` and `/me*` are live; agree on route errors format with G3; pass `user_id=current_user().id` to the connector routes and `user_id=job.owner_id` through `fetch_documents` (CONTRACTS §7).

**Pitfalls**
- Do not run long work inside the request, and do not start a background task in the API process (it freezes in Lambda). `create_job` starts the worker through the runner and returns at once.
- Every route returns in < 25 s. Request bodies are <= 6 MB.
- Never write outside `settings.runs_dir`. Store uploads through `Blobs`.
- `await` the async orchestrator getters. A missing `await` returns a coroutine, not a Job.
- SSE behind gzip middleware buffers; exclude the events route.
- `Last-Event-ID` is a string; parse to int safely.
- Never echo API keys in `/health` errors. Never return a user's stored model API key from any route.
- `/health` clients need a `job`. Use A1 `health_job(user)`; do not build your own job object.
- Return 404, not 403, for another user's job. Do not tell a caller that the job exists.
- Check `token_use=access` and `client_id`. An ID token or a token from another app client must fail.
- An access token can expire during a long SSE stream. The stream ends and the client reconnects with a fresh token; do not keep a stream open past `BOB_SSE_MAX_S`.
- The file route needs `{name:path}`. A plain `{name}` does not match keys with `/`.

---

## G2 Connectors (Gunbir)

**Role:** External source connectors and demo data owner.
**Mission:** Fetch real content from websites (Firecrawl) and internal apps (Composio: Notion first, then Jira, Confluence, Google Drive) as `Document` objects with live progress. Keep each user's Composio connections private. Produce the smoke corpus that all backend tests use, the cached demo corpus, and the re-sync diff.

**Read first:** CONTRACTS §0, §1, §2 (SourceSpec, Document, UserProfile), §6 (connector routes, `/sources/preview`), §7 (`fetch_documents`), §10, §12. PLAN §2, §6 (pre-start checklist), §9, §11. DECISIONS D27 (Composio part).

**You own:** `backend/bob/connectors/firecrawl.py`, `connectors/composio.py`, `connectors/sync.py`, `demo/*` (`demo/smoke/`, `demo/corpus/`), your tests.
**Do not touch:** `connectors/__init__.py`, `upload.py`, `parsers.py` (G1), all Aaditya files, `frontend/*`.

**You provide:** `firecrawl.fetch(spec, job_id, progress) -> list[Document]`; `composio.connect(toolkit, redirect_url, *, user_id)`, `status(toolkit, connection_id, *, user_id)`, `browse(toolkit, account_id, q, *, user_id)`, `fetch(spec, job_id, progress, *, user_id)` (Composio user id = `COMPOSIO_USER_PREFIX + user_id`, CONTRACTS §7); `sync.diff(old_docs, new_docs) -> {added, changed, removed}`; `demo/smoke/*.md`, `demo/smoke/seeds.jsonl`, `demo/corpus/`. Consumers: G1, A1 (resync), A2/A3/A4 (smoke tests).
**You consume:** A1 models, cache, ledger: `ledger.record(job_id, "firecrawl" | "composio", calls=..., usd=...)` (CONTRACTS §7). Config: `FIRECRAWL_API_KEY`, `COMPOSIO_API_KEY`, `COMPOSIO_USER_PREFIX` (`bob-`), `COMPOSIO_DEMO_ACCOUNTS`. G1 passes the Bob user id (route: `current_user()`; worker: `Job.owner_id`). Commit the first real smoke page by T+0:10 so A3 can test the Writer.

**Research at first use** (your first task; use the default until you confirm):

| Item | When | Default until confirmed |
|---|---|---|
| Composio toolkits enabled + tool slugs | T+0:45 | Notion only |

**Tasks**
1. **T+0:00-0:20:** Real Firecrawl scrape of 3-5 demo doc pages -> `demo/smoke/<slug>.md` (markdown only, with source URL in a front-matter line). Write 10 real seed questions with real answers from those pages -> `demo/smoke/seeds.jsonl` (`{"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}`). These are real examples a support agent would see, based on the real pages. Commit and announce by T+0:20.
2. **T+0:20-0:45 (research task):** list the Composio toolkits that are enabled on the account and their tools through the SDK; print slugs and input schemas; pick the search/list and fetch/get-content tools for Notion; verify each with one real call. Store the verified slugs in a constant with a comment of the date. Until this is done, plan for Notion only.
3. **T+0:45-1:30:**
   - `firecrawl.py`: use the Firecrawl SDK `start_crawl(url, limit=crawl_limit, scrape_options=markdown)` then poll `get_crawl_status(id)` every 2 s; call `progress(done, total, url)` per new page; convert each page to `Document` (`uri` = page URL, `title` from metadata). Check method names against the installed `firecrawl-py` version before coding. Cache by crawl request.
   - `composio.py`: Composio Python SDK. Every call uses the Composio `user_id` = `COMPOSIO_USER_PREFIX + UserProfile.id` (for example `bob-<cognito sub>`, or `bob-local` in local mode), so each user's Notion and Jira connections are private. `connect`: create or reuse the auth config for the toolkit, initiate the connected account for that `user_id`, return `{auth_url, connection_id}`. `status`: poll the connected account until `ACTIVE`. `browse`: search pages with the verified slugs; return `[{id, title, kind}]`. `fetch`: for each page id, fetch blocks/content, convert to markdown, `uri = notion://<page_id>`. `COMPOSIO_DEMO_ACCOUNTS` applies to the demo user only; never use it for another user.
   - Full demo crawl (cap 25 pages) of the demo docs -> `demo/corpus/` (one `.md` per page plus `index.json` with uri, title, hash). Real fetched content only.
4. **T+1:30 checkpoint 1.**
5. **T+1:40-2:50 (P1 items; Notion stays P0 and must not break):** Jira (`jql` scope -> issues with summary, description, comments; `uri = jira://<key>`) and Confluence or Google Drive (same slug discovery rule). `sync.py`: re-fetch each `SourceSpec`, compare `content_hash` per `uri`, return `added`, `changed`, `removed`. Cache the real Notion demo pages to `demo/corpus/notion/`.
6. **T+3:00-3:30:** connect the demo accounts for the demo user before the demo; put the connected account ids in `.env` (never committed); fix bugs.

**Definition of done:** A real crawl of the demo URL emits per-page progress and returns 20-25 `Document`s; a real Notion OAuth connect works from the UI popup; browse lists real pages; fetch returns their text; two Bob users do not see each other's Composio connections; `demo/smoke/` and `demo/corpus/` contain only real fetched content; `sync.diff` reports a change after a real page edit.

**Handoffs and sync points:** T+0:20 smoke corpus to A2/A3/A4/A1; T+0:45 verified toolkits and slugs to G1 and G3; T+1:15 function signatures to G1 (with the keyword-only `user_id`, CONTRACTS §7); T+1:30 corpus cached; T+2:30 `sync.py` to A1.

**Pitfalls**
- Do not guess Composio tool slugs or argument names; list and verify them at runtime.
- Do not use one fixed Composio `user_id` for all users. Always build it from `COMPOSIO_USER_PREFIX` and the Bob user id.
- Notion content comes as blocks; handle pagination and nested children.
- Firecrawl crawl is async and slow; never block a request on it; keep `crawl_limit` at 25.
- OAuth redirect URL = `BOB_PUBLIC_URL + BOB_OAUTH_CALLBACK_PATH` (`/oauth/callback`), the frontend route G3 serves. Agree on it early.
- Do not fake or hand-edit the corpus. If a fetch fails, fix it and fetch again.
- In the cloud, Firecrawl and Composio fetch run inside the Fargate worker (no time limit), not in the API Lambda.
- The image copies `demo/` to `/app/demo`. Commit `demo/corpus/` before A5 deploys checkpoint 2.
- In aws mode the OAuth redirect URL starts with `BOB_PUBLIC_URL` (the CloudFront URL), not localhost.

---

## G3 UI: Setup + Plan + Account (Gunbir)

**Role:** Frontend shell, auth, API client, Setup, Plan and Account screens owner.
**Mission:** Build the React app shell with sign-in and the typed API client, then the Setup screen where a user enters a goal and connects real sources, the Plan screen where the user edits the real coverage map and starts the build, and the Account screen where the user connects their own AWS account for Bedrock and picks a model for each role.

**Read first:** CONTRACTS §0, §1, §2 (all; you mirror it), §6 (all routes, incl. `/config/public` and `/me*`), §8 (`plan.ready`, `job.status`, `stage.progress`). PLAN §2 steps 1-2, §7 items 1-2, §9 steps 2-3. DECISIONS D26, D27, D33.

**You own:** `frontend/` scaffold (`package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`), `frontend/src/main.tsx`, `App.tsx`, router and layout (app shell), `frontend/src/auth/*` (Amplify config + Authenticator wrapper), `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/screens/Setup*`, `frontend/src/screens/Plan*`, `frontend/src/screens/Account*`, shared non-viz UI components you create.
**Do not touch:** `screens/Build*`, `Row*`, `Report*`, `components/viz/*` (G4), all backend files.

**You provide:** `types.ts` (exact mirror of CONTRACTS §2, incl. `UserProfile` (with `models`, `models_verified_at`), `BedrockAccess` (no model fields), `ModelConfig`, `ModelRoles`, `Control`, `JobOptions` (with `models`), `Axis.role`/`weights`, `Candidate.coords`, `DPOPair` new fields, `Report.mix_coverage`, `CostSummary.model_ids`/`price_unknown`, `Job.owner_id`/`bedrock`/`models`/`heartbeat_at`), `client.ts` (one typed function per §6 route with the bearer token, incl. a function for the file `/url` route), an SSE helper with reconnect, the auth wrapper, routes `/`, `/jobs`, `/jobs/:id/plan`, `/jobs/:id/build`, `/jobs/:id/rows/:rowId`, `/jobs/:id/report`, `/account`, `/oauth/callback`. Consumers: G4.
**You consume:** G1 routes; G2 connector flow; A3 Plan shape; A5 Cognito pool (through `/api/config/public`).

**Tasks**
1. **T+0:00-0:20:** Vite + React 18 + TS strict scaffold, router, layout, `types.ts` from CONTRACTS §2 (same names, fields, literal unions; `CASE_TYPES`, `DIFFICULTIES` as consts). Add the `capped: bool` field of the `/sources/preview` response (CONTRACTS §6) and show it on the Setup screen. npm deps: `aws-amplify`, `@aws-amplify/ui-react`, `@microsoft/fetch-event-source`. Commit and tell G4 by T+0:20.
2. **T+0:20-1:30:**
   - `client.ts`: relative base `/api` (same origin through CloudFront); no hard-coded host. `vite.config.ts` proxies `/api` to `localhost:8000` in dev. Add `Authorization: Bearer <access token>` to every call (from Amplify `fetchAuthSession`; no header when auth is `none`). Errors raise with the server `{error, provider, detail}`. On 401 (`sign in required`), send the user to sign-in. Show 412 with the missing step and a link to `/account`: `connect AWS first` -> the AWS access panel, `verify models first` -> the Models panel. Show 429 as "too many running jobs".
   - SSE helper: `@microsoft/fetch-event-source` (`EventSource` cannot send headers). Send the auth header and `Last-Event-ID` yourself (the last seen event id). On reconnect, get a fresh token. Close only on `done`, `error` or `job.status cancelled`.
   - Auth wrapper (`frontend/src/auth/*`, **by T+1:30**): at start, read `GET /api/config/public` at runtime -> `{auth: "none" | "cognito", cognito?: {region, user_pool_id, client_id, domain}}`. When `cognito`, configure AWS Amplify v6 and wrap the app in the `@aws-amplify/ui-react` Authenticator. When `none`, render the app with no sign-in. One build runs on Vite dev and on CloudFront.
   - Account screen (`/account`, **by T+1:30**), two panels:
     - **AWS access** ("Connect AWS"): from `GET /me/aws/setup` show Bob's AWS account id, the external id, a download of the template `bedrock-role.yaml` (through the client with the auth header), and the CLI command with a copy button. Form: role ARN and Bedrock region (default from config) -> `PUT /me/aws`. Verify button -> `POST /me/aws/verify` (AssumeRole only); show the exact STS error text. Show the verified state. P1: a CloudFormation quick-create link when A5 has a public template URL.
     - **Models**: one row per role (`writer`, `planner`, `judge`, `fallback`; empty fallback = writer). Per role: provider, model id (free text, P0; a picker from `GET /me/models/available`, P1), base URL + API key for `openai_compatible` (P1; after save show only "key set", never the key), advanced fields `json_mode` and `cache`, price overrides (`price_in_per_m`, `price_out_per_m`) -> `PUT /me/models`. Verify button -> `POST /me/models/verify`; show the result per role and the exact error text (for example "model access not enabled in us-east-1"). Show the verified state.
     - A save on either panel clears that panel's verified state; show "verify again".
   - Setup screen: goal textarea; URL input with crawl limit; file upload (drag and drop, calls `/uploads`, shows names and sizes); connector buttons from `GET /connectors` (Notion first): click -> `POST /connect` -> open `auth_url` in a popup -> poll `/status` -> show connected; then a browse picker (`/browse`) to select pages; row count, budget, seed upload; if `bedrock_verified_at` or `models_verified_at` is not set, show a banner that names the missing step ("Connect AWS first" or "Verify models first") with a link to `/account`; Create -> `POST /jobs` -> navigate to a progress view driven by SSE `stage.progress` until `plan.ready`.
   - Plan screen: the grid is topic x case_type (the cell axes) with toggle per cell or per row/column; target per cell. Mix axes (persona, difficulty) show as chips with editable weights; edit persona names and descriptions; remove values. Notes panel; estimated cost vs budget; Start -> `PUT /jobs/{id}/plan` -> Build route.
3. **T+1:30 checkpoint 1.** Sign-in works on the CloudFront URL; the Account screen loads `/me/aws/setup`.
4. **T+1:40-2:50:** Job list page (`GET /jobs`); Setup preview of fetched documents (`/sources/preview`, shows uri, title, chars); provider error banners and `/health` status chips (incl. `bedrock`); fallback badge from `log` events.
5. **T+3:00-3:30:** Advanced options panel on the Setup screen (P1): one field per `JobOptions` field (`cell_axes`, `max_cells`, `case_mix`, `keep_p`, `reject_p`, `audit_rate`, `max_rounds`, `overgen`, `dpo_mode`, `dpo_rate`, `numbers_allow_user`, `extract_exempt_absent`), plus a per-job model override (`models`, same fields as the Models panel); empty = config or profile default; send only set fields in `JobSpec.options`. Polish (empty states, loading states, keyboard focus).

**Definition of done:** A user signs in on the CloudFront URL, connects AWS and verifies the models on the Account screen (a free-text model id works for each role), and creates a job from a real URL, a real uploaded file and a real Notion page in one job; the Plan screen renders the real Planner output as a topic x case_type grid with mix-axis weight chips; toggling cells, editing personas and editing weights changes the plan sent to `PUT /plan` and therefore the build; SSE reconnects with a fresh token and `Last-Event-ID`; `tsc --noEmit` passes; no hard-coded data anywhere.

**Handoffs and sync points:** T+0:20 `types.ts` to G4; T+1:00 SSE helper and the file `/url` client function to G4; agree on the OAuth redirect route (`/oauth/callback`) with G2 and G1; T+1:30 auth wrapper and Account screen for checkpoint 1; update `types.ts` within the hour of any A1 model change.

**Pitfalls**
- Do not add fields to `types.ts` that are not in CONTRACTS §2.
- Never ship sample JSON or placeholder rows. Show an empty state until the API answers.
- Popup blockers: open the OAuth popup directly in the click handler.
- Disabling cells must keep `Cell.id` stable; edit fields, do not rebuild cells.
- Never hard-code `localhost`, a cloud host or Cognito ids in the client. Read the auth config from `/api/config/public` at runtime. The same build runs on Vite dev and on CloudFront.
- `npm run build` must pass at all times. A5's `infra/deploy.sh` runs it.
- `EventSource` cannot send the auth header. Use the fetch-event-source helper everywhere.
- The access token can expire during a long SSE stream. Get a fresh token on each reconnect.
- A plain `<a href>` to a file cannot send the auth header. Download through the `/url` route.
- Never show or keep a user's API key after save. The API returns only `api_key_set`.
- Do not hard-code a model list or vendor names in the UI. Model ids are free text (P0) or come from `/me/models/available` (P1).

---

## G4 UI: Build + Results (Gunbir)

**Role:** Live build view, row inspector and report owner.
**Mission:** Make the factory visible. Show the coverage map filling live, every row with its verdict, the proof behind each row (source spans and checks), and the final quality report with spot-check and downloads.

**Read first:** CONTRACTS §2 (Cell, Row, CheckResult, SpanRef, Report, CostSummary, DPOPair), §4 (check names, to label them), §6 (rows, spot-check, export, files, file `/url`), §8 (all events). PLAN §2 steps 3-5, §7 items 3-6, §9 steps 4-7.

**You own:** `frontend/src/screens/Build*`, `frontend/src/screens/Row*`, `frontend/src/screens/Report*`, `frontend/src/components/viz/*`.
**Do not touch:** `api/*`, `types.ts`, `auth/*`, Setup/Plan/Account screens, app shell (G3), all backend files.

**You provide:** Build, Row inspector and Report screens; heatgrid and chart components.
**You consume:** G3 `types.ts`, `client.ts` (with the bearer token), SSE helper (fetch-event-source), file `/url` client function; G1 routes; A1 events; A4 Row and Report shapes.

**Tasks**
1. **T+0:00-0:20:** design the Build layout and the heatgrid against `types.ts` shapes (no sample data in the repo; render empty until events arrive).
2. **T+0:20-1:30 (live from T+0:50 on the thin path):**
   - Build screen on SSE: heatgrid of cells (rows = topics, columns = case types; persona and difficulty are mixed inside each cell); cell color = `kept / target` (0 to 1 sequential scale, distinct color for disabled, outline for cells in the current gap round); tooltip with generated, kept, rejected, judged, target.
   - Counters (`counts`): generated, kept, rejected, judged, duplicates; status and stage line (`job.status`, `stage.progress`); cost meter (`cost.total_usd` vs budget, frontier-only estimate; mark the Bedrock part as "billed to your AWS account"; show the model id per role from `CostSummary.model_ids`; show a "price unknown" badge for each role in `CostSummary.price_unknown`; show a warning when the judge model id == the writer model id); fallback badge from `cost.fallbacks_used` and `log`.
   - Row feed from `row` events (newest first, cap 200 in memory): verdict badge, case type, `user_preview`, confidence, judge icon, reject reason; filter kept/rejected; click opens the row inspector.
   - Reject reasons summary (count by check name) from rows seen.
3. **T+1:30 checkpoint 1.**
4. **T+1:40-2:50:**
   - Row inspector (`GET /rows/{id}`): messages; persona and difficulty from `Row.coords`; check list in tier order with pass/fail, score, detail (show "Exempt" names in `extract.names`); source panel showing each `SpanRef` text with the cited span highlighted (offsets relative to the span text); link to the source `uri`; badges for judged and audited; for unanswerable rows show `jev.not_in_docs` detail.
   - Report screen (`report.ready` or `GET /jobs/{id}`): coverage heatgrid (final), `mix_coverage` breakdown per persona and per difficulty, pass rate per check bar chart, reject reasons, judge rate and agreement, cost vs frontier-only, token stats, rounds table.
   - Order: row inspector and Report screen are P0 (checkpoint 2); spot-check panel and DPO/extra-preset downloads are P1 (by T+3:30).
   - Spot-check panel (P1): walk the 50 `sample_row_ids`, thumbs up/down -> `POST /spot-check` -> update the report with the returned `Report`.
   - Export panel: preset and format pickers from `/presets`, `POST /export`, downloads from `Job.files` (keys like `openai-chat/train/train.jsonl`). Each download calls `GET /jobs/{id}/files/{name}/url` and opens the returned URL. The DPO download shows the pair mode (`synthesized` or `natural`) (P1).
   - `round` events: banner "Round 2: N thin cells, M hard cells".
5. **T+3:00-3:30:** polish animation of cell fills; performance check with 1,000+ row events.

**Definition of done:** On a real job, the heatgrid fills live; reconnecting the page resumes from replay without double counts; any kept row opens to highlighted spans and passed checks; a rejected row shows its reason; the `round` banner shows round 2; the report shows coverage per persona and per difficulty; `openai-chat` and `full` downloads open through the `/url` route on the CloudFront URL (P0). By T+3:30: spot-check updates the report numbers and the DPO download opens and shows its pair mode (P1).

**Handoffs and sync points:** T+0:50 start on the live thin path; T+2:30 get a real Report JSON (with `mix_coverage`) from A4; report any missing field to A1 through `CHANGES_REQUESTED.md`.

**Pitfalls**
- Event replay sends old events again on reconnect; de-duplicate by event id.
- A closed SSE stream is normal (Lambda ends it after 14 min, or the token expires); the G3 SSE helper reconnects with a fresh token. Close the stream only on `done`, `error`, or `job.status cancelled`.
- In the cloud, the plan can take 30-60 s more to show (Fargate cold start). Show the `stage.progress` "starting worker" line; do not treat the wait as an error.
- `cell.update` is throttled; never compute cell totals from `row` events alone.
- Do not render 1,000 DOM rows; virtualize or cap the feed.
- No hard-coded demo numbers in charts. Empty state until data arrives.
- Color is not the only signal: show the kept/target number in the tooltip and on hover.
- Do not use plain links for downloads. A link cannot send the auth header; use the `/url` route.
- Do not hard-code model names ("Haiku", "Sonnet") in labels. Read the model ids from `CostSummary.model_ids`; the judge is "judge model".
- A cost with a price-unknown role is too low. Show the badge next to the total, not only in a tooltip.
- Do not facet the heatgrid by persona or difficulty. They are mix axes, not cells; show them in the `mix_coverage` breakdown.
