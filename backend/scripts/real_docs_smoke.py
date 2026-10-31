import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from bob.config import default_bedrock_access, default_model_roles
from bob.core import ledger
from bob.core.models import Document, GenContext, Job, JobSpec, SourceSpec
from bob.export import export
from bob.pipeline.chunk import chunk_documents
from bob.pipeline.evidence import Retriever, build_evidence
from bob.pipeline.generate import generate
from bob.pipeline.planner import propose_plan
from bob.pipeline.topics import build_topics
from bob.pipeline.verify import verify


async def main():
    text = Path("../.agents/quality/behavior-brief.md").read_text(encoding="utf-8")
    now = datetime.now(UTC)
    doc = Document(
        id="repo-doc",
        source_kind="upload",
        uri="upload://behavior-brief.md",
        title="Bob behavior brief",
        text=text,
        content_hash=hashlib.sha1(text.encode()).hexdigest(),
        fetched_at=now,
    )
    spec = JobSpec(
        goal="Help explain the Bob behavior brief accurately",
        sources=[SourceSpec(kind="upload", upload_ids=["repo-doc"])],
        target_rows=4,
        budget_usd=2,
    )
    job = Job(
        id="real-doc-integration",
        spec=spec,
        owner_id="local",
        models=default_model_roles(),
        bedrock=default_bedrock_access(),
        created_at=now,
        updated_at=now,
    )
    ledger.register_job(job)
    chunks = chunk_documents([doc])
    print("chunk", len(chunks), flush=True)
    topics = await build_topics(chunks, spec.goal, job=job)
    print("topics", len(topics), flush=True)
    evidence = await build_evidence(chunks, job=job)
    print("evidence", len(evidence.items), flush=True)
    chunk_map = {c.id: c for c in chunks}
    topic_map = {t.id: t for t in topics}
    plan = await propose_plan(
        spec.goal, topics, [], spec.target_rows, spec.budget_usd, job=job, chunks=chunk_map
    )
    job.plan = plan
    print("plan", len(plan.cells), flush=True)

    async def emit(*args):
        pass

    ctx = GenContext(
        job=job,
        docs={doc.id: doc},
        chunks=chunk_map,
        topics=topic_map,
        evidence=evidence,
        retriever=Retriever(chunks),
        seeds=[],
        emit=emit,
    )
    cell = next(c for c in plan.cells if c.coords.get("case_type") == "answerable")
    candidates = await generate(cell, plan, ctx, 3)
    print("generate", len(candidates), flush=True)
    if not candidates:
        raise RuntimeError("Writer produced zero candidates")
    rows = await verify(candidates, ctx)
    print("verify", len(rows), "kept", sum(r.verdict == "kept" for r in rows), flush=True)
    [
        print(
            "REJECTION",
            r.reject_reason,
            [(c.name, c.passed, c.detail) for c in r.checks if not c.passed],
            flush=True,
        )
        for r in rows
    ]
    files = export(job, rows, [], "full", ["jsonl"], out_dir=Path("../runs/real-doc-integration/export"))
    print("export", len(files), "files", flush=True)
    if not any(r.verdict == "kept" for r in rows):
        raise RuntimeError("No verified kept rows; export is empty")
    print("cost_usd", ledger.total_usd(job.id), flush=True)


asyncio.run(main())
