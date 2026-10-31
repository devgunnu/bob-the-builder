"""Job state machine; the only backend API the web layer calls (CONTRACTS section 7). Owner: A1.

Signatures are final. Bodies marked "A1 wave 1" come next.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal

from bob.core.backends import get_blobs, get_events, get_runner, get_store
from bob.core.blobs import Blobs
from bob.core.events import EventLog
from bob.core.models import (
    BedrockAccess,
    Event,
    Job,
    JobSpec,
    Message,
    ModelRoles,
    Plan,
    Report,
    Row,
    UserProfile,
)
from bob.core.runner import LocalRunner, Runner
from bob.core.store import Store

_WAVE1 = "A1 wave 1"


class Orchestrator:
    def __init__(
        self,
        store: Store | None = None,
        events: EventLog | None = None,
        blobs: Blobs | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.store = store or get_store()
        self.events = events or get_events()
        self.blobs = blobs or get_blobs()
        self.runner = runner or get_runner()
        if isinstance(self.runner, LocalRunner):
            self.runner.bind(self.run_job)

    # ---------- jobs ----------
    async def create_job(self, spec: JobSpec, user: UserProfile) -> Job:
        """1. user.bedrock_verified_at not set -> 412 {"error": "connect AWS first"}; else models_verified_at
        not set -> 412 {"error": "verify models first"}.
        2. Capacity check before save: RunnerBusy -> route 429 {"error": "too many running jobs"}; nothing saved.
        3. Save Job (owner_id = user.id, bedrock = snapshot of user.bedrock,
           models = spec.options.models or user.models).
        4. Append job.status created + stage.progress {stage: "fetch", done: 0, total: 0,
           detail: "starting worker"}, then runner.start(id, "create"). Returns at once (< 1 s).
        """
        raise NotImplementedError(_WAVE1)

    async def run_job(self, job_id: str, mode: Literal["create", "resync"]) -> None:
        """The whole job body; both runners call it. ingest -> read -> plan -> wait for approval
        (poll store.get_control every BOB_CONTROL_POLL_S, up to BOB_APPROVAL_WAIT_MINUTES; build from
        Control.plan) -> build -> fill gaps -> DPO -> report -> export -> done. Writes Job.heartbeat_at every
        BOB_HEARTBEAT_S, also while it waits. Checks the cancel flag between stages and before each Writer
        call. Budget guard at 0.95 * budget_usd. Any stage exception -> status error + error event.
        """
        raise NotImplementedError(_WAVE1)

    async def approve_plan(self, job_id: str, plan: Plan) -> Job:
        """store.set_control(id, "approved", plan); returns the Job."""
        raise NotImplementedError(_WAVE1)

    async def cancel(self, job_id: str) -> Job:
        """store.set_control(id, "cancel"). If runner.is_running(id) is false: set status cancelled and emit
        the event (the API writes events only when no worker runs). aws runner stop() after 10 s if needed.
        """
        raise NotImplementedError(_WAVE1)

    async def get_job(self, job_id: str) -> Job:
        """Reads the store (DynamoDB / S3 in aws mode) and runs the watchdog: not terminal, heartbeat_at (or
        created_at) older than BOB_HEARTBEAT_TIMEOUT_S, runner.is_running false -> status error,
        error = "worker stopped: <stoppedReason>", one error event (conditional update).
        """
        raise NotImplementedError(_WAVE1)

    async def list_jobs(self, owner_id: str) -> list[Job]:
        """Only this user's jobs."""
        raise NotImplementedError(_WAVE1)

    async def list_rows(
        self,
        job_id: str,
        verdict: Literal["kept", "rejected"] | None = None,
        cell_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[Row]]:
        """(total, page) from the store."""
        raise NotImplementedError(_WAVE1)

    async def get_row(self, job_id: str, row_id: str) -> Row:
        raise NotImplementedError(_WAVE1)

    async def spot_check(self, job_id: str, row_id: str, ok: bool) -> Report:
        """Sets Row.spot_check and returns a rebuilt Report. Only when status is done/cancelled/error and no
        worker runs (else the route returns 409 {"error": "job is running"}). No events. < 25 s.
        """
        raise NotImplementedError(_WAVE1)

    async def export(self, job_id: str, preset: str, formats: list[str]) -> dict[str, str]:
        """Re-export with A4 export(); sets Job.files. Same 409 rule as spot_check. No events. < 25 s."""
        raise NotImplementedError(_WAVE1)

    async def resync(self, job_id: str) -> Job:
        """P1: runner.start(id, "resync") (CONTRACTS section 10)."""
        raise NotImplementedError(_WAVE1)

    def subscribe(self, job_id: str, last_event_id: int | None) -> AsyncIterator[Event]:
        """EventLog.subscribe with replay from last_event_id; runs the watchdog in the SSE loop."""
        raise NotImplementedError(_WAVE1)

    # ---------- users + Bedrock access (section 14) ----------
    async def get_or_create_user(self, user_id: str, email: str | None) -> UserProfile:
        """New profile: random external_id (uuid4, never changed), default models from config; local mode
        also gets a default BedrockAccess.
        """
        raise NotImplementedError(_WAVE1)

    async def update_bedrock(self, user_id: str, access: BedrockAccess) -> UserProfile:
        """Saves the access and clears bedrock_verified_at."""
        raise NotImplementedError(_WAVE1)

    async def verify_bedrock(self, user_id: str) -> dict:
        """AWS access only: sts:AssumeRole (< 25 s). Sets bedrock_verified_at on success; returns the
        /me/aws/verify shape with the exact STS error on failure.
        """
        raise NotImplementedError(_WAVE1)

    # ---------- models (D33) ----------
    async def update_models(
        self, user_id: str, models: ModelRoles, api_keys: dict[str, str] | None = None
    ) -> UserProfile:
        """Saves the ModelRoles (api_keys P1, KMS-encrypted) and clears models_verified_at."""
        raise NotImplementedError(_WAVE1)

    async def verify_models(self, user_id: str) -> dict:
        """One tiny real call per configured role (all providers), checks the JSON output (< 25 s).
        Returns {ok, roles: {writer: "ok" | error, ...}}; sets models_verified_at on success.
        """
        raise NotImplementedError(_WAVE1)

    def health_job(self, user: UserProfile) -> Job:
        """Small system Job (not saved) with the caller's bedrock + models; /health and verify calls pass it."""
        now = datetime.now(UTC)
        return Job(
            id=f"health-{uuid.uuid4().hex[:8]}",
            spec=JobSpec(goal="health check", sources=[]),
            owner_id=user.id,
            bedrock=user.bedrock,
            models=user.models,
            created_at=now,
            updated_at=now,
        )


# ---------- seeds (section 7) ----------
def load_seeds(data: bytes, name: str) -> list[list[Message]]:
    """JSONL {"messages": [...]} or {"user", "assistant"}; CSV columns user,assistant. `name` picks the parser."""
    text = data.decode("utf-8-sig")
    out: list[list[Message]] = []
    if name.lower().endswith(".csv"):
        for rec in csv.DictReader(io.StringIO(text)):
            user, assistant = (rec.get("user") or "").strip(), (rec.get("assistant") or "").strip()
            if user and assistant:
                out.append([Message(role="user", content=user), Message(role="assistant", content=assistant)])
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if "messages" in rec:
            out.append([Message.model_validate(m) for m in rec["messages"]])
        elif "user" in rec and "assistant" in rec:
            out.append(
                [
                    Message(role="user", content=rec["user"]),
                    Message(role="assistant", content=rec["assistant"]),
                ]
            )
    return out
