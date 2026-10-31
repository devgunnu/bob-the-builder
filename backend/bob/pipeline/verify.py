"""3-tier verification cascade (CONTRACTS section 4). Owner: A4.

Per candidate, in this order; the first hard fail stops the cascade:
  tier 1 (code, hard): format, banned_phrases, dedup, numbers
  tier 2: extract.names (hard, ScaleDown Extract + EvidenceIndex), then one Jev `decide()` call with exactly
          5 questions (soft: 3 shared + 2 for the case type)
  routing: hard fail -> rejected; confidence < REJECT_P -> rejected; all Jev pass -> kept (AUDIT_RATE of them
          go to tier 3 too); else tier 3
  tier 3: judge role model through get_llm(job, "judge"); its verdict is final.

Every threshold and mode comes from `settings_for(job)`. Two pass bars come from the CONTRACTS section 4 table
(not config vars): `jev.quality` >= 0.6 and `jev.realistic` >= 0.5.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import string
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rapidfuzz import fuzz, utils

from bob.config import EffectiveSettings, settings_for
from bob.core.models import (
    Candidate,
    CheckResult,
    Chunk,
    DPOPair,
    Evidence,
    GenContext,
    Message,
    Row,
    SpanRef,
)

if TYPE_CHECKING:
    import numpy as np

    from bob.clients.jev import Decision, Question

QUALITY_PASS = 0.6  # CONTRACTS section 4 table
REALISTIC_PASS = 0.5  # CONTRACTS section 4 table
USER_WORDS = (5, 300)
ASSISTANT_WORDS = (10, 400)

# checks that are not proof that a reply is wrong (DPO pairs need a content check)
NON_CONTENT_CHECKS = {"format", "dedup", "provider_error"}

JUDGE_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge.md"
JUDGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["keep", "reject"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,  # native JSON mode needs it set explicitly
}

# ScaleDown Extract schema for the assistant reply (CONTRACTS section 4).
REPLY_EXTRACT_KEYS = ("features", "settings", "urls", "limits")
REPLY_EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        k: {"type": "array", "items": {"type": "string"}, "description": d}
        for k, d in (
            ("features", "product features, tools, endpoints or options the reply names"),
            ("settings", "settings, parameters, flags or config fields the reply names"),
            ("urls", "URLs or paths the reply names"),
            ("limits", "limits, quotas, prices or numeric rules the reply names"),
        )
    },
}


# ---------------------------------------------------------------- text helpers
def turns(messages: list[Message], role: str) -> list[str]:
    return [m.content for m in messages if m.role == role]


def user_text(cand: Candidate) -> str:
    return "\n\n".join(turns(cand.messages, "user"))


def assistant_text(cand: Candidate) -> str:
    return "\n\n".join(turns(cand.messages, "assistant"))


def word_count(text: str) -> int:
    return len(text.split())


_PUNCT = str.maketrans("", "", string.punctuation)


def normalize_turn(text: str) -> str:
    return " ".join(text.lower().translate(_PUNCT).split())


def turn_hash(text: str) -> str:
    return hashlib.sha1(normalize_turn(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- tier 1
def check_format(messages: list[Message]) -> CheckResult:
    def fail(detail: str) -> CheckResult:
        return CheckResult(name="format", tier=1, passed=False, detail=detail)

    turns_ = [m for m in messages if m.role != "system"]
    if len(turns_) < 2:
        return fail("Needs a user turn then an assistant turn")
    for i, m in enumerate(turns_):
        want = "user" if i % 2 == 0 else "assistant"
        if m.role != want:
            return fail(f"Turn {i + 1} is '{m.role}', expected '{want}' (user then assistant)")
        if not m.content.strip():
            return fail(f"Turn {i + 1} ({m.role}) is empty")
    if turns_[-1].role != "assistant":
        return fail("The last turn must be the assistant reply")
    for m in turns_:
        lo, hi = USER_WORDS if m.role == "user" else ASSISTANT_WORDS
        n = word_count(m.content)
        if not lo <= n <= hi:
            return fail(f"The {m.role} turn has {n} words; allowed {lo} to {hi}")
    return CheckResult(name="format", tier=1, passed=True, detail="Valid user then assistant turns")


BANNED_PHRASES = [
    re.compile(r"\baccording to the (?:text|passage|document)s?\b", re.IGNORECASE),
    re.compile(r"\bas an ai\b", re.IGNORECASE),
    re.compile(r"\bin the provided context\b", re.IGNORECASE),
]


def check_banned(messages: list[Message]) -> CheckResult:
    for text in turns(messages, "assistant"):
        for pat in BANNED_PHRASES:
            m = pat.search(text)
            if m:
                return CheckResult(
                    name="banned_phrases",
                    tier=1,
                    passed=False,
                    detail=f"Uses the banned phrase '{m.group(0)}'",
                )
    return CheckResult(name="banned_phrases", tier=1, passed=True, detail="No banned phrases")


_LIST_MARKER = re.compile(r"(?m)^\s*\d{1,2}[.)]\s+")
_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")


def normalize_number(int_part: str, frac: str | None = None) -> str:
    """'1,000' -> '1000'; '007' -> '7'; '2.50' -> '2.5'; '3.0' -> '3'."""
    whole = int_part.replace(",", "").lstrip("0") or "0"
    frac = (frac or "").rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def numbers_in(text: str) -> set[str]:
    """Normalized numbers in text. '30-day' and '30 days' both give '30'; list markers ('1. ') are skipped."""
    text = _LIST_MARKER.sub(" ", text)
    return {normalize_number(m.group(1), m.group(2)) for m in _NUMBER.finditer(text)}


def check_numbers(
    reply: str,
    *,
    passage_texts: list[str],
    evidence_numbers: set[str],
    user: str,
    case_type: str,
    allow_user: str,
) -> CheckResult:
    found = numbers_in(reply)
    if not found:
        return CheckResult(name="numbers", tier=1, passed=True, detail="No numbers in the reply")
    allowed = set(evidence_numbers)
    for t in passage_texts:
        allowed |= numbers_in(t)
    user_ok = allow_user == "all" or (allow_user == "false_premise" and case_type == "false_premise")
    user_nums = numbers_in(user) if user_ok else set()
    missing = sorted(found - allowed - user_nums, key=lambda x: (len(x), x))
    if missing:
        listed = ", ".join(f"'{n}'" for n in missing)
        return CheckResult(
            name="numbers",
            tier=1,
            passed=False,
            detail=f"Number {listed} is not in the cited passages or the docs"
            if len(missing) == 1
            else f"Numbers {listed} are not in the cited passages or the docs",
        )
    from_user = sorted((found - allowed) & user_nums)
    detail = f"All {len(found)} numbers appear in the passages or the docs"
    if from_user:
        detail += "; from the user turn: " + ", ".join(f"'{n}'" for n in from_user)
    return CheckResult(name="numbers", tier=1, passed=True, detail=detail)


# ---------------------------------------------------------------- per-job verify state (lives on ctx)
@dataclass
class _DedupIndex:
    hashes: dict[str, set[str]] = field(default_factory=dict)  # cell_id -> user-turn hashes of kept rows
    vecs: dict[str, list[Any]] = field(default_factory=dict)  # cell_id -> embeddings of kept user turns


@dataclass
class _VerifyState:
    dedup: _DedupIndex
    judge_sem: asyncio.Semaphore
    evidence_numbers: set[str] | None = None
    evidence_by_id: dict[str, Evidence] | None = None


_STATE_ATTR = "_a4_verify_state"


def _state(ctx: GenContext, s: EffectiveSettings) -> _VerifyState:
    """Per-job state on the GenContext (it lives only inside run_job; never in module globals)."""
    st = getattr(ctx, _STATE_ATTR, None)
    if st is None:
        st = _VerifyState(dedup=_DedupIndex(), judge_sem=asyncio.Semaphore(max(1, s.judge_concurrency)))
        setattr(ctx, _STATE_ATTR, st)
    if st.evidence_by_id is None or len(st.evidence_by_id) != len(ctx.evidence.items):
        st.evidence_by_id = {e.id: e for e in ctx.evidence.items}
        nums: set[str] = set()
        for e in ctx.evidence.items:
            nums |= numbers_in(f"{e.value or ''} {e.span_text}")
        st.evidence_numbers = nums
    return st


async def register_kept(ctx: GenContext, rows: list[Row]) -> None:
    """Add kept rows to the dedup index (verify does this itself; A1 can call it for rows of an older run)."""
    kept = [r for r in rows if r.verdict == "kept"]
    if not kept:
        return
    st = _state(ctx, settings_for(ctx.job))
    texts = ["\n\n".join(turns(r.messages, "user")) for r in kept]
    vecs = await _embed(texts)
    for r, t, v in zip(kept, texts, vecs, strict=True):
        st.dedup.hashes.setdefault(r.cell_id, set()).add(turn_hash(t))
        st.dedup.vecs.setdefault(r.cell_id, []).append(v)


async def _embed(texts: list[str]) -> np.ndarray:
    from bob.pipeline.embed import embed  # A2

    return await asyncio.to_thread(embed, texts)


def check_dedup(
    cell_id: str, text: str, vec: Any, index: _DedupIndex, pending: _DedupIndex, cos_max: float
) -> CheckResult:
    import numpy as np

    h = turn_hash(text)
    if h in index.hashes.get(cell_id, set()):
        return CheckResult(
            name="dedup", tier=1, passed=False, detail="Same user message as a kept row in this cell"
        )
    if h in pending.hashes.get(cell_id, set()):
        return CheckResult(
            name="dedup", tier=1, passed=False, detail="Same user message as another row in this batch"
        )
    others = index.vecs.get(cell_id, []) + pending.vecs.get(cell_id, [])
    if others:
        sims = np.asarray(others) @ np.asarray(vec)
        best = float(sims.max())
        if best > cos_max:
            return CheckResult(
                name="dedup",
                tier=1,
                passed=False,
                score=round(best, 4),
                detail=f"Near-duplicate of a row in this cell (cosine {best:.2f} > {cos_max:.2f})",
            )
        score = round(best, 4)
    else:
        score = 0.0
    return CheckResult(name="dedup", tier=1, passed=True, score=score, detail="Not a duplicate in this cell")


# ---------------------------------------------------------------- tier 2: extract.names
def names_from_fields(fields: list[Any]) -> list[str]:
    """Names to check from ScaleDown ExtractField items (name = schema key, value = extracted item)."""
    keys = set(REPLY_EXTRACT_KEYS) | {k.rstrip("s") for k in REPLY_EXTRACT_KEYS}
    out: list[str] = []
    seen: set[str] = set()
    for f in fields:
        name = str(getattr(f, "name", "") or "").strip()
        value = str(getattr(f, "value", "") or "").strip()
        item = (value or str(getattr(f, "span_text", "") or "").strip()) if name.lower() in keys else name
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def find_evidence_or_text(name: str, ctx: GenContext) -> list[Evidence]:
    """Match indexed evidence or a verbatim occurrence in a kept source chunk.

    Extract is incomplete, so absence from its index alone does not mean a name is absent from the docs.
    A text match only establishes that the name occurs; the separate support checks assess the answer.
    """
    hits = ctx.evidence.find(name)
    if hits:
        return hits
    needle = name.strip()
    if not needle:
        return []
    for chunk in ctx.chunks.values():
        if not chunk.kept:
            continue
        pattern = (
            (r"(?<!\w)" if needle[0].isalnum() else "")
            + re.escape(needle)
            + (r"(?!\w)" if needle[-1].isalnum() else "")
        )
        match = re.search(pattern, chunk.text, re.IGNORECASE)
        if match:
            offset = match.start()
            span = match.group()
            return [
                Evidence(
                    id=f"text:{chunk.id}:{offset}",
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    kind="entity",
                    name=span,
                    span_text=span,
                    start=chunk.start + offset,
                    end=chunk.start + offset + len(span),
                    confidence=1.0,
                )
            ]
    return []


def match_names(
    names: list[str],
    find: Any,
    *,
    case_type: str,
    absent_topic: str | None,
    exempt_absent: bool,
    absent_match: int,
) -> tuple[CheckResult, list[Evidence]]:
    """extract.names on already-extracted names. `find(name) -> list[Evidence]` is EvidenceIndex.find."""
    matched: list[Evidence] = []
    exempt: list[str] = []
    missing: list[str] = []
    can_exempt = exempt_absent and case_type in ("unanswerable", "partial") and bool(absent_topic)
    for n in names:
        hits = find(n)
        if hits:
            matched.extend(hits)
        elif (
            can_exempt
            and fuzz.token_set_ratio(n, absent_topic, processor=utils.default_process) >= absent_match
        ):
            exempt.append(n)
        else:
            missing.append(n)
    ev_ids = list(dict.fromkeys(e.id for e in matched))
    exempt_note = "".join(f" Exempt: '{n}' is the absent topic." for n in exempt)
    if missing:
        detail = f"Mentions '{missing[0]}', which is not in the docs"
        if len(missing) > 1:
            detail += " (also " + ", ".join(f"'{n}'" for n in missing[1:]) + ")"
        return CheckResult(
            name="extract.names", tier=2, passed=False, detail=detail + "." + exempt_note, evidence_ids=ev_ids
        ), matched
    if not names:
        detail = "No feature, setting, URL or limit names in the reply."
    else:
        n_ok = len(names) - len(exempt)
        detail = f"{n_ok} of {len(names)} names match the docs." if n_ok else "No names to match."
    return CheckResult(
        name="extract.names", tier=2, passed=True, detail=(detail + exempt_note).strip(), evidence_ids=ev_ids
    ), matched


# ---------------------------------------------------------------- tier 2: Jev
SHARED_QUESTIONS = ("cell", "quality", "realistic")
CASE_QUESTIONS: dict[str, tuple[str, str]] = {
    "answerable": ("supported", "answers"),
    "partial": ("supported", "flags_gap"),
    "unanswerable": ("not_in_docs", "abstains"),
    "false_premise": ("contradicted", "corrects"),
}
QUALITY_LEVELS = ["unusable", "poor", "acceptable", "good", "excellent"]
NOUL_PROMPTS = {
    "realistic": "The USER message reads like a real person, not a test question.",
    "supported": "Every factual claim in the ASSISTANT reply is stated in the PASSAGES.",
    "answers": "The ASSISTANT reply directly resolves what the USER asked.",
    "flags_gap": "The ASSISTANT reply says which part the docs do not cover and offers a human handoff.",
    "not_in_docs": "The PASSAGES contain the answer to the USER question.",
    "abstains": (
        "The ASSISTANT reply says the docs do not cover this, offers a human handoff, and invents no details."
    ),
    "contradicted": "The PASSAGE contradicts the assumption in the USER message.",
    "corrects": "The ASSISTANT reply politely corrects the wrong assumption using the PASSAGE.",
}
NOUL_LABELS = {
    "realistic": "Reads like a real user",
    "supported": "Every claim is in the passages",
    "answers": "Answers the question",
    "flags_gap": "Names the uncovered part and offers a handoff",
    "not_in_docs": "Passages do not contain the answer",
    "abstains": "Says the docs do not cover it, offers a handoff, invents nothing",
    "contradicted": "Passage contradicts the user's assumption",
    "corrects": "Corrects the wrong assumption from the passage",
}


def topic_options(ctx: GenContext, cell_topic: str) -> list[str]:
    names = sorted({t.name for t in ctx.topics.values()} | {cell_topic})
    return names[:255]


def build_questions(case_type: str, topic_names: list[str]) -> list[Question]:
    """Exactly 5 questions: 3 shared + 2 for the case type (CONTRACTS section 4)."""
    from bob.clients.jev import Question  # A2

    if case_type not in CASE_QUESTIONS:
        raise ValueError(f"unknown case type {case_type!r}")
    qs = [
        Question(
            id="cell", type="choice", prompt="Which topic is the USER message about?", options=topic_names
        ),
        Question(
            id="quality",
            type="score",
            prompt="Rate the ASSISTANT reply as a support answer.",
            levels=QUALITY_LEVELS,
        ),
        Question(id="realistic", type="noul", prompt=NOUL_PROMPTS["realistic"]),
    ]
    for qid in CASE_QUESTIONS[case_type]:
        qs.append(Question(id=qid, type="noul", prompt=NOUL_PROMPTS[qid]))
    return qs


def build_state(passages: list[Chunk], user: str, assistant: str) -> str:
    blocks = []
    for i, ch in enumerate(passages, 1):
        head = f" ({ch.heading})" if ch.heading else ""
        blocks.append(f"[{i}]{head}\n{ch.text.strip()}")
    passages_text = "\n\n".join(blocks) if blocks else "(none)"
    return f"PASSAGES:\n{passages_text}\n\nUSER:\n{user.strip()}\n\nASSISTANT:\n{assistant.strip()}"


def jev_checks(
    case_type: str, decisions: dict[str, Decision], cell_topic: str, keep_p: float
) -> tuple[list[CheckResult], list[tuple[CheckResult, float]]]:
    """Jev Decisions -> CheckResults by the section 4 pass rules.

    Returns (all 5 checks, [(case-type check, pass-direction probability)]).
    """
    checks: list[CheckResult] = []
    case: list[tuple[CheckResult, float]] = []

    def need(qid: str) -> Decision:
        if qid not in decisions:
            raise KeyError(f"Jev returned no answer for question '{qid}'")
        return decisions[qid]

    d = need("cell")
    top = str(d.value)
    ok = top == cell_topic
    p_cell = (
        float(d.probs.get(cell_topic, d.prob if ok else 0.0)) if d.probs else float(d.prob if ok else 0.0)
    )
    checks.append(
        CheckResult(
            name="jev.cell",
            tier=2,
            passed=ok,
            score=round(p_cell, 4),
            detail=f"Jev: the user message is about '{top}' (p={d.prob:.2f})"
            + ("" if ok else f"; the cell topic is '{cell_topic}'"),
        )
    )
    d = need("quality")
    q = float(d.prob)
    checks.append(
        CheckResult(
            name="jev.quality",
            tier=2,
            passed=q >= QUALITY_PASS,
            score=round(q, 4),
            detail=f"Jev: reply quality {q:.2f} ('{d.value}'), needs >= {QUALITY_PASS:.2f}",
        )
    )
    d = need("realistic")
    p = float(d.prob)
    checks.append(
        CheckResult(
            name="jev.realistic",
            tier=2,
            passed=p >= REALISTIC_PASS,
            score=round(p, 4),
            detail=f"Jev: {NOUL_LABELS['realistic'].lower()} (p={p:.2f}, needs >= {REALISTIC_PASS:.2f})",
        )
    )
    for qid in CASE_QUESTIONS[case_type]:
        d = need(qid)
        p = float(d.prob)
        if qid == "not_in_docs":
            pass_p = 1.0 - p
            passed = p <= 1.0 - keep_p
            detail = f"Jev: passages contain the answer p={p:.2f}, needs <= {1.0 - keep_p:.2f}"
        else:
            pass_p = p
            passed = p >= keep_p
            detail = f"Jev: {NOUL_LABELS[qid].lower()} (p={p:.2f}, needs >= {keep_p:.2f})"
        c = CheckResult(name=f"jev.{qid}", tier=2, passed=passed, score=round(p, 4), detail=detail)
        checks.append(c)
        case.append((c, pass_p))
    return checks, case


# ---------------------------------------------------------------- passages and spans
def cited_chunks(cand: Candidate, ctx: GenContext) -> list[Chunk]:
    return [ctx.chunks[c] for c in dict.fromkeys(cand.chunk_ids) if c in ctx.chunks]


def jev_passages(cand: Candidate, ctx: GenContext, st: _VerifyState) -> list[Chunk]:
    """unanswerable: Retriever.top_k(user, 5); false_premise: the chunk with premise_evidence_id; else cited."""
    if cand.case_type == "unanswerable":
        return list(ctx.retriever.top_k(user_text(cand), 5))
    if cand.case_type == "false_premise" and cand.premise_evidence_id:
        ev = (st.evidence_by_id or {}).get(cand.premise_evidence_id)
        if ev is not None and ev.chunk_id in ctx.chunks:
            return [ctx.chunks[ev.chunk_id]]
    return cited_chunks(cand, ctx)


def build_spans(chunks: list[Chunk], evidence: list[Evidence], ctx: GenContext) -> list[SpanRef]:
    out: list[SpanRef] = []
    seen: set[tuple[str, int, int]] = set()

    def add(doc_id: str, start: int, end: int, text: str) -> None:
        key = (doc_id, start, end)
        if key in seen:
            return
        seen.add(key)
        doc = ctx.docs.get(doc_id)
        out.append(
            SpanRef(
                doc_id=doc_id,
                uri=doc.uri if doc else "",
                title=doc.title if doc else "",
                start=start,
                end=end,
                text=text,
            )
        )

    for ch in chunks:
        add(ch.doc_id, ch.start, ch.end, ch.text)
    for ev in evidence:
        add(ev.doc_id, ev.start, ev.end, ev.span_text)
    return out


# ---------------------------------------------------------------- cascade
@dataclass
class _Outcome:
    checks: list[CheckResult] = field(default_factory=list)
    hard_fail: CheckResult | None = None
    case_checks: list[tuple[CheckResult, float]] = field(default_factory=list)
    matched: list[Evidence] = field(default_factory=list)
    passages: list[Chunk] = field(default_factory=list)

    def add(self, c: CheckResult, *, hard: bool) -> bool:
        self.checks.append(c)
        if hard and not c.passed and self.hard_fail is None:
            self.hard_fail = c
        return c.passed


async def _log(ctx: GenContext, level: str, message: str) -> None:
    try:
        await ctx.emit("log", {"level": level, "message": message})
    except Exception:  # noqa: BLE001 - a log event must never break verification
        pass


def _tier1_static(cand: Candidate, o: _Outcome) -> None:
    if not o.add(check_format(cand.messages), hard=True):
        return
    o.add(check_banned(cand.messages), hard=True)


def _tier1_numbers(
    cand: Candidate, ctx: GenContext, s: EffectiveSettings, st: _VerifyState, o: _Outcome
) -> None:
    passage_texts = [c.text for c in cited_chunks(cand, ctx)]
    o.add(
        check_numbers(
            assistant_text(cand),
            passage_texts=passage_texts,
            evidence_numbers=st.evidence_numbers or set(),
            user=user_text(cand),
            case_type=cand.case_type,
            allow_user=s.numbers_allow_user,
        ),
        hard=True,
    )


async def _tier2(
    cand: Candidate, ctx: GenContext, s: EffectiveSettings, st: _VerifyState, o: _Outcome
) -> None:
    job = ctx.job
    reply = assistant_text(cand)
    if cand.case_type in s.extract_names_case_types:
        from bob.clients.scaledown import extract  # A2

        try:
            fields = await extract(reply, REPLY_EXTRACT_SCHEMA, "verify", job=job)
        except Exception as e:  # noqa: BLE001 - provider error: reject the row loudly, keep the job going
            await _log(ctx, "warn", f"verify: ScaleDown Extract failed on row {cand.id}: {e}")
            o.add(
                CheckResult(name="provider_error", tier=2, passed=False, detail=f"Extract failed: {e}"),
                hard=True,
            )
            return
        check, matched = match_names(
            names_from_fields(fields),
            lambda name: find_evidence_or_text(name, ctx),
            case_type=cand.case_type,
            absent_topic=cand.absent_topic,
            exempt_absent=s.extract_exempt_absent,
            absent_match=s.absent_match,
        )
        o.matched = matched
        if not o.add(check, hard=True):
            return

    from bob.clients.jev import decide  # A2

    cell_topic = cand.coords.get("topic", "")
    o.passages = jev_passages(cand, ctx, st)
    state = build_state(o.passages, user_text(cand), reply)
    try:
        decisions = await decide(
            state, build_questions(cand.case_type, topic_options(ctx, cell_topic)), "verify", job=job
        )
        checks, case = jev_checks(cand.case_type, decisions, cell_topic, s.keep_p)
    except Exception as e:  # noqa: BLE001
        await _log(ctx, "warn", f"verify: Jev failed on row {cand.id}: {e}")
        o.add(CheckResult(name="provider_error", tier=2, passed=False, detail=f"Jev failed: {e}"), hard=True)
        return
    for c in checks:
        o.add(c, hard=False)
    o.case_checks = case


def confidence_of(o: _Outcome) -> float:
    return round(min(p for _, p in o.case_checks), 4) if o.case_checks else 0.0


def audit_draw(job_id: str, cand_id: str) -> float:
    """Stable uniform [0, 1) per row, so a re-run with the cache makes the same audit picks."""
    h = hashlib.sha256(f"audit:{job_id}:{cand_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def route(o: _Outcome, s: EffectiveSettings, job_id: str, cand_id: str) -> tuple[str, str | None, bool, bool]:
    """-> (route, reject_reason, routed_to_judge, audited). route: kept | rejected | judge."""
    if o.hard_fail is not None:
        return "rejected", o.hard_fail.detail, False, False
    conf = confidence_of(o)
    if conf < s.reject_p:
        lowest = min(o.case_checks, key=lambda cp: cp[1])[0]
        return "rejected", lowest.detail, False, False
    jev = [c for c in o.checks if c.name.startswith("jev.")]
    if all(c.passed for c in jev):
        audited = audit_draw(job_id, cand_id) < s.audit_rate
        return ("judge" if audited else "kept"), None, False, audited
    return "judge", None, True, False


def _judge_input(cand: Candidate, o: _Outcome) -> str:
    passages = o.passages or []
    blocks = "\n\n".join(
        f"[{i}]{f' ({c.heading})' if c.heading else ''}\n{c.text.strip()}" for i, c in enumerate(passages, 1)
    )
    checks = "\n".join(
        f"- {c.name}: {'pass' if c.passed else 'fail'}"
        + (f" (score {c.score:.2f})" if c.score is not None else "")
        + f" - {c.detail}"
        for c in o.checks
    )
    extra = ""
    if cand.absent_topic:
        extra += f"\nABSENT TOPIC (what the docs should not cover): {cand.absent_topic}"
    convo = "\n".join(f"{m.role.upper()}: {m.content.strip()}" for m in cand.messages if m.role != "system")
    return (
        f"CASE TYPE: {cand.case_type}{extra}\n\nPASSAGES:\n{blocks or '(none)'}\n\n"
        f"ROW:\n{convo}\n\nAUTOMATIC CHECKS:\n{checks or '(none)'}"
    )


async def judge(cand: Candidate, o: _Outcome, ctx: GenContext, st: _VerifyState) -> CheckResult:
    """Tier 3. Returns a 'judge' CheckResult; passed = verdict keep. Provider errors -> reject with the error."""
    from bob.llm.client import get_llm  # A1

    system = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    msg = Message(role="user", content=_judge_input(cand, o))
    async with st.judge_sem:
        try:
            out, _usage = await get_llm(ctx.job, "judge").complete_json("judge", system, [msg], JUDGE_SCHEMA)
        except Exception as e:  # noqa: BLE001
            await _log(ctx, "warn", f"verify: judge failed on row {cand.id}: {e}")
            return CheckResult(name="judge", tier=3, passed=False, detail=f"Judge call failed: {e}")
    verdict = str(out.get("verdict", "")).strip().lower()
    reason = str(out.get("reason", "")).strip() or "(no reason given)"
    if verdict not in ("keep", "reject"):
        return CheckResult(name="judge", tier=3, passed=False, detail=f"Judge gave no valid verdict: {out}")
    return CheckResult(
        name="judge", tier=3, passed=verdict == "keep", detail=f"Judge: {verdict}. {reason}", score=None
    )


def _row(
    cand: Candidate,
    o: _Outcome,
    ctx: GenContext,
    *,
    verdict: str,
    reason: str | None,
    routed: bool,
    audited: bool,
) -> Row:
    chunks = cited_chunks(cand, ctx)
    evidence = list(o.matched)
    st = getattr(ctx, _STATE_ATTR, None)
    if cand.premise_evidence_id and st and st.evidence_by_id:
        ev = st.evidence_by_id.get(cand.premise_evidence_id)
        if ev is not None:
            evidence.append(ev)
    return Row(
        id=cand.id,
        job_id=cand.job_id,
        cell_id=cand.cell_id,
        coords=dict(cand.coords),
        case_type=cand.case_type,
        round=cand.round,
        messages=list(cand.messages),
        chunk_ids=list(cand.chunk_ids),
        absent_topic=cand.absent_topic,
        premise_evidence_id=cand.premise_evidence_id,
        spans=build_spans(chunks, evidence, ctx),
        checks=list(o.checks),
        confidence=confidence_of(o),
        verdict=verdict,  # type: ignore[arg-type]
        reject_reason=reason,
        routed_to_judge=routed,
        audited=audited,
        cost_usd=cand.cost_usd,
        created_at=datetime.now(UTC),
    )


async def verify(cands: list[Candidate], ctx: GenContext) -> list[Row]:
    """Run the cascade on a batch (usually one cell). Returns one Row per candidate, same order."""
    if not cands:
        return []
    s = settings_for(ctx.job)
    st = _state(ctx, s)
    outs = [_Outcome() for _ in cands]

    # tier 1: format, banned_phrases
    for c, o in zip(cands, outs, strict=True):
        _tier1_static(c, o)

    # tier 1: dedup (one embed call for the batch; earlier survivors in the batch count too)
    live = [i for i, o in enumerate(outs) if o.hard_fail is None]
    if live:
        vecs = await _embed([user_text(cands[i]) for i in live])
        pending = _DedupIndex()
        for i, v in zip(live, vecs, strict=True):
            c = cands[i]
            if outs[i].add(
                check_dedup(c.cell_id, user_text(c), v, st.dedup, pending, s.dedup_cos), hard=True
            ):
                pending.hashes.setdefault(c.cell_id, set()).add(turn_hash(user_text(c)))
                pending.vecs.setdefault(c.cell_id, []).append(v)
        vec_of = dict(zip(live, vecs, strict=True))
    else:
        vec_of = {}

    # tier 1: numbers
    for c, o in zip(cands, outs, strict=True):
        if o.hard_fail is None:
            _tier1_numbers(c, ctx, s, st, o)

    # tier 2
    await asyncio.gather(
        *(_tier2(c, ctx, s, st, o) for c, o in zip(cands, outs, strict=True) if o.hard_fail is None)
    )

    # routing + tier 3
    routes = [route(o, s, ctx.job.id, c.id) for c, o in zip(cands, outs, strict=True)]
    to_judge = [i for i, r in enumerate(routes) if r[0] == "judge"]
    verdicts = await asyncio.gather(*(judge(cands[i], outs[i], ctx, st) for i in to_judge))
    judged = dict(zip(to_judge, verdicts, strict=True))

    rows: list[Row] = []
    for i, (c, o) in enumerate(zip(cands, outs, strict=True)):
        r_route, reason, routed, audited = routes[i]
        if i in judged:
            jc = judged[i]
            o.checks.append(jc)
            verdict = "kept" if jc.passed else "rejected"
            reason = None if jc.passed else jc.detail
        else:
            verdict = r_route
        rows.append(_row(c, o, ctx, verdict=verdict, reason=reason, routed=routed, audited=audited))

    # kept rows join the dedup index for later batches
    for i, row in enumerate(rows):
        if row.verdict == "kept" and i in vec_of:
            st.dedup.hashes.setdefault(row.cell_id, set()).add(turn_hash(user_text(cands[i])))
            st.dedup.vecs.setdefault(row.cell_id, []).append(vec_of[i])
    return rows


async def check_flawed(cand: Candidate, ctx: GenContext) -> list[CheckResult]:
    """DPO: tier 1 (no dedup: the twin repeats the user turn on purpose) + tier 2 only; no judge, no audit."""
    s = settings_for(ctx.job)
    st = _state(ctx, s)
    o = _Outcome()
    _tier1_static(cand, o)
    if o.hard_fail is None:
        _tier1_numbers(cand, ctx, s, st, o)
    if o.hard_fail is None:
        await _tier2(cand, ctx, s, st, o)
    return o.checks


def content_failures(checks: list[CheckResult]) -> list[str]:
    """Names of failed content checks (not format, dedup or a provider error)."""
    return [c.name for c in checks if not c.passed and c.name not in NON_CONTENT_CHECKS]


# ---------------------------------------------------------------- DPO pairs (CONTRACTS section 4, D30)
def dpo_draw(job_id: str, row_id: str) -> float:
    """Stable uniform [0, 1) per row for the DPO_RATE sample."""
    h = hashlib.sha256(f"dpo:{job_id}:{row_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _pair_id(row_id: str, mode: str, other: str = "") -> str:
    return hashlib.sha1(f"{mode}:{row_id}:{other}".encode()).hexdigest()[:12]


def _prompt(row: Row) -> list[Message]:
    msgs = [m for m in row.messages if m.role != "system"]
    return msgs[:-1] if msgs and msgs[-1].role == "assistant" else msgs


def _user_key(row: Row) -> tuple[str, str]:
    return row.cell_id, turn_hash("\n\n".join(turns(row.messages, "user")))


def natural_pairs(rows: list[Row]) -> list[DPOPair]:
    """DPO_MODE=pair: in one cell, a kept reply + a reply rejected by a content check, same normalized user turn."""
    rejected: dict[tuple[str, str], list[Row]] = {}
    for r in rows:
        if r.verdict == "rejected" and content_failures(r.checks):
            rejected.setdefault(_user_key(r), []).append(r)
    pairs: list[DPOPair] = []
    for r in rows:
        if r.verdict != "kept":
            continue
        for bad in rejected.get(_user_key(r), []):
            pairs.append(
                DPOPair(
                    id=_pair_id(r.id, "natural", bad.id),
                    row_id=r.id,
                    mode="natural",
                    prompt=_prompt(r),
                    chosen=turns(r.messages, "assistant")[-1],
                    rejected=turns(bad.messages, "assistant")[-1],
                    rejection_reason=bad.reject_reason or "",
                    rejected_checks=content_failures(bad.checks),
                )
            )
    return pairs


def synthesized_pair(row: Row, flawed: Candidate, checks: list[CheckResult]) -> DPOPair | None:
    """Keep the pair only when a content check rejects the flawed twin (not format, dedup or a provider error)."""
    fmt = next((c for c in checks if c.name == "format"), None)
    if fmt is not None and not fmt.passed:
        return None  # a malformed twin is no proof
    failed = content_failures(checks)
    if not failed:
        return None  # the checks did not catch the flaw: drop the pair
    first = next(c for c in checks if c.name == failed[0])
    return DPOPair(
        id=_pair_id(row.id, "synthesized"),
        row_id=row.id,
        mode="synthesized",
        prompt=_prompt(row),
        chosen=turns(row.messages, "assistant")[-1],
        rejected=assistant_text(flawed),
        rejection_reason=first.detail,
        rejected_checks=failed,
    )


async def build_dpo_pairs(rows: list[Row], ctx: GenContext) -> list[DPOPair]:
    """DPO pairs by DPO_MODE: synthesize (A3 generate_flawed + tier 1/2 proof) | pair (natural) | off."""
    s = settings_for(ctx.job)
    if s.dpo_mode == "off":
        return []
    if s.dpo_mode == "pair":
        return natural_pairs(rows)

    from bob.core import ledger  # A1
    from bob.pipeline.generate import generate_flawed  # A3

    job = ctx.job
    sample = [r for r in rows if r.verdict == "kept" and dpo_draw(job.id, r.id) < s.dpo_rate]
    sem = asyncio.Semaphore(max(1, s.writer_concurrency))
    budget_hit = False

    async def one(row: Row) -> DPOPair | None:
        nonlocal budget_hit
        async with sem:
            if ledger.total_usd(job.id) >= 0.95 * job.spec.budget_usd:  # budget guard
                if not budget_hit:
                    budget_hit = True
                    await _log(ctx, "warn", "dpo: budget guard reached; no more flawed twins")
                return None
            try:
                flawed = await generate_flawed(row, ctx)
            except Exception as e:  # noqa: BLE001 - one failed twin must not stop the job
                await _log(ctx, "warn", f"dpo: generate_flawed failed on row {row.id}: {e}")
                return None
        return synthesized_pair(row, flawed, await check_flawed(flawed, ctx))

    results = await asyncio.gather(*(one(r) for r in sample))
    return [p for p in results if p is not None]
