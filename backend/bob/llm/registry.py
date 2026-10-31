"""Model registry: capabilities and default prices per model id prefix (D33). Owner: A1.

Reads `llm/registry.json` (`BOB_MODEL_REGISTRY`, relative to `backend/` or absolute). Unknown models get safe
defaults: `prompt` JSON mode, no cache, price unknown. `ModelConfig.json_mode` / `cache` / `price_*` override
the registry when they are not `auto` / None.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from bob.core.models import ModelConfig

JsonMode = Literal["tool", "native", "prompt"]
REGION_PREFIXES = ("global.", "us-gov.", "us.", "eu.", "apac.", "jp.", "au.", "ca.")
_BACKEND = Path(__file__).resolve().parents[2]  # backend/


class ModelCaps(BaseModel):
    prefix: str | None = None  # registry entry that matched; None = unknown model (defaults)
    json_mode: JsonMode = "prompt"
    cache: bool = False
    min_cache_tokens: int | None = None
    allows_temperature: bool = True
    max_tokens: int = 4096
    extra_fields: dict[str, Any] = {}
    role_extra_fields: dict[str, dict[str, Any]] = {}
    price_in_per_m: float | None = None
    price_out_per_m: float | None = None
    cache_read_mult: float = 0.1
    cache_write_mult: float = 1.25

    @property
    def known(self) -> bool:
        return self.prefix is not None

    @property
    def price_known(self) -> bool:
        return self.price_in_per_m is not None and self.price_out_per_m is not None

    def fields_for(self, role: str) -> dict[str, Any]:
        """additionalModelRequestFields for a role: extra_fields + role_extra_fields[role] (shallow merge)."""
        out = dict(self.extra_fields)
        out.update(self.role_extra_fields.get(role, {}))
        return out

    def usd(
        self, in_tokens: int, out_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0
    ) -> float | None:
        """Cost of one call; `in_tokens` excludes the cache tokens. None when the price is unknown."""
        if not self.price_known:
            return None
        pin, pout = self.price_in_per_m or 0.0, self.price_out_per_m or 0.0
        return (
            in_tokens * pin
            + cache_read_tokens * pin * self.cache_read_mult
            + cache_write_tokens * pin * self.cache_write_mult
            + out_tokens * pout
        ) / 1_000_000


def strip_region(model_id: str) -> str:
    """'global.anthropic.claude-haiku-5-5' -> 'anthropic.claude-haiku-5-5'. ARNs keep their last path part."""
    mid = model_id.strip()
    if mid.startswith("arn:"):
        mid = mid.rsplit("/", 1)[-1]
    for p in REGION_PREFIXES:
        if mid.startswith(p):
            return mid[len(p) :]
    return mid


def _registry_path() -> Path:
    from bob.config import get_settings

    p = Path(get_settings().model_registry)
    if not p.is_absolute() and not p.is_file():
        p = _BACKEND / p
    return p


@lru_cache
def load_registry(path: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(Path(path or _registry_path()).read_text(encoding="utf-8"))
    entries = sorted(data.get("models", []), key=lambda e: len(e["prefix"]), reverse=True)
    return data.get("default", {}), entries


def caps_for_id(model_id: str) -> ModelCaps:
    """Registry capabilities for a model id (no ModelConfig overrides)."""
    default, entries = load_registry()
    bare = strip_region(model_id)
    for e in entries:
        if bare.startswith(e["prefix"]):
            return ModelCaps(**{**default, **e})
    return ModelCaps(**{k: v for k, v in default.items() if k != "prefix"})


def caps_for(cfg: ModelConfig) -> ModelCaps:
    """Registry capabilities with the ModelConfig overrides on top (json_mode, cache, prices)."""
    caps = caps_for_id(cfg.model_id) if cfg.provider == "bedrock" else ModelCaps()
    upd: dict[str, Any] = {}
    if cfg.json_mode != "auto":
        upd["json_mode"] = cfg.json_mode
    if cfg.cache == "off":
        upd["cache"] = False
    if cfg.price_in_per_m is not None:
        upd["price_in_per_m"] = cfg.price_in_per_m
    if cfg.price_out_per_m is not None:
        upd["price_out_per_m"] = cfg.price_out_per_m
    return caps.model_copy(update=upd) if upd else caps
