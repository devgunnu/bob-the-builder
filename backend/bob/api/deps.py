"""The one place where the API layer reaches into A1's core (G1).

The contract names these pieces but not every detail of how they are exposed.
The assumptions below are logged in .agents/CHANGES_REQUESTED.md for A1 to
confirm; if A1's code differs, only this file changes.

Assumptions:
- `bob.config.settings` is a pydantic-settings object; env BOB_<NAME> maps to
  attribute <name> (BOB_RUNS_DIR -> settings.runs_dir, CONTRACTS §0 rule 7).
- `Orchestrator()` takes no constructor arguments and picks its backends
  through `bob.core.backends`.
- Events yielded by `Orchestrator.subscribe` have `seq: int`, `type: str` and
  `data: dict` (the same three values as `EventLog.append(job_id, type, data) -> seq`).
  Read in `bob.api.sse.event_parts`.
- A missing job or row raises `LookupError` (for example `KeyError`).
"""

from __future__ import annotations

from functools import lru_cache

from bob.config import settings
from bob.orchestrator import Orchestrator

__all__ = ["get_orchestrator", "settings"]


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    return Orchestrator()
