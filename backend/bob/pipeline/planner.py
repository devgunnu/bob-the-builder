"""Planner: topics + goal -> coverage map (Plan). Owner: A3. CONTRACTS section 3, PLAN section 2.

Cells are the cross product of the CELL_AXES only (default topic x case_type). The other axes are mix axes:
their values rotate inside each cell by `Axis.weights`. All thresholds come from `settings_for(job)`.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from functools import cache
from pathlib import Path

from bob.config import EffectiveSettings, settings_for
from bob.core.models import CASE_TYPES, DIFFICULTIES, Axis, Cell, Chunk, Job, Message, Plan, Topic
from bob.llm.client import Role, Usage, current_job, get_llm, model_for
from bob.llm.registry import caps_for

PROMPTS_DIR = Path(__file__).parent / "prompts"
MERGE_SEP = " + "  # a merged topic value joins the real topic names
AXIS_ORDER = ("topic", "persona", "case_type", "difficulty")

CASE_TYPE_DESCRIPTIONS = {
    "answerable": "The docs fully answer the question.",
    "partial": "The docs answer one part; the reply names the uncovered part and offers a handoff.",
    "unanswerable": "On-topic but not in the docs; the reply says so and offers a handoff.",
    "false_premise": "The user assumes a wrong fact; the reply corrects it with the real value.",
}
DIFFICULTY_DESCRIPTIONS = {
    "single_fact": "One fact from the docs.",
    "multi_step": "A procedure, or two linked facts.",
    "multi_doc": "Facts from two different documents.",
}

# Planning estimates (tokens). Used only for est_cost_usd before any real call of the build exists.
EST_WRITER_OUT_PER_ROW = 260
EST_WRITER_INSTR_TOKENS = 1_400  # writer.md + case-type prompt + slot specs
EST_POOL_CHUNKS = 10
EST_CHUNK_TOKENS = 400
EST_JEV_IN_PER_ROW = 2_600
EST_SCALEDOWN_IN_PER_ROW = 350
EST_JUDGE_SHARE = 0.07  # routed + audited share of candidates (PLAN section 10)
EST_JUDGE_IN, EST_JUDGE_OUT = 2_000, 120
EST_ROUND_FACTOR = 1.25  # gap rounds after round 1


# ---------- prompt helpers (shared with generate.py) ----------
@cache
def load_prompt(name: str) -> str:
    """Prompt file text, newline-normalized so the cached prefix is byte-stable on every OS."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n").strip() + "\n"


def render(template: str, **values: str) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def cell_id(coords: dict[str, str]) -> str:
    key = json.dumps(sorted(coords.items()), ensure_ascii=False)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def topic_members(value: str, topics: dict[str, Topic] | list[Topic]) -> list[Topic]:
    """Real topics behind a topic axis value. A merged value is the real names joined by MERGE_SEP."""
    items = list(topics.values()) if isinstance(topics, dict) else list(topics)
    by_name = {t.name: t for t in items}
    if value in by_name:
        return [by_name[value]]
    return [by_name[p] for p in value.split(MERGE_SEP) if p in by_name]


def normalize_weights(values: list[str], weights: dict[str, float] | None) -> dict[str, float]:
    """Shares for `values` that add up to 1. Missing, negative or all-zero weights -> equal shares."""
    w = {v: max(0.0, float((weights or {}).get(v, 0.0))) for v in values}
    total = sum(w.values())
    if total <= 0:
        return {v: 1.0 / len(values) for v in values} if values else {}
    return {v: x / total for v, x in w.items()}


# ---------- prices (registry or ModelConfig override) ----------
def model_prices(job: Job, role: Role) -> tuple[float | None, float | None, bool]:
    """(price in per M, price out per M, cache supported) for the job's model of `role` (registry + overrides)."""
    caps = caps_for(model_for(job, role))
    return caps.price_in_per_m, caps.price_out_per_m, caps.cache


def usage_cost_usd(job: Job, role: Role, usage: Usage) -> float:
    """Real cost of one call from its real token counts (Converse in_tokens exclude the cache tokens).

    Unknown price -> 0.0; the LLM client already put the role in CostSummary.price_unknown.
    """
    if usage.cached:
        return 0.0
    caps = caps_for(model_for(job, role))
    usd = caps.usd(usage.in_tokens, usage.out_tokens, usage.cache_read_tokens, usage.cache_write_tokens)
    return usd or 0.0


# ---------- topics: cap and merge ----------
def _merge_pair(a: Topic, b: Topic) -> Topic:
    big, small = (a, b) if len(a.chunk_ids) >= len(b.chunk_ids) else (b, a)
    ids = sorted({*big.id.split("+"), *small.id.split("+")})
    return Topic(
        id="+".join(ids),
        name=big.name + MERGE_SEP + small.name,
        description=f"{big.description} Also: {small.description}",
        chunk_ids=big.chunk_ids + [c for c in small.chunk_ids if c not in set(big.chunk_ids)],
        brief="\n\n".join(x for x in (big.brief, small.brief) if x),
    )


def merge_smallest(topics: list[Topic]) -> list[Topic]:
    """Merge the two smallest topics (fewest chunks) into one; the merged topic keeps both real names."""
    if len(topics) < 2:
        return list(topics)
    order = sorted(range(len(topics)), key=lambda i: (len(topics[i].chunk_ids), topics[i].name))
    i, j = order[0], order[1]
    merged = _merge_pair(topics[i], topics[j])
    rest = [t for k, t in enumerate(topics) if k not in (i, j)]
    return sorted([*rest, merged], key=lambda t: (-len(t.chunk_ids), t.name))


def cap_topics(topics: list[Topic], max_topics: int) -> list[Topic]:
    out = sorted(topics, key=lambda t: (-len(t.chunk_ids), t.name))
    while len(out) > max(1, max_topics):
        out = merge_smallest(out)
    return out


def topic_doc_count(topic: Topic, chunks: dict[str, Chunk] | None) -> int | None:
    if not chunks:
        return None
    return len({chunks[c].doc_id for c in topic.chunk_ids if c in chunks})


# ---------- axes and cells ----------
def build_axes(
    s: EffectiveSettings,
    topics: list[Topic],
    personas: list[dict],
    difficulty_weights: dict[str, float] | None,
) -> list[Axis]:
    cell_axes = set(s.cell_axes)
    p_values = [p["name"] for p in personas]
    raw = {
        "topic": (
            [t.name for t in topics],
            {t.name: t.description for t in topics},
            {},
        ),
        "persona": (
            p_values,
            {p["name"]: p.get("description", "") for p in personas},
            {p["name"]: p.get("weight", 0.0) for p in personas},
        ),
        "case_type": (list(CASE_TYPES), dict(CASE_TYPE_DESCRIPTIONS), dict(s.case_mix)),
        "difficulty": (list(DIFFICULTIES), dict(DIFFICULTY_DESCRIPTIONS), dict(difficulty_weights or {})),
    }
    axes = []
    for name in AXIS_ORDER:
        values, desc, weights = raw[name]
        role = "cell" if name in cell_axes else "mix"
        axes.append(
            Axis(
                name=name,
                values=values,
                descriptions=desc,
                role=role,
                weights=normalize_weights(values, weights) if role == "mix" else {},
            )
        )
    return axes


def build_cells(
    axes: list[Axis], cell_axes: list[str], topics: list[Topic], chunks: dict[str, Chunk] | None = None
) -> list[Cell]:
    """Cross product of the cell axes (in CELL_AXES order). A multi_doc cell of a one-doc topic is disabled."""
    by_name = {a.name: a for a in axes}
    names = [n for n in cell_axes if n in by_name]
    docs_per_topic = {t.name: topic_doc_count(t, chunks) for t in topics}
    cells = []
    for combo in itertools.product(*(by_name[n].values for n in names)):
        coords = dict(zip(names, combo, strict=True))
        enabled = True
        if coords.get("difficulty") == "multi_doc" and "topic" in coords:
            n_docs = docs_per_topic.get(coords["topic"])
            enabled = n_docs is None or n_docs >= 2
        cells.append(Cell(id=cell_id(coords), coords=coords, enabled=enabled, target=0))
    return cells


# ---------- allocation ----------
def _round(raw: dict[str, float], total: int) -> dict[str, int]:
    """Largest-remainder rounding: integers near `raw` that add up to `total`; ties go to the larger value."""
    out = {k: math.floor(v) for k, v in raw.items()}
    order = sorted(raw, key=lambda k: (-(raw[k] - math.floor(raw[k])), -raw[k], k))
    diff, i = total - sum(out.values()), 0
    while diff > 0 and order:
        out[order[i % len(order)]] += 1
        diff, i = diff - 1, i + 1
    return out


def _apply_minimum(out: dict[str, int], raw: dict[str, float], minimum: int, total: int) -> dict[str, int]:
    """Raise every value to `minimum`; pay for it from the largest values above the minimum when possible."""
    out = {k: max(minimum, v) for k, v in out.items()}
    by_size = sorted(raw, key=lambda k: (-raw[k], k))
    diff = sum(out.values()) - total
    while diff > 0:
        moved = False
        for k in by_size:
            if diff == 0:
                break
            if out[k] > minimum:
                out[k] -= 1
                diff -= 1
                moved = True
        if not moved:
            break  # total < cells x minimum: the minimum wins
    return out


def _split_by_weight(cells: list[Cell], total: float) -> dict[str, float]:
    weights = {c.id: max(c.weight, 0.0) for c in cells}
    wsum = sum(weights.values())
    if wsum <= 0:
        weights, wsum = {c.id: 1.0 for c in cells}, float(len(cells))
    return {cid: total * w / wsum for cid, w in weights.items()}


def allocate_targets(plan: Plan, *, job: Job | None = None) -> Plan:
    """Split plan.target_rows across the enabled cells by weight and CASE_MIX; each gets >= MIN_CELL_TARGET.

    When case_type is a cell axis, each case type gets its CASE_MIX share (renormalized over the case types
    that have an enabled cell), split by cell weight. Else the rows split by cell weight only. Integer
    rounding gives the remainder to the largest cells. Disabled cells get target 0.
    `job` defaults to current_job() (set by run_job).
    """
    s = settings_for(job or current_job())
    enabled = [c for c in plan.cells if c.enabled]
    total = plan.target_rows
    targets: dict[str, int] = {}
    raw: dict[str, float] = {}
    if enabled and all("case_type" in c.coords for c in enabled):
        present = sorted({c.coords["case_type"] for c in enabled}, key=CASE_TYPES.index)
        mix = normalize_weights(present, s.case_mix)
        group_totals = _round({ct: total * mix[ct] for ct in present}, total)
        for ct in present:
            group_raw = _split_by_weight(
                [c for c in enabled if c.coords["case_type"] == ct], group_totals[ct]
            )
            raw.update(group_raw)
            targets.update(_round(group_raw, group_totals[ct]))
    elif enabled:
        raw = _split_by_weight(enabled, total)
        targets = _round(raw, total)
    targets = _apply_minimum(targets, raw, s.min_cell_target, total)
    cells = [c.model_copy(update={"target": targets.get(c.id, 0) if c.enabled else 0}) for c in plan.cells]
    return plan.model_copy(update={"cells": cells})


# ---------- cost estimate ----------
def estimate_cost_usd(plan: Plan, job: Job, topics: list[Topic], chunks: dict[str, Chunk] | None) -> float:
    """Build cost estimate: writer calls x prompt tokens x the job's model prices (cache from the registry),
    plus Jev, ScaleDown and the judge share per candidate. Unknown LLM prices count as 0."""
    s = settings_for(job)
    by_topic = {t.name: t for t in topics}
    w_in, w_out, w_cache = model_prices(job, "writer")
    j_in, j_out, _ = model_prices(job, "judge")
    usd = 0.0
    n_cands = 0
    for c in plan.cells:
        if not c.enabled or c.target <= 0:
            continue
        rows = math.ceil(c.target * s.overgen * EST_ROUND_FACTOR)
        calls = math.ceil(rows / max(1, s.writer_batch))
        n_cands += rows
        t = by_topic.get(c.coords.get("topic", ""))
        pool = t.chunk_ids[:EST_POOL_CHUNKS] if t else []
        pool_tokens = (
            sum(chunks[x].n_tokens for x in pool if x in chunks) if chunks else len(pool) * EST_CHUNK_TOKENS
        )
        prefix = (len(t.brief) // 4 if t else 0) + pool_tokens
        if w_in is not None and w_out is not None:
            prefix_usd = prefix * w_in * (0.1 if w_cache else 1.0)
            if w_cache:  # one cache write per cell
                prefix_usd += prefix * w_in * 1.25 / calls
            per_call = (
                prefix_usd + EST_WRITER_INSTR_TOKENS * w_in + s.writer_batch * EST_WRITER_OUT_PER_ROW * w_out
            )
            usd += calls * per_call / 1_000_000
    usd += (
        n_cands
        * (EST_JEV_IN_PER_ROW * s.jev_price_in_per_m + EST_SCALEDOWN_IN_PER_ROW * s.scaledown_price_in_per_m)
        / 1_000_000
    )
    if j_in is not None and j_out is not None:
        usd += n_cands * EST_JUDGE_SHARE * (EST_JUDGE_IN * j_in + EST_JUDGE_OUT * j_out) / 1_000_000
    return round(usd, 4)


# ---------- seeds ----------
def seed_topic_hits(seeds: list[list[Message]], topics: list[Topic]) -> dict[str, int]:
    """Topic name -> number of seeds whose user turn is nearest (embedding cosine) to that topic."""
    users = [next((m.content for m in s if m.role == "user"), "") for s in seeds]
    users = [u for u in users if u.strip()]
    hits = {t.name: 0 for t in topics}
    if not users or not topics:
        return hits
    from bob.pipeline.embed import embed  # A2

    t_vec = embed([f"{t.name}. {t.description} {t.brief[:600]}" for t in topics])
    u_vec = embed(users)
    t_vec = t_vec / (((t_vec**2).sum(axis=1, keepdims=True)) ** 0.5 + 1e-9)
    u_vec = u_vec / (((u_vec**2).sum(axis=1, keepdims=True)) ** 0.5 + 1e-9)
    best = (u_vec @ t_vec.T).argmax(axis=1)
    for i in best.tolist():
        hits[topics[i].name] += 1
    return hits


def seed_notes(seeds: list[list[Message]], topics: list[Topic]) -> list[str]:
    if not seeds:
        return ["No seed examples were given, so the Writer takes its style from the docs and the personas."]
    hits = seed_topic_hits(seeds, topics)
    covered = [n for n, k in hits.items() if k > 0]
    notes = [f"Your seed examples cover {len(covered)} of {len(topics)} topics."]
    missing = [n for n, k in hits.items() if k == 0]
    if missing:
        shown = ", ".join(missing[:3]) + (f" and {len(missing) - 3} more" if len(missing) > 3 else "")
        notes.append(f"No seed examples cover {shown}.")
    return notes


# ---------- planner call ----------
PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "system_prompt": {"type": "string"},
        "personas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "weight": {"type": "number"},
                },
                "required": ["name", "description", "weight"],
                "additionalProperties": False,
            },
        },
        "difficulty_weights": {
            "type": "object",
            "properties": {d: {"type": "number"} for d in DIFFICULTIES},
            "required": list(DIFFICULTIES),
            "additionalProperties": False,
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["system_prompt", "personas", "difficulty_weights", "notes"],
    "additionalProperties": False,
}


def planner_message(
    goal: str,
    topics: list[Topic],
    seeds: list[list[Message]],
    target_rows: int,
    budget_usd: float,
    n_docs: int | None,
) -> str:
    lines = [f"Goal: {goal}", "", f"Target rows: {target_rows}. Budget: ${budget_usd:.2f}."]
    if n_docs is not None:
        lines.append(f"Number of source documents: {n_docs}.")
    lines += ["", f"Topics ({len(topics)}), found in the documentation:"]
    for t in topics:
        excerpt = " ".join(t.brief.split())[:500]
        lines.append(f"- {t.name} ({len(t.chunk_ids)} passages): {t.description}")
        if excerpt:
            lines.append(f"  Brief: {excerpt}")
    lines.append("")
    if seeds:
        lines.append(f"Seed examples from the company ({len(seeds)}). First ones:")
        for s in seeds[:3]:
            user = next((m.content for m in s if m.role == "user"), "")
            lines.append(f"- USER: {' '.join(user.split())[:300]}")
    else:
        lines.append("Seed examples: none.")
    return "\n".join(lines)


def _clean_personas(raw: object) -> list[dict]:
    out, seen = [], set()
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        name = " ".join(str(p.get("name", "")).split())[:60]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        weight = p.get("weight")
        out.append(
            {
                "name": name,
                "description": " ".join(str(p.get("description", "")).split()),
                "weight": float(weight) if isinstance(weight, int | float) else 0.0,
            }
        )
    return out[:5]


async def propose_plan(
    goal: str,
    topics: list[Topic],
    seeds: list[list[Message]],
    target_rows: int,
    budget_usd: float,
    *,
    job: Job | None = None,
    chunks: dict[str, Chunk] | None = None,
) -> Plan:
    """One planner-role call -> Plan with cells over CELL_AXES, mix axes with weights, notes and est cost.

    `job` (keyword-only, default current_job()): settings_for(job) and get_llm(job, "planner"). `chunks` (optional): lets the plan
    count documents per topic (multi_doc rules) and use real chunk token counts in the estimate.
    """
    if not topics:
        raise ValueError("propose_plan needs at least one topic")
    job = job or current_job()
    s = settings_for(job)
    topics = cap_topics(topics, s.max_topics)
    n_docs = len({c.doc_id for c in chunks.values()}) if chunks else None

    llm = get_llm(job, "planner")
    msg = planner_message(goal, topics, seeds, target_rows, budget_usd, n_docs)
    data: dict = {}
    personas: list[dict] = []
    for _ in range(2):  # semantic check: retry once, then fail loudly
        data, _usage = await llm.complete_json(
            "planner", load_prompt("planner.md"), [Message(role="user", content=msg)], PLANNER_SCHEMA
        )
        personas = _clean_personas(data.get("personas"))
        if personas and str(data.get("system_prompt", "")).strip():
            break
    else:
        raise ValueError("planner returned no personas or no system_prompt twice")

    diff_w = data.get("difficulty_weights") if isinstance(data.get("difficulty_weights"), dict) else {}
    diff_w = {k: float(v) for k, v in diff_w.items() if isinstance(v, int | float)}
    if n_docs is not None and n_docs < 2:
        diff_w["multi_doc"] = 0.0

    axes = build_axes(s, topics, personas, diff_w)
    cells = build_cells(axes, s.cell_axes, topics, chunks)
    merged_note = None
    while sum(c.enabled for c in cells) > s.max_cells and len(topics) > 1:
        topics = merge_smallest(topics)
        axes = build_axes(s, topics, personas, diff_w)
        cells = build_cells(axes, s.cell_axes, topics, chunks)
        merged_note = f"Small topics were merged so the map has at most {s.max_cells} cells."

    notes = seed_notes(seeds, topics)
    if merged_note:
        notes.append(merged_note)
    notes += [" ".join(str(n).split()) for n in data.get("notes", []) if str(n).strip()][:4]

    plan = Plan(
        goal=goal,
        system_prompt=str(data["system_prompt"]).strip(),
        axes=axes,
        cells=cells,
        notes=notes,
        target_rows=target_rows,
        est_cost_usd=0.0,
    )
    plan = allocate_targets(plan, job=job)
    plan.est_cost_usd = estimate_cost_usd(plan, job, topics, chunks)
    return plan
