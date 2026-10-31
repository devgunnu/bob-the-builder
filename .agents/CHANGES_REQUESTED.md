# Change requests between owners

Use this file when you need a change in a file that you do not own (CONTRACTS §0 rule 1).
Add one entry, then tell your builder. The file owner marks the entry `done` with the commit hash.

| Time | From | To (owner) | File | Request | Status |
|---|---|---|---|---|---|
| 2026-10-30 T+0:15 | A1 | A5 | `.gitignore` | created by A1 before first commit; A5 please review | pending |
| 2026-10-30 T+0:15 | A1 | A5 | `backend/bob/aws/*` | please use these names (A1 imports them lazily): `bob.aws.secrets.load_secret_into_env(secret_arn: str \| None) -> None` (config.get_settings() calls it when BOB_ENV=aws, before Settings()); zero-arg classes `bob.aws.blobs.S3Blobs`, `bob.aws.store.DynamoStore`, `bob.aws.events.DynamoEventLog`, `bob.aws.runner.EcsRunner` (read get_settings()) | open |
