"""Firecrawl connector tests.

The cleanup tests run offline on chrome copied from a real docs.firecrawl.dev
scrape. The crawl test makes a real Firecrawl call (3 pages, about 3 credits)
and is skipped when FIRECRAWL_API_KEY is not set.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bob.connectors.firecrawl import clean_markdown, crawl, page_url

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip()


_load_env()

# Chrome copied from the real /billing scrape (2026-10-31).
RAW_PAGE = (
    "> ## Documentation Index\n>\n"
    "> Fetch the complete documentation index at: [/llms.txt](https://docs.firecrawl.dev/llms.txt)\n>\n"
    "> Use this file to discover all available pages before exploring further.\n\n"
    "[Skip to main content](https://docs.firecrawl.dev/billing#content-area)\n\n"
    "## [​](https://docs.firecrawl.dev/billing\\#overview)  Overview\n\n"
    "Firecrawl billing is **credit-based**. Every API call that you make consumes credits.\n\n"
    "[Suggest edits](https://github.com/firecrawl/firecrawl-docs/edit/main/billing.mdx)"
    " [Raise issue](https://github.com/firecrawl/firecrawl-docs/issues/new)\n\n"
    ' {"docsConfig":{"theme":"aspen","name":"Firecrawl Docs"' + ',"x":1' * 600 + "}}\n\n"
    "✕\n\n"
    "- \U0001f44b Hi! Power AI agents with clean web data!\n\n"
    "- I can help with search, scrape, MCP setup, or billing.\n"
)


def test_clean_markdown_strips_docs_chrome_and_keeps_content():
    cleaned = clean_markdown(RAW_PAGE)
    assert cleaned.startswith("## Overview")
    assert "Firecrawl billing is **credit-based**." in cleaned
    for junk in (
        "Documentation Index",
        "Skip to main",
        "Suggest edits",
        "docsConfig",
        "✕",
        "\U0001f44b",
    ):
        assert junk not in cleaned


def test_clean_markdown_is_noop_on_clean_pages():
    page = (REPO_ROOT / "demo" / "smoke" / "rate-limits.md").read_text().split("---\n\n", 1)[1]
    assert clean_markdown(page) == page.strip()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://docs.firecrawl.dev/billing#plans",
            "https://docs.firecrawl.dev/billing",
        ),
        ("https://docs.firecrawl.dev/billing/", "https://docs.firecrawl.dev/billing"),
        ("https://docs.firecrawl.dev/billing", "https://docs.firecrawl.dev/billing"),
    ],
)
def test_page_url(raw, expected):
    assert page_url(raw) == expected


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("FIRECRAWL_API_KEY"), reason="needs FIRECRAWL_API_KEY")
async def test_real_crawl_reports_progress_per_page():
    events: list[tuple[int, int, str]] = []

    async def progress(done: int, total: int, detail: str) -> None:
        events.append((done, total, detail))

    result = await crawl("https://docs.firecrawl.dev/webhooks/overview", 3, progress)

    assert 1 <= len(result.pages) <= 3
    assert result.credits_used >= 1
    urls = [page.url for page in result.pages]
    assert len(urls) == len(set(urls))
    assert all(url.startswith("https://docs.firecrawl.dev/") and "#" not in url for url in urls)
    assert all(not url.endswith(".md") for url in urls)
    for page in result.pages:
        assert page.title
        assert "docsConfig" not in page.markdown
        assert "\n\n\n" not in page.markdown
    assert events[0][0] == 0
    page_events = [e for e in events if e[0] > 0]
    assert [e[0] for e in page_events] == list(range(1, len(result.pages) + 1))
    assert {e[2] for e in page_events} == set(urls)
