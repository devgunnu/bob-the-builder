"""Cache the real demo corpus (CONTRACTS §12): demo/corpus/*.md + demo/corpus/index.json.

Runs the same crawl the product runs for a URL source (bob.connectors.firecrawl.crawl),
so the cached pages match what a live demo job fetches. Optional: also caches the
pages shared with a Notion connection to demo/corpus/notion/.

Default mode scrapes a curated list of support pages (checked against the real site map),
so the corpus is predictable; `--crawl` runs the live crawl instead.

Usage (repo root, keys in .env):
    backend/.venv/bin/python demo/build_corpus.py [--url https://docs.firecrawl.dev] [--limit 25] [--crawl]
    backend/.venv/bin/python demo/build_corpus.py --notion-only [--user local]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "demo" / "corpus"
PAGES_DIR = REPO_ROOT / "demo" / "notion_pages"
# Curated support pages, in priority order. Checked against the real site map before scraping.
SUPPORT_PATHS = [
    "/introduction",
    "/billing",
    "/rate-limits",
    "/webhooks/overview",
    "/webhooks/events",
    "/webhooks/security",
    "/webhooks/testing",
    "/features/key-restrictions",
    "/features/ip-restrictions",
    "/features/scrape",
    "/features/batch-scrape",
    "/features/crawl",
    "/features/map",
    "/features/search",
    "/features/enhanced-mode",
    "/features/proxies",
    "/features/fast-scraping",
    "/features/lockdown",
    "/features/pii-redaction",
    "/features/llm-extract",
    "/features/extract",
    "/features/change-tracking",
    "/features/document-parsing",
    "/advanced-scraping-guide",
    "/partner-credits",
    "/features/sso",
    "/features/threat-protection",
]
MAX_PAGE_CHARS = 60_000  # feature pages with 8 languages of code tabs run 100k-300k chars
# --crawl mode only: steers the crawl toward pages a first-reply support agent needs (Firecrawl crawl `prompt`).
SUPPORT_PROMPT = (
    "Crawl only pages a customer support agent needs to answer user questions: billing, credits, "
    "plans, rate limits, concurrency, errors and troubleshooting, webhooks, API keys and key "
    "restrictions, and the main scrape, crawl, map, search, batch scrape and extract feature pages. "
    "Skip quickstarts for other tools, integrations, use cases, changelogs and API reference endpoint pages."
)

sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from bob.connectors import composio as cz  # noqa: E402
from bob.connectors.firecrawl import crawl, page_url, scrape_page, site_urls  # noqa: E402


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70] or "page"


def write_page(folder: Path, name: str, uri: str, title: str, text: str) -> dict[str, str]:
    folder.mkdir(parents=True, exist_ok=True)
    fetched = datetime.now(UTC).isoformat(timespec="seconds")
    path = folder / f"{name}.md"
    path.write_text(f"---\nsource_url: {uri}\ntitle: {title}\nfetched_at: {fetched}\n---\n\n{text}\n")
    return {
        "file": str(path.relative_to(CORPUS)),
        "uri": uri,
        "title": title,
        "chars": str(len(text)),
        "hash": hashlib.sha1(text.encode()).hexdigest(),
    }


async def progress(done: int, total: int, detail: str) -> None:
    print(f"  [{done}/{total}] {detail}")


async def build_curated(url: str, limit: int) -> list[dict[str, str]]:
    base = page_url(url)
    available = set(await site_urls(url))
    wanted = [base + path for path in SUPPORT_PATHS if base + path in available]
    print(f"map: {len(available)} pages; {len(wanted)} of {len(SUPPORT_PATHS)} support pages exist")
    entries: list[dict[str, str]] = []
    for page_link in wanted:
        if len(entries) >= limit:
            break
        page, reason = await scrape_page(page_link, max_chars=MAX_PAGE_CHARS)
        if page is None:
            print(f"  skipped {page_link}: {reason}")
            continue
        name = slug(re.sub(r"^https?://[^/]+", "", page.url) or "index")
        entries.append(write_page(CORPUS, name, page.url, page.title, page.markdown))
        print(f"  [{len(entries)}/{limit}] {page.url} ({len(page.markdown)} chars)")
    return entries


async def build_docs(url: str, limit: int, prompt: str | None) -> list[dict[str, str]]:
    print(f"crawling {url} (limit {limit})")
    result = await crawl(url, limit, progress, prompt=prompt)
    entries = []
    for page in sorted(result.pages, key=lambda p: p.url):
        name = slug(re.sub(r"^https?://[^/]+", "", page.url) or "index")
        entries.append(write_page(CORPUS, name, page.url, page.title, page.markdown))
    for skipped_url, reason in result.skipped.items():
        print(f"  skipped {skipped_url}: {reason}")
    print(f"{len(entries)} pages, {result.credits_used} credits")
    return entries


def demo_wiki_titles() -> set[str]:
    """Titles of the fictional demo wiki pages; only these are cached (never personal pages)."""
    titles = set()
    for path in PAGES_DIR.glob("[0-9][0-9]-*.md"):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        titles.add(first.lstrip("# ").strip())
    return titles


async def build_notion(user_id: str) -> list[dict[str, str]]:
    connections = await cz.connections(user_id=user_id)
    account_id = next((c["account_id"] for c in connections if c["toolkit"] == "notion"), None)
    if not account_id:
        print(f"no active Notion connection for {user_id!r}; skipping Notion")
        return []
    wanted = demo_wiki_titles()
    pages = [p for p in await cz.browse("notion", account_id, "", user_id=user_id) if p["title"] in wanted]
    if not pages:
        print("no demo wiki pages shared yet (run demo/seed_notion.py); skipping Notion")
    tools = cz.toolkit_tools("notion")
    entries = []
    for page in pages:
        data = await cz._execute(
            tools.fetch,
            {"page_id": page["id"]},
            account_id=account_id,
            user_id=user_id,
            version=tools.version,
        )
        text = cz.notion_to_markdown(data.get("markdown") or "")
        if text:
            uri = f"notion://{cz.notion_page_id(page['id'])}"
            entries.append(write_page(CORPUS / "notion", slug(page["title"]), uri, page["title"], text))
            print(f"  notion: {page['title']} ({len(text)} chars)")
    return entries


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://docs.firecrawl.dev")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--user", default="local")
    parser.add_argument("--notion-only", action="store_true")
    parser.add_argument("--crawl", action="store_true", help="live-style crawl instead of the curated list")
    parser.add_argument("--no-prompt", action="store_true", help="--crawl without support-page guidance")
    args = parser.parse_args()

    index_path = CORPUS / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"docs": [], "notion": []}
    if not args.notion_only:
        if args.crawl:
            prompt = None if args.no_prompt else SUPPORT_PROMPT
            index["docs"] = await build_docs(args.url, args.limit, prompt)
            index["source"] = {"mode": "crawl", "url": args.url, "limit": args.limit, "prompt": prompt}
        else:
            index["docs"] = await build_curated(args.url, args.limit)
            index["source"] = {"mode": "curated", "url": args.url, "paths": SUPPORT_PATHS}
    index["notion"] = await build_notion(args.user)
    index["built_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    CORPUS.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {index_path.relative_to(REPO_ROOT)}")
    return 0 if index["docs"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
