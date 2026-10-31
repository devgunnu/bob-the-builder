"""Real-response disk cache (CONTRACTS sections 0, 12). Owner: A1.

Key = sha256(endpoint, model, canonical JSON body). The response JSON is stored through Blobs under
`cache/<sha256>.json` (local: settings.runs_dir/_blobs/cache/, aws: S3). It stores only real responses and
never invents one. `BOB_CACHE=0` turns it off (get returns None, put does nothing).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from bob.config import get_settings


def canonical(body: Any) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def cache_key(endpoint: str, model: str, body: Any) -> str:
    h = hashlib.sha256()
    h.update(endpoint.encode())
    h.update(b"\0")
    h.update(model.encode())
    h.update(b"\0")
    h.update(canonical(body).encode())
    return h.hexdigest()


def _blob_key(key: str) -> str:
    return f"cache/{key}.json"


def enabled() -> bool:
    return bool(get_settings().cache)


async def get(endpoint: str, model: str, body: Any) -> Any | None:
    """The stored real response for this request, or None (miss, or BOB_CACHE=0)."""
    if not enabled():
        return None
    from bob.core.backends import get_blobs

    blobs = get_blobs()
    key = _blob_key(cache_key(endpoint, model, body))
    try:
        data = await blobs.get(key)
    except (KeyError, FileNotFoundError):
        return None
    try:
        return json.loads(data)
    except ValueError:
        return None


async def put(endpoint: str, model: str, body: Any, response: Any) -> None:
    """Store a real response (JSON-serializable). No-op with BOB_CACHE=0."""
    if not enabled():
        return
    from bob.core.backends import get_blobs

    data = json.dumps(response, ensure_ascii=False, default=str).encode("utf-8")
    await get_blobs().put(_blob_key(cache_key(endpoint, model, body)), data, "application/json")
