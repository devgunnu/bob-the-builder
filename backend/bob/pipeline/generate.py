"""Writer: cell -> candidates (CONTRACTS sections 3, 4; PLAN section 2). Owner: A3.

Prompt layout per Writer call (D33, prompt caching):
- system: prompts/writer.md with the plan system prompt and up to 2 real seed examples (stable per job);
- cache_prefix: topic brief + compressed passages with their chunk ids (stable per topic, so every cell and
  batch of the topic reads the same cached prefix); the LLM client puts the cache point after it;
- user message: case-type instructions, the strict variant for hard cells, and the slot list of this batch
  (persona, difficulty, focus passages, false-premise evidence item). Mix values change only here.

No temperature: diversity comes from the persona and difficulty mix, "different rows", rotating focus
passages and the list of openings that earlier batches used.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from bob.config import settings_for
from bob.core.models import (
    CASE_TYPES,
    Axis,
    Candidate,
    Cell,
    Chunk,
    Document,
    Evidence,
    GenContext,
    Job,
    Message,
    Plan,
    Row,
    Topic,
)
from bob.llm.bedrock import LLMError, LLMOutputError
from bob.llm.client import LLMClient, get_llm, model_for
from bob.pipeline.planner import (
    CASE_TYPE_DESCRIPTIONS,
    DIFFICULTY_DESCRIPTIONS,
    load_prompt,
    normalize_weights,
    render,
    topic_members,
    usage_cost_usd,
)

POOL_SIZE = 10  # passages in the cached prefix per topic
FP_KINDS = ("setting", "number", "limit")  # false_premise evidence kinds, by preference
SEED_EXAMPLES = 2
AVOID_OPENINGS = 12
HARD_CELL_REJECT_RATE = 0.5  # same rule as gaps.py: rejected / generated above this -> strict prompt

WRITER_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot": {"type": "integer"},
                    "user": {"type": "string"},
                    "assistant": {"type": "string"},
                    "chunk_ids": {"type": "array", "items": {"type": "string"}},
                    "absent_topic": {"type": ["string", "null"]},
                    "premise_evidence_id": {"type": ["string", "null"]},
                },
                "required": ["slot", "user", "assistant", "chunk_ids", "absent_topic", "premise_evidence_id"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rows"],
    "additionalProperties": False,
}


# ---------- mix rotation ----------
def smooth_sequence(weights: dict[str, float], n: int) -> list[str]:
    """n values in a smooth weighted round-robin order: shares follow the weights, values interleave."""
    values = [v for v, w in weights.items() if w > 0]
    if not values or n <= 0:
        return []
    total = sum(weights[v] for v in values)
    current = dict.fromkeys(values, 0.0)
    out = []
    for _ in range(n):
        for v in values:
            current[v] += weights[v]
        pick = max(values, key=lambda v: (current[v], -values.index(v)))
        current[pick] -= total
        out.append(pick)
    return out


def mix_weights(cell: Cell, axis: Axis, multi_doc_ok: bool = True) -> dict[str, float]:
    """Shares for one mix axis in this cell: plan weights, or the gap-round boost (Cell.mix_weights), with
    multi_doc removed when the topic has passages from one document only."""
    override = (getattr(cell, "mix_weights", None) or {}).get(axis.name)
    w = dict(override) if override else dict(axis.weights)
    w = normalize_weights(axis.values, w)
    if axis.name == "difficulty" and not multi_doc_ok and "multi_doc" in w:
        w["multi_doc"] = 0.0
        w = normalize_weights(axis.values, w)
    return w


def mix_schedule(
    cell: Cell, plan: Plan, n: int, multi_doc_ok: bool = True, offset: int = 0
) -> list[dict[str, str]]:
    """All-4-axis coords for n rows of a cell. Each mix axis follows its weights; later axes shift by one
    step per cycle of the first axis, so equal-length axes do not always pair the same values."""
    mix = [a for a in plan.axes if a.role == "mix" and a.name not in cell.coords]
    start = (int(cell.id[:8], 16) % 101 if re.fullmatch(r"[0-9a-f]{8}", cell.id[:8]) else 0) + offset
    seqs: list[list[str]] = []
    first_len = 1
    for k, axis in enumerate(mix):
        w = mix_weights(cell, axis, multi_doc_ok)
        if k == 0:
            first_len = max(1, sum(1 for x in w.values() if x > 0))
            seq = smooth_sequence(w, start + n)[start:]
        else:
            seq = smooth_sequence(w, start + n + n // first_len + 1)[start:]
            seq = [seq[i + i // first_len] for i in range(n)]
        seqs.append(seq)
    return [{**cell.coords, **{a.name: s[i] for a, s in zip(mix, seqs, strict=True)}} for i in range(n)]


# ---------- context ----------
@dataclass
class TopicContext:
    value: str  # topic axis value (real name, or merged real names)
    prefix: str  # cached part: brief + passages
    pool: list[str]  # chunk ids in the prefix, in order
    doc_of: dict[str, str]  # chunk id -> doc id
    evidence: list[Evidence] = field(default_factory=list)  # false_premise candidates in the pool

    @property
    def multi_doc_ok(self) -> bool:
        return len(set(self.doc_of.values())) >= 2


def _topic_pool(ctx: GenContext, members: list[Topic]) -> list[str]:
    """Top-k retrieved passages for the topic (members interleaved), then the rest of the topic's chunks.
    Makes sure that two documents are in the pool when the topic has them."""
    per_member: list[list[str]] = []
    for t in members:
        hits = [c.id for c in ctx.retriever.top_k(f"{t.name}. {t.description}", k=POOL_SIZE, topic_id=t.id)]
        rest = [c for c in t.chunk_ids if c in ctx.chunks and ctx.chunks[c].kept and c not in hits]
        per_member.append([c for c in hits if c in ctx.chunks] + rest)
    pool: list[str] = []
    for i in range(max((len(x) for x in per_member), default=0)):
        for ids in per_member:
            if i < len(ids) and ids[i] not in pool:
                pool.append(ids[i])
    all_ids, pool = pool, pool[:POOL_SIZE]
    docs = {ctx.chunks[c].doc_id for c in pool}
    if len(docs) < 2:
        other = next((c for c in all_ids[POOL_SIZE:] if ctx.chunks[c].doc_id not in docs), None)
        if other and pool:
            pool[-1] = other
    return pool


def build_prefix(
    value: str,
    members: list[Topic],
    pool: list[Chunk],
    texts: list[str],
    docs: dict[str, Document],
) -> str:
    """Cached prompt part for a topic: names, brief, then each passage with its chunk id and source."""
    parts = [f"# Topic: {value}", ""]
    for t in members:
        parts.append(f"{t.name}: {t.description}")
    briefs = [t.brief.strip() for t in members if t.brief.strip()]
    if briefs:
        parts += ["", "## Topic brief", "", "\n\n".join(briefs)]
    parts += ["", "## Passages", ""]
    for ch, text in zip(pool, texts, strict=True):
        doc = docs.get(ch.doc_id)
        source = doc.title if doc else ch.uri
        head = f"[{ch.id}] source: {source}" + (f" | section: {ch.heading}" if ch.heading else "")
        parts += [head, (text or ch.text).strip(), ""]
    return "\n".join(parts).strip() + "\n"


def premise_evidence(items: list[Evidence]) -> list[Evidence]:
    """False-premise candidates: evidence with a value, preferring settings, numbers and limits."""
    for kinds in (FP_KINDS, None):
        out = [e for e in items if e.value and (kinds is None or e.kind in kinds)]
        if out:
            return out
    return []


async def topic_context(ctx: GenContext, value: str) -> TopicContext:
    from bob.clients.scaledown import compress  # A2

    members = topic_members(value, ctx.topics)
    if not members:
        raise ValueError(f"topic {value!r} is not in the job topics")
    pool = _topic_pool(ctx, members)
    if not pool:
        raise ValueError(f"topic {value!r} has no kept passages")
    texts = await asyncio.gather(*(compress(ctx.chunks[c].text, job=ctx.job, prompt=ctx.job.spec.goal) for c in pool))
    chunks = [ctx.chunks[c] for c in pool]
    return TopicContext(
        value=value,
        prefix=build_prefix(value, members, chunks, list(texts), ctx.docs),
        pool=pool,
        doc_of={c.id: c.doc_id for c in chunks},
        evidence=premise_evidence([e for c in pool for e in ctx.evidence.by_chunk(c)]),
    )


def writer_system(plan: Plan, seeds: list[list[Message]]) -> str:
    """Stable per job: writer.md + the plan system prompt + up to 2 real seed examples (style only)."""
    text = render(load_prompt("writer.md"), system_prompt=plan.system_prompt.strip())
    examples = []
    for s in seeds:
        user = next((m.content for m in s if m.role == "user"), "").strip()
        asst = next((m.content for m in s if m.role == "assistant"), "").strip()
        if user and asst:
            examples.append(f"USER: {user}\nASSISTANT: {asst}")
        if len(examples) == SEED_EXAMPLES:
            break
    if examples:
        text += (
            "\n## Style examples from the company\n\n"
            "Real conversations. Use them only for tone, length and the way customers write. "
            "Do not copy their content.\n\n" + "\n\n".join(examples) + "\n"
        )
    return text


# ---------- slots ----------
@dataclass
class Slot:
    coords: dict[str, str]  # all 4 axes
    focus: list[str]  # chunk ids to build the row on
    evidence: Evidence | None = None  # false_premise


def assign_focus(tc: TopicContext, coords: list[dict[str, str]], start: int = 0) -> list[Slot]:
    """Rotate the focus passages (and false-premise evidence items) over the pool, slot by slot."""
    slots = []
    for i, c in enumerate(coords):
        k = start + i
        first = tc.pool[k % len(tc.pool)]
        focus = [first]
        if c.get("difficulty") == "multi_doc":
            second = next(
                (x for x in tc.pool[k % len(tc.pool) :] + tc.pool if tc.doc_of[x] != tc.doc_of[first]), None
            )
            if second:
                focus.append(second)
        elif c.get("difficulty") == "multi_step" and len(tc.pool) > 1:
            focus.append(tc.pool[(k + 1) % len(tc.pool)])
        ev = None
        if c.get("case_type") == "false_premise" and tc.evidence:
            ev = tc.evidence[k % len(tc.evidence)]
            focus = [ev.chunk_id] + [x for x in focus if x != ev.chunk_id][:1]
        slots.append(Slot(coords=c, focus=focus, evidence=ev))
    return slots


def _axis_desc(plan: Plan, name: str, value: str) -> str:
    axis = next((a for a in plan.axes if a.name == name), None)
    desc = axis.descriptions.get(value, "") if axis else ""
    if not desc:
        desc = {**CASE_TYPE_DESCRIPTIONS, **DIFFICULTY_DESCRIPTIONS}.get(value, "")
    return f"{value}" + (f" ({desc})" if desc else "")


def batch_message(
    plan: Plan,
    case_type: str,
    slots: list[Slot],
    *,
    strict: bool,
    batch_no: int,
    round_no: int,
    avoid: list[str],
) -> str:
    parts = [load_prompt(f"writer_{case_type}.md")]
    if strict:
        parts.append(load_prompt("writer_strict.md"))
    lines = [
        "## Rows to write",
        "",
        f"Write {len(slots)} different rows, one for each slot (round {round_no}, batch {batch_no}).",
        "",
    ]
    for i, s in enumerate(slots, 1):
        lines.append(f"Slot {i}")
        if "persona" in s.coords:
            lines.append(f"- persona: {_axis_desc(plan, 'persona', s.coords['persona'])}")
        if "difficulty" in s.coords:
            lines.append(f"- difficulty: {_axis_desc(plan, 'difficulty', s.coords['difficulty'])}")
        lines.append("- focus passages: " + ", ".join(f"[{c}]" for c in s.focus))
        if s.evidence is not None:
            e = s.evidence
            lines.append(
                f'- evidence item: id={e.id}; kind={e.kind}; name="{e.name}"; right value="{e.value}"; '
                f'source text: "{" ".join(e.span_text.split())}"'
            )
        lines.append("")
    if avoid:
        lines.append("Earlier rows of this cell already start with these openings. Do not reuse them:")
        lines += [f'- "{o}"' for o in avoid[-AVOID_OPENINGS:]]
        lines.append("")
    parts.append("\n".join(lines))
    return "\n".join(p.strip() + "\n" for p in parts)


# ---------- parsing ----------
def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def opening(text: str, n_words: int = 4) -> str:
    return " ".join(text.split()[:n_words])


def absent_is_present(ctx: GenContext, absent: str, threshold: int) -> bool:
    """Code check: the absent topic must not be obviously in the top retrieved passages."""
    a = absent.lower().strip()
    return any(fuzz.partial_ratio(a, c.text.lower()) >= threshold for c in ctx.retriever.top_k(absent, k=3))


@dataclass
class BatchResult:
    rows: list[dict]
    cost_usd: float


async def call_writer(llm: LLMClient, job: Job, system: str, prefix: str, msg: str) -> BatchResult | None:
    """One Writer call. JSON parse failure: the client retries once, then raises -> drop. A reply with no
    usable rows: ask once more (changed message, so the response cache does not repeat it), then drop."""
    cost = 0.0
    for attempt in range(2):
        text = (
            msg if attempt == 0 else msg + "\nYour last reply had no usable rows. Return one row per slot.\n"
        )
        try:
            data, usage = await llm.complete_json(
                "writer", system, [Message(role="user", content=text)], WRITER_SCHEMA, cache_prefix=prefix
            )
        except LLMOutputError:
            return None
        cost += usage_cost_usd(job, "writer", usage)
        rows = data.get("rows")
        if isinstance(rows, list) and any(isinstance(r, dict) for r in rows):
            return BatchResult(rows=[r for r in rows if isinstance(r, dict)], cost_usd=cost)
    return None


def build_candidates(
    ctx: GenContext,
    cell: Cell,
    case_type: str,
    slots: list[Slot],
    result: BatchResult,
    tc: TopicContext,
    seen: set[str],
    batch_no: int,
) -> list[Candidate]:
    job = ctx.job
    s = settings_for(job)
    pool = set(tc.pool)
    by_slot: dict[int, dict] = {}
    for r in result.rows:
        try:
            k = int(r.get("slot"))
        except (TypeError, ValueError):
            continue
        if 1 <= k <= len(slots) and k not in by_slot:
            by_slot[k] = r
    out: list[Candidate] = []
    writer_model = model_for(job, "writer").model_id
    for k, r in sorted(by_slot.items()):
        slot = slots[k - 1]
        user, asst = str(r.get("user") or "").strip(), str(r.get("assistant") or "").strip()
        if not user or not asst or _norm(user) in seen:
            continue
        cited = [c for c in (r.get("chunk_ids") or []) if isinstance(c, str) and c in pool]
        absent = str(r.get("absent_topic") or "").strip() or None
        premise = None
        if case_type in ("partial", "unanswerable"):
            if not absent or absent_is_present(ctx, absent, s.absent_match):
                continue
        else:
            absent = None
        if case_type == "false_premise":
            pid = str(r.get("premise_evidence_id") or "").strip()
            ids = {e.id for e in tc.evidence}
            if pid not in ids:
                pid = slot.evidence.id if slot.evidence else ""
            if not pid:
                continue
            premise = pid
        seen.add(_norm(user))
        cid = hashlib.sha1(f"{job.id}|{cell.id}|{job.round}|{batch_no}|{k}|{user}".encode()).hexdigest()[:12]
        out.append(
            Candidate(
                id=cid,
                job_id=job.id,
                cell_id=cell.id,
                round=job.round,
                case_type=case_type,
                coords=dict(slot.coords),
                messages=[Message(role="user", content=user), Message(role="assistant", content=asst)],
                chunk_ids=cited or list(slot.focus),
                premise_evidence_id=premise,
                absent_topic=absent,
                writer_model=writer_model,
                cost_usd=0.0,
            )
        )
    for c in out:
        c.cost_usd = result.cost_usd / len(out)
    return out


def is_hard(cell: Cell) -> bool:
    return cell.generated > 0 and cell.rejected / cell.generated > HARD_CELL_REJECT_RATE


async def _log(ctx: GenContext, level: str, message: str) -> None:
    try:
        await ctx.emit("log", {"level": level, "message": message})
    except Exception:  # the event bus must not stop generation
        pass


# ---------- generate ----------
@dataclass
class _CellMemory:
    """In-process memory of one cell across generate() calls (A1 calls generate once per WRITER_BATCH).

    It only steers diversity (rotation offset, openings to avoid, exact-duplicate users). Losing it on a
    restart is harmless: durable state stays in the Store."""

    slots_done: int = 0
    calls: int = 0
    openings: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)


_cell_memory: dict[tuple[str, str], _CellMemory] = {}
_topic_tasks: dict[tuple[str, str, int], asyncio.Task] = {}


async def cached_topic_context(ctx: GenContext, value: str) -> TopicContext:
    """topic_context once per job, topic and GenContext (concurrent cells of one topic share it)."""
    key = (ctx.job.id, value, id(ctx))
    task = _topic_tasks.get(key)
    if task is None or (task.done() and task.exception() is not None):
        task = _topic_tasks[key] = asyncio.ensure_future(topic_context(ctx, value))
    return await task


def forget_job(job_id: str) -> None:
    """Drop the in-process generation memory of a finished job."""
    for k in [k for k in _cell_memory if k[0] == job_id]:
        del _cell_memory[k]
    for k in [k for k in _topic_tasks if k[0] == job_id]:
        del _topic_tasks[k]


async def generate(cell: Cell, plan: Plan, ctx: GenContext, n: int) -> list[Candidate]:
    """Up to n candidates for a cell, in batches of WRITER_BATCH different rows per Writer call.

    Each batch rotates the mix values by their weights, continuing the rotation of earlier calls for the
    cell; every Candidate.coords has all 4 axes. Partial and unanswerable rows carry absent_topic (checked
    against the Retriever); false_premise rows carry a real premise_evidence_id. Dropped rows (bad JSON,
    missing fields, a present absent topic) are not replaced in this call.
    """
    if n <= 0 or not cell.enabled:
        return []
    job = ctx.job
    s = settings_for(job)
    batch = max(1, s.writer_batch)
    llm = get_llm(job, "writer")
    system = writer_system(plan, ctx.seeds)
    strict = is_hard(cell)
    mem = _cell_memory.setdefault((job.id, cell.id), _CellMemory())
    offset = mem.slots_done
    mem.slots_done += n

    contexts: dict[str, TopicContext] = {}
    if "topic" in cell.coords:
        contexts[cell.coords["topic"]] = await cached_topic_context(ctx, cell.coords["topic"])
    multi_doc_ok = all(tc.multi_doc_ok for tc in contexts.values()) if contexts else True
    coords = mix_schedule(cell, plan, n, multi_doc_ok, offset=offset)
    for c in coords:  # a mix topic axis (unusual CELL_AXES) needs its own context
        if c["topic"] not in contexts:
            contexts[c["topic"]] = await cached_topic_context(ctx, c["topic"])

    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for c in coords:
        if c.get("case_type") not in CASE_TYPES:
            raise ValueError(f"cell {cell.id}: unknown case type {c.get('case_type')!r}")
        groups.setdefault((c["topic"], c["case_type"]), []).append(c)

    work: list[tuple[str, list[Slot], TopicContext]] = []
    base = int(cell.id[:6], 16) if re.fullmatch(r"[0-9a-f]{6}", cell.id[:6]) else 0
    for (topic, case_type), cs in groups.items():
        tc = contexts[topic]
        if case_type == "false_premise" and not tc.evidence:
            await _log(
                ctx, "warn", f"No evidence items with a value in topic {topic!r}: no false_premise rows."
            )
            continue
        slots = assign_focus(tc, cs, base + offset)
        for i in range(0, len(slots), batch):
            work.append((case_type, slots[i : i + batch], tc))

    errors: list[Exception] = []

    async def run(case_type: str, slots: list[Slot], tc: TopicContext) -> list[Candidate]:
        mem.calls += 1
        call_no = mem.calls
        msg = batch_message(
            plan,
            case_type,
            slots,
            strict=strict,
            batch_no=call_no,
            round_no=job.round,
            avoid=list(mem.openings),
        )
        try:
            res = await call_writer(llm, job, system, tc.prefix, msg)
        except LLMError as e:
            errors.append(e)
            await _log(ctx, "warn", f"Writer call failed for cell {cell.id}: {e}")
            return []
        if res is None:
            await _log(ctx, "warn", f"Writer batch dropped for cell {cell.id}: no valid JSON rows")
            return []
        cands = build_candidates(ctx, cell, case_type, slots, res, tc, mem.seen, call_no)
        mem.openings = (mem.openings + [opening(c.messages[0].content) for c in cands])[-AVOID_OPENINGS:]
        return cands

    out: list[Candidate] = []
    if work:  # first batch alone: it writes the prompt cache and gives openings to avoid
        out += await run(*work[0])
        for r in await asyncio.gather(*(run(*w) for w in work[1:])):
            out += r
    if work and not out and errors:
        raise errors[-1]
    return out[:n]


# ---------- DPO flawed twins (P1) ----------
def _span_chunks(ctx: GenContext, row: Row) -> list[str]:
    ids = list(getattr(row, "chunk_ids", None) or [])
    if ids:
        return [c for c in ids if c in ctx.chunks]
    out = []
    for sp in row.spans:
        for ch in ctx.chunks.values():
            if ch.doc_id == sp.doc_id and ch.start < sp.end and sp.start < ch.end and ch.id not in out:
                out.append(ch.id)
    return out


FLAWED_SCHEMA = {
    "type": "object",
    "properties": {
        "replies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"item": {"type": "integer"}, "assistant": {"type": "string"}},
                "required": ["item", "assistant"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["replies"],
    "additionalProperties": False,
}

_FLAW_HINTS = {
    "answerable": "add one plausible detail that the passages do not state",
    "partial": "also answer the uncovered part with invented details",
    "unanswerable": "answer confidently with invented details instead of abstaining",
    "false_premise": "accept the wrong assumption as true",
}


class FlawedDropped(ValueError):
    """The Writer gave no usable flawed reply for this row (bad JSON twice or missing item)."""


def flawed_message(ctx: GenContext, rows: list[Row]) -> str:
    parts = []
    for i, row in enumerate(rows, 1):
        user = next((m.content for m in row.messages if m.role == "user"), "")
        asst = next((m.content for m in row.messages if m.role == "assistant"), "")
        passages = []
        for cid in _span_chunks(ctx, row)[:4]:
            passages.append(f"[{cid}]\n{ctx.chunks[cid].text.strip()}")
        if not passages:
            passages = [sp.text.strip() for sp in row.spans[:4]]
        absent = getattr(row, "absent_topic", None)
        parts.append(
            "\n".join(
                [
                    f"## Item {i}",
                    f"Case type: {row.case_type} (flaw: {_FLAW_HINTS.get(row.case_type, '')})",
                    *([f"Uncovered part (absent_topic): {absent}"] if absent else []),
                    "",
                    "PASSAGES:",
                    "\n\n".join(passages) or "(none)",
                    "",
                    f"USER: {user}",
                    "",
                    f"CORRECT ASSISTANT REPLY: {asst}",
                ]
            )
        )
    return "\n\n".join(parts) + f"\n\nWrite {len(rows)} flawed replies, one per item.\n"


async def generate_flawed_batch(rows: list[Row], ctx: GenContext) -> list[Candidate | None]:
    """One Writer call for up to WRITER_BATCH rows: one flawed twin per row (None = dropped).

    Ledger bucket `writer` (the client records it); purpose `dpo`. The twin keeps the row's cell, coords and
    user turn, with the flawed reply as the assistant turn.
    """
    if not rows:
        return []
    job = ctx.job
    llm = get_llm(job, "writer")
    system = load_prompt("writer_flawed.md")
    msg = flawed_message(ctx, rows)
    data = None
    cost = 0.0
    for attempt in range(2):
        text = msg if attempt == 0 else msg + "Your last reply had no usable replies. Write one per item.\n"
        try:
            val, usage = await llm.complete_json(
                "writer", system, [Message(role="user", content=text)], FLAWED_SCHEMA, cache_prefix=""
            )
        except LLMOutputError:
            break
        cost += usage_cost_usd(job, "writer", usage)
        reps = val.get("replies")
        if isinstance(reps, list) and reps:
            data = reps
            break
    by_item: dict[int, str] = {}
    for r in data or []:
        if not isinstance(r, dict):
            continue
        try:
            k = int(r.get("item"))
        except (TypeError, ValueError):
            continue
        text = str(r.get("assistant") or "").strip()
        if 1 <= k <= len(rows) and text and k not in by_item:
            by_item[k] = text
    writer_model = model_for(job, "writer").model_id
    n_ok = max(1, len(by_item))
    out: list[Candidate | None] = []
    for k, row in enumerate(rows, 1):
        text = by_item.get(k)
        correct = next((m.content for m in row.messages if m.role == "assistant"), "")
        if not text or _norm(text) == _norm(correct):
            out.append(None)
            continue
        user = next(m for m in row.messages if m.role == "user")
        out.append(
            Candidate(
                id=hashlib.sha1(f"{row.id}|flawed".encode()).hexdigest()[:12],
                job_id=row.job_id,
                cell_id=row.cell_id,
                round=row.round,
                case_type=row.case_type,
                coords=dict(row.coords),
                messages=[
                    Message(role="user", content=user.content),
                    Message(role="assistant", content=text),
                ],
                chunk_ids=_span_chunks(ctx, row),
                premise_evidence_id=getattr(row, "premise_evidence_id", None),
                absent_topic=getattr(row, "absent_topic", None),
                writer_model=writer_model,
                cost_usd=cost / n_ok,
            )
        )
    return out


class _FlawedBatcher:
    """Collects concurrent generate_flawed() calls of one job into Writer calls of WRITER_BATCH rows."""

    def __init__(self, ctx: GenContext, size: int):
        self.ctx = ctx
        self.size = size
        self.pending: list[tuple[Row, asyncio.Future]] = []
        self.timer: asyncio.TimerHandle | None = None

    def add(self, row: Row) -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        self.pending.append((row, fut))
        if len(self.pending) >= self.size:
            self._flush()
        elif self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(0.05, self._flush)
        return fut

    def _flush(self) -> None:
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        items, self.pending = self.pending[: self.size], self.pending[self.size :]
        if self.pending:
            self.timer = asyncio.get_running_loop().call_later(0.05, self._flush)
        if items:
            asyncio.ensure_future(self._run(items))

    async def _run(self, items: list[tuple[Row, asyncio.Future]]) -> None:
        try:
            res = await generate_flawed_batch([r for r, _ in items], self.ctx)
            for (_, fut), cand in zip(items, res, strict=True):
                if not fut.done():
                    fut.set_result(cand)
        except Exception as e:
            for _, fut in items:
                if not fut.done():
                    fut.set_exception(e)


_batchers: dict[tuple[int, str], _FlawedBatcher] = {}


async def generate_flawed(row: Row, ctx: GenContext) -> Candidate:
    """DPO synthesize mode: one flawed reply to the SAME user turn (CONTRACTS section 4).

    Concurrent calls for one job share Writer calls of WRITER_BATCH rows (call them with asyncio.gather).
    Raises FlawedDropped when the Writer gives no usable reply for this row.
    """
    key = (id(asyncio.get_running_loop()), ctx.job.id)
    b = _batchers.get(key)
    if b is None or b.ctx is not ctx:
        b = _batchers[key] = _FlawedBatcher(ctx, max(1, settings_for(ctx.job).writer_batch))
    try:
        cand = await b.add(row)
    finally:
        if not b.pending and b.timer is None and _batchers.get(key) is b:
            _batchers.pop(key, None)
    if cand is None:
        raise FlawedDropped(f"no usable flawed reply for row {row.id}")
    return cand
