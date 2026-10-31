# .agents: Bob the Builder knowledge base

Everything a human or an AI agent needs to build Bob at Night Hack (2026-10-30). Current version: **v4, the data factory**. Read in this order:

1. **[PLAN.md](PLAN.md)**: pitch, user flow, architecture, Jev and CDM roles, team and agents, 4-hour timeline, definition of done, cut lines, demo, cost, risks.
2. **[CONTRACTS.md](CONTRACTS.md)**: source of truth for code. File ownership, core models, stage signatures, verification cascade, Jev and ScaleDown clients, HTTP API, orchestrator, SSE events, config, re-sync, export, real-only rules. Lock before coding.
3. **[AGENT_BRIEFS.md](AGENT_BRIEFS.md)**: the prompt for each coding agent (A1 to A4, G1 to G4).
4. **[DECISIONS.md](DECISIONS.md)**: why each choice was made. v4 decisions are D18 to D24. Open questions are at the end.
5. **[WEB_BACKLOG.md](WEB_BACKLOG.md)**: open art, meme and animation tasks for the frontend (for Codex).
6. **[research/11-data-factory.md](research/11-data-factory.md)**: the v4 ideation record. Why templates were dropped, the mechanisms we considered, the user flow, the Jev / CDM roles and the cascade.

## TL;DR (v4)
- **What Bob is:** a synthetic data factory. Goal + company material in, verified fine-tuning data out. Every row ships with its proof.
- **Pitch:** "The LLM writes, and small decision models check every row. The frontier model only looks at the rows where the checks disagree."
- **Sources:** website URLs (Firecrawl), Notion / Confluence / Jira / Google Drive (Composio), file uploads, optional seed examples.
- **Read:** chunk, free filters, dedup, Jev triage, topics with ScaleDown Summarize briefs, ScaleDown Extract evidence index with verbatim spans.
- **Plan:** the Planner (Sonnet 5.5) proposes a coverage map: topic x persona x case type (answerable, partial, unanswerable, false premise) x difficulty. The user edits it and clicks Start.
- **Generate:** the Writer (Haiku 5.5) makes candidates per cell, 5 per call, with prompt caching.
- **Verify:** tier 1 code, tier 2 Jev + Extract invented-feature check with calibrated routing, tier 3 Sonnet judge on about 5% uncertain rows + a 2% audit.
- **Fill gaps:** rounds 2 and 3 target empty cells and cells with high rejection rates. Base-model probing is a stretch.
- **Ship:** a data quality report, DPO pairs from rejected vs kept replies, presets (OpenAI chat, ShareGPT, Alpaca, ModelForge, DPO, full) in JSONL / JSON / CSV / Parquet, plus manifest and provenance.
- **No training:** Bob makes data only (D20). **No mocks:** every call is real; only a cache of real responses (D23).
- **Stack:** FastAPI + SSE, React + TypeScript; all LLMs are Anthropic on AWS Bedrock. Convex and Photon are dropped (D24).
- **Team:** Aaditya owns AI and backend logic (A1 to A4); Gunbir owns frontend and integrations (G1 to G4). Estimate: about $1.70 per 1,000 kept rows vs about $20 frontier-only.

## History (older material, read for context only)
v4 retires templates, question programs, grammar banks, the generator library and Architect-written generator code (D18). The files below are kept as a record. Where they conflict with PLAN.md or CONTRACTS.md, PLAN.md and CONTRACTS.md win.

- [ASSESSMENT.md](ASSESSMENT.md): **pre-v4.** Honest verdict on the v2/v3 plan. Its advice on visible proof, correctness over cost, a sponsor corpus and scope still applies; its fine-tune and eval advice does not (D20).
- [research/01-modelforge-integration.md](research/01-modelforge-integration.md): ModelForge formats and quirks. Still valid for the `modelforge-*` export presets.
- [research/02-jev-cdm-validation.md](research/02-jev-cdm-validation.md): Jev sections still valid. **CDM sections superseded** (wrong term; see 05).
- [research/03-alternative-approaches.md](research/03-alternative-approaches.md): cheap selection, generation, QC, prior art, cost math. Background.
- [research/04-hackathon-stack-and-build-plan.md](research/04-hackathon-stack-and-build-plan.md): partner integrations and stack. **Partly superseded:** Convex and Photon are dropped, and the timeline is replaced by PLAN.md.
- [research/05-cdm-recheck-and-llm-free-generation.md](research/05-cdm-recheck-and-llm-free-generation.md): the correct CDM facts (ScaleDown Constrained Decoding Models) are still valid. **The zero-LLM generation engine is superseded.**
- [research/06-true-synthetic-generation.md](research/06-true-synthetic-generation.md): **superseded** (by 07, then by v4).
- [research/07-dataset-generators.md](research/07-dataset-generators.md): **superseded.** Zero-LLM generator library.
- [research/08-worked-example.md](research/08-worked-example.md): **superseded.** Worked example for the generator library.
- [research/09-llm-architect-design.md](research/09-llm-architect-design.md): **sections 1 to 4 superseded** (Architect-written generator code). The verification ideas and evidence are kept in v4; the eval plan is dropped (D20).
- [research/10-why-product-why-model.md](research/10-why-product-why-model.md): still valid for the "why a product" argument and the faithfulness / abstention focus. Its model-eval demo is dropped (D20).

## Caveats
Research agents could not reach several vendor sites (TypeSafe, OpenRouter, Firecrawl docs, Hugging Face), so some prices, endpoints and model IDs come from third-party sources. The pre-start checklist in PLAN.md section 6 verifies them with real calls first.
