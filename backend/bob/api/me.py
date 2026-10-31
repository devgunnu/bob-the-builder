"""Account routes (G1, CONTRACTS §6 and §14): AWS access and models per role.

`/me` itself lives in routes.py. Every route here needs a signed-in user and acts
only on that user's own profile. Verify calls are real calls (STS AssumeRole or the
default chain, one tiny model call per role) and finish in under 25 s.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import FileResponse
from pydantic import ValidationError

from bob.api.auth import current_user
from bob.api.deps import get_orchestrator, settings
from bob.api.errors import ApiError
from bob.core.models import BedrockAccess, ModelRoles, UserProfile
from bob.orchestrator import Orchestrator

router = APIRouter()

User = Annotated[UserProfile, Depends(current_user)]
Orch = Annotated[Orchestrator, Depends(get_orchestrator)]

TEMPLATE_NAME = "bedrock-role.yaml"
# The Docker image copies infra/templates/ to /app/infra/templates/ (CONTRACTS §13);
# a local checkout reads the repo copy.
TEMPLATE_DIRS = (
    Path("/app/infra/templates"),
    Path(__file__).resolve().parents[3] / "infra" / "templates",
)
STACK_NAME = "BobBedrockAccess"
LIST_MODELS_TIMEOUT_S = 20


def template_path() -> Path | None:
    for folder in TEMPLATE_DIRS:
        path = folder / TEMPLATE_NAME
        if path.is_file():
            return path
    return None


@lru_cache(maxsize=1)
def _sts_account_id() -> str | None:
    """Bob's own AWS account id from the default chain, looked up once."""
    import boto3

    try:
        return str(boto3.client("sts").get_caller_identity()["Account"])
    except Exception:  # no or bad local credentials: the screen says how to set it
        return None


async def bob_account_id() -> str | None:
    if settings.account_id:
        return settings.account_id
    return await asyncio.to_thread(_sts_account_id)


def cli_command(account_id: str | None, external_id: str) -> str:
    return (
        f"aws cloudformation deploy --template-file {TEMPLATE_NAME} --stack-name {STACK_NAME} "
        "--capabilities CAPABILITY_NAMED_IAM --parameter-overrides "
        f"BobAccountId={account_id or '<bob-account-id>'} ExternalId={external_id}"
    )


# ---------- AWS access ----------


@router.get("/me/aws/setup")
async def aws_setup(user: User) -> dict[str, Any]:
    account_id = await bob_account_id()
    return {
        "bob_account_id": account_id,
        "external_id": user.external_id,
        "template_url": "/api/me/aws/template",
        "cli_command": cli_command(account_id, user.external_id),
    }


@router.get("/me/aws/template")
async def aws_template(user: User) -> FileResponse:
    del user  # signed-in users only
    path = template_path()
    if path is None:
        raise ApiError(404, "template not found", detail=f"{TEMPLATE_NAME} is missing from infra/templates")
    return FileResponse(path, media_type="application/x-yaml", filename=TEMPLATE_NAME)


@router.put("/me/aws")
async def save_aws(access: BedrockAccess, user: User, orchestrator: Orch) -> UserProfile:
    return await orchestrator.update_bedrock(user.id, access)


@router.post("/me/aws/verify")
async def verify_aws(user: User, orchestrator: Orch) -> dict[str, Any]:
    return await orchestrator.verify_bedrock(user.id)


# ---------- models (D33) ----------


@router.put("/me/models")
async def save_models(user: User, orchestrator: Orch, body: Annotated[dict[str, Any], Body()]) -> UserProfile:
    """Body = ModelRoles, plus optional `api_keys: {role: key}` for openai_compatible (P1)."""
    raw = dict(body)
    api_keys = raw.pop("api_keys", None) or None
    try:
        models = ModelRoles.model_validate(raw)
    except ValidationError as exc:
        detail = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise ApiError(422, "invalid request", detail=detail) from exc
    try:
        return await orchestrator.update_models(user.id, models, api_keys)
    except NotImplementedError as exc:
        raise ApiError(
            501, "API keys for OpenAI-compatible endpoints are not available yet", detail=str(exc)
        ) from exc


@router.post("/me/models/verify")
async def verify_models(user: User, orchestrator: Orch) -> dict[str, Any]:
    return await orchestrator.verify_models(user.id)


def _list_bedrock_models(access: BedrockAccess, user_id: str) -> list[dict[str, Any]]:
    """Text models and inference profiles the caller's access can see in its region."""
    from bob.llm.credentials import session_for

    client = session_for(access, f"models-{user_id}").client("bedrock", region_name=access.region)
    out: list[dict[str, Any]] = []
    for profile in client.list_inference_profiles(maxResults=1000).get("inferenceProfileSummaries", []):
        if profile.get("status") == "ACTIVE":
            out.append(
                {
                    "id": profile["inferenceProfileId"],
                    "name": profile.get("inferenceProfileName", ""),
                    "kind": "profile",
                }
            )
    for model in client.list_foundation_models(byOutputModality="TEXT").get("modelSummaries", []):
        if "ON_DEMAND" in model.get("inferenceTypesSupported", []):
            out.append(
                {
                    "id": model["modelId"],
                    "name": f"{model.get('providerName', '')} {model.get('modelName', '')}".strip(),
                    "kind": "model",
                }
            )
    return out


@router.get("/me/models/available")
async def available_models(user: User) -> list[dict[str, Any]]:
    """P1: Bedrock models and inference profiles in the user's region, through their access."""
    if user.bedrock is None:
        raise ApiError(412, "connect AWS first")
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_list_bedrock_models, user.bedrock, user.id), timeout=LIST_MODELS_TIMEOUT_S
        )
    except TimeoutError as exc:
        raise ApiError(504, "Bedrock did not answer in time", provider="bedrock") from exc
    except Exception as exc:
        raise ApiError(
            502, "could not list Bedrock models", provider="bedrock", detail=f"{type(exc).__name__}: {exc}"
        ) from exc
