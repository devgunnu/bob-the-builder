"""Composio connector (G2): connect, browse and fetch internal apps (Notion first).

Every call is scoped to one Bob user: the Composio user id is
`COMPOSIO_USER_PREFIX + user_id` (for example `bob-local`, `bob-<cognito sub>`),
so one user never sees another user's connections (CONTRACTS §14).

Auth configs are Composio-managed OAuth and restricted to read-only tools: Bob
only reads. Tool slugs and versions below were listed and verified with real
calls on 2026-10-30 (CONTRACTS: never guess slugs).

Composio's SDK is synchronous, so every call runs in `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from composio import Composio

from bob.connectors.parsers import normalize_markdown

if TYPE_CHECKING:
    from bob.core.models import Document, SourceSpec

Progress = Callable[[int, int, str], Awaitable[None]]

DEFAULT_USER_PREFIX = "bob-"
ACTIVE = "ACTIVE"
BROWSE_PAGE_SIZE = 50
MAX_FETCH_PAGES = 200


@dataclass(frozen=True)
class ToolkitTools:
    search: str
    fetch: str
    version: str
    read_only: tuple[str, ...]


# Verified 2026-10-30 against the live Composio catalog (tools.get_raw_composio_tools).
TOOLKITS: dict[str, ToolkitTools] = {
    "notion": ToolkitTools(
        search="NOTION_SEARCH_NOTION_PAGE",
        fetch="NOTION_GET_PAGE_MARKDOWN",
        version="20261018_00",
        read_only=(
            "NOTION_SEARCH_NOTION_PAGE",
            "NOTION_GET_PAGE_MARKDOWN",
            "NOTION_RETRIEVE_PAGE",
            "NOTION_FETCH_ALL_BLOCK_CONTENTS",
            "NOTION_GET_ABOUT_ME",
        ),
    ),
}
AUTH_CONFIG_NAME = "bob-{toolkit}-read"


class ComposioError(RuntimeError):
    """A Composio step failed. The message is shown to the user."""


class ConnectionNotFound(LookupError):
    """No such connection for this user (also used for another user's connection)."""


# ---------- client + helpers ----------


@lru_cache(maxsize=1)
def client() -> Composio:
    api_key = os.environ.get("COMPOSIO_API_KEY")
    if not api_key:
        raise ComposioError("COMPOSIO_API_KEY is not set")
    return Composio(api_key=api_key)


def composio_user_id(user_id: str) -> str:
    prefix = os.environ.get("COMPOSIO_USER_PREFIX", DEFAULT_USER_PREFIX)
    return f"{prefix}{user_id}"


def toolkit_tools(toolkit: str) -> ToolkitTools:
    tools = TOOLKITS.get(toolkit)
    if tools is None:
        supported = ", ".join(sorted(TOOLKITS))
        raise ComposioError(f"toolkit {toolkit!r} is not supported yet (supported: {supported})")
    return tools


async def _run[T](fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    return await asyncio.to_thread(fn, *args, **kwargs)


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


async def _execute(
    slug: str, arguments: dict[str, Any], *, account_id: str, user_id: str, version: str
) -> Any:
    result = await _run(
        client().tools.execute,
        slug,
        arguments,
        connected_account_id=account_id,
        user_id=composio_user_id(user_id),
        version=version,
    )
    if not _field(result, "successful", False):
        raise ComposioError(f"{slug} failed: {_field(result, 'error') or 'no error message'}")
    return _field(result, "data", {})


# ---------- auth configs + connections ----------


async def auth_config_id(toolkit: str) -> str:
    """Reuse Bob's read-only auth config for the toolkit, or create it once."""
    tools = toolkit_tools(toolkit)
    name = AUTH_CONFIG_NAME.format(toolkit=toolkit)
    listed = await _run(client().auth_configs.list, toolkit_slug=toolkit)
    for item in listed.items:
        if item.name == name and item.status == "ENABLED":
            return str(item.id)
    created = await _run(
        client().auth_configs.create,
        toolkit,
        {
            "type": "use_composio_managed_auth",
            "name": name,
            "restrict_to_following_tools": list(tools.read_only),
        },
    )
    return str(created.id)


async def connect(toolkit: str, redirect_url: str, *, user_id: str) -> dict[str, str]:
    """Start the OAuth flow. The browser opens `auth_url`; Composio returns to `redirect_url`."""
    config_id = await auth_config_id(toolkit)
    request = await _run(
        client().connected_accounts.link,
        composio_user_id(user_id),
        config_id,
        callback_url=redirect_url,
    )
    return {"auth_url": str(request.redirect_url), "connection_id": str(request.id)}


async def _owned_account(connection_id: str, user_id: str) -> Any:
    try:
        account = await _run(client().connected_accounts.get, connection_id)
    except Exception as exc:  # the SDK raises its own NotFound types
        raise ConnectionNotFound(connection_id) from exc
    if _field(account, "user_id") != composio_user_id(user_id):
        raise ConnectionNotFound(connection_id)
    return account


async def status(toolkit: str, connection_id: str, *, user_id: str) -> dict[str, Any]:
    toolkit_tools(toolkit)
    account = await _owned_account(connection_id, user_id)
    connected = _field(account, "status") == ACTIVE
    return {
        "connected": connected,
        "account_id": str(account.id) if connected else None,
    }


async def connections(*, user_id: str) -> list[dict[str, Any]]:
    """GET /connectors: one entry per supported toolkit, with the user's active account if any."""
    listed = await _run(
        client().connected_accounts.list,
        user_ids=[composio_user_id(user_id)],
        toolkit_slugs=list(TOOLKITS),
        statuses=[ACTIVE],
    )
    active: dict[str, str] = {}
    for item in listed.items:
        slug = _field(_field(item, "toolkit"), "slug")
        if slug in TOOLKITS and slug not in active:
            active[slug] = str(item.id)
    return [
        {"toolkit": slug, "connected": slug in active, "account_id": active.get(slug)} for slug in TOOLKITS
    ]


# ---------- Notion parsing ----------


def notion_title(page: dict[str, Any]) -> str:
    for prop in (page.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            text = "".join(part.get("plain_text", "") for part in prop.get("title") or [])
            if text.strip():
                return text.strip()
    return "Untitled"


def notion_page_id(raw: str) -> str:
    """Accept hyphenated or plain 32-char UUIDs; return the hyphenated form."""
    hexed = re.sub(r"[^0-9a-fA-F]", "", raw)
    if len(hexed) != 32:
        raise ComposioError(f"not a Notion page id: {raw!r}")
    hexed = hexed.lower()
    return f"{hexed[:8]}-{hexed[8:12]}-{hexed[12:16]}-{hexed[16:20]}-{hexed[20:]}"


# Notion-flavored markdown -> plain markdown. Outside code fences only.
NOTION_DROP_TAG = re.compile(r"<(?:unknown|empty-block|table_of_contents)\b[^>]*/?>")
NOTION_ANY_TAG = re.compile(r"</?[a-z][a-z0-9-]*(?:\s[^<>]*)?/?>")
NOTION_ATTRS = re.compile(r"\s*\{(?:color|toggle)=\"[^\"]*\"\}")
EMPTY_TASK = re.compile(r"^\s*[-*] \[[ xX]\]\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
NOTION_TABLE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.DOTALL)
NOTION_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL)
NOTION_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.DOTALL)


def _cell(raw: str) -> str:
    text = NOTION_ANY_TAG.sub("", raw)
    return " ".join(text.split()).replace("|", "\\|")


def _notion_table(match: re.Match[str]) -> str:
    """<table><tr><td>..</td></tr></table> -> a markdown pipe table (first row = header)."""
    rows = [[_cell(c) for c in NOTION_CELL.findall(r)] for r in NOTION_ROW.findall(match.group(1))]
    rows = [r for r in rows if r]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n" + "\n".join(lines) + "\n"


def _tables_outside_code(text: str) -> str:
    parts = re.split(r"(^\s*(?:```|~~~).*?^\s*(?:```|~~~)[^\n]*$)", text, flags=re.MULTILINE | re.DOTALL)
    return "".join(part if i % 2 else NOTION_TABLE.sub(_notion_table, part) for i, part in enumerate(parts))


def notion_to_markdown(text: str) -> str:
    """Strip Notion-only markup (spans, columns, placeholders, color attrs, empty to-dos);
    turn Notion <table> blocks into markdown tables."""
    text = _tables_outside_code(text)
    out: list[str] = []
    in_code = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
            out.append(line.strip())
            continue
        if in_code:
            out.append(line)
            continue
        line = NOTION_DROP_TAG.sub("", line)
        line = NOTION_ANY_TAG.sub("", line)
        line = NOTION_ATTRS.sub("", line)
        line = line.lstrip("\t").rstrip()
        if EMPTY_TASK.match(line):
            continue
        out.append(re.sub(r"^(#{1,6})\s{2,}", r"\1 ", line))
    return normalize_markdown("\n".join(out))


# ---------- browse + fetch ----------


async def browse(toolkit: str, account_id: str, q: str, *, user_id: str) -> list[dict[str, str]]:
    """Pages the user's connection can read, matching `q` in the title (empty q lists all)."""
    tools = toolkit_tools(toolkit)
    await _owned_account(account_id, user_id)
    data = await _execute(
        tools.search,
        {"query": q, "page_size": BROWSE_PAGE_SIZE, "filter_value": "page"},
        account_id=account_id,
        user_id=user_id,
        version=tools.version,
    )
    items = []
    for page in data.get("results") or []:
        if page.get("object") != "page" or page.get("archived") or page.get("in_trash"):
            continue
        items.append({"id": str(page["id"]), "title": notion_title(page), "kind": "page"})
    return items


@dataclass(frozen=True)
class FetchedPage:
    page_id: str
    uri: str
    title: str
    text: str
    truncated: bool
    unknown_blocks: int


async def fetch_page(
    toolkit: str, account_id: str, page_id: str, *, user_id: str, title: str | None = None
) -> FetchedPage:
    """One page as clean markdown. The caller has already checked that the account is the user's."""
    tools = toolkit_tools(toolkit)
    page_id = notion_page_id(page_id)
    data = await _execute(
        tools.fetch, {"page_id": page_id}, account_id=account_id, user_id=user_id, version=tools.version
    )
    text = notion_to_markdown(data.get("markdown") or "")
    return FetchedPage(
        page_id=page_id,
        uri=f"notion://{page_id}",
        title=title or _first_heading(text) or "Untitled",
        text=text,
        truncated=bool(data.get("truncated")),
        unknown_blocks=len(data.get("unknown_block_ids") or []),
    )


async def fetch(spec: SourceSpec, job_id: str, progress: Progress, *, user_id: str) -> list[Document]:
    """kind="composio": fetch the selected pages as Documents (uri notion://<page_id>)."""
    from bob.core.models import Document

    toolkit = spec.toolkit or ""
    toolkit_tools(toolkit)  # clear error for an unsupported toolkit before any call
    account_id = spec.connected_account_id
    if not account_id:
        raise ComposioError(f"{toolkit} source has no connected_account_id")
    await _owned_account(account_id, user_id)
    page_ids = [notion_page_id(p) for p in spec.scope.get("page_ids") or []]
    if not page_ids:
        raise ComposioError(f"{toolkit} source has no page_ids in scope")
    if len(page_ids) > MAX_FETCH_PAGES:
        raise ComposioError(f"too many pages ({len(page_ids)}); the limit is {MAX_FETCH_PAGES}")

    titles = {item["id"]: item["title"] for item in await browse(toolkit, account_id, "", user_id=user_id)}
    documents: list[Document] = []
    await progress(0, len(page_ids), f"fetching {len(page_ids)} {toolkit} pages")
    for index, page_id in enumerate(page_ids, start=1):
        page = await fetch_page(toolkit, account_id, page_id, user_id=user_id, title=titles.get(page_id))
        if page.text:
            documents.append(
                Document(
                    id=hashlib.sha1(page.uri.encode()).hexdigest()[:12],
                    source_kind="composio",
                    uri=page.uri,
                    title=page.title,
                    text=page.text,
                    content_hash=hashlib.sha1(page.text.encode()).hexdigest(),
                    metadata={
                        "toolkit": toolkit,
                        "page_id": page.page_id,
                        "truncated": page.truncated,
                        "unknown_blocks": page.unknown_blocks,
                    },
                    fetched_at=datetime.now(UTC),
                )
            )
        await progress(index, len(page_ids), page.title)

    from bob.core import ledger

    ledger.record(job_id, "composio", calls=len(page_ids) + 1)
    return documents


def _first_heading(text: str) -> str | None:
    match = re.search(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None
