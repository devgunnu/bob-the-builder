# Research 02: Validating "Jev classifies, CDMs generate"

> Source: research agent, 2026-10-30. Several domains (openrouter.ai, huggingface.co, typesafe docs) were blocked in the research sandbox; many figures come from third-party write-ups and vendor claims. Verify against docs.typesafe.ai and provider docs in the first 30 minutes.

## Verdict
**Keep Jev as the classifier: it fits very well. Reword "CDMs generate the dataset": decision models cannot write text.** Give decision models the jobs of selecting, routing, verifying, and judging, and let templates or a cheap generator write the words.

## 1. What the terms mean

### Jev: TypeSafe AI's "System One" decision model (confirmed)
- Non-generative. You send a `state` (text) plus named `questions`; it returns typed answers with calibrated probabilities. Question types:
  - **Noul**: yes/no probability.
  - **Choice**: up to 255 options, a probability for each.
  - **Score**: 2 to 10 ordered rubric levels, returned as a weighted score.
- Early access 2026-09-15. TypeSafe raised a $40M seed led by DCVC. Architecture undisclosed; trained with "RLCD" (Reinforcement Learning for Calibrated Decisions). TypeSafe explicitly pitches it for "AI map reduce jobs for classifying large corpora", which is our use case.
- Price: $0.042 per 1M input tokens, output free. Measured $0.000015 to $0.00003 per decision.
- Latency: about 184 to 313 ms p50 (first party and OpenRouter vary; OpenRouter p90 about 1.7 s). Five questions per request cost about the same server time as one.
- Context: 32k to 64k tokens (sources conflict). Rate limits unclear (one source: 1,200 RPM).
- Access:
  - OpenRouter: `POST /api/alpha/decisions` (not `/chat/completions`), model `typesafe/jev-1.13-20260917` (1.14 also referenced). Not in the public model list.
  - Vercel AI Gateway: `typesafe-ai/jev` via the AI SDK experimental evaluate method.
  - Also DigitalOcean (`/v1/systemone`), Requesty, Cloudflare.
  - Direct `api.typesafe.ai/v1/systemone` was waitlisted (conflicting reports on whether that ended). OpenRouter/Vercel reportedly need no approval.
  - Do not send `temperature` or `max_tokens`. Use raw HTTP, not an OpenAI SDK.
- Measured accuracy: 27/27 on support tickets; 94.0% on simple choices; 79% on 59 to 77 option sets. **11.5% of answers at >= 90% confidence were wrong** (Clef and d1: 2 to 3%). TypeSafe's own benchmark: 67.8% vs 74.1% for a frontier model.
- Weak spots: counting/arithmetic, date comparisons, double negatives, bloated context, contradictory instructions, prompt injection inside the data.
- **Critical caveat:** arXiv 2609.26758 ("Type-Safe Is Not Error-Free") found that renaming options from `0/1` to `no/yes` flipped 70 of 100 answers (AUC 0.94 to 0.23). The model follows option *names*, not the rubric bound to them.

### CDM: "Constrained Decision Model" is a category, not a product
No formal definition found; nearest is the "constrained decision head" in the paper above. In practice: models whose output is constrained to a schema you declare, returning probabilities over your options.

| Model | Who | Weights | Notes |
|---|---|---|---|
| Jev 1.13/1.14 | TypeSafe | Closed | $0.042/M input |
| Clef 27B | Cloudflare | Apache-2.0 | $0.24/M input; about 54 GB BF16; Jev-compatible API |
| Clef-flash 9B | Cloudflare | Apache-2.0 | $0.09/M input on Workers AI; hosted context about 24k; reportedly >= 41 GB VRAM; released 2026-10-01 |
| Strands Decider 2B | AWS Strands | Open (reported) | Small |
| OpenAI Decisions API, Microsoft-Decision-1, d1 | various | Closed | OpenAI's in beta since 2026-10-06 |

**Key fact: none of these generate text.** Output is the decision JSON only.

### Fallback interpretations (not the founder's meaning)
- JEPA / LLM-JEPA: a training objective, not usable off the shelf tonight. Drop.
- Diffusion LMs: relevant only as an optional fast generator. Mercury 2.5 (Inception): $0.04/$0.15 per M at launch promo (list $0.20/$0.75), about 857 to 1,107 tok/s, JSON schema support, 77% IFBench. DiffusionGemma 26B-A4B open weights with vLLM. "Lost in Diffusion" (ACL Findings 2026): diffusion LMs hallucinate more than matched autoregressive models, so always verify.

## 2. Does each half work?

### (a) Chunk classification with Jev: yes, strongly
One call per chunk, several questions:
- `Noul` self-contained factual or procedural content that could answer a question?
- `Score` information density, 4 to 5 level rubric.
- `Choice` best task type: `qa | instruction | howto | definition | comparison | reasoning | not_useful`.
- `Noul` boilerplate / navigation / legal?
- `Noul` contains PII?
- `Noul` contains instructions aimed at an AI (injection)?

Cost: 400-token chunk + about 200 tokens of question definitions is about $0.000025. **10k chunks about $0.25; a 1M-token corpus about $0.05.** With 32 to 64 concurrent requests, 10k chunks in a few minutes.

Risk fixes:
1. Option-name sensitivity: put meaning in the option name (`useful_self_contained_fact`, not `1`). Run a name-swap check on 50 chunks; it doubles as a "we measured robustness" demo point.
2. Overconfidence: set thresholds from 50 to 100 hand-labelled chunks, not raw 0.9.
3. Prompt injection: strip instruction-like text first or flag it with a separate Noul.

### (b) Generation with CDMs: not as stated; yes once redefined
Decision models can:
1. **Extractive selection.** Split a chunk into sentences, pass them as `Choice` options (<= 255): "which sentence is the key claim?" / "which answers Q?". Answers come verbatim from source, grounded by construction.
2. **Template routing.** `Choice` over templates ("What is X?", "How do you X?", "Why does X?", "Compare X and Y"), fill slots from spaCy noun chunks or headings. Zero-LLM pairs, mediocre fluency, about $0.
3. **Verification.** After any generator: `Noul` "answer fully supported by passage?" and `Noul` "question answerable from passage alone?". Drop below threshold.
4. **Preference pairs.** Chosen = grounded answer; rejected = neighbour-chunk, truncated, or perturbed answer. Jev `Score`s both; keep clear margins. A/B `Choice` judge run in both orders to cancel position bias.

Fluent text still needs a cheap generator:

| Generator | Cost, about 1M-token corpus (30% kept) | Notes |
|---|---|---|
| Mercury 2.5 (promo) | about $0.03 | Fast, JSON schema; verify with Jev |
| gpt-5-nano ($0.05/$0.40) | about $0.08 | Can be slow (7.5 s median measured) |
| Local model on GPU box via vLLM | about $0 marginal | Setup time |
| Templates only | $0 | Free tier |

(See research 03: Claude Haiku 5.5 at $0.10/$0.50 standard is in the same price band with stronger instruction following.)

## 3. Recommendation

| Part | Verdict | Stronger version |
|---|---|---|
| Jev as chunk classifier | KEEP | Multi-question call; thresholds tuned on about 100 hand labels; descriptive option names + name-swap check |
| "CDMs generate dataset" | REWORD, KEEP CDM | CDMs select, route, verify, judge. Text from templates or a cheap generator |
| Clef / Clef-flash | Optional fallback | Jev-compatible API, so swap is an endpoint change. Do not plan on local Clef tonight (>= 41 to 54 GB VRAM, vLLM support unmerged) |
| Diffusion LM | Optional generator | Always followed by Jev verification |
| JEPA | DROP | |

**Pitch:** "System 1 decides, a tiny model writes, System 1 verifies. Every row carries a calibrated faithfulness probability." Cost per 1M-token corpus: about $0.05 classify + $0.03 to $0.08 generate + $0.02 verify.

Fallback if Jev access fails: embedding model on the GPU box + logistic regression on about 200 labels, ideally trained on cached Jev labels ("distilled System 1"). Generation fallback: templates only.

## Sources
- Jev: https://sebastianraschka.com/blog/2026/jev-classification-generalization.html, https://magazine.sebastianraschka.com/p/classifier-history-and-jev, https://github.com/WallerChen/jev-measured, https://www.vktr.com/ai-platforms/chatgpt-cocreator-launches-typesafe-ai-with-jev/, https://thenewstack.io/typesafe-jev-system-one/, https://www.digitalocean.com/resources/articles/what-is-jev, https://www.eesel.ai/blog/typesafe-jev, https://docs.typesafe.ai/introduction/machine-learning-primer
- Jev API/limits: https://openrouter.ai/typesafe/jev-1.13, https://openrouter.ai/docs/guides/community/jev, https://openrouter.ai/blog/insights/what-is-jev/, https://docs.digitalocean.com/products/inference/how-to/use-system-one-api/, https://zuplo.com/docs/ai-gateway/jev.md, https://www.layer3labs.io/guides/jev-limits, https://www.requesty.ai/models/typesafe/jev-1.14.0, https://apidog.com/blog/how-to-access-jev/, https://qdrant.tech/blog/jevjitsu/
- Decision models: https://arxiv.org/pdf/2609.26758, https://blog.cloudflare.com/clef-decision-models/, https://www.eesel.ai/blog/cloudflare-clef-pricing, https://latenode.com/news/cloudflare-cuts-clef-flash-price-trims-hosted-context-to-24k, https://www.theregister.com/a/5300649, https://www.eesel.ai/blog/decision-models, https://aimultiple.com/decision-models
- Fallbacks: https://arxiv.org/html/2509.14252v2, https://inceptionlabs.ai/blog/introducing-mercury-2-5, https://artificialanalysis.ai/es/models/mercury-2-5/providers, https://arxiv.org/pdf/2604.10556, https://www.morphllm.com/cheapest-llm
