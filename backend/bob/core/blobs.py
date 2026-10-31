"""Blobs protocol + local implementation (CONTRACTS section 7). Owner: A1. aws impl: bob/aws/blobs.py (A5).

Keys are relative paths that mirror the local runs/ tree, e.g. "runs/<job_id>/export/openai-chat/train/train.jsonl".
LocalBlobs maps key "runs/<rest>" to settings.runs_dir/<rest>, and any other key (e.g. "cache/<sha>.json")
to settings.runs_dir/_blobs/<key>, so it never writes outside settings.runs_dir.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable


@runtime_checkable
class Blobs(Protocol):
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def exists(self, key: str) -> bool: ...
    async def list(self, prefix: str) -> list[str]: ...
    async def upload_tree(self, local_dir: Path, prefix: str) -> list[str]: ...
    async def url(self, key: str, filename: str | None = None) -> str | None:
        """aws: presigned GET (1 h); local: None (the route streams the file)."""
        ...

    async def put_url(
        self,
        key: str,
        content_type: str | None = None,
        content_length: int | None = None,
        expires_s: int = 900,
    ) -> str | None:
        """aws: presigned PUT for a direct browser upload (added by G1 for /uploads/presign);
        local: None (the API accepts the bytes itself, it has no 6 MB request limit)."""
        ...


class LocalBlobs:
    def __init__(self, runs_dir: Path | None = None):
        if runs_dir is None:
            from bob.config import get_settings

            runs_dir = get_settings().runs_dir
        self.root = Path(runs_dir).resolve()

    def path_for(self, key: str) -> Path:
        """Local file for a key. Raises ValueError for a key that leaves runs_dir."""
        parts = PurePosixPath(key.replace("\\", "/")).parts
        if not parts or ".." in parts or key.startswith("/"):
            raise ValueError(f"bad blob key {key!r}")
        rel = Path(*parts[1:]) if parts[0] == "runs" else Path("_blobs", *parts)
        return self.root / rel

    def key_for(self, path: Path) -> str:
        rel = Path(path).resolve().relative_to(self.root).as_posix()
        if rel.startswith("_blobs/"):
            return rel[len("_blobs/") :]
        return f"runs/{rel}"

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        p = self.path_for(key)

        def _write() -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)

        await asyncio.to_thread(_write)

    async def get(self, key: str) -> bytes:
        p = self.path_for(key)
        if not p.is_file():
            raise KeyError(key)
        return await asyncio.to_thread(p.read_bytes)

    async def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    async def list(self, prefix: str) -> list[str]:
        def _list() -> list[str]:
            # walk the narrowest existing folder, then filter by the string prefix
            head = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
            base = self.path_for(head) if head else self.root
            if not base.is_dir():
                return []
            keys = [self.key_for(f) for f in base.rglob("*") if f.is_file() and not f.name.endswith(".tmp")]
            return sorted(k for k in keys if k.startswith(prefix))

        return await asyncio.to_thread(_list)

    async def upload_tree(self, local_dir: Path, prefix: str) -> list[str]:
        """Copy every file under local_dir to prefix/<relative path>. A no-op copy when they are the same place."""
        src = Path(local_dir).resolve()
        prefix = prefix.rstrip("/")

        def _copy() -> list[str]:
            keys: list[str] = []
            for f in sorted(src.rglob("*")):
                if not f.is_file():
                    continue
                key = f"{prefix}/{f.relative_to(src).as_posix()}"
                dst = self.path_for(key)
                if dst.resolve() != f:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)
                keys.append(key)
            return keys

        return await asyncio.to_thread(_copy)

    async def url(self, key: str, filename: str | None = None) -> str | None:
        return None

    async def put_url(
        self,
        key: str,
        content_type: str | None = None,
        content_length: int | None = None,
        expires_s: int = 900,
    ) -> str | None:
        self.path_for(key)  # same key check as put()
        return None
