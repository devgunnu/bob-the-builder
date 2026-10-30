# Bob the Builder: Master Plan (v2.1, strictly zero-LLM)

> Night Hack @ Founders, Inc., 2026-10-30. Build 5:00 to 10:00pm, live demo, no slides.
> v2 replaces v1 after the founder's challenge: Bob now **generates** new data with no LLM. See `research/05` for the evidence.
> `CONTRACTS.md` holds the interfaces; `DECISIONS.md` holds the reasoning.

## 1. One-line pitch
**Bob compiles your documents into a fact graph and programs brand-new training data from it, with zero LLM tokens. Small constrained models read and phrase; code computes the answers, so every row is correct by construction and traceable to its source.**

Demo headline: *"5,000 new training rows, multi-hop questions, computed answers, reasoning traces and hard negatives, for about 40 cents (free on ScaleDown's starter tokens). The same job with Opus 5.5: about $70. LLM tokens used: 0."*

## 2. How we got here

| Idea | v1 | v2 |
|---|---|---|
| Jev classifies chunks | Keep | **Keep**, plus ranking, verification and phrase decoding |
| CDMs generate | Reworded (wrong term researched) | **Keep as intended.** CDM = ScaleDown **Constrained Decoding Models**: Extract builds the fact graph, Summarize writes constrained prose |
| LLM writer | Core | **Removed.** Strictly zero-LLM (team decision). LLMs appear only as the *estimated* cost baseline; none is ever called |

## 3. Architecture

```
  files | URL (Firecrawl)
     │
  1 INGEST + CHUNK        heading-aware, 300-500 tok, CSV/tables -> rows         $0
  2 FREE FILTERS          heuristics + MinHash + embeddings + semantic dedup   $0
  3 TRIAGE   (Jev)        useful / density / content type / boilerplate / PII / injection
  4 EXTRACT  (ScaleDown)  typed facts with confidence + verbatim source spans
  5 FACT GRAPH            entity resolution, unit normalization, cross-chunk merge,
                          fact confidence = extract conf x span check x corroboration
  6 COMPOSE  (code)       question programs over the graph; answers COMPUTED
  7 REALIZE  (code + CDM) grammar bank -> many surface forms; Summarize for long answers
  8 RANK     (Jev)        Choice: most natural candidate; Noul: fluent? answerable alone?
  9 VERIFY                span check, Jev "supported?", dedup, decontam, PII
 10 CERTIFY               re-verify 5% sample (spans, recompute, Jev) + human spot-checks -> pass rate ± CI
 11 EXPORT                canonical rows -> presets -> JSONL/JSON/CSV/Parquet/Arrow/Avro/JSONB(.sql)
                          + bob_manifest.json (+ optional ModelForge validate)

  ZERO-LLM RULE: only Jev, ScaleDown CDMs and static embeddings may be called.
  One allowlisted call_model() gateway; the "LLM tokens: 0" meter reads its ledger.
```

### Question programs (stage 6)
Each program takes graph nodes and returns `(question_slots, answer, reasoning_path, provenance)`.

| Program | Example | Answer |
|---|---|---|
| lookup | What is the default timeout of the ingest service? | copied value |
| inverse | Which service listens on port 8080? | graph query |
| multi-hop | What is the timeout of the service that the API gateway depends on? | 2-hop join |
| compare | Which is faster to restore, plan A or plan B, and by how much? | computed difference |
| convert | How many minutes is the 5,400 s retention window? | computed |
| aggregate | How many endpoints require admin scope? List them. | count + list |
| superlative | Which region has the highest storage cost? | argmax |
| procedure | How do I rotate an API key? / What comes after step 3? | ordered steps |
| definition | What is a tenant? | definition span |
| causal / conditional | What happens if the quota is exceeded? | effect span |
| true/false + fix | True or false: X defaults to 10. | false, it's 30 (source) |
| multi-turn | 3 to 5 turn walk across a graph neighbourhood | chat rows |
| CoT | any multi-hop/compute program | step-by-step trace from the path |
| explain-topic | Explain how billing works. | Summarize over the cluster's chunks |
| summarization | Summarize this section in 2 sentences. | Summarize |

DPO for free: rejected = the same program run on a perturbed fact (sibling value, wrong hop, off-by-one step), with a `rejection_strategy` label.

### Why this impresses
- New data: multi-hop and computed questions exist nowhere in the source.
- Correct by construction: answers come from code and verbatim spans, not sampling.
- Reasoning traces and verifiable answers (usable for RLVR later) with no LLM.
- Full provenance per row: every fact links to the character span it came from.

## 4. Cost model (1M-token corpus, about 5,000 rows)

| Step | Cost |
|---|---|
| Jev triage | about $0.04 |
| ScaleDown Extract | about $0.03 |
| ScaleDown Summarize (cluster explanations) | about $0.04 |
| Jev ranking + verification | about $0.32 |
| **Total** | **about $0.43** (about $0 under ScaleDown's 50M free tokens) |
| LLM tokens | **0** |
| Opus 5.5 generate + judge baseline | about $70 |

Prices: Jev $0.042/M input; ScaleDown $0.04/M input, output free. Verify at 5:00pm.

## 5. Formats and presets
Unchanged from v1 (see `CONTRACTS.md` §5): JSONL, JSON (plain array), CSV, Parquet, Arrow, Avro, Postgres JSONB `.sql`, optional HF Hub. Presets: ModelForge SFT / chat / DPO / QA fallback, OpenAI chat / DPO, Alpaca, ShareGPT, TRL, custom mapping, full (with provenance).

New: **ModelForge CoT preset** puts the reasoning trace + answer in `completion`. **RLVR preset** `{prompt, answer, verifier}` for trainers with verifiable rewards (not ModelForge yet).

ModelForge rules still apply: canonical columns only, identical row types, one file per folder, token-length stats + cap.

## 6. Standalone by design
Python package `bob` (3.12+), never imports ModelForge; integrates through files + `bob_manifest.json` + optional `POST /api/datasets/validate`.

## 7. Stack and layout
FastAPI + asyncio pipeline, Convex for live progress and file links, Vite + React UI, Photon Spectrum sidecar for iMessage. GPU box: embeddings, and fine-tuning the demo model with ModelForge.

```
bob/
  cli.py api.py models.py
  pipeline/ ingest.py chunk.py filters.py embed.py dedup.py
            jev.py scaledown.py          # raw HTTP clients, disk cache, replay
            graph.py                     # facts, entity resolution, units, confidence
            programs/                    # one module per program family
            realize/ grammar/*.yaml realizer.py inflect.py
            rank.py verify.py certify.py cost.py models_allowlist.py
  export/ presets.py formats.py jsonb_sql.py manifest.py modelforge.py
web/  convex/  imessage/  demo/  tests/
```

## 8. Build plan (5:00 to 10:00pm)

Roles (2 people: A+B and C+D):
- **A: Read** (ingest, filters, Jev triage, ScaleDown Extract, fact graph)
- **B: Compose** (question programs, DPO perturbation, CoT traces)
- **C: Speak + ship** (grammar bank, realizer, Jev ranking, Summarize tasks, exporters, presets)
- **D: Show** (UI, Convex, Photon, demo)

| Time | A | B | C | D |
|---|---|---|---|---|
| 5:00-5:20 | All: lock `CONTRACTS.md` (Fact + Program shapes), keys, one working Jev call + one ScaleDown Extract call | | | |
| 5:20-6:20 | ingest, chunk, heuristics, dedup, Jev triage | programs on a **hand-written fixture graph**: lookup, inverse, definition, procedure, compare | grammar bank v1 (5+ phrasings per program), realizer, JSONL/Parquet/CSV + ModelForge presets | Convex + UI skeleton; Photon echo bot |
| 6:20-7:20 | Extract schema, fact graph, entity resolution, span check | multi-hop, aggregate, convert, true/false, CoT, DPO perturbation | Jev ranking, Summarize explain-topic, Avro/JSONB/Arrow, manifest | live job view: stage stepper, graph stats, sample feed, cost meter |
| 7:20-8:00 | **Integrate on real graph** | | | |
| **8:00 CUT LINE 1** | Docs -> fact graph -> 5+ program types -> ranked rows -> JSONL + Parquet in the UI with provenance and cost. Drop Avro/JSONB/multi-turn/Photon if behind. | | | |
| 8:00-9:00 | corroboration scores, "why dropped" | multi-turn walks, program coverage sampler | grammar bank v2 (20+ per program), certificate | **fact graph visual** (click a row, see its path light up), Opus cost comparison, iMessage reply; backup video |
| **9:00 FREEZE** | Bug fixes only | | | |
| 8:00-9:00 (B, in parallel) | | Kick off the **ModelForge fine-tune** on the GPU box with the first full dataset; build the 5-question base-vs-tuned eval | | |
| 9:00-9:30 | Stretch: Jev phrase-decoding paraphraser; record base-vs-tuned clip for the backup video | | | |
| 9:30-10:00 | Rehearse 3x, warm caches, README, push | | | |

Grammar bank tip: writing phrasings is the most parallel, lowest-risk work. Anyone who is blocked writes grammar.

## 9. Demo: a real product, end to end (2 minutes)

**Corpus:** a real product's docs. Default proposal: **ModelForge itself** (its DEVELOPER_GUIDE, web Docs screen, code docstrings, CLI help, plus anything on its site). It's ours, it's real, and it closes the loop: Bob builds the data, ModelForge trains on it. If the team picks another product, keep the same script.

**Before the demo (by 9:00):** run the full job once, fine-tune a small base model (0.5B to 1.5B, LoRA via ModelForge on the GPU box), and save a 5-question eval where the base model is wrong and the tuned model is right. Keep both models loaded.

1. **0:00 Hook.** "Every synthetic data tool is an LLM rewriting your docs. Bob uses zero LLM tokens, and every answer is computed from the source."
2. **0:15 Text it.** A judge texts Bob the product's docs URL. "On it."
3. **0:30 Read.** UI: pages crawled, Jev drops boilerplate, Extract pulls facts with source spans, and the fact graph grows on screen.
4. **0:55 Compose.** Rows stream in. Click a multi-hop row: its path lights up across three docs, with a computed answer and a reasoning trace. Show a DPO pair whose rejected answer swapped one value.
5. **1:15 Ship.** One click: ModelForge JSONL + Parquet + Postgres JSONB. Meter: "$0.04 spent. Opus 5.5 estimate: $6.90. **LLM tokens: 0**" (read from the gateway ledger).
6. **1:30 Prove it.** Side by side: base model vs model fine-tuned in ModelForge on Bob's data, asked a question about the product. Base model guesses; tuned model answers correctly and cites the step.
7. **1:50 Phone buzzes.** "1,000 rows, link attached."
8. **1:55 Close.** "Your docs, compiled into a model that knows your product. No LLM touched the data."

Keep a pre-run job in a second tab and the backup video ready.

## 10. Pre-event checklist
- [ ] ScaleDown account (50M free tokens), key, one Extract + one Summarize call; confirm `api.scaledown.xyz` request shape and output caps.
- [ ] Jev via OpenRouter Decisions API (`POST /api/alpha/decisions`) working; confirm model ID.
- [ ] Photon line provisioned; Firecrawl key; Convex project.
- [ ] `pip install` pyarrow fastavro orjson datasketch model2vec scikit-learn networkx pint inflect pymupdf python-docx trafilatura psycopg[binary] fastapi uvicorn httpx firecrawl convex.
- [ ] Confirm the demo product (default: ModelForge) and gather its docs into `demo/` (crawl the site if it has one, plus repo docs).
- [ ] ModelForge installed on the GPU box; a small base model (0.5B to 1.5B) downloaded; one throwaway LoRA run to confirm it trains in a few minutes.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Extraction errors (about 89.5% field accuracy in one test) | Keep high-confidence fields; span must appear verbatim; corroborate repeated facts; Jev checks fact vs span. |
| Repetitive phrasing | Big grammar bank; Jev picks the best of many; paraphrase stretch; Summarize for long answers. |
| Entity resolution merges wrong things | Conservative: exact-normalized match + high embedding similarity + same type. |
| Corpus not fact-dense | Pick the demo corpus carefully; fall back to Summarize-based tasks for narrative text. |
| ScaleDown or Jev access / request format | Working calls first; cache everything to disk; replay mode. Jev fallback: ScaleDown Classify (same Decisions API). |
| Summarize output cap and weak query focus | Use it for topic explanations and summaries only; keep factual answers programmatic. |
| Wifi / rate limits | Disk cache, replay, semaphores, hotspot, backup video. |
| Scope creep | Freeze at 9:00; multi-turn, Avro, JSONB, Photon, fine-tune loop are toggles. |

## 12. Prize targets
1. **Anthropic top 3**: novelty ("zero-LLM data generation") plus the team building it with Claude Code. The pipeline uses no Claude (or any LLM) by design; Claude Code is the team's build tool.
2. **Photon iMessage** ($1k): text a URL, get a dataset.
3. Name Firecrawl, Convex, ScaleDown, TypeSafe in the demo.
