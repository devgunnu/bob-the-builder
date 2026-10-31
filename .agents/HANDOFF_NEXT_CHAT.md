# Handoff: run Bob end to end on `gunbir/integration`

Paste the prompt at the bottom into a new Claude Code chat opened on this repo. The rest of this file is the runbook that prompt points to.

## Where things stand (2026-10-31)
- **One branch has everything:** `gunbir/integration` = Aaditya's core (A1 to A4) + infra (A5, `codex/infra-deployment`) + G1/G2 backend + the full frontend (former `claude/bob-web`, design-reviewed) + the integration fixes. Remote branches: `main`, `gunbir/integration`, `codex/infra-deployment`, plus the finished session branch `claude/bold-hopper-tsps3y`.
- **Every route the frontend calls exists** (CONTRACTS §6), and `frontend/src/api/types.ts` matches `backend/bob/core/models.py` field for field (checked by script on 2026-10-31).
- **Both halves ran together locally** (auth `none`). Real calls from the browser worked: `/me`, the AWS and models save + verify, uploads, `POST /jobs` (stopped by the AWS check, as it should), `/connectors`, `/health`. Each provider error reached the UI word for word.
- **Not done yet: one full real job.** The last cloud session could not reach Jev, ScaleDown, Firecrawl, Composio or Hugging Face (network policy), and had no valid AWS keys. No call was ever stubbed.
- **Tests:** backend 157 passed. The 25 failures + 3 errors all need provider keys or network, except one stale A1 assertion (`test_create_job_429_and_missing_stage_error`, logged). Frontend `npx tsc -b && npm run build` passes.
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
| `BOB_AUTH=none` | Local sign-in off | |

**Known trap:** `.env.example` has an empty `AWS_PROFILE=` line. `uvicorn --env-file` exports it as an empty string and every AWS call fails with `ProfileNotFound: The config profile () could not be found`. Comment it out (`# AWS_PROFILE=`) or set a real profile. Logged for A1.

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

After the run, also check: `/jobs` lists the job; a reload of Build and Report replays from SSE; **Cancel** on a second job stops within 5 s.

Screenshot each screen at 1440x900 and 390x844 with Playwright (Chromium is pre-installed) and send them. Keep any scripts outside the repo.

## 4. Things already known
- Rows come from the store oldest first; the UI reads the newest end (`api.newestRows`).
- `Row.spans` mixes whole chunks and extracted facts, both with document offsets. The row screen shows each chunk once and highlights the facts inside it.
- The worker emits `stage.progress` only while reading; during the build it reports per cell (`cell.update`), so still Bob follows job status.
- After `files.ready` the worker sends `job.status done`, then `done {files}`. The client closes the stream on either.
- `/api/health` is paid: the UI shares one result per 5 minutes.
- `POST /jobs/{id}/resync` returns 501 until A1 wires `connectors/sync.py` (in, tested).
- Presigned uploads for files over 6 MB exist in the API (`POST /uploads/presign`); the UI still sends everything through `POST /uploads`.

## 5. Rules
- Real data only: no mocks or fake rows in the repo. If a real call fails, show the provider error.
- One owner per file. Gunbir: `frontend/`, `backend/bob/api/*`, `backend/bob/connectors/*`, `demo/*`. Never edit Aaditya's files (`core`, `pipeline`, `llm`, `clients`, `export`, `orchestrator.py`, `config.py`, `infra/`); ask in `CHANGES_REQUESTED.md`.
- UI stays calm (`UX_NOTES.md`); memes and animation only on the landing page.
- Before every push: `npx tsc -b && npm run build`, plus backend tests for the modules you touched.
- Commit small. No PR unless asked. No em dashes anywhere.

---

## Prompt for the new chat

You're continuing **Bob the Builder**, our Night Hack synthetic data factory (plan v4.1). I'm Gunbir: frontend and integrations (G1 to G4). Aaditya owns AI, backend logic and deployment (A1 to A5).

Work on branch **`gunbir/integration`**. It has everything: backend, frontend and infra.

Read first:
1. `.agents/HANDOFF_NEXT_CHAT.md`: the runbook.
2. `.agents/WORKLOG_GUNBIR.md`: the newest entries.
3. `.agents/CHANGES_REQUESTED.md`: the open rows.
4. `.agents/CONTRACTS.md` §6, §8 and §14, and `.agents/UX_NOTES.md`.

Then, in order:
1. Check that `/api/health` is `ok` for all five providers. If a host is blocked or a key is missing, tell me exactly which one and stop.
2. Run the end-to-end table in the runbook, §3, on the smoke corpus, in the browser, with real calls. Fix every break in my files. Log asks for Aaditya's files in `CHANGES_REQUESTED.md`.
3. Send me screenshots of every screen from the real run, at 1440x900 and 390x844.
4. Then do the UI for presigned uploads over 6 MB, and Jira / Confluence in Composio (P1).
5. Update `WORKLOG_GUNBIR.md`, then commit and push to `gunbir/integration`.

Talk to me outcome first and keep it short; I'm often on my phone. Ask at most 2 questions at a time. No em dashes. Back every decision with evidence.
