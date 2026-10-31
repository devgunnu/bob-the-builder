"""A2 chunk, filter, embed and dedup tests on real local text (the repo's own `.agents/*.md` docs)."""

from collections import Counter

import a2_support
import numpy as np

from bob.pipeline.chunk import MAX_TOKENS, chunk_documents
from bob.pipeline.embed import dedup_chunks, embed
from bob.pipeline.filters import drop_reason, heuristic_filter


def test_chunk_offsets_and_sizes():
    docs = a2_support.agents_documents()
    assert docs
    by_id = {d.id: d for d in docs}
    chunks = chunk_documents(docs)
    print(f"{len(docs)} docs -> {len(chunks)} chunks")
    for c in chunks:
        assert c.text == by_id[c.doc_id].text[c.start : c.end]
        assert c.text.strip() == c.text
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    sizes = sorted(c.n_tokens for c in chunks)
    print(
        "tokens p10/p50/p90/max:",
        sizes[len(sizes) // 10],
        sizes[len(sizes) // 2],
        sizes[9 * len(sizes) // 10],
        sizes[-1],
    )
    # big chunks only when one table / code block is bigger than MAX_TOKENS (never split inside them)
    for c in chunks:
        if c.n_tokens > MAX_TOKENS * 1.1:
            assert "```" in c.text or c.text.count("\n|") >= 2, (c.heading, c.n_tokens)
    assert sum(c.heading is not None for c in chunks) > 0.8 * len(chunks)


def test_chunks_keep_code_blocks_whole():
    docs = a2_support.agents_documents()
    for c in chunk_documents(docs):
        assert c.text.count("```") % 2 == 0, (c.heading, c.text[:200])


def test_filter_and_dedup():
    docs = a2_support.agents_documents()
    chunks = heuristic_filter(chunk_documents(docs))
    reasons = Counter(c.drop_reason for c in chunks)
    print("filter:", dict(reasons))
    assert reasons[None] > 0.5 * len(chunks)
    assert (
        drop_reason("- [Home](/)\n- [Docs](/docs)\n- [Pricing](/pricing)\n- [Blog](/blog)") == "nav_density"
    )
    assert drop_reason("We use cookies. Accept all cookies to continue. Privacy policy.") == "cookie_footer"

    # a real repeated chunk is a duplicate; the first copy stays
    copy = chunks[0].model_copy(update={"id": "copy", "kept": True, "drop_reason": None})
    out = dedup_chunks([chunks[0].model_copy(update={"kept": True, "drop_reason": None}), copy, *chunks[1:]])
    assert out[0].kept and out[1].drop_reason == "duplicate"
    print("dedup:", Counter(c.drop_reason for c in out))


def test_embed_normalized():
    v = embed(
        ["refund an annual plan", "get money back for a yearly subscription", "configure the Fargate worker"]
    )
    assert v.shape[0] == 3
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)
    assert v[0] @ v[1] > v[0] @ v[2]
