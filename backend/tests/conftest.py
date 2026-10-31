"""Test setup: every test run writes under a fresh BOB_RUNS_DIR (never the repo runs/ folder)."""

import os
import tempfile

# Unconditional: the documented test command sources ../.env (BOB_RUNS_DIR=runs) first, and test
# jobs must never land in the real local runs dir that the app shows.
os.environ["BOB_RUNS_DIR"] = tempfile.mkdtemp(prefix="bob-test-runs-")
os.environ.setdefault("BOB_ENV", "local")
