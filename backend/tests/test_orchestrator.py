"""Orchestrator on local backends (tmp runs_dir) with real Bedrock / STS calls for the verify methods.

The job tests check the real error paths (a failing stage ends the job in `error`, never a hang)
and the offline parts of resync (uploads only: no provider call).
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from bob.config import default_model_roles
from bob.core.blobs import LocalBlobs
from bob.core.events import LocalEventLog
from bob.core.models import BedrockAccess, Job, JobSpec, JobStatus, SourceSpec
from bob.core.runner import LocalRunner, RunnerBusy
from bob.core.store import LocalStore
from bob.orchestrator import JobRunning, Orchestrator, PreconditionFailed, load_seeds, stage

SPEC = JobSpec(goal="support bot", sources=[SourceSpec(kind="upload", upload_ids=["u1"])], target_rows=20)


def _orch(tmp_path, runner=None) -> Orchestrator:
    return Orchestrator(
        store=LocalStore(tmp_path),
        events=LocalEventLog(tmp_path),
        blobs=LocalBlobs(tmp_path),
        runner=runner or LocalRunner(max_workers=2, max_active_per_user=1),
    )


async def test_existing_profile_switches_to_hosting_bedrock(tmp_path, monkeypatch):
    from bob.config import get_settings

    settings = get_settings().model_copy(update={"env": "aws", "bedrock_auth": "default", "bedrock_default_region": "us-east-1"})
    monkeypatch.setattr("bob.orchestrator.get_settings", lambda: settings)
    o = _orch(tmp_path)
    user = await o.get_or_create_user("local", None)
    user.bedrock = BedrockAccess(mode="assume_role", role_arn="arn:aws:iam::123456789012:role/Old", region="us-west-2")
    user.bedrock_verified_at = datetime.now(UTC)
    user.models_verified_at = datetime.now(UTC)
    await o.store.put_user(user)

    migrated = await o.get_or_create_user("local", None)
    assert migrated.bedrock == BedrockAccess(mode="default", region="us-east-1")
    assert migrated.bedrock_verified_at is None and migrated.models_verified_at is None
    assert (await o.store.get_user("local")).bedrock == migrated.bedrock

    updated = await o.update_bedrock("local", BedrockAccess(mode="assume_role", role_arn="arn:aws:iam::123456789012:role/Other", region="us-west-2"))
    assert updated.bedrock == migrated.bedrock


async def _wait_terminal(o: Orchestrator, job_id: str, timeout: float = 20) -> Job:
    for _ in range(int(timeout * 10)):
        job = await o.store.get_job(job_id)
        if job.status in (
            JobStatus.done,
            JobStatus.error,
            JobStatus.cancelled,
        ) and not await o.runner.is_running(job_id):
            return job
        await asyncio.sleep(0.1)
    raise AssertionError("job did not end")


async def test_user_methods_real(tmp_path):
    o = _orch(tmp_path)
    u = await o.get_or_create_user("local", None)
    assert u.bedrock is not None and u.bedrock.mode == "default"
    again = await o.get_or_create_user("local", "a@b.c")
    assert again.external_id == u.external_id and again.email == "a@b.c"

    res = await o.verify_bedrock("local")  # real STS GetCallerIdentity on the default chain
    assert res == {"ok": True}
    assert (await o._user("local")).bedrock_verified_at is not None

    res = await o.verify_models("local")  # one real Converse call per role
    assert res["ok"], res
    assert set(res["roles"]) == {"writer", "planner", "judge"}
    assert (await o._user("local")).models_verified_at is not None

    u = await o.update_models("local", default_model_roles())
    assert u.models_verified_at is None
    u = await o.update_bedrock("local", BedrockAccess(mode="default", region="us-east-1"))
    assert u.bedrock_verified_at is None


async def test_verify_models_exact_error_real(tmp_path):
    o = _orch(tmp_path)
    await o.get_or_create_user("bad", None)
    roles = default_model_roles().model_copy()
    roles.judge = roles.judge.model_copy(update={"model_id": "global.anthropic.claude-no-such-model"})
    await o.update_models("bad", roles)
    res = await o.verify_models("bad")
    assert res["ok"] is False and res["roles"]["writer"] == "ok"
    assert "claude-no-such-model" in res["roles"]["judge"] and "us-east-1" in res["roles"]["judge"]
    assert (await o._user("bad")).models_verified_at is None


async def test_create_job_412_rules(tmp_path):
    o = _orch(tmp_path)
    u = await o.get_or_create_user("u-aws", None)
    u.bedrock = None
    with pytest.raises(PreconditionFailed) as e:
        await o.create_job(SPEC, u)
    assert e.value.body == {"error": "connect AWS first"}
    u.bedrock = BedrockAccess(mode="assume_role", role_arn="arn:aws:iam::1:role/x", region="us-east-1")
    u.bedrock_verified_at = datetime.now(UTC)
    with pytest.raises(PreconditionFailed) as e:
        await o.create_job(SPEC, u)
    assert e.value.body == {"error": "verify models first"}
    assert await o.list_jobs("u-aws") == []


async def test_create_job_429_and_missing_stage_error(tmp_path):
    gate = asyncio.Event()
    o = _orch(tmp_path)
    real_run = o.run_job

    async def gated(job_id, mode):
        await gate.wait()
        await real_run(job_id, mode)

    o.runner.bind(gated, o.store)
    u = await o.get_or_create_user("local", None)
    u.bedrock_verified_at = u.models_verified_at = datetime.now(UTC)
    await o.store.put_user(u)

    job = await o.create_job(SPEC, u)
    assert job.owner_id == "local" and job.models == u.models and job.bedrock == u.bedrock
    with pytest.raises(RunnerBusy):
        await o.create_job(SPEC, u)
    assert [j.id for j in await o.list_jobs("local")] == [job.id]  # nothing saved on 429

    gate.set()
    done = await _wait_terminal(o, job.id)
    assert done.status is JobStatus.error
    # G1's fetch_documents is merged, so the job fails on the made-up upload id, never hangs
    assert done.error == "UploadNotFound: upload 'u1' not found"
    types = [e.type for e in await o.events.read_after(job.id, 0)]
    assert types[:2] == ["job.status", "stage.progress"] and types[-1] == "error"
    assert done.heartbeat_at is not None


async def test_cancel_without_worker_and_watchdog(tmp_path):
    o = _orch(tmp_path)
    now = datetime.now(UTC)
    job = Job(
        id="j-cancel",
        spec=SPEC,
        owner_id="local",
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )
    await o.store.put_job(job)
    out = await o.cancel(job.id)
    assert out.status is JobStatus.cancelled
    assert (await o.store.get_control(job.id)).state == "cancel"
    assert [e.data["status"] for e in await o.events.read_after(job.id, 0)] == ["cancelled"]

    old = now - timedelta(seconds=600)
    stale = Job(
        id="j-stale",
        spec=SPEC,
        owner_id="local",
        models=default_model_roles(),
        created_at=old,
        updated_at=old,
    )
    stale.status = JobStatus.building
    await o.store.put_job(stale)
    got = await o.get_job(stale.id)
    assert got.status is JobStatus.error and got.error.startswith("worker stopped: ")
    await o.get_job(stale.id)  # second check: no second event
    evs = await o.events.read_after(stale.id, 0)
    assert [e.type for e in evs] == ["error"]

    with pytest.raises(JobRunning):
        await o.approve_plan(stale.id, None)  # terminal job


async def test_subscribe_replays_after_last_event_id(tmp_path):
    o = _orch(tmp_path)
    now = datetime.now(UTC)
    job = Job(
        id="j-sub", spec=SPEC, owner_id="local", models=default_model_roles(), created_at=now, updated_at=now
    )
    await o.store.put_job(job)
    for i in range(4):
        await o.events.append(job.id, "log", {"level": "info", "message": str(i)})
    got = []
    async for ev in o.subscribe(job.id, 2):
        got.append(ev.id)
        if ev.id == 4:
            break
    assert got == [3, 4]


async def test_spot_check_409_when_running(tmp_path):
    o = _orch(tmp_path)
    now = datetime.now(UTC)
    job = Job(
        id="j-run", spec=SPEC, owner_id="local", models=default_model_roles(), created_at=now, updated_at=now
    )
    job.status = JobStatus.building
    await o.store.put_job(job)
    with pytest.raises(JobRunning):
        await o.spot_check(job.id, "r1", True)
    with pytest.raises(JobRunning):
        await o.export(job.id, "openai-chat", ["jsonl"])


def test_stage_lookup_names_owner(monkeypatch):
    monkeypatch.setitem(
        __import__("bob.orchestrator", fromlist=["_STAGES"])._STAGES, "generate", ("missing_a3_stage",)
    )
    with pytest.raises(RuntimeError, match=r"generate \(A3\)"):
        stage("generate")


def test_load_seeds():
    jl = b'{"messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]}\n{"user": "q2", "assistant": "a2"}\n'
    assert len(load_seeds(jl, "s.jsonl")) == 2
    assert load_seeds(b"user,assistant\nq,a\n", "s.csv")[0][1].content == "a"


async def _finished_upload_job(o: Orchestrator) -> Job:
    """A done job over two real smoke uploads, with its fetched documents saved like _ingest does."""
    from pathlib import Path

    from bob.connectors import fetch_documents
    from bob.connectors.upload import save_uploads
    from bob.core.models import Axis, Cell, Plan

    smoke = Path(__file__).resolve().parents[2] / "demo" / "smoke"
    saved = await save_uploads(
        [(n, (smoke / n).read_bytes()) for n in ("billing.md", "rate-limits.md")], owner_id="local"
    )
    u = await o.get_or_create_user("local", None)
    now = datetime.now(UTC)
    spec = JobSpec(goal="support bot", sources=[SourceSpec(kind="upload", upload_ids=[f.id for f in saved])])
    cell = Cell(id="c1", coords={"topic": "Billing", "case_type": "answerable"}, target=5, kept=5)
    plan = Plan(
        goal="support bot",
        system_prompt="You answer billing questions.",
        axes=[Axis(name="topic", values=["Billing"]), Axis(name="case_type", values=["answerable"])],
        cells=[cell],
        target_rows=5,
        est_cost_usd=0.1,
    )
    job = Job(
        id=f"rs{now.strftime('%H%M%S%f')}",
        spec=spec,
        owner_id=u.id,
        models=u.models,
        status=JobStatus.done,
        plan=plan,
        created_at=now,
        updated_at=now,
    )

    async def progress(done: int, total: int, detail: str) -> None:
        return None

    docs = await fetch_documents(spec.sources[0], job.id, progress, user_id=u.id)
    await o._save_docs(job.id, docs)
    await o.store.put_job(job)
    return job


async def test_resync_with_no_source_changes_is_done_at_once():
    o = Orchestrator(runner=LocalRunner(max_workers=2, max_active_per_user=1))
    job = await _finished_upload_job(o)
    assert len(await o._load_docs(job.id)) == 2

    started = await o.resync(job.id)
    assert started.status is JobStatus.ingesting
    with pytest.raises(JobRunning):  # not done any more: a second resync is refused
        await o.resync(job.id)
    done = await _wait_terminal(o, job.id)
    assert done.status is JobStatus.done and done.stage_detail == "no changes in the sources"
    assert done.error is None and done.plan == job.plan
    events = await o.events.read_after(job.id, 0)
    statuses = [e.data["status"] for e in events if e.type == "job.status"]
    assert statuses[0] == "ingesting" and statuses[-1] == "done"
    assert events[-1].type == "done"
    logs = [e.data["message"] for e in events if e.type == "log"]
    assert "resync: 0 added, 0 changed, 0 removed" in logs


def _report():
    from bob.core.models import Report

    return Report(
        coverage=[],
        mix_coverage={},
        pass_rate_by_check={},
        reject_reasons={},
        duplicates_removed=0,
        judge_rate=0.0,
        judge_agreement=None,
        spot_check={},
        sample_row_ids=[],
        token_stats={},
        rounds=[],
    )


async def test_resync_guards():
    o = Orchestrator(runner=LocalRunner(max_workers=2, max_active_per_user=1))
    job = await _finished_upload_job(o)
    # error / cancelled before any report: the first run never finished, nothing to re-sync
    for status in (JobStatus.error, JobStatus.cancelled, JobStatus.building):
        await o.store.put_job(job.model_copy(update={"status": status, "heartbeat_at": datetime.now(UTC)}))
        with pytest.raises(JobRunning, match="only a finished job"):
            await o.resync(job.id)
    await o.store.put_job(job.model_copy(update={"plan": None}))
    with pytest.raises(JobRunning, match="no plan"):
        await o.resync(job.id)


async def test_resync_retries_after_a_failed_resync_and_ignores_a_leftover_cancel():
    o = Orchestrator(runner=LocalRunner(max_workers=2, max_active_per_user=1))
    job = await _finished_upload_job(o)
    # a failed resync left the job in error (the first run's report is still there),
    # and a Cancel pressed as the first run ended left the control flag on "cancel"
    failed = job.model_copy(
        update={"status": JobStatus.error, "error": "Firecrawl: down", "report": _report()}
    )
    await o.store.put_job(failed)
    await o.store.set_control(job.id, "cancel")
    await o.resync(job.id)
    done = await _wait_terminal(o, job.id)
    assert done.status is JobStatus.done and done.stage_detail == "no changes in the sources"
    assert done.error is None


async def test_resync_puts_the_job_back_when_no_worker_starts():
    class NoStart(LocalRunner):
        async def start(self, job_id, mode):
            raise RuntimeError("no worker")

    o = Orchestrator(runner=NoStart(max_workers=2, max_active_per_user=1))
    job = await _finished_upload_job(o)
    with pytest.raises(RuntimeError, match="no worker"):
        await o.resync(job.id)
    back = await o.store.get_job(job.id)
    assert back.status is JobStatus.done and back.stage_detail == job.stage_detail
    statuses = [e.data["status"] for e in await o.events.read_after(job.id, 0) if e.type == "job.status"]
    assert statuses == ["ingesting", "done"]
