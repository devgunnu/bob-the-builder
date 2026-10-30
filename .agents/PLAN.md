# Bob the Builder: Master Plan

> Night Hack @ Founders, Inc., 2026-10-30. Build 5:00 to 10:00pm, live demo, no slides.
> Compiled from four research agents (see `research/`). This is the single source of truth for the build; `CONTRACTS.md` holds the interfaces, `DECISIONS.md` holds the reasoning.

## 1. One-line pitch
**Bob turns any corpus into a premium, fully formatted fine-tuning dataset for cents: System 1 models decide what matters, a tiny model writes, System 1 verifies, and every row ships with provenance and a calibrated faithfulness score.**

Demo headline: *"2,500 training rows from a 1M-token corpus for about 40 cents (about 13 cents on our own GPU). The same job with Opus 5.5 costs about $35."*

## 2. What changed from the original hypothesis

| Original | Verdict | Why (details in research/02) |
|---|---|---|
| Jev classifies chunks as useful or not | **Keep, and expand** | Jev (TypeSafe's System 1 decision model) is built for exactly this. $0.042 per M input tokens, output free, about 200 to 300 ms. One call answers 5 or 6 questions at once. |
| CDMs generate the dataset | **Reword** | Constrained Decision Models (Jev, Cloudflare Clef, etc.) only return probabilities over options you define. They cannot write text. They *can* select sentences, route templates, verify answers, and judge preference pairs, which is where most of the quality comes from. |
| (new) Something has to write | **Add a tiny writer** | Templates ($0), a local model on our GPU box ($0 marginal), or Claude Haiku 5.5 ($0.10 / $0.50 per M). The writer only writes short instructions in the default mode (Humpback), keeping output tokens minimal. |

The idea is still "no heavy LLMs". It is now defensible: heavy models never touch the data, and the light models only do the jobs they are good at.

## 3. Architecture

```
          INPUT                                   COST
  files (pdf/docx/md/txt/csv/json) | URL (Firecrawl)
                 │
  1. INGEST + CHUNK   heading-aware, 300-500 tok; CSV -> row groups     $0
                 │
  2. CHEAP FILTERS    Gopher/C4/FineWeb heuristics (relaxed for PDFs)   $0   drops ~30-60%
                 │    MinHash dedup (datasketch)                        $0
  3. EMBED            potion-base-8M (CPU) or bge on GPU box            $0
                 │    semantic dedup (cos > 0.95 within cluster)        $0   drops ~10-30%
  4. JEV DECIDE       one call per chunk, 6 questions:                  ~$0.06 / 1M-tok corpus
                 │      useful (Noul), density (Score), task type (Choice),
                 │      boilerplate (Noul), PII (Noul), injection (Noul)
  5. SELECT           signal = f(jev, density, heuristics);
                 │    k-means (k≈√N), per-cluster quota under user BUDGET  $0
  6. WRITE (router)   T0 extractive/template: Jev Choice picks sentence/template   $0
                 │    T1 Humpback (default): chunk = answer, writer makes instruction
                 │    T2 grounded QA / assistant rewrite for top ~20%
                 │    DPO: rejected = free perturbation or no-context answer
                 │    writer backends: local vLLM | Haiku 5.5 | Mercury (optional)
  7. VERIFY           Jev Noul: supported? answerable alone?            ~$0.07
                 │    cosine groundedness, regex quality, output dedup, PII scrub
                 │    -> every row gets faithfulness_p; drop below threshold
  8. CERTIFY          sampled judge (5-10%) -> pass rate ± Wilson 95% CI
                 │
  9. EXPORT           canonical rows -> preset (field mapping) -> format writer
                      JSONL, JSON, CSV, Parquet, Avro, Arrow, Postgres JSONB (.sql)
                      + bob_manifest.json (+ optional ModelForge validate)
```

### Why each stage earns its place
- Stages 2 and 3 are free and remove most of the junk, so paid calls only see good chunks.
- Stage 4 is where Jev shines: calibrated, cheap, structured. Six questions in one call cost about the same as one.
- Stage 6 Humpback keeps the writer's output to about 60 tokens per example (output tokens are about 95% of LLM cost).
- Stage 7 turns "cheap" into "trustworthy". It also catches writer hallucinations, which is why a small or diffusion model is safe to use.

## 4. Cost model (1M-token corpus to 2,000 SFT + 500 DPO rows)

| Step | Bob (Haiku 5.5 writer) | Bob (GPU box writer) | Naive (Opus 5.5) |
|---|---|---|---|
| Classify (Jev, about 2,500 chunks x 600 tok) | $0.06 | $0.06 | (n/a, LLM reads everything) |
| Write 2,000 SFT (Humpback) | $0.18 | $0 | $16.80 |
| Write 500 DPO rejected | $0.07 | $0 | $4.20 |
| Verify (Jev, 2,500 rows x about 860 tok) | $0.09 | $0.09 | $14 (Opus judge) |
| **Total** | **≈ $0.40** | **≈ $0.15** | **≈ $35** |

Prices: Jev $0.042 / M input; Haiku 5.5 $0.10 / $0.50 per M (batch halves it); Opus 5.5 $4 / $20. Show the Batch toggle as "production mode".

Verify all prices in the first 30 minutes (research agents could not reach some vendor pages).

## 5. Formats and presets

Every exporter is a projection of one canonical row (see `CONTRACTS.md`).

| Format | Library | Notes |
|---|---|---|
| JSONL | `orjson` | Default. ModelForge-native. |
| JSON | `orjson` | Plain top-level array (never a wrapped object; ModelForge's regex may pick the wrong key). |
| CSV | `csv` | `QUOTE_ALL`, `utf-8-sig`; nested messages as a JSON string column plus flat prompt/response. Warn: ModelForge cannot use nested CSV. |
| Parquet | `pyarrow` | Explicit schema always; `zstd`. ModelForge's preferred type. |
| Arrow | `pyarrow` | Cheap add; ModelForge reads `.arrow`. |
| Avro | `fastavro` | Explicit schema, nullable unions, `deflate`, `validate_many`. |
| JSONB | `.sql` script | JSONB is a Postgres column type, not a file. Ship `CREATE TABLE ... data jsonb` + inserts with a random dollar-quote tag + optional GIN index; optional direct push via `psycopg` 3. UI label: "Postgres JSONB (.sql)". |
| HF Hub | `datasets` | Optional push with dataset card. |

Presets (field mappings):
- **ModelForge SFT**: `{prompt, completion}` strings (safest; works for text_generation, instruction_following, summarization).
- **ModelForge SFT chat**: `{messages}`.
- **ModelForge DPO**: `{prompt, chosen, rejected}`.
- **ModelForge QA fallback**: context + question in `prompt`, answer in `completion` (ModelForge's extractive_qa cannot train).
- OpenAI chat SFT, OpenAI DPO, Alpaca, ShareGPT, TRL prompt/completion, TRL DPO.
- **Custom**: user supplies a field mapping (JSON) in UI/CLI.

ModelForge rules Bob must follow (from research/01): canonical column names only (aliases are never applied), identical keys and types in every row, no extra columns, one file per folder (directories merge, and Parquet hides JSONL), and token-length stats with a max-length cap (512 truncation under 12 GB VRAM).

## 6. Standalone by design
- Bob is its own Python package (`bob`), Python 3.12+. **It never imports ModelForge.**
- ModelForge integration = write the file + `bob_manifest.json` (maps to ModelForge's `DatasetValidationRequest` / `TrainingRunRequest`), plus an optional `--validate-with-modelforge URL TOKEN` that calls `POST /api/datasets/validate`.
- Without ModelForge, the same output works with OpenAI fine-tuning, TRL, Unsloth, Axolotl, LlamaFactory, or HF Hub via presets.

## 7. Stack and repo layout

- Backend: **FastAPI** + asyncio pipeline (Python-native format libs; matches ModelForge's stack).
- Realtime + files: **Convex** (`jobs`, `samples` tables; exports in Convex storage for public links). Optional: fall back to server-sent events if Convex setup stalls.
- Frontend: **Vite + React + Tailwind** (+ Convex `useQuery`). Bolt may scaffold it.
- iMessage: **Photon Spectrum** Bun sidecar (TypeScript only) calling FastAPI.
- GPU box: **vLLM** serving a small instruct model (e.g. Qwen3-8B class) with an OpenAI-compatible endpoint; also GPU embeddings if wanted.

```
bob-the-builder/
  .agents/                 plan, contracts, decisions, research (this folder)
  bob/                     python package
    cli.py                 `bob build <path|url> --preset --format --budget --writer`
    api.py                 FastAPI: POST /jobs, GET /jobs/{id}, GET /presets
    pipeline/
      ingest.py chunk.py filters.py embed.py dedup.py
      jev.py               decision client (raw HTTP), classify + verify + judge
      select.py            scoring, clustering, budget quotas
      write.py             router + writer backends (vllm, anthropic, templates)
      verify.py certify.py
      cost.py              token + $ ledger, baseline comparison
    export/
      presets.py formats.py jsonb_sql.py manifest.py modelforge.py
    models.py              Chunk, Example, Job (pydantic)
  web/                     Vite React app
  convex/                  schema.ts, jobs.ts, samples.ts, files.ts
  imessage/                spectrum-ts sidecar
  demo/                    cached corpus + cached Jev/writer responses + golden run
  tests/                   round-trip test for every format + ModelForge schema check
  .env.example
```

## 8. Build plan (5:00 to 10:00pm)

Roles for 4 (merge A+B and C+D for 2; for 3, D absorbs Photon only if time allows):
- **A: Selection** (ingest, chunk, filters, embed, dedup, Jev classify, select)
- **B: Writing + trust** (writer router, Humpback, DPO, Jev verify, certify, cost ledger, vLLM on GPU box)
- **C: Output** (canonical schema, presets, all format writers, manifest, ModelForge validate, CLI, tests)
- **D: Experience** (web UI, Convex, Photon iMessage, demo + backup video)

| Time | A | B | C | D |
|---|---|---|---|---|
| **5:00-5:20** | All: lock `CONTRACTS.md`, repo skeleton, `.env`, one working Jev call + one writer call | | | |
| 5:20-6:20 | ingest (files + Firecrawl), chunk, heuristics, MinHash | vLLM up on GPU box; writer interface; Humpback prompt; templates tier | canonical model; JSONL/JSON/CSV/Parquet/Arrow; ModelForge + OpenAI + Alpaca + ShareGPT presets | Convex schema + mutations; UI skeleton (upload, options) |
| 6:20-7:20 | embeddings, semantic dedup, Jev 6-question classify (async, cached to disk), select + budget | DPO (perturbation + no-context), Jev verify, cosine groundedness, cost ledger | Avro, JSONB .sql, manifest, `bob build` CLI, round-trip tests | live job view (stages, progress, cost ticker, sample feed); Photon echo bot on a real phone |
| 7:20-8:00 | **Integrate end to end** (A + B + C), D wires UI to `POST /jobs` | | | |
| **8:00 CUT LINE 1 (MVP)** | Upload or URL -> Jev-selected chunks -> Humpback SFT -> verified rows -> JSONL + Parquet + CSV downloads in the UI with live progress and cost. **If behind: drop Avro/JSONB/HF/DPO/Photon.** | | | |
| 8:00-9:00 | "why dropped" reasons; signal map data (UMAP coords) | certificate (sampled judge + Wilson CI); Opus baseline comparison | ModelForge validate call; zip bundle; HF push (optional) | cost meter vs Opus, signal map, certificate card; iMessage reply with link + attachment; **record backup video** |
| **9:00 CUT LINE 2 (freeze)** | Bug fixes only | | | |
| 9:00-9:30 | Stretch: hand Parquet to ModelForge live and start a run | | | |
| 9:30-9:50 | Rehearse demo 3x with a timer; warm caches; reset DB | | | |
| 9:50-10:00 | README with architecture diagram + sponsor list; commit + push | | | |

## 9. Demo script (2 minutes, live)
1. **0:00 Hook.** "Good fine-tuning data costs dollars per example. Bob makes it for fractions of a cent."
2. **0:15 Text it.** A judge texts Bob a docs URL plus "qa 200". Bob replies instantly: "On it."
3. **0:30 Watch it think.** Web UI shows the same job live: 15 pages, 240 chunks, heuristics drop nav and boilerplate, Jev keeps 70 high-signal chunks (show its probabilities and a rejected chunk with its reason).
4. **0:55 Watch it write and check itself.** Rows stream in with faithfulness scores; one gets rejected as unsupported. Cost meter: "$0.03 so far. Opus 5.5: $2.80. 93x cheaper."
5. **1:20 Ship it.** One click: Parquet, ModelForge JSONL, Avro, Postgres JSONB `.sql` loaded into Postgres in one line. Certificate: "94% ± 4% grounded".
6. **1:40 Close the loop.** Phone buzzes: "200 examples, $0.04, download link + file attached." Optional: start a ModelForge run on it.
7. **1:55 Close.** "Any corpus to training data, in a minute, for pennies."

Keep a pre-run job in a second tab and the backup video ready.

## 10. Pre-event checklist (before 5pm, no product code)
- [ ] Jev access: OpenRouter key and a working `POST /api/alpha/decisions` call (fallback: Vercel AI Gateway, DigitalOcean, Cloudflare Clef-flash on Workers AI).
- [ ] Anthropic key (each builder gets $50; pool them). Confirm Haiku 5.5 model ID and price.
- [ ] GPU box: vLLM installed, writer model weights downloaded, OpenAI-compatible endpoint reachable from laptops.
- [ ] Photon: account at app.photon.codes, managed iMessage line provisioned, `PROJECT_ID` / `PROJECT_SECRET`.
- [ ] Firecrawl key; Convex project (`npx convex dev` once).
- [ ] `pip install` pyarrow fastavro orjson datasketch model2vec scikit-learn pymupdf python-docx trafilatura psycopg[binary] fastapi uvicorn httpx anthropic firecrawl convex; download potion-base-8M.
- [ ] Choose and pre-crawl the demo corpus; save to `demo/`.
- [ ] Confirm Photon's "double prize with SDK" offer applies tonight.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Jev access or request format | Get a working call first. Raw HTTP, no `temperature`/`max_tokens`. Fallbacks: Clef-flash (same API shape), then embedding + LogReg head trained on cached Jev labels ("distilled System 1"). |
| Jev confidently wrong (11.5% wrong at ≥ 90%) | Thresholds set on about 100 hand labels; descriptive option names (`useful_self_contained_fact`, never `0/1`); 50-chunk name-swap robustness check. |
| Prompt injection in uploaded docs | Strip instruction-like text; dedicated injection Noul; never let chunk text become a system prompt. |
| Writer hallucination (esp. small or diffusion) | Jev verify + cosine groundedness on every row; Humpback mode keeps answers verbatim from source. |
| Humpback answers read like documents | Assistant-rewrite tier for top 20%; record style in metadata. |
| Wifi / API rate limits | Cache every Jev and writer response to disk; replay mode; semaphores (6 to 8) with backoff; phone hotspot; backup video. |
| vLLM setup eats time | B gives it 30 minutes max, then falls back to Haiku 5.5. |
| Photon early preview | Pin version; test on a real phone by 7:20; fall back to Spectrum terminal provider. |
| Convex limits (1 MB docs) | Files in storage, only last 50 samples in DB. SSE fallback. |
| Schema surprises | Explicit schemas + round-trip read test per format + ModelForge column check. |
| Scope creep | Hard freeze at 9:00. DPO, Avro, JSONB, HF, Photon are all toggles that can be dropped. |

## 12. Prize targets
1. **Anthropic top 3** ($10k credits): overall demo quality; Claude Haiku 5.5 as writer + judge.
2. **Photon Best iMessage Agent** ($1k, possibly doubled): "text a URL, get a dataset".
3. Name Firecrawl and Convex in the demo for partner goodwill.
