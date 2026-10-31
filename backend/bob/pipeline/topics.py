"""Topics: k-means on chunk embeddings, names by the writer model, briefs by ScaleDown Summarize.
CONTRACTS section 3. Owner: A2.

k = clamp(round(sqrt(n)), 4, MAX_TOPICS), never more than n. One `get_llm(job, "writer")` JSON call per
cluster (3 sample chunks nearest to the centroid + the goal) gives name + one-line description. A model
output error (LLMOutputError) drops the name, and the topic uses the heading of its nearest chunk.
ScaleDown Summarize per topic gives `brief` (<= 1,000 tokens). Sets `Chunk.topic_id` in place.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math

import numpy as np

from bob.clients import scaledown
from bob.clients.jev import emit_log, strict_schema
from bob.config import settings_for
from bob.core.models import Chunk, Job, Message, Topic
from bob.llm.client import current_job, get_llm
from bob.pipeline.embed import aembed

log = logging.getLogger(__name__)

MIN_K = 4
SAMPLES = 3
BRIEF_INPUT_CHARS = 24_000  # Summarize input per topic: the chunks nearest to the centroid first
BRIEF_INSTRUCTIONS = (
    "Write a factual brief of these documentation passages for a writer who makes support questions. "
    "Keep product names, settings, limits, numbers and steps exactly as written. At most 600 words."
)

NAME_SYSTEM = (
    "You name groups of documentation passages. Give a short, human-readable topic name (1 to 4 words, "
    "for example 'Refunds' or 'API keys') and a one-line description of what the passages cover. "
    "Use only what the passages say."
)
NAME_SCHEMA = strict_schema(
    {
        "type": "object",
        "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
    }
)


def choose_k(n: int, max_topics: int) -> int:
    if n <= 0:
        return 0
    return min(n, max(MIN_K, min(max_topics, round(math.sqrt(n)))))


def cluster(vecs: np.ndarray, k: int) -> np.ndarray:
    from sklearn.cluster import KMeans

    if k <= 1:
        return np.zeros(len(vecs), dtype=int)
    return KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(vecs)


async def _name(job: Job, goal: str, samples: list[Chunk]) -> tuple[str, str] | None:
    from bob.llm.bedrock import LLMOutputError

    passages = "\n\n".join(
        f"PASSAGE {i + 1} ({c.heading or 'no heading'}):\n{c.text[:2000]}" for i, c in enumerate(samples)
    )
    msg = Message(role="user", content=f"GOAL: {goal}\n\n{passages}")
    try:
        data, _ = await get_llm(job, "writer").complete_json("writer", NAME_SYSTEM, [msg], NAME_SCHEMA)
    except LLMOutputError as e:
        log.warning("topic name dropped: %s", e)
        return None
    name, desc = str(data.get("name", "")).strip(), str(data.get("description", "")).strip()
    return (name, desc) if name else None


async def _brief(job: Job, name: str, members: list[Chunk]) -> str:
    parts, size = [], 0
    for c in members:
        if size + len(c.text) > BRIEF_INPUT_CHARS and parts:
            break
        parts.append(c.text)
        size += len(c.text)
    try:
        return await scaledown.summarize(
            "\n\n".join(parts), "topics", f"Topic: {name}. {BRIEF_INSTRUCTIONS}", job=job
        )
    except Exception as e:  # a brief is optional context; the topic stays
        await emit_log(job, "warn", f"topic brief for {name!r} failed: {type(e).__name__}: {e}")
        return ""


async def build_topics(chunks: list[Chunk], goal: str, *, job: Job | None = None) -> list[Topic]:
    """Topics over the kept chunks. Sets `topic_id` on each kept chunk (in place)."""
    job = job or current_job()
    kept = [c for c in chunks if c.kept]
    k = choose_k(len(kept), settings_for(job).max_topics)
    if k == 0:
        return []
    vecs = await aembed([f"{c.heading or ''}\n{c.text}" for c in kept])
    labels = await asyncio.to_thread(cluster, vecs, k)

    groups: list[list[int]] = [[] for _ in range(k)]
    for i, lab in enumerate(labels):
        groups[int(lab)].append(i)
    groups = [g for g in groups if g]
    ordered: list[list[Chunk]] = []
    for g in groups:
        centroid = vecs[g].mean(axis=0)
        sims = vecs[g] @ centroid
        ordered.append([kept[g[j]] for j in np.argsort(-sims)])

    names = await asyncio.gather(*(_name(job, goal, members[:SAMPLES]) for members in ordered))
    topics: list[Topic] = []
    used: set[str] = set()
    for members, nd in zip(ordered, names, strict=True):
        name, desc = nd or ((members[0].heading or "General").split(" > ")[-1], "")
        base, n = name, 2
        while name.lower() in used:
            name, n = f"{base} ({n})", n + 1
        used.add(name.lower())
        ids = [c.id for c in members]
        tid = hashlib.sha1(",".join(sorted(ids)).encode()).hexdigest()[:10]
        for c in members:
            c.topic_id = tid
        topics.append(Topic(id=tid, name=name, description=desc, chunk_ids=ids))

    briefs = await asyncio.gather(*(_brief(job, t.name, m) for t, m in zip(topics, ordered, strict=True)))
    for t, b in zip(topics, briefs, strict=True):
        t.brief = b
    return topics


__all__ = ["build_topics", "choose_k", "cluster"]
