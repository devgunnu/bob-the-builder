"""Seed the fictional support wiki (demo/notion_pages/*.md) into the demo Notion workspace.

Bob's Notion auth config is read-only (bob.connectors.composio.TOOLKITS). This script
adds NOTION_CREATE_NOTION_PAGE to it for the duration of the run and always restores
the read-only list afterwards, even on failure.

Before running: create an empty Notion page titled PARENT_TITLE and share it with the
Composio connection (page menu -> Connections). Pages are created under it.
Re-running skips pages whose title already exists.

Usage (repo root, COMPOSIO_API_KEY in .env):
    backend/.venv/bin/python demo/seed_notion.py [--user local]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO_ROOT / "demo" / "notion_pages"
PARENT_TITLE = "Bob Demo – Support Wiki (fictional)"
CREATE_TOOL = "NOTION_CREATE_NOTION_PAGE"

sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from bob.connectors import composio as cz  # noqa: E402


def page_sources() -> list[tuple[str, str]]:
    """[(title, markdown body without the H1)] in file order, README excluded."""
    pages = []
    for path in sorted(PAGES_DIR.glob("[0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8").strip()
        match = re.match(r"#\s+(.+)\n+", text)
        if not match:
            raise SystemExit(f"{path.name}: first line must be '# Title'")
        pages.append((match.group(1).strip(), text[match.end() :].strip()))
    return pages


async def set_tools(config_id: str, tools: list[str]) -> None:
    await asyncio.to_thread(
        cz.client().auth_configs.update,
        config_id,
        options={"type": "default", "restrict_to_following_tools": tools},
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="local", help="Bob user id that owns the Notion connection")
    args = parser.parse_args()

    connections = await cz.connections(user_id=args.user)
    account_id = next((c["account_id"] for c in connections if c["toolkit"] == "notion"), None)
    if not account_id:
        print(f"No active Notion connection for Bob user {args.user!r}.", file=sys.stderr)
        return 1

    visible = await cz.browse("notion", account_id, "", user_id=args.user)
    parent = next((p for p in visible if p["title"] == PARENT_TITLE), None)
    if parent is None:
        print(
            f"Parent page {PARENT_TITLE!r} is not shared with the connection.\n"
            "Create it in Notion and add the connection under its ... -> Connections.",
            file=sys.stderr,
        )
        return 1
    existing = {p["title"] for p in visible}

    tools = cz.toolkit_tools("notion")
    config_id = await cz.auth_config_id("notion")
    read_only = list(tools.read_only)
    await set_tools(config_id, [*read_only, CREATE_TOOL])
    try:
        for title, body in page_sources():
            if title in existing:
                print(f"skip (exists): {title}")
                continue
            data = await cz._execute(
                CREATE_TOOL,
                {"parent_id": parent["id"], "title": title, "markdown": body},
                account_id=account_id,
                user_id=args.user,
                version=tools.version,
            )
            print(f"created: {title} ({data.get('id', '?')})")
    finally:
        await set_tools(config_id, read_only)
        print("auth config restored to read-only tools")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
