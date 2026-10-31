"""Bedrock credentials from a BedrockAccess (D26, CONTRACTS section 14). Owner: A1.

- mode="default": the default boto3 chain (local dev; `AWS_PROFILE` from the env or `.env`).
- mode="assume_role": STS AssumeRole on the user's role with the external id, session name `bob-<job_id>`,
  wrapped in botocore `RefreshableCredentials` that refresh `BOB_CRED_REFRESH_S` (300 s) before expiry.
  Role chaining limits a session to 1 h and a job can wait 60 min for approval, so a client never keeps
  fixed old keys. The STS call uses Bob's own credentials (default chain: the task / Lambda role).

`bedrock_runtime(access, job_id)` returns one cached `bedrock-runtime` client per (access, job) in the
access region. No Anthropic SDK in the request path.
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime
from typing import Any

import boto3
import botocore.session
from botocore.config import Config
from botocore.credentials import RefreshableCredentials

from bob.config import get_settings
from bob.core.models import BedrockAccess

_lock = threading.Lock()
_clients: dict[tuple, Any] = {}

# botocore retries off: the LLM client does 3 retries with backoff itself.
_CLIENT_CONFIG = Config(
    retries={"max_attempts": 1, "mode": "standard"},
    read_timeout=300,
    connect_timeout=10,
    max_pool_connections=64,
)


def session_name(job_id: str) -> str:
    """`bob-<job_id>`, cut to the STS limits (2-64 chars of [\\w+=,.@-])."""
    return re.sub(r"[^\w+=,.@-]", "-", f"bob-{job_id}")[:64]


def base_session() -> boto3.Session:
    """Bob's own AWS session: default chain, with AWS_PROFILE from Settings when set (it can come from .env)."""
    profile = get_settings().aws_profile
    return boto3.Session(profile_name=profile) if profile else boto3.Session()


def _require_role(access: BedrockAccess) -> str:
    if not access.role_arn:
        raise ValueError("assume_role needs BedrockAccess.role_arn")
    return access.role_arn


def assume_role_once(access: BedrockAccess, name: str, duration_s: int = 3600) -> dict[str, Any]:
    """One STS AssumeRole call. Returns botocore credential metadata. Raises the exact botocore error."""
    role_arn = _require_role(access)
    sts = base_session().client(
        "sts", region_name=access.region, endpoint_url=f"https://sts.{access.region}.amazonaws.com"
    )
    kw: dict[str, Any] = {"RoleArn": role_arn, "RoleSessionName": name, "DurationSeconds": duration_s}
    if access.external_id:
        kw["ExternalId"] = access.external_id
    try:
        creds = sts.assume_role(**kw)["Credentials"]
    except Exception as e:
        # role chaining caps a session at 1 h; ask again without a duration when the role allows less
        if duration_s != 900 and "DurationSeconds" in str(e):
            kw["DurationSeconds"] = 900
            creds = sts.assume_role(**kw)["Credentials"]
        else:
            raise
    return {
        "access_key": creds["AccessKeyId"],
        "secret_key": creds["SecretAccessKey"],
        "token": creds["SessionToken"],
        "expiry_time": creds["Expiration"].astimezone(UTC).isoformat(),
    }


def refreshable_credentials(access: BedrockAccess, job_id: str) -> RefreshableCredentials:
    """AssumeRole credentials that refresh BOB_CRED_REFRESH_S before expiry."""
    name = session_name(job_id)

    def _refresh() -> dict[str, Any]:
        return assume_role_once(access, name)

    creds = RefreshableCredentials.create_from_metadata(
        metadata=_refresh(), refresh_using=_refresh, method="sts-assume-role"
    )
    lead = int(get_settings().cred_refresh_s)
    # botocore refreshes at the advisory lead time and blocks on refresh at the mandatory lead time
    creds._advisory_refresh_timeout = lead  # noqa: SLF001
    creds._mandatory_refresh_timeout = lead  # noqa: SLF001
    return creds


def session_for(access: BedrockAccess, job_id: str) -> boto3.Session:
    if access.mode == "default":
        return base_session()
    bs = botocore.session.get_session()
    bs._credentials = refreshable_credentials(access, job_id)  # noqa: SLF001
    return boto3.Session(botocore_session=bs)


def bedrock_runtime(access: BedrockAccess, job_id: str) -> Any:
    """Cached boto3 `bedrock-runtime` client in access.region with the access credentials."""
    if access.mode == "default":
        key: tuple = ("default", get_settings().aws_profile, access.region)
    else:
        key = ("assume_role", access.role_arn, access.external_id, access.region, job_id)
    with _lock:
        client = _clients.get(key)
        if client is None:
            client = session_for(access, job_id).client(
                "bedrock-runtime", region_name=access.region, config=_CLIENT_CONFIG
            )
            _clients[key] = client
        return client


def drop_job(job_id: str) -> None:
    """Forget the cached assume-role clients of a finished job."""
    with _lock:
        for k in [k for k in _clients if k[0] == "assume_role" and k[-1] == job_id]:
            del _clients[k]


def verify_access(access: BedrockAccess, user_id: str) -> dict[str, Any]:
    """AWS access check for POST /me/aws/verify. assume_role: one STS AssumeRole; default: STS
    GetCallerIdentity on the default chain. Returns {ok: True, identity} or {ok: False, error: <exact error>}.
    """
    try:
        if access.mode == "assume_role":
            meta = assume_role_once(access, session_name(f"verify-{user_id}"), duration_s=900)
            sts = boto3.Session(
                aws_access_key_id=meta["access_key"],
                aws_secret_access_key=meta["secret_key"],
                aws_session_token=meta["token"],
            ).client("sts", region_name=access.region)
        else:
            sts = base_session().client("sts", region_name=access.region)
        ident = sts.get_caller_identity()
        return {"ok": True, "identity": ident["Arn"], "checked_at": datetime.now(UTC).isoformat()}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
