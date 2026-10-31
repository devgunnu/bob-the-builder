# Bob the Builder: Master Plan (v4, the data factory)

> Build window: **4 hours** (T+0:00 to T+4:00). Two builders, four coding agents each. Result: a fully working product with **real calls only** (no mocks, no fake data).
> Interfaces: `CONTRACTS.md`. Reasoning: `DECISIONS.md` (D18 to D24). Agent prompts: `AGENT_BRIEFS.md`. Ideation record: `research/11-data-factory.md`.
> v4 retires templates, question programs, grammar banks and Architect-written generator code.

## 1. Pitch

**Bob is a synthetic data factory. You give it a goal and your company's material. It maps what the data must cover, generates candidates with a cheap LLM, checks every row with small decision models, and fills the gaps until the map is full. Every row ships with its proof.**

Pitch line: *"The LLM writes, and small decision models check every row. The frontier model only looks at the rows where the checks disagree."*

## 2. The product, from the user's side

| Step | What the user does | What Bob does |
|---|---|---|
| 1. Goal | Types a goal, adds sources (website URL, file uploads, Notion / Confluence / Jira / Google Drive through Composio), sets row count and budget, optionally uploads seed examples | Fetches everything: Firecrawl for URLs, Composio for internal apps, parsers for files |
| 2. Plan | Reviews the coverage map (topics x personas x case types x difficulty). Turns cells on or off, edits personas, clicks **Start** | Reads the material (chunk, filter, Jev triage, topics, ScaleDown Extract evidence), then the Planner proposes the map with notes ("Your seeds cover 4 of 14 topics") and a cost estimate |
| 3. Build | Watches the map fill live; opens any row to see its source spans and checks; opens any rejected row to see why | Writer makes candidates per cell; the cascade verifies each one; only verified rows are kept |
| 4. Fill gaps | Watches round 2 and 3 target thin and hard cells | Gap controller: empty cells, cells with high rejection rates, (stretch) cells where the base model fails |
| 5. Result | Spot-checks a 50-row sample (thumbs up / down), downloads the dataset in a chosen preset and format | Data quality report: coverage, pass rate per check, reject reasons, judge agreement, Jev accuracy from the spot-check, cost vs frontier-only |
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
   Planner (Sonnet 5.5) ► coverage map: topic x persona x case_type x difficulty ► user edits ► Start

 Build loop (rounds 1..3)
   Writer (Haiku 5.5, batched, prompt-cached, ScaleDown Compress on context) ► candidates
   Verify:  Tier 1 code ► Tier 2 Jev + Extract name check ► route by confidence ► Tier 3 Sonnet judge (~5%)
   Gap controller ► next round targets thin / hard cells
   Rejected + kept replies to the same question ► DPO pairs

 Ship
   Report ► presets (OpenAI chat, ShareGPT, Alpaca, ModelForge, DPO, full) ► JSONL / JSON / CSV / Parquet
   + bob_manifest.json + provenance.parquet

 Web ──────────────────────────────────────────────────────────────────────────── Gunbir
   FastAPI routes + SSE  ◄──►  React UI: Setup ► Plan ► Build (live map + feed) ► Row inspector ► Report
```

## 4. Where Jev and the CDMs work

| Stage | Jev | ScaleDown CDMs |
|---|---|---|
| Read | Triage each chunk (4 questions per call) | **Extract** builds the evidence index with verbatim spans; **Summarize** writes topic briefs |
| Generate | | **Compress** shrinks context; briefs replace full pages in Writer prompts |
| Verify | One call per candidate, 5 questions (3 shared + 2 per case type, CONTRACTS §4); calibrated probability routes the row | **Extract** pulls every feature / setting / URL from the reply; code checks each against the evidence index (invented-feature detector) |
| "Not in docs" rows | Confirms the top-5 retrieved chunks do not answer the question | |
| Gap fill | Labels kept rows with their real topic, so coverage is measured, not assumed | |
| Report | Spot-check measures Jev's real accuracy on this job | Spans power the row inspector |

Real fallbacks (no stubs): Jev -> ScaleDown Classify -> Haiku JSON. Extract -> Haiku extraction with the same verbatim-span check. The UI shows a badge when a fallback is in use.

## 5. Team and agents

### Aaditya: AI and backend logic (agents A1 to A4)

| Agent | Scope | Owns |
|---|---|---|
| **A1 Core** | Shared models, config, store, events + SSE log, cost ledger, disk cache of real responses, Bedrock client, orchestrator state machine and build loop | `core/*`, `config.py`, `llm/bedrock.py`, `orchestrator.py`, `pyproject.toml` |
| **A2 Read** | Jev client + fallback chain, ScaleDown client, chunking, filters, embeddings, dedup, triage, topics, evidence index, retriever | `clients/*`, `pipeline/chunk.py filters.py embed.py triage.py topics.py evidence.py` |
| **A3 Plan + Write** | Planner (coverage map), target allocation, Writer prompts and generation for all 4 case types, gap controller | `pipeline/planner.py generate.py gaps.py`, `pipeline/prompts/planner.md writer*.md` |
| **A4 Verify + Ship** | 3-tier cascade, judge prompt, DPO pairs, report, presets, formats, manifest; stretch: base-model probing | `pipeline/verify.py report.py probe.py`, `pipeline/prompts/judge.md`, `export/*` |

### Gunbir: frontend and integrations (agents G1 to G4)

| Agent | Scope | Owns |
|---|---|---|
| **G1 API + Files** | FastAPI app, all routes in CONTRACTS §6, SSE endpoint, uploads, file parsers, `fetch_documents()` dispatch, `/health` with real key checks | `api/*`, `connectors/__init__.py upload.py parsers.py` |
| **G2 Connectors** | Firecrawl (crawl with live progress), Composio (OAuth connect, browse, fetch for Notion, Confluence, Jira, Google Drive), re-sync diff, demo corpus cache | `connectors/firecrawl.py composio.py sync.py`, `demo/*` |
| **G3 UI: Setup + Plan** | Vite + React + TS shell, API client, `types.ts`, Setup screen (goal, sources, connectors, uploads, budget), Plan screen (editable coverage map, estimate, Start) | `frontend/src/api/*`, `frontend/src/screens/Setup*`, `Plan*`, app shell |
| **G4 UI: Build + Results** | Live Build screen (map heatgrid, counters, cost meter, row feed, reject reasons), Row inspector (messages, checks, highlighted source spans), Report screen (charts, spot-check panel, export and downloads) | `frontend/src/screens/Build*`, `Row*`, `Report*`, `frontend/src/components/viz/*` |

Gunbir's agents call the backend only through `Orchestrator` and `fetch_documents()`. Aaditya's agents never touch `api/`, `connectors/` or `frontend/`.

## 6. Timeline (4 hours)

### Before T+0:00 (both builders, 15 minutes, not part of the 4 hours)
- [ ] Bedrock: AWS credentials work; one real call each to the Haiku 5.5 and Sonnet 5.5 model IDs (or inference profiles) in your region.
- [ ] OpenRouter key: one real Jev Decisions call (`/api/alpha/decisions`).
- [ ] ScaleDown key: one real Extract, Summarize, Classify and Compress call.
- [ ] Firecrawl key: one real scrape of the demo docs.
- [ ] Composio key: auth config for Notion (and Jira or Confluence if available); connect one real account.
- [ ] Demo Notion workspace: 5 to 10 real internal-style pages (support FAQ, escalation policy, known issues) for the demo product.
- [ ] Repo: `backend/` and `frontend/` folders, branches `aaditya/*` and `gunbir/*`, `.env` shared out of band (never committed).

### T+0:00 to T+0:20: Lock
| Agent | Task |
|---|---|
| A1 | `core/models.py` exactly as CONTRACTS §2, `config.py`, `pyproject.toml`, empty `orchestrator.py` with the §7 signatures. Commit by T+0:15. |
| A2 | Jev and ScaleDown clients with real calls; confirm the request and response shapes; write them into CONTRACTS §5 if they differ |
| A3 | Bedrock call through `llm/bedrock.py` draft (with A1); first Writer prompt tested on the first real smoke page (G2 commits it by T+0:10) |
| A4 | `prompts/judge.md`; export preset functions (pure code, no external calls) |
| G1 | FastAPI skeleton, `/health` with real key checks, CORS, run script; then `POST /uploads`, `POST /jobs` and the MD parser by T+0:45 (needed for the thin path) |
| G2 | First real Firecrawl page -> `demo/smoke/` by T+0:10, then 3 to 5 pages total -> `demo/smoke/*.md`; 10 real seed questions -> `demo/smoke/seeds.jsonl` |
| G3 | Vite + React + TS scaffold, router, layout, `types.ts` from CONTRACTS §2 |
| G4 | Design the Build screen layout and the heatgrid component against `types.ts` shapes |

### T+0:20 to T+1:30: Build the core
| Agent | Deliverable by T+1:30 |
|---|---|
| A1 | **Thin real path by T+0:50** (CONTRACTS §12). Then: store with disk persistence, event bus + replay, ledger with frontier-only estimate, full build loop with rounds and budget guard |
| A2 | chunk, filter, embed, dedup, triage, topics with briefs, EvidenceIndex + Retriever; all tested on `demo/smoke/` with real calls |
| A3 | Planner returns a valid `Plan` for the smoke corpus; Writer works for all 4 case types; batched (5 per call), prompt caching on |
| A4 | Tier 1 + tier 2 + routing + tier 3 judge working on real candidates; JSONL + Parquet export for `openai-chat` |
| G1 | All routes in CONTRACTS §6 wired to the Orchestrator; SSE with `Last-Event-ID` replay; uploads + parsers for PDF, DOCX, MD, HTML, TXT, CSV |
| G2 | Firecrawl connector with page progress; Composio connect + browse + fetch for Notion; full demo crawl cached to `demo/corpus/` |
| G3 | Setup screen (goal, URL, uploads, connector buttons with real OAuth popup, row count, budget, seeds); Plan screen (map editor, notes, estimate, Start) |
| G4 | Build screen on live SSE: heatgrid, counters, cost meter, row feed with reject reasons |

### T+1:30: Checkpoint 1 (merge to `main`, 10 minutes)
**Pass:** In the browser, a user enters a goal + the smoke URL, sees a real plan, clicks Start, watches real rows stream in with real verdicts, and downloads a real JSONL file. No hard-coded data anywhere.
If it fails: all 8 agents fix the break first; nothing new starts.

### T+1:40 to T+2:50: Complete the product
| Agent | Deliverable by T+2:50 |
|---|---|
| A1 | Gap rounds wired end to end; cancel; resync orchestration (P1); concurrency tuned so 500 rows finish in under 10 minutes |
| A2 | Real fallback chains tested (force a Jev failure, see ScaleDown Classify take over); triage and evidence quality pass on the full demo corpus |
| A3 | Gap controller (deficit + rejection-rate boost); persona and difficulty diversity checked by reading 50 real rows; prompt fixes |
| A4 | DPO pairs, full report, all presets and formats, manifest + provenance.parquet, stratified train/eval split |
| G1 | Error handling: provider errors shown in the UI; `/sources/preview`; job list |
| G2 | Composio Jira and Confluence (or Google Drive) fetch; `sync.py` diff for re-sync |
| G3 | Job list / history page; Setup preview of fetched documents; polish |
| G4 | Row inspector with source span highlights and check list; Report screen with spot-check panel and downloads |

### T+2:50: Checkpoint 2 (merge, 10 minutes)
**Pass:** All P0 items (section 8) work end to end on the real demo corpus (Firecrawl site + Notion through Composio): 500+ kept rows, one gap round, report complete, `openai-chat` and `full` downloads open. P1 items finish in T+3:00 to T+3:30.

### T+3:00 to T+3:30: Hardening and P1 / stretch
- Everyone: fix bugs found at checkpoint 2.
- If green: re-sync (P1), base-model probing (stretch, A4), UI polish (G3, G4).

### T+3:30: Feature freeze
### T+3:30 to T+4:00: Ship
- Full real run of the demo on a fresh job; keep it as the backup job (and screen-record it).
- README with setup and run steps; rehearse the demo 2 times.

## 7. Definition of done at T+3:30 (P0 + P1, all real)
1. A new user can create a job from a public URL, an uploaded file, and a Notion page in one job.
2. The plan screen shows a real coverage map from the Planner, and edits change the build.
3. The build runs real Writer, Jev, ScaleDown and judge calls; rows stream live; rejected rows show their reason.
4. At least one gap round runs and targets the thin cells.
5. Every kept row opens to its source spans and its passed checks.
6. The report shows coverage, pass rates, reject reasons, judge agreement, cost and frontier-only estimate, and the spot-check updates it.
7. Exports: `openai-chat`, `sharegpt`, `modelforge-chat`, `dpo`, `full` in JSONL and Parquet, plus manifest and provenance.
8. A real provider failure shows an error or a fallback badge in the UI, and the job does not hang.

## 8. Priorities and cut lines
| Priority | Items |
|---|---|
| **P0** (must work at checkpoint 2) | URL + upload + Notion sources; read pipeline; plan + edit; build with 3-tier verification; at least one gap round; live UI; row inspector; report; JSONL + Parquet in `openai-chat` and `full` |
| **P1** | Gap round 3; DPO pairs; job list page; Jira + Confluence / Drive; other presets and formats; re-sync; spot-check |
| **Stretch** | Base-model probing; multi-turn rows |

Cut order if late: stretch -> re-sync -> extra Composio toolkits -> extra presets -> DPO. Never cut verification or the row inspector; they are the product.

## 9. Demo (3 minutes)
**Corpus:** a sponsor's public docs (default: Firecrawl's docs) via Firecrawl, plus 5 to 10 internal-style Notion pages (support FAQ, escalation policy, known issues) via Composio.
**Goal:** "First-reply support assistant for Firecrawl. Use only our docs. If the docs do not cover it, say so and hand off to a human."

1. **0:00 Hook.** "Every synthetic data tool asks an LLM to write data and hopes it is right. Bob checks every row."
2. **0:15 Sources.** Paste the docs URL; click Notion, pick the internal pages. Firecrawl pages and Notion pages count up.
3. **0:40 Plan.** The coverage map appears: 12 topics x 4 personas x 4 case types x 3 difficulty levels. Read one note aloud ("No seed examples cover rate limits"). Turn off one topic. Start.
4. **1:00 Build.** The map fills. Counters: generated, kept, rejected, judged. Click a rejected row: "Mentions 'webhook retries config', which is not in the docs." Click a kept "not in docs" row: Jev confirmed none of the top-5 passages answer it.
5. **1:50 Gap round.** "Round 2: 9 thin cells, 3 hard cells." The empty cells fill.
6. **2:20 Report.** Coverage 100%, pass rates per check, 5% sent to the judge, judge agreement, cost vs frontier-only (real numbers from the ledger; expect about $2 vs about $20).
7. **2:40 Ship.** Download OpenAI-chat JSONL and the DPO file. "Every row has a provenance record."
8. **2:55 Close.** "Your docs and internal wiki in, verified training data out."

Keep the backup job from T+3:30 open in a second tab.

## 10. Cost model (estimate, about 1,000 kept rows; check prices before T+0:00)
| Part | Calls | Estimate |
|---|---|---|
| Firecrawl crawl (25 pages) | 25 | credits |
| Jev triage + ScaleDown Extract + Summarize | about 500 | about $0.05 |
| Planner (Sonnet 5.5) | 2 to 3 | about $0.10 |
| Writer (Haiku 5.5, about 1,700 candidates, 5 per call, cached prompts) | about 340 | about $0.40 |
| Jev + Extract verification of 1,700 candidates | about 3,400 | about $0.15 |
| Judge (Sonnet 5.5, about 5% routed + 2% audit) | about 120 | about $1.00 |
| **Total** | | **about $1.70** |
| Frontier-only (Sonnet writes and judges every candidate) | | about $20 |

## 11. Risks
| Risk | Mitigation |
|---|---|
| A key or endpoint fails at T+0:00 | Pre-start checklist; real fallback chains; `/health` shows each provider's state |
| Jev request shape differs from research | A2 confirms it in the first 20 minutes and updates CONTRACTS §5 |
| Bedrock model ID or region not enabled | Check before T+0:00; use the cross-region inference profile |
| Bedrock throttling | Semaphores, backoff, batching 5 candidates per call, prompt caching |
| Rows look alike | Persona and difficulty axes; batched generation asks for 5 different rows; dedup; A3 reads 50 real rows at T+2:00 |
| Composio OAuth friction in the demo | Connect the demo account before the demo; keep the connected account id in `.env` |
| Firecrawl slow | Crawl cap 25; the demo corpus crawl is cached by T+1:30 (real data, cached) |
| Integration breaks at checkpoints | Contracts locked at T+0:20; one owner per file; thin real path by T+0:50 |
| Scope | Cut lines in section 8; freeze at T+3:30 |
