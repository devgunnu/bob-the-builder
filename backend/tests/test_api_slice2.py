"""G1 API slice 2 on the real app, A1's real local core and real providers.

Account routes make real STS / Bedrock calls (on a machine without AWS credentials
they return the exact AWS error, which is what the routes must show). Connector
routes use the real Composio connection of the local user (skipped without one).
The download tests need a finished job: it is written through A1's real local Store
with a real export file on disk (state setup only; nothing is faked).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from bob.api.app import app
from bob.api.auth import current_user
from bob.api.deps import get_orchestrator, settings
from bob.core.models import Job, JobSpec, JobStatus, ModelConfig, ModelRoles

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "demo" / "smoke"
WIKI_TITLES = {
    "Support FAQ (internal)",
    "Escalation policy",
    "Known issues and workarounds",
    "Refunds and credit adjustments",
    "Enterprise and plan-change hand-offs",
    "Reply style guide and canned replies",
}


def _load_env() -> None:
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip()


_load_env()
needs_composio = pytest.mark.skipif(not os.environ.get("COMPOSIO_API_KEY"), reason="needs COMPOSIO_API_KEY")
needs_firecrawl = pytest.mark.skipif(
    not os.environ.get("FIRECRAWL_API_KEY"), reason="needs FIRECRAWL_API_KEY"
)


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bob") as c:
        yield c
    app.dependency_overrides.clear()


async def as_user(user_id: str) -> None:
    other = await get_orchestrator().get_or_create_user(user_id, None)
    app.dependency_overrides[current_user] = lambda: other


# ---------- account ----------


async def test_aws_setup_and_template(client):
    me = (await client.get("/api/me")).json()
    setup = (await client.get("/api/me/aws/setup")).json()
    assert setup["external_id"] == me["external_id"]
    assert setup["template_url"] == "/api/me/aws/template"
    assert f"ExternalId={me['external_id']}" in setup["cli_command"]
    assert "--stack-name BobBedrockAccess" in setup["cli_command"]
    r = await client.get("/api/me/aws/template")
    assert r.status_code == 200 and "BobBedrockAccess" in r.text


async def test_put_and_verify_aws_real_sts(client):
    access = {
        "mode": "assume_role",
        "role_arn": "arn:aws:iam::123456789012:role/BobBedrockAccess",
        "region": "us-east-1",
    }
    profile = (await client.put("/api/me/aws", json=access)).json()
    assert profile["bedrock"]["role_arn"] == access["role_arn"]
    assert profile["bedrock_verified_at"] is None
    result = (await client.post("/api/me/aws/verify")).json()
    assert result["ok"] is False and result["error"]  # real STS error for a role we cannot assume
    restore = {"mode": "default", "region": "us-east-1"}
    assert (await client.put("/api/me/aws", json=restore)).status_code == 200


async def test_put_and_verify_models_real_calls(client):
    model = ModelConfig(model_id="global.anthropic.claude-haiku-5-5").model_dump()
    body = {"writer": model, "planner": model, "judge": model}
    profile = (await client.put("/api/me/models", json=body)).json()
    assert profile["models"]["writer"]["model_id"] == "global.anthropic.claude-haiku-5-5"
    assert profile["models_verified_at"] is None
    assert "api_keys" not in profile["models"]
    result = (await client.post("/api/me/models/verify")).json()
    assert set(result["roles"]) >= {"writer", "planner", "judge"}
    assert all(isinstance(v, str) and v for v in result["roles"].values())


async def test_models_available_shows_real_bedrock_answer(client):
    r = await client.get("/api/me/models/available")
    assert r.status_code in (200, 502)
    if r.status_code == 502:
        assert r.json()["provider"] == "bedrock" and r.json()["detail"]
    else:
        assert r.json()["models"]


async def test_presets_list_matches_a4(client):
    names = {p["name"] for p in (await client.get("/api/presets")).json()}
    assert {"openai-chat", "full", "dpo", "sharegpt"} <= names


# ---------- connectors ----------


@needs_composio
async def test_connectors_list_and_browse_real(client):
    listed = (await client.get("/api/connectors")).json()
    notion = next(c for c in listed if c["toolkit"] == "notion")
    if not notion["connected"]:
        pytest.skip("no active Notion connection for the local user")
    pages = (await client.get(f"/api/connectors/notion/browse?account_id={notion['account_id']}&q=")).json()
    assert WIKI_TITLES <= {p["title"] for p in pages}
    status = (await client.get(f"/api/connectors/notion/status?connection_id={notion['account_id']}")).json()
    assert status == {"connected": True, "account_id": notion["account_id"]}
    await as_user("intruder")
    r = await client.get(f"/api/connectors/notion/status?connection_id={notion['account_id']}")
    assert r.status_code == 404


async def test_connect_rejects_foreign_redirect(client):
    r = await client.post("/api/connectors/notion/connect", json={"redirect_url": "https://evil.example/cb"})
    assert r.status_code == 400 and r.json()["error"] == "redirect_url must point at this app"


@needs_composio
async def test_unsupported_toolkit_is_400(client):
    r = await client.get("/api/connectors/salesforce/browse?account_id=x&q=")
    assert r.status_code in (400, 404)


# ---------- preview ----------


async def _upload(client, *names: str) -> list[str]:
    files = [("files", (n, (SMOKE / n).read_bytes(), "text/markdown")) for n in names]
    return (await client.post("/api/uploads", files=files)).json()["upload_ids"]


async def test_preview_uploads_and_cap(client):
    ids = await _upload(client, "billing.md", "rate-limits.md")
    r = (await client.post("/api/sources/preview", json={"kind": "upload", "upload_ids": ids})).json()
    assert r["capped"] is False
    assert [d["title"] for d in r["documents"]] == ["Billing | Firecrawl", "Rate Limits | Firecrawl"]
    many = await _upload(client, *(["webhooks-overview.md"] * 11))
    r = (await client.post("/api/sources/preview", json={"kind": "upload", "upload_ids": many})).json()
    assert r["capped"] is True and len(r["documents"]) == 10


async def test_preview_rejects_another_users_upload(client):
    ids = await _upload(client, "billing.md")
    await as_user("intruder")
    r = await client.post("/api/sources/preview", json={"kind": "upload", "upload_ids": ids})
    assert r.status_code == 404


@needs_composio
async def test_preview_notion_wiki_real(client):
    listed = (await client.get("/api/connectors")).json()
    notion = next(c for c in listed if c["toolkit"] == "notion")
    if not notion["connected"]:
        pytest.skip("no active Notion connection for the local user")
    pages = (await client.get(f"/api/connectors/notion/browse?account_id={notion['account_id']}&q=")).json()
    ids = [p["id"] for p in pages if p["title"] in WIKI_TITLES]
    spec = {
        "kind": "composio",
        "toolkit": "notion",
        "connected_account_id": notion["account_id"],
        "scope": {"page_ids": ids},
    }
    r = (await client.post("/api/sources/preview", json=spec)).json()
    assert {d["title"] for d in r["documents"]} == WIKI_TITLES
    assert all(d["uri"].startswith("notion://") and d["chars"] > 500 for d in r["documents"])


@needs_firecrawl
async def test_preview_url_real(client):
    spec = {"kind": "url", "url": "https://docs.firecrawl.dev/webhooks/overview", "crawl_limit": 2}
    r = await client.post("/api/sources/preview", json=spec)
    assert r.status_code == 200, r.text
    docs = r.json()["documents"]
    assert 1 <= len(docs) <= 2
    assert docs[0]["uri"] == "https://docs.firecrawl.dev/webhooks/overview" and docs[0]["chars"] > 500


# ---------- finished-job routes ----------


@pytest.fixture
async def done_job():
    orch = get_orchestrator()
    user = await orch.get_or_create_user("local", None)
    now = datetime.now(UTC)
    job = Job(
        id=f"t{os.urandom(5).hex()}",
        spec=JobSpec(goal="download test", sources=[]),
        owner_id=user.id,
        models=user.models,
        status=JobStatus.done,
        created_at=now,
        updated_at=now,
    )
    name = "openai-chat/train/train.jsonl"
    path = Path(settings.runs_dir).resolve() / job.id / "export" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"messages": []}\n')
    job.files = {name: name}
    await orch.store.put_job(job)
    return job, name


async def test_file_url_and_download(client, done_job):
    job, name = done_job
    url = (await client.get(f"/api/jobs/{job.id}/files/{name}/url")).json()["url"]
    assert url == f"/api/jobs/{job.id}/files/{name}"
    r = await client.get(url)
    assert r.status_code == 200 and r.text == '{"messages": []}\n'
    assert (await client.get(f"/api/jobs/{job.id}/files/../../job.json")).status_code == 404
    assert (await client.get(f"/api/jobs/{job.id}/files/openai-chat/eval/eval.jsonl")).status_code == 404
    await as_user("intruder")
    assert (await client.get(f"/api/jobs/{job.id}/files/{name}/url")).status_code == 404


async def test_export_validation_and_spot_check_404(client, done_job):
    job, _ = done_job
    r = await client.post(f"/api/jobs/{job.id}/export", json={"preset": "nope", "formats": ["jsonl"]})
    assert r.status_code == 400 and "openai-chat" in r.json()["detail"]
    r = await client.post(f"/api/jobs/{job.id}/export", json={"preset": "openai-chat", "formats": ["xml"]})
    assert r.status_code == 400 and r.json()["error"] == "unsupported format"
    r = await client.post(f"/api/jobs/{job.id}/rows/missing/spot-check", json={"ok": True})
    assert r.status_code == 404


async def test_resync_is_501_until_sync_lands(client, done_job):
    job, _ = done_job
    r = await client.post(f"/api/jobs/{job.id}/resync")
    assert r.status_code == 501 and r.json()["error"] == "re-sync is not available yet"


async def test_unknown_or_foreign_job_routes_404(client, done_job):
    job, name = done_job
    await as_user("intruder")
    for method, path, body in (
        ("post", f"/api/jobs/{job.id}/export", {"preset": "openai-chat", "formats": ["jsonl"]}),
        ("post", f"/api/jobs/{job.id}/rows/r1/spot-check", {"ok": True}),
        ("post", f"/api/jobs/{job.id}/resync", None),
        ("get", f"/api/jobs/{job.id}/files/{name}", None),
    ):
        r = await getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (path, r.status_code)


async def test_models_roles_from_contract_shape():
    assert set(ModelRoles.model_fields) >= {"writer", "planner", "judge", "fallback"}
