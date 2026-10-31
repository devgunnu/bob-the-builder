"""GET /api/health (G1, CONTRACTS §6): one cheap real call per provider, in parallel.

Each check returns "ok" or the provider's error text (keys redacted). Checks bypass
fallbacks and the response cache, so "ok" means that provider itself answered now:
- bedrock:   STS check of the caller's BedrockAccess (AssumeRole, or GetCallerIdentity
             in default mode); "not connected" when the profile has no AWS access.
- jev:       one tiny Jev Decisions call (no fallback chain; unique state, never cached).
- scaledown: one tiny Classify call (unique text, never cached).
- firecrawl: credit-usage lookup (no credits used).
- composio:  list Bob's Notion auth configs (no tool call).
Every check has its own timeout so the route stays well under the 25 s CloudFront limit.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable

from bob.api.deps import settings
from bob.core.models import Job, UserProfile

CHECK_TIMEOUT_S = 15.0
SECRET_ENV = (
    "JEV_API_KEY",
    "SCALEDOWN_API_KEY",
    "FIRECRAWL_API_KEY",
    "COMPOSIO_API_KEY",
    "OPENROUTER_API_KEY",
)


def _secrets() -> list[str]:
    values = [os.environ.get(name, "") for name in SECRET_ENV]
    for attr in ("jev_api_key", "scaledown_api_key", "firecrawl_api_key", "composio_api_key"):
        values.append(str(getattr(settings, attr, "") or ""))
    return [v for v in values if len(v) >= 8]


def scrub(message: str) -> str:
    for secret in _secrets():
        message = message.replace(secret, "***")
    return message[:500]


async def check_bedrock(user: UserProfile) -> str:
    if user.bedrock is None:
        return "not connected"
    from bob.llm.credentials import verify_access

    result = await asyncio.to_thread(verify_access, user.bedrock, user.id)
    return "ok" if result.get("ok") else str(result.get("error") or "failed")


async def check_jev(job: Job) -> str:
    from bob.clients.jev import Question, _jev_call

    question = Question(id="health", type="noul", prompt="The USER message is a greeting")
    await _jev_call(f"USER: hello (health check {uuid.uuid4().hex})", [question], job=job, purpose="health")
    return "ok"


async def check_scaledown(job: Job) -> str:
    from bob.clients.scaledown import classify

    await classify(f"hello, health check {uuid.uuid4().hex}", ["greeting", "complaint"], "health", job=job)
    return "ok"


async def check_firecrawl() -> str:
    from bob.connectors.firecrawl import make_client

    await asyncio.to_thread(make_client().get_credit_usage)
    return "ok"


async def check_composio() -> str:
    from bob.connectors import composio

    await asyncio.to_thread(composio.client().auth_configs.list, toolkit_slug="notion")
    return "ok"


async def _run(check: Callable[[], Awaitable[str]]) -> str:
    try:
        return await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_S)
    except TimeoutError:
        return f"timed out after {int(CHECK_TIMEOUT_S)} s"
    except Exception as exc:  # each provider's own error text is the result
        return scrub(f"{type(exc).__name__}: {exc}")


async def health(user: UserProfile, job: Job) -> dict[str, dict[str, str]]:
    checks: dict[str, Callable[[], Awaitable[str]]] = {
        "bedrock": lambda: check_bedrock(user),
        "jev": lambda: check_jev(job),
        "scaledown": lambda: check_scaledown(job),
        "firecrawl": check_firecrawl,
        "composio": check_composio,
    }
    results = await asyncio.gather(*(_run(check) for check in checks.values()))
    return {"keys": dict(zip(checks, results, strict=True))}
