#!/usr/bin/env bash
# Run the Bob API locally on :8000 (the Vite dev server proxies /api here).
# Env comes from ../.env (see .env.example). Local mode: BOB_ENV=local.
set -euo pipefail
cd "$(dirname "$0")"
exec uvicorn bob.api.app:app --host 127.0.0.1 --port "${PORT:-8000}" --reload --env-file ../.env
