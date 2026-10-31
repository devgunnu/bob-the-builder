# Handoff: run Bob end to end on `gunbir/integration`

Paste the prompt at the bottom (backend + frontend combined) into a new Claude Code chat opened on this repo. The rest of this file is the runbook that prompt points to.

## Where things stand (2026-10-31)
- **One branch has everything:** `gunbir/integration` = Aaditya's core (A1 to A4) + infra (A5, `codex/infra-deployment`) + G1/G2 backend + the full frontend (former `claude/bob-web`, design-reviewed) + the integration fixes. Remote branches: `main`, `gunbir/integration`, `codex/infra-deployment`, plus the finished session branch `claude/bold-hopper-tsps3y`.
- **Every route the frontend calls exists** (CONTRACTS §6), and `frontend/src/api/types.ts` matches `backend/bob/core/models.py` field for field (checked by script on 2026-10-31).
- **No login (demo):** the sign-in is gone from the frontend and the backend. Every caller is the built-in user `local`; owner checks stay in code.
- **Built on 2026-10-31:** resync (`POST /jobs/{id}/resync`, "Check the sources again" on Report), the frontend presigned upload for files over 5 MB, and the fixes from a real browser run.
- **Browser run so far** (Playwright, real local stack): Account, Setup (uploads, URL preview, Apps tab), seeds and options all work; `POST /jobs` stops at 412 "connect AWS first", as it should without AWS. Each provider error reaches the UI word for word.
- **Not done yet: one full real job.** The cloud session's proxy denies Jev, ScaleDown, Firecrawl, Composio and Hugging Face, no provider keys are set, and the AWS key in the env is a placeholder. No call was ever stubbed.
- **Tests:** backend 162 passed, 24 failed + 3 errors, all of which need provider keys or blocked hosts. Every G1/G2 test passes except the live `/health` test. Frontend `npx tsc -b && npm run build` passes.
- History: `.agents/WORKLOG_GUNBIR.md` (newest first). Open asks: `.agents/CHANGES_REQUESTED.md`.

## 1. What the run needs

### Keys (`.env` at the repo root, from `.env.example`; never commit it)
| Var | For | Notes |
|---|---|---|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (or a working `AWS_PROFILE`) | Bedrock in local mode (`BOB_BEDROCK_AUTH=default`) | The account needs model access to `global.anthropic.claude-haiku-5-5` and `global.anthropic.claude-sonnet-5-5` in `us-east-1` |
| `JEV_API_KEY` | Jev checks + triage | `JEV_BASE_URL=https://api.typesafe.ai`, `JEV_MODEL=jev-1.14.0` |
| `SCALEDOWN_API_KEY` | Extract, Summarize, Classify, Compress | |
| `FIRECRAWL_API_KEY` | URL sources and preview | Free plan: 10 scrapes/min, 2 crawls/min |
| `COMPOSIO_API_KEY` | Notion | The demo Notion connection already exists for user `bob-local` |

The AWS key in the cloud env must be a real key. The one there on 2026-10-31 is a placeholder: AWS rejects it with `InvalidClientTokenId`.

**Fixed trap:** an empty `AWS_PROFILE=` used to break every local AWS call (`ProfileNotFound`). `.env.example` now comments it out and `config.py` drops an empty value.

### Network (only in a Claude cloud session)
Allow these hosts in the environment's network settings (cloud environment menu in the title bar, then Edit):
- `api.typesafe.ai`
- `api.scaledown.xyz`
- `api.firecrawl.dev`
- `backend.composio.dev`
- `huggingface.co` (model2vec embeddings download on first use)

AWS hosts were already reachable. Put the keys in the environment's secrets (not in chat). A new session picks both up.

## 2. Start it
```bash
cd backend && uv sync --all-extras
```
```bash
cd backend && PATH=$PWD/.venv/bin:$PATH ./run.sh
```
```bash
cd frontend && npm install && npm run dev
```
Open http://localhost:5173 (Vite proxies `/api` to :8000). Quick checks:
```bash
curl -s localhost:5173/api/ping && curl -s localhost:5173/api/health
```
`/health` must show `ok` for all five keys before you go on. It makes paid calls, so don't loop it.

## 3. The end-to-end run (the pass test, PLAN §6 checkpoint 1)
Use the smoke corpus (`demo/smoke/`, 5 pages + `seeds.jsonl`) and keep it small: **Change** → 60 rows, $2 budget.

| # | Do | Pass when | If it breaks, look at |
|---|---|---|---|
| 1 | `/account`: **Check access**, then **Save and check** on models | Both cards say Verified | `orchestrator.verify_bedrock` / `verify_models`; the exact error shows under each role |
| 2 | `/`: type a goal, Enter. Files tab: upload `billing.md`, `rate-limits.md`, `webhooks-overview.md`. Optional: Website tab with `https://docs.firecrawl.dev/rate-limits` and **Preview pages** | Files listed; preview lists pages with char counts | `api/routes.py` uploads, `api/sources.py` preview |
| 3 | Optional: open **Change**, drop `seeds.jsonl` as seeds | "1 seed file" | `orchestrator._seeds` |
| 4 | **Draft the plan** | Reading screen moves through 6 steps with counts | SSE `stage.progress`; `backend/runs/<job>/`; `/tmp` API log |
| 5 | Plan screen: turn one cell off, change one cell's rows, open **Fine-tune**, move a persona slider | Summary line updates rows and cost | `screens/Plan.tsx` |
| 6 | **Start building** | Build screen: heatgrid fills, Kept / Rejected tabs fill, cost counts up | `PUT /jobs/{id}/plan`, `cell.update`, `row` events |
| 7 | Click a kept row and a rejected row | Conversation, cited passages with highlighted facts, checks (failed ones open) | `screens/RowInspector.tsx` `groupSpans`; `Row.spans` from `pipeline/verify.py build_spans` |
| 8 | Click a heatgrid cell | Drawer lists that cell's newest rows | `api.newestRows` |
| 9 | Wait for done, open **Report** | Coverage, Quality, Spot-check (vote on 3 rows), Other formats | `report.ready`, `/spot-check` |
| 10 | **Download dataset**, then export `full` as Parquet and download it | Files download and open | `/export`, `/files/{name}/url` |
| 11 | Optional: one job with a Notion source (Apps tab, pick the 6 wiki pages) | Pages fetched and cited | `connectors/composio.py` |
| 12 | On the done job's Report: **Check the sources again** | Build opens; with no change in the sources the job is back to done at once ("no changes in the sources") | `Orchestrator.resync`, `_resync_body`, `connectors/sync.py` |

After the run, also check: `/jobs` lists the job; a reload of Build and Report replays from SSE; **Cancel** on a second job stops within 5 s.

Screenshot each screen at 1440x900 and 390x844 with Playwright (Chromium is pre-installed) and send them. Keep any scripts outside the repo.

## 4. Things already known
- Rows come from the store oldest first; the UI reads the newest end (`api.newestRows`).
- `Row.spans` mixes whole chunks and extracted facts, both with document offsets. The row screen shows each chunk once and highlights the facts inside it.
- The worker emits `stage.progress` only while reading; during the build it reports per cell (`cell.update`), so still Bob follows job status.
- After `files.ready` the worker sends `job.status done`, then `done {files}`. The client closes the stream on either, but only when `GET /jobs/{id}` says the job is finished now (a re-synced job replays an older `done`).
- `/api/health` is paid: the UI shares one result per 5 minutes, also across reloads.

## 5. Rules
- Real data only: no mocks or fake rows in the repo. If a real call fails, show the provider error.
- One owner per file. Gunbir: `frontend/`, `backend/bob/api/*`, `backend/bob/connectors/*`, `demo/*`. Never edit Aaditya's files (`core`, `pipeline`, `llm`, `clients`, `export`, `orchestrator.py`, `config.py`, `infra/`); ask in `CHANGES_REQUESTED.md`.
- UI stays calm (`UX_NOTES.md`); memes and animation only on the landing page.
- Before every push: `npx tsc -b && npm run build`, plus backend tests for the modules you touched.
- Commit small. No PR unless asked. No em dashes anywhere.

---

## Prompt for the new chat (backend + frontend, one branch)

You are continuing **Bob the Builder**, a synthetic data factory (repo: github.com/devgunnu/bob-the-builder, plan v4.1). A user gives a goal and their docs; Bob plans a coverage map, writes candidate fine-tuning rows with a cheap LLM, checks every row with small decision models (TypeSafe Jev, ScaleDown CDMs) and code, and ships the dataset with proof per row.

I am Gunbir. In this chat you own **all of my parts at once**: G1 (API, auth, uploads, parsers), G2 (connectors: Firecrawl, Composio, demo corpus), G3 and G4 (the frontend). Aaditya owns A1 to A5 (core, pipeline, LLM layer, export, orchestrator, config, deploy). The goal of this chat: **one real job end to end, browser to download, on one branch.**

## Setup
1. Work on branch `gunbir/integration`. It has everything: backend, frontend, infra. Pull it first.
2. Create `.env` at the repo root from `.env.example`. If keys are already in the environment, write them from there; otherwise use the block below. `.env.example` already comments out `AWS_PROFILE`. Confirm `git check-ignore .env` matches. NEVER stage, commit, print or echo a key value.

<<<ENV
(paste the contents of my local .env here, or leave empty if the keys are in the environment's secrets)
ENV>>>

3. Backend: `cd backend && uv sync --extra dev`
4. Frontend: `cd frontend && npm ci`
5. Tests:
   - Backend: `cd backend && set -a && . ../.env && set +a && .venv/bin/python -m pytest -q tests/`. Without provider keys or network, 162 pass; the rest need keys or the allowlisted hosts. All 72 G1/G2 tests (`test_api*.py`, `test_sse.py`, `test_parsers.py`, `test_firecrawl.py`, `test_composio.py`, `test_sync.py`) must pass when the Firecrawl and Composio keys are set.
   - Frontend: `cd frontend && npx tsc -b && npm run build` must pass.
6. If this is a Claude cloud session and a call is denied by the proxy (HTTP 403 on CONNECT), tell me the host. These must be allowed: `api.typesafe.ai`, `api.scaledown.xyz`, `api.firecrawl.dev`, `backend.composio.dev`, `huggingface.co`.

## Read first
- `.agents/HANDOFF_NEXT_CHAT.md`: the runbook. Section 3 is the end-to-end checklist with pass conditions and where to look when a step breaks.
- `.agents/WORKLOG_GUNBIR.md`: status, the API route table, decisions, how to run, and the dated log. This is your main context.
- `.agents/CONTRACTS.md` §6 (HTTP API), §7 (orchestrator and connector interfaces), §8 (SSE events), §10 (re-sync), §12 (real-only rules), §14 (auth and ownership).
- `.agents/CHANGES_REQUESTED.md`: the open requests between owners.
- `.agents/UX_NOTES.md` and `frontend/README.md`.

## State you inherit
- **Backend:** every CONTRACTS §6 route exists (`backend/bob/api/`: `routes.py`, `account.py`, `sources.py`, `health.py`, `sse.py`, `auth.py`), including presigned uploads. Connectors are in `backend/bob/connectors/` (`parsers.py`, `upload.py`, `firecrawl.py`, `composio.py`, `sync.py`). `sync.py` has `refetch`, `refetch_diff`, `diff` and `stale_doc_ids`; `Orchestrator.resync` uses them. There is no sign-in: every caller is the user `local`.
- **Frontend:** `frontend/` (React 18, TS, Vite, Tailwind v4, Amplify v6 lazy-loaded) covers the landing page, Setup, Plan, Build, Row, Report, Account and Jobs. It was design-reviewed at 1440x900 and 390x844. `src/api/types.ts` matches `core/models.py` field for field. The client calls the relative `/api`, and Vite proxies it to :8000.
- **Proven so far:** both halves run together locally. Real calls from the browser work up to `POST /jobs`, which stops at 412 without AWS. **No full job has run yet.**
- **Composio:** the Notion auth config `bob-notion-read` is read-only (5 tools). Bob user `local` maps to Composio user `bob-local`, which has an ACTIVE Notion connection that sees the fictional demo wiki ("Bob Demo – Support Wiki (fictional)", 6 pages).
- **Demo data:** `demo/smoke/` (5 pages + 10 seeds), `demo/corpus/` (25 Firecrawl docs pages), `demo/corpus/notion/` (6 wiki pages).
- **Firecrawl key is on the free plan:** 10 req/min for scrape and map, 2 req/min for crawl, 1,000 credits/month. Keep real calls small.
- **Known behaviors** (don't "fix" these): rows page oldest first, so the UI reads the newest end. `Row.spans` mixes chunks and facts with document offsets. The worker reports build progress per cell. `/api/health` is paid, so the UI checks it every 5 minutes.

## Tasks, in order
1. **Health check.** Start `backend/run.sh` (API on :8000) and `cd frontend && npm run dev` (:5173).
   - `curl -s localhost:5173/api/health` must show `ok` for bedrock, jev, scaledown, firecrawl and composio.
   - If one isn't `ok`, tell me which one and its exact error, then do everything in task 2 that doesn't depend on it.
2. **End-to-end in the browser** (Playwright; Chromium is pre-installed in cloud sessions). Follow the runbook's §3 checklist on the smoke corpus with 20 to 60 rows and a $1 to $2 budget:
   - Account: AWS and models verified.
   - Setup: upload the smoke files, preview a URL, connect and browse Notion and pick the wiki pages.
   - Plan: draft, edit, start.
   - Build: rows stream in, the heatgrid fills, the cell drawer works.
   - Row: a kept row and a rejected row.
   - Report: spot-check 3 rows.
   - Download: the openai-chat JSONL, plus `full` as Parquet.
   - Then: "Check the sources again" on the done job, the job list, a reload replays the stream, and cancel stops a second job within 5 s.
   - **Without AWS credentials**, job creation stops at 412 "connect AWS first". That's expected; finish everything up to that point and report anything else that breaks.
   - Fix every bug in my files, backend or frontend, and re-run the step that broke.
   - For Aaditya's files, add a `CHANGES_REQUESTED.md` row with the exact error and the fix you propose.
3. **Screenshots.** Send me every screen from the real run at 1440x900 and 390x844. Keep the Playwright scripts outside the repo.
4. **If time remains (P1):** Jira and Confluence in `composio.py`, researched with real calls at first use; confirm the ScaleDown extract schema with a real call.

## Rules
- **Real calls only** (CONTRACTS §12): no mocks, no fake responses, no fake rows in the repo. If a real call fails, show the provider's error.
- **Ownership:**
  - You may edit `backend/bob/api/*`, `backend/bob/connectors/*`, `demo/*`, `frontend/*`, and our tests.
  - Never edit Aaditya's files: `core`, `pipeline`, `llm`, `clients`, `export`, `orchestrator.py`, `config.py`, `pyproject.toml`, `infra/`, `.env.example`. Add a `CHANGES_REQUESTED.md` row instead, and ask me first if the change is truly blocking.
- **Security:**
  - Every `/jobs/{id}/*` route returns 404 for another user.
  - Uploads are owner-scoped.
  - Composio calls use `bob-<user id>`.
  - Never return or log an API key.
- **UI:** keep it calm per `UX_NOTES.md`: one primary action per screen, plain language, and errors always visible. Memes and animation stay on the landing page only.
- **Before each commit:**
  - Backend: `cd backend && .venv/bin/ruff check <files>`. Run `ruff format` only on files you changed, never on the whole tree.
  - Run the backend tests for the modules you touched.
  - Frontend: `npx tsc -b && npm run build`.
- **Logging:** after each task, add a dated entry at the top of the Log section in `.agents/WORKLOG_GUNBIR.md`, and update its Status and Next sections. Don't add notes about data retention, TTLs, or stack removal policies anywhere.
- **Git:** commit in small steps on `gunbir/integration` with plain messages. Ask me before pushing or deleting any branch.
- **Talking to me:**
  - Outcome first, short; I'm often on my phone. At most 2 questions at a time. No em dashes. Back decisions with evidence.
  - When done, tell me in plain language: what works end to end, what you changed, test results, and what's blocked on whom.
