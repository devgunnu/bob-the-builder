# Gunbir work log (G1 API + Files, G2 Connectors)

Running log of Gunbir's backend work. Newest entries at the top of the log.
Frontend (G3, G4) lives in `frontend/` on this branch (the former `claude/bob-web`).
**Working branch from 2026-10-31: `gunbir/integration`** = `main` + Aaditya's former `a1-core`, `a2-read`, `a3-plan-write`, `a4-verify-ship` + former `claude/bob-web` + `codex/infra-deployment` + our former `gunbir/g1-api` and `gunbir/g2-connectors`. Merged branches were deleted on GitHub except `codex/infra-deployment` (Aaditya's CodeBuild deploys from it). Remote branches left: `main`, `gunbir/integration`, `codex/infra-deployment`.
Source of truth stays `PLAN.md` and `CONTRACTS.md` (v4.1); this file records what is built, what is decided, and what is waiting on whom.

## Status

| Part | Owner | Branch | State |
|---|---|---|---|
| 1. Smoke corpus (`demo/smoke/`) | G2 | `gunbir/g2-connectors` | Done |
| 2. API slice 1 (parsers, uploads, auth, SSE, thin-path routes) | G1 | `gunbir/integration` | Done; runs on A1's real core; 44 G1/G2 tests pass |
| 3. Firecrawl + Composio (Notion) connectors | G2 | `gunbir/integration` | Done; real crawl, real Notion browse + fetch |
| 3b. Demo docs corpus (`demo/corpus/`, 25 pages) | G2 | `gunbir/integration` | Done |
| 3c. Demo Notion wiki (6 fictional pages) | G2 | `gunbir/integration` | Done: seeded in Notion, cached to `demo/corpus/notion/` |
| 4a. `/api/health` + container boot fix (`python-multipart`) | G1 | `gunbir/integration` | Done; container-style boot verified |
| 4. API slice 2 (`/me/aws*`, `/me/models*`, `/connectors*`, preview, spot-check, export, files + `/url`, presets, resync 501) | G1 | `gunbir/integration` | Done: all contract routes, including `/uploads/presign` (P1) |
| 5. Jira / Confluence, `sync.py` (P1; orchestrator resync needs `sync.py`) | G2 | `gunbir/integration` | `sync.py` done (A1 wires resync); Jira / Confluence later |
| 6. Integration with the frontend | G1 + G3/G4 | `gunbir/integration` | Merged, contract mismatches fixed, local stack runs together; full real job not run yet (see Next) |

## Waiting on

| From | What | Logged in |
|---|---|---|
| A1 | One stale test in `test_orchestrator.py` (`test_create_job_429_and_missing_stage_error`) assumes the G1 stage is missing | `CHANGES_REQUESTED.md` |
| A1 | Optional: `_seeds` passes `owner_id=job.owner_id` to `read_upload` | `CHANGES_REQUESTED.md` |
| A1 / team | Keys for a full local run: AWS credentials (Bedrock), `JEV_API_KEY`, `SCALEDOWN_API_KEY` (new names; contract §9 still says `OPENROUTER_API_KEY`) | |

## Decisions made (G1 / G2 scope)

| Decision | Why |
|---|---|
| Smoke corpus = 5 support-style pages: `/billing`, `/rate-limits`, `/webhooks/overview`, `/webhooks/security`, `/features/key-restrictions` | Short pages full of real limits, settings and numbers, which the false-premise and `numbers` checks need. Feature pages (scrape, crawl) were 50k to 300k chars each. |
| `clean_markdown()` strips docs-site chrome from Firecrawl output | Mintlify pages carry a ~100k-char JSON config blob, a chat-widget greeting, "Suggest edits" footers and heading anchor links after `only_main_content`. `/billing` went from 130k to 24k chars with no content lost. Moves into `connectors/firecrawl.py` in Part 3. |
| Firecrawl calls retry on rate limits (wait 15 s, 5 tries) | Our key is on the free plan: 10 req/min on scrape/map, 2 req/min on crawl, 1,000 credits/month. |
| All A1 touch points in one G1 file, `api/deps.py` | Written before A1 existed; when A1 landed only `deps.py` (`get_settings()`), `sse.event_parts` (`Event.id`) and the error mapping changed. |
| Routes no longer pre-check 412; app-wide handlers map A1's `PreconditionFailed` (412), `JobRunning` (409) and `RunnerBusy` (429) | One source of truth: the orchestrator decides. |
| Uploads are owner-scoped: `.owner` marker per upload; `POST /jobs` returns 404 for another user's `upload_ids` / `seed_upload_id`; the upload connector re-checks the owner in the worker | Acceptance criterion (quality/acceptance.md): a second user must not use the first user's uploads. |
| Demo corpus = curated list of 27 support paths checked against the real site map, first 25 under 60k chars | A blind crawl from the docs root returned quickstarts, use cases and API-reference stubs; a Firecrawl `prompt` crawl was too narrow (6 pages). The crawl connector keeps an optional `prompt`. |
| Demo Notion wiki is fictional, written for the demo, under a parent page marked "(fictional)"; facts shared with the public docs match them exactly | Gives the dataset internal-only facts and real "not in docs" gaps, without passing as Firecrawl's real policy. |
| Composio cannot create root-level Notion pages | Tool limitation ("must have a parent"), so one parent page must be made by hand. |
| `build_corpus.py` caches only the demo wiki titles from Notion | A first run cached a personal page; it was deleted before any commit. |
| `sse.py` and `parsers.py` import nothing from A1 at load time | So both are testable now, before A1 lands. |
| Upload document URI = `upload://<upload_id>/<name>` (contract example shows `upload://<name>`) | Two uploads with the same file name would get the same `Document.id`. |
| Upload ids must be 32 hex chars | A crafted id cannot escape the `runs/uploads/` prefix. |
| `.json` / `.jsonl` uploads are accepted but refused as document sources | They are seed files (A1 `load_seeds`), not docs. |
| CSV: markdown table up to 30 rows x 8 columns, else one `##` section per row | The chunker never splits inside a table, so a large table would become one giant chunk. |
| HTML parser drops `script`, `style`, `nav`, `footer`, `button`, `form`, `svg` and empty links; prefers `<main>` / `<article>` | The live docs page went from 257 KB to 3 KB of clean content. |
| `PUT /jobs/{id}/plan` returns 409 unless the job status is `awaiting_approval` | Not in the contract; prevents approving a plan twice or on a finished job. Frontend should handle the 409. |
| `POST /jobs` checks `bedrock_verified_at` / `models_verified_at` in the route (412) and maps `RunnerBusy` to 429 | Contract §6 status rules. |
| Error body everywhere: `{error, provider?, detail?}`; validation errors -> 422 `{error: "invalid request", detail}` | One shape for the frontend to show. |
| No GZip middleware | It buffers the SSE stream. |
| Composio Notion auth config `bob-notion-read` (`ac_ELz4KgTaZsVZ`) is Composio-managed OAuth restricted to 5 read-only tools | Bob only reads; a bug cannot edit or delete a user's pages. |
| Notion fetch uses `NOTION_GET_PAGE_MARKDOWN` (one call per page); browse uses `NOTION_SEARCH_NOTION_PAGE`; both pinned to version `20261018_00` | Markdown in one call, no recursive block walk; a pinned version cannot change shape under us. |
| Connections are created with `connected_accounts.link` (hosted `connect.composio.dev/link/...` page) | Composio retired `initiate` for managed OAuth (HTTP 400 "no longer supported"). |
| `notion_to_markdown()` strips Notion-flavored markup (spans, columns, `<unknown/>`, `<empty-block/>`, `{color=...}`, empty to-dos) outside code fences | Found on the first real fetch; the tags would pollute chunks and checks. A real page went from 1,112 to 337 chars with all text kept. |
| Every Composio call checks that the connection's `user_id` is `bob-<caller id>`; otherwise `ConnectionNotFound` | Per-user privacy (CONTRACTS §14); tested with a real call as another user. |
| Firecrawl crawl excludes `*.md` paths, skips pages under 200 chars or HTTP >= 400, cancels the crawl on timeout or task cancel | Docs sites publish `.md` duplicates; no paying for pages nobody reads. |
| Merged `gunbir/g1-api` into `gunbir/g2-connectors` (`c78e652`) | Connectors reuse `parsers.normalize_markdown`; one copy of shared code. |
| Deployment: S3 + CloudFront for the UI (not Amplify Hosting) | Matches v4.1 (D25). `aws-amplify` is used only as the Cognito sign-in library in the frontend. |

## How to run

Local scratch environment (until A1 adds `backend/pyproject.toml`):

```bash
uv venv .venv && VIRTUAL_ENV=.venv uv pip install firecrawl-py python-dotenv fastapi uvicorn pydantic pydantic-settings pypdf python-docx markdownify beautifulsoup4 "pyjwt[crypto]" httpx python-multipart pytest pytest-asyncio reportlab ruff
```

```bash
cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest -q tests/
```

```bash
.venv/bin/python demo/scrape_smoke.py   # re-scrape the smoke corpus; needs FIRECRAWL_API_KEY in .env
```

API (works once A1 core lands): `backend/run.sh` serves on `:8000`; the Vite dev server proxies `/api`.

## Log

### 2026-10-31: design review, frontend fixes against the real backend, sync.py (merged from `claude/bold-hopper-tsps3y`)
- **Design review of Codex's work** (`6e3857d..e4fd613`) against UX_NOTES at 1440x900 and 390x844, with throwaway Playwright fixtures outside the repo. Fixed: wordmark overlapped the step tracker on phones; Report hero collapsed into a one-word column on phones; Plan's Start button is a sticky bottom bar on phones; Setup had two submit buttons; jargon (Jev triage, raw check names, case-type ids, job status ids); the Row screen always showed Build as the current step; heatgrid clipped its headers on phones; Amplify UI (520 KB) loaded even with auth `none` (now a lazy chunk, `auth/CognitoGate.tsx`).
- **Frontend vs the real backend:** new model fields in `types.ts`; the final `done` event; rows page oldest first, so "Load older rows" and the cell drawer now read from the newest end (`api.newestRows`); source passages show once with the extracted facts highlighted inside them (spans carry document offsets; the old slice landed mid-word); still Bob follows job status (the worker reports per cell, not per stage); local-mode Account (default AWS chain, no role to deploy); missing `BOB_ACCOUNT_ID` shows a clear note; plain 409 messages; Report labels check names.
- **Cost fix:** every screen called `/api/health` (one paid call per provider) on mount and every 60 s. Now one shared result, at most every 5 minutes, only while visible; the red chip opens the exact errors on tap.
- **P1:** `connectors/sync.py` (`diff`, `stale_doc_ids`, 3 tests on smoke docs); self sign-up switch (`signup` in `/config/public`, sign-up tab only when open); Bedrock model picker in the Models panel (suggestions from `/me/models/available`).
- **Merge note:** that branch had its own API slice 2 written in parallel (`api/me.py`, `api/results.py`). This branch's version (`account.py`, `sources.py`, `routes.py`) was kept; the duplicates were dropped, and the frontend was adapted to its response shapes.
- **First local run of both halves together** (`backend/run.sh` + `npm run dev`, auth `none`): `/me`, `/me/aws/setup`, `PUT /me/aws`, `/me/aws/verify`, `PUT /me/models`, `/me/models/verify`, `/uploads` (3 smoke files), `POST /jobs` (412 with the real reason), `/connectors`, `/health` all answered from the real code, and each provider error reached the UI word for word. Found: the empty `AWS_PROFILE=` in `.env.example` breaks boto3 locally (logged for A1). The run stopped there: the cloud session's network policy denied `api.typesafe.ai`, `api.scaledown.xyz`, `api.firecrawl.dev`, `backend.composio.dev`, `huggingface.co`, and its AWS keys were invalid. No call was stubbed.

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
1. **Run one real job end to end** (runbook: `.agents/HANDOFF_NEXT_CHAT.md`): upload or URL, plan, edit, build, row, report, download. Fix every break in G-owned files; ask A1 through `CHANGES_REQUESTED.md` for the rest.
2. A1 wires `resync()` on `connectors/sync.py` (the route returns 501 until then).
3. Jira and Confluence in `composio.py` (P1), researched with real calls at first use.
4. Frontend presigned upload for files over 6 MB (`POST /uploads/presign`; local `PUT /api/uploads/{id}/content` needs the Authorization header).
