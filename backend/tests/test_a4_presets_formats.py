"""A4: presets, formats, manifest (pure code on hand-written rows)."""

from __future__ import annotations

import json

import pandas as pd
import pyarrow.parquet as pq
import pytest
from a4_inputs import SYSTEM, make_job, make_pair, make_row, make_rows

from bob.core.models import JobOptions, Message
from bob.export.formats import write_records
from bob.export.manifest import build_manifest, effective_settings, model_ids
from bob.export.presets import PRESETS, get_preset, list_presets


def test_preset_list_matches_contract():
    names = {p["name"] for p in list_presets()}
    assert names == {"openai-chat", "sharegpt", "alpaca", "modelforge-chat", "modelforge-sft", "dpo", "full"}
    for p in list_presets():
        assert {"jsonl", "parquet"} <= set(p["formats"])
    with pytest.raises(ValueError):
        get_preset("nope")


def test_row_presets_shapes():
    row = make_row(1, "Rate limits", "answerable")
    oc = PRESETS["openai-chat"].fn(row, SYSTEM)
    assert [m["role"] for m in oc["messages"]] == ["system", "user", "assistant"]
    assert oc["messages"][0]["content"] == SYSTEM
    sg = PRESETS["sharegpt"].fn(row, SYSTEM)
    assert [c["from"] for c in sg["conversations"]] == ["system", "human", "gpt"]
    al = PRESETS["alpaca"].fn(row, SYSTEM)
    assert al["input"] == "" and al["instruction"] == row.messages[0].content
    assert al["output"] == row.messages[1].content
    sft = PRESETS["modelforge-sft"].fn(row, SYSTEM)
    assert set(sft) == {"prompt", "completion"}
    full = PRESETS["full"].fn(row, SYSTEM)
    assert full["id"] == row.id and full["coords"]["persona"] == "Developer" and full["checks"]
    pair = PRESETS["dpo"].fn(make_pair(row), SYSTEM)
    assert pair["prompt"][0]["role"] == "system" and pair["chosen"] != pair["rejected"]


def test_single_turn_presets_skip_multi_turn():
    row = make_row(2, "Crawling", "answerable")
    row.messages = row.messages + [
        Message(role="user", content="And what about the paid plan, how many then?"),
        Message(
            role="assistant", content="The docs list the paid plan limits on the pricing page, please check."
        ),
    ]
    assert PRESETS["alpaca"].fn(row, SYSTEM) is None
    assert PRESETS["modelforge-sft"].fn(row, SYSTEM) is None
    assert len(PRESETS["openai-chat"].fn(row, SYSTEM)["messages"]) == 5


@pytest.mark.parametrize("preset", list(PRESETS))
@pytest.mark.parametrize("fmt", ["jsonl", "json", "csv", "parquet"])
def test_every_preset_and_format_opens_in_pandas(tmp_path, preset, fmt):
    p = get_preset(preset)
    rows = make_rows()
    if p.source == "pairs":
        recs = [p.fn(make_pair(r), SYSTEM) for r in rows[:3]]
    else:
        recs = [x for x in (p.fn(r, SYSTEM) for r in rows) if x is not None]
    path = write_records(recs, p.columns, tmp_path / f"train.{fmt}", fmt)
    df = {
        "jsonl": lambda: pd.read_json(path, lines=True),
        "json": lambda: pd.read_json(path),
        "csv": lambda: pd.read_csv(path),
        "parquet": lambda: pd.read_parquet(path),
    }[fmt]()
    assert len(df) == len(recs)
    assert set(p.columns) <= set(df.columns)


def test_parquet_nested_schema_is_stable(tmp_path):
    p = get_preset("openai-chat")
    recs = [p.fn(r, SYSTEM) for r in make_rows()]
    path = write_records(recs, p.columns, tmp_path / "t.parquet", "parquet")
    schema = pq.read_schema(path)
    assert str(schema.field("messages").type) == "list<element: struct<role: string, content: string>>"
    full = get_preset("full")
    path = write_records(
        [full.fn(r, SYSTEM) for r in make_rows()], full.columns, tmp_path / "f.parquet", "parquet"
    )
    schema = pq.read_schema(path)
    assert str(schema.field("checks").type) == "string"  # JSON string: stable across rows
    assert str(schema.field("confidence").type) == "double"
    back = json.loads(pd.read_parquet(path)["checks"][0])
    assert back[0]["name"] == "format"


def test_empty_files_keep_columns(tmp_path):
    p = get_preset("dpo")
    for fmt in ("parquet", "csv"):
        path = write_records([], p.columns, tmp_path / f"e.{fmt}", fmt)
        df = pd.read_parquet(path) if fmt == "parquet" else pd.read_csv(path)
        assert list(df.columns) == p.columns and len(df) == 0


def test_manifest_has_effective_settings_and_no_secrets():
    job = make_job(JobOptions(keep_p=0.8, numbers_allow_user="false_premise"))
    m = build_manifest(
        job, make_rows(), preset="openai-chat", formats=["jsonl"], splits={"train": 1}, files=[]
    )
    assert m["settings"]["keep_p"] == 0.8
    assert m["settings"]["numbers_allow_user"] == "false_premise"
    assert not any("api_key" in k or "secret" in k for k in m["settings"])
    assert set(m["models"]) == {"writer", "planner", "judge", "fallback"}
    assert m["models"]["fallback"] == m["models"]["writer"]  # fallback None = writer
    assert m["checks"]["format"]["ran"] == len(make_rows())
    json.dumps(m)  # serializable
    assert effective_settings(job)["keep_p"] == 0.8
    assert model_ids(job)["judge"].startswith("bedrock:")
