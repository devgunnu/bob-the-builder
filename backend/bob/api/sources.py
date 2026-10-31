"""Source routes (G1 on G2's connectors, CONTRACTS §6): Composio connect and browse, and preview.

Composio connections are private per user: every call passes the caller's id, and
`connectors/composio.py` refuses a connection that belongs to someone else.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from bob.api.auth import current_user
from bob.api.deps import settings
from bob.api.errors import ApiError, not_found
from bob.connectors.upload import UploadError, UploadNotFound, check_owner
from bob.core.models import SourceSpec, UserProfile

router = APIRouter()

User = Annotated[UserProfile, Depends(current_user)]

PREVIEW_MAX_DOCS = 10
PREVIEW_TIMEOUT_S = 20.0


def _composio_error(exc: Exception) -> ApiError:
    from bob.connectors.composio import ConnectionNotFound

    if isinstance(exc, ConnectionNotFound):
        return not_found("connection not found")
    return ApiError(502, "Composio call failed", provider="composio", detail=str(exc)[:500])


def _redirect_ok(redirect_url: str) -> bool:
    """Only send Composio back to our own callback page (dev origins or BOB_PUBLIC_URL)."""
    path = settings.oauth_callback_path
    allowed = ["http://localhost:5173", "http://127.0.0.1:5173"]
    if settings.public_url:
        allowed.append(settings.public_url.rstrip("/"))
    return any(redirect_url == origin + path for origin in allowed)


@router.get("/connectors")
async def list_connectors(user: User) -> list[dict[str, Any]]:
    from bob.connectors import composio

    if not settings.composio_api_key:
        return []  # the Apps tab says no connectors are configured
    try:
        return await composio.connections(user_id=user.id)
    except Exception as exc:
        raise _composio_error(exc) from exc


@router.post("/connectors/{toolkit}/connect")
async def connect(toolkit: str, user: User, redirect_url: Annotated[str, Body(embed=True)]) -> dict[str, str]:
    from bob.connectors import composio

    if not _redirect_ok(redirect_url):
        raise ApiError(400, "redirect_url must be this app's /oauth/callback page", detail=redirect_url)
    try:
        composio.toolkit_tools(toolkit)
        return await composio.connect(toolkit, redirect_url, user_id=user.id)
    except composio.ComposioError as exc:
        raise ApiError(400, str(exc), provider="composio") from exc
    except Exception as exc:
        raise _composio_error(exc) from exc


@router.get("/connectors/{toolkit}/status")
async def connection_status(toolkit: str, connection_id: str, user: User) -> dict[str, Any]:
    from bob.connectors import composio

    try:
        return await composio.status(toolkit, connection_id, user_id=user.id)
    except Exception as exc:
        raise _composio_error(exc) from exc


@router.get("/connectors/{toolkit}/browse")
async def browse(toolkit: str, account_id: str, user: User, q: str = "") -> list[dict[str, str]]:
    from bob.connectors import composio

    try:
        return await composio.browse(toolkit, account_id, q, user_id=user.id)
    except Exception as exc:
        raise _composio_error(exc) from exc


@router.post("/sources/preview")
async def preview(spec: SourceSpec, user: User) -> dict[str, Any]:
    """Fetch only, no job: at most 10 pages or 20 s; `capped` when it stopped early."""
    if spec.kind == "url":
        from bob.connectors import firecrawl

        if not spec.url:
            raise ApiError(400, "url source has no url")
        try:
            pages, capped = await firecrawl.preview(spec.url, spec.crawl_limit, timeout_s=PREVIEW_TIMEOUT_S)
        except firecrawl.CrawlError as exc:
            raise ApiError(502, "preview failed", provider="firecrawl", detail=str(exc)[:500]) from exc
        docs = [{"uri": p.url, "title": p.title, "chars": len(p.markdown)} for p in pages]
        return {"documents": docs, "capped": capped}

    capped = False
    if spec.kind == "upload":
        try:
            await check_owner(spec.upload_ids, user.id)
        except UploadNotFound as exc:
            raise not_found("upload not found") from exc
        if len(spec.upload_ids) > PREVIEW_MAX_DOCS:
            spec = spec.model_copy(update={"upload_ids": spec.upload_ids[:PREVIEW_MAX_DOCS]})
            capped = True
    if spec.kind == "composio":
        page_ids = list(spec.scope.get("page_ids") or [])
        if len(page_ids) > PREVIEW_MAX_DOCS:
            spec = spec.model_copy(update={"scope": {**spec.scope, "page_ids": page_ids[:PREVIEW_MAX_DOCS]}})
            capped = True

    from bob.connectors import fetch_documents

    async def no_progress(_done: int, _total: int, _detail: str) -> None:
        return None

    from bob.core import ledger

    preview_id = f"preview-{uuid.uuid4().hex[:8]}"  # a throwaway ledger entry, dropped below
    try:
        docs = await asyncio.wait_for(
            fetch_documents(spec, preview_id, no_progress, user_id=user.id), timeout=PREVIEW_TIMEOUT_S
        )
    except TimeoutError as exc:
        raise ApiError(
            504, "preview took longer than 20 s", detail="the job itself has no time limit"
        ) from exc
    except UploadError as exc:
        raise ApiError(400, "bad upload", detail=str(exc)) from exc
    except Exception as exc:
        if spec.kind == "composio":
            raise _composio_error(exc) from exc
        raise ApiError(502, "preview failed", detail=f"{type(exc).__name__}: {exc}"[:500]) from exc
    finally:
        ledger.forget(preview_id)
    out = [{"uri": d.uri, "title": d.title, "chars": len(d.text)} for d in docs[:PREVIEW_MAX_DOCS]]
    return {"documents": out, "capped": capped or len(docs) > PREVIEW_MAX_DOCS}
