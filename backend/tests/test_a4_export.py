"""A4: export() file layout, keys, split, manifest, provenance (pure code on hand-written rows)."""

from __future__ import annotations

import json
from collections import Counter

import pandas as pd
from a4_inputs import make_job, make_pair, make_row, make_rows

from bob.config import settings_for
from bob.export import export, export_dir, split_stratified


def test_split_is_stratified_and_one_row_cells_stay_in_train():
    items = [(f"c{c}", f"id{c}-{i}") for c in range(5) for i in range(20)] + [("solo", "only")]
    out = split_stratified(items, lambda x: x[0], lambda x: x[1])
    assert len(out["eval"]) == round(101 * 0.05) == 5
    assert Counter(c for c, _ in out["eval"]) == {f"c{c}": 1 for c in range(5)}
    assert ("solo", "only") in out["train"]
    assert split_stratified(items, lambda x: x[0], lambda x: x[1]) == out  # stable
    small = split_stratified([("a", "1")], lambda x: x[0], lambda x: x[1])
    assert small == {"train": [("a", "1")], "eval": []}


def test_export_openai_chat_layout_and_keys(tmp_path):
    job = make_job()
    rows = make_rows()
    files = export(job, rows, [], "openai-chat", ["jsonl", "parquet"], tmp_path)
    assert set(files) == {
        "openai-chat/train/train.jsonl",
        "openai-chat/train/train.parquet",
        "openai-chat/eval/eval.jsonl",
        "openai-chat/eval/eval.parquet",
        "openai-chat/provenance.parquet",
        "openai-chat/bob_manifest.json",
    }
    for key, url in files.items():
        assert (tmp_path / key).is_file()
        assert url == f"/api/jobs/{job.id}/files/{key}"
    kept = [r for r in rows if r.verdict == "kept"]
    train = pd.read_json(tmp_path / "openai-chat/train/train.jsonl", lines=True)
    ev = pd.read_parquet(tmp_path / "openai-chat/eval/eval.parquet")
    assert len(train) + len(ev) == len(kept)
    assert len(ev) == round(len(kept) * 0.05)
    assert train["messages"][0][0]["role"] == "system"
    prov = pd.read_parquet(tmp_path / "openai-chat/provenance.parquet")
    assert set(prov["row_id"]) == {r.id for r in kept}
    assert json.loads(prov["coords"][0])["persona"]
    m = json.loads((tmp_path / "openai-chat/bob_manifest.json").read_text(encoding="utf-8"))
    assert m["splits"] == {"train": len(train), "eval": len(ev)}
    assert m["settings"]["keep_p"] == settings_for(job).keep_p
    assert "openai-chat/train/train.jsonl" in m["files"]


def test_export_full_and_dpo(tmp_path):
    job = make_job()
    rows = make_rows()
    files = export(job, rows, [], "full", ["jsonl", "parquet", "csv", "json"], tmp_path)
    assert "full/train/train.csv" in files and "full/eval/eval.json" in files
    df = pd.read_parquet(tmp_path / "full/train/train.parquet")
    assert {"id", "checks", "spans", "coords", "confidence", "verdict"} <= set(df.columns)
    kept = [r for r in rows if r.verdict == "kept"]
    pairs = [make_pair(r) for r in kept[:6]]
    files = export(job, rows, pairs, "dpo", ["jsonl", "parquet"], tmp_path)
    tr = pd.read_json(tmp_path / "dpo/train/train.jsonl", lines=True)
    assert len(tr) + len(pd.read_parquet(tmp_path / "dpo/eval/eval.parquet")) == 6
    prov = pd.read_parquet(tmp_path / "dpo/provenance.parquet")
    assert set(prov["mode"]) == {"synthesized"} and json.loads(prov["rejected_checks"][0]) == [
        "extract.names"
    ]
    # DPO_MODE=off -> empty but valid files
    export(job, rows, [], "dpo", ["parquet"], tmp_path / "off")
    assert len(pd.read_parquet(tmp_path / "off/dpo/train/train.parquet")) == 0


def test_single_turn_presets_and_default_dir(tmp_path):
    job = make_job()
    rows = [make_row(i, "Crawling", "answerable") for i in range(3)]
    export(job, rows, [], "alpaca", ["jsonl"], tmp_path)
    assert len(pd.read_json(tmp_path / "alpaca/train/train.jsonl", lines=True)) == 3
    assert export_dir(job) == settings_for(job).runs_dir / job.id / "export"
