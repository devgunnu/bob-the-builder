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

## TL;DR
- **Selection:** free heuristics + dedup + embeddings, then Jev (System 1 decision model) asks six questions per chunk for about $0.06 per 1M-token corpus.
- **Writing:** Humpback mode, where the source chunk is the answer and a tiny writer (local vLLM, or Claude Haiku 5.5) writes only the instruction. Templates as a $0 tier. DPO rejected answers via free perturbations.
- **Trust:** Jev verifies every row, cosine groundedness, sampled judge certificate with confidence interval.
- **Output:** one canonical row, projected into ModelForge / OpenAI / Alpaca / ShareGPT / TRL / custom presets, written as JSONL, JSON, CSV, Parquet, Arrow, Avro, or Postgres JSONB `.sql`.
- **Cost:** about $0.40 for 2,500 rows (about $0.15 on our GPU) vs about $35 with Opus 5.5.
- **Standalone:** never imports ModelForge; integrates through files + `bob_manifest.json`.

## Caveats
Research agents could not reach several vendor sites (TypeSafe, OpenRouter, Photon, Firecrawl docs, Hugging Face), so some prices, endpoints and model IDs come from third-party sources. The pre-event checklist in PLAN.md verifies them first.
