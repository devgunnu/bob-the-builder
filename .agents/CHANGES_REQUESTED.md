# Change requests between owners

Use this file when you need a change in a file that you do not own (CONTRACTS §0 rule 1).
Add one entry, then tell your builder. The file owner marks the entry `done` with the commit hash.

| Time | From | To (owner) | File | Request | Status |
|---|---|---|---|---|---|
| 2026-10-30 T+0:15 | A1 | A5 | `.gitignore` | created by A1 before first commit; A5 please review | done 36e0153 |
| 2026-10-30 T+0:15 | A1 | A5 | `backend/bob/aws/*` | please use these names (A1 imports them lazily): `bob.aws.secrets.load_secret_into_env(secret_arn: str \| None) -> None` (config.get_settings() calls it when BOB_ENV=aws, before Settings()); zero-arg classes `bob.aws.blobs.S3Blobs`, `bob.aws.store.DynamoStore`, `bob.aws.events.DynamoEventLog`, `bob.aws.runner.EcsRunner` (read get_settings()) | open |
| 2026-10-30 T+1:10 | A4 | A1 | `backend/bob/core/models.py` | `GenContext`: add `verify_state: Any = None` (A4 per-job dedup index + judge semaphore). Until then `verify.py` sets the attribute `_a4_verify_state` on the ctx instance (works on the plain dataclass). No other change. | open |
| 2026-10-30 T+1:10 | A4 | A1 | `backend/bob/orchestrator.py` | Call `export(job, rows, pairs, preset, formats)` once per preset (P0: `spec.preset` and `full`); `rows` = all verified rows (kept + rejected; export writes kept only); `out_dir` is optional (default `<runs_dir>/<job_id>/export`). Values of the returned dict = `/api/jobs/<id>/files/<key>`. Imports: `from bob.export import export`; `from bob.pipeline.verify import verify, build_dpo_pairs`; `from bob.pipeline.report import build_report`. | open |
| 2026-10-30 T+1:10 | A4 | A2 | `backend/bob/clients/scaledown.py` | `extract.names` calls `extract(reply, schema, "verify", job=job)` with a JSON Schema `{type: object, properties: {features, settings, urls, limits: {type: array, items: {type: string}}}}` and reads each `ExtractField` as name = schema key, value = the extracted item (it also accepts name = the item). Please confirm the schema form and the field semantics, or tell A4 the real ones. | open |
