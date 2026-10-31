"""Sign-in check (G1, CONTRACTS §14, D27).

BOB_AUTH=none    -> every caller is the user "local" (local development).
BOB_AUTH=cognito -> `Authorization: Bearer <access token>` is verified against
                    the user pool JWKS: signature, issuer, expiry,
                    token_use == "access" and client_id. An ID token or a token
                    from another app client fails.
Then `Orchestrator.get_or_create_user` returns the UserProfile.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Request

from bob.api.deps import get_orchestrator, settings
from bob.api.errors import ApiError
from bob.core.models import UserProfile
from bob.orchestrator import Orchestrator

LOCAL_USER_ID = "local"
AUTH_MODES = ("none", "cognito")
JWKS_CACHE_S = 3600
CLOCK_SKEW_S = 30


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str | None


class InvalidToken(Exception):
    pass


def check_auth_config() -> None:
    """Fail fast at startup when BOB_AUTH is unknown or Cognito ids are missing."""
    mode = settings.auth
    if mode not in AUTH_MODES:
        raise RuntimeError(f"BOB_AUTH must be one of {AUTH_MODES}, got {mode!r}")
    if mode == "cognito":
        missing = [
            env
            for env, value in (
                ("BOB_COGNITO_REGION", settings.cognito_region),
                ("BOB_COGNITO_USER_POOL_ID", settings.cognito_user_pool_id),
                ("BOB_COGNITO_CLIENT_ID", settings.cognito_client_id),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"BOB_AUTH=cognito needs {', '.join(missing)}")


def cognito_issuer() -> str:
    return f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        f"{cognito_issuer()}/.well-known/jwks.json",
        cache_keys=True,
        lifespan=JWKS_CACHE_S,
    )


def _decode_access_token(token: str) -> Identity:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=cognito_issuer(),
            leeway=CLOCK_SKEW_S,
            options={
                "require": ["exp", "iss", "sub", "token_use"],
                "verify_aud": False,
            },
        )
    except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
        raise InvalidToken(str(exc)) from exc
    if claims.get("token_use") != "access":
        raise InvalidToken("not an access token")
    if claims.get("client_id") != settings.cognito_client_id:
        raise InvalidToken("token is for another app client")
    # Access tokens carry no email claim unless a pre-token-generation trigger adds one.
    return Identity(user_id=str(claims["sub"]), email=claims.get("email"))


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def identify(request: Request) -> Identity:
    if settings.auth == "none":
        return Identity(user_id=LOCAL_USER_ID, email=None)
    token = bearer_token(request)
    if token is None:
        raise ApiError(401, "sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        # PyJWKClient fetches the JWKS with blocking urllib on a cache miss.
        return await asyncio.to_thread(_decode_access_token, token)
    except InvalidToken as exc:
        raise ApiError(
            401,
            "sign in required",
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def current_user(
    request: Request, orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)]
) -> UserProfile:
    identity = await identify(request)
    return await orchestrator.get_or_create_user(identity.user_id, identity.email)
