"""Composio connector tests (real Composio calls; skipped without COMPOSIO_API_KEY).

The Notion browse/fetch test also needs an ACTIVE Notion connection for the
user `local` (Composio user `bob-local`); it is skipped until one exists.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bob.connectors import composio as cz

REPO_ROOT = Path(__file__).resolve().parents[2]
env = REPO_ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip()

needs_key = pytest.mark.skipif(not os.environ.get("COMPOSIO_API_KEY"), reason="needs COMPOSIO_API_KEY")


def test_composio_user_id_uses_prefix(monkeypatch):
    monkeypatch.setenv("COMPOSIO_USER_PREFIX", "bob-")
    assert cz.composio_user_id("local") == "bob-local"
    assert cz.composio_user_id("4f1c-sub") == "bob-4f1c-sub"


@pytest.mark.parametrize(
    "raw",
    [
        "1f0e3c2a4b5d6e7f8091a2b3c4d5e6f7",
        "1f0e3c2a-4b5d-6e7f-8091-a2b3c4d5e6f7",
        "1F0E3C2A4B5D6E7F8091A2B3C4D5E6F7",
    ],
)
def test_notion_page_id_normalizes(raw):
    assert cz.notion_page_id(raw) == "1f0e3c2a-4b5d-6e7f-8091-a2b3c4d5e6f7"


def test_notion_page_id_rejects_garbage():
    with pytest.raises(cz.ComposioError):
        cz.notion_page_id("not-a-page")


def test_notion_title_reads_title_property():
    page = {
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "Escalation "}, {"plain_text": "policy"}],
            }
        }
    }
    assert cz.notion_title(page) == "Escalation policy"
    assert cz.notion_title({"properties": {}}) == "Untitled"


# Same structure as a real NOTION_GET_PAGE_MARKDOWN response (2026-10-31), neutral text.
NOTION_RAW = (
    '<span color="gray">Escalate within </span><span color="gray">`2 hours`</span>'
    '<span color="gray"> for paid plans.</span>\n'
    '<unknown url="https://app.notion.com/p/abc#def" alt="button"/>\n'
    "# Escalation policy\n---\n<columns>\n"
    '\t<column ratio="50">\n\t\t###  Tier 1 {color="gray_bg"}\n'
    "\t\t- [x] Check status page\n\t\t- [ ]\n\t</column>\n"
    '\t<column ratio="50">\n\t\t###  Tier 2 {color="gray_bg"}\n'
    "\t\t- [ ] Page on-call engineer\n\t</column>\n</columns>\n"
    '```html\n<div class="keep">code stays</div>\n```\n<empty-block/>'
)


def test_notion_to_markdown_strips_notion_markup_and_keeps_text():
    md = cz.notion_to_markdown(NOTION_RAW)
    assert md.splitlines()[0] == "Escalate within `2 hours` for paid plans."
    assert "# Escalation policy" in md
    assert "### Tier 1" in md and "### Tier 2" in md
    assert "- [x] Check status page" in md
    assert "- [ ] Page on-call engineer" in md
    for junk in (
        "<span",
        "<column",
        "<unknown",
        "<empty-block",
        "{color=",
        "\t",
        "- [ ]\n",
    ):
        assert junk not in md
    assert '<div class="keep">code stays</div>' in md


def test_unsupported_toolkit_is_a_clear_error():
    with pytest.raises(cz.ComposioError, match="not supported yet"):
        cz.toolkit_tools("salesforce")


def _local_notion_connection() -> str | None:
    listed = cz.client().connected_accounts.list(
        user_ids=[cz.composio_user_id("local")], toolkit_slugs=["notion"]
    )
    return str(listed.items[0].id) if listed.items else None


@needs_key
@pytest.mark.asyncio
async def test_connections_are_private_per_user():
    connection_id = _local_notion_connection()
    if connection_id is None:
        pytest.skip("no Notion connection for bob-local yet")
    # The owner sees it; any other Bob user gets "not found", never the account.
    assert "connected" in await cz.status("notion", connection_id, user_id="local")
    with pytest.raises(cz.ConnectionNotFound):
        await cz.status("notion", connection_id, user_id="someone-else")
    with pytest.raises(cz.ConnectionNotFound):
        await cz.browse("notion", connection_id, "", user_id="someone-else")
    other = await cz.connections(user_id="someone-else")
    assert other == [{"toolkit": "notion", "connected": False, "account_id": None}]


@needs_key
@pytest.mark.asyncio
async def test_auth_config_is_reused_and_read_only():
    first = await cz.auth_config_id("notion")
    second = await cz.auth_config_id("notion")
    assert first == second
    config = cz.client().auth_configs.get(first)
    restricted = set(getattr(config, "restrict_to_following_tools", None) or [])
    assert restricted <= set(cz.TOOLKITS["notion"].read_only)


@needs_key
@pytest.mark.asyncio
async def test_notion_browse_and_fetch_markdown():
    connection_id = _local_notion_connection()
    status = await cz.status("notion", connection_id, user_id="local") if connection_id else None
    if not status or not status["connected"]:
        pytest.skip("Notion connection for bob-local is not ACTIVE yet")
    pages = await cz.browse("notion", connection_id, "", user_id="local")
    assert pages, "the connection can read no pages; share some pages with it in Notion"
    assert all(set(p) == {"id", "title", "kind"} for p in pages)
    page = pages[0]
    data = await cz._execute(
        cz.TOOLKITS["notion"].fetch,
        {"page_id": page["id"]},
        account_id=connection_id,
        user_id="local",
        version=cz.TOOLKITS["notion"].version,
    )
    assert isinstance(data.get("markdown"), str)
