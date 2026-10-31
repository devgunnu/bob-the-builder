"""Job state machine; the only backend API the web layer calls (CONTRACTS sections 6, 7, 8, 14). Owner: A1.

Errors for the routes (G1): `PreconditionFailed` -> HTTP 412 (`.body`), `RunnerBusy` (core/runner.py) ->
HTTP 429 `{"error": "too many running jobs"}`, `JobRunning` -> HTTP 409 `{"error": "job is running"}`,
`KeyError` -> HTTP 404.

Stage functions of A2, A3, A4 and G1 are imported lazily at first use by their CONTRACTS section 3 / 7
names, so this module imports without them. A missing stage ends the job in `error` with the module name.
`run_job` sets `bob.llm.client.CURRENT_JOB`, so stage functions without a `job` parameter can call
`get_llm(current_job(), role)`.
"""

from __future__ import annotations

import asyncio
import csv
import importlib
import inspect
import io
import json
import math
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from bob.config import default_bedrock_access, default_model_roles, get_settings, settings_for
from bob.core import ledger
from bob.core.backends import get_blobs, get_events, get_runner, get_store
from bob.core.blobs import Blobs
from bob.core.events import EventLog, JobEmitter
from bob.core.models import (
    TERMINAL_STATUSES,
    BedrockAccess,
    Cell,
    Chunk,
    Document,
    DPOPair,
    Event,
    GenContext,
    Job,
    JobSpec,
    JobStatus,
    Message,
    ModelRoles,
    Plan,
    Report,
    Row,
    UserProfile,
)
from bob.core.runner import LocalRunner, Runner, RunnerBusy
from bob.core.store import Store

__all__ = ["JobRunning", "Orchestrator", "PreconditionFailed", "RunnerBusy", "load_seeds"]


# ---------- errors for the routes ----------
class PreconditionFailed(Exception):
    """HTTP 412. `body` = {"error": "connect AWS first"} or {"error": "verify models first"}."""

    status_code = 412

    def __init__(self, message: str):
        super().__init__(message)
        self.body = {"error": message}


class JobRunning(Exception):
    """HTTP 409 {"error": "job is running"} (spot_check / export while a worker runs)."""

    status_code = 409

    def __init__(self, message: str = "job is running"):
        super().__init__(message)
        self.body = {"error": message}


class _Cancelled(Exception):
    pass


# ---------- lazy stage imports (A2, A3, A4, G1) ----------
_STAGES: dict[str, tuple[str, ...]] = {
    # A2
    "chunk_documents": ("bob.pipeline.chunk",),
    "heuristic_filter": ("bob.pipeline.filters",),
    "dedup_chunks": ("bob.pipeline.embed", "bob.pipeline.filters", "bob.pipeline.chunk"),
    "triage": ("bob.pipeline.triage",),
    "build_topics": ("bob.pipeline.topics",),
    "build_evidence": ("bob.pipeline.evidence",),
    "Retriever": ("bob.pipeline.evidence",),
    # A3
    "propose_plan": ("bob.pipeline.planner",),
    "allocate_targets": ("bob.pipeline.planner", "bob.pipeline.gaps"),
    "generate": ("bob.pipeline.generate",),
    "plan_gap_round": ("bob.pipeline.gaps",),
    # A4
    "verify": ("bob.pipeline.verify",),
    "build_dpo_pairs": ("bob.pipeline.verify", "bob.pipeline.dpo"),
    "build_report": ("bob.pipeline.report",),
    "export": ("bob.export", "bob.export.presets", "bob.export.formats"),
    # G1
    "fetch_documents": ("bob.connectors",),
    "read_upload": ("bob.connectors.upload",),
}
_OWNER = {
    "chunk_documents": "A2",
    "heuristic_filter": "A2",
    "dedup_chunks": "A2",
    "triage": "A2",
    "build_topics": "A2",
    "build_evidence": "A2",
    "Retriever": "A2",
    "propose_plan": "A3",
    "allocate_targets": "A3",
    "generate": "A3",
    "plan_gap_round": "A3",
    "verify": "A4",
    "build_dpo_pairs": "A4",
    "build_report": "A4",
    "export": "A4",
    "fetch_documents": "G1",
    "read_upload": "G1",
}


def stage(name: str) -> Any:
    """The stage function `name` from its owner's module. RuntimeError names the missing module."""
    errors = []
    for mod in _STAGES[name]:
        try:
            m = importlib.import_module(mod)
        except ImportError as e:
            errors.append(f"{mod}: {e}")
            continue
        fn = getattr(m, name, None)
        if fn is not None:
            return fn
        errors.append(f"{mod} has no {name}")
    raise RuntimeError(f"stage {name} ({_OWNER[name]}) is not available: {'; '.join(errors)}")


async def _maybe_await(v: Any) -> Any:
    return await v if inspect.isawaitable(v) else v


def _now() -> datetime:
    return datetime.now(UTC)


def _dt_age_s(ts: datetime) -> float:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (_now() - ts).total_seconds()


# ---------- per-run state (lives only inside run_job) ----------
@dataclass
class _Run:
    job: Job
    emit: JobEmitter
    store: Store
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    control_state: str | None = None
    approved_plan: Plan | None = None
    budget_hit: bool = False
    dirty: bool = False
    last_save: float = 0.0
    save_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def save(self, force: bool = False) -> None:
        """put_job on each status change (force) and at most every 2 s otherwise."""
        self.dirty = True
        if not force and time.monotonic() - self.last_save < 2.0:
            return
        async with self.save_lock:
            self.job.cost = ledger.summary(self.job.id)
            self.job.updated_at = _now()
            self.dirty = False
            self.last_save = time.monotonic()
            await self.store.put_job(self.job)

    async def status(self, status: JobStatus, detail: str = "") -> None:
        self.job.status = status
        self.job.stage_detail = detail
        await self.save(force=True)
        await self.emit.emit("job.status", {"status": status.value, "detail": detail})

    async def progress(self, stage_name: str, done: int, total: int, detail: str = "") -> None:
        self.job.stage_detail = detail or stage_name
        await self.emit.emit(
            "stage.progress", {"stage": stage_name, "done": done, "total": total, "detail": detail}
        )

    async def log(self, level: str, message: str) -> None:
        await self.emit.emit("log", {"level": level, "message": message})

    async def counts(self, **kw: int) -> None:
        for k, v in kw.items():
            self.job.counts[k] = v
        await self.emit.emit("counts", dict(self.job.counts))

    async def cost(self) -> None:
        self.job.cost = ledger.summary(self.job.id)
        await self.emit.emit("cost", self.job.cost.model_dump(mode="json"))

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise _Cancelled()


class Orchestrator:
    def __init__(
        self,
        store: Store | None = None,
        events: EventLog | None = None,
        blobs: Blobs | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.store = store or get_store()
        self.events = events or get_events()
        self.blobs = blobs or get_blobs()
        self.runner = runner or get_runner()
        if isinstance(self.runner, LocalRunner):
            self.runner.bind(self.run_job, self.store)

    # ======================================================================================
    # jobs
    # ======================================================================================
    async def create_job(self, spec: JobSpec, user: UserProfile) -> Job:
        """1. user.bedrock_verified_at not set -> 412 {"error": "connect AWS first"}; else models_verified_at
        not set -> 412 {"error": "verify models first"}.
        2. Capacity check before save: RunnerBusy -> route 429 {"error": "too many running jobs"}; nothing saved.
        3. Save Job (owner_id = user.id, bedrock = snapshot of user.bedrock,
           models = spec.options.models or user.models).
        4. Append job.status created + stage.progress {stage: "fetch", done: 0, total: 0,
           detail: "starting worker"}, then runner.start(id, "create"). Returns at once (< 1 s).
        Local mode (BOB_BEDROCK_AUTH=default): the first job of an unverified profile runs verify_bedrock
        and verify_models once (real calls on the default chain).
        """
        s = get_settings()
        if (
            s.bedrock_auth == "default"
            and user.bedrock is not None
            and user.bedrock.mode == "default"
            and (user.bedrock_verified_at is None or user.models_verified_at is None)
        ):
            if user.bedrock_verified_at is None:
                await self.verify_bedrock(user.id)
            if (await self._user(user.id)).models_verified_at is None:
                await self.verify_models(user.id)
            user = await self._user(user.id)
        if user.bedrock is None or user.bedrock_verified_at is None:
            raise PreconditionFailed("hosting AWS access unavailable" if s.env == "aws" and s.bedrock_auth == "default" else "connect AWS first")
        if user.models_verified_at is None:
            raise PreconditionFailed("hosting models unavailable" if s.env == "aws" and s.bedrock_auth == "default" else "verify models first")

        now = _now()
        job = Job(
            id=uuid.uuid4().hex[:12],
            spec=spec,
            owner_id=user.id,
            bedrock=user.bedrock.model_copy(deep=True),
            models=(spec.options.models or user.models).model_copy(deep=True),
            created_at=now,
            updated_at=now,
        )
        reserve = getattr(self.runner, "reserve", None)
        if reserve is not None:
            await reserve(job.id, user.id)  # atomically reserve AWS capacity before saving
        else:
            check = getattr(self.runner, "check_capacity", None)
            if check is not None:
                await check(user.id)
        try:
            await self.store.put_job(job)
            await self.events.append(job.id, "job.status", {"status": job.status.value, "detail": ""})
            await self.events.append(
                job.id,
                "stage.progress",
                {"stage": "fetch", "done": 0, "total": 0, "detail": "starting worker"},
            )
            await self.runner.start(job.id, "create")
        except RunnerBusy:
            job.status = JobStatus.error
            job.error = "too many running jobs"
            job.updated_at = _now()
            await self.store.put_job(job)
            await self.events.append(job.id, "error", {"message": job.error})
            raise
        except BaseException:
            if reserve is not None:
                await self.runner.release(job.id)
            raise
        return job

    async def run_job(self, job_id: str, mode: Literal["create", "resync"]) -> None:
        """The whole job body; both runners call it. ingest -> read -> plan -> wait for approval
        (poll store.get_control every BOB_CONTROL_POLL_S, up to BOB_APPROVAL_WAIT_MINUTES; build from
        Control.plan) -> build -> fill gaps -> DPO -> report -> export -> done. Writes Job.heartbeat_at every
        BOB_HEARTBEAT_S, also while it waits. Checks the cancel flag between stages and before each Writer
        call. Budget guard at 0.95 * budget_usd. Any stage exception -> status error + error event.
        """
        from bob.llm import credentials
        from bob.llm.client import CURRENT_JOB

        job = await self.store.get_job(job_id)
        if job.status in TERMINAL_STATUSES:
            return
        run = _Run(job=job, emit=JobEmitter(self.events, job_id), store=self.store)
        ledger.register_job(job)
        if job.cost.by_model:
            ledger.load(job_id, job.cost)
        token = CURRENT_JOB.set(job)
        job.heartbeat_at = _now()
        await run.save(force=True)
        monitor = asyncio.create_task(self._monitor(run), name=f"bob-monitor-{job_id}")
        body = asyncio.create_task(
            self._pipeline(run) if mode == "create" else self._resync_body(run), name=f"bob-body-{job_id}"
        )
        cancel_wait = asyncio.create_task(run.cancel.wait())
        try:
            await asyncio.wait({body, cancel_wait}, return_when=asyncio.FIRST_COMPLETED)
            if not body.done():  # cancel flag: stop the body now (cancel within 5 s)
                body.cancel()
                await asyncio.gather(body, return_exceptions=True)
                raise _Cancelled()
            body.result()
        except (_Cancelled, asyncio.CancelledError) as e:
            await run.emit.flush()
            await run.status(JobStatus.cancelled, "cancelled")
            if isinstance(e, asyncio.CancelledError):
                raise
        except Exception as e:  # any stage error: status error + error event, never a hang
            await run.emit.flush()
            job.error = f"{type(e).__name__}: {e}"
            await run.status(JobStatus.error, job.error[:500])
            await run.emit.emit("error", {"message": job.error})
        finally:
            for t in (monitor, cancel_wait, body):
                t.cancel()
            await asyncio.gather(monitor, cancel_wait, body, return_exceptions=True)
            await run.emit.flush()
            await run.save(force=True)
            CURRENT_JOB.reset(token)
            credentials.drop_job(job_id)

    async def _monitor(self, run: _Run) -> None:
        """Heartbeat every BOB_HEARTBEAT_S, control flag every BOB_CONTROL_POLL_S, flush dirty job state."""
        s = get_settings()
        last_hb = time.monotonic()
        while True:
            await asyncio.sleep(s.control_poll_s)
            try:
                ctl = await self.store.get_control(run.job.id)
                run.control_state = ctl.state
                if ctl.state == "approved":
                    run.approved_plan = ctl.plan
                elif ctl.state == "cancel":
                    run.cancel.set()
                if time.monotonic() - last_hb >= s.heartbeat_s:
                    last_hb = time.monotonic()
                    run.job.heartbeat_at = _now()
                    await run.save(force=True)
                elif run.dirty and time.monotonic() - run.last_save >= 2.0:
                    await run.save(force=True)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # a store hiccup must not kill the job
                await run.log("warn", f"monitor: {type(e).__name__}: {e}")

    # ---------- the pipeline ----------
    async def _pipeline(self, run: _Run) -> None:
        job = run.job
        eff = settings_for(job)

        # ingest
        await run.status(JobStatus.ingesting, "fetching sources")
        docs = await self._ingest(run)
        seeds = await self._seeds(run)
        run.check_cancel()

        # read
        await run.status(JobStatus.reading, "reading documents")
        chunks, topics, evidence, retriever = await self._read(run, docs)
        run.check_cancel()

        # plan
        await run.status(JobStatus.planning, "proposing the plan")
        await run.progress("plan", 0, 1, "planner")
        propose_plan = stage("propose_plan")
        plan = await propose_plan(
            job.spec.goal,
            list(topics.values()),
            seeds,
            job.spec.target_rows,
            job.spec.budget_usd,
            chunks=chunks,
        )
        job.plan = plan
        await run.progress("plan", 1, 1, "plan ready")
        await run.cost()
        await run.emit.emit("plan.ready", plan.model_dump(mode="json"))
        await run.status(JobStatus.awaiting_approval, "waiting for plan approval")

        plan = await self._wait_approval(run)
        run.check_cancel()

        # build
        ctx = GenContext(
            job=job,
            docs={d.id: d for d in docs},
            chunks=chunks,
            topics=topics,
            evidence=evidence,
            retriever=retriever,
            seeds=seeds,
            emit=run.emit.emit,
        )
        await self._build(run, ctx, plan, eff)

        # DPO
        pairs: list[DPOPair] = []
        if eff.dpo_mode != "off" and not run.budget_hit:
            run.check_cancel()
            kept = await self._all_rows(job.id, "kept")
            if kept:
                build_dpo_pairs = stage("build_dpo_pairs")
                await run.log("info", f"building DPO pairs ({eff.dpo_mode})")
                pairs = await build_dpo_pairs(kept, ctx)
                await self._save_pairs(job.id, pairs)
                await run.counts(dpo_pairs=len(pairs))
                await run.cost()
        elif run.budget_hit and eff.dpo_mode != "off":
            await run.log("warn", "budget guard: DPO pairs skipped")

        # report + export
        run.check_cancel()
        await run.status(JobStatus.reporting, "building the report")
        rows = await self._all_rows(job.id)
        build_report = stage("build_report")
        report = await asyncio.to_thread(build_report, job, rows)
        job.report = report
        await run.emit.emit("report.ready", report.model_dump(mode="json"))
        await run.progress("export", 0, 1, "exporting")
        # P0: the job preset and "full"; "dpo" too when DPO pairs exist (an extra preset failure only logs)
        files = await self._export_files(job, rows, pairs, job.spec.preset, job.spec.formats)
        extra = ["full"] + (["dpo"] if pairs else [])
        for preset in [p for p in extra if p != job.spec.preset]:
            try:
                files.update(await self._export_files(job, rows, pairs, preset, job.spec.formats))
            except Exception as e:
                await run.log("warn", f"export {preset}: {type(e).__name__}: {e}")
        job.files = files
        await run.progress("export", 1, 1, "exported")
        await run.emit.emit("files.ready", {"files": files})
        await run.cost()
        await run.emit.flush()
        await run.status(JobStatus.done, "done")
        await run.emit.emit("done", {"files": files})

    async def _resync_body(self, run: _Run) -> None:
        raise NotImplementedError("resync is P1 (needs G2 connectors/sync.py)")

    async def _ingest(self, run: _Run) -> list[Document]:
        job = run.job
        fetch_documents = stage("fetch_documents")
        docs: dict[str, Document] = {}
        n = len(job.spec.sources)
        for i, src in enumerate(job.spec.sources):

            async def progress(done: int, total: int, detail: str, _i: int = i) -> None:
                await run.progress("fetch", done, total, f"source {_i + 1}/{n}: {detail}")

            got = await fetch_documents(src, job.id, progress, user_id=job.owner_id)
            for d in got:
                docs[d.id] = d
            run.check_cancel()
        if not docs:
            raise RuntimeError("no documents were fetched from the sources")
        for d in docs.values():
            await self.blobs.put(
                f"runs/{job.id}/docs/{d.id}.json", d.model_dump_json().encode(), "application/json"
            )
        await run.progress("fetch", len(docs), len(docs), f"{len(docs)} documents")
        await run.counts(docs=len(docs))
        await run.cost()
        return list(docs.values())

    async def _seeds(self, run: _Run) -> list[list[Message]]:
        upload_id = run.job.spec.seed_upload_id
        if not upload_id:
            return []
        read_upload = stage("read_upload")
        seeds: list[list[Message]] = []
        for name, data in await read_upload(upload_id):
            seeds.extend(load_seeds(data, name))
        await run.log("info", f"{len(seeds)} seed examples loaded")
        return seeds

    async def _read(self, run: _Run, docs: list[Document]) -> tuple[dict, dict, Any, Any]:
        job = run.job
        chunk_documents = stage("chunk_documents")
        heuristic_filter = stage("heuristic_filter")
        dedup_chunks = stage("dedup_chunks")
        triage = stage("triage")
        build_topics = stage("build_topics")
        build_evidence = stage("build_evidence")
        retriever_cls = stage("Retriever")

        await run.progress("chunk", 0, len(docs), "chunking")
        chunks: list[Chunk] = await asyncio.to_thread(chunk_documents, docs)
        chunks = await asyncio.to_thread(heuristic_filter, chunks)
        chunks = await asyncio.to_thread(dedup_chunks, chunks)
        all_chunks = {c.id: c for c in chunks}
        kept = [c for c in chunks if c.kept]
        await run.progress("chunk", len(docs), len(docs), f"{len(chunks)} chunks, {len(kept)} kept")
        await run.counts(chunks=len(chunks), chunks_kept=len(kept))
        run.check_cancel()

        await run.progress("triage", 0, len(kept), "triage")
        triaged = await triage(kept)
        for c in triaged:
            all_chunks[c.id] = c
        kept = [c for c in triaged if c.kept]
        await run.progress("triage", len(triaged), len(triaged), f"{len(kept)} useful chunks")
        await run.counts(chunks_kept=len(kept))
        await run.cost()
        if not kept:
            raise RuntimeError("no useful chunks left after triage")
        run.check_cancel()

        await run.progress("topics", 0, 1, "topics")
        topics_list = await build_topics(kept, job.spec.goal)
        topics = {t.id: t for t in topics_list}
        await run.progress("topics", 1, 1, f"{len(topics)} topics")
        await run.counts(topics=len(topics))
        await run.cost()
        run.check_cancel()

        await run.progress("evidence", 0, 1, "evidence")
        evidence = await build_evidence(kept)
        await run.progress("evidence", 1, 1, f"{len(evidence.items)} evidence items")
        await run.counts(evidence=len(evidence.items))
        await run.cost()
        retriever = await asyncio.to_thread(retriever_cls, kept)

        lines = "".join(c.model_dump_json() + "\n" for c in all_chunks.values())
        await self.blobs.put(f"runs/{job.id}/chunks.jsonl", lines.encode(), "application/x-ndjson")
        return {c.id: c for c in kept}, topics, evidence, retriever

    async def _wait_approval(self, run: _Run) -> Plan:
        s = get_settings()
        deadline = time.monotonic() + s.approval_wait_minutes * 60
        while time.monotonic() < deadline:
            ctl = await self.store.get_control(run.job.id)
            if ctl.state == "cancel":
                raise _Cancelled()
            if ctl.state == "approved":
                plan = ctl.plan or run.job.plan
                if plan is None:
                    raise RuntimeError("approved without a plan")
                return plan
            await asyncio.sleep(s.control_poll_s)
        raise TimeoutError(f"plan approval timed out after {s.approval_wait_minutes} minutes")

    async def _build(self, run: _Run, ctx: GenContext, plan: Plan, eff: Any) -> None:
        job = run.job
        allocate_targets = stage("allocate_targets")
        plan = await asyncio.to_thread(allocate_targets, plan)
        job.plan = plan
        ctx.job = job
        await run.status(JobStatus.building, "round 1")

        cells = [c for c in plan.cells if c.enabled]
        work = [(c, math.ceil(c.target * eff.overgen)) for c in cells]
        job.round = 1
        await run.emit.emit(
            "round",
            {
                "n": 1,
                "reason": "initial",
                "cells": [c.id for c, _ in work],
                "planned": sum(n for _, n in work),
            },
        )
        await self._round(run, ctx, work, eff)

        plan_gap_round = None
        for r in range(2, max(1, eff.max_rounds) + 1):
            if run.budget_hit:
                break
            run.check_cancel()
            if plan_gap_round is None:
                plan_gap_round = stage("plan_gap_round")
            gaps = await asyncio.to_thread(plan_gap_round, job, job.plan.cells)
            gaps = [(c, n) for c, n in gaps if n > 0]
            if not gaps:
                await run.log("info", f"targets met after round {r - 1}")
                break
            # plan_gap_round may return copies: use the cells inside job.plan so counters stay in one place
            by_id = {c.id: c for c in job.plan.cells}
            work = [(by_id.get(c.id, c), n) for c, n in gaps]
            job.round = r
            await run.status(JobStatus.filling_gaps, f"round {r}")
            await run.emit.emit(
                "round",
                {
                    "n": r,
                    "reason": "gaps",
                    "cells": [c.id for c, _ in work],
                    "planned": sum(n for _, n in work),
                },
            )
            await self._round(run, ctx, work, eff)

    async def _round(self, run: _Run, ctx: GenContext, work: list[tuple[Cell, int]], eff: Any) -> None:
        sem = asyncio.Semaphore(max(1, eff.writer_concurrency))

        async def one(cell: Cell, n: int) -> None:
            async with sem:
                try:
                    await self._fill_cell(run, ctx, cell, n, eff)
                except (_Cancelled, asyncio.CancelledError):
                    raise
                except Exception as e:  # one cell failure never kills the job
                    await run.log("warn", f"cell {cell.id} {cell.coords}: {type(e).__name__}: {e}")

        await asyncio.gather(*(one(c, n) for c, n in work))

    def _budget_ok(self, run: _Run) -> bool:
        return ledger.total_usd(run.job.id) < 0.95 * run.job.spec.budget_usd

    async def _fill_cell(self, run: _Run, ctx: GenContext, cell: Cell, n: int, eff: Any) -> None:
        generate = stage("generate")
        verify = stage("verify")
        job = run.job
        remaining = n
        while remaining > 0:
            run.check_cancel()
            if run.budget_hit or not self._budget_ok(run):
                if not run.budget_hit:
                    run.budget_hit = True
                    await run.log(
                        "warn",
                        f"budget guard: ${ledger.total_usd(job.id):.4f} >= 95% of ${job.spec.budget_usd:.2f}; "
                        "no new Writer calls",
                    )
                return
            batch = min(max(1, eff.writer_batch), remaining)
            cands = await generate(cell, job.plan, ctx, batch)
            remaining -= batch
            if not cands:
                await run.log("warn", f"cell {cell.id}: the Writer returned no candidates")
                continue
            rows: list[Row] = await verify(cands, ctx)
            await self.store.put_rows(job.id, rows)
            await self._account(run, cell, len(cands), rows)

    async def _account(self, run: _Run, cell: Cell, n_cands: int, rows: list[Row]) -> None:
        job = run.job
        cell.generated += n_cands
        kept = sum(1 for r in rows if r.verdict == "kept")
        cell.kept += kept
        mix_axes = {axis.name for axis in job.plan.axes if axis.role == "mix"}
        for row in rows:
            if row.verdict == "kept":
                for axis in mix_axes:
                    if axis in row.coords:
                        counts = cell.mix_kept.setdefault(axis, {})
                        value = row.coords[axis]
                        counts[value] = counts.get(value, 0) + 1
        cell.rejected += len(rows) - kept
        cell.judged += sum(1 for r in rows if r.routed_to_judge or r.audited)
        c = job.counts
        c["candidates"] = c.get("candidates", 0) + n_cands
        c["kept"] = c.get("kept", 0) + kept
        c["rejected"] = c.get("rejected", 0) + len(rows) - kept
        c["judged"] = c.get("judged", 0) + sum(1 for r in rows if r.routed_to_judge or r.audited)
        c["duplicates"] = c.get("duplicates", 0) + sum(
            1
            for r in rows
            if r.verdict == "rejected" and any(not ch.passed and "dup" in ch.name.lower() for ch in r.checks)
        )
        for r in rows:
            user = next((m.content for m in r.messages if m.role == "user"), "")
            await run.emit.emit(
                "row",
                {
                    "id": r.id,
                    "cell_id": r.cell_id,
                    "verdict": r.verdict,
                    "reject_reason": r.reject_reason,
                    "case_type": r.case_type,
                    "user_preview": user[:160],
                    "confidence": r.confidence,
                    "routed_to_judge": r.routed_to_judge,
                },
            )
        await run.emit.emit(
            "cell.update",
            {
                "cell_id": cell.id,
                "generated": cell.generated,
                "kept": cell.kept,
                "rejected": cell.rejected,
                "judged": cell.judged,
                "target": cell.target,
            },
        )
        await run.counts()
        await run.cost()
        await run.save()

    # ---------- rows, pairs, export helpers ----------
    async def _all_rows(self, job_id: str, verdict: Literal["kept", "rejected"] | None = None) -> list[Row]:
        out: list[Row] = []
        offset = 0
        while True:
            total, page = await self.store.list_rows(job_id, verdict=verdict, offset=offset, limit=1000)
            out.extend(page)
            offset += len(page)
            if not page or offset >= total:
                return out

    async def _save_pairs(self, job_id: str, pairs: list[DPOPair]) -> None:
        data = "".join(p.model_dump_json() + "\n" for p in pairs).encode()
        await self.blobs.put(f"runs/{job_id}/dpo_pairs.jsonl", data, "application/x-ndjson")

    async def _load_pairs(self, job_id: str) -> list[DPOPair]:
        key = f"runs/{job_id}/dpo_pairs.jsonl"
        if not await self.blobs.exists(key):
            return []
        text = (await self.blobs.get(key)).decode("utf-8")
        return [DPOPair.model_validate_json(line) for line in text.splitlines() if line.strip()]

    async def _export_files(
        self, job: Job, rows: list[Row], pairs: list[DPOPair], preset: str, formats: list[str]
    ) -> dict[str, str]:
        export = stage("export")
        out_dir = Path(get_settings().runs_dir).resolve() / job.id / "export"
        out_dir.mkdir(parents=True, exist_ok=True)
        files = await asyncio.to_thread(export, job, rows, pairs, preset, formats, out_dir)
        await self.blobs.upload_tree(out_dir, f"runs/{job.id}/export")
        return dict(files)

    async def _require_idle(self, job: Job) -> None:
        if job.status not in TERMINAL_STATUSES or await self.runner.is_running(job.id):
            raise JobRunning()

    # ---------- control ----------
    async def approve_plan(self, job_id: str, plan: Plan) -> Job:
        """store.set_control(id, "approved", plan); returns the Job."""
        job = await self.get_job(job_id)
        if job.status in TERMINAL_STATUSES:
            raise JobRunning(f"job is {job.status.value}")
        await self.store.set_control(job_id, "approved", plan)
        return await self.store.get_job(job_id)

    async def cancel(self, job_id: str) -> Job:
        """store.set_control(id, "cancel"). If runner.is_running(id) is false: set status cancelled and emit
        the event (the API writes events only when no worker runs). aws runner stop() after 10 s if needed.
        """
        job = await self.store.get_job(job_id)
        if job.status in TERMINAL_STATUSES:
            return job
        await self.store.set_control(job_id, "cancel")
        if not await self.runner.is_running(job_id):
            prev = job.status
            job.status = JobStatus.cancelled
            job.stage_detail = "cancelled"
            job.updated_at = _now()
            if await self._put_if_status(job, prev):
                await self.events.append(job_id, "job.status", {"status": "cancelled", "detail": "cancelled"})
            return await self.store.get_job(job_id)
        return job

    # ---------- getters (async: DynamoDB / S3 in aws mode) ----------
    async def get_job(self, job_id: str) -> Job:
        """Reads the store and runs the watchdog: not terminal, heartbeat_at (or created_at) older than
        BOB_HEARTBEAT_TIMEOUT_S, runner.is_running false -> status error,
        error = "worker stopped: <stoppedReason>", one error event (conditional update).
        """
        job = await self.store.get_job(job_id)
        return await self._watchdog(job)

    async def _put_if_status(self, job: Job, expected: JobStatus) -> bool:
        cond = getattr(self.store, "put_job_if_status", None)
        if cond is not None:
            return bool(await cond(job, expected))
        cur = await self.store.get_job(job.id)
        if cur.status != expected:
            return False
        await self.store.put_job(job)
        return True

    async def _watchdog(self, job: Job) -> Job:
        if job.status in TERMINAL_STATUSES:
            return job
        ref = job.heartbeat_at or job.created_at
        if _dt_age_s(ref) <= get_settings().heartbeat_timeout_s:
            return job
        if await self.runner.is_running(job.id):
            return job
        reason_fn = getattr(self.runner, "stopped_reason", None)
        reason = await _maybe_await(reason_fn(job.id)) if reason_fn else None
        reason = reason or f"no heartbeat for {get_settings().heartbeat_timeout_s} s"
        prev = job.status
        new = job.model_copy(deep=True)
        new.status = JobStatus.error
        new.error = f"worker stopped: {reason}"
        new.stage_detail = new.error
        new.updated_at = _now()
        if await self._put_if_status(new, prev):
            await self.events.append(job.id, "error", {"message": new.error})
            return new
        return await self.store.get_job(job.id)

    async def list_jobs(self, owner_id: str) -> list[Job]:
        """Only this user's jobs."""
        return await self.store.list_jobs(owner_id)

    async def list_rows(
        self,
        job_id: str,
        verdict: Literal["kept", "rejected"] | None = None,
        cell_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[Row]]:
        """(total, page) from the store."""
        return await self.store.list_rows(
            job_id, verdict=verdict, cell_id=cell_id, offset=offset, limit=limit
        )

    async def get_row(self, job_id: str, row_id: str) -> Row:
        return await self.store.get_row(job_id, row_id)

    async def spot_check(self, job_id: str, row_id: str, ok: bool) -> Report:
        """Sets Row.spot_check and returns a rebuilt Report. Only when status is done/cancelled/error and no
        worker runs (else JobRunning -> 409 {"error": "job is running"}). No events. < 25 s.
        """
        job = await self.store.get_job(job_id)
        await self._require_idle(job)
        row = await self.store.get_row(job_id, row_id)
        row.spot_check = ok
        await self.store.put_rows(job_id, [row])
        rows = await self._all_rows(job_id)
        build_report = stage("build_report")
        report = await asyncio.to_thread(build_report, job, rows)
        job.report = report
        job.updated_at = _now()
        await self.store.put_job(job)
        return report

    async def export(self, job_id: str, preset: str, formats: list[str]) -> dict[str, str]:
        """Re-export with A4 export(); adds the files to Job.files. Same 409 rule as spot_check. No events."""
        job = await self.store.get_job(job_id)
        await self._require_idle(job)
        rows = await self._all_rows(job_id)
        pairs = await self._load_pairs(job_id)
        files = await self._export_files(job, rows, pairs, preset, formats)
        job.files = {**job.files, **files}
        job.updated_at = _now()
        await self.store.put_job(job)
        return files

    async def resync(self, job_id: str) -> Job:
        """P1: runner.start(id, "resync") (CONTRACTS section 10). Needs G2 connectors/sync.py."""
        raise NotImplementedError("resync is P1 (needs G2 connectors/sync.py)")

    async def subscribe(self, job_id: str, last_event_id: int | None) -> AsyncIterator[Event]:
        """EventLog.subscribe with replay from last_event_id; runs the watchdog in the SSE loop.
        Call it without await: `async for ev in orch.subscribe(job_id, last_id)`."""
        await self.get_job(job_id)  # KeyError for a missing job; runs the watchdog once
        it = self.events.subscribe(job_id, last_event_id).__aiter__()
        period = max(5.0, min(15.0, get_settings().heartbeat_timeout_s / 3))
        nxt: asyncio.Future = asyncio.ensure_future(it.__anext__())
        try:
            while True:
                done, _ = await asyncio.wait({nxt}, timeout=period)
                if nxt in done:
                    try:
                        ev = nxt.result()
                    except StopAsyncIteration:
                        return
                    yield ev
                    nxt = asyncio.ensure_future(it.__anext__())
                else:
                    await self.get_job(job_id)  # watchdog; its error event arrives through the log
        finally:
            nxt.cancel()
            aclose = getattr(it, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except (RuntimeError, asyncio.CancelledError):
                    pass

    # ======================================================================================
    # users + Bedrock access (section 14)
    # ======================================================================================
    async def _user(self, user_id: str) -> UserProfile:
        u = await self.store.get_user(user_id)
        if u is None:
            raise KeyError(user_id)
        return u

    async def get_or_create_user(self, user_id: str, email: str | None) -> UserProfile:
        """New profile: random external_id (uuid4, never changed), default models from config; local mode
        (BOB_BEDROCK_AUTH=default) also gets a default BedrockAccess.
        """
        u = await self.store.get_user(user_id)
        if u is not None:
            s = get_settings()
            if s.bedrock_auth == "default" and u.bedrock != default_bedrock_access(s):
                u.bedrock = default_bedrock_access(s)
                u.bedrock_verified_at = None
                u.models_verified_at = None
                await self.store.put_user(u)
            if email and u.email != email:
                u.email = email
                await self.store.put_user(u)
            return u
        s = get_settings()
        u = UserProfile(
            id=user_id,
            email=email,
            external_id=str(uuid.uuid4()),
            bedrock=default_bedrock_access(s) if s.bedrock_auth == "default" else None,
            models=default_model_roles(s),
            created_at=_now(),
        )
        await self.store.put_user(u)
        return u

    async def update_bedrock(self, user_id: str, access: BedrockAccess) -> UserProfile:
        """Saves the access and clears bedrock_verified_at. aws mode forces mode=assume_role; the external
        id is always the profile's own external_id."""
        u = await self._user(user_id)
        access = access.model_copy()
        if get_settings().env == "aws" and get_settings().bedrock_auth == "default":
            access = default_bedrock_access()
        elif get_settings().env == "aws":
            access.mode = "assume_role"
        if access.mode == "assume_role":
            access.external_id = u.external_id
        u.bedrock = access
        u.bedrock_verified_at = None
        await self.store.put_user(u)
        return u

    async def verify_bedrock(self, user_id: str) -> dict:
        """AWS access only: sts:AssumeRole (< 25 s). Sets bedrock_verified_at on success; returns
        {ok, error?} with the exact STS error on failure.
        """
        from bob.llm.credentials import verify_access

        u = await self._user(user_id)
        if u.bedrock is None:
            return {"ok": False, "error": "no AWS access saved: PUT /me/aws first"}
        if get_settings().env == "aws" and u.bedrock.mode != get_settings().bedrock_auth:
            return {"ok": False, "error": f"AWS mode needs mode={get_settings().bedrock_auth}"}
        try:
            res = await asyncio.wait_for(asyncio.to_thread(verify_access, u.bedrock, user_id), timeout=20)
        except TimeoutError:
            res = {"ok": False, "error": f"STS did not answer in 20 s (region {u.bedrock.region})"}
        if res.get("ok"):
            u.bedrock_verified_at = _now()
            await self.store.put_user(u)
            return {"ok": True}
        return {"ok": False, "error": res.get("error", "unknown error")}

    # ---------- models (D33) ----------
    async def update_models(
        self, user_id: str, models: ModelRoles, api_keys: dict[str, str] | None = None
    ) -> UserProfile:
        """Saves the ModelRoles and clears models_verified_at. api_keys (openai_compatible) are P1."""
        if api_keys:
            raise NotImplementedError("openai_compatible API keys are P1 (KMS-encrypted keys)")
        u = await self._user(user_id)
        u.models = models
        u.models_verified_at = None
        await self.store.put_user(u)
        return u

    async def verify_models(self, user_id: str) -> dict:
        """One tiny real call per configured role (all providers), checks the JSON output (< 25 s).
        Returns {ok, roles: {writer: "ok" | error, ...}}; sets models_verified_at on success.
        `fallback` is checked only when it is set (None = the writer model).
        """
        from bob.llm.client import get_llm

        u = await self._user(user_id)
        roles = ["writer", "planner", "judge"] + (["fallback"] if u.models.fallback is not None else [])
        if u.bedrock is None:
            return {"ok": False, "roles": {r: "connect AWS first" for r in roles}}
        job = self.health_job(u)
        ledger.register_job(job)
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        msgs = [Message(role="user", content='Return the JSON object {"ok": true}.')]

        async def check(role: str) -> str:
            cfg = getattr(u.models, role) or u.models.writer
            try:
                llm = get_llm(job, role)  # type: ignore[arg-type]
                if hasattr(llm, "use_cache"):
                    llm.use_cache = False  # a verify call is always a real call
                val, _ = await asyncio.wait_for(
                    llm.complete_json(role, "You reply with JSON only.", msgs, schema),  # type: ignore[arg-type]
                    timeout=20,
                )
                if val.get("ok") is not True:
                    return f"{cfg.model_id}: JSON output check failed: {json.dumps(val)[:200]}"
                return "ok"
            except TimeoutError:
                return f"{cfg.model_id}: no answer in 20 s (region {u.bedrock.region})"
            except Exception as e:
                return f"{type(e).__name__}: {e}"

        results = await asyncio.gather(*(check(r) for r in roles))
        out = dict(zip(roles, results, strict=True))
        ledger.forget(job.id)
        ok = all(v == "ok" for v in out.values())
        if ok:
            u = await self._user(user_id)
            u.models_verified_at = _now()
            await self.store.put_user(u)
        return {"ok": ok, "roles": out}

    def health_job(self, user: UserProfile) -> Job:
        """Small system Job (not saved) with the caller's bedrock + models; /health and verify calls pass it."""
        now = _now()
        return Job(
            id=f"health-{uuid.uuid4().hex[:8]}",
            spec=JobSpec(goal="health check", sources=[]),
            owner_id=user.id,
            bedrock=user.bedrock,
            models=user.models,
            created_at=now,
            updated_at=now,
        )


# ---------- seeds (section 7) ----------
def load_seeds(data: bytes, name: str) -> list[list[Message]]:
    """JSONL {"messages": [...]} or {"user", "assistant"}; CSV columns user,assistant. `name` picks the parser."""
    text = data.decode("utf-8-sig")
    out: list[list[Message]] = []
    if name.lower().endswith(".csv"):
        for rec in csv.DictReader(io.StringIO(text)):
            user, assistant = (rec.get("user") or "").strip(), (rec.get("assistant") or "").strip()
            if user and assistant:
                out.append([Message(role="user", content=user), Message(role="assistant", content=assistant)])
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if "messages" in rec:
            out.append([Message.model_validate(m) for m in rec["messages"]])
        elif "user" in rec and "assistant" in rec:
            out.append(
                [
                    Message(role="user", content=rec["user"]),
                    Message(role="assistant", content=rec["assistant"]),
                ]
            )
    return out
