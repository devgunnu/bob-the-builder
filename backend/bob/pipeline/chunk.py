"""Heading-aware chunking with exact offsets (CONTRACTS section 3). Owner: A2.

- Blocks: markdown headings, paragraphs, fenced code blocks and tables. Code blocks and tables are never split.
- Sections (a heading and its blocks) are packed into chunks of about MIN_TOKENS..MAX_TOKENS tokens. A heading
  starts a new chunk when the current chunk already has MIN_TOKENS, or when the next section does not fit.
- A paragraph that is bigger than MAX_TOKENS is split at sentence ends (then at line ends).
- `Chunk.start` / `Chunk.end` are char offsets in `Document.text`, and `chunk.text == doc.text[start:end]`
  always holds (asserted). Chunk the final Document.text only: never normalize text after chunking.
- Token count: a fast estimate, words x 1.3.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from bob.core.models import Chunk, Document

MIN_TOKENS = 300
MAX_TOKENS = 500

_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t#]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_TABLE = re.compile(r"^ {0,3}\|")
_SENT_END = re.compile(r"(?<=[.!?])\s+(?=\S)|\n+")


def n_tokens(text: str) -> int:
    return round(len(text.split()) * 1.3)


@dataclass
class _Block:
    start: int
    end: int
    kind: str  # heading | para | code | table
    heading: str | None  # heading path at this block, "A > B > C"
    tokens: int


def _lines(text: str) -> list[tuple[int, int]]:
    """(start, end) of each line without its newline."""
    out, pos = [], 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        out.append((pos, pos + len(stripped)))
        pos += len(line)
    return out


def _blocks(text: str) -> list[_Block]:
    lines = _lines(text)
    blocks: list[_Block] = []
    path: list[tuple[int, str]] = []  # (level, title)
    i = 0

    def head() -> str | None:
        return " > ".join(t for _, t in path) or None

    def add(s: int, e: int, kind: str) -> None:
        seg = text[s:e]
        # trim trailing whitespace so offsets cover real text only
        e = s + len(seg.rstrip())
        if e > s:
            blocks.append(_Block(s, e, kind, head(), n_tokens(text[s:e])))

    while i < len(lines):
        s, e = lines[i]
        line = text[s:e]
        if not line.strip():
            i += 1
            continue
        m = _FENCE.match(line)
        if m:
            fence = m.group(1)
            j = i + 1
            while j < len(lines):
                ls, le = lines[j]
                if text[ls:le].strip().startswith(fence[0] * len(fence)):
                    break
                j += 1
            j = min(j, len(lines) - 1)
            add(s, lines[j][1], "code")
            i = j + 1
            continue
        h = _HEADING.match(line)
        if h:
            level = len(h.group(1))
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, h.group(2).strip()))
            add(s, e, "heading")
            i += 1
            continue
        if _TABLE.match(line):
            j = i
            while j + 1 < len(lines) and _TABLE.match(text[lines[j + 1][0] : lines[j + 1][1]]):
                j += 1
            add(s, lines[j][1], "table")
            i = j + 1
            continue
        # paragraph: until a blank line, a heading, a fence or a table
        j = i
        while j + 1 < len(lines):
            ns, ne = lines[j + 1]
            nl = text[ns:ne]
            if not nl.strip() or _HEADING.match(nl) or _FENCE.match(nl) or _TABLE.match(nl):
                break
            j += 1
        add(s, lines[j][1], "para")
        i = j + 1
    return blocks


def _split_big(text: str, b: _Block) -> list[_Block]:
    """Split a paragraph bigger than MAX_TOKENS at sentence (or line) ends."""
    if b.kind != "para" or b.tokens <= MAX_TOKENS:
        return [b]
    pieces: list[tuple[int, int]] = []
    pos = b.start
    for m in _SENT_END.finditer(text, b.start, b.end):
        pieces.append((pos, m.start()))
        pos = m.end()
    pieces.append((pos, b.end))
    out: list[_Block] = []
    cur_s, cur_e = pieces[0]
    for ps, pe in pieces[1:]:
        if n_tokens(text[cur_s:pe]) > MAX_TOKENS:
            out.append(_Block(cur_s, cur_e, "para", b.heading, n_tokens(text[cur_s:cur_e])))
            cur_s = ps
        cur_e = pe
    out.append(_Block(cur_s, cur_e, "para", b.heading, n_tokens(text[cur_s:cur_e])))
    return [x for x in out if x.end > x.start]


def _sections(blocks: list[_Block]) -> list[list[_Block]]:
    secs: list[list[_Block]] = []
    for b in blocks:
        if b.kind == "heading" or not secs:
            secs.append([b])
        else:
            secs[-1].append(b)
    return secs


def chunk_document(doc: Document) -> list[Chunk]:
    text = doc.text
    blocks: list[_Block] = []
    for b in _blocks(text):
        blocks.extend(_split_big(text, b))

    groups: list[list[_Block]] = []
    cur: list[_Block] = []
    cur_tok = 0
    for sec in _sections(blocks):
        sec_tok = sum(b.tokens for b in sec)
        if cur and (cur_tok >= MIN_TOKENS or cur_tok + sec_tok > MAX_TOKENS):
            groups.append(cur)
            cur, cur_tok = [], 0
        for b in sec:  # a big section is split between its blocks
            if cur and cur_tok + b.tokens > MAX_TOKENS and any(x.kind != "heading" for x in cur):
                groups.append(cur)
                cur, cur_tok = [], 0
            cur.append(b)
            cur_tok += b.tokens
    if cur:
        groups.append(cur)

    chunks: list[Chunk] = []
    for g in groups:
        start, end = g[0].start, g[-1].end
        body = text[start:end]
        heading = next((b.heading for b in g if b.kind != "heading"), None) or g[0].heading
        chunk = Chunk(
            id=hashlib.sha1((doc.id + str(start)).encode()).hexdigest()[:12],
            doc_id=doc.id,
            uri=doc.uri,
            heading=heading,
            text=body,
            start=start,
            end=end,
            n_tokens=n_tokens(body),
        )
        assert chunk.text == text[chunk.start : chunk.end]
        chunks.append(chunk)
    return chunks


def chunk_documents(docs: list[Document]) -> list[Chunk]:
    """Heading-aware chunks of 300-500 tokens with exact offsets in Document.text."""
    out: list[Chunk] = []
    for d in docs:
        out.extend(chunk_document(d))
    return out


__all__ = ["MAX_TOKENS", "MIN_TOKENS", "chunk_document", "chunk_documents", "n_tokens"]
