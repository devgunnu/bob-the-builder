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

## D20. Bob makes data only; no training in the product
- **Decision:** remove the training step. Bob does not fine-tune or evaluate a tuned model. This replaces the live fine-tune in D14 and the model evals in D16 and D17.
- **Gap signals without training:** (1) coverage gaps (cells under target); (2) rejection rate per cell (a hard cell gets more weight); (3) base-model probing (stretch): ask a base model the kept questions and boost the cells where it fails.
- **Why:** a fine-tune and a fair eval do not fit in 4 hours with everything else, and the verification loop is the product (research 10). Student-in-the-loop training was considered and dropped (research 11).
- **Would change if:** the build finishes early and a trainer (for example ModelForge, through the export files in D9) can run a short job with no code change in Bob.

## D21. Verification cascade, and the roles of Jev and the CDMs
- **Decision:** 3 tiers per candidate (CONTRACTS section 4). Tier 1 is code: format, banned phrases, dedup, numbers. Tier 2 is one Jev call (questions by case type) plus a ScaleDown Extract invented-feature check against the evidence index. Calibrated probabilities route the row: keep at `confidence >= KEEP_P` (0.9); reject on a hard fail or under `REJECT_P` (0.3); else tier 3. Tier 3 is the Sonnet 5.5 judge, on about 5% uncertain rows plus a 2% random audit of kept rows.
- **Jev roles:** triage each chunk (useful, boilerplate, PII, injection); check every candidate; confirm that the top-5 retrieved chunks do not answer a "not in docs" question; label the real topic of each kept row, so coverage is measured.
- **CDM roles:** Extract builds the evidence index with verbatim spans and pulls feature, setting, URL and limit names from each reply. Summarize writes topic briefs. Compress shrinks Writer context. Classify is the first Jev fallback.
- **Guards:**
  - Jev is about 11.5% wrong at >= 90% confidence. Every kept answerable row needs both `jev.supported` and `extract.names`. The tier-3 audit measures the real error rate on each job.
  - Jev follows option names. Use descriptive names only, never `0/1`.
  - Jev is weak at arithmetic and dates. The tier-1 `numbers` check covers this in code.
  - Extract field accuracy is about 89.5%. Code keeps only fields whose `span_text` is a verbatim substring of the input.
- **Real fallbacks (no stubs):** Jev -> ScaleDown Classify -> Haiku JSON. Extract -> Haiku extraction with the same verbatim-span check. The UI shows a badge when a fallback is in use.
- **Why:** "The LLM writes, and small decision models check every row. The frontier model only looks at the rows where the checks disagree." The estimate is about $1.70 per 1,000 kept rows, against about $20 frontier-only (PLAN section 10).
- **Would change if:** the audit shows low tier-2 vs tier-3 agreement (for example, under 85%). Then raise `KEEP_P` or send more rows to the judge.

## D22. Models: Anthropic on AWS Bedrock
- **Decision:** Writer = Claude Haiku 5.5. Judge and Planner = Claude Sonnet 5.5. All calls go through `anthropic.AsyncAnthropicBedrock`, with prompt caching on the Writer system prompt and topic brief, and 5 candidates per Writer call. This replaces D4 (local vLLM) and the Opus 5.5 Architect question.
- **Why:** one provider and one set of AWS credentials for all generative calls. The cheap model does the volume. The strong model plans once and judges only the uncertain rows.
- **Would change if:** the model IDs or inference profiles are not enabled in our region at T+0:00. Then use the cross-region inference profile.

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

## Open questions
Still open:
1. Exact Bedrock model IDs or inference profiles for Haiku 5.5 and Sonnet 5.5, and the region. Check at T+0:00 (CONTRACTS section 9).
2. Jev request and response shape on OpenRouter `/api/alpha/decisions`, and the model version (1.13 or 1.14). A2 confirms in the first 20 minutes.
3. ScaleDown: direct `api.scaledown.xyz` or through OpenRouter, and the exact Extract schema format.
4. Which Composio toolkits are enabled on our account. Notion is required (P0); Jira, Confluence or Google Drive is P1.
5. Demo Notion content: who writes the 5 to 10 internal-style pages, and do they match the product in the Firecrawl docs?
6. Current prices for Haiku 5.5, Sonnet 5.5, Jev and ScaleDown, for the cost meter and the frontier-only estimate.
7. Do we need non-English corpora (switch to potion-multilingual-128M)?

Answered:
- ~~Demo product: ModelForge or another real product?~~ Firecrawl docs plus Notion pages (D24).
- ~~Is the Photon iMessage prize worth it?~~ Dropped (D24).
- ~~Strict zero-LLM?~~ Reversed (D16). Now Writer, Planner and Judge in controlled roles (D21, D22).
- ~~Writer: Haiku 5.5 via API, or a local model?~~ Haiku 5.5 on Bedrock (D22).
- ~~Architect: Opus 5.5 or Sonnet 5.5?~~ No Architect (D18). Sonnet 5.5 is the Planner and Judge (D22).

