"""Result routes (G1, CONTRACTS §6): spot-check, export, file downloads, presets, re-sync.

Downloads go through `/files/{name}/url` because a plain link cannot send the auth
header: aws mode answers with a presigned S3 URL (1 h); local mode with the API path.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import FileResponse, RedirectResponse, Response

from bob.api.auth import current_user
from bob.api.deps import get_orchestrator
from bob.api.errors import ApiError, not_found
from bob.api.routes import owned_job
from bob.core.models import Job, Report, UserProfile
from bob.orchestrator import Orchestrator

router = APIRouter()

User = Annotated[UserProfile, Depends(current_user)]
Orch = Annotated[Orchestrator, Depends(get_orchestrator)]


@router.get("/presets")
async def presets(user: User) -> list[dict[str, Any]]:
    del user  # signed-in users only
    from bob.export.presets import list_presets

    return list_presets()


@router.post("/jobs/{job_id}/rows/{row_id}/spot-check")
async def spot_check(
    job_id: str, row_id: str, user: User, orchestrator: Orch, ok: Annotated[bool, Body(embed=True)]
) -> Report:
    await owned_job(job_id, user, orchestrator)
    try:
        return await orchestrator.spot_check(job_id, row_id, ok)
    except KeyError as exc:
        raise not_found("row not found") from exc


@router.post("/jobs/{job_id}/export")
async def export(
    job_id: str,
    user: User,
    orchestrator: Orch,
    preset: Annotated[str, Body()],
    formats: Annotated[list[str], Body()],
) -> dict[str, Any]:
    from bob.export.presets import PRESETS

    await owned_job(job_id, user, orchestrator)
    known = PRESETS.get(preset)
    if known is None:
        raise ApiError(400, f"unknown preset {preset!r}", detail=sorted(PRESETS))
    bad = [f for f in formats if f not in known.formats]
    if not formats or bad:
        raise ApiError(400, f"{preset} supports {', '.join(known.formats)}", detail=bad or None)
    return {"files": await orchestrator.export(job_id, preset, formats)}


def _blob_key(job: Job, name: str) -> str:
    """Blob key of an exported file. `name` must be one of the job's own file keys."""
    parts = PurePosixPath(name).parts
    if name not in job.files or not parts or ".." in parts or name.startswith("/"):
        raise not_found("file not found")
    return f"runs/{job.id}/export/{name}"


@router.get("/jobs/{job_id}/files/{name:path}/url")
async def file_url(job_id: str, name: str, user: User, orchestrator: Orch) -> dict[str, str]:
    job = await owned_job(job_id, user, orchestrator)
    key = _blob_key(job, name)
    url = await orchestrator.blobs.url(key, PurePosixPath(name).name)
    return {"url": url or f"/api/jobs/{job_id}/files/{name}"}


@router.get("/jobs/{job_id}/files/{name:path}")
async def file_download(job_id: str, name: str, user: User, orchestrator: Orch) -> Response:
    job = await owned_job(job_id, user, orchestrator)
    key = _blob_key(job, name)
    filename = PurePosixPath(name).name
    url = await orchestrator.blobs.url(key, filename)
    if url:
        return RedirectResponse(url, status_code=302)
    path_for = getattr(orchestrator.blobs, "path_for", None)
    if path_for is None:
        raise ApiError(500, "file storage has no download URL")
    path = path_for(key)
    if not path.is_file():
        raise not_found("file not found")
    return FileResponse(path, filename=filename)


@router.post("/jobs/{job_id}/resync")
async def resync(job_id: str, user: User, orchestrator: Orch) -> Job:
    await owned_job(job_id, user, orchestrator)
    try:
        return await orchestrator.resync(job_id)
    except NotImplementedError as exc:
        raise ApiError(501, "re-sync is not available yet", detail=str(exc)) from exc
