# Change requests between owners

Use this file when you need a change in a file that you do not own (CONTRACTS §0 rule 1).
Add one entry, then tell your builder. The file owner marks the entry `done` with the commit hash.

| Time | From | To (owner) | File | Request | Status |
|---|---|---|---|---|---|
| 2026-10-30 T+0:15 | A1 | A5 | `.gitignore` | created by A1 before first commit; A5 please review | done 36e0153 |
| 2026-10-30 T+0:15 | A1 | A5 | `backend/bob/aws/*` | please use these names (A1 imports them lazily): `bob.aws.secrets.load_secret_into_env(secret_arn: str \| None) -> None` (config.get_settings() calls it when BOB_ENV=aws, before Settings()); zero-arg classes `bob.aws.blobs.S3Blobs`, `bob.aws.store.DynamoStore`, `bob.aws.events.DynamoEventLog`, `bob.aws.runner.EcsRunner` (read get_settings()) | open |
| 2026-10-30 | A1 | A5 | `backend/bob/aws/runner.py`, `aws/store.py` | optional methods the orchestrator uses when present (local impls on `aaditya/a1-core`): `Runner.check_capacity(owner_id) -> None` (raise RunnerBusy before create_job saves; else nothing-saved-on-429 cannot hold), `Runner.stopped_reason(job_id) -> str \| None` (ECS stoppedReason for the watchdog; may be async), `Store.put_job_if_status(job, expected: JobStatus) -> bool` (conditional META update for the watchdog/cancel) | open |
| 2026-10-30 | A1 | A2, A3 | `pipeline/*` | stages without a `job` parameter (triage, build_topics, build_evidence, propose_plan) get the job from `bob.llm.client.current_job()` (ContextVar set by run_job) and call `get_llm(current_job(), role)` | open |
| 2026-10-30 | A1 | G1 | `api/routes.py`, `api/sse.py` | orchestrator errors: `PreconditionFailed` (.status_code 412, .body), `RunnerBusy` -> 429, `JobRunning` (.status_code 409, .body), `KeyError` -> 404. `subscribe()` is an async generator (no await). After `files.ready` the worker emits `job.status done` then a `done` event `{files}` | done (G1 maps all four in `api/errors.py` + `routes.py`) |
| 2026-10-30 | A4 | A1 | `core/models.py`, `orchestrator.py` | GenContext.verify_state; export spec.preset + "full" | done (see A1 commit "A1: orchestrator") |
| 2026-10-30 | G1 | A1 | `backend/bob/config.py` | Confirm the settings attribute names G1 reads. | done: names match; G1 uses `get_settings()` |
| 2026-10-30 | G1 | A1 | `backend/bob/orchestrator.py` | Confirm `Orchestrator()` takes no args; missing job/row raises `LookupError`. | done: optional args with defaults; `KeyError` |
| 2026-10-30 | G1 | A1 | `backend/bob/core/models.py` | Define `Event`. | done: `Event(id, type, data)`; G1 reads `event.id` |
| 2026-10-30 | G1 | A1 | `backend/pyproject.toml` | Add `python-multipart` (FastAPI needs it for `POST /uploads` multipart forms; without it the app fails at import). Dev only: `reportlab` (parser tests build a PDF from the smoke pages). `beautifulsoup4` is not needed: `markdownify` already depends on it. | open |
| 2026-10-31 | G1 | A1 | `backend/tests/test_orchestrator.py` | `test_create_job_429_and_missing_stage_error` expects the job error to mention `fetch_documents` (written before G1 existed). With G1's `fetch_documents` merged, the same job now fails correctly with `UploadNotFound: upload 'u1' not found`. Please assert on that (or upload a real smoke file first). | open |
