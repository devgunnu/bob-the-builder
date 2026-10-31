# Change requests between owners

Use this file when you need a change in a file that you do not own (CONTRACTS §0 rule 1).
Add one entry, then tell your builder. The file owner marks the entry `done` with the commit hash.

| Time | From | To (owner) | File | Request | Status |
|---|---|---|---|---|---|
| T+0 | G3 | G2 | connectors/composio.py | Composio `SourceSpec.scope` keys: the UI sends `{page_ids}` for Notion and Confluence, `{file_ids}` for Google Drive, `{project_keys, issue_keys}` for Jira (from `/browse` item `kind`). Confirm or tell G3 the keys you expect. | open |
| T+0 | G3 | G1 | api/app.py | Error bodies: the client reads `{error, provider, detail}` on non-2xx responses, as G3's brief says. Please return that shape from every route. | open |
| T+0 | G3 | G1 | api/app.py | Dev setup: Vite proxies `/api` to `http://localhost:8000` (override with `BOB_API_PROXY`); production uses `VITE_API_URL`. Serve the API under `/api` on port 8000, and send SSE with `id:` lines so `Last-Event-ID` replay works. | open |
| T+0 | G3 | G1 | api/routes.py | OAuth redirect route is `/oauth/callback` on the frontend origin; `POST /connectors/{toolkit}/connect` receives it as `redirect_url`. | open |
