# Research 03: Alternative and Complementary Approaches

> Source: research agent, 2026-10-30. Anthropic prices are from the official pricing page. Gemini and Mercury prices are from aggregators (confirm before quoting on stage).

## TL;DR
- **About 95% of synthetic-data cost is LLM output tokens.** So: (1) discard 70 to 90% of the corpus with CPU-only methods before any LLM call, and (2) make the LLM write as little as possible. Cheapest: **Humpback / instruction backtranslation**, where the source chunk is the answer and the LLM writes only the instruction.
- Cheapest strong model: **Claude Haiku 5.5**: $0.10 / $0.50 per M standard (prompts <= 100k), $0.05 / $0.25 batch.

| Approach | Cost per 1k examples |
|---|---|
| Humpback, Haiku 5.5 batch | about $0.04 |
| Grounded QA, Haiku 5.5 batch | about $0.10 |
| Same QA, Opus 5.5 only | about $8.40 |
| Opus 5.5 generate + judge (naive) | about $14 |

Headline: **80 to 350x cheaper than Opus.**

## A. Signal selection (cheap, mostly non-LLM)

| Rank | Technique | Does | Cost/speed | Tonight? |
|---|---|---|---|---|
| 1 | Heuristic filters (Gopher / C4 / FineWeb) | Kill boilerplate, menus, OCR junk, TOCs | Pure Python, 10k+ chunks/s/core | Yes, about 30 min |
| 2 | Static embeddings (Model2Vec potion) + k-means diversity | Cover every topic | CPU, seconds for 100k | Yes |
| 3 | MinHash LSH + semantic dedup | Remove repeats | `datasketch`; reuse embeddings | Yes |
| 4 | "Bob-Edu" classifier head (FineWeb-Edu recipe) | Learns user's definition of signal | About $0.04 of labels, trains in 2 s | Yes (wow) |
| 5 | Information density | Keywords, entities, numbers, definition/procedure patterns | spaCy sm / YAKE | Cheap add-on |
| 6 | Perplexity filter (KenLM / SmolLM2-135M) | Drop too-low and too-high perplexity | Fast | Optional |
| 7 | DSIR importance resampling | Reweight toward 5 to 50 user target examples | CPU | Stretch |

Heuristic rules (designed for web; relax for PDFs/CSVs):
- Gopher: mean word length 3 to 10; symbol/word < 0.1; <= 90% lines bulleted; <= 30% lines ending "..."; >= 80% words with a letter; >= 2 stop words; duplicate-line fraction <= 0.30; top 2-gram char fraction <= 0.20.
- C4: keep lines ending in terminal punctuation with >= 3 words; drop "lorem ipsum" or `{`; drop < 3 sentences.
- FineWeb: >= 12% lines end in punctuation; duplicate-line chars <= 10%; <= 67% short lines (< 30 chars).

FineWeb-Edu recipe, Bob version: label 300 to 500 chunks 0 to 5 for "useful as fine-tuning material for <user goal>" (Haiku 5.5 about $0.035, or Jev, see research 02), fit Ridge/LogReg on potion embeddings, score the rest for $0. (FineWeb-Edu: Llama-3-70B labelled 460k pages, linear head on arctic-embed-m, threshold 3, F1 82%.)

Embedding models:

| Model | Params | Throughput (est.) | Notes |
|---|---|---|---|
| potion-base-8M | 7.5M | 10k to 30k+ chunks/s CPU | MTEB about 51. Default |
| potion-base-32M / potion-retrieval-32M | 32M | Similar | Retrieval variant for groundedness |
| potion-multilingual-128M | 128M | Fast | Non-English |
| bge-small-en-v1.5 | 33M | 100 to 500/s ONNX CPU (much faster on GPU) | Better quality |
| nomic-embed / ModernBERT-embed | 137 to 150M | 30 to 150/s CPU | Long chunks; use GPU box |

Dedup: MinHash 5-gram shingles, 128 perms, LSH Jaccard 0.8. Semantic: within cluster drop cosine > 0.95. Diversity: k about sqrt(N), sample per cluster proportional to sqrt(size) x mean quality.

## B. Generation (cheap)

Prices (USD per M tokens, in/out):

| Model | Standard | Batch | Source |
|---|---|---|---|
| Claude Haiku 5.5 (<= 100k prompt) | $0.10 / $0.50 | $0.05 / $0.25 | Official. Cache hit $0.01; > 100k prompt jumps to $0.50 / $2.50 |
| Claude Haiku 4.5 | $1 / $5 | $0.50 / $2.50 | Official |
| Claude Sonnet 5.5 | $2 / $10 | $1 / $5 | Official |
| Claude Opus 5.5 (baseline) | $4 / $20 | $2 / $10 | Official |
| Claude Fable 5.1 (top baseline) | $10 / $50 | $5 / $25 | Official |
| Gemini 3.1 Flash-Lite | about $0.25 / $1.50 | about half | Aggregators |
| Inception Mercury 3 | $0.20 / $0.70 list | n/a | Aggregators |
| Llama 3.1 8B hosted | about $0.02 to $0.05 / $0.05 | n/a | Aggregators |

Cost per 1k (chunk 400 tok, prompt 200, question 60, answer 250):
1. **Humpback** (600 in, 60 out): about $0.045/1k batch, $0.09/1k standard. Add a 1 to 5 self-curation score in the same call and keep 4s and 5s. Caveat: answers read like documents; fix with an assistant-style rewrite tier on the top 20%.
2. **Multi-QA per chunk** (5 pairs per call): about $0.08/1k batch. Single QA per call: $0.105/1k batch, $0.21/1k standard.
3. **Templates / extractive, no LLM: $0.** CSV row templates, "Explain {heading}", "What is X?" from definition sentences, cloze, table lookups.
4. **Local small models** on GPU via vLLM (Qwen3-4B/8B, Llama-3.1-8B, Genstruct-7B, Bonito-8B with 16 task types): about $0.03 to $0.05/1k at rental prices, $0 marginal on our own box.
5. Gemini Flash-Lite about $0.18 to $0.60/1k; Mercury about $0.17 to $0.33/1k (speed, about 1,000 tok/s).
6. Baselines: Opus 5.5 QA $8.40/1k; with Opus judge about $14/1k; Fable 5.1 $21/1k.

Use sparingly: Magpie (ungrounded), Self-Instruct / Evol-Instruct (3 to 5x calls; Evol only top 5 to 10%), distilabel (good but heavy to wire tonight).

DPO pairs at near zero cost:
- Chosen: grounded answer (or source chunk in Humpback mode).
- Rejected: (a) Haiku answering without context (plausible hallucination, about $0.07/1k batch); (b) free perturbations: entity/number swap from a same-cluster chunk, truncation, neighbour-cluster answer; (c) tiny local model output.
- Record `rejection_strategy` per pair.

Batch API can take up to 24h: run live demo on standard, show a "Batch -50%" toggle in the cost meter.

## C. Quality control (cheap first, LLM last)
1. Groundedness (free): cosine(answer, chunk) with potion-retrieval-32M, reject < about 0.55 (calibrate); ROUGE-L / token overlap; extractive answers must be substrings. Optional NLI cross-encoder (DeBERTa-v3 MNLI).
2. Question quality (free): length bounds; ends in "?" or imperative; reject answer leakage; regex reject "according to the text" / "this document".
3. Output dedup: MinHash on questions; embedding dedup on pairs at cosine > 0.92.
4. Decontamination: 13-gram overlap vs MMLU, GSM8K, HumanEval, ARC. PII scrub (Presidio or regex).
5. Optional small reward model (Skywork-Reward-V2 0.6B to 1.7B class) to rank DPO pairs.
6. Sampled judge certificate: 5% with Sonnet 5.5 batch about $0.06/1k, or 10% Haiku about $0.006/1k. Report pass rate with Wilson 95% CI ("93% +/- 4% grounded and helpful").

## D. Prior art and competitors

| Tool | What | Gap Bob fills |
|---|---|---|
| Meta synthetic-data-kit | CLI ingest, create, curate (LLM), save | LLM-heavy, no pre-selection, no cost accounting, no UI |
| Unsloth | Fast fine-tuning | Training tool; export target |
| Argilla / distilabel | Pipeline framework | Engineer framework, no upload-to-dataset flow |
| NVIDIA NeMo Curator | GPU pretraining-scale curation | Not for small corpus to SFT/DPO |
| Gretel / NeMo Data Designer | Schema/prompt synthesis | Not corpus-grounded selection |
| DataDreamer | Research library | No product UX |
| Bonito | 7B/8B task generator | A model; usable as local backend |
| Easy Dataset (10k+ stars) | GUI docs to fine-tuning data | Closest competitor; LLM on every chunk, no non-LLM selection, no cost meter, no DPO by perturbation |
| Kiln | Desktop synthetic + evals | Prompt-driven, not corpus mining |

Differentiation: select before generate; full provenance per row; cost receipt + quality certificate; formats nobody else exports (Parquet, Avro, Postgres JSONB with DDL) plus OpenAI chat, ShareGPT, Alpaca.

## E. Recommended architecture (this agent's version; merged into ../PLAN.md)
```
Upload -> parse -> chunk (300-500 tok, heading aware) -> heuristics ($0)
 -> potion embeddings -> MinHash + semantic dedup ($0)
 -> Bob-Edu head (about $0.04 labels) + info density -> signal score
 -> k-means quota sampling under BUDGET
 -> router: templates ($0) | Humpback (default) | multi-QA/rewrite (top 20%) | DPO
 -> QC: groundedness, regex, dedup, decontam, PII, 5% judge -> pass rate +/- CI
 -> export: JSONL presets, JSON, CSV, Parquet, Avro, Postgres JSONB .sql
```
Full pipeline cost, 1M-token corpus to 2,000 SFT + 500 DPO (Haiku 5.5 standard): labels $0.035 + Humpback $0.18 + DPO $0.07 + judge $0.12 = **about $0.40** (about $0.16 per 1k). Same with Opus 5.5 only: $25 to $35.

Wow features:
1. Live cost meter vs Opus 5.5 / Fable 5.1 with running multiple ("212x cheaper"), split by savings source; Batch toggle halves it live.
2. Signal map: 2D UMAP of chunks coloured by score; dropped chunks fade stage by stage; click to see chunk and its examples.
3. Budget slider ("best dataset for 10 cents"): quality-per-dollar knapsack across tiers, ends in a Dataset Certificate (judge pass rate +/- CI, decontam clean, PII scrubbed, 100% provenance).

## Sources
- https://platform.claude.com/docs/en/about-claude/pricing
- https://pricepertoken.com/pricing-page/model/anthropic-claude-haiku-5.5
- https://anotherwrapper.com/llm-pricing/gemini-3.1-flash-lite-preview, https://www.morphllm.com/gemini-api-pricing
- https://www.inceptionlabs.ai/models, https://openrouter.ai/inception/mercury
- https://perkstack.co/blog/cheapest-llama-3-1-8b-api
- FineWeb-Edu: https://arxiv.org/pdf/2406.17557
- Model2Vec: https://github.com/MinishLab/model2vec, https://minish.ai/packages/model2vec/results/
- Bonito: https://www.arxiv.org/pdf/2402.18334, https://huggingface.co/BatsResearch/Llama-3.1-8B-bonito-v1
- Gretel/NVIDIA: https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel
- Easy Dataset / Kiln: https://arxiv.org/abs/2507.04009
- From model knowledge (verify): Humpback arXiv 2308.06259, Magpie 2406.08464, SemDeDup 2303.09540, DSIR 2302.03169, Gopher 2112.11446, C4 1910.10683, CCNet 1911.00359, Genstruct-7B.
