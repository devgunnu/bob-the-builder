"""Test setup: every test run writes under a fresh BOB_RUNS_DIR (never the repo runs/ folder)."""

import os
import tempfile

os.environ.setdefault("BOB_RUNS_DIR", tempfile.mkdtemp(prefix="bob-test-runs-"))
os.environ.setdefault("BOB_ENV", "local")
