# Bob the Builder: Master Plan (v4.1, the data factory; BYO AWS + Cognito)

> Build window: **4 hours** (T+0:00 to T+4:00). Two builders, 9 coding agents (Aaditya 5, Gunbir 4). Result: a fully working product with **real calls only** (no mocks, no fake data).
> Deploy target: AWS serverless (Lambda API + Fargate job workers), CONTRACTS §13 and D25. Local mode stays the default for development.
> v4.1: each user brings their own AWS account for Bedrock (D26). Users sign in with Cognito (D27). Review fixes: D28 to D32. Model-agnostic LLM layer: every LLM role is configurable; Claude Haiku 5.5 and Sonnet 5.5 are only defaults (D33).
> Interfaces: `CONTRACTS.md`. Reasoning: `DECISIONS.md` (D18 to D33). Agent prompts: `AGENT_BRIEFS.md`. Ideation record: `research/11-data-factory.md`.
> v4 retires templates, question programs, grammar banks and Architect-written generator code.

## 1. Pitch

**Bob is a synthetic data factory. You give it a goal and your company's material. It maps what the data must cover, generates candidates with a cheap LLM, checks every row with small decision models, and fills the gaps until the map is full. Every row ships with its proof.**

Pitch line: *"The LLM writes, and small decision models check every row. The strong model only looks at the rows where the checks disagree."*

## 2. The product, from the user's side

| Step | What the user does | What Bob does |
|---|---|---|
| 0. Sign in + Connect AWS | Signs in (Cognito). On the Account screen, deploys the `BobBedrockAccess` role from the template with one CLI command (`aws cloudformation deploy --template-file bedrock-role.yaml --stack-name BobBedrockAccess --capabilities CAPABILITY_NAMED_IAM --parameter-overrides BobAccountId=<id> ExternalId=<ext>`). In the AWS access panel, pastes the role ARN, picks the Bedrock region, clicks **Verify**. In the Models panel, picks the model for each role (writer, planner, judge, fallback; defaults Haiku 5.5 / Sonnet 5.5) and clicks **Verify** | Makes the user profile with a fixed external id. Shows Bob's account id, the external id, the template download and the CLI command. AWS verify does the AssumeRole. Models verify makes one tiny real call per role and checks the JSON output. Both show the exact error on failure (D26, D27, D33). A job cannot start until both are verified |
| 1. Goal | Types a goal, adds sources (website URL, file uploads, Notion / Confluence / Jira / Google Drive through Composio), sets row count and budget, optionally uploads seed examples | Fetches everything: Firecrawl for URLs, Composio for internal apps, parsers for files |
| 2. Plan | Reviews the coverage map: a grid of topic x case type. Personas and difficulty are mixed inside each cell; the user edits their weights as chips. Turns cells on or off, edits personas, clicks **Start** | Reads the material (chunk, filter, Jev triage, topics, ScaleDown Extract evidence), then the Planner proposes the map with notes ("Your seeds cover 4 of 14 topics") and a cost estimate (D29) |
| 3. Build | Watches the map fill live; opens any row to see its source spans and checks; opens any rejected row to see why | Writer makes candidates per cell; the cascade verifies each one; only verified rows are kept |
| 4. Fill gaps | Watches round 2 and 3 target thin and hard cells | Gap controller: empty cells, cells with high rejection rates, under-covered persona and difficulty values, (stretch) cells where the base model fails |
| 5. Result | Spot-checks a 50-row sample (thumbs up / down), downloads the dataset in a chosen preset and format | Data quality report: coverage per cell and per persona and difficulty, pass rate per check, reject reasons, judge agreement, Jev accuracy from the spot-check, cost vs frontier-only. DPO pairs: for a share of kept rows, Bob synthesizes a flawed twin reply, and keeps the pair only when the checks reject the twin (D30) |
| 6. Docs change (P1) | Clicks **Re-sync** | Re-fetches, diffs, re-verifies stale rows, regenerates only affected cells |

Bob does **not** train models (D20).

## 3. Architecture

```
 Sources ──────────────────────────────────────────────────────────────────────── Gunbir
   URL ──► Firecrawl (crawl, markdown)
   Notion / Confluence / Jira / Drive ──► Composio (OAuth, fetch) ──►  Document[]
   Uploads ──► parsers (PDF, DOCX, MD, HTML, TXT, CSV)

 Read ─────────────────────────────────────────────────────────────────────────── Aaditya
   chunk (heading-aware) ► heuristic filter ► embed + dedup (model2vec)
   ► Jev triage (useful / boilerplate / PII / injection)
   ► topics (k-means + Writer names + ScaleDown Summarize briefs)
   ► ScaleDown Extract ► EvidenceIndex (features, settings, limits, numbers, URLs + verbatim spans)

 Plan
   Planner model (default Sonnet 5.5) ► coverage map: cells = topic x case_type (CELL_AXES);
   persona and difficulty = mix axes with weights, mixed inside each cell (D29) ► user edits ► Start

 Build loop (rounds 1..3)
   Writer model (default Haiku 5.5, batched, prompt-cached where the model supports it, ScaleDown Compress) ► candidates
     (each batch of 5 rotates persona and difficulty by their weights)
   Verify:  Tier 1 code ► Tier 2 Jev + Extract name check ► route by confidence ► Tier 3 judge model (default Sonnet 5.5, ~5%)
   Gap controller ► next round targets thin / hard cells and under-covered mix values
 After the loop
   DPO (DPO_MODE=synthesize): Writer model makes a flawed twin for DPO_RATE of kept rows ► tier 1 + 2
   ► keep the pair only if a content check rejects the twin (D30)

 Ship
   Report ► presets (OpenAI chat, ShareGPT, Alpaca, ModelForge, DPO, full) ► JSONL / JSON / CSV / Parquet
   + bob_manifest.json + provenance.parquet

 Web ──────────────────────────────────────────────────────────────────────────── Gunbir
   FastAPI routes + SSE  ◄──►  React UI: Sign in ► Account (Connect AWS) ► Setup ► Plan
                                          ► Build (live map + feed) ► Row inspector ► Report
   Auth (D27): Cognito user pool; the UI uses Amplify v6 and sends `Authorization: Bearer <access token>`;
               `api/auth.py` checks the JWT with the pool JWKS; every job has an `owner_id`

 Deploy (AWS serverless, CONTRACTS §13, D25) ───────────────────────────────────── Aaditya
   Browser ──► CloudFront (one domain)
                 ├─ default ──► S3 frontend bucket (React build; SPA rewrite to /index.html)
                 └─ /api/*  ──► Lambda Function URL (RESPONSE_STREAM)
                                FastAPI + Lambda Web Adapter (short routes + SSE), role BobApiRole
                                  │ JWT check (Cognito JWKS) ► current_user()
                                  │ create_job / resync ──► ecs.run_task ──► Fargate worker (one per job)
                                  │ approve / cancel    ──► control + approved plan in DynamoDB (worker polls every 1 s)
                                  └ SSE ◄── polls DynamoDB events every 500 ms; watchdog on heartbeat (D31)
   Fargate worker: same image, role BobWorkerTaskRole, `python -m bob.worker <job_id> <mode>`:
     ingest ► read ► plan ► wait for approval ► build loop ► DPO ► report ► export ► exit
     heartbeat every 10 s (also while it waits for approval)
   LLM layer (D33): pipeline code calls get_llm(job, role) for writer / planner / judge / fallback;
                  it never names a vendor model. llm/registry.json gives JSON mode, cache and prices per model
   Bedrock (D26): API (verify) and worker ──► sts:AssumeRole (external id) ──► BobBedrockAccess role
                  in the USER's AWS account ──► Bedrock Converse API (any Bedrock model) in the user's region
                  (billed to the user); credentials refresh 300 s before expiry
   OpenAI-compatible (P1): any chat completions endpoint (base URL + user API key); the key is
                  encrypted with the KMS key `alias/bob-user-keys` and never returned to the client
   Cognito: user pool in stack `BobData` (email sign-in, PKCE, managed login domain, invite only)
   State:   DynamoDB table `bob` (user profiles `USER#<sub>` / `PROFILE`, job list per user, job summary + control,
            events, rows) + S3 data bucket (job.json, approved plan, docs, chunks, exports, uploads, cache)
   Secrets: Secrets Manager `bob/keys` (Jev, ScaleDown, Firecrawl, Composio). No user AWS keys are stored.
   Network: default VPC, public subnets, egress-only security group, no NAT.
   IaC:     AWS CDK v2 (Python) in `infra/`, stacks `BobData` + `BobApp`; `infra/deploy.sh` deploys in < 15 min
            `infra/templates/bedrock-role.yaml` = the template each user deploys in their own account
```

Local mode (`BOB_ENV=local`) stays the default for development: in-memory + `runs/` on disk, in-process asyncio runner, in-memory event bus, `BOB_AUTH=none` (user id `local`), `BOB_BEDROCK_AUTH=default` (default boto3 chain). All checkpoint-1 work and all tests run in local mode first. `BOB_ENV=aws` switches every backend at once through `core/backends.py`. The orchestrator code is the same in both modes.

## 4. Where Jev and the CDMs work

| Stage | Jev | ScaleDown CDMs |
|---|---|---|
| Read | Triage each chunk (4 questions per call) | **Extract** builds the evidence index with verbatim spans; **Summarize** writes topic briefs |
| Generate | | **Compress** shrinks context; briefs replace full pages in Writer prompts |
| Verify | One call per candidate, 5 questions (3 shared + 2 per case type, CONTRACTS §4); calibrated probability routes the row | **Extract** pulls every feature / setting / URL from the reply; code checks each against the evidence index (invented-feature detector) |
| "Not in docs" rows | Confirms the top-5 retrieved chunks do not answer the question | Extract name check: for unanswerable and partial rows, a name that matches `absent_topic` (`ABSENT_MATCH` 85) is exempt, so a correct "the docs do not cover X" reply passes (D28). Never exempt for answerable or false-premise rows |
| DPO flawed replies | Tier 2 checks the flawed twin (no judge) | Extract name check catches the invented detail; the pair is kept only if a content check (not `format` or `dedup`) rejects the twin (D30) |
| Gap fill | Labels kept rows with their real topic, so coverage is measured, not assumed | |
| Report | Spot-check measures Jev's real accuracy on this job | Spans power the row inspector |

The `numbers` check also allows numbers that appear in the user turn (`NUMBERS_ALLOW_USER=all`), so a correct "It is 30 days, not 60" reply passes; `jev.corrects` still catches a reply that accepts the wrong value (D28).

Real fallbacks (no stubs): Jev -> ScaleDown Classify -> fallback model JSON. Extract -> fallback model extraction with the same verbatim-span check. The fallback model is configurable (default = the writer model). The UI shows a badge when a fallback is in use.

## 5. Team and agents

### Aaditya: AI, backend logic and deployment (agents A1 to A5)

| Agent | Scope | Owns |
|---|---|---|
| **A1 Core** | Shared models (incl. `UserProfile`, `BedrockAccess`, `JobOptions`, `Control`), config (with the AWS, auth and BYO Bedrock vars) and `settings_for(job)`, backend protocols + local implementations (`blobs`, `store`, `events`, `runner`, `backends` factory), events + SSE log, cost ledger, cache of real responses through `Blobs`, model-agnostic LLM layer (`LLMClient` protocol, `get_llm(job, role)`, Bedrock Converse client, model registry, OpenAI-compatible client P1), Bedrock credentials (default chain or assume role with refresh), orchestrator state machine (owner checks, 412 / 429 rules, watchdog, user profile and verify), `run_job` (the full job body, used by both runners) and build loop | `core/*`, `config.py`, `llm/client.py`, `llm/bedrock.py`, `llm/openai_compat.py`, `llm/registry.py`, `llm/registry.json`, `llm/credentials.py`, `orchestrator.py`, `pyproject.toml`, `.env.example` |
| **A2 Read** | Jev client + fallback chain, ScaleDown client, chunking, filters, embeddings, dedup, triage, topics, evidence index, retriever | `clients/*`, `pipeline/chunk.py filters.py embed.py triage.py topics.py evidence.py` |
| **A3 Plan + Write** | Planner (coverage map with cell axes + mix axes), target allocation (`CASE_MIX`, `MAX_CELLS`), Writer prompts and generation for all 4 case types (fill `absent_topic` for unanswerable and partial), `generate_flawed()` for DPO twins, gap controller | `pipeline/planner.py generate.py gaps.py`, `pipeline/prompts/planner.md writer*.md writer_flawed.md` |
| **A4 Verify + Ship** | 3-tier cascade (absent-topic exemption, user-turn numbers), judge prompt, `build_dpo_pairs()` (synthesize / pair / off), report (incl. `mix_coverage`), presets, formats, manifest; stretch: base-model probing | `pipeline/verify.py report.py probe.py`, `pipeline/prompts/judge.md`, `export/*` |
| **A5 Deploy** | AWS serverless deployment (CONTRACTS §13): aws implementations of the A1 protocols (boto3 in `asyncio.to_thread`, incl. `Runner.is_running`), secrets loader, Fargate worker entry, Docker image with the Lambda Web Adapter (copies `infra/templates/` to `/app/infra/templates/`), CDK stacks `BobData` (with the Cognito user pool and the KMS key `alias/bob-user-keys`) + `BobApp` (fixed role names `BobApiRole`, `BobWorkerTaskRole` with `sts:AssumeRole`; KMS: API role Encrypt + Decrypt, worker role Decrypt only), the user role template, deploy script, root README (setup, deploy, BYO AWS steps); tests on real DynamoDB and S3 (no moto, no LocalStack: D23) | `bob/aws/blobs.py store.py events.py runner.py secrets.py`, `bob/worker.py`, `backend/Dockerfile`, root `.dockerignore`, `infra/**` (incl. `infra/templates/bedrock-role.yaml`), root `README.md` |

### Gunbir: frontend and integrations (agents G1 to G4)

| Agent | Scope | Owns |
|---|---|---|
| **G1 API + Files** | FastAPI app, all routes in CONTRACTS §6 (incl. `/config/public`, `/me*` with `/me/models*`, file `/url` route), auth dependency `current_user()` (Cognito JWT or `local`), SSE endpoint, uploads, file parsers, `fetch_documents()` dispatch, `/health` with real key checks | `api/*` (incl. `api/auth.py`), `connectors/__init__.py upload.py parsers.py` |
| **G2 Connectors** | Firecrawl (crawl with live progress), Composio (OAuth connect, browse, fetch for Notion, Confluence, Jira, Google Drive; `user_id` per user), re-sync diff, demo corpus cache | `connectors/firecrawl.py composio.py sync.py`, `demo/*` |
| **G3 UI: Setup + Plan + Account** | Vite + React + TS shell, API client (auth header), SSE helper (`@microsoft/fetch-event-source`), `types.ts`, auth wrapper (Amplify v6 Authenticator, config from `/api/config/public`), Account screen (AWS access panel: template download, CLI command, role ARN, region, Verify; Models panel: provider and model id per role, advanced JSON mode / cache, price overrides, Verify), Setup screen (goal, sources, connectors, uploads, budget), Plan screen (topic x case type grid, mix-axis weight chips, estimate, Start) | `frontend/src/api/*`, `frontend/src/auth/*`, `frontend/src/screens/Account*`, `Setup*`, `Plan*`, app shell |
| **G4 UI: Build + Results** | Live Build screen (map heatgrid, counters, cost meter, row feed, reject reasons), Row inspector (messages, checks, highlighted source spans), Report screen (charts, persona and difficulty breakdown, spot-check panel, export and downloads) | `frontend/src/screens/Build*`, `Row*`, `Report*`, `frontend/src/components/viz/*` |

Gunbir's agents call the backend only through `Orchestrator` and `fetch_documents()`. Aaditya's agents never touch `api/`, `connectors/` or `frontend/`. A5 owns `infra/`, `backend/Dockerfile` and the root `README.md`; other agents send README text through `CHANGES_REQUESTED.md`. A5 asks A1 for changes to `pyproject.toml` (A1 adds `boto3` at T+0:15 and `pyjwt[crypto]`).

## 6. Timeline (4 hours)

### Before T+0:00 (both builders, 15 minutes, not part of the 4 hours)
This list keeps only things that must exist before T+0:00. Each provider's first real call is the first task of its owner agent ("research at first use", D32, section 13).
- [ ] Accounts and API keys exist: AWS (Bob hosting account), OpenRouter (Jev), ScaleDown, Firecrawl, Composio.
- [ ] Demo Notion workspace: 5 to 10 real internal-style pages (support FAQ, escalation policy, known issues) for the demo product.
- [ ] Repo: `backend/` and `frontend/` folders, branches `aaditya/*` and `gunbir/*`, `.env` shared out of band (never committed).
- [ ] AWS (A5): run `cdk bootstrap aws://<account>/<region>` (default region us-east-1).
- [ ] AWS (A5): Docker Desktop runs. Node 20 is installed. Run `npm i -g aws-cdk`.
- [ ] AWS (A5): a local `secrets.json` holds the API keys (never committed).

### T+0:00 to T+0:20: Lock
| Agent | Task |
|---|---|
| A1 | `core/models.py` exactly as CONTRACTS §2 (incl. `UserProfile`, `BedrockAccess`, `JobOptions`, `Control`), `config.py`, `pyproject.toml`, empty `orchestrator.py` with the §7 signatures. Also: protocol stubs + local implementations in `core/blobs.py store.py events.py runner.py backends.py`; the new config vars (CONTRACTS §9); `boto3` and `pyjwt[crypto]` in `pyproject.toml`. Commit by T+0:15. Research at first use: the default Bedrock model IDs / inference profiles with the first real Bedrock call (T+0:20) |
| A2 | Jev and ScaleDown clients with real calls (research at first use); confirm the request and response shapes; write them into CONTRACTS §5 if they differ |
| A3 | First LLM call through `get_llm(job, role)` and the `llm/bedrock.py` Converse draft (with A1); first Writer prompt tested on the first real smoke page (G2 commits it by T+0:10) |
| A4 | `prompts/judge.md`; export preset functions (pure code, no external calls) |
| A5 | Confirm the Bob hosting account and region (default us-east-1). CDK app skeleton; deploy `BobData` with the Cognito user pool; set the secret value (`aws secretsmanager put-secret-value --secret-id bob/keys --secret-string file://secrets.json`); post the table, bucket, secret, user pool id, client id and domain to all agents (A1 adds them to `.env.example`) |
| G1 | FastAPI skeleton, `/health` with real key checks, CORS, run script; then `POST /uploads`, `POST /jobs` and the MD parser by T+0:45 (needed for the thin path) |
| G2 | First real Firecrawl page -> `demo/smoke/` by T+0:10 (research at first use), then 3 to 5 pages total -> `demo/smoke/*.md`; 10 real seed questions -> `demo/smoke/seeds.jsonl` |
| G3 | Vite + React + TS scaffold, router, layout, `types.ts` from CONTRACTS §2 |
| G4 | Design the Build screen layout and the heatgrid component against `types.ts` shapes |

### T+0:20 to T+1:30: Build the core
| Agent | Deliverable by T+1:30 |
|---|---|
| A1 | **Thin real path by T+0:50** (CONTRACTS §12). Then: local `Store` with disk persistence and user profiles, local event bus + replay (both behind the protocols that A5 implements for aws), ledger with frontier-only estimate, full build loop with rounds and budget guard, `settings_for(job)`. `llm/credentials.py` (default chain + assume role with botocore `RefreshableCredentials`); `llm/client.py`, `llm/bedrock.py` (Converse), `llm/registry.py` + `registry.json` (research the registry capabilities by T+1:00). Orchestrator: `get_or_create_user`, `update_bedrock`, `verify_bedrock`, models verify per role, 412 / 429 rules, heartbeat + watchdog. Research the prices by T+1:30 |
| A2 | chunk, filter, embed, dedup, triage, topics with briefs, EvidenceIndex + Retriever; all tested on `demo/smoke/` with real calls |
| A3 | Planner returns a valid `Plan` for the smoke corpus (cell axes topic x case type, mix axes with weights, `MAX_CELLS`); Writer works for all 4 case types and fills `absent_topic`; batched (5 per call), prompt caching on |
| A4 | Tier 1 + tier 2 + routing + tier 3 judge working on real candidates (with the absent-topic exemption and user-turn numbers); JSONL + Parquet export for `openai-chat` |
| A5 | `backend/Dockerfile`, `.dockerignore`; `bob/aws/*` against A1's protocols (incl. `Runner.is_running`, `RunnerBusy`), tested on real DynamoDB and S3; `bob/worker.py` (heartbeat); `BobApp` stack with fixed role names `BobApiRole`, `BobWorkerTaskRole` and `sts:AssumeRole` on `BobBedrockAccess*`; `infra/templates/bedrock-role.yaml`. **By T+1:15:** the CloudFront URL serves the UI, and `/api/ping` + `/api/health` work there with the current backend code |
| G1 | All routes in CONTRACTS §6 wired to the Orchestrator; `api/auth.py` (`current_user()`, `BOB_AUTH=none` / `cognito`); `/config/public` and `/me*` routes (incl. `PUT /me/models`, `POST /me/models/verify`); owner check (404); SSE with `Last-Event-ID` replay; uploads + parsers for PDF, DOCX, MD, HTML, TXT, CSV |
| G2 | Firecrawl connector with page progress; Composio connect + browse + fetch for Notion (research the enabled toolkits and tool slugs by T+0:45); full demo crawl cached to `demo/corpus/` |
| G3 | Auth wrapper (Amplify v6, config from `/api/config/public`) and API client with the auth header; Account screen (AWS access panel + Models panel); Setup screen (goal, URL, uploads, connector buttons with real OAuth popup, row count, budget, seeds); Plan screen (topic x case type grid, mix-axis weight chips, notes, estimate, Start) |
| G4 | Build screen on live SSE: heatgrid, counters, cost meter, row feed with reject reasons |

### T+1:30: Checkpoint 1 (merge to `main`, 10 minutes)
**Pass:** In the browser, a user enters a goal + the smoke URL, sees a real plan, clicks Start, watches real rows stream in with real verdicts, and downloads a real JSONL file. No hard-coded data anywhere. This test runs in local mode (`BOB_AUTH=none`, `BOB_BEDROCK_AUTH=default`).
**Cloud pass:** the CloudFront URL serves the UI, `/api/ping` + `/api/health` return real results there, sign-in works on the CloudFront URL, and `/api/me` returns the profile.
If it fails: all 9 agents fix the break first; nothing new starts.

### T+1:40 to T+2:50: Complete the product
| Agent | Deliverable by T+2:50 |
|---|---|
| A1 | Gap rounds wired end to end; cancel; resync orchestration (P1); concurrency tuned so 500 rows finish in under 10 minutes |
| A2 | Real fallback chains tested (force a Jev failure, see ScaleDown Classify take over); triage and evidence quality pass on the full demo corpus |
| A3 | Gap controller (deficit + rejection-rate boost + mix-value boost); `generate_flawed()` + `prompts/writer_flawed.md`; persona and difficulty diversity checked by reading 50 real rows; prompt fixes |
| A4 | `build_dpo_pairs()` (synthesize mode), full report with `mix_coverage`, all presets and formats, manifest + provenance.parquet, stratified train/eval split |
| A5 | Deploy the checkpoint-1 merge. Create the demo user (`aws cognito-idp admin-create-user`) and connect it to the team's account through the same template. **By T+2:00:** real job in the cloud with the demo user's assume-role Bedrock access: create -> Fargate worker -> plan -> approve -> rows on SSE through CloudFront -> file download from S3. Measure the worker cold start. Test SSE reconnect (set `BOB_SSE_MAX_S=60` for one test). Cancel stops the job in 5 s. Kill one worker and see the job end in `error`. Test the cross-account path with a second AWS account if one is available |
| G1 | Error handling: provider errors shown in the UI; 412 / 429 messages; `/sources/preview`; job list (own jobs only) |
| G2 | Composio Jira and Confluence (or Google Drive) fetch; `sync.py` diff for re-sync |
| G3 | Job list / history page; Setup preview of fetched documents; polish |
| G4 | Row inspector with source span highlights and check list; Report screen with persona and difficulty breakdown, spot-check panel and downloads (through the file `/url` route) |

### T+2:50: Checkpoint 2 (merge, 10 minutes)
**Pass:** All P0 items (section 8) work end to end on the real demo corpus (Firecrawl site + Notion through Composio): sign in -> Connect AWS (verified) -> models verified -> job -> rows -> download; 500+ kept rows, one gap round, report complete, `openai-chat` and `full` downloads open. This test runs **on the CloudFront URL** (P0). P1 items finish in T+3:00 to T+3:30.

### T+3:00 to T+3:30: Hardening and P1 / stretch
- Everyone: fix bugs found at checkpoint 2.
- If green: re-sync (P1), base-model probing (stretch, A4), UI polish (G3, G4), Advanced options panel (G3, P1).
- A5 (P1): resync mode in the worker; origin-secret header (CloudFront adds `X-Bob-Origin`; the API rejects calls without it, so nobody can call the Function URL directly); AWS Budgets alarm; presigned uploads; a CloudWatch Logs Insights query for errors; CloudFormation quick-create link (research the public template URL).

### T+3:30: Feature freeze
### T+3:30 to T+4:00: Ship
- A5: deploy the frozen `main` (tag `demo`) once. Run the demo job once on the CloudFront URL. Keep localhost as the backup.
- Full real run of the demo on a fresh job; keep it as the backup job (and screen-record it).
- A5: root README with setup, deploy and BYO AWS steps; rehearse the demo 2 times.
- After the event: run `cdk destroy --all` (the buckets use DESTROY + autoDeleteObjects).

## 7. Definition of done at T+3:30 (P0 + P1, all real)
1. A new user can create a job from a public URL, an uploaded file, and a Notion page in one job.
2. The plan screen shows a real coverage map from the Planner (topic x case type, with persona and difficulty mix weights), and edits change the build.
3. The build runs real Writer, Jev, ScaleDown and judge calls; rows stream live; rejected rows show their reason.
4. At least one gap round runs and targets the thin cells.
5. Every kept row opens to its source spans and its passed checks.
6. The report shows coverage (per cell and per persona and difficulty), pass rates, reject reasons, judge agreement, cost and frontier-only estimate, and the spot-check updates it.
7. Exports: `openai-chat`, `sharegpt`, `modelforge-chat`, `dpo`, `full` in JSONL and Parquet, plus manifest and provenance. DPO pairs are synthesized flawed twins that a content check rejected.
8. A real provider failure shows an error or a fallback badge in the UI, and the job does not hang. A dead worker ends the job in `error` (watchdog); it does not hang.
9. A user signs in with Cognito. A user sees and opens only their own jobs (other jobs return 404).
10. A user connects their own AWS account on the Account screen; verify passes; the job's Bedrock calls run through the assumed `BobBedrockAccess` role.
11. A user picks the model for each role (any Bedrock model, through Converse); models verify passes per role; the job uses the chosen models. OpenAI-compatible endpoints work (P1).
12. Items 1 to 11 work on the CloudFront URL: the API runs on Lambda, each job runs in its own Fargate worker, rows stream on SSE through CloudFront, and downloads come from S3.
13. `infra/deploy.sh` deploys both stacks from a clean checkout in less than 15 minutes and prints the CloudFront URL.

## 8. Priorities and cut lines
| Priority | Items |
|---|---|
| **P0** (must work at checkpoint 2) | URL + upload + Notion sources; read pipeline; plan + edit; build with 3-tier verification; at least one gap round; live UI; row inspector; report; JSONL + Parquet in `openai-chat` and `full`; Cognito sign-in; owner checks; BYO Bedrock through assume role with credential refresh; Account screen with template download + CLI command + verify; configurable models on Bedrock (any provider family) through Converse + registry + verify per role; worker heartbeat + watchdog; deploy: both stacks, aws backends, worker on Fargate, SSE through the Function URL, checkpoint-2 pass on the CloudFront URL, deploy script |
| **P1** | Gap round 3; DPO pairs (synthesize mode); job list page; Jira + Confluence / Drive; other presets and formats; re-sync; spot-check; Advanced options panel (`JobOptions`); CloudFormation quick-create link; self sign-up (`BOB_SIGNUP=open`); `openai_compatible` provider with KMS-encrypted keys; model picker (`/me/models/available`); per-job model override in the Advanced panel; deploy: resync in the cloud, origin-secret header, budget alarm, presigned uploads, logs query |
| **Stretch** | Base-model probing; multi-turn rows |

Cut order if late: stretch -> re-sync -> extra Composio toolkits -> extra presets -> DPO. Never cut verification or the row inspector; they are the product.
Deploy cut line: if the cloud job path fails at T+3:30, demo on localhost and show the deployed UI + `/api/health`.

## 9. Demo (3 minutes)
**Where:** the CloudFront URL (deployed tag `demo`). Backup: localhost.
**Before the demo:** the demo user is already signed in, and AWS is already connected (the team's own account through the same template).
**Corpus:** a sponsor's public docs (default: Firecrawl's docs) via Firecrawl, plus 5 to 10 internal-style Notion pages (support FAQ, escalation policy, known issues) via Composio.
**Goal:** "First-reply support assistant for Firecrawl. Use only our docs. If the docs do not cover it, say so and hand off to a human."

1. **0:00 Hook.** "Every synthetic data tool asks an LLM to write data and hopes it is right. Bob checks every row."
2. **0:15 Sources.** Paste the docs URL; click Notion, pick the internal pages. Firecrawl pages and Notion pages count up. Optional (5 s): show the Account screen. "Bedrock runs in your own AWS account."
3. **0:40 Plan.** The coverage map appears: 12 topics x 4 case types = 48 cells, 4 personas and 3 difficulty levels mixed in each cell. Read one note aloud ("No seed examples cover rate limits"). Turn off one topic. Start.
4. **1:00 Build.** The map fills. Counters: generated, kept, rejected, judged. Click a rejected row: "Mentions 'webhook retries config', which is not in the docs." Click a kept "not in docs" row: Jev confirmed none of the top-5 passages answer it.
5. **1:50 Gap round.** "Round 2: 9 thin cells, 3 hard cells." The empty cells fill.
6. **2:20 Report.** Coverage 100%, pass rates per check, 5% sent to the judge, judge agreement, cost vs frontier-only (real numbers from the ledger; expect about $2 vs about $20).
7. **2:40 Ship.** Download OpenAI-chat JSONL and the DPO file. "Every row has a provenance record."
8. **2:55 Close.** "Your docs and internal wiki in, verified training data out."

Start the demo job early: the Fargate worker cold start takes 30 to 60 s before the plan shows.
Keep the backup job from T+3:30 open in a second tab. Keep localhost running as the backup if the cloud path fails.

## 10. Cost model (estimate, about 1,000 kept rows; A1 researches the prices by T+1:30)
Bedrock prices depend on the models the user chooses. The table uses the defaults (Haiku 5.5 writer and fallback, Sonnet 5.5 planner and judge). Prices come from the registry or the user's overrides; an unknown price shows as "unknown" (`price_unknown`).
**Billed to the user's AWS account (Bedrock, D26):**
| Part | Calls | Estimate |
|---|---|---|
| Planner model (default Sonnet 5.5) | 2 to 3 | about $0.10 |
| Writer model (default Haiku 5.5, about 1,700 candidates, 5 per call, cached prompts) | about 340 | about $0.40 |
| Writer DPO flawed replies (`DPO_RATE` 0.3: about 300 twins, 5 per call) | about 60 | about $0.07 |
| Judge model (default Sonnet 5.5, about 5% routed + 2% audit) | about 120 | about $1.00 |
| **Subtotal (user's AWS bill)** | | **about $1.57** |

**Paid by Bob:**
| Part | Calls | Estimate |
|---|---|---|
| Firecrawl crawl (25 pages) | 25 | credits |
| Jev triage + ScaleDown Extract + Summarize | about 500 | about $0.05 |
| Jev + Extract verification of 1,700 candidates | about 3,400 | about $0.15 |
| Jev + Extract checks of about 300 DPO flawed replies | about 600 | about $0.03 |
| Composio | | free tier |
| AWS: Fargate worker (2 vCPU / 4 GB, about $0.10 per hour, about 15 min per job with the approval wait) | 1 task per job | about $0.03 per job |
| AWS: Lambda, DynamoDB on-demand, S3, CloudFront | | less than $0.01 per job |
| AWS: Cognito user pool | | free tier covers the demo |
| AWS: Secrets Manager (1 secret) | | $0.40 per month |
| **Subtotal (Bob, per job, without the monthly secret)** | | **about $0.27** |

| | | |
|---|---|---|
| **Total per job (both parts)** | | **about $1.85** |
| Frontier-only (the judge model writes and judges every candidate, priced at the judge model price) | | about $20 |

The per-job budget guard (`budget_usd`) covers all buckets, also the Bedrock cost billed to the user. The ledger shows Bedrock cost as "billed to your AWS account". AWS idle cost is about zero: no NAT gateway and no always-on task.

## 11. Risks
| Risk | Mitigation |
|---|---|
| A key or endpoint fails at T+0:00 | Each owner makes the first real call as the first task (research at first use, D32); real fallback chains; `/health` shows each provider's state |
| Jev request shape differs from research | A2 confirms it in the first 20 minutes and updates CONTRACTS §5 |
| Bedrock model ID or region not enabled | A1 researches the model IDs at the first Bedrock call; use the cross-region inference profile; model IDs are editable per user |
| Bedrock throttling | Semaphores, backoff, batching 5 candidates per call, prompt caching |
| Rows look alike | Persona and difficulty mix axes rotate inside each batch; batched generation asks for 5 different rows; dedup; A3 reads 50 real rows at T+2:00 |
| Composio OAuth friction in the demo | Connect the demo account before the demo; keep the connected account id in `.env` |
| Firecrawl slow | Crawl cap 25; the demo corpus crawl is cached by T+1:30 (real data, cached) |
| Integration breaks at checkpoints | Contracts locked at T+0:20; one owner per file; thin real path by T+0:50 |
| Scope | Cut lines in section 8; freeze at T+3:30 |
| Fargate cold start (30-60 s) before the plan shows | `stage.progress` "starting worker" event from the API; small image; start the demo job early; measure at T+2:00 |
| Worker dies or capacity is full | Heartbeat every 10 s; watchdog sets `error` after 90 s when `Runner.is_running` is false; `RunnerBusy` -> HTTP 429 before the job is saved (D31) |
| CloudFront cuts an idle SSE stream | `: ping` every 15 s; origin read timeout 60 s; stream ends at 840 s and reconnects with `Last-Event-ID` |
| SPA fallback hides API errors | CloudFront Function on the default behavior only; never distribution-wide custom error pages (they turn API 404s into index.html) |
| Bob's roles cannot assume the user role | `/api/health` and `/me/aws/verify` on the cloud URL; fixed role names `BobApiRole`, `BobWorkerTaskRole`; both have `sts:AssumeRole` on `BobBedrockAccess*` |
| AssumeRole fails (wrong external id, trust policy, role name) | `/me/aws/verify` shows the exact STS error; fixed Bob role names |
| Model access not enabled or region lacks the chosen model in the user's account | Models verify makes one real call per role and names the model and region; model IDs are editable |
| A model does not support forced tool use or JSON output | Registry `json_mode`; `prompt` mode + one retry; the verify call checks JSON output per role |
| No prompt caching on the chosen model | The cost estimate uses the registry `cache` value; the plan estimate shows the higher cost |
| A weak judge model lowers quality | Judge agreement and the spot-check are in the report; the UI warns when judge == writer model |
| Marketplace models need a subscription | Verify shows the exact AccessDenied text; A5 researches the marketplace permissions |
| Unknown prices | `price_unknown` badge; the user can set prices in the Models panel |
| Role-chaining 1 h session limit | Credentials refresh 300 s before expiry; client rebuilt |
| Access token expires during a long SSE stream | fetch-event-source reconnects with a fresh token |
| Cross-account path not tested | Test with a second AWS account if available; same-account assume role for the demo |
| Lambda read-only disk breaks a module that writes to `runs/` | Rule: write only under `BOB_RUNS_DIR`; cloud health + thin path at T+1:15 to T+2:00 finds it |
| Public URL burns budget | Cognito sign-in (invite only); per-user active job limit (`BOB_MAX_ACTIVE_JOBS_PER_USER=1`); Bedrock is billed to the user's AWS account; per-job `budget_usd`, `BOB_MAX_WORKERS=2`, Lambda reserved concurrency 20, AWS Budgets alarm (P1) |
| Deploy breaks just before the demo | Freeze at T+3:30, deploy tag `demo` once, localhost backup |
| Docker build on Windows | Build with `--platform linux/amd64`; check Docker Desktop before T+0:00 |

## 12. Configuration
Env vars give the defaults. `JobOptions` (in `JobSpec.options`) overrides them per job. All pipeline code reads thresholds through `settings_for(job)` (A1), never directly from env. The manifest records the effective values. The full list is in CONTRACTS §9.

| Knob | Default | What it does |
|---|---|---|
| `CELL_AXES` | `topic,case_type` | Axes that form cells. The other axes are mix axes (D29) |
| `MAX_CELLS` | 120 | The Planner merges the smallest topics until enabled cells <= this |
| `CASE_MIX` | `answerable:0.5,partial:0.15,unanswerable:0.2,false_premise:0.15` | Share of rows per case type |
| `KEEP_P` | 0.9 | Confidence at or above this keeps the row |
| `REJECT_P` | 0.3 | Confidence below this rejects the row; a value between the two goes to the judge |
| `DPO_MODE` | `synthesize` | `synthesize` / `pair` / `off` (D30) |
| `DPO_RATE` | 0.3 | Share of kept rows that get a flawed twin |
| `NUMBERS_ALLOW_USER` | `all` | `all` / `false_premise` / `none`: numbers from the user turn are allowed in the reply (D28) |
| `EXTRACT_EXEMPT_ABSENT` | `true` | Exempt the absent topic in `extract.names` for unanswerable and partial rows (D28) |
| `BOB_AUTH` | `none` | `none` / `cognito`; aws deploy sets `cognito` (D27) |
| `BOB_BEDROCK_AUTH` | `default` | `default` / `assume_role`; aws deploy sets `assume_role` (D26) |
| `BOB_MAX_ACTIVE_JOBS_PER_USER` | 1 | More active jobs -> HTTP 429 (D31) |
| `BOB_DEFAULT_WRITER_MODEL` | `bedrock:global.anthropic.claude-haiku-5-5` | Default writer model for new profiles, format `<provider>:<model_id>` (D33) |
| `BOB_DEFAULT_PLANNER_MODEL` | `bedrock:global.anthropic.claude-sonnet-5-5` | Default planner model (D33) |
| `BOB_DEFAULT_JUDGE_MODEL` | `bedrock:global.anthropic.claude-sonnet-5-5` | Default judge model (D33) |
| `BOB_DEFAULT_FALLBACK_MODEL` | empty (= writer) | Default model for the Jev and Extract fallback chains (D33) |
| `BOB_MODEL_REGISTRY` | `bob/llm/registry.json` | Model capabilities and default prices per model id prefix (D33) |

The Setup screen has an "Advanced" panel for the `JobOptions` fields, also a per-job model override (G3, P1).

## 13. Research during the build
The team researches these as we go, not before T+0:00 (D32). Each item has an owner, a deadline and a default until it is confirmed.

| Item | Owner | When | Default until confirmed |
|---|---|---|---|
| Bob hosting AWS account + region | A5 | T+0:00 | us-east-1 |
| Default Bedrock model IDs / inference profiles | A1 | first Bedrock call (T+0:20) | `global.anthropic.claude-haiku-5-5`, `global.anthropic.claude-sonnet-5-5` |
| Converse with assumed-role session credentials (botocore `RefreshableCredentials`) | A1 | T+1:00 | boto3 `bedrock-runtime` client in `asyncio.to_thread` |
| Model registry capabilities (JSON mode, cache, temperature, prices) | A1 | T+1:00 | unknown models: `prompt` JSON mode, no cache, price unknown |
| Bedrock marketplace model permissions (`aws-marketplace:ViewSubscriptions`, `Subscribe`) | A5 | T+2:00 | default models only |
| Jev request/response shape, model version | A2 | T+0:20 | CONTRACTS §5 shape, `jev-1.13` |
| ScaleDown endpoint + Extract schema format | A2 | T+0:20 | `api.scaledown.xyz` |
| Composio toolkits enabled + tool slugs | G2 | T+0:45 | Notion only |
| Prices (default models, Jev, ScaleDown) | A1 | T+1:30 | registry values |
| CloudFormation quick-create template URL | A5 | P1 | CLI command only |
| Cross-account test account | A5 | T+2:00 | same-account role |

Non-English corpora: default no. Custom domain: default no. Login: answered by D27.
