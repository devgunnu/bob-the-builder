# Bob the Builder: Decision Log

Each entry: decision, why, what would change it.

## D1. Jev is the classifier (kept from the original hypothesis)
- **Why:** Jev is a non-generative decision model priced at $0.042 per M input tokens with free output, about 200 to 300 ms per call, multiple questions per call, calibrated probabilities. TypeSafe pitches it for corpus classification. About $0.06 to classify a 1M-token corpus.
- **Watch:** about 11.5% wrong at ≥ 90% confidence; follows option names over rubric (arXiv 2609.26758). Mitigated by descriptive option names, hand-label thresholds, a name-swap check.
- **Would change if:** we cannot get access tonight. Fallback order: Cloudflare Clef-flash (same API shape), then a distilled head on embeddings.

## D2. CDMs generate (v2, supersedes v1)
- **v1 was wrong:** research searched "Constrained Decision Models". The real term is ScaleDown's **Constrained Decoding Models** (launched 2026-10-13): Summarize writes constrained text, Extract returns typed fields with verbatim source spans, Classify returns label probabilities. $0.04/M input, output free, 50M free starter tokens.
- **Decision:** Extract builds a fact graph; code composes new examples with computed answers; a grammar bank + Jev ranking phrases them; Summarize writes topic explanations and summaries. Zero LLM tokens.

## D3. [Superseded by D12] Humpback (instruction backtranslation) as default writing mode
- **Why:** output tokens are about 95% of cost. Treating the source chunk as the answer means the writer emits about 60 tokens per example and answers are grounded by construction.
- **Trade-off:** answers read like documents. Assistant-rewrite tier for the top 20% fixes this.

## D4. [Superseded by D12] Writer backends: local vLLM, Haiku 5.5, templates
- **Why:** the team has a GPU box, so marginal writing cost is $0. Haiku 5.5 ($0.10 / $0.50 per M) is the reliable cloud fallback and powers the Anthropic prize story. Templates guarantee a $0 tier.
- **Rule:** if vLLM is not serving by 5:50pm, switch to Haiku and move on.

## D5. Free filters before any paid call
- Gopher / C4 / FineWeb heuristics, MinHash, semantic dedup, k-means diversity. Removes 40 to 80% of chunks for $0.

## D6. Every row carries provenance and a faithfulness score
- Source, page, chunk id, cluster, signal, Jev `supported` probability, cosine groundedness, writer, cost. Differentiates Bob from Easy Dataset, synthetic-data-kit, distilabel.

## D7. One canonical row, many projections
- Presets map fields; format writers serialize. Adding a format or preset never touches the pipeline.

## D8. JSONB means a Postgres-ready `.sql` export
- JSONB is a Postgres column type, not a file format. Bob ships DDL + inserts (random dollar-quote tag) + optional GIN index, plus an optional direct push via psycopg 3.

## D9. Standalone first; ModelForge through files, not imports
- Bob never imports ModelForge (it pulls in torch, Python 3.13, transformers 5.8). Integration = canonical file + `bob_manifest.json` + optional REST validation. Works with any trainer via presets.
- ModelForge quirks handled in presets: summarization uses prompt/completion; extractive QA folds into instruction following; one file per folder; no extra columns.

## D10. Partner tech only where it earns its place
- Firecrawl (URL ingest), Convex (live progress + public file links), Photon (text a URL, get a dataset). Anthropic: no pipeline role under D13 (Claude Code is the build tool). Skip Mercury (banking), HeyPCB, Nebula.

## D11. Dropped
- JEPA / LLM-JEPA: a training objective, not usable tonight.
- Local Clef: needs 41 to 54 GB VRAM and unmerged vLLM support.
- distilabel: good framework, too heavy to wire in five hours.
- Magpie / Self-Instruct / Evol-Instruct as defaults: ungrounded or 3 to 5x cost. Evol may be applied to the top 5 to 10% as a stretch.

## D12. [RETIRED by D18] Zero-LLM generation engine (v2)
- **Why:** the founder wants generation, not reformatting, without LLMs. Extract, Compose, Realize, Rank produces new multi-hop, computed, reasoning-trace and hard-negative rows that appear nowhere in the source, and answers are correct by construction.
- **Trade-off:** less open-ended voice than an LLM; quality is capped by extraction accuracy; best on fact-dense corpora.
- **LLM role:** none. Team chose strictly zero-LLM (D13).

## D13. [RETIRED by D16] Strictly zero-LLM (team decision, 2026-10-30)
- No general-purpose generative LLM anywhere: writing, judging, certifying or fallback. Enforced by an allowlisted model gateway and a build-failing import test.
- Jev access fallback is ScaleDown Classify (also a decision API), then an embedding classifier head. Never an LLM.
- The Opus 5.5 figure is a computed estimate, never a real run.

## D14. Demo on a real product, end to end
- Corpus: a real product's docs. Default proposal: ModelForge itself (dogfooding), see PLAN §9.
- Close the loop live: Bob builds the dataset, ModelForge fine-tunes a small model on the GPU box, and the tuned model answers questions about the product that the base model gets wrong.

## D15. [RETIRED by D18] [PROPOSED, awaiting team] Generator library for fine-tuning rows
- Bob synthesizes dataset rows for any corpus with zero LLM: knowledge from the fact graph, language from CDMs + grammars + deterministic transforms, judgement from Jev + verifiers.
- Eleven generators (research/07). Core tonight: task multiplier, corrupt-and-restore, constraint compositor, knowledge composer, abstention, preference pairs.
- ModelForge stays only a compatible export target (D9). Research/06's ModelForge-centred oracle idea is withdrawn.

## D16. [PARTLY RETIRED by D18] LLM proposes, Bob proves (v3, team decision)
- **Why:** hand-written templates can't cover every use case and the output reads as templated. An LLM is needed for generality and natural language.
- **Roles:** Architect (strong model, per corpus) writes the task taxonomy, extraction schema, generator programs, verifier code and unit tests (AutoIF-style). Writer (cheap model, per row) phrases rows with answer slots locked. Jev, ScaleDown and code verify every row.
- **Kept:** fact graph, computed answers, abstention / false-premise families, programmatic defect injection for DPO, provenance, all verifiers.
- **Eval:** human-written test set (incl. fake-feature questions) and a naive-LLM-data baseline, so results aren't circular.
- Details: research/09.

## D17. [PROPOSED] Position Bob for behaviour, not memorisation
- RAG beats unsupervised fine-tuning for knowledge (Ovadia et al., EMNLP 2024), so "a model that memorised your docs" is a weak pitch.
- Bob's main use case becomes RAFT-style data: question + relevant chunk + verified distractors -> cited answer, plus "not in the retrieved docs" abstentions. Second: narrow-skill distillation (extraction, classification, house-style replies, tool calls).
- Demo: 4 models with the same retrieval, scored on human-written questions; hallucination rate is the headline. Details: research/10.

## D18. Retire templates (v4, team decision, 2026-10-30)
- **Decision:** drop the templates concept completely. This retires the v2 question programs and grammar bank (D12), the v2 generator library (D15, research 07 and 08), and the v3 idea of an Architect LLM that writes generator code (the generator-code part of D16, research 09 sections 1 to 4). It also ends the zero-LLM generation role of the CDMs in D2.
- **Why:** templates cannot cover every use case, and the output reads as templated. LLM-written generator code needs a sandbox, unit tests and a repair loop that do not fit in a 4-hour build. A cheap Writer LLM that writes rows per coverage cell, checked by decision models, gives generality and natural language with less machinery.
- **Kept:** from D16, the verification ideas (every row checked by code, Jev and ScaleDown; failures dropped and counted; provenance on every row). From D17, the focus on faithfulness and abstention: "not in docs" and false-premise rows are first-class case types.
- **Would change if:** the Writer cannot produce rows that pass verification at a useful rate (for example, under 30% on the smoke corpus after prompt fixes).

## D19. Closed-loop data factory
- **Decision:** Bob is a loop: map, generate, verify, fill gaps. The Planner proposes a coverage map (topic x persona x case_type x difficulty; case types `answerable`, `partial`, `unanswerable`, `false_premise`). The user edits it. The Writer generates candidates per cell. The cascade verifies each candidate. The gap controller sends rounds 2 and 3 to thin and hard cells.
- **Why:** coverage is what prompting alone gets wrong (research 10, Q1). A map makes coverage visible, editable and measurable. The map is the quality-diversity idea (MAP-Elites, Rainbow Teaming) without training. The loop also makes the demo visible: the map fills live.
- **Would change if:** the map is too large to fill in the demo time (then cut the difficulty axis or cap the topics).
- **[Map shape superseded by D29]:** cells are now topic x case_type only. Persona and difficulty are mix axes inside each cell.

## D20. Bob makes data only; no training in the product
- **Decision:** remove the training step. Bob does not fine-tune or evaluate a tuned model. This replaces the live fine-tune in D14 and the model evals in D16 and D17.
- **Gap signals without training:** (1) coverage gaps (cells under target); (2) rejection rate per cell (a hard cell gets more weight); (3) base-model probing (stretch): ask a base model the kept questions and boost the cells where it fails.
- **Why:** a fine-tune and a fair eval do not fit in 4 hours with everything else, and the verification loop is the product (research 10). Student-in-the-loop training was considered and dropped (research 11).
- **Would change if:** the build finishes early and a trainer (for example ModelForge, through the export files in D9) can run a short job with no code change in Bob.

## D21. Verification cascade, and the roles of Jev and the CDMs
- **Decision:** 3 tiers per candidate (CONTRACTS section 4). Tier 1 is code: format, banned phrases, dedup, numbers. Tier 2 is one Jev call (questions by case type) plus a ScaleDown Extract invented-feature check against the evidence index. Calibrated probabilities route the row: keep at `confidence >= KEEP_P` (0.9); reject on a hard fail or under `REJECT_P` (0.3); else tier 3. Tier 3 is the judge model (default Sonnet 5.5), on about 5% uncertain rows plus a 2% random audit of kept rows.
- **Jev roles:** triage each chunk (useful, boilerplate, PII, injection); check every candidate; confirm that the top-5 retrieved chunks do not answer a "not in docs" question; label the real topic of each kept row, so coverage is measured.
- **CDM roles:** Extract builds the evidence index with verbatim spans and pulls feature, setting, URL and limit names from each reply. Summarize writes topic briefs. Compress shrinks Writer context. Classify is the first Jev fallback.
- **Guards:**
  - Jev is about 11.5% wrong at >= 90% confidence. Every kept answerable row needs both `jev.supported` and `extract.names`. The tier-3 audit measures the real error rate on each job.
  - **[Changed by D28]:** `extract.names` now has an absent-topic exemption for unanswerable and partial rows only. It has no exemption for answerable and false_premise rows.
  - Jev follows option names. Use descriptive names only, never `0/1`.
  - Jev is weak at arithmetic and dates. The tier-1 `numbers` check covers this in code. **[Changed by D28]:** numbers from the user turn are also allowed in the reply (`NUMBERS_ALLOW_USER`).
  - **[Changed by D28]:** `KEEP_P`, `REJECT_P`, the audit rate and the other thresholds are config defaults. A job can override them (`JobOptions`, read through `settings_for(job)`).
  - Extract field accuracy is about 89.5%. Code keeps only fields whose `span_text` is a verbatim substring of the input.
- **Real fallbacks (no stubs):** Jev -> ScaleDown Classify -> fallback model JSON. Extract -> fallback model extraction with the same verbatim-span check. The UI shows a badge when a fallback is in use.
- **Why:** "The LLM writes, and small decision models check every row. The strong model only looks at the rows where the checks disagree." The estimate is about $1.85 per 1,000 kept rows (DPO flawed replies included, D30), against about $20 frontier-only (PLAN section 10).
- **Would change if:** the audit shows low tier-2 vs tier-3 agreement (for example, under 85%). Then raise `KEEP_P` or send more rows to the judge.

## D22. [Superseded by D33; defaults kept] Models: Anthropic on AWS Bedrock
- **Decision:** Writer = Claude Haiku 5.5. Judge and Planner = Claude Sonnet 5.5. All calls go through `anthropic.AsyncAnthropicBedrock`, with prompt caching on the Writer system prompt and topic brief, and 5 candidates per Writer call. This replaces D4 (local vLLM) and the Opus 5.5 Architect question.
- **Why:** one provider and one set of AWS credentials for all generative calls. The cheap model does the volume. The strong model plans once and judges only the uncertain rows.
- **Would change if:** the model IDs or inference profiles are not enabled in our region at T+0:00. Then use the cross-region inference profile.
- **[Partly superseded by D26]:** the 3 model IDs are now per-user defaults for new profiles. The user can override them. Bedrock calls run in the user's own AWS account and region, through an assumed role, not with Bob's credentials. The model ID check moves to research at first use (D32).

## D23. Real-only development, no mocks
- **Decision:** no mock clients, no fake responses, no fake corpus, no hard-coded UI data. Every call to Bedrock, Jev, ScaleDown, Firecrawl and Composio is real from the first line of code. Tests run on `demo/smoke/` (a small real corpus) with small sizes.
- **Allowed:** a disk cache of real responses (`core/cache.py`). It never invents a response. `BOB_CACHE=0` turns it off.
- **Why:** mocks hide broken keys and wrong request shapes until the demo. The thin real path by T+0:50 makes failures show early.
- **Would change if:** nothing tonight. A provider that fails uses its real fallback (D21) or gets fixed.

## D24. Stack, integrations, demo and team split
- **Stack:** FastAPI backend with SSE (`Last-Event-ID` replay) and a React + TypeScript (Vite) frontend. Convex is dropped: SSE gives live progress. Photon / iMessage is dropped. This replaces D10.
- **Integrations:** Firecrawl for URLs. Composio for Notion, Confluence, Jira and Google Drive (OAuth, browse, fetch). Uploads (PDF, DOCX, MD, HTML, TXT, CSV). Optional seed examples (JSONL or CSV).
- **Demo:** a sponsor's public docs (default: Firecrawl's docs) through Firecrawl, plus 5 to 10 real internal-style Notion pages (support FAQ, escalation policy, known issues) through Composio. Goal: a first-reply support assistant that says so when the docs do not cover a question. This replaces D14.
- **Team:** Aaditya owns AI and backend logic, including the Jev and CDM implementations (agents A1 to A4: core, read, plan + write, verify + ship). Gunbir owns all frontend and integrations: API and SSE, uploads, Firecrawl, Composio (agents G1 to G4). One owner per file (CONTRACTS section 1).
- **Build window:** 4 hours. Checkpoints at T+1:30 and T+2:50. Feature freeze at T+3:30.
- **Would change if:** Composio OAuth fails for the demo account. Then the demo uploads the same real Notion pages, exported as markdown.
- **[v4.1 note]:** the team split is unchanged. New owned files: A1 `llm/credentials.py` and `.env.example`; A3 `prompts/writer_flawed.md` and `generate_flawed()`; A5 the Cognito user pool, fixed role names, `infra/templates/bedrock-role.yaml` and the root `README.md`; G1 `api/auth.py`; G3 `frontend/src/auth/*`, `frontend/src/screens/Account*` and the route `/account` (D26, D27).

## D25. Deploy to AWS serverless: Lambda API + Fargate job workers (team decision, 2026-10-30)
- **Decision:** CloudFront serves the React build from S3 and sends `/api/*` to a Lambda Function URL with response streaming. The API Lambda runs FastAPI through the AWS Lambda Web Adapter. It runs only short routes and SSE. Each job runs in one Fargate task (same image, `python -m bob.worker`). The task lives from ingest through plan approval to `done`. State is in DynamoDB (job summary, control flags, events, rows) and S3 (job document, docs, chunks, exports, uploads, cache). API keys are in Secrets Manager. Bedrock uses the IAM role. AWS CDK (Python) in `infra/` deploys two stacks: `BobData` and `BobApp`. Aaditya owns the deploy through a new agent, A5 Deploy (CONTRACTS section 13).
- **Local mode stays:** `BOB_ENV=local` keeps the in-memory store, the `runs/` folder and the in-process runner. A1 writes the store, events, blobs and runner behind protocols. A5 writes the aws versions. The orchestrator code is the same in both modes.
- **Why:** an API Lambda cannot keep a 10-minute job alive after it sends the response, but a Fargate task can. One task for each job keeps the read state (chunks, embeddings, evidence index) in memory across plan approval, and it has only one cold start. Idle cost is about zero (no NAT, no always-on task). An API on Fargate behind an ALB has less work, but the team chose Lambda for the API.
- **Costs:** Fargate cold start (30 to 60 s) before the plan shows. Uploads are limited to 6 MB. Routes must return in less than 25 s. SSE needs a heartbeat and reconnects every 14 minutes. The orchestrator getters become async.
- **Would change if:** the cloud job path fails at T+3:30. Then the demo runs on localhost and shows the deployed UI and `/api/health`.
- **[Partly superseded by D26 and D27]:** "Bedrock uses the IAM role" is replaced. In aws mode, Bob's roles assume the user's `BobBedrockAccess` role, and Bob's roles do not need `bedrock:InvokeModel*` (except with `BOB_BEDROCK_AUTH=default`, for the team's own tests). Bob's IAM roles get fixed names `BobApiRole` and `BobWorkerTaskRole`. `BobData` also holds a Cognito user pool. A job's worker reads the approved plan from `Control`, and a watchdog stops hung jobs (D31).

## D26. Bring your own AWS account for Bedrock inference (v4.1)
- **Decision:** Bedrock calls (all LLM roles: writer, planner, judge, fallback; D33) run in the user's own AWS account, and the user's account pays for them. Bob's own keys still pay for Jev, ScaleDown, Firecrawl and Composio.
- **Mechanism:** a cross-account IAM role with an external id. Bob stores no long-lived user keys.
  1. On first sign-in, Bob makes a `UserProfile` with a random `external_id` (uuid4). It never changes.
  2. The Account screen ("Connect AWS") shows Bob's AWS account id, the external id, a download of `bedrock-role.yaml` (`GET /me/aws/template`, file `infra/templates/bedrock-role.yaml`, owner A5) and one `aws cloudformation deploy` command. A quick-create link is P1.
  3. The template makes role `BobBedrockAccess` in the user's account. Trust: Bob's account root, with `sts:ExternalId` and `aws:PrincipalArn` in [`BobApiRole`, `BobWorkerTaskRole`]. Permissions: `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on `arn:aws:bedrock:*::foundation-model/*` and `arn:aws:bedrock:*:*:inference-profile/*` (all model families, D33), plus `bedrock:ListFoundationModels` and `bedrock:ListInferenceProfiles`. Some marketplace models also need `aws-marketplace:ViewSubscriptions` and `aws-marketplace:Subscribe` on first use (research, D32).
  4. The user pastes the role ARN and picks the Bedrock region. `BedrockAccess` holds only AWS access: `mode`, `role_arn`, `external_id`, `region`. The models are separate (`UserProfile.models: ModelRoles`, D33). `POST /me/aws/verify` does the AssumeRole check only. `POST /me/models/verify` makes one tiny real call per configured role. Both show the exact error on failure.
  5. A job cannot start until both checks pass (HTTP 412 `{"error": "connect AWS first"}` or `{"error": "verify models first"}`).
- **Credentials:** `llm/credentials.py` (A1) makes credentials from `BedrockAccess`. `mode="default"` uses the default boto3 chain (local dev). `mode="assume_role"` uses STS AssumeRole with the external id, session name `bob-<job_id>`. Role chaining limits a session to 1 hour, and a job can wait 60 minutes for approval. So credentials refresh `BOB_CRED_REFRESH_S` (300 s) before expiry (botocore `RefreshableCredentials` for the Converse client, D33).
- **Fixed role names:** Bob's roles are `BobApiRole` and `BobWorkerTaskRole` (CDK `roleName`). The user's trust policy stays valid across deploys.
- **Snapshot per job:** `create_job` copies `Job.bedrock` and `Job.models` from the profile. A later profile edit does not change a running job.
- **Config:** `BOB_BEDROCK_AUTH=default` (`default` | `assume_role`; the aws deploy sets `assume_role`), `BOB_ACCOUNT_ID`, `BOB_CRED_REFRESH_S=300`, `BOB_BEDROCK_DEFAULT_REGION=us-east-1`. The model defaults for new profiles come from `BOB_DEFAULT_*_MODEL` (D33). Bob's hosting region is separate from each user's Bedrock region.
- **Why:** a public Bob that pays for all Bedrock calls is an open cost risk. With this design, each user pays for their own generation, and Bob holds no user secrets. The ledger shows Bedrock cost as "billed to your AWS account".
- **Trade-off:** each user must deploy a CloudFormation stack and enable model access before the first job. The cross-account path has more failure points (external id, trust policy, region, model access). The verify route names the exact failure.
- **Demo:** the demo user is pre-connected to the team's own account through the same template (same-account assume role works). Test cross-account with a second account if one is available.
- **Would change if:** AssumeRole or the client refresh does not work by T+2:00. Then the demo runs with `BOB_BEDROCK_AUTH=default` on the team's account.

## D27. Accounts and auth: Cognito user pool + IAM (v4.1)
- **Decision:** a Cognito user pool in stack `BobData` (A5): email sign-in, app client without a secret, PKCE, managed login domain. Sign-up is invite only by default (`BOB_SIGNUP=invite`). The team creates the demo user with `aws cognito-idp admin-create-user`.
- **Frontend (G3):** AWS Amplify v6 with the Authenticator. It reads the auth config at runtime from `GET /api/config/public`, so one build runs on Vite dev and on CloudFront. `client.ts` adds `Authorization: Bearer <access token>` to every call. `EventSource` cannot send headers, so SSE uses `@microsoft/fetch-event-source`, which sends the header and `Last-Event-ID`, and gets a fresh token on reconnect. Downloads use `GET /jobs/{id}/files/{name:path}/url`, because a plain link cannot send the header.
- **API (G1, `api/auth.py`):** dependency `current_user()`. `BOB_AUTH=cognito` checks the access token with the pool JWKS (issuer, `token_use=access`, `client_id`, expiry). `BOB_AUTH=none` (local default) gives user id `local`. Open routes: `/ping` and `/config/public`. All other routes need a user.
- **Owner isolation:** `Job.owner_id`. `GET /jobs` lists only the user's jobs. Every `/jobs/{id}/*` route returns 404 when the owner is different. `/health` needs a signed-in user.
- **Composio:** the Composio `user_id` is `COMPOSIO_USER_PREFIX + UserProfile.id` (`bob-`), so each user's Notion and Jira connections are private. `COMPOSIO_DEMO_ACCOUNTS` applies to the demo user only.
- **IAM:** Bob's roles as in D26. The Lambda Function URL stays `AuthType NONE` behind CloudFront. The origin-secret header stays P1.
- **Why:** the public CloudFront URL had no login (old Q9). Anyone could start jobs, see other users' jobs and use the team's Composio connections. A user identity is also necessary for D26 (one AWS profile per user).
- **Trade-off:** more work in G1, G3 and A5, and one more failure point at sign-in. Local mode keeps `BOB_AUTH=none`, so the thin path and checkpoint 1 do not change.
- **Would change if:** Cognito sign-in does not work on CloudFront by checkpoint 2. Then the demo runs on localhost with `BOB_AUTH=none`.

## D28. Verification fixes, configurable (v4.1)
- **Problem 1 (`extract.names`):** a correct unanswerable reply names the missing feature ("The docs do not cover bulk PDF export"). Extract finds "bulk PDF export". It is not in the evidence index, so the row hard-fails as an invented feature. Partial rows have the same problem for the uncovered part.
- **Fix 1:** `Candidate.absent_topic` is now filled for unanswerable and partial rows. A3 Writer prompts fill it. For these 2 case types only, a name is exempt when rapidfuzz `token_set_ratio(name, absent_topic) >= ABSENT_MATCH` (85). The check detail lists exempt names. Answerable and false_premise rows never get the exemption: an invented name there is the hallucination we catch. The A3 check stays: `Retriever.top_k(absent_topic)` must not contain the absent topic. Config: `EXTRACT_NAMES_CASE_TYPES=answerable,partial,unanswerable,false_premise`, `EXTRACT_EXEMPT_ABSENT=true`, `ABSENT_MATCH=85`.
- **Problem 2 (`numbers`):** a good false-premise correction repeats the wrong number from the user ("It is 30 days, not 60"). 60 is not in the docs, so the row fails.
- **Fix 2:** numbers that are in the user turn are also allowed in the reply. Config `NUMBERS_ALLOW_USER=all` (`all` | `false_premise` | `none`). Tier-2 `jev.corrects` still catches a reply that accepts the wrong value.
- **Per-job overrides:** env vars give the defaults. `JobSpec.options: JobOptions` can override them (cell axes, max cells, case mix, `KEEP_P`, `REJECT_P`, audit rate, max rounds, overgen, DPO mode and rate, `NUMBERS_ALLOW_USER`, `EXTRACT_EXEMPT_ABSENT`). A1 adds `settings_for(job) -> EffectiveSettings` in `config.py`. All pipeline code reads thresholds through it, never directly from env. The manifest records the effective values. The Setup screen "Advanced" panel is P1 (G3).
- **Why:** without these fixes, the 2 case types that make Bob different (abstention and false premise) fail at a high rate, for correct replies.
- **Trade-off:** the exemption can let a real invented name pass if it fuzzy-matches the absent topic. The match applies only to unanswerable and partial rows, and Jev and the tier-3 audit still check them.
- **Would change if:** the audit shows invented names that pass through the exemption. Then raise `ABSENT_MATCH` or set `EXTRACT_EXEMPT_ABSENT=false` for the job.

## D29. Map shape: cells are topic x case_type; persona and difficulty are mix axes (v4.1)
- **Problem:** 12 topics x 4 personas x 4 case types x 3 difficulties = 576 cells. With 1,000 rows, most cells get 1 or 2 rows, but each Writer call makes 5. "Coverage 100%" is not possible.
- **Decision:** cells = `CELL_AXES` (default `topic,case_type`). `Axis` gains `role` (`cell` | `mix`) and `weights`. Persona and difficulty are mix axes: each Writer batch of 5 rotates mix values by their weights. `Cell.coords` has only the cell axis keys. `Row.coords` and `Candidate.coords` hold all 4 axis values, so the report still shows coverage per persona and per difficulty (`Report.mix_coverage`). `plan_gap_round` also boosts mix values that are under their weight.
- **Config:** `MAX_CELLS=120`, `MAX_TOPICS=20`, `MIN_CELL_TARGET=3`. The Planner merges the smallest topics until enabled cells <= `MAX_CELLS`. `CASE_MIX=answerable:0.5,partial:0.15,unanswerable:0.2,false_premise:0.15` replaces the hard-coded mix in `allocate_targets`.
- **Demo numbers:** 12 topics x 4 case types = 48 cells, about 20 rows per cell for 1,000 rows. The Plan screen grid is topic x case_type; mix axes show as chips with editable weights.
- **Why:** each cell gets enough rows for full Writer batches and a real coverage number. The persona and difficulty spread stays visible.
- **Trade-off:** the map cannot guarantee one row for each persona x difficulty combination in each cell. The mix is by weight, not by cell.
- **Would change if:** a job needs a cell per persona (for example a persona-specific dataset). Then set `cell_axes` in `JobOptions`.

## D30. DPO pairs: synthesize flawed twins (v4.1)
- **Problem:** the old rule pairs a kept and a rejected reply to the same user turn. Each candidate has a different user turn, and dedup removes repeats, so almost no pairs exist.
- **Decision:** `DPO_MODE=synthesize` (`synthesize` | `pair` | `off`), `DPO_RATE=0.3` (share of kept rows that get a flawed twin). For a sampled kept row, A3 `generate_flawed(row, ctx)` asks the Writer for one flawed reply to the same user turn, by case type: answerable adds one plausible detail that is not in the passages; partial also answers the uncovered part with invented details; unanswerable answers with confidence instead of abstaining; false_premise accepts the wrong premise. Prompt `prompts/writer_flawed.md`, 5 flawed replies per call, prompt-cached, ledger bucket `writer`, purpose `dpo`.
- **Proof:** A4 runs the flawed reply through tier 1 + tier 2 only (no judge). The pair is kept only when a content check rejects the flawed reply (not `format` or `dedup`). Otherwise Bob drops it. `DPOPair` gains `row_id`, `mode` (`synthesized` | `natural`) and `rejected_checks`.
- **Other modes:** `pair` is the old natural pairing (same normalized user turn in a cell). `off` makes no DPO file.
- **Order:** `build_dpo_pairs(rows, ctx)` runs after the build loop, before the report. The budget guard applies.
- **Why:** every pair is proof-backed: the checks show why the rejected reply is wrong. The flaws target the same hallucination types that the product prevents.
- **Trade-off:** more Writer calls (about 30% more rows, in batches of 5) and more tier-2 calls.
- **Would change if:** the Writer cannot make flawed replies that fail a content check at a useful rate. Then lower `DPO_RATE` or use `pair`.

## D31. Job robustness (v4.1)
- **Problem 1:** the worker could not read the approved plan. **Fix:** `Store.get_control(job_id) -> Control` with `state` (`approved` | `cancel`) and `plan`. In aws mode, META holds `control` and `plan_key` (S3 `runs/<id>/approved_plan.json`).
- **Problem 2:** the API could not tell if a worker runs. **Fix:** `Runner.is_running(job_id) -> bool`. Local: the asyncio task exists and is not done. Aws: `ecs.describe_tasks` on the META `task_arn`, running unless `lastStatus == STOPPED`. Cancel, the HTTP 409 rule and the watchdog use it.
- **Problem 3:** a dead worker left the job hung. **Fix:** the worker writes `Job.heartbeat_at` every `BOB_HEARTBEAT_S` (10 s), also while it waits for approval. A watchdog in `Orchestrator.get_job` and the SSE loop sets status `error` when the job is not terminal, the heartbeat (or `created_at`) is older than `BOB_HEARTBEAT_TIMEOUT_S` (90 s) and `is_running()` is false. It writes `Job.error = "worker stopped: <stoppedReason>"` and one `error` event, with a conditional update on META. No worker runs, so the single event writer rule stays.
- **Problem 4:** a full runner failed after the job was saved. **Fix:** `Runner.start` raises `RunnerBusy` at `BOB_MAX_WORKERS` tasks, or when the user has `BOB_MAX_ACTIVE_JOBS_PER_USER` (1) active jobs. `create_job` checks capacity before it saves the job. The route returns HTTP 429 `{"error": "too many running jobs"}`. Nothing is saved.
- **Why:** each fix removes one way that a job can hang or leave a broken record in the demo.
- **Trade-off:** 90 s timeout means a dead worker shows as `error` up to 90 s late. A shorter timeout can fail jobs during a Fargate cold start.
- **Would change if:** cold starts take more than 90 s. Then raise `BOB_HEARTBEAT_TIMEOUT_S`.

## D32. Open questions are researched during the build (v4.1)
- **Decision:** the team does not answer the provider questions before T+0:00. Each item has an owner, a deadline and a default (table in "Open questions" below). Each provider's first real call is the first task of its owner agent. The pre-start checklist keeps only things that must exist before T+0:00: accounts, API keys, Docker, Node, `cdk bootstrap`.
- **Why:** research before the start uses time that the build needs, and the first real call gives the true answer. D23 (real calls from the first line) makes wrong guesses show early.
- **Would change if:** a default is wrong and the fix blocks other agents. Then the owner posts the answer to the other agents at once.

## D33. Model-agnostic LLM layer (v4.1 addendum)
- **Decision:** every LLM role is configurable: `writer`, `planner`, `judge`, `fallback` (the model for the Jev and Extract fallback chains; default = the writer model). Claude Haiku 5.5 (writer, fallback) and Claude Sonnet 5.5 (planner, judge) stay only as defaults. Any model works.
- **Providers:** `bedrock` (P0): any Bedrock model or inference profile in the user's own AWS account (Anthropic, Amazon Nova, Meta Llama, Mistral, DeepSeek, Qwen, OpenAI gpt-oss, and more). It uses the Bedrock Converse API through boto3 in `asyncio.to_thread`, with the user's assumed-role credentials. No Anthropic SDK is in the request path, and `anthropic` is not a required dep. `openai_compatible` (P1): any OpenAI-compatible chat completions endpoint, with raw `httpx`. The user gives `base_url` and an API key. Bob encrypts the key with KMS (`alias/bob-user-keys`) and never returns it to the client (`key_set: true`).
- **Models:** `ModelConfig` (provider, model id, JSON mode, cache, price overrides) and `ModelRoles` (writer, planner, judge, fallback). `UserProfile.models`, `Job.models` (snapshot at `create_job`) and `JobOptions.models` (per-job override). `BedrockAccess` holds only AWS access. `CostSummary` adds `model_ids` and `price_unknown`.
- **Client (A1):** `llm/client.py` (`LLMClient`, `get_llm(job, role)`), `llm/bedrock.py` (Converse), `llm/openai_compat.py` (P1), `llm/registry.py` + `llm/registry.json`. The registry gives the capabilities per model id prefix: JSON mode (`tool`, `native` or `prompt`), cache support, `allows_temperature`, extra fields and default prices. Unknown models get safe defaults: `prompt` JSON mode, no cache, price unknown. Pipeline code calls `get_llm(job, role)` and never names a vendor model. Prompts are model-neutral (no prefill, no vendor-only tags).
- **Routes and UI:** `PUT /me/models`, `POST /me/models/verify` (one tiny real call per role), `GET /me/models/available` (P1). The Account screen has an "AWS access" panel and a "Models" panel (G3).
- **Config:** `BOB_DEFAULT_WRITER_MODEL`, `BOB_DEFAULT_PLANNER_MODEL`, `BOB_DEFAULT_JUDGE_MODEL`, `BOB_DEFAULT_FALLBACK_MODEL` (format `<provider>:<model_id>`; empty fallback = writer). These replace `BOB_WRITER_MODEL`, `BOB_JUDGE_MODEL` and `BOB_PLANNER_MODEL`. `BOB_MODEL_REGISTRY`, `BOB_KMS_KEY_ID` (aws).
- **Cost:** the frontier-only estimate prices the same token counts at the judge model price, for any judge model.
- **Why:** do not lock users into the Anthropic stack. Users pay for Bedrock in their own account (D26), so they must be free to pick the models that they can use, and that they want to pay for.
- **Trade-offs:** some models do not support forced tool use or JSON output; then `prompt` mode + one retry applies, and the verify call checks JSON output per role. Some models have no prompt caching, so the cost goes up; the plan estimate shows it. A weak judge lowers quality; the report shows judge agreement and the UI warns when judge == writer model. Marketplace models can need a subscription; verify shows the exact AccessDenied text. Unknown prices show a `price_unknown` badge; the user can set prices.
- **Priority:** P0 = configurable models on Bedrock (any model family) through Converse + registry + verify per role. P1 = `openai_compatible` with encrypted keys, model picker, per-job model override.
- **Would change if:** Converse does not work for the default Claude models by T+1:00 (for example caching or JSON output fails). Then use the defaults only and keep other models P1.

## D34. Jev through its direct API, not OpenRouter (v4.1 addendum)
- **Decision:** `clients/jev.py` (A2) calls the Jev API directly with a Jev API console key. Config: `JEV_API_KEY`, `JEV_BASE_URL`, `JEV_MODEL`. `OPENROUTER_API_KEY` is not used by Jev. It stays only as an optional key for ScaleDown via OpenRouter (CONTRACTS section 5). The secret `bob/keys` holds `JEV_API_KEY`.
- **Default:** `JEV_BASE_URL` is empty in `config.py` and `.env.example`. A2 confirms the base URL, the path, the auth header and the request shape at the first real call (T+0:20, D32), then sends the value to A1. `JEV_MODEL` keeps `typesafe/jev-1.13-20260917` until A2 confirms the model name form of the direct API.
- **Why:** user decision on 2026-10-30. The team has a Jev console key. One less provider between Bob and Jev.
- **Trade-off:** the base URL and shape are not known before the first call. A wrong guess is not allowed, so the value stays empty until A2 confirms it.
- **Would change if:** the direct Jev API is not available to the team key by T+0:20. Then A2 uses the section 5 fallback chain and reports it.

## Open questions

### Research during the build (D32)
| Item | Owner | When | Default until confirmed |
|---|---|---|---|
| Bob hosting AWS account + region (old Q8) | A5 | T+0:00 | us-east-1 |
| Default Bedrock model IDs / inference profiles (old Q1) | A1 | first Bedrock call (T+0:20) | `global.anthropic.claude-haiku-5-5`, `global.anthropic.claude-sonnet-5-5` |
| Converse API with assumed-role `RefreshableCredentials` | A1 | T+1:00 | boto3 `bedrock-runtime` client rebuilt on refresh |
| Jev request/response shape, model version (old Q2) | A2 | T+0:20 | CONTRACTS section 5 shape, `jev-1.13`, direct Jev API (D34; base URL confirmed at first call) |
| ScaleDown endpoint + Extract schema format (old Q3) | A2 | T+0:20 | `api.scaledown.xyz` |
| Composio toolkits enabled + tool slugs (old Q4) | G2 | T+0:45 | Notion only |
| Prices for Haiku, Sonnet, Jev, ScaleDown (old Q6) | A1 | T+1:30 | config table values |
| CloudFormation quick-create template URL | A5 | P1 | CLI command only |
| Cross-account test account | A5 | T+2:00 | same-account role |
| Marketplace model permissions (`aws-marketplace:*`) | A5 | first non-Anthropic model test | only Anthropic + Nova tested |
| Model registry capabilities (JSON mode, cache, temperature, prices) | A1 | T+1:00 | unknown models: `prompt` JSON mode, no cache, price unknown |

Note: old Q8 said the hosting region must have Haiku 5.5 and Sonnet 5.5. With D26, the Bedrock region is each user's choice, so this rule now applies to the user's Bedrock region, not to Bob's hosting region.

### Still open
5. Demo Notion content: who writes the 5 to 10 internal-style pages, and do they match the product in the Firecrawl docs?

### Still open (not in v4.1)
- One git worktree per agent, and the merge rule.
- Live demo row target.
- An explicit exception to the no-fake-data rule (D23) for the team-written Notion pages.
- Q5 (above).

Answered:
- ~~Q7. Do we need non-English corpora (switch to potion-multilingual-128M)?~~ Default: no.
- ~~Q9. Do we need a login on the public URL?~~ Yes: Cognito user pool + IAM (D27).
- ~~Q10. Custom domain?~~ Default: no. Use the CloudFront domain.
- ~~Demo product: ModelForge or another real product?~~ Firecrawl docs plus Notion pages (D24).
- ~~Is the Photon iMessage prize worth it?~~ Dropped (D24).
- ~~Strict zero-LLM?~~ Reversed (D16). Now Writer, Planner and Judge in controlled roles (D21, D22).
- ~~Writer: Haiku 5.5 via API, or a local model?~~ Haiku 5.5 on Bedrock by default; any model is allowed (D22, D33).
- ~~Architect: Opus 5.5 or Sonnet 5.5?~~ No Architect (D18). Sonnet 5.5 is the default Planner and Judge (D22, D33).

