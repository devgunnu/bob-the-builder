# Handoff prompt for a new Claude Code chat

Paste everything below the line into a new Claude Code chat opened on the `bob-the-builder` repo.

---

You're continuing work on **Bob the Builder**, our Night Hack project: a synthetic data factory. A user gives a goal and their company's docs. Bob plans a coverage map, writes candidate fine-tuning rows with a cheap LLM, checks every row with small decision models (TypeSafe Jev, ScaleDown CDMs) and code, and ships the dataset with proof for each row. Plan version: **v4.1** (Cognito sign-in, bring-your-own AWS for Bedrock, model-agnostic LLM roles).

I'm Gunbir. I own the frontend and integrations (agents G1 to G4: API, connectors, UI). Aaditya owns the AI and backend logic and deployment (A1 to A5).

## Where things stand
- **`claude/bob-web`**: the full frontend in `frontend/` (React 18, TypeScript, Vite, Tailwind v4, motion, Amplify v6, fetch-event-source).
  - Covers the landing page with the blackout transition, and the Setup, Plan, Build, Row, Report, Account and Jobs screens.
  - Uses the typed API client and the authenticated SSE stream.
  - Codex just finished the backlog there: sprite poses, landing memes, stage-aware still Bob, paged row history, a heatgrid cell drawer, accessibility, route splitting with a virtualized feed, and landing polish (commits `6e3857d` to `e4fd613`).
- **`gunbir/integration`**: the backend in `backend/` (Aaditya's `aaditya/a1-core` merged with my `gunbir/g1-api` and `gunbir/g2-connectors`). It has the FastAPI routes, SSE, uploads, parsers, Firecrawl, Composio (Notion) and the pipeline. `.agents/CHANGES_REQUESTED.md` and `.agents/WORKLOG_GUNBIR.md` there answer the frontend's requests.
- The frontend has never run against the real backend yet. Every screen was checked only with throwaway Playwright fixtures outside the repo.

## Read first
1. `.agents/README.md`, `.agents/PLAN.md`, then `.agents/CONTRACTS.md` sections 1, 2, 6, 8, 12 and 14 (the source of truth).
2. `.agents/AGENT_BRIEFS.md`: the G1 to G4 briefs (ownership and pitfalls).
3. `.agents/UX_NOTES.md` (UI rules), `.agents/WEB_BACKLOG.md`, `frontend/README.md`.
4. On `gunbir/integration`: `.agents/CHANGES_REQUESTED.md`, `.agents/WORKLOG_GUNBIR.md`, `backend/run.sh`.

## What to do, in order
1. **Design review of Codex's work.**
   - Pull `claude/bob-web`, run `cd frontend && npm install && npx tsc -b && npm run build`, and read commits `6e3857d..e4fd613`.
   - Check every screen against `UX_NOTES.md`: calm, one primary action, plain language, no hidden gestures, still Bob inside the app, personality only on the landing page.
   - Screenshot each screen at 1440x900 and 390x844 with Playwright (Chromium is pre-installed; intercept `/api` with fixtures in a script outside the repo, never committed).
   - Fix what's off, then send me the screenshots.
2. **Integrate frontend and backend.**
   - Create an integration branch from `gunbir/integration` and merge `claude/bob-web` into it (or the reverse, whichever is cleaner). Resolve conflicts in the files I own.
   - Reconcile any API or contract mismatches. Use the answered entries in `CHANGES_REQUESTED.md`.
3. **Run it for real, locally.**
   - Start the backend with `backend/run.sh` (auth `none`) and the frontend with `npm run dev` (proxies `/api` to `localhost:8000`).
   - Run one real job on the smoke corpus: upload or URL → plan → edit → build → row → report → download.
   - Fix every break in the files I own. If you need keys, ask me for a local `.env` and never commit it.
   - If a real call fails, show the provider error. Never stub a call.
4. **Then:** the Account screen's connect and verify flow against the real `/me/*` routes, Composio Notion in Setup, and the remaining P1 items in PLAN §8.

## Rules
- **Real data only** (CONTRACTS §0, §12): no mocks, fake rows or placeholder data in the repo.
- **One owner per file.**
  - Mine: `frontend/`, `backend/bob/api/*`, `backend/bob/connectors/*`, `demo/*`.
  - Never edit Aaditya's files (`backend/bob/core`, `pipeline`, `llm`, `clients`, `export`, `orchestrator.py`, `config.py`, `infra/`). Ask through `.agents/CHANGES_REQUESTED.md` and tell me.
- **Keep the UI calm** per `UX_NOTES.md`. Memes and animation stay on the landing page only.
- **Verify before pushing:** `npx tsc -b && npm run build` must pass, and backend tests must pass for the modules you touch.
- **Git:** commit small with clear messages and push to the working branch. Don't open a PR unless I ask.
- **Talking to me:**
  - Lead with the outcome and keep it short; I'm often on my phone.
  - Ask at most 2 questions at a time.
  - Never use em dashes in any text, docs or commit messages.
  - Back decisions with evidence (docs, research, real test results).
