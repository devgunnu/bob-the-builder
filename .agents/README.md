# .agents: Bob the Builder knowledge base

Everything a human or an AI agent needs to build Bob at Night Hack (2026-10-30). Current version: **v4.1, the data factory** (v4 + review fixes + bring-your-own AWS for Bedrock + Cognito auth). Read in this order:

1. **[PLAN.md](PLAN.md)**: pitch, user flow, architecture, Jev and CDM roles, team and agents, 4-hour timeline, definition of done, cut lines, demo, cost, risks, configuration, research during the build.
2. **[CONTRACTS.md](CONTRACTS.md)**: source of truth for code. File ownership, core models, stage signatures, verification cascade, Jev and ScaleDown clients, HTTP API, orchestrator, SSE events, config, re-sync, export, real-only rules, and §14 (v4.1: BYO AWS Bedrock, Cognito auth, users). Lock before coding.
3. **[AGENT_BRIEFS.md](AGENT_BRIEFS.md)**: the prompt for each coding agent (A1 to A5, G1 to G4).
4. **[DECISIONS.md](DECISIONS.md)**: why each choice was made. v4 decisions are D18 to D25. v4.1 decisions are D26 to D33 (D26 BYO AWS Bedrock, D27 Cognito + IAM auth, D28 to D31 review fixes, D32 research as we go, D33 model-agnostic LLM layer).
   - **[WEB_BACKLOG.md](WEB_BACKLOG.md)** and **[UX_NOTES.md](UX_NOTES.md)**: frontend art and animation backlog (for Codex), and the rules that keep the UI calm.
   - **[CODEX_PROMPT.md](CODEX_PROMPT.md)**: the paste-ready prompt for Codex on the frontend.
5. **[research/11-data-factory.md](research/11-data-factory.md)**: the v4 ideation record. Why templates were dropped, the mechanisms we considered, the user flow, the Jev / CDM roles and the cascade.

Build state (read these to see what exists, not what is planned):
- **Working branch: `gunbir/integration`.** It holds all merged work (A1 to A5, G1 to G4). Remote branches: `main`, `gunbir/integration`, `codex/infra-deployment` (the CodeBuild deploy branch).
- **[WORKLOG_GUNBIR.md](WORKLOG_GUNBIR.md)**: G1 (API, auth, uploads, parsers) and G2 (Firecrawl, Composio, demo corpus): status, the full API route list, decisions, how to run, and a dated log.
- **[CHANGES_REQUESTED.md](CHANGES_REQUESTED.md)**: open and done requests between owners.
- **[quality/](quality/)**: acceptance checks, evaluation set and workstream tracker.

## TL;DR (v4.1)
- **What Bob is:** a synthetic data factory. Goal + company material in, verified fine-tuning data out. Every row ships with its proof.
- **Pitch:** "The LLM writes, and small decision models check every row. The strong model only looks at the rows where the checks disagree."
- **Sources:** website URLs (Firecrawl), Notion / Confluence / Jira / Google Drive (Composio), file uploads, optional seed examples.
- **Read:** chunk, free filters, dedup, Jev triage, topics with ScaleDown Summarize briefs, ScaleDown Extract evidence index with verbatim spans.
- **Plan:** the Planner model (default Sonnet 5.5) proposes a coverage map. Cells are topic x case type (answerable, partial, unanswerable, false premise). Persona and difficulty are mix axes inside each cell, with editable weights (D29). Demo: 12 topics x 4 case types = 48 cells. The user edits the map and clicks Start.
- **Generate:** the Writer model (default Haiku 5.5) makes candidates per cell, 5 per call, with prompt caching.
- **Verify:** tier 1 code, tier 2 Jev + Extract invented-feature check with calibrated routing, tier 3 judge model (default Sonnet 5.5) on about 5% uncertain rows + a 2% audit. Correct "not in docs" and false-premise rows pass: the absent topic is exempt, and numbers from the user turn are allowed (D28).
- **Fill gaps:** rounds 2 and 3 target empty cells and cells with high rejection rates. Base-model probing is a stretch.
- **Ship:** a data quality report, DPO pairs (the Writer synthesizes a flawed twin of a kept row; the pair is kept only when a check rejects the twin, D30), presets (OpenAI chat, ShareGPT, Alpaca, ModelForge, DPO, full) in JSONL / JSON / CSV / Parquet, plus manifest and provenance.
- **No training:** Bob makes data only (D20). **No mocks:** every call is real; only a cache of real responses (D23).
- **Stack:** FastAPI + SSE, React + TypeScript; LLM calls go through a model-agnostic layer (Bedrock Converse API). Convex and Photon are dropped (D24).
- **Models:** any Bedrock model, defaults Claude Haiku 5.5 / Sonnet 5.5; OpenAI-compatible endpoints P1 (D33).
- **Accounts (D27):** users sign in with a Cognito user pool (invite only). The API checks the JWT. Each user sees only their own jobs.
- **BYO AWS Bedrock (D26):** each user deploys the `BobBedrockAccess` role in their own AWS account from a template, then verifies it on the Account screen. Bob assumes the role with an external id, so Bedrock runs and bills in the user's account. Bob still pays for Jev, ScaleDown, Firecrawl and Composio.
- **Configurable:** env vars give defaults (`CELL_AXES`, `CASE_MIX`, `KEEP_P`, `DPO_MODE`, and more); `JobOptions` overrides them per job (PLAN §12, CONTRACTS §9).
- **No hang (D31):** the worker writes a heartbeat; a watchdog ends a job with a dead worker in `error`; full capacity returns HTTP 429.
- **Deploy:** AWS serverless (D25, CONTRACTS §13): CloudFront + S3 for the UI, Lambda for the API and SSE, one Fargate worker per job, DynamoDB + S3 for state, CDK in `infra/`. Local mode stays the default for development.
- **Team:** Aaditya owns AI, backend logic and deployment (A1 to A5); Gunbir owns frontend and integrations (G1 to G4). Estimate: about $1.85 per 1,000 kept rows (most of it Bedrock, billed to the user's AWS account) vs about $20 frontier-only.

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
Research agents could not reach several vendor sites (TypeSafe, OpenRouter, Firecrawl docs, Hugging Face), so some prices, endpoints and model IDs come from third-party sources. Each owner agent verifies them with a real call at first use (PLAN.md section 13, D32).
