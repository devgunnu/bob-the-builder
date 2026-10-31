"""S3 implementation of the blob protocol."""

# Needed: the class defines a method named `list`, so an evaluated `list[str]` annotation
# inside the class body would refer to that method and fail with TypeError at import.
from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from bob.config import get_settings


def _key(key: str) -> str:
    if not key or key.startswith("/") or "\\" in key or ".." in PurePosixPath(key).parts:
        raise ValueError(f"invalid blob key: {key!r}")
    return key


def missing(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


class S3Blobs:
    def __init__(self) -> None:
        self.bucket = get_settings().bucket
        if not self.bucket:
            raise ValueError("BOB_BUCKET is required")
        self.client = boto3.client("s3")
        # SigV4 for upload URLs: it signs Content-Length (SigV2, boto3's default for presigned S3
        # URLs in some regions, signs only Content-Type, so any size would be accepted).
        self._upload_signer = boto3.client("s3", config=Config(signature_version="s3v4"))

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        args = {"Bucket": self.bucket, "Key": _key(key), "Body": data}
        if content_type:
            args["ContentType"] = content_type
        await asyncio.to_thread(self.client.put_object, **args)

    async def get(self, key: str) -> bytes:
        def read() -> bytes:
            try:
                return self.client.get_object(Bucket=self.bucket, Key=_key(key))["Body"].read()
            except ClientError as exc:
                if missing(exc):
                    raise KeyError(key) from exc
                raise

        return await asyncio.to_thread(read)

    async def exists(self, key: str) -> bool:
        def check() -> bool:
            try:
                self.client.head_object(Bucket=self.bucket, Key=_key(key))
                return True
            except ClientError as exc:
                if missing(exc):
                    return False
                raise

        return await asyncio.to_thread(check)

    async def list(self, prefix: str) -> list[str]:
        def get_keys() -> list[str]:
            pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
            return sorted(item["Key"] for page in pages for item in page.get("Contents", []))

        return await asyncio.to_thread(get_keys)

    async def upload_tree(self, local_dir: Path, prefix: str) -> list[str]:
        files = sorted(p for p in Path(local_dir).rglob("*") if p.is_file())
        keys = []
        for path in files:
            key = _key(f"{prefix.rstrip('/')}/{path.relative_to(local_dir).as_posix()}")
            await asyncio.to_thread(self.client.upload_file, str(path), self.bucket, key)
            keys.append(key)
        return keys

    async def put_url(
        self,
        key: str,
        content_type: str | None = None,
        content_length: int | None = None,
        expires_s: int = 900,
    ) -> str:
        """Presigned PUT (added by G1 for /uploads/presign). Content-Type and Content-Length are
        signed, so S3 rejects an upload with another type or size. The data bucket needs a CORS rule
        allowing PUT from BOB_PUBLIC_URL (A5)."""
        params: dict = {"Bucket": self.bucket, "Key": _key(key)}
        if content_type:
            params["ContentType"] = content_type
        if content_length is not None:
            params["ContentLength"] = content_length
        return await asyncio.to_thread(
            self._upload_signer.generate_presigned_url, "put_object", Params=params, ExpiresIn=expires_s
        )

    async def url(self, key: str, filename: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": _key(key)}
        if filename:
            params["ResponseContentDisposition"] = f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
        return await asyncio.to_thread(
            self.client.generate_presigned_url, "get_object", Params=params, ExpiresIn=3600
        )
