"""LocalStore, LocalEventLog, JobEmitter and LocalRunner on real disk (tmp runs_dir)."""

import asyncio
from datetime import UTC, datetime

import pytest

from bob.config import default_bedrock_access, default_model_roles
from bob.core.events import JobEmitter, LocalEventLog
from bob.core.models import Job, JobSpec, JobStatus, Plan, Row, UserProfile
from bob.core.runner import LocalRunner, RunnerBusy
from bob.core.store import LocalStore


def _job(job_id: str, owner: str = "local") -> Job:
    now = datetime.now(UTC)
    return Job(
        id=job_id,
        spec=JobSpec(goal="g", sources=[]),
        owner_id=owner,
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )


def _row(job_id: str, rid: str, verdict="kept", cell="c1") -> Row:
    return Row(
        id=rid,
        job_id=job_id,
        cell_id=cell,
        coords={"topic": "t"},
        case_type="answerable",
        round=1,
        messages=[],
        spans=[],
        checks=[],
        confidence=0.9,
        verdict=verdict,
        cost_usd=0.0,
        created_at=datetime.now(UTC),
    )


async def test_store_persists_and_reloads(tmp_path):
    s = LocalStore(tmp_path)
    await s.put_job(_job("j1"))
    await s.put_job(_job("j2", owner="other"))
    await s.put_rows("j1", [_row("j1", "r1"), _row("j1", "r2", "rejected", "c2")])
    r1 = _row("j1", "r1")
    r1.spot_check = True
    await s.put_rows("j1", [r1])
    plan = Plan(goal="g", system_prompt="s", axes=[], cells=[], target_rows=1, est_cost_usd=0)
    await s.set_control("j1", "approved", plan)
    await s.set_control("j1", "cancel")
    now = datetime.now(UTC)
    user = UserProfile(id="sub|x/y", external_id="e", models=default_model_roles(), created_at=now)
    await s.put_user(user)

    s2 = LocalStore(tmp_path)  # restart
    assert [j.id for j in await s2.list_jobs("local")] == ["j1"]
    total, rows = await s2.list_rows("j1", verdict="kept")
    assert total == 1 and rows[0].spot_check is True
    assert (await s2.list_rows("j1", cell_id="c2"))[0] == 1
    ctl = await s2.get_control("j1")
    assert ctl.state == "cancel" and ctl.plan is not None  # cancel keeps the approved plan
    assert (await s2.get_user("sub|x/y")).external_id == "e"
    assert await s2.get_user("nobody") is None
    with pytest.raises(KeyError):
        await s2.get_job("missing")
    with pytest.raises(ValueError):
        s2.job_dir("../x")


async def test_put_job_if_status(tmp_path):
    s = LocalStore(tmp_path)
    job = _job("j1")
    await s.put_job(job)
    err = job.model_copy(update={"status": JobStatus.error})
    assert await s.put_job_if_status(err, JobStatus.created)
    assert not await s.put_job_if_status(err, JobStatus.created)  # second writer loses
    assert (await s.get_job("j1")).status is JobStatus.error


async def test_events_persist_replay_and_live(tmp_path):
    log = LocalEventLog(tmp_path)
    for i in range(3):
        assert await log.append("j1", "log", {"i": i}) == i + 1
    log2 = LocalEventLog(tmp_path)  # restart: reload from events.jsonl
    assert [e.id for e in await log2.read_after("j1", 1)] == [2, 3]

    got = []

    async def reader():
        async for ev in log2.subscribe("j1", 2):
            got.append(ev.id)
            if ev.id == 5:
                return

    t = asyncio.create_task(reader())
    await asyncio.sleep(0.05)
    await log2.append("j1", "log", {"i": 3})
    await log2.append("j1", "log", {"i": 4})
    await asyncio.wait_for(t, 2)
    assert got == [3, 4, 5]


async def test_emitter_throttles_and_coalesces(tmp_path):
    log = LocalEventLog(tmp_path)
    em = JobEmitter(log, "j1")
    for i in range(20):
        await em.emit("cell.update", {"cell_id": "a", "kept": i})
        await em.emit("counts", {"kept": i})
    await em.emit("row", {"id": "r"})  # not throttled
    await asyncio.sleep(0.6)
    await em.flush()
    evs = await log.read_after("j1", 0)
    cells = [e.data["kept"] for e in evs if e.type == "cell.update"]
    counts = [e.data["kept"] for e in evs if e.type == "counts"]
    assert cells[0] == 0 and cells[-1] == 19 and len(cells) <= 3
    assert counts[0] == 0 and counts[-1] == 19 and len(counts) <= 3
    assert sum(1 for e in evs if e.type == "row") == 1


async def test_runner_capacity_and_stop(tmp_path):
    store = LocalStore(tmp_path)
    started = asyncio.Event()

    async def run_job(job_id, mode):
        started.set()
        await asyncio.sleep(30)

    runner = LocalRunner(max_workers=2, max_active_per_user=1)
    runner.bind(run_job, store)
    for jid, owner in (("a", "u1"), ("b", "u1"), ("c", "u2"), ("d", "u3")):
        await store.put_job(_job(jid, owner))
    await runner.start("a", "create")
    await started.wait()
    assert await runner.is_running("a")
    with pytest.raises(RunnerBusy):
        await runner.check_capacity("u1")  # per-user limit
    with pytest.raises(RunnerBusy):
        await runner.start("b", "create")
    await runner.start("c", "create")
    with pytest.raises(RunnerBusy):
        await runner.check_capacity("u3")  # max_workers
    await runner.stop("a")
    assert not await runner.is_running("a")
    assert runner.stopped_reason("a") == "worker task cancelled"
    await runner.stop("c")
    await runner.check_capacity("u1")
    assert default_bedrock_access().region
