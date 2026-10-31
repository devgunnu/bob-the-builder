# Change requests between owners

Use this file when you need a change in a file that you do not own (CONTRACTS §0 rule 1).
Add one entry, then tell your builder. The file owner marks the entry `done` with the commit hash.

| Time | From | To (owner) | File | Request | Status |
|---|---|---|---|---|---|
| 2026-10-30 | G1 | A1 | `backend/bob/config.py` | Confirm the attribute names G1 reads: `settings.auth`, `cognito_region`, `cognito_user_pool_id`, `cognito_client_id`, `cognito_domain`, `public_url`, `sse_heartbeat_s`, `sse_max_s` (env `BOB_<NAME>` -> `<name>`, as with `runs_dir`). If yours differ, G1 changes only `api/deps.py` and the callers listed there. | open |
| 2026-10-30 | G1 | A1 | `backend/bob/orchestrator.py` | Confirm `Orchestrator()` takes no constructor arguments (G1 keeps one instance per process in `api/deps.get_orchestrator`). Missing job or row: raise `LookupError` (for example `KeyError`); routes map it to 404. | open |
| 2026-10-30 | G1 | A1 | `backend/bob/core/events.py` | Contract §7 uses an `Event` type but §2 does not define it. G1 reads `event.seq: int`, `event.type: str`, `event.data: dict` (same values as `EventLog.append`). Please add `Event` to `core/models.py` with these fields, or tell G1 the names. | open |
| 2026-10-30 | G1 | A1 | `backend/pyproject.toml` | Add `python-multipart` (FastAPI needs it for `POST /uploads` multipart) and `beautifulsoup4` (HTML parser imports it directly). Dev only: `pytest`, `pytest-asyncio`, `reportlab` (parser tests build a PDF from the smoke pages). | open |
