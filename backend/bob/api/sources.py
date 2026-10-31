"""Source routes (G1, CONTRACTS §6): Composio connectors and a capped source preview.

Connector routes act on the caller's own Composio user (`bob-<user id>`); another
user's connection id gives 404. `POST /sources/preview` fetches without a job and
stops at PREVIEW_MAX_PAGES pages or PREVIEW_BUDGET_S seconds (`capped: true`).
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from bob.api.auth import current_user
from bob.api.deps import settings
from bob.api.errors import ApiError, not_found
from bob.connectors import composio
from bob.connectors.upload import UploadNotFound, check_owner, read_upload
from bob.core.models import SourceSpec, UserProfile

router = APIRouter()
User = Annotated[UserProfile, Depends(current_user)]

PREVIEW_MAX_PAGES = 10
PREVIEW_BUDGET_S = 20.0
PREVIEW_SCRAPE_CONCURRENCY = 5
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class ConnectBody(BaseModel):
    redirect_url: str | None = None


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def allowed_origins() -> set[str]:
    origins = set(DEV_ORIGINS)
    if settings.public_url:
        origins.add(_origin(settings.public_url))
    return origins


def oauth_redirect(requested: str | None) -> str:
    """The OAuth return URL: our own frontend only (no open redirect through Composio)."""
    if requested is None:
        if not settings.public_url:
            raise ApiError(400, "redirect_url is required", detail="BOB_PUBLIC_URL is not set")
        return settings.public_url.rstrip("/") + settings.oauth_callback_path
    if _origin(requested) not in allowed_origins():
        raise ApiError(400, "redirect_url must point at this app", detail=sorted(allowed_origins()))
    return requested


async def _composio_call(coro: Any) -> Any:
    try:
        return await coro
    except composio.ConnectionNotFound as exc:
        raise not_found("connection not found") from exc
    except composio.ComposioNotConfigured as exc:
        raise ApiError(503, "not configured on this server", provider="composio", detail=str(exc)) from exc
    except composio.ComposioError as exc:
        raise ApiError(400, "connector error", provider="composio", detail=str(exc)) from exc
    except Exception as exc:  # SDK / network errors: show the provider's text
        raise ApiError(
            502, "connector error", provider="composio", detail=f"{type(exc).__name__}: {exc}"
        ) from exc


# ---------- connectors ----------


@router.get("/connectors")
async def list_connectors(user: User) -> list[dict[str, Any]]:
    return await _composio_call(composio.connections(user_id=user.id))


@router.post("/connectors/{toolkit}/connect")
async def connect(toolkit: str, body: ConnectBody, user: User) -> dict[str, str]:
    redirect = oauth_redirect(body.redirect_url)
    return await _composio_call(composio.connect(toolkit, redirect, user_id=user.id))


@router.get("/connectors/{toolkit}/status")
async def connector_status(toolkit: str, user: User, connection_id: str = Query(...)) -> dict[str, Any]:
    return await _composio_call(composio.status(toolkit, connection_id, user_id=user.id))


@router.get("/connectors/{toolkit}/browse")
async def browse(toolkit: str, user: User, account_id: str = Query(...), q: str = "") -> list[dict[str, str]]:
    return await _composio_call(composio.browse(toolkit, account_id, q, user_id=user.id))


# ---------- preview ----------


async def _preview_uploads(spec: SourceSpec, user: UserProfile) -> tuple[list[dict], bool]:
    from bob.connectors.parsers import ParseError, parse_file

    try:
        await check_owner(spec.upload_ids, user.id)
    except UploadNotFound as exc:
        raise not_found("upload not found") from exc
    docs: list[dict] = []
    for upload_id in spec.upload_ids:
        for name, data in await read_upload(upload_id):
            if len(docs) >= PREVIEW_MAX_PAGES:
                return docs, True
            try:
                parsed = await asyncio.to_thread(parse_file, name, data)
            except ParseError as exc:
                raise ApiError(400, "bad upload", detail=str(exc)) from exc
            docs.append(
                {"uri": f"upload://{upload_id}/{name}", "title": parsed.title, "chars": len(parsed.text)}
            )
    return docs, False


async def _preview_url(spec: SourceSpec, deadline: float) -> tuple[list[dict], bool]:
    from bob.connectors.firecrawl import page_url, scrape_page, site_urls

    if not spec.url:
        raise ApiError(400, "url source has no url")
    loop = asyncio.get_running_loop()
    base = page_url(spec.url)
    urls = [u for u in await site_urls(spec.url) if u.startswith(base)] or [base]
    if base in urls:  # the page the user typed comes first
        urls.remove(base)
        urls.insert(0, base)
    wanted = urls[: min(PREVIEW_MAX_PAGES, spec.crawl_limit)]
    capped = len(urls) > len(wanted)
    gate = asyncio.Semaphore(PREVIEW_SCRAPE_CONCURRENCY)

    async def one(u: str) -> dict | None:
        async with gate:
            page, _ = await scrape_page(u)
        return {"uri": page.url, "title": page.title, "chars": len(page.markdown)} if page else None

    tasks = [asyncio.create_task(one(u)) for u in wanted]
    done, pending = await asyncio.wait(tasks, timeout=max(0.0, deadline - loop.time()))
    for task in pending:
        task.cancel()
    docs = [t.result() for t in tasks if t in done and not t.exception() and t.result()]
    return docs, capped or bool(pending)


async def _preview_composio(spec: SourceSpec, user: UserProfile, deadline: float) -> tuple[list[dict], bool]:
    toolkit = spec.toolkit or ""
    account_id = spec.connected_account_id
    if not account_id:
        raise ApiError(400, f"{toolkit} source has no connected_account_id")
    loop = asyncio.get_running_loop()
    pages = await _composio_call(composio.browse(toolkit, account_id, "", user_id=user.id))
    titles = {p["id"]: p["title"] for p in pages}
    page_ids = [composio.notion_page_id(p) for p in spec.scope.get("page_ids") or []]
    docs: list[dict] = []
    for page_id in page_ids[:PREVIEW_MAX_PAGES]:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return docs, True
        try:
            page = await asyncio.wait_for(
                composio.fetch_page(toolkit, account_id, page_id, user_id=user.id, title=titles.get(page_id)),
                timeout=remaining,
            )
        except TimeoutError:
            return docs, True
        docs.append({"uri": page.uri, "title": page.title, "chars": len(page.text)})
    return docs, len(page_ids) > PREVIEW_MAX_PAGES


@router.post("/sources/preview")
async def preview(spec: SourceSpec, user: User) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PREVIEW_BUDGET_S
    if spec.kind == "upload":
        docs, capped = await _preview_uploads(spec, user)
    elif spec.kind == "url":
        from bob.connectors.firecrawl import FirecrawlNotConfigured

        try:
            docs, capped = await _preview_url(spec, deadline)
        except ApiError:
            raise
        except FirecrawlNotConfigured as exc:
            raise ApiError(
                503, "not configured on this server", provider="firecrawl", detail=str(exc)
            ) from exc
        except Exception as exc:
            raise ApiError(
                502, "preview failed", provider="firecrawl", detail=f"{type(exc).__name__}: {exc}"
            ) from exc
    else:
        docs, capped = await _preview_composio(spec, user, deadline)
    return {"documents": docs, "capped": capped}
