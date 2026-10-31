"""Evidence index with verbatim spans, and the chunk Retriever (CONTRACTS section 3). Owner: A2.

`build_evidence`: ScaleDown Extract per kept chunk with the evidence schema (CONTRACTS section 5). Every
field is validated in code: `span_text` must be a verbatim substring of the chunk, and the offsets are
document offsets (`chunk.start + offset in chunk.text`), so `doc.text[start:end] == span_text` always holds.
A field that is not found is dropped. The Extract fallback (fallback model) runs inside `scaledown.extract`.

`EvidenceIndex.find(name)`: normalize (lowercase, strip punctuation, simple singular), then rapidfuzz
`token_set_ratio >= 90`. `Retriever.top_k`: embedding cosine, optional topic filter.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re

import numpy as np
from rapidfuzz import fuzz

from bob.clients import scaledown
from bob.clients.jev import emit_log
from bob.core.models import Chunk, Evidence, Job
from bob.llm.client import current_job
from bob.pipeline.embed import embed

log = logging.getLogger(__name__)

FIND_MIN = 90

_NAME = {"type": "object", "properties": {"name": {"type": "string"}}}
_NAME_VALUE = {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}}}
EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "features": {
            "type": "array",
            "items": _NAME,
            "description": "product features, capabilities or UI elements, named as in the text",
        },
        "settings": {
            "type": "array",
            "items": _NAME_VALUE,
            "description": "configuration settings, options or fields, with their value or default",
        },
        "limits": {
            "type": "array",
            "items": _NAME_VALUE,
            "description": "limits, quotas, time windows, prices or numbers, with their value",
        },
        "procedures": {"type": "array", "items": _NAME, "description": "named procedures or tasks"},
        "definitions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"term": {"type": "string"}, "meaning": {"type": "string"}},
            },
            "description": "terms that the text defines, with their meaning",
        },
        "urls": {
            "type": "array",
            "items": {"type": "object", "properties": {"url": {"type": "string"}}},
            "description": "URLs",
        },
    },
}
KIND = {
    "features": "feature",
    "settings": "setting",
    "limits": "limit",
    "procedures": "procedure",
    "definitions": "definition",
    "urls": "url",
}

_PUNCT = re.compile(r"[^\w\s]")


def _singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith(("ses", "xes", "ches", "shes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def normalize(name: str) -> str:
    words = _PUNCT.sub(" ", name.lower().replace("_", " ")).split()
    return " ".join(_singular(w) for w in words)


class EvidenceIndex:
    def __init__(self, items: list[Evidence] | None = None):
        self.items: list[Evidence] = list(items or [])
        self._norm = [normalize(e.name) for e in self.items]
        self._by_chunk: dict[str, list[Evidence]] = {}
        for e in self.items:
            self._by_chunk.setdefault(e.chunk_id, []).append(e)

    def find(self, name: str) -> list[Evidence]:
        """Items whose normalized name matches `name` (rapidfuzz token_set_ratio >= 90), best first."""
        q = normalize(name)
        if not q:
            return []
        scored = []
        for e, n in zip(self.items, self._norm, strict=True):
            if not n:
                continue
            s = 100.0 if n == q else fuzz.token_set_ratio(q, n)
            if s >= FIND_MIN:
                scored.append((s, e))
        scored.sort(key=lambda t: -t[0])
        return [e for _, e in scored]

    def by_chunk(self, chunk_id: str) -> list[Evidence]:
        return list(self._by_chunk.get(chunk_id, []))

    def names(self, kinds: set[str] | None = None) -> set[str]:
        return {e.name for e in self.items if kinds is None or e.kind in kinds}

    def __len__(self) -> int:
        return len(self.items)


def evidence_from_fields(chunk: Chunk, fields: list[scaledown.ExtractField]) -> list[Evidence]:
    out: list[Evidence] = []
    seen: set[tuple[str, int, int]] = set()
    for f in fields:
        kind = KIND.get(f.key)
        if kind is None:
            continue
        # re-check against the chunk: verbatim span, then document offsets
        if chunk.text[f.start : f.end] != f.span_text:
            i = chunk.text.find(f.span_text)
            if i < 0:
                continue
            f = f.model_copy(update={"start": i, "end": i + len(f.span_text)})
        start, end = chunk.start + f.start, chunk.start + f.end
        if (kind, start, end) in seen:
            continue
        seen.add((kind, start, end))
        out.append(
            Evidence(
                id=hashlib.sha1(f"{chunk.id}:{kind}:{start}:{end}".encode()).hexdigest()[:12],
                chunk_id=chunk.id,
                doc_id=chunk.doc_id,
                kind=kind,
                name=f.name,
                value=f.value or None,
                span_text=f.span_text,
                start=start,
                end=end,
                confidence=f.confidence,
            )
        )
    return out


async def _chunk_evidence(c: Chunk, *, job: Job) -> list[Evidence] | None:
    try:
        fields = await scaledown.extract(c.text, EVIDENCE_SCHEMA, "evidence", job=job)
    except Exception as e:  # ScaleDown and the fallback model both failed for this chunk
        log.warning("evidence failed for chunk %s: %s", c.id, e)
        return None
    return evidence_from_fields(c, fields)


async def build_evidence(chunks: list[Chunk], *, job: Job | None = None) -> EvidenceIndex:
    job = job or current_job()
    kept = [c for c in chunks if c.kept]
    results = await asyncio.gather(*(_chunk_evidence(c, job=job) for c in kept))
    failed = sum(1 for r in results if r is None)
    if failed:
        await emit_log(job, "warn", f"evidence extraction failed for {failed} of {len(kept)} chunks")
    return EvidenceIndex([e for r in results if r for e in r])


class Retriever:
    """Embedding cosine retrieval over chunks (sync; the constructor embeds every chunk once)."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = list(chunks)
        texts = [f"{c.heading or ''}\n{c.text}" for c in self.chunks]
        self._vecs = embed(texts) if texts else np.zeros((0, 1), dtype=np.float32)

    def top_k(self, query: str, k: int = 5, topic_id: str | None = None) -> list[Chunk]:
        if not self.chunks or k <= 0:
            return []
        idx = np.arange(len(self.chunks))
        if topic_id is not None:
            idx = np.array([i for i, c in enumerate(self.chunks) if c.topic_id == topic_id], dtype=int)
            if idx.size == 0:
                return []
        q = embed([query])[0]
        sims = self._vecs[idx] @ q
        order = idx[np.argsort(-sims)[:k]]
        return [self.chunks[i] for i in order]


__all__ = [
    "EVIDENCE_SCHEMA",
    "EvidenceIndex",
    "Retriever",
    "build_evidence",
    "evidence_from_fields",
    "normalize",
]
