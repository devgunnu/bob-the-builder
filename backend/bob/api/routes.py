"""HTTP routes (G1, CONTRACTS §6). Mounted under /api.

This file holds the thin-path routes: ping, public config, /me, uploads, jobs,
plan approval, cancel, rows and the event stream. Every route returns in well
under 25 s and starts no background work (Lambda freezes it); long work runs in
the job runner that `Orchestrator.create_job` starts.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from starlette.responses import StreamingResponse

from bob.api.auth import current_user
from bob.api.deps import get_orchestrator, settings
from bob.api.errors import ApiError, not_found
from bob.api.sse import parse_last_event_id, sse_response
from bob.connectors.upload import UploadError, UploadNotFound, check_owner, save_uploads
from bob.core.models import Job, JobSpec, Plan, Row, UserProfile
from bob.orchestrator import Orchestrator

router = APIRouter()

# Lambda request bodies are capped at 6 MB; reject earlier with a clear message.
MAX_UPLOAD_BODY_BYTES = 6 * 1024 * 1024
MAX_ROWS_PAGE = 200
JOB_SUMMARY_EXCLUDE = {"plan", "report"}

User = Annotated[UserProfile, Depends(current_user)]
Orch = Annotated[Orchestrator, Depends(get_orchestrator)]


async def owned_job(job_id: str, user: UserProfile, orchestrator: Orchestrator) -> Job:
    """The caller's job, or 404. Never reveal that another user's job exists."""
    try:
        job = await orchestrator.get_job(job_id)
    except LookupError as exc:
        raise not_found("job not found") from exc
    if job.owner_id != user.id:
        raise not_found("job not found")
    return job


# ---------- open routes ----------


@router.get("/ping")
async def ping() -> dict[str, bool]:
    return {"ok": True}


@router.get("/config/public")
async def config_public() -> dict[str, Any]:
    if settings.auth != "cognito":
        return {"auth": "none"}
    return {
        "auth": "cognito",
        "cognito": {
            "region": settings.cognito_region,
            "user_pool_id": settings.cognito_user_pool_id,
            "client_id": settings.cognito_client_id,
            "domain": settings.cognito_domain,
        },
    }


# ---------- user ----------


@router.get("/me")
async def me(user: User) -> UserProfile:
    return user


# ---------- uploads ----------


@router.post("/uploads")
async def upload_files(request: Request, files: list[UploadFile], user: User) -> dict[str, Any]:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BODY_BYTES:
        raise ApiError(413, "upload too large", detail="the request body limit is 6 MB")
    payload: list[tuple[str, bytes]] = []
    total = 0
    for upload in files:
        data = await upload.read()
        total += len(data)
        if total > MAX_UPLOAD_BODY_BYTES:
            raise ApiError(413, "upload too large", detail="the request body limit is 6 MB")
        payload.append((upload.filename or "file", data))
    try:
        saved = await save_uploads(payload, owner_id=user.id)
    except UploadError as exc:
        raise ApiError(400, "bad upload", detail=str(exc)) from exc
    return {
        "upload_ids": [f.id for f in saved],
        "files": [{"id": f.id, "name": f.name, "bytes": f.bytes} for f in saved],
    }


# ---------- jobs ----------


@router.post("/jobs")
async def create_job(spec: JobSpec, user: User, orchestrator: Orch) -> Job:
    """404 for another user's upload ids; 412 and 429 come from the orchestrator."""
    upload_ids = [uid for src in spec.sources if src.kind == "upload" for uid in src.upload_ids]
    if spec.seed_upload_id:
        upload_ids.append(spec.seed_upload_id)
    try:
        await check_owner(upload_ids, user.id)
    except UploadNotFound as exc:
        raise not_found("upload not found") from exc
    return await orchestrator.create_job(spec, user)


@router.get("/jobs")
async def list_jobs(user: User, orchestrator: Orch) -> list[dict[str, Any]]:
    jobs = await orchestrator.list_jobs(user.id)
    jobs.sort(key=lambda job: job.created_at, reverse=True)
    return [job.model_dump(mode="json", exclude=JOB_SUMMARY_EXCLUDE) for job in jobs]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: User, orchestrator: Orch) -> Job:
    return await owned_job(job_id, user, orchestrator)


@router.put("/jobs/{job_id}/plan")
async def approve_plan(job_id: str, plan: Plan, user: User, orchestrator: Orch) -> Job:
    job = await owned_job(job_id, user, orchestrator)
    if job.status != "awaiting_approval":
        raise ApiError(
            409,
            "plan can only be approved while the job awaits approval",
            detail=job.status,
        )
    return await orchestrator.approve_plan(job_id, plan)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user: User, orchestrator: Orch) -> Job:
    await owned_job(job_id, user, orchestrator)
    return await orchestrator.cancel(job_id)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request, user: User, orchestrator: Orch) -> StreamingResponse:
    await owned_job(job_id, user, orchestrator)
    events = orchestrator.subscribe(job_id, parse_last_event_id(request))
    return sse_response(events, heartbeat_s=settings.sse_heartbeat_s, max_s=settings.sse_max_s)


# ---------- rows ----------


@router.get("/jobs/{job_id}/rows")
async def list_rows(
    job_id: str,
    user: User,
    orchestrator: Orch,
    verdict: Annotated[str | None, Query(pattern="^(kept|rejected)$")] = None,
    cell_id: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS_PAGE)] = 50,
) -> dict[str, Any]:
    await owned_job(job_id, user, orchestrator)
    total, rows = await orchestrator.list_rows(
        job_id, verdict=verdict, cell_id=cell_id, offset=offset, limit=limit
    )
    return {"total": total, "rows": [row.model_dump(mode="json") for row in rows]}


@router.get("/jobs/{job_id}/rows/{row_id}")
async def get_row(job_id: str, row_id: str, user: User, orchestrator: Orch) -> Row:
    await owned_job(job_id, user, orchestrator)
    try:
        return await orchestrator.get_row(job_id, row_id)
    except LookupError as exc:
        raise not_found("row not found") from exc
