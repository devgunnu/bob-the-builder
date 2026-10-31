"""Free heuristic chunk filter (CONTRACTS section 3). Owner: A2.

Sets `kept=False` and `drop_reason`; it never deletes a chunk. Reasons:
  "nav_density"   most of the text is links or link lists (menus, sidebars, breadcrumbs)
  "short"         fewer than MIN_WORDS words
  "cookie_footer" cookie banners, copyright / legal footers, newsletter boxes
"""

from __future__ import annotations

import re

from bob.core.models import Chunk

MIN_WORDS = 40
NAV_LINK_SHARE = 0.5  # share of non-space chars inside links
NAV_LINE_SHARE = 0.6  # share of non-empty lines that are mostly one link

_MD_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_BARE_URL = re.compile(r"https?://\S+")
_BOILER = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bcookies?\b.*\b(accept|consent|preferences|policy)\b",
        r"\b(accept|reject) all( cookies)?\b",
        r"\ball rights reserved\b",
        r"(©|\(c\)|copyright)\s*(19|20)\d\d",
        r"\b(privacy policy|terms of (service|use)|cookie policy)\b",
        r"\bsubscribe to our newsletter\b",
        r"\bwas this (page|article) helpful\b",
    )
]


def _nonspace(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def link_share(text: str) -> float:
    total = _nonspace(text)
    if not total:
        return 0.0
    linked = sum(_nonspace(m.group(0)) for m in _MD_LINK.finditer(text))
    rest = _MD_LINK.sub(" ", text)
    linked += sum(_nonspace(m.group(0)) for m in _BARE_URL.finditer(rest))
    return linked / total


def link_line_share(text: str) -> float:
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return 0.0
    navy = 0
    for ln in lines:
        body = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", ln)
        if body and link_share(body) >= 0.7:
            navy += 1
    return navy / len(lines)


def _is_nav(text: str) -> bool:
    return link_share(text) > NAV_LINK_SHARE or link_line_share(text) > NAV_LINE_SHARE


def _is_boilerplate(text: str) -> bool:
    hits = sum(1 for p in _BOILER if p.search(text))
    words = len(text.split())
    return hits >= 2 or (hits >= 1 and words < 120)


def drop_reason(text: str) -> str | None:
    if _is_nav(text):
        return "nav_density"
    if _is_boilerplate(text):
        return "cookie_footer"
    if len(_MD_LINK.sub(r"\1", text).split()) < MIN_WORDS:
        return "short"
    return None


def heuristic_filter(chunks: list[Chunk]) -> list[Chunk]:
    """Mark nav, short and cookie/footer chunks as dropped. Chunks that are already dropped stay as they are."""
    out: list[Chunk] = []
    for c in chunks:
        if c.kept:
            reason = drop_reason(c.text)
            if reason:
                c = c.model_copy(update={"kept": False, "drop_reason": reason})
        out.append(c)
    return out


__all__ = ["MIN_WORDS", "drop_reason", "heuristic_filter", "link_line_share", "link_share"]
