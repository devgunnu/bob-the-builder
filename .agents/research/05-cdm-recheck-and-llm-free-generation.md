# Research 05: CDM Recheck and LLM-Free Generation

> 2026-10-30, after the founder challenged research 02. **This file supersedes the CDM sections of research 02.**
> Network note: docs.scaledown.ai, openrouter.ai, dev.to, medium.com and ibl.ai could not be fetched from the research sandbox. Facts below come from search-result snippets of those pages. Verify against docs.scaledown.ai at 5:00pm.

## 1. The correction
Research 02 searched for "Constrained **Decision** Models" and found nothing, so it treated CDM as a loose category of decision models. The real term is **Constrained Decoding Models (CDMs)**, a product family launched by **ScaleDown** on 2026-10-13. They do produce text, inside limits set by the task. The founder was right.

## 2. What ScaleDown CDMs are

| Model | Output | Notes |
|---|---|---|
| **Summarize** (`summarize`, OpenRouter `scaledown/summarize`) | **Text.** Summaries of long text, images, PDFs; vendor says it covers extractive *and* abstractive summarization | Output cap reported as 1,000 tokens natively (OpenRouter lists 4,000). Independent test (n=6 QMSum meetings): ROUGE-L 0.230 vs 0.201 for local Qwen3-1.7B, **no invented facts** (Qwen had two). Weakness: query focus (summarized the presentation instead of answering "what did the PM question"). |
| **Extract** (`extract` / `extract-1`, OpenRouter `scaledown/extract`) | JSON fields you describe, each with **confidence + character-offset source span** (+ context window, default 500 chars per side) | OpenAI-compatible chat completions at `api.scaledown.xyz`; text in last user message; fields via standard `response_format` JSON schema. Nested objects and arrays supported (Vercel listing). Schema is guidance, not validation (types/enums/required not enforced; LiteLLM). Multiple matches ordered by confidence. Independent receipt test: 89.5% field accuracy, **100% verbatim spans** (local Qwen3-1.7B: 94%). Judgment fields are routed to the classify model; their spans point at evidence. |
| **Classify** (`scaledown/classify-1`) | Probabilities over your labels | Runs on the OpenRouter **Decisions API**, not chat completions (same family as Jev). |
| **Compress** | Compressed prompt/context | `POST /compress/raw/`; compression rate `auto` or fraction to remove. |

- **Price:** $0.04 per M input tokens, **$0 output** on OpenRouter (Vercel lists Extract at $0.05). 1M-token context listed. **New accounts get 50M free tokens** (LangChain integration docs), which covers the whole hackathon.
- **Claims:** "200x faster, 467x cheaper than frontier LLM APIs" (vendor, unverified).
- **Architecture:** "constrained space scoring and span pointing" (partner guide). ibl.ai's critique: constrained decoding is a decoding-time technique, not a new architecture, and the "skips autoregressive generation" claim holds for two of the three models but not one (most likely Summarize, given it writes abstractive text). Integrations: `langchain-scaledown`, LangSmith gateway, LiteLLM provider.

**Implication:** CDMs are small single-task models, not general LLMs. Extract and Classify cannot write new text. Summarize can, within limits. Jev (research 02) still owns decisions.

## 3. Can we generate synthetic data with no LLM at all? Yes.

The honest constraint: an LLM-free system cannot write free-form text about anything. It *can* produce large amounts of **new, correct, varied** training data when it works like a compiler. Read the corpus into structured facts, **program** new examples from those facts, then put them into natural language with constrained models. This is how procedural math and reasoning datasets are built, and it is stronger than LLM generation on one axis: **answers are computed or copied, so they are correct by construction.**

### The engine: Extract, Compose, Realize, Rank

```
chunks ──► EXTRACT (ScaleDown Extract)          facts with source spans
             │  entities, attributes, relations, numbers+units,
             │  definitions, procedures(steps), causes/effects, conditions
             ▼
        FACT GRAPH  (entity resolution: normalized names + embedding merge)
             │
             ▼
        COMPOSE  (question programs over the graph; answers COMPUTED)
             │  lookup, inverse lookup, multi-hop chains, comparisons,
             │  arithmetic (differences, ratios, unit conversion), aggregation
             │  (count / list / superlative), procedure order, definition,
             │  cause→effect, conditional, true/false + correction,
             │  multi-turn walks, chain-of-thought traces from the hop path
             ▼
        REALIZE  (overgenerate surface forms)
             │  grammar bank: 20-50 phrasings per program type, slot inflection,
             │  answer = computed value + justification from source spans,
             │  optional ScaleDown Summarize to fuse supporting spans into prose
             ▼
        RANK  (Jev Choice: pick the most natural of up to 255 candidates;
             │  Jev Noul: "fluent and unambiguous?", "answerable alone?")
             ▼
        new SFT / chat / CoT / DPO rows, zero LLM tokens
```

### Why the result is new data, not reformatted data
- **Multi-hop:** "Which service that depends on Postgres has the lowest timeout?" joins facts from three different chunks. That sentence and its answer appear nowhere in the corpus.
- **Computed answers:** comparisons, differences, unit conversions, counts and superlatives are calculated by code, so the model learns to reason over facts instead of memorising sentences.
- **Reasoning traces:** the graph path *is* the chain of thought. "Step 1: X depends on Y (doc A, p3). Step 2: Y's timeout is 30s (doc B, p1). ..." That gives verifiable CoT data with no LLM.
- **Multi-document synthesis:** Summarize run over a *cluster* of related chunks gives a "explain topic T" answer that no single chunk contains.
- **Combinatorial scale:** a graph with 2,000 facts supports tens of thousands of distinct programs. Diversity is controlled by sampling programs to cover the graph, not by temperature.
- **Hard DPO negatives for free:** rejected = the same program run with a perturbed fact (a sibling entity's value, a wrong hop, an off-by-one step). These are plausible, subtly wrong, and labelled with exactly what is wrong.
- **Verifiable-reward data:** every computed answer is checkable, so the same rows can feed GRPO/RLVR trainers (not ModelForge yet, which lacks GRPO).

### Stretch: Jev as a decoder ("decision-decoded text")
Build a sentence phrase by phrase: at each step, a phrase bank mined from the corpus plus the grammar proposes candidates, and Jev `Choice` picks the next phrase given the state so far. That is literally constrained generation by decisions. At about $0.00002 per step and about 8 phrase steps per sentence, that is about $0.0002 per sentence. Use it to paraphrase realized questions for extra diversity. Demo value is high; build only after the main engine works.

### Cost (1M-token corpus, about 600k tokens kept after free filters)

| Step | Calls | Cost |
|---|---|---|
| Jev triage (6 questions per chunk) | about 1,500 | about $0.04 |
| ScaleDown Extract over kept chunks | about 1,500 | about $0.03 |
| Summarize (cluster explanations, 300 clusters x about 3k tokens in) | 300 | about $0.04 |
| Jev rank (5,000 examples x about 1.5k tokens of candidates) | 5,000 | about $0.32 |
| **Total for about 5,000 rows** | | **about $0.43 at list price, $0 under the 50M free tokens** |
| LLM tokens used | | **0** |

Same 5,000 rows via Opus 5.5 generate + judge: about $70.

### Where it is weaker (be upfront with judges)
1. **Open-ended voice.** Template-realized questions can feel repetitive. Mitigations: big grammar bank, Jev ranking, Jev-decoded paraphrase, Summarize for long-form answers.
2. **Extraction quality caps everything.** One test measured 89.5% field accuracy. Mitigations: keep only high-confidence fields, require the span to appear verbatim in the source, cross-check repeated facts across chunks, and let Jev verify each fact against its span.
3. **Best on fact-dense corpora:** docs, manuals, specs, policies, product catalogs, tables, research papers. Weaker on narrative, opinion or dialogue corpora (Summarize-based tasks still work there).
4. **Summarize** has a 1,000-token cap and weak query focus, and whether it is "non-autoregressive" is disputed. It is still a small single-task model, not an LLM.
5. Vendor claims (speed, cost, architecture) are unverified; docs could not be fetched today.

## 4. Verdict on the original hypothesis (revised)

| Part | Revised verdict |
|---|---|
| Jev classifies chunks | **Keep.** Also ranks realizations and verifies, and can decode phrase by phrase. |
| CDMs generate the dataset | **Keep, as the founder intended.** ScaleDown Extract builds the fact graph, Summarize writes constrained prose, and code composes new examples. No LLM anywhere in the pipeline. |
| LLM writer (research 03/04) | Demoted to an **optional, off-by-default "polish" tier**, and as the baseline in the cost comparison. |

## Sources
- ScaleDown on OpenRouter: https://openrouter.ai/scaledown, https://openrouter.ai/scaledown/summarize, https://openrouter.ai/scaledown/extract, https://openrouter.ai/scaledown/classify-1, https://openrouter.ai/scaledown/extract/llms.txt
- ScaleDown docs: https://docs.scaledown.ai/api-reference/extract
- LiteLLM provider: https://docs.litellm.ai/docs/providers/scaledown
- Vercel AI Gateway: https://vercel.com/ai-gateway/models/scaledown-summarize-1, https://vercel.com/ai-gateway/models/scaledown-extract-1
- Launch: https://x.com/neal_k_patel/status/2109978626124898587, https://x.com/OpenRouter/status/2109989782302716140, https://x.com/exec_sum/status/2110045480398803243, https://x.com/ChrisGPT/status/2110063757703495935
- Independent test: https://dev.to/ishank-dev/scaledown-cdms-fast-cheap-classify-extract-and-summarize-models-tested-1adp
- Critique: https://ibl.ai/blog/constrained-decoding-models-not-a-new-architecture
- Guides: https://www.starlingelevate.com/blog/constrained-decoding-models-cdm-full-guide, https://tinyml.substack.com/p/the-world-of-summarization, https://storeofscope.substack.com/p/cdms-jev-and-the-decisions-around
- Compress / LangChain: https://docs.langchain.com/oss/python/integrations/middleware/scaledown, https://www.langchain.com/blog/building-long-running-agents-with-scaledown-and-deep-agents, https://benchlm.ai/models/scaledown-compress
- Jev: https://www.requesty.ai/blog/typesafe-jev-explained, https://www.sanity.io/glossary/jev-typesafe-ai-model
- Constrained generation background: https://www.ijcai.org/proceedings/2025/1115.pdf, https://arxiv.org/html/2309.12415, https://github.com/Hellisotherpeople/Constrained-Text-Generation-Studio
