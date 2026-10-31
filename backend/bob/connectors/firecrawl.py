"""Firecrawl connector (G2): crawl a website into Documents with live progress.

`crawl()` is the SDK-facing core (no Bob models): start a crawl, poll its
status every CRAWL_POLL_S, report progress once per new page, clean each page.
`fetch()` wraps it for `fetch_documents()` (SourceSpec -> list[Document]).

Firecrawl's SDK is synchronous, so every call runs in `asyncio.to_thread`.
The API key comes from FIRECRAWL_API_KEY (local: .env; aws: loaded from the
bob/keys secret into the environment before startup).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar

from firecrawl import Firecrawl
from firecrawl.v2.types import ScrapeOptions
from firecrawl.v2.utils.error_handler import FirecrawlError, RateLimitError

from bob.connectors.parsers import normalize_markdown

if TYPE_CHECKING:
    from bob.core.models import Document, SourceSpec

Progress = Callable[[int, int, str], Awaitable[None]]
T = TypeVar("T")

CRAWL_POLL_S = 2.0
CRAWL_TIMEOUT_S = 15 * 60
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_WAIT_S = 15.0  # free plan: 2 crawl starts/min, 10 scrapes/min
EXCLUDE_TAGS = ["script", "style", "noscript"]
# Raw markdown copies ("page.md") duplicate the HTML pages on docs sites.
EXCLUDE_PATHS = [r".*\.md$"]
MIN_PAGE_CHARS = 200

# ---------- cleanup of docs-site chrome that survives only_main_content ----------
# Seen on Mintlify docs (for example docs.firecrawl.dev); harmless elsewhere.

HEADING_ANCHOR = re.compile(r"^(#{1,6})\s*\[​?\]\([^)]*\)\s*", re.MULTILINE)
EDIT_FOOTER = re.compile(r"^\[Suggest edits\]\(.*$", re.MULTILINE)
SKIP_LINK = re.compile(r"^\[Skip to main content\]\(.*$", re.MULTILINE)
LONE_UI_GLYPH = re.compile(r"^\s*[✕×]\s*$", re.MULTILINE)
# Leading "> ## Documentation Index ... llms.txt ..." notice block.
DOC_INDEX_NOTICE = re.compile(
    r"\A(?:>.*\n?)*?>\s*#*\s*Documentation Index(?:.*\n?)*?(?=^[^>\n])", re.MULTILINE
)
# Chat-widget greeting appended after the content ("- 👋 Hi! ..." bullets to the end).
CHAT_WIDGET_TAIL = re.compile(r"^-\s*\U0001f44b.*\Z", re.MULTILINE | re.DOTALL)
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
    return normalize_markdown(text)


def page_url(url: str) -> str:
    """Canonical page URL: no #fragment, no trailing slash."""
    return url.split("#", 1)[0].rstrip("/") or url


# ---------- crawl ----------


class CrawlError(RuntimeError):
    """A crawl failed. The message is shown to the user."""


@dataclass(frozen=True)
class CrawledPage:
    url: str
    title: str
    markdown: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawlResult:
    crawl_id: str
    pages: list[CrawledPage]
    credits_used: int
    skipped: dict[str, str]  # url -> reason


def make_client() -> Firecrawl:
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        raise CrawlError("FIRECRAWL_API_KEY is not set")
    return Firecrawl(api_key=api_key)


async def _call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking SDK call in a thread; wait and retry on rate limits."""
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except RateLimitError:
            if attempt == RATE_LIMIT_RETRIES:
                raise
            await asyncio.sleep(RATE_LIMIT_WAIT_S * attempt)
    raise AssertionError("unreachable")


def _to_page(doc: Any) -> tuple[CrawledPage | None, str, str | None]:
    """(page or None, url, skip reason) for one Firecrawl document."""
    meta = doc.metadata
    raw_url = (meta.source_url or meta.url) if meta else None
    url = page_url(raw_url or "")
    status = meta.status_code if meta else None
    if status is not None and status >= 400:
        return None, url, f"HTTP {status}"
    markdown = clean_markdown(doc.markdown or "")
    if len(markdown) < MIN_PAGE_CHARS:
        return None, url, f"only {len(markdown)} chars"
    title = ((meta.title if meta else None) or url).strip()
    metadata: dict[str, Any] = {"status_code": status}
    if meta and meta.language:
        metadata["language"] = meta.language
    return (
        CrawledPage(url=url, title=title, markdown=markdown, metadata=metadata),
        url,
        None,
    )


async def crawl(
    url: str,
    limit: int,
    progress: Progress,
    *,
    client: Firecrawl | None = None,
    poll_s: float = CRAWL_POLL_S,
    timeout_s: float = CRAWL_TIMEOUT_S,
) -> CrawlResult:
    """Crawl `url` (at most `limit` pages). Calls progress(done, total, url) per new page."""
    client = client or make_client()
    started = await _call(
        client.start_crawl,
        url,
        limit=limit,
        exclude_paths=EXCLUDE_PATHS,
        scrape_options=ScrapeOptions(
            formats=["markdown"], only_main_content=True, exclude_tags=EXCLUDE_TAGS
        ),
    )
    await progress(0, limit, f"crawl started: {url}")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    pages: dict[str, CrawledPage] = {}
    skipped: dict[str, str] = {}
    try:
        while True:
            job = await _call(client.get_crawl_status, started.id)
            total = max(job.total or 0, len(pages) + len(skipped))
            for doc in job.data:
                page, doc_url, reason = _to_page(doc)
                if not doc_url or doc_url in pages or doc_url in skipped:
                    continue
                if page is None:
                    skipped[doc_url] = reason or "skipped"
                    continue
                pages[doc_url] = page
                await progress(len(pages), total, doc_url)
            if job.status == "completed":
                return CrawlResult(
                    started.id, list(pages.values()), job.credits_used, skipped
                )
            if job.status in ("failed", "cancelled"):
                raise CrawlError(f"crawl {job.status} for {url}")
            if loop.time() > deadline:
                raise CrawlError(f"crawl of {url} did not finish in {int(timeout_s)} s")
            await asyncio.sleep(poll_s)
    except (asyncio.CancelledError, CrawlError):
        # Stop paying for a crawl nobody will read.
        with contextlib.suppress(FirecrawlError):
            await asyncio.to_thread(client.cancel_crawl, started.id)
        raise


# ---------- connector entry point ----------


def to_document(page: CrawledPage, *, crawl_id: str) -> Document:
    from bob.core.models import Document

    return Document(
        id=hashlib.sha1(page.url.encode()).hexdigest()[:12],
        source_kind="url",
        uri=page.url,
        title=page.title,
        text=page.markdown,
        content_hash=hashlib.sha1(page.markdown.encode()).hexdigest(),
        metadata={**page.metadata, "crawl_id": crawl_id},
        fetched_at=datetime.now(UTC),
    )


async def fetch(spec: SourceSpec, job_id: str, progress: Progress) -> list[Document]:
    """kind="url": crawl spec.url (cap spec.crawl_limit) into Documents."""
    if not spec.url:
        raise CrawlError("url source has no url")
    try:
        result = await crawl(spec.url, spec.crawl_limit, progress)
    except FirecrawlError as exc:
        raise CrawlError(f"Firecrawl: {exc}") from exc

    from bob.core import ledger

    ledger.record(
        job_id, "firecrawl", calls=max(result.credits_used, len(result.pages))
    )
    return [to_document(page, crawl_id=result.crawl_id) for page in result.pages]
