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

## D12. Zero-LLM generation engine (v2)
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

## D15. [PROPOSED, awaiting team] Generator library for fine-tuning rows
- Bob synthesizes dataset rows for any corpus with zero LLM: knowledge from the fact graph, language from CDMs + grammars + deterministic transforms, judgement from Jev + verifiers.
- Eleven generators (research/07). Core tonight: task multiplier, corrupt-and-restore, constraint compositor, knowledge composer, abstention, preference pairs.
- ModelForge stays only a compatible export target (D9). Research/06's ModelForge-centred oracle idea is withdrawn.

## D16. LLM proposes, Bob proves (v3, team decision)
- **Why:** hand-written templates can't cover every use case and the output reads as templated. An LLM is needed for generality and natural language.
- **Roles:** Architect (strong model, per corpus) writes the task taxonomy, extraction schema, generator programs, verifier code and unit tests (AutoIF-style). Writer (cheap model, per row) phrases rows with answer slots locked. Jev, ScaleDown and code verify every row.
- **Kept:** fact graph, computed answers, abstention / false-premise families, programmatic defect injection for DPO, provenance, all verifiers.
- **Eval:** human-written test set (incl. fake-feature questions) and a naive-LLM-data baseline, so results aren't circular.
- Details: research/09.

## D17. [PROPOSED] Position Bob for behaviour, not memorisation
- RAG beats unsupervised fine-tuning for knowledge (Ovadia et al., EMNLP 2024), so "a model that memorised your docs" is a weak pitch.
- Bob's main use case becomes RAFT-style data: question + relevant chunk + verified distractors -> cited answer, plus "not in the retrieved docs" abstentions. Second: narrow-skill distillation (extraction, classification, house-style replies, tool calls).
- Demo: 4 models with the same retrieval, scored on human-written questions; hallucination rate is the headline. Details: research/10.

## Open questions for the team
1. Demo product: ModelForge (default) or another real product?
2. Is the Photon iMessage prize worth one person's evening, or should D go all in on the web UI?
3. ~~Strict zero-LLM?~~ Reversed: LLM in controlled roles (D16).
5. Writer: Claude Haiku 5.5 via API, or a local model on the GPU box?
6. Architect: Opus 5.5 or Sonnet 5.5?
4. Do we need non-English corpora (switch to potion-multilingual-128M)?
