"""Who is calling (G1, CONTRACTS §14). There is no sign-in: every caller is the one
built-in user "local". Routes still go through `current_user`, so ownership checks
(404 for another user's job, upload or connection) stay in place and tests can act
as another user by overriding this dependency.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from bob.api.deps import get_orchestrator
from bob.core.models import UserProfile
from bob.orchestrator import Orchestrator

LOCAL_USER_ID = "local"


async def current_user(orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)]) -> UserProfile:
    return await orchestrator.get_or_create_user(LOCAL_USER_ID, None)
