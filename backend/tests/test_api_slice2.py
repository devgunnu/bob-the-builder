"""G1 API slice 2 on the real app and A1's real local core (BOB_ENV=local, BOB_AUTH=none).

Covers the account, source and result routes without paid calls: profile edits go to
the real local store, the preview parses real smoke uploads, and the file route serves
a real blob. Provider calls (STS, Bedrock, Composio, Firecrawl) are covered by the
connector tests and the end-to-end run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from bob.api.app import app
from bob.api.auth import current_user
from bob.api.deps import get_orchestrator
from bob.core.models import Job, JobSpec, JobStatus

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


async def test_aws_setup_and_template(client):
    me = (await client.get("/api/me")).json()
    setup = (await client.get("/api/me/aws/setup")).json()
    assert setup["external_id"] == me["external_id"]
    assert setup["template_url"] == "/api/me/aws/template"
    assert f"ExternalId={me['external_id']}" in setup["cli_command"]
    assert "--stack-name BobBedrockAccess" in setup["cli_command"]
    r = await client.get("/api/me/aws/template")
    assert r.status_code == 200 and "RoleName: BobBedrockAccess" in r.text
    assert "attachment" in r.headers["content-disposition"]


async def test_save_aws_clears_verification_and_pins_external_id(client):
    await as_user("aws-saver")
    body = {
        "mode": "assume_role",
        "role_arn": "arn:aws:iam::123456789012:role/BobBedrockAccess",
        "external_id": "forged",
        "region": "eu-west-1",
    }
    r = await client.put("/api/me/aws", json=body)
    assert r.status_code == 200, r.text
    profile = r.json()
    assert profile["bedrock"]["region"] == "eu-west-1"
    assert profile["bedrock"]["external_id"] == profile["external_id"] != "forged"
    assert profile["bedrock_verified_at"] is None


async def test_models_validation_and_p1_keys(client):
    await as_user("model-saver")
    me = (await client.get("/api/me")).json()
    r = await client.put("/api/me/models", json={"writer": {"provider": "bedrock"}})
    assert r.status_code == 422 and r.json()["error"] == "invalid request"
    r = await client.put("/api/me/models", json={**me["models"], "api_keys": {"writer": "sk-1"}})
    assert r.status_code == 501
    models = {
        **me["models"],
        "judge": {**me["models"]["judge"], "model_id": "us.anthropic.claude-sonnet-5-5"},
    }
    r = await client.put("/api/me/models", json=models)
    assert (
        r.status_code == 200 and r.json()["models"]["judge"]["model_id"] == "us.anthropic.claude-sonnet-5-5"
    )
    assert r.json()["models_verified_at"] is None


async def test_presets_list(client):
    names = {p["name"] for p in (await client.get("/api/presets")).json()}
    assert {"openai-chat", "full", "dpo", "sharegpt"} <= names


async def test_preview_of_uploads_parses_real_files(client):
    files = [
        ("files", (n, (SMOKE / n).read_bytes(), "text/markdown")) for n in ("billing.md", "rate-limits.md")
    ]
    ids = (await client.post("/api/uploads", files=files)).json()["upload_ids"]
    r = await client.post("/api/sources/preview", json={"kind": "upload", "upload_ids": ids})
    assert r.status_code == 200, r.text
    docs = r.json()["documents"]
    assert [d["title"] for d in docs] == ["Billing | Firecrawl", "Rate Limits | Firecrawl"]
    assert all(d["chars"] > 1000 for d in docs) and r.json()["capped"] is False
    await as_user("intruder-2")
    r = await client.post("/api/sources/preview", json={"kind": "upload", "upload_ids": ids})
    assert r.status_code == 404


async def test_connect_only_redirects_to_our_callback(client):
    r = await client.post("/api/connectors/notion/connect", json={"redirect_url": "https://evil.example/cb"})
    assert r.status_code == 400 and "oauth/callback" in r.json()["error"]


async def _done_job(owner_id: str, files: dict[str, str]) -> Job:
    now = datetime.now(UTC)
    orch = get_orchestrator()
    user = await orch.get_or_create_user(owner_id, None)
    job = Job(
        id=f"t{now.strftime('%H%M%S%f')}",
        spec=JobSpec(goal="file route test", sources=[]),
        owner_id=owner_id,
        bedrock=user.bedrock,
        models=user.models,
        status=JobStatus.done,
        files=files,
        created_at=now,
        updated_at=now,
    )
    await orch.store.put_job(job)
    return job


async def test_files_url_and_download(client):
    name = "openai-chat/train/train.jsonl"
    job = await _done_job("local", {name: "x"})
    data = (SMOKE / "seeds.jsonl").read_bytes()
    await get_orchestrator().blobs.put(f"runs/{job.id}/export/{name}", data)
    r = await client.get(f"/api/jobs/{job.id}/files/{name}/url")
    assert r.status_code == 200 and r.json() == {"url": f"/api/jobs/{job.id}/files/{name}"}
    r = await client.get(r.json()["url"])
    assert r.status_code == 200 and r.content == data
    assert (await client.get(f"/api/jobs/{job.id}/files/other.jsonl")).status_code == 404
    assert (await client.get(f"/api/jobs/{job.id}/files/../job.json")).status_code == 404
    await as_user("intruder-3")
    assert (await client.get(f"/api/jobs/{job.id}/files/{name}/url")).status_code == 404


async def test_export_checks_preset_and_formats(client):
    job = await _done_job("local", {})
    r = await client.post(f"/api/jobs/{job.id}/export", json={"preset": "nope", "formats": ["jsonl"]})
    assert r.status_code == 400
    r = await client.post(f"/api/jobs/{job.id}/export", json={"preset": "openai-chat", "formats": ["xlsx"]})
    assert r.status_code == 400 and r.json()["detail"] == ["xlsx"]


async def test_resync_is_501_and_new_routes_hide_other_jobs(client):
    job = await _done_job("local", {})
    assert (await client.post(f"/api/jobs/{job.id}/resync")).status_code == 501
    await as_user("intruder-4")
    assert (await client.post(f"/api/jobs/{job.id}/resync")).status_code == 404
    assert (
        await client.post(f"/api/jobs/{job.id}/export", json={"preset": "full", "formats": ["jsonl"]})
    ).status_code == 404
    assert (await client.post(f"/api/jobs/{job.id}/rows/r1/spot-check", json={"ok": True})).status_code == 404
