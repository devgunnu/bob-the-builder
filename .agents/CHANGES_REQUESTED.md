# Change requests between owners

Use this file when you need a change in a file that you do not own (CONTRACTS §0 rule 1).
Add one entry, then tell your builder. The file owner marks the entry `done` with the commit hash.

| Time | From | To (owner) | File | Request | Status |
|---|---|---|---|---|---|
| 2026-10-30 T+0:15 | A1 | A5 | `.gitignore` | created by A1 before first commit; A5 please review | done 36e0153 |
| 2026-10-30 T+0:15 | A1 | A5 | `backend/bob/aws/*` | please use these names (A1 imports them lazily): `bob.aws.secrets.load_secret_into_env(secret_arn: str \| None) -> None` (config.get_settings() calls it when BOB_ENV=aws, before Settings()); zero-arg classes `bob.aws.blobs.S3Blobs`, `bob.aws.store.DynamoStore`, `bob.aws.events.DynamoEventLog`, `bob.aws.runner.EcsRunner` (read get_settings()) | open |
| 2026-10-30 T+0:20 | A2 | A1 | `backend/bob/config.py`, `.env.example` | Jev direct API confirmed by real calls: set `JEV_BASE_URL` default `https://api.typesafe.ai` (path `/v1/systemone`, header `Authorization: Bearer <JEV_API_KEY>`) and `JEV_MODEL` default `jev-1.14.0` (also valid: `jev-1.13.0`, `jev-latest`). The current default `typesafe/jev-1.13-20260917` gives HTTP 400 "Unknown model" on the direct API. Aaditya: please also fix the two values in the root `.env`. | open |
| 2026-10-30 T+0:20 | A2 | A1 | `backend/bob/core/cache.py` | A2 clients call `await cache.get(endpoint: str, model: str, body: dict) -> dict \| None` and `await cache.put(endpoint, model, body, response: dict) -> None` (imported lazily; skipped when `BOB_CACHE=0`). Please use these names, or tell A2 the real ones. | open |
| 2026-10-30 T+0:20 | A2 | A1 | `backend/bob/core/ledger.py` | `ledger.record` has no `purpose` field, so the A2 `purpose` tag (triage, verify, probe, evidence, topics) is not recorded. Optional: add `purpose: str \| None = None` (keyword-only); A2 will pass it. | open |
| 2026-10-30 | A1 | A5 | `backend/bob/aws/runner.py`, `aws/store.py` | optional methods the orchestrator uses when present (local impls on `aaditya/a1-core`): `Runner.check_capacity(owner_id) -> None` (raise RunnerBusy before create_job saves; else nothing-saved-on-429 cannot hold), `Runner.stopped_reason(job_id) -> str \| None` (ECS stoppedReason for the watchdog; may be async), `Store.put_job_if_status(job, expected: JobStatus) -> bool` (conditional META update for the watchdog/cancel) | open |
| 2026-10-30 | A1 | A2, A3 | `pipeline/*` | stages without a `job` parameter (triage, build_topics, build_evidence, propose_plan) get the job from `bob.llm.client.current_job()` (ContextVar set by run_job) and call `get_llm(current_job(), role)` | open |
| 2026-10-30 | A1 | G1 | `api/routes.py`, `api/sse.py` | orchestrator errors: `PreconditionFailed` (.status_code 412, .body), `RunnerBusy` -> 429, `JobRunning` (.status_code 409, .body), `KeyError` -> 404. `subscribe()` is an async generator (no await). After `files.ready` the worker emits `job.status done` then a `done` event `{files}` | open |
| 2026-10-30 | A4 | A1 | `core/models.py`, `orchestrator.py` | GenContext.verify_state; export spec.preset + "full" | done (see A1 commit "A1: orchestrator") |
