"""Build the smoke corpus (demo/smoke/*.md) from a real Firecrawl scrape.

Discovers real doc URLs with Firecrawl `map`, picks a few support-relevant
pages, scrapes each as markdown, and writes one file per page. Every file
starts with a front-matter block holding the source URL and title.

Usage (from the repo root, with FIRECRAWL_API_KEY in .env):
    python demo/scrape_smoke.py [--site https://docs.firecrawl.dev] [--pages 5]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from firecrawl import Firecrawl
from firecrawl.v2.utils.error_handler import RateLimitError

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "demo" / "smoke"

# Pages a first-reply support bot gets asked about, in priority order.
# Matched against the path of real URLs returned by `map` (exact match).
# Chosen because they are short and full of concrete limits, settings and
# numbers, which the verification checks need.
SUPPORT_PATHS: list[str] = [
    "/billing",
    "/rate-limits",
    "/webhooks/overview",
    "/webhooks/security",
    "/features/key-restrictions",
    "/webhooks/events",
    "/introduction",
]

MIN_CHARS = 800  # skip near-empty pages (redirect stubs, nav-only pages)
MAX_CHARS = (
    60_000  # skip huge pages (multi-language code tabs) to keep smoke tests cheap
)
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_WAIT_S = 15  # free plan: 10 requests/min

# Docs-site chrome that survives `only_main_content` (seen on Mintlify sites such as docs.firecrawl.dev).
HEADING_ANCHOR = re.compile(r"^(#{1,6})\s*\[\u200b?\]\([^)]*\)\s*", re.MULTILINE)
EDIT_FOOTER = re.compile(r"^\[Suggest edits\]\(.*$", re.MULTILINE)
LONE_UI_GLYPH = re.compile(r"^\s*[\u2715\u00d7]\s*$", re.MULTILINE)
SKIP_LINK = re.compile(r"^\[Skip to main content\]\(.*$", re.MULTILINE)
# Leading "> ## Documentation Index ... llms.txt ..." notice block.
DOC_INDEX_NOTICE = re.compile(
    r"\A(?:>.*\n?)*?>\s*#*\s*Documentation Index(?:.*\n?)*?(?=^[^>\n])", re.MULTILINE
)
# Chat-widget greeting appended after the content ("- 👋 Hi! ..." bullets to end of page).
CHAT_WIDGET_TAIL = re.compile(r"^-\s*\U0001F44B.*\Z", re.MULTILINE | re.DOTALL)
JSON_BLOB_MIN_CHARS = 2_000


def clean_markdown(markdown: str) -> str:
    """Strip docs-site chrome while keeping every line of real page content."""
    lines = [
        line
        for line in markdown.splitlines()
        if not (line.lstrip().startswith("{") and len(line) >= JSON_BLOB_MIN_CHARS)
    ]
    text = "\n".join(lines)
    text = DOC_INDEX_NOTICE.sub("", text)
    text = SKIP_LINK.sub("", text)
    text = HEADING_ANCHOR.sub(r"\1 ", text)
    text = EDIT_FOOTER.sub("", text)
    text = LONE_UI_GLYPH.sub("", text)
    text = CHAT_WIDGET_TAIL.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def with_rate_limit_retry(call, *args, **kwargs):
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            return call(*args, **kwargs)
        except RateLimitError:
            if attempt == RATE_LIMIT_RETRIES:
                raise
            print(f"rate limited, waiting {RATE_LIMIT_WAIT_S}s (attempt {attempt})")
            time.sleep(RATE_LIMIT_WAIT_S)


def slugify(url: str) -> str:
    path = re.sub(r"^https?://[^/]+", "", url).strip("/") or "index"
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")[:60]


def normalize_url(url: str) -> str:
    """Drop `#fragment` and the `.md` raw-copy suffix so each page appears once."""
    return re.sub(r"(\.md)?(#.*)?$", "", url).rstrip("/")


def pick_urls(all_urls: list[str], n_pages: int) -> list[str]:
    by_path = {
        re.sub(r"^https?://[^/]+", "", normalize_url(u)): normalize_url(u)
        for u in all_urls
    }
    picked = [by_path[path] for path in SUPPORT_PATHS if path in by_path]
    return picked[: n_pages + 2]  # a couple of spares in case some pages are skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="https://docs.firecrawl.dev")
    parser.add_argument("--pages", type=int, default=5)
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        print(
            "FIRECRAWL_API_KEY is not set (add it to .env at the repo root).",
            file=sys.stderr,
        )
        return 1

    client = Firecrawl(api_key=api_key)

    site_map = with_rate_limit_retry(client.map, args.site, limit=500)
    all_urls = [link.url for link in site_map.links]
    print(f"map: {len(all_urls)} URLs found on {args.site}")

    candidates = pick_urls(all_urls, args.pages)
    if not candidates:
        print("No support-relevant URLs matched; check SUPPORT_PATHS.", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for url in candidates:
        if len(written) >= args.pages:
            break
        doc = with_rate_limit_retry(
            client.scrape,
            url,
            formats=["markdown"],
            only_main_content=True,
            exclude_tags=["script", "style", "noscript"],
        )
        markdown = clean_markdown(doc.markdown or "")
        if not MIN_CHARS <= len(markdown) <= MAX_CHARS:
            print(
                f"skip ({len(markdown)} chars, outside {MIN_CHARS}-{MAX_CHARS}): {url}"
            )
            continue
        title = (
            doc.metadata.title if doc.metadata and doc.metadata.title else url
        ).strip()
        front_matter = (
            "---\n"
            f"source_url: {url}\n"
            f"title: {title}\n"
            f"fetched_at: {datetime.now(UTC).isoformat(timespec='seconds')}\n"
            "---\n\n"
        )
        path = OUT_DIR / f"{slugify(url)}.md"
        path.write_text(front_matter + markdown + "\n", encoding="utf-8")
        written.append(path)
        print(f"wrote {path.relative_to(REPO_ROOT)} ({len(markdown)} chars)")

    print(f"done: {len(written)} pages in {OUT_DIR.relative_to(REPO_ROOT)}")
    return 0 if len(written) >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
