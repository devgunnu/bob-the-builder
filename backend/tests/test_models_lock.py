from datetime import UTC, datetime

from bob.config import EffectiveSettings, default_model_roles, get_settings, parse_model_spec, settings_for
from bob.core.models import Job, JobOptions, JobSpec, JobStatus, SourceSpec
from bob.llm.client import model_for


def _job(options: JobOptions | None = None) -> Job:
    spec = JobSpec(
        goal="support bot for the smoke docs",
        sources=[SourceSpec(kind="upload", upload_ids=["u1"])],
        target_rows=20,
        options=options or JobOptions(),
    )
    now = datetime.now(UTC)
    return Job(
        id="j1", spec=spec, owner_id="local", models=default_model_roles(), created_at=now, updated_at=now
    )


def test_job_defaults_roundtrip():
    job = _job()
    assert job.status is JobStatus.created
    assert job.report is None and job.heartbeat_at is None
    assert job.spec.options == JobOptions()
    assert Job.model_validate_json(job.model_dump_json()) == job


def test_settings_for_applies_options():
    base = get_settings()
    base_keep, base_axes = base.keep_p, list(base.cell_axes)
    job = _job(JobOptions(keep_p=0.75, cell_axes=["topic", "persona"]))
    eff = settings_for(job)
    assert isinstance(eff, EffectiveSettings)
    assert eff.keep_p == 0.75
    assert eff.cell_axes == ["topic", "persona"]
    assert eff.reject_p == base.reject_p  # untouched option keeps the env default
    assert eff.runs_dir == base.runs_dir
    # the cached base Settings object is not changed
    assert get_settings().keep_p == base_keep and get_settings().cell_axes == base_axes


def test_model_spec_and_fallback():
    cfg = parse_model_spec("bedrock:global.anthropic.claude-haiku-5-5")
    assert (
        cfg is not None and cfg.provider == "bedrock" and cfg.model_id == "global.anthropic.claude-haiku-5-5"
    )
    assert parse_model_spec("") is None
    job = _job()
    assert model_for(job, "fallback") == job.models.writer
