"""Settings from env (CONTRACTS section 9). Owner: A1.

Pipeline code never reads thresholds from env or `get_settings()` directly: it calls `settings_for(job)`,
which returns the env defaults with the job's non-None `JobSpec.options` (JobOptions) on top.

Env var names map to fields: `BOB_X` -> `x` (for example `BOB_RUNS_DIR` -> `runs_dir`); other vars use the
lower-case name (`KEEP_P` -> `keep_p`, `JEV_API_KEY` -> `jev_api_key`).

Where values come from:
- local (`BOB_ENV=local`, the default): process env, then `.env` and `../.env` (so it works from the repo
  root and from `backend/`). Local dev only.
- aws (`BOB_ENV=aws` in the process env): process env only. No `.env` file is read. Provider keys come only
  from AWS Secrets Manager (`BOB_SECRET_ARN`, secret `bob/keys`), loaded into the process env by
  `bob.aws.secrets.load_secret_into_env` before Settings is built. A missing ARN or a failed load raises.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from bob.core.models import BedrockAccess, Job, JobOptions, ModelConfig, ModelRoles

CommaList = Annotated[list[str], NoDecode]
CommaFloatMap = Annotated[dict[str, float], NoDecode]


def _f(env: str, default: Any = None, **kw: Any) -> Any:
    """Field read from the env var `env` (case-insensitive); the field name can also be used in code."""
    return Field(default=default, validation_alias=env, **kw)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,  # set per mode in build_settings(): local only
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        env_ignore_empty=True,
    )

    # ---------- Bob's own AWS (hosting); Bedrock only when BOB_BEDROCK_AUTH=default ----------
    aws_region: str | None = _f("AWS_REGION")
    aws_profile: str | None = _f("AWS_PROFILE")

    # ---------- model defaults for new profiles (D33); format <provider>:<model_id> ----------
    default_writer_model: str = _f("BOB_DEFAULT_WRITER_MODEL", "bedrock:global.anthropic.claude-haiku-5-5")
    default_planner_model: str = _f("BOB_DEFAULT_PLANNER_MODEL", "bedrock:global.anthropic.claude-sonnet-5-5")
    default_judge_model: str = _f("BOB_DEFAULT_JUDGE_MODEL", "bedrock:global.anthropic.claude-sonnet-5-5")
    default_fallback_model: str = _f("BOB_DEFAULT_FALLBACK_MODEL", "")  # empty = the writer model
    model_registry: str = _f("BOB_MODEL_REGISTRY", "bob/llm/registry.json")
    kms_key_id: str | None = _f("BOB_KMS_KEY_ID")  # aws: alias/bob-user-keys (P1)

    # ---------- provider keys ----------
    jev_api_key: str = _f("JEV_API_KEY", "")  # Jev API console key; direct Jev API (D34)
    jev_base_url: str = _f("JEV_BASE_URL", "https://api.typesafe.ai")
    jev_model: str = _f("JEV_MODEL", "jev-1.14.0")
    openrouter_api_key: str = _f("OPENROUTER_API_KEY", "")  # optional: only ScaleDown via OpenRouter
    scaledown_api_key: str = _f("SCALEDOWN_API_KEY", "")
    scaledown_base_url: str = _f("SCALEDOWN_BASE_URL", "https://api.scaledown.xyz")
    firecrawl_api_key: str = _f("FIRECRAWL_API_KEY", "")
    composio_api_key: str = _f("COMPOSIO_API_KEY", "")
    composio_user_prefix: str = _f("COMPOSIO_USER_PREFIX", "bob-")
    composio_demo_accounts: str = _f("COMPOSIO_DEMO_ACCOUNTS", "")  # "notion:<connected_account_id>,..."

    # ---------- prices for non-LLM services (USD per M input tokens); LLM prices: registry ----------
    jev_price_in_per_m: float = _f("JEV_PRICE_IN_PER_M", 0.042)
    scaledown_price_in_per_m: float = _f("SCALEDOWN_PRICE_IN_PER_M", 0.04)

    # ---------- verification and generation ----------
    triage_injection_p: float = _f("TRIAGE_INJECTION_P", 0.5)
    triage_pii_p: float = _f("TRIAGE_PII_P", 0.8)
    triage_boilerplate_p: float = _f("TRIAGE_BOILERPLATE_P", 0.8)
    keep_p: float = _f("KEEP_P", 0.9)  # * JobOptions
    reject_p: float = _f("REJECT_P", 0.3)  # *
    audit_rate: float = _f("AUDIT_RATE", 0.02)  # *
    dedup_cos: float = _f("DEDUP_COS", 0.92)
    overgen: float = _f("OVERGEN", 1.6)  # *
    max_rounds: int = _f("MAX_ROUNDS", 3)  # *
    writer_batch: int = _f("WRITER_BATCH", 5)
    writer_concurrency: int = _f("WRITER_CONCURRENCY", 16)
    jev_concurrency: int = _f("JEV_CONCURRENCY", 32)
    scaledown_concurrency: int = _f("SCALEDOWN_CONCURRENCY", 16)
    judge_concurrency: int = _f("JUDGE_CONCURRENCY", 4)
    cache: bool = _f("BOB_CACHE", True)  # BOB_CACHE=0 turns the real-response cache off

    # ---------- verification and data (section 4) ----------
    extract_names_case_types: CommaList = _f(
        "EXTRACT_NAMES_CASE_TYPES", ["answerable", "partial", "unanswerable", "false_premise"]
    )
    extract_exempt_absent: bool = _f("EXTRACT_EXEMPT_ABSENT", True)  # *
    absent_match: int = _f("ABSENT_MATCH", 85)
    numbers_allow_user: Literal["all", "false_premise", "none"] = _f("NUMBERS_ALLOW_USER", "all")  # *
    dpo_mode: Literal["synthesize", "pair", "off"] = _f("DPO_MODE", "synthesize")  # *
    dpo_rate: float = _f("DPO_RATE", 0.3)  # *
    cell_axes: CommaList = _f("CELL_AXES", ["topic", "case_type"])  # *
    max_cells: int = _f("MAX_CELLS", 120)  # *
    max_topics: int = _f("MAX_TOPICS", 20)
    min_cell_target: int = _f("MIN_CELL_TARGET", 3)
    case_mix: CommaFloatMap = _f(  # *
        "CASE_MIX", {"answerable": 0.5, "partial": 0.15, "unanswerable": 0.2, "false_premise": 0.15}
    )

    # ---------- accounts and BYO AWS (section 14) ----------
    bedrock_auth: Literal["default", "assume_role"] = _f("BOB_BEDROCK_AUTH", "default")
    account_id: str | None = _f("BOB_ACCOUNT_ID")
    cred_refresh_s: int = _f("BOB_CRED_REFRESH_S", 300)
    bedrock_default_region: str = _f("BOB_BEDROCK_DEFAULT_REGION", "us-east-1")
    max_active_jobs_per_user: int = _f("BOB_MAX_ACTIVE_JOBS_PER_USER", 1)
    heartbeat_s: int = _f("BOB_HEARTBEAT_S", 10)
    heartbeat_timeout_s: int = _f("BOB_HEARTBEAT_TIMEOUT_S", 90)
    oauth_callback_path: str = _f("BOB_OAUTH_CALLBACK_PATH", "/oauth/callback")

    # ---------- deployment (D25) ----------
    env: Literal["local", "aws"] = _f("BOB_ENV", "local")
    runs_dir: Path = _f("BOB_RUNS_DIR", Path("runs"))  # aws: /tmp/runs
    table: str = _f("BOB_TABLE", "bob")
    bucket: str | None = _f("BOB_BUCKET")
    secret_arn: str | None = _f("BOB_SECRET_ARN")
    ecs_cluster: str | None = _f("BOB_ECS_CLUSTER")
    task_def: str | None = _f("BOB_TASK_DEF")
    subnets: CommaList = _f("BOB_SUBNETS", [])
    security_group: str | None = _f("BOB_SECURITY_GROUP")
    container_name: str = _f("BOB_CONTAINER_NAME", "worker")
    max_workers: int = _f("BOB_MAX_WORKERS", 2)
    control_poll_s: float = _f("BOB_CONTROL_POLL_S", 1.0)
    approval_wait_minutes: int = _f("BOB_APPROVAL_WAIT_MINUTES", 60)
    event_poll_ms: int = _f("BOB_EVENT_POLL_MS", 500)
    sse_heartbeat_s: int = _f("BOB_SSE_HEARTBEAT_S", 15)
    sse_max_s: int = _f("BOB_SSE_MAX_S", 840)
    public_url: str | None = _f("BOB_PUBLIC_URL")
    embed_model_path: str | None = _f("BOB_EMBED_MODEL_PATH")

    @field_validator("extract_names_case_types", "cell_axes", "subnets", mode="before")
    @classmethod
    def _split_list(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("case_mix", mode="before")
    @classmethod
    def _split_map(cls, v: Any) -> Any:
        if isinstance(v, str):
            out: dict[str, float] = {}
            for part in v.split(","):
                if part.strip():
                    key, _, val = part.partition(":")
                    out[key.strip()] = float(val)
            return out
        return v


class EffectiveSettings(Settings):
    """Settings for one job: env defaults with the job's non-None JobOptions on top (CONTRACTS section 9).

    `JobOptions.models` is not a setting: create_job copies it into the `Job.models` snapshot.
    """


# JobOptions fields that are thresholds/modes (all except `models`).
_OPTION_FIELDS = tuple(n for n in JobOptions.model_fields if n != "models")


LOCAL_ENV_FILES = (".env", "../.env")  # local dev only; prod reads keys from Secrets Manager


def process_env_mode() -> Literal["local", "aws"]:
    """BOB_ENV from the process env only (never from a .env file)."""
    return "aws" if os.environ.get("BOB_ENV", "local").strip().lower() == "aws" else "local"


def _load_aws_secret() -> None:
    """aws mode: load the bob/keys secret JSON into os.environ (A5 module, imported lazily). Fails loudly."""
    arn = (os.environ.get("BOB_SECRET_ARN") or "").strip()
    if not arn:
        raise RuntimeError("BOB_ENV=aws needs BOB_SECRET_ARN (secret bob/keys); keys are not read from .env")
    try:
        from bob.aws.secrets import load_secret_into_env  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("BOB_ENV=aws needs bob.aws.secrets.load_secret_into_env (A5)") from e
    try:
        load_secret_into_env(arn)
    except Exception as e:
        raise RuntimeError(f"BOB_ENV=aws: loading secret {arn} failed: {e}") from e


def build_settings(mode: Literal["local", "aws"]) -> Settings:
    """Settings for a mode. aws: process env only (no .env file). local: process env + LOCAL_ENV_FILES."""
    if mode == "aws":
        return Settings(_env_file=None)  # type: ignore[call-arg]
    s = Settings(_env_file=LOCAL_ENV_FILES)  # type: ignore[call-arg]
    if s.env == "aws":
        raise RuntimeError("BOB_ENV=aws must come from the process env, not from a .env file")
    return s


def _drop_empty_aws_vars() -> None:
    """`uvicorn --env-file` exports `AWS_PROFILE=` as an empty string, and boto3 then fails
    every call with `ProfileNotFound: The config profile () could not be found`."""
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        if os.environ.get(name) == "":
            del os.environ[name]


@lru_cache
def get_settings() -> Settings:
    _drop_empty_aws_vars()
    mode = process_env_mode()
    if mode == "aws":
        _load_aws_secret()
    return build_settings(mode)


def settings_for(job: Job) -> EffectiveSettings:
    base = get_settings()
    values = base.model_dump()
    for name in _OPTION_FIELDS:
        value = getattr(job.spec.options, name)
        if value is not None:
            values[name] = value
    return EffectiveSettings.model_construct(**values)


# ---------- model defaults (D33) ----------
def parse_model_spec(spec: str) -> ModelConfig | None:
    """`<provider>:<model_id>` -> ModelConfig. Empty string -> None. The model id can contain ':'."""
    spec = spec.strip()
    if not spec:
        return None
    provider, sep, model_id = spec.partition(":")
    if not sep or not model_id or provider not in ("bedrock", "openai_compatible"):
        raise ValueError(f"bad model spec {spec!r}: want '<bedrock|openai_compatible>:<model_id>'")
    return ModelConfig(provider=provider, model_id=model_id)  # type: ignore[arg-type]


def default_model_roles(settings: Settings | None = None) -> ModelRoles:
    """Default ModelRoles for a new profile, from BOB_DEFAULT_*_MODEL. fallback None = the writer model."""
    s = settings or get_settings()
    return ModelRoles(
        writer=parse_model_spec(s.default_writer_model),
        planner=parse_model_spec(s.default_planner_model),
        judge=parse_model_spec(s.default_judge_model),
        fallback=parse_model_spec(s.default_fallback_model),
    )


def default_bedrock_access(settings: Settings | None = None) -> BedrockAccess:
    """Default BedrockAccess for the local user: BOB_BEDROCK_AUTH mode in BOB_BEDROCK_DEFAULT_REGION."""
    s = settings or get_settings()
    return BedrockAccess(mode=s.bedrock_auth, region=s.bedrock_default_region)
