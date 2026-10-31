"""The one place where the API layer reaches into A1's core (G1).

Confirmed against `aaditya/a1-core` (939263c):
- `bob.config.get_settings()` returns the cached Settings (env BOB_<NAME> -> <name>).
- `Orchestrator()` builds its backends from `bob.core.backends` when no args are given.
- `Orchestrator.subscribe` is an async generator of `Event(id, type, data)`
  (read in `bob.api.sse.event_parts`).
- A missing job or row raises `KeyError`; errors for routes: `PreconditionFailed`
  (412), `JobRunning` (409), `RunnerBusy` (429), mapped in `bob.api.errors`.
"""

from __future__ import annotations

from functools import lru_cache

from bob.config import get_settings
from bob.orchestrator import Orchestrator

settings = get_settings()

__all__ = ["get_orchestrator", "settings"]


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    return Orchestrator()
