# Bob the Builder: Decision Log

Each entry: decision, why, what would change it.

## D1. Jev is the classifier (kept from the original hypothesis)
- **Why:** Jev is a non-generative decision model priced at $0.042 per M input tokens with free output, about 200 to 300 ms per call, multiple questions per call, calibrated probabilities. TypeSafe pitches it for corpus classification. About $0.06 to classify a 1M-token corpus.
- **Watch:** about 11.5% wrong at ≥ 90% confidence; follows option names over rubric (arXiv 2609.26758). Mitigated by descriptive option names, hand-label thresholds, a name-swap check.
- **Would change if:** we cannot get access tonight. Fallback order: Cloudflare Clef-flash (same API shape), then a distilled head on embeddings.

## D2. CDMs decide and verify; they do not write
- **Why:** Constrained Decision Models only output probabilities over declared options. They are used for extractive sentence selection, template routing, verification, and preference judging.
- **Would change if:** a decision-model vendor ships constrained text output.

## D3. Humpback (instruction backtranslation) is the default writing mode
- **Why:** output tokens are about 95% of cost. Treating the source chunk as the answer means the writer emits about 60 tokens per example and answers are grounded by construction.
- **Trade-off:** answers read like documents. Assistant-rewrite tier for the top 20% fixes this.

## D4. Writer backends: local vLLM on the GPU box first, Haiku 5.5 second, templates always
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
- Firecrawl (URL ingest), Convex (live progress + public file links), Photon (text a URL, get a dataset), Anthropic (writer + judge). Skip Mercury (banking), HeyPCB, Nebula.

## D11. Dropped
- JEPA / LLM-JEPA: a training objective, not usable tonight.
- Local Clef: needs 41 to 54 GB VRAM and unmerged vLLM support.
- distilabel: good framework, too heavy to wire in five hours.
- Magpie / Self-Instruct / Evol-Instruct as defaults: ungrounded or 3 to 5x cost. Evol may be applied to the top 5 to 10% as a stretch.

## Open questions for the team
1. Demo corpus: which docs site or file set will judges care about most?
2. Is the Photon iMessage prize worth one person's evening, or should D go all in on the web UI?
3. Which writer model fits the GPU box's VRAM (decides Qwen3-8B vs 4B vs larger)?
4. Do we need non-English corpora (switch to potion-multilingual-128M)?
