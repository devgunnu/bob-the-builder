# Gunbir work log (G1 API + Files, G2 Connectors)

Running log of Gunbir's backend work. Newest entries at the top of the log.
**Working branch: `gunbir/integration`.** It holds everything: `main`, all of Aaditya's work (former `aaditya/a1-core`, `a2-read`, `a3-plan-write`, `a4-verify-ship`, plus `codex/infra-deployment`), the frontend (former `claude/bob-web`) and ours (former `gunbir/g1-api`, `gunbir/g2-connectors`). Merged branches were deleted on GitHub after checking each was fully contained. Remote branches left: `main`, `gunbir/integration`, `codex/infra-deployment` (kept because Aaditya's CodeBuild deploys from it).
Frontend (G3, G4) lives in `frontend/` on this branch. Runbook for the first full job: `.agents/HANDOFF_NEXT_CHAT.md`.
Source of truth stays `PLAN.md` and `CONTRACTS.md` (v4.1); this file records what is built, what is decided, and what is waiting on whom.

## Status

| Part | Owner | State |
|---|---|---|
| 1. Smoke corpus (`demo/smoke/`: 5 pages + 10 seed Q&As) | G2 | Done |
| 2. API slice 1 (parsers, uploads, who is calling, SSE, thin-path routes) | G1 | Done; runs on A1's real core; no sign-in now (every caller is `local`) |
| 3. Firecrawl + Composio (Notion) connectors | G2 | Done; real crawl, real Notion browse + fetch |
| 3b. Demo docs corpus (`demo/corpus/`, 25 pages) | G2 | Done |
| 3c. Demo Notion wiki (6 fictional pages, in Notion + `demo/corpus/notion/`) | G2 | Done |
| 4a. `/api/health` + container boot fix (`python-multipart`) | G1 | Done; container-style boot verified |
| 4. API slice 2: every route in CONTRACTS §6, including `/uploads/presign` (P1) | G1 | Done; resync works (no 501) |
| 4b. Cloud fix: `bob/aws/blobs.py` import crash; SigV4 presigned uploads | G1 (in A5 files, with Gunbir's OK) | Done |
| 5. `connectors/sync.py` (P1, for resync) | G2 | Done (`refetch`, `refetch_diff`); orchestrator resync built by us 2026-10-31 |
| 5b. Jira / Confluence / Drive (P1) | G2 | Next |
| 6. Frontend wired to the real API | G1 + G3/G4 | Done: design review, contract fixes, both halves run together locally (2026-10-31 entry) |
| 7. Full real job (needs AWS credentials + Jev / ScaleDown / Firecrawl / Composio keys and network) | all | Blocked: the cloud proxy denies the provider hosts and the AWS key in the env is a placeholder. Runbook in `HANDOFF_NEXT_CHAT.md` |
| 8. Login removed for the demo | G1 + G3 | Done (frontend by RETR0-OS `9ab76c0`, backend + docs by us `41c8f20`) |
| 9. Frontend presigned upload for files over 5 MB | G3 | Done (`cd2b336`, checked in the browser with an 8 MB file) |
| 10. Resync in the orchestrator + "Check the sources again" on Report | G2 (A1 files, with Gunbir's OK) | Done (`aed40d7`, `aae59be`) |

Tests (2026-10-31): backend 162 passed, 24 failed + 3 errors, all of which need provider keys or hosts the cloud proxy denies. Every G1/G2 test passes except the live `/health` test. Frontend `npx tsc -b && npm run build` passes.

## Waiting on

| From | What | Logged in |
|---|---|---|
| Gunbir (environment settings) | Provider keys (`JEV_API_KEY`, `SCALEDOWN_API_KEY`, `FIRECRAWL_API_KEY`, `COMPOSIO_API_KEY`), real AWS credentials, and the network allowlist: `api.typesafe.ai`, `api.scaledown.xyz`, `api.firecrawl.dev`, `backend.composio.dev`, `huggingface.co` | |
| A2 / A4 | Confirm the ScaleDown extract schema form (needs a real ScaleDown call) | `CHANGES_REQUESTED.md` |
| A5 | Point CodeBuild at `gunbir/integration` (or `main` after merging it), if still relevant | |

Everything else in `CHANGES_REQUESTED.md` is done (see that file).

## API routes (G1, all under `/api`)

| Route | Notes |
|---|---|
| `GET /ping` | Lambda readiness check. No sign-in anywhere: every caller is the built-in user `local` |
| `GET /health` | One cheap real call per provider in parallel (15 s each); no fallbacks, no cache; keys redacted |
| `GET /me`; `GET /me/aws/setup`, `GET /me/aws/template`, `PUT /me/aws`, `POST /me/aws/verify` | AWS connect flow (A1 `update_bedrock` / `verify_bedrock`) |
| `PUT /me/models`, `POST /me/models/verify`, `GET /me/models/available` | Models per role (`api_keys` answer 501 until A1's P1 keys land); `available` lists Bedrock models + inference profiles through the caller's role (20 s cap) |
| `POST /uploads` (6 MB), `POST /uploads/presign` (200 MB), `PUT /uploads/{id}/content` (local mode only) | Owner-scoped uploads; presign gives an S3 PUT in aws mode. The frontend uses presign for files over 5 MB; the local PUT needs no auth header |
| `GET /connectors`, `POST /connectors/{toolkit}/connect`, `GET .../status`, `GET .../browse` | Composio, per user (`bob-<id>`); redirect must be this app's origin |
| `POST /sources/preview` | No job; 10 pages or 20 s, `capped` flag |
| `POST /jobs` (412 / 429 from A1), `GET /jobs`, `GET /jobs/{id}`, `PUT /jobs/{id}/plan` (409 unless awaiting approval), `POST /jobs/{id}/cancel` | Every `/jobs/{id}/*` route 404s for another user's job |
| `GET /jobs/{id}/events` | SSE: `retry: 1000`, `: ping` every 15 s, replay from `Last-Event-ID`, closes after 840 s |
| `GET /jobs/{id}/rows`, `GET /jobs/{id}/rows/{row_id}`, `POST /jobs/{id}/rows/{row_id}/spot-check` | Spot-check 409 while a worker runs (A1) |
| `GET /presets`, `POST /jobs/{id}/export`, `GET /jobs/{id}/files/{name:path}` + `/url` | Preset and format validated against A4; downloads only for names in `Job.files` |
| `POST /jobs/{id}/resync` | Works on a done job with a plan, 409 otherwise (429 at capacity). UI: "Check the sources again" on Report |

Errors everywhere: `{error, provider?, detail?}`; validation 422 `{error: "invalid request", detail}`; crashes 500 `{error: "internal error", detail}`.

## Decisions made (G1 / G2 scope)

| Decision | Why |
|---|---|
| Smoke corpus = 5 support-style pages: `/billing`, `/rate-limits`, `/webhooks/overview`, `/webhooks/security`, `/features/key-restrictions` | Short pages full of real limits, settings and numbers, which the false-premise and `numbers` checks need. Feature pages were 50k to 300k chars each. |
| `clean_markdown()` (in `connectors/firecrawl.py`) strips docs-site chrome from Firecrawl output | Mintlify pages carry a ~100k-char JSON config blob, a chat-widget greeting, "Suggest edits" footers and heading anchor links after `only_main_content`. `/billing` went from 130k to 24k chars with no content lost. |
| Firecrawl calls retry on rate limits (wait 15 s, 5 tries) | Our key is on the free plan: 10 req/min on scrape/map, 2 req/min on crawl, 1,000 credits/month. |
| Firecrawl crawl excludes `*.md` paths, skips pages under 200 chars or HTTP >= 400, cancels the crawl on timeout or task cancel | Docs sites publish `.md` duplicates; no paying for pages nobody reads. |
| Demo corpus = curated list of 27 support paths checked against the real site map, first 25 under 60k chars | A blind crawl from the docs root returned quickstarts, use cases and API-reference stubs; a Firecrawl `prompt` crawl was too narrow (6 pages). The crawl connector keeps an optional `prompt`. |
| All A1 touch points in one G1 file, `api/deps.py` | Written before A1 existed; when A1 landed only `deps.py`, `sse.event_parts` and the error mapping changed. |
| `sse.py` and `parsers.py` import nothing from A1 at load time | Testable on their own. |
| `POST /jobs`: 412 / 429 come from A1 (`PreconditionFailed`, `RunnerBusy`), mapped app-wide with `JobRunning` (409) | One source of truth: the orchestrator decides. |
| `PUT /jobs/{id}/plan` returns 409 unless the job is `awaiting_approval` | Not in the contract; prevents approving twice or on a finished job. |
| Uploads are owner-scoped: `.owner` marker; `POST /jobs` and preview 404 for another user's upload or seed id; the upload connector re-checks in the worker | Acceptance criterion (quality/acceptance.md). |
| Upload URI = `upload://<upload_id>/<name>`; upload ids must be 32 hex chars; `.json` / `.jsonl` accepted only as seed files | Unique document ids; no key escapes `runs/uploads/`; seeds are not docs. |
| Parsers: CSV is a table up to 30 x 8, else one `##` section per row; HTML drops script/style/nav/footer/button/form/svg and empty links, prefers `<main>` / `<article>` | The chunker never splits a table; the live docs HTML went from 257 KB to 3 KB. |
| Presigned uploads: SigV4 client signs `content-length;content-type;host`, 15 min; local mode returns this API's `PUT /uploads/{id}/content` | boto3's default SigV2 presign did not sign the size, so S3 would accept any size. Local mode has no 6 MB limit, so the frontend flow is the same in both modes. |
| `/health` calls providers directly (Jev without its fallback chain, unique inputs so the cache never answers) | "ok" must mean that provider answered now. |
| OAuth `redirect_url` must be a dev origin or `BOB_PUBLIC_URL` | No open redirect through Composio. |
| Downloads only for names in `Job.files`, plus a path check; aws: 302 to a presigned GET | No path traversal; the frontend uses the `/url` route because a link cannot send the auth header. |
| `/sources/preview` for URLs: Firecrawl map, then scrape up to 10 pages (5 in parallel) within the 20 s budget | A crawl is too slow to show anything in 20 s. |
| Composio Notion auth config `bob-notion-read` (`ac_ELz4KgTaZsVZ`) is managed OAuth restricted to 5 read-only tools | Bob only reads; a bug cannot edit or delete a user's pages. |
| Notion: browse `NOTION_SEARCH_NOTION_PAGE`, fetch `NOTION_GET_PAGE_MARKDOWN`, both pinned to `20261018_00`; connections via `connected_accounts.link` | Markdown in one call; pinned shape; Composio retired `initiate` for managed OAuth. |
| `notion_to_markdown()` strips Notion markup and turns `<table>` blocks into markdown tables, outside code fences | Found on real fetches: tags polluted chunks, and flattened tables lost which value belongs to which row. |
| Every Composio call checks the connection's `user_id` is `bob-<caller id>`, else 404 | Per-user privacy (CONTRACTS §14). |
| Demo Notion wiki is fictional, under "Bob Demo – Support Wiki (fictional)"; facts shared with the public docs match them exactly. `seed_notion.py --create-parent-under` creates the parent when none is shared (Composio cannot create root-level pages); the create tool is enabled only during the run | Internal-only facts and real "not in docs" gaps, without passing as Firecrawl's real policy. |
| `build_corpus.py` caches only the demo wiki titles from Notion | A first run cached a personal page; it was deleted before any commit. |
| Ruff: lint with the project config in `backend/pyproject.toml`; format only our own files | A repo-wide format once rewrote an A3 file; that change was reverted. |
| Branch cleanup: delete a branch only after checking it is fully contained in the pushed `gunbir/integration`; keep a branch a deploy pipeline uses | No lost work; no broken deploy. |
| Deployment: S3 + CloudFront for the UI (not Amplify Hosting) | Matches v4.1 (D25). `aws-amplify` is only the Cognito sign-in library in the frontend. |

## How to run

```bash
cd backend && uv sync --extra dev
```

```bash
cd backend && ./run.sh   # API on :8000 (local mode, no sign-in); the Vite dev server proxies /api
```

```bash
cd backend && set -a && . ../.env && set +a && .venv/bin/python -m pytest -q tests/
```

```bash
backend/.venv/bin/python demo/build_corpus.py               # rebuild demo/corpus/ (Firecrawl, ~25 credits)
backend/.venv/bin/python demo/build_corpus.py --notion-only # re-cache the Notion wiki
backend/.venv/bin/python demo/seed_notion.py                # re-seed the Notion wiki (skips existing pages)
```

Keys in `.env` (never committed): `FIRECRAWL_API_KEY`, `COMPOSIO_API_KEY`, `COMPOSIO_USER_PREFIX=bob-`; a full job also needs AWS credentials, `JEV_API_KEY`, `SCALEDOWN_API_KEY`.

## Log

### 2026-10-31: sync refetch, browser run fixes, login removed, resync built (`gunbir/integration`)
- `9ee77eb`: `sync.refetch(job)` re-fetches each source as the job owner, `sync.refetch_diff(job, old_docs)` returns the new docs, the diff and the stale doc ids. Tests: an offline upload refetch (no change, owner-scoped) plus real Notion and Firecrawl refetch tests that skip without keys.
- Browser run (Playwright on the real local stack, scripts outside the repo): it reached `POST /jobs` -> 412 "connect AWS first", as expected. All five `/health` providers fail with exact errors (bedrock `NoCredentialsError`; jev, scaledown, firecrawl, composio "key not set") because the cloud env has no keys and the proxy denies the hosts. Test jobs had leaked into `backend/runs` before the conftest fix.
- `9f43abf`, fixes from that run: missing Composio or Firecrawl keys answer 503 "not configured on this server" (was 400 and 502); Plan, Build and Report show only the error and a link to the jobs when a job can't load; the stream stops retrying on 4xx; the preview error stays in the Website tab; the job error sits next to Draft the plan with plain titles; the paid `/health` result survives reloads for 5 minutes (sessionStorage); the phone header chip reads "N down".
- `cd2b336`: files over 5 MB upload through `POST /uploads/presign` and a direct PUT; smaller files go in multipart batches under 6 MB.
- `41c8f20`: login removed on the backend too (Cognito check, `/config/public`, `BOB_AUTH`, `BOB_COGNITO_*`, `BOB_SIGNUP`, pyjwt); `config.py` drops an empty `AWS_PROFILE`; `.env.example` sources cleanly; data bucket CORS PUT for presigned uploads (`cdk synth` checked).
- `aed40d7`: orchestrator resync (re-fetch, re-read, re-verify kept rows citing changed or removed docs, stale ones rejected, one gap round with reason "resync", report and export); `verify.py` uses `ctx.verify_state`; `_seeds` reads as the owner; conftest always uses a temp runs dir; the stale 429 test fixed; offline resync tests.
- `aae59be`: "Check the sources again" link on Report; the stream closes only when the job is finished now; a re-checked row replaces its old feed entry.

### 2026-10-31: design review, frontend fixes against the real backend, sync.py (merged from `claude/bold-hopper-tsps3y`)
- **Design review of Codex's work** (`6e3857d..e4fd613`) against UX_NOTES at 1440x900 and 390x844, with throwaway Playwright fixtures outside the repo. Fixed: wordmark overlapped the step tracker on phones; Report hero collapsed into a one-word column on phones; Plan's Start button is a sticky bottom bar on phones; Setup had two submit buttons; jargon (Jev triage, raw check names, case-type ids, job status ids); the Row screen always showed Build as the current step; heatgrid clipped its headers on phones; Amplify UI (520 KB) loaded even with auth `none` (now a lazy chunk, `auth/CognitoGate.tsx`).
- **Frontend vs the real backend:** new model fields in `types.ts`; the final `done` event; rows page oldest first, so "Load older rows" and the cell drawer now read from the newest end (`api.newestRows`); source passages show once with the extracted facts highlighted inside them (spans carry document offsets; the old slice landed mid-word); still Bob follows job status (the worker reports per cell, not per stage); local-mode Account (default AWS chain, no role to deploy); missing `BOB_ACCOUNT_ID` shows a clear note; plain 409 messages; Report labels check names.
- **Cost fix:** every screen called `/api/health` (one paid call per provider) on mount and every 60 s. Now one shared result, at most every 5 minutes, only while visible; the red chip opens the exact errors on tap.
- **P1:** `connectors/sync.py` (`diff`, `stale_doc_ids`, 3 tests on smoke docs); self sign-up switch (`signup` in `/config/public`, sign-up tab only when open); Bedrock model picker in the Models panel (suggestions from `/me/models/available`).
- **Merge note:** that branch had its own API slice 2 written in parallel (`api/me.py`, `api/results.py`). This branch's version (`account.py`, `sources.py`, `routes.py`) was kept; the duplicates were dropped, and the frontend was adapted to its response shapes.
- **First local run of both halves together** (`backend/run.sh` + `npm run dev`, auth `none`): `/me`, `/me/aws/setup`, `PUT /me/aws`, `/me/aws/verify`, `PUT /me/models`, `/me/models/verify`, `/uploads` (3 smoke files), `POST /jobs` (412 with the real reason), `/connectors`, `/health` all answered from the real code, and each provider error reached the UI word for word. Found: the empty `AWS_PROFILE=` in `.env.example` breaks boto3 locally (logged for A1). The run stopped there: the cloud session's network policy denied `api.typesafe.ai`, `api.scaledown.xyz`, `api.firecrawl.dev`, `backend.composio.dev`, `huggingface.co`, and its AWS keys were invalid. No call was stubbed.

### 2026-10-31: docs brought up to date (`gunbir/integration`)
- Rewrote the top of this log: current status, waiting-on, a full API route table, decisions (stale rows replaced), how to run with A1's `pyproject.toml`.
- `.agents/README.md`: "Build state" section (working branch, this log, change requests, quality folder).
- `quality/workstreams.md`: G1 and G2 rows record verified state and evidence; other owners' rows untouched.
- `CHANGES_REQUESTED.md`: the frontend's OAuth and `/url` / template requests marked done.

### 2026-10-31: branch cleanup, presigned uploads, S3 import fix (`gunbir/integration`, `0d5eeb9`)
- Merged 2 new `codex/infra-deployment` commits (CodeBuild credential reuse, manual starts); pushed `gunbir/integration`; deleted `aaditya/a1-core`, `a2-read`, `a3-plan-write`, `a4-verify-ship` and `claude/bob-web` on GitHub after checking each is fully contained. Kept `codex/infra-deployment` (Aaditya's CodeBuild deploys from it).
- `Blobs.put_url(key, content_type, content_length, expires_s=900)` in `core/blobs.py` (local: None) and `aws/blobs.py`. boto3 had presigned the PUT with SigV2, which does not sign Content-Length (any size accepted); the upload URL now comes from a SigV4 client and signs `content-length;content-type;host`.
- **Cloud bug found and fixed:** `bob/aws/blobs.py` failed at import (`list` method shadowing `list[str]` annotations), so uploads, the cache, exports and the worker would crash in aws mode while `/api/ping` still passed. One-line fix; all `bob.aws.*` modules import.
- `POST /uploads/presign` (200 MB cap, type check, owner + `.presign` markers) and `PUT /uploads/{id}/content` (local mode: size must match; 409 in aws mode, where the browser uploads to S3). `read_upload` hides both marker files.
- Tests: local presign end to end, bad type 400, too big 413, size mismatch 400, other user 404, S3 URL signs size + type. Full suite: 164 passed (rest: missing AWS / Jev / ScaleDown keys + A1's stale test). Fresh-install boot: `/api/ping` 200.
- Asked A5 (table): data bucket CORS must allow browser `PUT` from `BOB_PUBLIC_URL`.

### 2026-10-31: branches combined and cleaned, API slice 2 (`gunbir/integration`)
- Merged `claude/bob-web` (sprites, row drawer, paged history, accessibility) and `codex/infra-deployment` (CloudShell deploy prep) cleanly. Combined test pass: backend 144 then 161 passed (all G1/G2 pass; the rest need AWS / Jev / ScaleDown keys, plus A1's one stale test); frontend `tsc -b && vite build` passes.
- Deleted `gunbir/g1-api` and `gunbir/g2-connectors` locally and on GitHub after checking both are fully contained in `gunbir/integration`. Aaditya's branches, `claude/bob-web` and `codex/infra-deployment` are also fully contained; left for their owners to delete.
- API slice 2 (`api/account.py`, `api/sources.py`, `api/routes.py`): `/me/aws/setup`, `/me/aws/template` (image path, then repo copy), `PUT /me/aws`, `POST /me/aws/verify`, `PUT /me/models` (+ optional `api_keys`, never returned), `POST /me/models/verify`, `GET /me/models/available` (Bedrock foundation models + inference profiles through the caller's role, 20 s cap), `/connectors`, `/connectors/{toolkit}/connect|status|browse`, `POST /sources/preview` (10 pages / 20 s, `capped`), `/presets`, spot-check, export (preset + format validated against A4), `/files/{name:path}` (302 to presigned URL in aws, stream locally) + `/url`, `POST /resync` (501 until `sync.py`).
- Safety: OAuth `redirect_url` must be our own origin (no open redirect); downloads only for names in `Job.files` plus a path check; every job route 404s for another user; preview checks upload owners.
- `composio.fetch_page()` shared by job fetch and preview.
- `tests/test_api_slice2.py`: 17 tests, real STS / Bedrock / Composio / Notion / Firecrawl calls where keys exist.

### 2026-10-31: demo Notion wiki seeded (`gunbir/integration`)
- `demo/seed_notion.py --create-parent-under "Weekly To-do List"`: Composio cannot create root-level pages, so the script created the parent "Bob Demo – Support Wiki (fictional)" (`40a41e04-143a-81fc-b9ae-c9bdf9e107f4`) under the one page the connection could see, then the 6 pages under it. The create tool was enabled only for the run; confirmed afterwards that the auth config is back to the 5 read-only tools. The parent can be moved to the top level in Notion at any time.
- **Bug found and fixed:** Notion returns tables as `<table><tr><td>`; `notion_to_markdown` stripped the tags and put every cell on its own line, losing which value belongs to which row. It now turns Notion tables into markdown tables (outside code fences, `|` escaped). New test with the real structure.
- `demo/build_corpus.py --notion-only` cached all 6 pages through the normal read path. Round trip vs the source drafts: every table row identical, no number lost, no Notion tags left.

### 2026-10-31: cleared the deploy path for A5 (`gunbir/integration`, `d4448fe`)
- Merged Aaditya's latest `a1-core` (his own integration of A2/A3/A4 + `c3a260f`: new model fields `Cell.mix_weights/mix_kept`, `CostSummary.by_purpose`, `Row.chunk_ids/absent_topic/premise_evidence_id`; Jev + triage config defaults). Table conflict resolved by row, keeping his "done" statuses.
- **Deploy blocker found and fixed:** a clean `pip install ./backend` (the Dockerfile step) gave an app that crashed at import (FastAPI needs `python-multipart` for `POST /uploads`), so the Lambda readiness check on `/api/ping` could never pass. Added `python-multipart` (+ dev `reportlab`) with `uv add`; pyproject + uv.lock updated.
- `GET /api/health` (`api/health.py`): parallel real checks with per-check 15 s timeouts, no fallbacks, no cache, keys redacted. Real local result in 2 s: firecrawl ok, composio ok; bedrock / jev / scaledown show their exact errors (no local AWS or Jev/ScaleDown keys).
- 500 catch-all keeps the `{error, detail}` shape (frontend ask).
- Verified like the container: fresh install from pyproject, `uvicorn bob.api.app:app --port 8080` with `BOB_AUTH=cognito`: `/api/ping` 200, `/api/config/public` 200, `/api/health` and `/api/me` 401 without a token.
- Answered the frontend's 5 requests in `CHANGES_REQUESTED.md`. 47 G1/G2 tests pass.

### 2026-10-31: integration branch, A1 core adoption, demo corpus (`gunbir/integration`)
- Merged `aaditya/a1-core` into `gunbir/g2-connectors` (`2fd398e`), then created `gunbir/integration` and merged the latest `a1-core` (AWS adapters, Dockerfile, CDK, quality workbench), `a2-read`, `a3-plan-write`, `a4-verify-ship` and `claude/bob-web`. Only conflicts: the `CHANGES_REQUESTED.md` table (kept every row) and `.gitignore` (union).
- Adapted G1 to A1's real code: `get_settings()`, `Event.id`, error handlers for `PreconditionFailed` / `JobRunning` / `RunnerBusy`. The orchestrator calls `fetch_documents(..., user_id=job.owner_id)` and `read_upload(upload_id)` exactly as G1 implements them.
- Upload ownership (see decisions). New `tests/test_api.py`: open routes, upload -> Documents, bad upload 400, bad body 422, orchestrator 412, 404 on every unknown-job route, cross-user upload 404.
- Full suite on the integration branch: 129 passed; 26 fail only for missing local AWS credentials / Jev and ScaleDown keys (24) or stale A1 assertions (2). All 44 G1/G2 tests pass.
- `connectors/firecrawl.py`: `scrape_page()`, `site_urls()`, optional crawl `prompt`.
- `demo/corpus/`: 25 real support pages (~310k chars, no chrome left) + `index.json` (`demo/build_corpus.py`, ~25 credits).
- `demo/notion_pages/`: 6 fictional wiki pages + README; `demo/seed_notion.py` (opens the create-page tool on the auth config for the run only, restores read-only in `finally`).

### 2026-10-31: Part 3, connectors (`gunbir/g2-connectors`)
- `connectors/firecrawl.py`: `crawl()` (start_crawl, poll every 2 s, progress once per new page, rate-limit retry, cancel on timeout) and `fetch()` -> `Document`s + ledger entry. `clean_markdown()` moved here from the smoke script; the script now imports it.
- Composio: inspected SDK 0.22.0 by introspection, listed all 60 Notion tools with real calls, created the read-only auth config, linked a Notion connection for `bob-local` (`ca_uKQOf8gvuHHF`, ACTIVE).
- `connectors/composio.py`: `connect`, `status`, `connections`, `browse`, `fetch`, `auth_config_id` (reuse or create once), `notion_to_markdown`. First real browse + fetch worked.
- Tests: 38 pass. New: `test_firecrawl.py` (cleanup offline + a real 3-page crawl, ~3 credits), `test_composio.py` (privacy check as another user, auth config reuse + read-only, real browse + fetch, Notion markup cleaner).
- The connected Notion workspace currently shares one personal page; the demo needs 5 to 10 support-style pages.

### 2026-10-30: Part 2, API slice 1 (`gunbir/g1-api`)
- Read the v4.1 G1 brief and CONTRACTS §2, §6, §7, §8, §9, §14. Checked every remote branch: no backend code from A1 yet.
- `connectors/parsers.py`: PDF (pypdf), DOCX (headings, lists, tables in document order), MD (front matter -> title + `source_url`), HTML (BeautifulSoup + markdownify), TXT, CSV. One normalized markdown form. Clear `ParseError` messages for unsupported, empty and broken files.
- `connectors/upload.py`: `save_uploads` (validate all, then `Blobs.put("runs/uploads/<id>/<name>")`), `read_upload(upload_id)`, `fetch(spec, ...)` -> `Document`s with `sha1` ids and hashes; parsing runs in `asyncio.to_thread`.
- `connectors/__init__.py`: `fetch_documents(spec, job_id, progress, *, user_id)` dispatch; Firecrawl and Composio modules imported lazily.
- `api/errors.py`, `api/deps.py`, `api/auth.py` (Cognito access-token check with cached JWKS: signature, issuer, expiry, `token_use=access`, `client_id`; `BOB_AUTH=none` -> user `local`; fail fast on bad config), `api/sse.py`, `api/routes.py`, `api/app.py`, `run.sh`.
- Routes in this slice: `/ping`, `/config/public`, `/me`, `POST /uploads` (6 MB cap -> 413), `POST /jobs` (412 / 429), `GET /jobs` (caller's jobs, newest first, without plan/report), `GET /jobs/{id}`, `PUT /jobs/{id}/plan`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events`, `GET /jobs/{id}/rows`, `GET /jobs/{id}/rows/{row_id}`. Every `/jobs/{id}/*` route returns 404 for another user's job.
- Tests: 21 pass. `test_parsers.py` (9) builds DOCX, PDF, HTML and CSV fixtures from the smoke pages at test time and checks real facts survive; also checked by hand against the live `docs.firecrawl.dev/webhooks/overview` HTML. `test_sse.py` (12): wire format, `retry:` first, heartbeat while idle, close at max lifetime, no lost event after a ping, source closed on disconnect, `Last-Event-ID` parsing.
- `ruff format` + `ruff check` clean; `mypy --strict` clean on the A1-independent modules.
- Logged 4 asks to A1 in `CHANGES_REQUESTED.md`.

### 2026-10-30: merged `main` (v4.1) into `gunbir/g2-connectors`
- v4.1 changed docs only: AWS serverless deploy (CloudFront + S3 UI, Lambda API + SSE, Fargate worker per job, DynamoDB + S3), Cognito sign-in, bring-your-own AWS for Bedrock, model-agnostic LLM layer, new A5 deploy agent.
- Smoke corpus needed no change. G1 grew: auth, owner checks, `/me*` routes, `Blobs` storage, Lambda limits (25 s per route, 6 MB bodies, no background work). G2: Composio calls now take `user_id` (`bob-<user id>`).

### 2026-10-30: Part 1, smoke corpus (`gunbir/g2-connectors`, `28d5d92`)
- Checked the installed `firecrawl-py` 4.54 SDK by introspection (context7 was unavailable): `map`, `scrape`, `start_crawl`, `get_crawl_status`; response fields `links[].url`, `metadata.title`.
- `demo/scrape_smoke.py`: maps `docs.firecrawl.dev` (453 URLs, 192 unique English pages), normalizes `#fragment` and `.md` duplicates, picks support pages by exact path, scrapes with `only_main_content` and `exclude_tags`, cleans, writes front matter (`source_url`, `title`, `fetched_at`).
- `demo/smoke/`: 5 pages (40k chars total) + `seeds.jsonl` with 10 support Q&As written from those pages. All 10 pass tier-1 rules (format, word limits, banned phrases, every number in the answer appears in the corpus).
- About 20 Firecrawl credits used. `.env` holds `FIRECRAWL_API_KEY`; it is gitignored and never staged.

## Next
1. Add the keys and allowlist the hosts, then run the runbook §3 end to end.
2. Jira and Confluence in `composio.py`, researched with real calls at first use.
3. Confirm the ScaleDown extract schema with a real call.
