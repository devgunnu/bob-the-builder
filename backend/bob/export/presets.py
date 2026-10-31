"""Export presets (CONTRACTS section 11). Owner: A4.

A preset turns one canonical kept `Row` (or one `DPOPair` for `dpo`) into one output record. Pure code.
The system prompt (`Plan.system_prompt`) is added here, at export time; candidates never carry it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from bob.core.models import DPOPair, Message, Row

FORMATS = ["jsonl", "json", "csv", "parquet"]
REQUIRED_FORMATS = ["jsonl", "parquet"]


def _with_system(messages: list[Message], system_prompt: str) -> list[Message]:
    turns = [m for m in messages if m.role != "system"]
    if system_prompt.strip():
        return [Message(role="system", content=system_prompt), *turns]
    return turns


def _msgs(messages: list[Message]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


def is_single_turn(messages: list[Message]) -> bool:
    turns = [m for m in messages if m.role != "system"]
    return len(turns) == 2 and turns[0].role == "user" and turns[1].role == "assistant"


def _first(messages: list[Message], role: str) -> str:
    return next(m.content for m in messages if m.role == role)


def openai_chat(row: Row, system_prompt: str) -> dict | None:
    return {"messages": _msgs(_with_system(row.messages, system_prompt))}


_SHAREGPT_FROM = {"system": "system", "user": "human", "assistant": "gpt"}


def sharegpt(row: Row, system_prompt: str) -> dict | None:
    return {
        "conversations": [
            {"from": _SHAREGPT_FROM[m.role], "value": m.content}
            for m in _with_system(row.messages, system_prompt)
        ]
    }


def alpaca(row: Row, system_prompt: str) -> dict | None:
    if not is_single_turn(row.messages):
        return None  # single turn only
    return {
        "instruction": _first(row.messages, "user"),
        "input": "",
        "output": _first(row.messages, "assistant"),
    }


def modelforge_chat(row: Row, system_prompt: str) -> dict | None:
    return {"messages": _msgs(_with_system(row.messages, system_prompt))}


def modelforge_sft(row: Row, system_prompt: str) -> dict | None:
    if not is_single_turn(row.messages):
        return None
    return {"prompt": _first(row.messages, "user"), "completion": _first(row.messages, "assistant")}


def full(row: Row, system_prompt: str) -> dict | None:
    out = row.model_dump(mode="json")
    out["system_prompt"] = system_prompt
    return out


def dpo(pair: DPOPair, system_prompt: str) -> dict | None:
    return {
        "prompt": _msgs(_with_system(pair.prompt, system_prompt)),
        "chosen": pair.chosen,
        "rejected": pair.rejected,
    }


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    source: str  # "rows" (kept rows) or "pairs" (DPO pairs)
    columns: list[str]  # top-level keys of one record (used for empty files)
    fn: Callable[..., dict | None]
    formats: tuple[str, ...] = tuple(FORMATS)


_ROW_COLUMNS = list(Row.model_fields) + ["system_prompt"]

PRESETS: dict[str, Preset] = {
    p.name: p
    for p in [
        Preset(
            "openai-chat",
            "OpenAI chat fine-tuning: {messages: [system, user, assistant]}",
            "rows",
            ["messages"],
            openai_chat,
        ),
        Preset(
            "sharegpt",
            "ShareGPT: {conversations: [{from: system/human/gpt, value}]}",
            "rows",
            ["conversations"],
            sharegpt,
        ),
        Preset(
            "alpaca",
            "Alpaca: {instruction, input, output} (single-turn rows only)",
            "rows",
            ["instruction", "input", "output"],
            alpaca,
        ),
        Preset(
            "modelforge-chat",
            "ModelForge chat: {messages} canonical columns only",
            "rows",
            ["messages"],
            modelforge_chat,
        ),
        Preset(
            "modelforge-sft",
            "ModelForge SFT: {prompt, completion} (single-turn rows only)",
            "rows",
            ["prompt", "completion"],
            modelforge_sft,
        ),
        Preset(
            "dpo",
            "DPO: {prompt: [messages], chosen, rejected} from proof-backed pairs",
            "pairs",
            ["prompt", "chosen", "rejected"],
            dpo,
        ),
        Preset("full", "Whole canonical row with provenance, spans and checks", "rows", _ROW_COLUMNS, full),
    ]
}


def get_preset(name: str) -> Preset:
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; known: {', '.join(PRESETS)}")
    return PRESETS[name]


def list_presets() -> list[dict]:
    """For G1 `GET /presets`: [{name, formats, description}]."""
    return [
        {"name": p.name, "formats": list(p.formats), "description": p.description} for p in PRESETS.values()
    ]
