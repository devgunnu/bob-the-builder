"""Embeddings and chunk dedup (CONTRACTS section 3). Owner: A2.

model2vec `minishlab/potion-base-8M`, CPU, loaded once per process, L2-normalized vectors (so a dot product is
the cosine). When `BOB_EMBED_MODEL_PATH` is set, the model loads from that path (the image bakes it in; no
Hugging Face download at runtime; in Lambda only /tmp is writable).

`embed()` is sync and CPU-bound; async code calls `aembed()` (asyncio.to_thread).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import threading
from typing import TYPE_CHECKING

import numpy as np

from bob.config import get_settings
from bob.core.models import Chunk

if TYPE_CHECKING:
    from model2vec import StaticModel

MODEL_NAME = "minishlab/potion-base-8M"
DEDUP_COS = 0.95

_model: StaticModel | None = None
_lock = threading.Lock()


def get_model() -> StaticModel:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from model2vec import StaticModel

                path = get_settings().embed_model_path
                _model = StaticModel.from_pretrained(path or MODEL_NAME)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """(len(texts), dim) float32 array, each row L2-normalized. Empty input -> shape (0, dim)."""
    model = get_model()
    if not texts:
        return np.zeros((0, model.dim), dtype=np.float32)
    vecs = np.asarray(model.encode(list(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


async def aembed(texts: list[str]) -> np.ndarray:
    return await asyncio.to_thread(embed, texts)


def _norm_hash(text: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", " ", text.lower()).strip().encode()).hexdigest()


def dedup_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Among kept chunks: exact (normalized) hash, then cosine > 0.95 -> kept=False, drop_reason="duplicate".

    The first chunk in input order stays. Chunks that are already dropped are not compared.
    """
    out = list(chunks)
    seen: set[str] = set()
    live: list[int] = []
    for i, c in enumerate(out):
        if not c.kept:
            continue
        h = _norm_hash(c.text)
        if h in seen:
            out[i] = c.model_copy(update={"kept": False, "drop_reason": "duplicate"})
            continue
        seen.add(h)
        live.append(i)
    if len(live) < 2:
        return out
    vecs = embed([out[i].text for i in live])
    keep_rows: list[int] = []
    for row, i in enumerate(live):
        if keep_rows and float(np.max(vecs[keep_rows] @ vecs[row])) > DEDUP_COS:
            out[i] = out[i].model_copy(update={"kept": False, "drop_reason": "duplicate"})
        else:
            keep_rows.append(row)
    return out


__all__ = ["DEDUP_COS", "MODEL_NAME", "aembed", "dedup_chunks", "embed", "get_model"]
