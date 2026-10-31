"""`bob_manifest.json` (CONTRACTS section 11). Owner: A4.

Records the job, plan, counts, cost, checks, the model id per role (`Job.models`), the effective settings of
the job (`settings_for(job)`: env defaults + `JobSpec.options`) and created_at. Never writes a secret.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bob.config import settings_for
from bob.core.models import Job, Row

# Settings fields that hold secrets or machine-local values: never in the manifest.
_SECRET_MARKERS = ("api_key", "secret", "kms_key", "aws_profile", "account_id")


def effective_settings(job: Job) -> dict[str, Any]:
    eff = settings_for(job).model_dump(mode="json")
    return {k: v for k, v in eff.items() if not any(m in k for m in _SECRET_MARKERS)}


def model_ids(job: Job) -> dict[str, str]:
    out: dict[str, str] = {}
    for role in ("writer", "planner", "judge", "fallback"):
        cfg = getattr(job.models, role) or job.models.writer  # fallback None = writer
        out[role] = f"{cfg.provider}:{cfg.model_id}"
    return out


def check_summary(rows: list[Row]) -> dict[str, dict[str, Any]]:
    """check name -> {tier, ran, passed, pass_rate} over all rows."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        for c in row.checks:
            s = out.setdefault(c.name, {"tier": c.tier, "ran": 0, "passed": 0})
            s["ran"] += 1
            s["passed"] += int(c.passed)
    for s in out.values():
        s["pass_rate"] = round(s["passed"] / s["ran"], 4) if s["ran"] else None
    return out


def build_manifest(
    job: Job,
    rows: list[Row],
    *,
    preset: str,
    formats: list[str],
    splits: dict[str, int],
    files: list[str],
) -> dict[str, Any]:
    return {
        "bob_manifest_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "job": {
            "id": job.id,
            "goal": job.spec.goal,
            "status": str(job.status.value),
            "round": job.round,
            "target_rows": job.spec.target_rows,
            "budget_usd": job.spec.budget_usd,
            "created_at": job.created_at.isoformat(),
        },
        "preset": preset,
        "formats": formats,
        "splits": splits,
        "files": files,
        "plan": job.plan.model_dump(mode="json") if job.plan else None,
        "counts": {
            **job.counts,
            "rows_total": len(rows),
            "rows_kept": sum(r.verdict == "kept" for r in rows),
            "rows_rejected": sum(r.verdict == "rejected" for r in rows),
        },
        "cost": job.cost.model_dump(mode="json"),
        "checks": check_summary(rows),
        "models": model_ids(job),
        "settings": effective_settings(job),
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
