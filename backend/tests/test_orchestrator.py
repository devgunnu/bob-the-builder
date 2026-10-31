"""Orchestrator on local backends (tmp runs_dir) with real Bedrock / STS calls for the verify methods.

A2/A3/A4/G1 stage modules are not on this branch yet: the job tests check the real error path
(a missing stage ends the job in `error` with the module name, never a hang).
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
    assert "fetch_documents" in done.error and "G1" in done.error
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
