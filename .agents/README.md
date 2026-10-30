# .agents: Bob the Builder knowledge base

Everything a human or an AI agent needs to build Bob at Night Hack (2026-10-30). Read in this order:

1. **[PLAN.md](PLAN.md)**: pitch, architecture, cost model, build schedule, demo script, checklist, risks.
2. **[CONTRACTS.md](CONTRACTS.md)**: data models, stage signatures, Jev questions, writer interface, presets, manifest, API, CLI. Lock before coding.
3. **[DECISIONS.md](DECISIONS.md)**: why each choice was made, fallbacks, open questions.
4. **research/**: the raw reports the plan was compiled from.
   - [01-modelforge-integration.md](research/01-modelforge-integration.md): exact formats, schemas and quirks of ModelForge.
   - [02-jev-cdm-validation.md](research/02-jev-cdm-validation.md): what Jev and Constrained Decision Models are, and where they fit.
   - [03-alternative-approaches.md](research/03-alternative-approaches.md): cheap selection, generation, QC, prior art, cost math.
   - [04-hackathon-stack-and-build-plan.md](research/04-hackathon-stack-and-build-plan.md): partner integrations, format libraries, stack, timeline, demo.
   - [05-cdm-recheck-and-llm-free-generation.md](research/05-cdm-recheck-and-llm-free-generation.md): **corrects 02.** CDM = ScaleDown Constrained Decoding Models; the zero-LLM generation engine.
   - [06-true-synthetic-generation.md](research/06-true-synthetic-generation.md): **proposal.** New data = new inputs x a trustworthy oracle (the real product, a docs-compiled simulator, solvers). Superseded by 07.
   - [07-dataset-generators.md](research/07-dataset-generators.md): **proposal.** Eleven zero-LLM generators that synthesize fine-tuning rows for any corpus (task multiplier, corrupt-and-restore, verifiable constraints, conversations, abstention, preference pairs, few-shot expander, ...).
   - [08-worked-example.md](research/08-worked-example.md): one real 60-word passage becomes about 570 rows, with exact counts, sample rows and evidence per technique.

## TL;DR (v2.1: strictly zero-LLM, demo on a real product)
- **Read:** free filters, then Jev triages chunks and ScaleDown Extract pulls typed facts with verbatim source spans into a fact graph.
- **Generate, with zero LLM tokens:** question programs compose new examples over the graph (multi-hop, comparisons, arithmetic, aggregation, procedures, true/false, multi-turn, reasoning traces). Answers are computed or copied, so they are correct by construction.
- **Speak:** a grammar bank overgenerates phrasings, Jev picks the most natural; ScaleDown Summarize writes topic explanations and summaries.
- **Trust:** span checks, corroboration, Jev verification, certificate with confidence interval; free hard DPO negatives from perturbed facts.
- **Output:** ModelForge / OpenAI / Alpaca / ShareGPT / TRL / CoT / RLVR / custom presets in JSONL, JSON, CSV, Parquet, Arrow, Avro, Postgres JSONB `.sql`.
- **Cost:** about $0.43 for 5,000 rows (about $0 on starter tokens) vs about $70 with Opus 5.5.
- **Demo:** Bob compiles a real product's docs into a dataset, ModelForge fine-tunes a small model on it live, and the tuned model answers product questions the base model gets wrong.
- **Standalone:** never imports ModelForge; integrates through files + `bob_manifest.json`.

## Caveats
Research agents could not reach several vendor sites (TypeSafe, OpenRouter, Photon, Firecrawl docs, Hugging Face), so some prices, endpoints and model IDs come from third-party sources. The pre-event checklist in PLAN.md verifies them first.
