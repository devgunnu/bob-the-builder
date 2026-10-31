"""A3 planner pure logic: axes, cells, merging, allocation. Real model objects, no LLM call."""

from datetime import UTC, datetime

from bob.config import default_model_roles, settings_for
from bob.core.models import CASE_TYPES, Chunk, Job, JobOptions, JobSpec, Plan, SourceSpec, Topic
from bob.pipeline.planner import (
    MERGE_SEP,
    allocate_targets,
    build_axes,
    build_cells,
    cap_topics,
    cell_id,
    merge_smallest,
    topic_members,
)


def _job(options: JobOptions | None = None, target_rows: int = 1000) -> Job:
    now = datetime.now(UTC)
    spec = JobSpec(
        goal="support bot",
        sources=[SourceSpec(kind="upload", upload_ids=["u1"])],
        target_rows=target_rows,
        options=options or JobOptions(),
    )
    return Job(
        id="j1", spec=spec, owner_id="local", models=default_model_roles(), created_at=now, updated_at=now
    )


def _topics(sizes: list[int]) -> list[Topic]:
    return [
        Topic(
            id=f"t{i}", name=f"Topic {i}", description=f"desc {i}", chunk_ids=[f"t{i}c{k}" for k in range(n)]
        )
        for i, n in enumerate(sizes)
    ]


PERSONAS = [
    {"name": "New admin", "description": "sets up the account", "weight": 0.5},
    {"name": "Developer", "description": "uses the API", "weight": 0.3},
    {"name": "Finance lead", "description": "checks bills", "weight": 0.2},
]


def _plan(job: Job, topics: list[Topic]) -> Plan:
    s = settings_for(job)
    axes = build_axes(s, topics, PERSONAS, {"single_fact": 2, "multi_step": 2, "multi_doc": 1})
    cells = build_cells(axes, s.cell_axes, topics)
    return Plan(
        goal="g", system_prompt="sp", axes=axes, cells=cells, target_rows=job.spec.target_rows, est_cost_usd=0
    )


def test_default_map_is_topic_by_case_type_with_mix_axes():
    job = _job()
    plan = _plan(job, _topics([10] * 12))
    assert len(plan.cells) == 48
    assert all(set(c.coords) == {"topic", "case_type"} for c in plan.cells)
    roles = {a.name: a.role for a in plan.axes}
    assert roles == {"topic": "cell", "case_type": "cell", "persona": "mix", "difficulty": "mix"}
    persona = next(a for a in plan.axes if a.name == "persona")
    assert abs(sum(persona.weights.values()) - 1) < 1e-9 and persona.weights["New admin"] == 0.5
    diff = next(a for a in plan.axes if a.name == "difficulty")
    assert abs(diff.weights["multi_doc"] - 0.2) < 1e-9
    assert len({c.id for c in plan.cells}) == 48
    c = plan.cells[0]
    assert c.id == cell_id(dict(reversed(list(c.coords.items()))))  # order-independent id


def test_allocate_targets_case_mix_and_total():
    job = _job()
    plan = allocate_targets(_plan(job, _topics([10] * 12)), job=job)
    assert sum(c.target for c in plan.cells) == 1000
    by_ct = {ct: sum(c.target for c in plan.cells if c.coords["case_type"] == ct) for ct in CASE_TYPES}
    assert by_ct == {"answerable": 500, "partial": 150, "unanswerable": 200, "false_premise": 150}
    assert min(c.target for c in plan.cells) >= settings_for(job).min_cell_target


def test_allocate_targets_minimum_and_disabled_cells():
    job = _job(
        JobOptions(case_mix={"answerable": 0.9, "partial": 0.1, "unanswerable": 0, "false_premise": 0})
    )
    plan = _plan(job, _topics([5] * 4))
    plan.cells[0].enabled = False
    plan = allocate_targets(plan.model_copy(update={"target_rows": 60}), job=job)
    assert plan.cells[0].target == 0
    enabled = [c for c in plan.cells if c.enabled]
    assert all(c.target >= 3 for c in enabled)  # MIN_CELL_TARGET
    assert sum(c.target for c in enabled) == 60  # minimums are paid from the largest cells


def test_allocate_targets_weight_shifts_rows():
    job = _job()
    plan = _plan(job, _topics([5] * 2))
    for c in plan.cells:
        if c.coords == {"topic": "Topic 0", "case_type": "answerable"}:
            c.weight = 3.0
    plan = allocate_targets(plan.model_copy(update={"target_rows": 100}), job=job)
    t = {(c.coords["topic"], c.coords["case_type"]): c.target for c in plan.cells}
    assert t[("Topic 0", "answerable")] == 38 and t[("Topic 1", "answerable")] == 12


def test_merge_and_cap_keep_real_names():
    topics = _topics([1, 2, 9, 8])
    merged = merge_smallest(topics)
    assert len(merged) == 3
    m = next(t for t in merged if MERGE_SEP in t.name)
    assert m.name == "Topic 1" + MERGE_SEP + "Topic 0" and len(m.chunk_ids) == 3
    assert [t.name for t in topic_members(m.name, topics)] == ["Topic 1", "Topic 0"]
    capped = cap_topics(_topics(list(range(1, 26))), 20)
    assert len(capped) == 20
    real = {t.name for t in _topics(list(range(1, 26)))}
    assert all(p in real for t in capped for p in t.name.split(MERGE_SEP))


def test_cells_over_custom_axes_and_multi_doc_rule():
    job = _job(JobOptions(cell_axes=["topic", "difficulty"]))
    topics = _topics([2, 2])
    chunks = {
        cid: Chunk(
            id=cid, doc_id=("d1" if t.id == "t0" else f"d{k}"), uri="u", text="x", start=0, end=1, n_tokens=1
        )
        for t in topics
        for k, cid in enumerate(t.chunk_ids)
    }
    s = settings_for(job)
    axes = build_axes(s, topics, PERSONAS, None)
    cells = build_cells(axes, s.cell_axes, topics, chunks)
    assert len(cells) == 6 and all(set(c.coords) == {"topic", "difficulty"} for c in cells)
    off = [c.coords for c in cells if not c.enabled]
    assert off == [{"topic": "Topic 0", "difficulty": "multi_doc"}]  # one-doc topic
    case_axis = next(a for a in axes if a.name == "case_type")
    assert case_axis.role == "mix" and abs(case_axis.weights["answerable"] - 0.5) < 1e-9
