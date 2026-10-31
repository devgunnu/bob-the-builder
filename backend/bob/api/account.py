"""Account routes (G1, CONTRACTS §6 + §14): connect AWS for Bedrock, pick and verify models.

All routes act on the signed-in user only. No route ever returns a stored API key
(`ModelConfig.api_key_set` is the only sign that one exists).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from bob.api.auth import current_user
from bob.api.deps import get_orchestrator, settings
from bob.api.errors import ApiError
from bob.core.models import BedrockAccess, ModelRoles, UserProfile
from bob.orchestrator import Orchestrator

router = APIRouter()

User = Annotated[UserProfile, Depends(current_user)]
Orch = Annotated[Orchestrator, Depends(get_orchestrator)]

TEMPLATE_NAME = "bedrock-role.yaml"
# Image path first (Dockerfile copies infra/templates to /app/infra/templates), then the repo copy.
TEMPLATE_PATHS = (
    Path("/app/infra/templates") / TEMPLATE_NAME,
    Path(__file__).resolve().parents[3] / "infra" / "templates" / TEMPLATE_NAME,
)
LIST_MODELS_TIMEOUT_S = 20.0
STACK_NAME = "BobBedrockAccess"


class ModelsUpdate(ModelRoles):
    """PUT /me/models body: ModelRoles plus optional keys for openai_compatible roles (P1)."""

    api_keys: dict[str, str] | None = None


def cli_command(account_id: str, external_id: str) -> str:
    return (
        f"aws cloudformation deploy --template-file {TEMPLATE_NAME} --stack-name {STACK_NAME} "
        "--capabilities CAPABILITY_NAMED_IAM --parameter-overrides "
        f"BobAccountId={account_id} ExternalId={external_id}"
    )


def template_path() -> Path:
    for path in TEMPLATE_PATHS:
        if path.is_file():
            return path
    raise ApiError(404, "template not found", detail=f"{TEMPLATE_NAME} is not in this build")


@router.get("/me/aws/setup")
async def aws_setup(user: User) -> dict[str, Any]:
    account_id = settings.account_id or ""
    return {
        "bob_account_id": account_id or None,
        "external_id": user.external_id,
        "template_url": "/api/me/aws/template",
        "cli_command": cli_command(account_id or "<BOB_ACCOUNT_ID>", user.external_id),
    }


@router.get("/me/aws/template")
async def aws_template(_: User) -> FileResponse:
    return FileResponse(template_path(), media_type="application/x-yaml", filename=TEMPLATE_NAME)


@router.put("/me/aws")
async def put_aws(access: BedrockAccess, user: User, orchestrator: Orch) -> UserProfile:
    return await orchestrator.update_bedrock(user.id, access)


@router.post("/me/aws/verify")
async def verify_aws(user: User, orchestrator: Orch) -> dict[str, Any]:
    return await orchestrator.verify_bedrock(user.id)


@router.put("/me/models")
async def put_models(body: ModelsUpdate, user: User, orchestrator: Orch) -> UserProfile:
    roles = ModelRoles.model_validate(body.model_dump(exclude={"api_keys"}))
    return await orchestrator.update_models(user.id, roles, body.api_keys or None)


@router.post("/me/models/verify")
async def verify_models(user: User, orchestrator: Orch) -> dict[str, Any]:
    return await orchestrator.verify_models(user.id)


def _list_models(access: BedrockAccess, user_id: str) -> list[dict[str, Any]]:
    from bob.llm.credentials import session_for

    bedrock = session_for(access, f"models-{user_id}").client("bedrock", region_name=access.region)
    models = [
        {
            "id": m["modelId"],
            "name": m.get("modelName") or m["modelId"],
            "provider": m.get("providerName"),
            "kind": "foundation_model",
            "on_demand": "ON_DEMAND" in (m.get("inferenceTypesSupported") or []),
        }
        for m in bedrock.list_foundation_models(byOutputModality="TEXT").get("modelSummaries", [])
    ]
    profiles: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        page = bedrock.list_inference_profiles(**({"nextToken": token} if token else {}))
        profiles += [
            {
                "id": p["inferenceProfileId"],
                "name": p.get("inferenceProfileName") or p["inferenceProfileId"],
                "provider": None,
                "kind": "inference_profile",
                "on_demand": True,
            }
            for p in page.get("inferenceProfileSummaries", [])
            if p.get("status", "ACTIVE") == "ACTIVE"
        ]
        token = page.get("nextToken")
        if not token:
            break
    return profiles + models


@router.get("/me/models/available")
async def models_available(user: User) -> dict[str, Any]:
    """Bedrock models and inference profiles the caller's AWS access can see (P1)."""
    if user.bedrock is None:
        raise ApiError(412, "connect AWS first")
    try:
        models = await asyncio.wait_for(
            asyncio.to_thread(_list_models, user.bedrock, user.id), timeout=LIST_MODELS_TIMEOUT_S
        )
    except TimeoutError as exc:
        raise ApiError(504, "listing models timed out", provider="bedrock") from exc
    except Exception as exc:  # the exact AWS error helps the user fix access
        raise ApiError(
            502, "could not list models", provider="bedrock", detail=f"{type(exc).__name__}: {exc}"
        ) from exc
    return {"region": user.bedrock.region, "models": models}
