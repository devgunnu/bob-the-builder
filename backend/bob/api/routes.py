"""HTTP routes (G1, CONTRACTS §6). Mounted under /api.

This file holds the thin-path routes: ping, public config, /me, uploads, jobs,
plan approval, cancel, rows and the event stream. Every route returns in well
under 25 s and starts no background work (Lambda freezes it); long work runs in
the job runner that `Orchestrator.create_job` starts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from bob.api.auth import current_user
from bob.api.deps import get_orchestrator, settings
from bob.api.errors import ApiError, not_found
from bob.api.sse import parse_last_event_id, sse_response
from bob.connectors.upload import (
    UploadError,
    UploadNotFound,
    check_owner,
    presign_upload,
    presigned,
    save_uploads,
)
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


@router.get("/health")
async def health(user: User, orchestrator: Orch) -> dict[str, Any]:
    """One cheap real call per provider (bob.api.health). Needs a signed-in user."""
    from bob.api.health import health as run_health

    return await run_health(user, orchestrator.health_job(user))


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


class PresignBody(BaseModel):
    name: str
    bytes: int
    content_type: str | None = None


@router.post("/uploads/presign")
async def presign(body: PresignBody, user: User, orchestrator: Orch) -> dict[str, Any]:
    """Direct upload for files over the 6 MB request limit (P1).

    aws: a presigned S3 PUT (Content-Type and Content-Length are signed, 15 min).
    local: this API's own `PUT /api/uploads/{id}/content` (send the Authorization header).
    Then use `upload_id` in a SourceSpec or as `seed_upload_id`, as with POST /uploads.
    """
    try:
        upload = await presign_upload(body.name, body.bytes, owner_id=user.id, content_type=body.content_type)
    except UploadError as exc:
        status = 413 if "limit" in str(exc) else 400
        raise ApiError(status, "bad upload", detail=str(exc)) from exc
    url = await orchestrator.blobs.put_url(upload.key, upload.content_type, upload.bytes)
    return {
        "upload_id": upload.id,
        "put_url": url or f"/api/uploads/{upload.id}/content",
        "method": "PUT",
        "headers": {"Content-Type": upload.content_type},
        "name": upload.name,
        "bytes": upload.bytes,
    }


@router.put("/uploads/{upload_id}/content")
async def upload_content(upload_id: str, request: Request, user: User, orchestrator: Orch) -> dict[str, Any]:
    """Local mode only: receives the bytes for a presigned upload (aws uploads go straight to S3)."""
    try:
        upload = await presigned(upload_id, owner_id=user.id)
    except UploadNotFound as exc:
        raise not_found("upload not found") from exc
    if await orchestrator.blobs.put_url(upload.key, upload.content_type, upload.bytes) is not None:
        raise ApiError(409, "upload directly to put_url", detail="this deployment uploads to S3")
    data = await request.body()
    if len(data) != upload.bytes:
        raise ApiError(400, "size mismatch", detail={"expected": upload.bytes, "got": len(data)})
    await orchestrator.blobs.put(upload.key, data, upload.content_type)
    return {"id": upload.id, "name": upload.name, "bytes": upload.bytes}


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


# ---------- spot-check, export, files, resync, presets ----------


class SpotCheckBody(BaseModel):
    ok: bool


class ExportBody(BaseModel):
    preset: str
    formats: list[str] = ["jsonl"]


def _presets() -> dict[str, dict[str, Any]]:
    from bob.export.presets import list_presets

    return {p["name"]: p for p in list_presets()}


@router.get("/presets")
async def presets(_: User) -> list[dict[str, Any]]:
    return list(_presets().values())


@router.post("/jobs/{job_id}/rows/{row_id}/spot-check")
async def spot_check(job_id: str, row_id: str, body: SpotCheckBody, user: User, orchestrator: Orch) -> Any:
    """Thumbs up/down on a kept row; returns the rebuilt Report (409 while a worker runs)."""
    await owned_job(job_id, user, orchestrator)
    try:
        return await orchestrator.spot_check(job_id, row_id, body.ok)
    except KeyError as exc:
        raise not_found("row not found") from exc


@router.post("/jobs/{job_id}/export")
async def export(job_id: str, body: ExportBody, user: User, orchestrator: Orch) -> dict[str, Any]:
    await owned_job(job_id, user, orchestrator)
    preset = _presets().get(body.preset)
    if preset is None:
        raise ApiError(400, "unknown preset", detail=sorted(_presets()))
    bad = [f for f in body.formats if f not in preset["formats"]]
    if bad or not body.formats:
        raise ApiError(400, "unsupported format", detail={"allowed": preset["formats"], "got": body.formats})
    return {"files": await orchestrator.export(job_id, body.preset, body.formats)}


def _export_key(job: Job, name: str) -> str:
    """Blob key of one export file. Only names listed in Job.files can be downloaded."""
    if name not in job.files:
        raise not_found("file not found")
    return f"runs/{job.id}/export/{name}"


def _local_export_path(job: Job, name: str) -> Path:
    root = (Path(settings.runs_dir) / job.id / "export").resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise not_found("file not found")
    return path


# Declared before the plain file route: `{name:path}` would otherwise swallow ".../url".
@router.get("/jobs/{job_id}/files/{name:path}/url")
async def file_url(job_id: str, name: str, user: User, orchestrator: Orch) -> dict[str, str]:
    job = await owned_job(job_id, user, orchestrator)
    key = _export_key(job, name)
    url = await orchestrator.blobs.url(key, Path(name).name)
    if url is None:
        _local_export_path(job, name)
        url = f"/api/jobs/{quote(job.id)}/files/{quote(name)}"
    return {"url": url}


@router.get("/jobs/{job_id}/files/{name:path}")
async def file_download(job_id: str, name: str, user: User, orchestrator: Orch) -> Any:
    job = await owned_job(job_id, user, orchestrator)
    key = _export_key(job, name)
    url = await orchestrator.blobs.url(key, Path(name).name)
    if url is not None:
        return RedirectResponse(url, status_code=302)
    return FileResponse(_local_export_path(job, name), filename=Path(name).name)


@router.post("/jobs/{job_id}/resync")
async def resync(job_id: str, user: User, orchestrator: Orch) -> Job:
    await owned_job(job_id, user, orchestrator)
    try:
        return await orchestrator.resync(job_id)
    except NotImplementedError as exc:
        raise ApiError(501, "re-sync is not available yet", detail=str(exc)) from exc
