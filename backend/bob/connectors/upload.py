"""Uploads: store files through Blobs, read them back, turn them into Documents (G1).

Keys: "runs/uploads/<upload_id>/<name>" (CONTRACTS §6). One upload id per file.
Nothing is written to local disk here; Blobs decides where bytes live
(local: under settings.runs_dir, aws: S3).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePath

from bob.connectors.parsers import SUPPORTED_EXTENSIONS, ParseError, parse_file
from bob.core.backends import get_blobs
from bob.core.models import Document, SourceSpec

UPLOAD_PREFIX = "runs/uploads"
# .json / .jsonl are accepted for seed files (A1 load_seeds); they are not document sources.
SEED_EXTENSIONS = (".jsonl", ".json")
ALLOWED_EXTENSIONS = SUPPORTED_EXTENSIONS + SEED_EXTENSIONS
UPLOAD_ID = re.compile(r"[0-9a-f]{32}")
MAX_NAME_CHARS = 150

Progress = Callable[[int, int, str], Awaitable[None]]


class UploadError(ValueError):
    """Bad upload input. The message is shown to the user."""


class UploadNotFound(LookupError):
    pass


@dataclass(frozen=True)
class UploadedFile:
    id: str
    name: str
    bytes: int


def safe_name(name: str) -> str:
    """Keep the base name only, with a safe character set and its extension."""
    base = PurePath(name.replace("\\", "/")).name
    stem, ext = PurePath(base).stem, PurePath(base).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._") or "file"
    return stem[: MAX_NAME_CHARS - len(ext)] + ext


def _check_upload_id(upload_id: str) -> None:
    if not UPLOAD_ID.fullmatch(upload_id):
        raise UploadNotFound(f"upload {upload_id!r} not found")


async def save_uploads(files: list[tuple[str, bytes]]) -> list[UploadedFile]:
    """Validate every file first, then store each under its own upload id."""
    if not files:
        raise UploadError("no files in the request")
    checked: list[tuple[str, bytes]] = []
    for raw_name, data in files:
        name = safe_name(raw_name)
        ext = PurePath(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(ALLOWED_EXTENSIONS)
            raise UploadError(f"{raw_name}: unsupported file type '{ext or 'none'}' (allowed: {allowed})")
        if not data:
            raise UploadError(f"{raw_name}: file is empty")
        checked.append((name, data))

    blobs = get_blobs()
    saved: list[UploadedFile] = []
    for name, data in checked:
        upload_id = uuid.uuid4().hex
        await blobs.put(f"{UPLOAD_PREFIX}/{upload_id}/{name}", data)
        saved.append(UploadedFile(id=upload_id, name=name, bytes=len(data)))
    return saved


async def read_upload(upload_id: str) -> list[tuple[str, bytes]]:
    """Return [(name, data)] for one upload id (CONTRACTS §7). Used for seeds and sources."""
    _check_upload_id(upload_id)
    blobs = get_blobs()
    prefix = f"{UPLOAD_PREFIX}/{upload_id}/"
    keys = sorted(await blobs.list(prefix))
    if not keys:
        raise UploadNotFound(f"upload {upload_id!r} not found")
    return [(key[len(prefix) :], await blobs.get(key)) for key in keys]


def _document(upload_id: str, name: str, data: bytes) -> Document:
    parsed = parse_file(name, data)
    uri = f"upload://{upload_id}/{name}"
    return Document(
        id=hashlib.sha1(uri.encode()).hexdigest()[:12],
        source_kind="upload",
        uri=uri,
        title=parsed.title,
        text=parsed.text,
        content_hash=hashlib.sha1(parsed.text.encode()).hexdigest(),
        metadata={
            "upload_id": upload_id,
            "filename": name,
            "bytes": len(data),
            **parsed.metadata,
        },
        fetched_at=datetime.now(UTC),
    )


async def fetch(spec: SourceSpec, job_id: str, progress: Progress) -> list[Document]:
    """kind="upload": parse every uploaded file into a Document."""
    if not spec.upload_ids:
        raise UploadError("upload source has no upload_ids")
    total = len(spec.upload_ids)
    documents: list[Document] = []
    await progress(0, total, "reading uploads")
    for index, upload_id in enumerate(spec.upload_ids, start=1):
        for name, data in await read_upload(upload_id):
            if PurePath(name).suffix.lower() in SEED_EXTENSIONS:
                raise UploadError(f"{name}: seed files (.jsonl/.json) are not document sources")
            try:
                documents.append(await asyncio.to_thread(_document, upload_id, name, data))
            except ParseError as exc:
                raise UploadError(str(exc)) from exc
            await progress(index, total, name)
    return documents
