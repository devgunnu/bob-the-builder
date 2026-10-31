"""A4: verify.py pure code (tier 1, name matching, routing) on hand-written inputs. No provider calls."""

from __future__ import annotations

from a4_inputs import make_job

from bob.config import settings_for
from bob.core.models import CheckResult, Evidence, JobOptions, Message
from bob.pipeline.verify import (
    _DedupIndex,
    _Outcome,
    audit_draw,
    check_banned,
    check_dedup,
    check_format,
    check_numbers,
    confidence_of,
    content_failures,
    match_names,
    numbers_in,
    route,
    turn_hash,
)

U = "How long do I have to ask for a refund after I pay for the yearly plan?"
A = "You can ask for a refund within 30 days of payment. After that, our team can still review special cases."


def msgs(user: str = U, reply: str = A) -> list[Message]:
    return [Message(role="user", content=user), Message(role="assistant", content=reply)]


def test_format():
    assert check_format(msgs()).passed
    assert not check_format([Message(role="assistant", content=A), Message(role="user", content=U)]).passed
    assert not check_format(msgs(user="Refund?")).passed  # < 5 words
    assert "words" in check_format(msgs(reply="Yes.")).detail
    assert not check_format([Message(role="user", content=U)]).passed
    assert not check_format(msgs(reply="   ")).passed


def test_banned_phrases():
    assert check_banned(msgs()).passed
    for bad in (
        "According to the document, you get 30 days.",
        "As an AI I cannot say.",
        "In the provided context it is 30 days.",
    ):
        c = check_banned(msgs(reply=bad))
        assert not c.passed and "banned phrase" in c.detail


def test_number_normalization():
    assert numbers_in("1,000 rows and 1000 rows") == {"1000"}
    assert numbers_in("a 30-day window") == numbers_in("30 days") == {"30"}
    assert numbers_in("2.50 and 2.5 and 3.0") == {"2.5", "3"}
    assert numbers_in("1. Open settings\n2. Click save") == set()  # list markers
    assert numbers_in("v2 of the API") == set()


def test_numbers_check_rules():
    passages = ["Refunds are possible within 30 days of payment. Plans start at $1,000 per year."]
    ok = check_numbers(
        A, passage_texts=passages, evidence_numbers=set(), user=U, case_type="answerable", allow_user="all"
    )
    assert ok.passed
    bad = check_numbers(
        "You have 45 days.",
        passage_texts=passages,
        evidence_numbers=set(),
        user=U,
        case_type="answerable",
        allow_user="all",
    )
    assert not bad.passed and "'45'" in bad.detail
    assert check_numbers(
        "It costs 1000 dollars.",
        passage_texts=passages,
        evidence_numbers=set(),
        user=U,
        case_type="answerable",
        allow_user="none",
    ).passed
    # false premise: the reply repeats the user's wrong number
    user = "I read that I have 60 days to ask for a refund, is that right?"
    reply = "It is 30 days, not 60, from the payment date."
    for mode, case, want in [
        ("all", "false_premise", True),
        ("all", "answerable", True),
        ("false_premise", "false_premise", True),
        ("false_premise", "answerable", False),
        ("none", "false_premise", False),
    ]:
        c = check_numbers(
            reply, passage_texts=passages, evidence_numbers=set(), user=user, case_type=case, allow_user=mode
        )
        assert c.passed is want, (mode, case, c.detail)
    assert check_numbers(
        reply,
        passage_texts=[],
        evidence_numbers={"30"},
        user=user,
        case_type="false_premise",
        allow_user="all",
    ).passed


def test_dedup_exact_hash():
    idx = _DedupIndex(hashes={"c1": {turn_hash(U)}})
    c = check_dedup("c1", U.upper() + "!!", None, idx, _DedupIndex(), 0.92)
    assert not c.passed and "kept row" in c.detail
    assert check_dedup("c2", U, None, idx, _DedupIndex(), 0.92).passed  # other cell
    pending = _DedupIndex(hashes={"c2": {turn_hash(U)}})
    assert not check_dedup("c2", U, None, idx, pending, 0.92).passed


EVIDENCE = [
    Evidence(
        id="e1",
        chunk_id="k1",
        doc_id="d1",
        kind="feature",
        name="recurring invoices",
        span_text="recurring invoices",
        start=0,
        end=18,
        confidence=0.9,
    )
]


def find(name: str) -> list[Evidence]:
    return [e for e in EVIDENCE if e.name == name.lower()]


def test_extract_names_invented_feature_fails():
    c, _ = match_names(
        ["recurring invoices", "bulk PDF export"],
        find,
        case_type="answerable",
        absent_topic=None,
        exempt_absent=True,
        absent_match=85,
    )
    assert not c.passed
    assert c.detail.startswith("Mentions 'bulk PDF export', which is not in the docs")
    assert c.evidence_ids == ["e1"]


def test_extract_names_absent_topic_exemption():
    kw = dict(absent_topic="exporting invoices as bulk PDF export", exempt_absent=True, absent_match=85)
    c, _ = match_names(["bulk PDF export"], find, case_type="unanswerable", **kw)
    assert c.passed and "Exempt: 'bulk PDF export' is the absent topic" in c.detail
    assert match_names(["bulk PDF export"], find, case_type="partial", **kw)[0].passed
    # never for answerable or false_premise
    assert not match_names(["bulk PDF export"], find, case_type="answerable", **kw)[0].passed
    assert not match_names(["bulk PDF export"], find, case_type="false_premise", **kw)[0].passed
    # switched off per job
    kw["exempt_absent"] = False
    assert not match_names(["bulk PDF export"], find, case_type="unanswerable", **kw)[0].passed
    assert match_names([], find, case_type="answerable", **kw)[0].passed


def _outcome(case_p: tuple[float, float], shared_pass: bool = True, hard: bool = False) -> _Outcome:
    o = _Outcome()
    o.add(CheckResult(name="format", tier=1, passed=not hard, detail="Turn bad" if hard else "ok"), hard=True)
    if hard:
        return o
    o.add(CheckResult(name="jev.cell", tier=2, passed=shared_pass, detail="cell"), hard=False)
    for name, p in zip(("jev.supported", "jev.answers"), case_p, strict=True):
        c = CheckResult(name=name, tier=2, passed=p >= 0.9, score=p, detail=f"{name} p={p}")
        o.add(c, hard=False)
        o.case_checks.append((c, p))
    return o


def test_routing_rules():
    job = make_job()
    s = settings_for(job)
    assert route(_outcome((0.9, 0.9), hard=True), s, job.id, "x") == ("rejected", "Turn bad", False, False)
    r = route(_outcome((0.95, 0.2)), s, job.id, "x")
    assert r[0] == "rejected" and r[1] == "jev.answers p=0.2"
    r = route(_outcome((0.95, 0.5)), s, job.id, "x")
    assert r[0] == "judge" and r[2] is True  # soft fail, above REJECT_P
    r = route(_outcome((0.95, 0.95), shared_pass=False), s, job.id, "x")
    assert r[0] == "judge" and r[2] is True  # shared check fail goes to the judge too
    assert confidence_of(_outcome((0.95, 0.91))) == 0.91
    # all pass -> kept, except the audit share
    picks = [route(_outcome((0.95, 0.95)), s, job.id, f"c{i}") for i in range(2000)]
    audited = sum(p[3] for p in picks)
    assert all(p[0] == ("judge" if p[3] else "kept") for p in picks)
    assert 15 <= audited <= 70  # AUDIT_RATE 0.02 of 2000
    # per-job thresholds through settings_for
    s2 = settings_for(make_job(JobOptions(reject_p=0.6, audit_rate=0.0)))
    assert route(_outcome((0.95, 0.5)), s2, job.id, "x")[0] == "rejected"
    assert not any(route(_outcome((0.95, 0.95)), s2, job.id, f"c{i}")[3] for i in range(200))
    assert 0 <= audit_draw("j", "c") < 1 and audit_draw("j", "c") == audit_draw("j", "c")


def test_content_failures():
    checks = [
        CheckResult(name="format", tier=1, passed=False, detail=""),
        CheckResult(name="extract.names", tier=2, passed=False, detail=""),
        CheckResult(name="jev.supported", tier=2, passed=True, detail=""),
    ]
    assert content_failures(checks) == ["extract.names"]


def test_verbatim_name_match_does_not_depend_on_index():
    from types import SimpleNamespace

    from bob.core.models import Chunk
    from bob.pipeline.evidence import EvidenceIndex
    from bob.pipeline.verify import find_evidence_or_text

    chunk = Chunk(
        id="c", doc_id="d", uri="upload://d", text="The Role is documented.", start=10, end=33, n_tokens=5
    )
    ctx = SimpleNamespace(chunks={"c": chunk}, evidence=EvidenceIndex())
    hit = find_evidence_or_text("role", ctx)[0]
    assert hit.span_text == "Role"
    assert (hit.start, hit.end) == (14, 18)
    assert find_evidence_or_text("ole", ctx) == []
    chunk.kept = False
    assert find_evidence_or_text("Role", ctx) == []
