"""Hand-written A4 test inputs (real code, hand-made rows; no fake provider responses). Owner: A4."""

from __future__ import annotations

from datetime import UTC, datetime

from bob.config import default_model_roles
from bob.core.models import (
    Axis,
    Cell,
    CheckResult,
    DPOPair,
    Job,
    JobOptions,
    JobSpec,
    Message,
    Plan,
    Row,
    SourceSpec,
    SpanRef,
)

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
SYSTEM = "You are the first-reply support assistant for Firecrawl. Use only the docs."

TOPICS = ["Rate limits", "Crawling"]
CASES = ["answerable", "unanswerable"]


def cell_id(topic: str, case: str) -> str:
    return f"{topic[:4].lower()}-{case[:3]}"


def make_plan(target: int = 6) -> Plan:
    cells = [
        Cell(id=cell_id(t, c), coords={"topic": t, "case_type": c}, target=target)
        for t in TOPICS
        for c in CASES
    ]
    return Plan(
        goal="First-reply support assistant for Firecrawl",
        system_prompt=SYSTEM,
        axes=[
            Axis(name="topic", values=TOPICS),
            Axis(name="case_type", values=CASES),
            Axis(name="persona", values=["Developer", "Founder"], role="mix", weights={"Developer": 0.5}),
            Axis(name="difficulty", values=["single_fact", "multi_step"], role="mix"),
        ],
        cells=cells,
        target_rows=target * len(cells),
        est_cost_usd=1.0,
    )


def make_job(options: JobOptions | None = None, job_id: str = "jobA4") -> Job:
    spec = JobSpec(
        goal="First-reply support assistant for Firecrawl",
        sources=[SourceSpec(kind="upload", upload_ids=["u1"])],
        target_rows=24,
        preset="openai-chat",
        formats=["jsonl", "parquet"],
        options=options or JobOptions(),
    )
    return Job(
        id=job_id,
        spec=spec,
        owner_id="local",
        models=default_model_roles(),
        plan=make_plan(),
        created_at=NOW,
        updated_at=NOW,
    )


def _checks(case: str, verdict: str, *, judged: str | None = None) -> list[CheckResult]:
    checks = [
        CheckResult(name="format", tier=1, passed=True, detail="ok"),
        CheckResult(name="banned_phrases", tier=1, passed=True, detail="ok"),
        CheckResult(name="dedup", tier=1, passed=True, detail="ok"),
        CheckResult(name="numbers", tier=1, passed=True, detail="ok"),
        CheckResult(name="extract.names", tier=2, passed=True, detail="ok"),
        CheckResult(name="jev.cell", tier=2, passed=True, score=0.9, detail="ok"),
        CheckResult(name="jev.quality", tier=2, passed=True, score=0.8, detail="ok"),
        CheckResult(name="jev.realistic", tier=2, passed=True, score=0.8, detail="ok"),
    ]
    good = verdict == "kept" or judged is not None
    a, b = ("supported", "answers") if case == "answerable" else ("not_in_docs", "abstains")
    checks.append(CheckResult(name=f"jev.{a}", tier=2, passed=good, score=0.95, detail=f"jev.{a} detail"))
    checks.append(CheckResult(name=f"jev.{b}", tier=2, passed=True, score=0.95, detail=f"jev.{b} detail"))
    if judged is not None:
        checks.append(
            CheckResult(name="judge", tier=3, passed=judged == "keep", detail=f"Judge: {judged}. x")
        )
    return checks


def make_row(
    i: int,
    topic: str,
    case: str,
    verdict: str = "kept",
    *,
    persona: str = "Developer",
    difficulty: str = "single_fact",
    round_: int = 1,
    judged: str | None = None,
    routed: bool = False,
    audited: bool = False,
    reject_check: str | None = None,
) -> Row:
    checks = _checks(case, verdict, judged=judged)
    reason = None
    if verdict == "rejected":
        if judged == "reject":
            reason = checks[-1].detail
        elif reject_check:
            for c in checks:
                if c.name == reject_check:
                    c.passed = False
                    c.detail = f"{reject_check} failed on row {i}"
                    reason = c.detail
                    break
            else:
                checks.insert(
                    0, CheckResult(name=reject_check, tier=1, passed=False, detail=f"{reject_check} {i}")
                )
                reason = checks[0].detail
            if reject_check in ("format", "dedup", "numbers", "banned_phrases", "extract.names"):
                idx = next(k for k, c in enumerate(checks) if c.name == reject_check)
                checks = checks[: idx + 1]
        else:
            failing = next(c for c in checks if not c.passed)
            reason = failing.detail
    user = f"Hi, how many pages can I crawl per minute on the free plan? question {i} about {topic}"
    reply = f"On the free plan you can crawl 10 pages per minute. Row {i} keeps to the docs for {topic}."
    return Row(
        id=f"r{i:03d}",
        job_id="jobA4",
        cell_id=cell_id(topic, case),
        coords={"topic": topic, "case_type": case, "persona": persona, "difficulty": difficulty},
        case_type=case,
        round=round_,
        messages=[Message(role="user", content=user), Message(role="assistant", content=reply)],
        spans=[
            SpanRef(
                doc_id="d1", uri="upload://rate-limits.md", title="Rate limits", start=0, end=20, text="x"
            )
        ],
        checks=checks,
        confidence=0.95 if verdict == "kept" else 0.5,
        verdict=verdict,  # type: ignore[arg-type]
        reject_reason=reason,
        routed_to_judge=routed,
        audited=audited,
        cost_usd=0.001,
        created_at=NOW,
    )


def make_rows() -> list[Row]:
    rows: list[Row] = []
    i = 0
    for t in TOPICS:
        for c in CASES:
            for k in range(5):
                rows.append(
                    make_row(
                        i, t, c, persona="Developer" if k % 2 == 0 else "Founder", round_=1 if k < 4 else 2
                    )
                )
                i += 1
    rows.append(make_row(i, "Rate limits", "answerable", "rejected", reject_check="dedup"))
    i += 1
    rows.append(make_row(i, "Rate limits", "answerable", "rejected", reject_check="extract.names"))
    i += 1
    rows.append(make_row(i, "Crawling", "unanswerable", "rejected", routed=True, judged="reject"))
    i += 1
    rows.append(make_row(i, "Crawling", "unanswerable", "kept", routed=True, judged="keep"))
    i += 1
    rows.append(make_row(i, "Crawling", "answerable", "kept", audited=True, judged="keep"))
    return rows


def make_pair(row: Row) -> DPOPair:
    return DPOPair(
        id=f"p-{row.id}",
        row_id=row.id,
        mode="synthesized",
        prompt=[m for m in row.messages if m.role == "user"],
        chosen=row.messages[-1].content,
        rejected="You can crawl 500 pages per minute and export to bulk PDF.",
        rejection_reason="Mentions 'bulk PDF', which is not in the docs",
        rejected_checks=["extract.names"],
    )
