"""Test support for A2 tests: real keys from the nearest `.env` and a small real Job. No mocks.

The `.env` search walks up from this file, so a git worktree under the main checkout finds the main `.env`.
Values already in os.environ win. JEV_BASE_URL / JEV_MODEL get the values confirmed at the first real call
(clients/jev.py docstring) only when the env value is empty or in the old OpenRouter form.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

JEV_BASE_URL = "https://api.typesafe.ai"
JEV_MODEL = "jev-1.14.0"


def _load_env() -> Path | None:
    for d in Path(__file__).resolve().parents:
        f = d / ".env"
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if v and k.strip() not in os.environ:
                    os.environ[k.strip()] = v
            return f
    return None


ENV_FILE = _load_env()
if not os.environ.get("JEV_BASE_URL"):
    os.environ["JEV_BASE_URL"] = JEV_BASE_URL
if os.environ.get("JEV_MODEL", "").startswith("typesafe/"):
    os.environ["JEV_MODEL"] = JEV_MODEL
os.environ.setdefault("BOB_ENV", "local")
if os.environ.get("BOB_ENV") != "aws":
    os.environ["BOB_SECRET_ARN"] = ""

from bob.config import default_bedrock_access, default_model_roles, get_settings  # noqa: E402
from bob.core.models import Job, JobSpec, SourceSpec  # noqa: E402

get_settings.cache_clear()


def make_job(job_id: str = "a2-test", goal: str = "support assistant for the Bob the Builder docs") -> Job:
    now = datetime.now(UTC)
    spec = JobSpec(goal=goal, sources=[SourceSpec(kind="upload", upload_ids=["a2"])], target_rows=20)
    return Job(
        id=job_id,
        spec=spec,
        owner_id="local",
        bedrock=default_bedrock_access(),
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )


def repo_root() -> Path:
    """Root of this checkout (the folder that holds `.agents/`)."""
    for d in Path(__file__).resolve().parents:
        if (d / ".agents").is_dir():
            return d
    raise RuntimeError("no .agents folder above the tests")


def agents_documents():
    """Real local text as Documents: the repo's own `.agents/*.md` files (not a fake corpus)."""
    import hashlib

    from bob.core.models import Document

    docs = []
    for p in sorted((repo_root() / ".agents").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        uri = f"upload://{p.name}"
        docs.append(
            Document(
                id=hashlib.sha1(uri.encode()).hexdigest()[:12],
                source_kind="upload",
                uri=uri,
                title=p.stem,
                text=text,
                content_hash=hashlib.sha1(text.encode()).hexdigest(),
                fetched_at=datetime.now(UTC),
            )
        )
    return docs
