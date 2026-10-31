"""G1 API tests on the real app and A1's real local core (BOB_ENV=local, one built-in user).

No external services are called: uploads go to local Blobs, and job creation stops
at the orchestrator's own 412 because the local user has not verified AWS access.
A second user is a real UserProfile from the orchestrator; only the sign-in step is
swapped (dependency override) so one test client can act as that user.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from bob.api.app import app
from bob.api.auth import current_user
from bob.api.deps import get_orchestrator
from bob.connectors import fetch_documents
from bob.connectors.upload import UploadNotFound, read_upload
from bob.core.models import SourceSpec

SMOKE = Path(__file__).resolve().parents[2] / "demo" / "smoke"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bob") as c:
        yield c
    app.dependency_overrides.clear()


async def as_user(user_id: str) -> None:
    other = await get_orchestrator().get_or_create_user(user_id, None)
    app.dependency_overrides[current_user] = lambda: other


async def upload_smoke(client: httpx.AsyncClient, *names: str) -> list[str]:
    files = [("files", (n, (SMOKE / n).read_bytes(), "text/markdown")) for n in names]
    r = await client.post("/api/uploads", files=files)
    assert r.status_code == 200, r.text
    return r.json()["upload_ids"]


async def noop_progress(done: int, total: int, detail: str) -> None:
    return None


async def test_open_routes(client):
    assert (await client.get("/api/ping")).json() == {"ok": True}
    assert (await client.get("/api/config/public")).status_code == 404  # no sign-in, no auth config
    me = (await client.get("/api/me")).json()
    assert me["id"] == "local" and me["external_id"]


async def test_upload_then_fetch_documents(client):
    ids = await upload_smoke(client, "billing.md", "rate-limits.md")
    docs = await fetch_documents(
        SourceSpec(kind="upload", upload_ids=ids), "t-job", noop_progress, user_id="local"
    )
    assert [d.title for d in docs] == ["Billing | Firecrawl", "Rate Limits | Firecrawl"]
    assert docs[0].metadata["source_url"] == "https://docs.firecrawl.dev/billing"
    assert all(d.uri.startswith("upload://") and d.source_kind == "upload" for d in docs)
    assert [name for name, _ in await read_upload(ids[0])] == ["billing.md"]  # owner marker hidden


async def test_bad_upload_and_bad_job_body(client):
    r = await client.post("/api/uploads", files=[("files", ("plan.xlsx", b"PK", "application/x"))])
    assert r.status_code == 400 and "unsupported file type" in r.json()["detail"]
    r = await client.post("/api/jobs", json={"goal": "x"})
    assert r.status_code == 422 and r.json()["error"] == "invalid request"


async def test_create_job_uses_orchestrator_412(client):
    ids = await upload_smoke(client, "webhooks-overview.md")
    spec = {"goal": "support bot", "sources": [{"kind": "upload", "upload_ids": ids}], "target_rows": 20}
    r = await client.post("/api/jobs", json=spec)
    assert r.status_code == 412 and r.json() == {"error": "connect AWS first"}


async def test_crash_keeps_error_shape(monkeypatch):
    # A real failure inside the orchestrator (its store read raises) must still answer {error, detail}.
    async def broken_list_jobs(owner_id: str):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(get_orchestrator(), "list_jobs", broken_list_jobs)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://bob") as c:
        r = await c.get("/api/jobs")
    assert r.status_code == 500
    assert r.json() == {"error": "internal error", "detail": "RuntimeError: store unavailable"}


async def test_unknown_job_is_404_everywhere(client):
    for path in ("/api/jobs/nope", "/api/jobs/nope/events", "/api/jobs/nope/rows", "/api/jobs/nope/rows/r1"):
        r = await client.get(path)
        assert r.status_code == 404, path
    assert (await client.post("/api/jobs/nope/cancel")).status_code == 404


async def test_another_users_upload_is_not_usable(client):
    ids = await upload_smoke(client, "webhooks-security.md")  # owned by "local"
    await as_user("intruder")
    spec = {"goal": "steal", "sources": [{"kind": "upload", "upload_ids": ids}]}
    r = await client.post("/api/jobs", json=spec)
    assert r.status_code == 404 and r.json() == {"error": "upload not found"}
    r = await client.post("/api/jobs", json={"goal": "steal", "sources": [], "seed_upload_id": ids[0]})
    assert r.status_code == 404
    with pytest.raises(UploadNotFound):
        await fetch_documents(
            SourceSpec(kind="upload", upload_ids=ids), "t-job", noop_progress, user_id="intruder"
        )
    assert (await client.get("/api/jobs")).json() == []


async def test_health_reports_each_provider_for_real(client, monkeypatch):
    for line in (Path(__file__).resolve().parents[2] / ".env").read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in ("FIRECRAWL_API_KEY", "COMPOSIO_API_KEY"):
            monkeypatch.setenv(key.strip(), value.strip())
    r = await client.get("/api/health")
    assert r.status_code == 200
    keys = r.json()["keys"]
    assert set(keys) == {"bedrock", "jev", "scaledown", "firecrawl", "composio"}
    assert all(isinstance(v, str) and v for v in keys.values())
    assert keys["firecrawl"] == "ok" and keys["composio"] == "ok"


def test_health_scrubs_keys_from_errors(monkeypatch):
    from bob.api.health import scrub

    monkeypatch.setenv("JEV_API_KEY", "jev-secret-123456")
    assert scrub("401 for key jev-secret-123456 at /v1") == "401 for key *** at /v1"
