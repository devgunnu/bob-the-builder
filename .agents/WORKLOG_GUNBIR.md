# Gunbir work log (G1 API + Files, G2 Connectors)

Running log of Gunbir's backend work. Newest entries at the top of the log.
Frontend (G3, G4) is built in a separate session on branch `claude/bob-web`.
Source of truth stays `PLAN.md` and `CONTRACTS.md` (v4.1); this file records what is built, what is decided, and what is waiting on whom.

## Status

| Part | Owner | Branch | State |
|---|---|---|---|
| 1. Smoke corpus (`demo/smoke/`) | G2 | `gunbir/g2-connectors` | Done, pushed (`28d5d92`), v4.1 merged in (`3fd32bc`) |
| 2. API slice 1 (parsers, uploads, auth, SSE, thin-path routes) | G1 | `gunbir/g1-api` | Written; parsers + SSE tested; routes wait on A1 core |
| 3. Firecrawl + Composio (Notion) connectors | G2 | | Next |
| 4. API slice 2 (health, `/me/aws*`, `/me/models*`, connectors, preview, spot-check, export, files, presets) | G1 | | After A1 core lands |
| 5. Jira / Confluence, `sync.py` (P1) | G2 | | Later |
| 6. Integration with the frontend | G1 + G3/G4 | | After 2 to 4 |

## Waiting on

| From | What | Logged in |
|---|---|---|
| A1 (Aaditya) | `core/models.py`, `config.py`, `core/backends.py` (`get_blobs`), `core/runner.py` (`RunnerBusy`), `orchestrator.py`. None exist on any branch yet. G1 routes, uploads and auth import them. | |
| A1 | Confirm `settings` attribute names G1 reads | `CHANGES_REQUESTED.md` |
| A1 | Confirm `Orchestrator()` has no constructor args; missing job/row raises `LookupError` | `CHANGES_REQUESTED.md` |
| A1 | Define `Event` (`seq`, `type`, `data`); the contract uses it but never defines it | `CHANGES_REQUESTED.md` |
| A1 | Add `python-multipart`, `beautifulsoup4` (+ dev: `pytest`, `pytest-asyncio`, `reportlab`) to `pyproject.toml` | `CHANGES_REQUESTED.md` |
| Frontend session | Merge `main` (v4.1). Its `client.ts` sends no auth header, uses plain `EventSource` (cannot send one), downloads files by direct link instead of the `/url` route, and `encodeURIComponent` breaks `{name:path}` keys. No Account screen yet. | |

## Decisions made (G1 / G2 scope)

| Decision | Why |
|---|---|
| Smoke corpus = 5 support-style pages: `/billing`, `/rate-limits`, `/webhooks/overview`, `/webhooks/security`, `/features/key-restrictions` | Short pages full of real limits, settings and numbers, which the false-premise and `numbers` checks need. Feature pages (scrape, crawl) were 50k to 300k chars each. |
| `clean_markdown()` strips docs-site chrome from Firecrawl output | Mintlify pages carry a ~100k-char JSON config blob, a chat-widget greeting, "Suggest edits" footers and heading anchor links after `only_main_content`. `/billing` went from 130k to 24k chars with no content lost. Moves into `connectors/firecrawl.py` in Part 3. |
| Firecrawl calls retry on rate limits (wait 15 s, 5 tries) | Our key is on the free plan: 10 req/min on scrape/map, 2 req/min on crawl, 1,000 credits/month. |
| All A1 touch points in one G1 file, `api/deps.py` | A1 code does not exist yet. If A1's names differ, only that file (and the few callers it lists) changes. |
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
1. Part 3: `connectors/firecrawl.py` (crawl with per-page progress, cleanup moved from the smoke script, retries, ledger entry) and `connectors/composio.py` (list toolkits and tool slugs at runtime, Notion connect / status / browse / fetch with `user_id = bob-<id>`). Needs `COMPOSIO_API_KEY`.
2. Full demo crawl (cap 25 pages) -> `demo/corpus/` + `index.json`.
3. When A1 core lands: run the routes, uploads and auth against it, then API slice 2.
