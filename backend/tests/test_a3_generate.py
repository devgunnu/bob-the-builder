"""A3 Writer: mix rotation (pure) and real Writer / Planner calls on real repo text.

The real-call tests use real passages from the repo docs (.agents/PLAN.md section 2, .agents/CONTRACTS.md
section 14) until demo/smoke/ lands. No mocks: every LLM call goes to Bedrock through get_llm(job, role).
"""

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bob.config import default_bedrock_access, default_model_roles, get_settings, settings_for
from bob.core.models import CASE_TYPES, Chunk, Document, Evidence, Job, JobSpec, Message, Plan, Topic
from bob.llm.client import get_llm
from bob.pipeline.generate import (
    WRITER_SCHEMA,
    TopicContext,
    assign_focus,
    batch_message,
    build_prefix,
    call_writer,
    mix_schedule,
    premise_evidence,
    smooth_sequence,
    writer_system,
)
from bob.pipeline.planner import allocate_targets, build_axes, build_cells, propose_plan

REPO = Path(__file__).resolve().parents[2]


def _job(target_rows: int = 20) -> Job:
    now = datetime.now(UTC)
    return Job(
        id="t-a3-gen",
        spec=JobSpec(goal="g", sources=[], target_rows=target_rows),
        owner_id="local",
        bedrock=default_bedrock_access(),
        models=default_model_roles(),
        created_at=now,
        updated_at=now,
    )


# ---------- pure ----------
def test_smooth_sequence_shares_and_interleave():
    seq = smooth_sequence({"a": 0.5, "b": 0.25, "c": 0.25}, 20)
    assert Counter(seq) == {"a": 10, "b": 5, "c": 5}
    assert all(seq[i] != seq[i + 1] or seq[i] == "a" for i in range(19))
    assert smooth_sequence({"a": 1, "b": 0}, 3) == ["a", "a", "a"]


def _demo_plan() -> Plan:
    job = _job(1000)
    s = settings_for(job)
    topics = [Topic(id=f"t{i}", name=f"T{i}", description="d", chunk_ids=[f"c{i}"]) for i in range(3)]
    personas = [{"name": f"P{i}", "description": "x", "weight": 0.25} for i in range(4)]
    axes = build_axes(s, topics, personas, {"single_fact": 1, "multi_step": 1, "multi_doc": 1})
    plan = Plan(
        goal="g",
        system_prompt="s",
        axes=axes,
        cells=build_cells(axes, s.cell_axes, topics),
        target_rows=1000,
        est_cost_usd=0,
    )
    return allocate_targets(plan, job=job)


def test_mix_schedule_all_axes_rotated_per_batch():
    plan = _demo_plan()
    cell = plan.cells[0]
    rows = mix_schedule(cell, plan, 24)
    assert all(set(r) == {"topic", "case_type", "persona", "difficulty"} for r in rows)
    assert all(r["topic"] == cell.coords["topic"] for r in rows)
    assert Counter(r["persona"] for r in rows) == {f"P{i}": 6 for i in range(4)}
    assert Counter(r["difficulty"] for r in rows) == {
        d: 8 for d in ("single_fact", "multi_step", "multi_doc")
    }
    assert len({(r["persona"], r["difficulty"]) for r in rows}) == 12  # every pair appears
    for i in range(0, 20, 5):  # each batch of 5 has at least 3 personas and 2 difficulties
        b = rows[i : i + 5]
        assert len({r["persona"] for r in b}) >= 3 and len({r["difficulty"] for r in b}) >= 2
    no_md = mix_schedule(cell, plan, 12, multi_doc_ok=False)
    assert all(r["difficulty"] != "multi_doc" for r in no_md)


def test_mix_schedule_uses_gap_boost():
    plan = _demo_plan()
    cell = plan.cells[0]
    if "mix_weights" not in type(cell).model_fields:
        pytest.skip("Cell.mix_weights not in models yet (change request to A1)")
    cell.mix_weights = {"persona": {"P3": 1.0}}
    assert {r["persona"] for r in mix_schedule(cell, plan, 10)} == {"P3"}


# ---------- real passages from the repo docs ----------
def _section(path: Path, start: str, end: str) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    a = text.index(start)
    return text[a : text.index(end, a + len(start))].strip()


def _doc(path: Path, title: str, text: str) -> Document:
    uri = f"upload://{path.name}"
    return Document(
        id=hashlib.sha1(uri.encode()).hexdigest()[:12],
        source_kind="upload",
        uri=uri,
        title=title,
        text=text,
        content_hash=hashlib.sha1(text.encode()).hexdigest(),
        fetched_at=datetime.now(UTC),
    )


def _chunks(doc: Document) -> list[Chunk]:
    out, pos = [], 0
    for para in re.split(r"\n(?=###? |\| [0-9]\.|[0-9]\. \*\*)", doc.text):
        start = doc.text.index(para, pos)
        pos = start + len(para)
        if len(para.strip()) < 120:
            continue
        cid = hashlib.sha1(f"{doc.id}{start}".encode()).hexdigest()[:12]
        out.append(
            Chunk(
                id=cid,
                doc_id=doc.id,
                uri=doc.uri,
                text=para.strip(),
                start=start,
                end=pos,
                n_tokens=len(para) // 4,
            )
        )
    return out


def _material():
    plan_md, contracts_md = REPO / ".agents" / "PLAN.md", REPO / ".agents" / "CONTRACTS.md"
    d1 = _doc(plan_md, "Bob guide: using Bob", _section(plan_md, "## 2. The product", "## 3. Architecture"))
    d2 = _doc(
        contracts_md,
        "Bob guide: accounts and AWS",
        _section(contracts_md, "### Sign-in (D27)", "### Security rules"),
    )
    chunks = _chunks(d1) + _chunks(d2)
    topic = Topic(
        id="t-acct",
        name="Accounts, AWS access and jobs",
        description="Signing in, connecting your AWS account for Bedrock, picking models and running a job.",
        chunk_ids=[c.id for c in chunks],
    )
    span = "Capacity per user: `BOB_MAX_ACTIVE_JOBS_PER_USER` (1). More gives HTTP 429."
    if span not in d2.text:
        span = "Refresh the credentials `BOB_CRED_REFRESH_S` (300 s) before expiry."
    src = next(c for c in chunks if span in c.text)
    start = d2.text.index(span)
    ev = Evidence(
        id="ev-1",
        chunk_id=src.id,
        doc_id=d2.id,
        kind="limit",
        name=span.split("`")[1],
        value=re.search(r"\((\d+)", span).group(1),
        span_text=span,
        start=start,
        end=start + len(span),
        confidence=1.0,
    )
    return {d1.id: d1, d2.id: d2}, chunks, topic, ev


@pytest.fixture
def real_env(monkeypatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _real_plan(job: Job, topic: Topic, chunks: list[Chunk]) -> Plan:
    return await propose_plan(
        "First-reply support assistant for Bob the Builder users. Use only our docs. If the docs do not cover "
        "it, say so and hand off to a human.",
        [topic],
        [],
        job.spec.target_rows,
        job.spec.budget_usd,
        job=job,
        chunks={c.id: c for c in chunks},
    )


async def test_real_propose_plan(real_env):
    job = _job(40)
    docs, chunks, topic, _ = _material()
    plan = await _real_plan(job, topic, chunks)
    assert plan.system_prompt and 3 <= len(next(a for a in plan.axes if a.name == "persona").values) <= 5
    assert len(plan.cells) == 4 and sum(c.target for c in plan.cells) == 40
    assert plan.est_cost_usd > 0
    out = Path(get_settings().runs_dir) / "a3_samples"
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")


@pytest.mark.parametrize("case_type", CASE_TYPES)
async def test_real_writer_batch(real_env, case_type):
    job = _job(40)
    docs, chunks, topic, ev = _material()
    plan = await _real_plan(job, topic, chunks)
    cell = next(c for c in plan.cells if c.coords["case_type"] == case_type)
    pool = chunks[:10]
    if ev.chunk_id not in {c.id for c in pool}:
        pool[-1] = next(c for c in chunks if c.id == ev.chunk_id)
    tc = TopicContext(
        value=topic.name,
        prefix=build_prefix(topic.name, [topic], pool, [c.text for c in pool], docs),
        pool=[c.id for c in pool],
        doc_of={c.id: c.doc_id for c in pool},
        evidence=premise_evidence([ev]),
    )
    coords = mix_schedule(cell, plan, settings_for(job).writer_batch, tc.multi_doc_ok)
    slots = assign_focus(tc, coords)
    msg = batch_message(plan, case_type, slots, strict=False, batch_no=1, round_no=1, avoid=[])
    system = writer_system(plan, [])
    res = await call_writer(get_llm(job, "writer"), job, system, tc.prefix, msg)
    assert res is not None
    rows = res.rows
    assert sorted(r["slot"] for r in rows) == [1, 2, 3, 4, 5]
    assert len({r["user"].strip().lower() for r in rows}) == 5
    assert len({" ".join(r["user"].split()[:2]).lower() for r in rows}) >= 4  # varied openings
    for r in rows:
        assert r["user"].strip() and r["assistant"].strip()
        assert set(r["chunk_ids"]) <= set(tc.pool) and r["chunk_ids"]
        if case_type in ("partial", "unanswerable"):
            assert r["absent_topic"] and r["absent_topic"].strip()
        if case_type == "false_premise":
            assert r["premise_evidence_id"] == ev.id
    assert res.cost_usd > 0
    out = Path(get_settings().runs_dir) / "a3_samples"
    out.mkdir(parents=True, exist_ok=True)
    sample = {"coords": slots[0].coords, **rows[0]}
    (out / f"{case_type}.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
    print(f"\n[{case_type}] " + json.dumps(sample)[:900])


async def test_real_writer_cache_read(real_env, monkeypatch):
    """Two calls with the same system + topic prefix and different slots: the second reads the cache."""
    monkeypatch.setenv("BOB_CACHE", "0")  # disk response cache off: both calls go to Bedrock
    get_settings.cache_clear()
    job = _job(40)
    docs, chunks, topic, _ = _material()
    plan = await _real_plan(job, topic, chunks)
    cell = next(c for c in plan.cells if c.coords["case_type"] == "answerable")
    pool = chunks[:10]
    prefix = build_prefix(topic.name, [topic], pool, [c.text for c in pool], docs)
    tc = TopicContext(
        value=topic.name, prefix=prefix, pool=[c.id for c in pool], doc_of={c.id: c.doc_id for c in pool}
    )
    system = writer_system(plan, [])
    llm = get_llm(job, "writer")
    usages = []
    for b in (1, 2):
        slots = assign_focus(tc, mix_schedule(cell, plan, 2), start=b * 2)
        msg = batch_message(plan, "answerable", slots, strict=False, batch_no=b, round_no=1, avoid=[])
        _, u = await llm.complete_json(
            "writer", system, [Message(role="user", content=msg)], WRITER_SCHEMA, cache_prefix=prefix
        )
        usages.append(u)
    assert usages[0].cache_write_tokens > 0 or usages[0].cache_read_tokens > 0
    assert usages[1].cache_read_tokens > 0
