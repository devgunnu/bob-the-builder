# Research 10: Why a product? Why a fine-tuned model?

> 2026-10-30. The two questions every judge and customer will ask. Honest answers, with evidence, and what they change in the plan.

## Q1. "Why do I need Bob? I can just ask Claude to write my dataset."

**For a few hundred rows, you don't.** Prompting a frontier model is fine. Generation itself is commoditized.

You need a product when prompting breaks down:

| Prompting it yourself | What goes wrong | What Bob adds |
|---|---|---|
| Scale (10k+ rows) | Hand-run prompts, rate limits, cost of a strong model per row | Architect once, cheap Writer per row, batching |
| Correctness | Hallucinated answers you can't see; checking needs another LLM | Every row verified against source and its own checker code; failures dropped and counted |
| Coverage | The model writes about what it finds interesting; whole sections get skipped; near-duplicates pile up | Coverage over the fact graph and task map; dedup |
| Repeatability | Docs change; you start over | Re-run the same generators on new docs; diffs only |
| Eval | No way to know if the data helped | Built-in held-out eval and naive-baseline comparison |
| Formats | Hand-converting to each trainer | Presets and formats |

**The honest core:** Bob's product value is the **verification, coverage and eval loop**, not the generation. If tonight's comparison can't show Bob's data beating naive LLM data, Bob has no reason to exist. That makes the 3-way eval (research 09) the most important thing to build.

## Q2. "Why do I need a fine-tuned model at all? Why not Claude plus my docs (RAG)?"

**For most "know my product docs" use cases, RAG with a good model beats fine-tuning.**

Evidence: Ovadia et al. (EMNLP 2024) found that RAG consistently outperformed unsupervised fine-tuning for injecting knowledge, both for facts seen in training and for new facts. Example reported: Mistral 7B on MMLU Anatomy went 0.556 to 0.570 with fine-tuning, and to 0.681 with RAG. The same paper notes that training on many variations of the same fact helps fine-tuning learn it (relevant to Bob's paraphrase volume, but RAG still wins). The finding is about unsupervised fine-tuning, not supervised instruction data, so it is narrower than "fine-tuning loses", but the direction is clear.

Practitioner consensus: **fine-tune behaviour, retrieve facts.** Fine-tuning pays off for narrow, high-volume, stable tasks where cost, latency, privacy or consistency matter; the common pattern is distillation (a frontier model labels once, a small model serves).

**So our current demo is the weakest use of fine-tuning.** "A small model that memorised the docs" invites "just use RAG". A judge who knows ML will say exactly that.

## What this changes: reposition Bob

Bob makes the data that teaches a **small, cheap model to behave well**, not to memorise.

### Main use case: faithful RAG models (RAFT-style data)
RAFT (Berkeley, 2024) fine-tunes on questions paired with the relevant document **plus distractor documents**, with chain-of-thought answers that cite the right passage. It consistently improved results on PubMed, HotpotQA and Gorilla (one summary cites +30.87% on HotpotQA over domain fine-tuning plus RAG). The model learns to **use** retrieved context and ignore noise.

Bob is unusually well placed to make this data:
- The fact graph knows exactly which chunk supports each answer, so it can pick realistic distractors (same cluster, wrong chunk).
- Abstention rows become "the retrieved docs don't contain this": the model learns to say so instead of guessing.
- False-premise rows teach it to correct the user from the context.
- Citations are verifiable because every answer has a source span.

### Second use case: distil a narrow skill into a small model
Extraction to a schema, ticket classification, support replies in house style, tool-call formatting. These are where small fine-tuned models beat frontier prompting on cost and latency, and where Bob's verifiers (schema checks, constraint checks) are strongest.

## New demo
Same retrieval for every model, 30 human-written questions (8 about features that don't exist):

| Model | Accuracy | Hallucination on fake features | Cost per 1k queries |
|---|---|---|---|
| Small base + RAG | measure | measure | measure |
| Small + naive-LLM-data + RAG | measure | measure | measure |
| **Small + Bob RAFT data + RAG** | measure | measure | measure |
| Opus 5.5 + RAG (ceiling) | measure | measure | measure |

Target story (must be measured, not assumed): *"Bob's data makes a small model as faithful as a frontier model on your docs, for a fraction of the cost per query."* If it doesn't get there, report the real gap; the hallucination column is the most likely win.

## Sources
- Ovadia et al., Fine-Tuning or Retrieval? (EMNLP 2024): https://arxiv.org/html/2312.05934v3, https://aclanthology.org/2024.emnlp-main.15; scope commentary: https://beancount.io/bean-labs/research-logs/2026/05/20/fine-tuning-or-retrieval-knowledge-injection-llms; review: https://liner.com/ja/review/finetuning-or-retrieval-comparing-knowledge-injection-in-llms
- RAFT: https://arxiv.org/pdf/2403.10131, https://sky.cs.berkeley.edu/project/raft/, https://gorilla.cs.berkeley.edu/blogs/9_raft.html, https://nikolettabasiou.substack.com/p/raft-when-rag-meets-supervised-fine
- Fine-tune vs prompt / distillation (practitioner sources, not benchmarks): https://kodekloud.com/blog/fine-tuning-vs-prompting-when-to-use-each/, https://alpeshnakrani.com/books/small-models/fine-tuning-and-distillation/, https://madiator.substack.com/p/finetuning-is-so-back, https://neuraltrust.ai/blog/fine-tuning-vs-prompting-cost
