"""Export formats: jsonl, json, csv, parquet (CONTRACTS section 11). Owner: A4.

Parquet and CSV need a stable schema for nested fields:
- a column whose every value is a list of flat string dicts with one key set (messages, conversations)
  becomes parquet `list<struct<key: string, ...>>`; CSV gets a JSON string;
- every other nested value (dict, list) becomes a JSON string;
- scalars keep their type (a column with mixed scalar types becomes a JSON string).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

EXTENSIONS = {"jsonl": "jsonl", "json": "json", "csv": "csv", "parquet": "parquet"}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=False)


def _struct_keys(values: list[Any]) -> list[str] | None:
    """Key list if every value is a list of flat str dicts with the same keys, else None."""
    keys: list[str] | None = None
    seen_item = False
    for v in values:
        if not isinstance(v, list):
            return None
        for item in v:
            if not isinstance(item, dict) or not all(isinstance(x, str) for x in item.values()):
                return None
            k = list(item.keys())
            if keys is None:
                keys = k
            elif set(k) != set(keys):
                return None
            seen_item = True
    return keys if seen_item else None


_SCALAR_TYPES = {bool: pa.bool_(), int: pa.int64(), float: pa.float64(), str: pa.string()}


def _column(values: list[Any]) -> pa.Array:
    keys = _struct_keys(values)
    if keys is not None:
        typ = pa.list_(pa.struct([(k, pa.string()) for k in keys]))
        return pa.array([[{k: item[k] for k in keys} for item in v] for v in values], type=typ)
    kinds = {type(v) for v in values if v is not None}
    if kinds <= {int, float} and kinds:
        typ = pa.float64() if float in kinds else pa.int64()
        return pa.array(values, type=typ)
    if len(kinds) == 1 and next(iter(kinds)) in _SCALAR_TYPES:
        return pa.array(values, type=_SCALAR_TYPES[next(iter(kinds))])
    if not kinds:
        return pa.array(values, type=pa.string())
    return pa.array([None if v is None else _dumps(v) for v in values], type=pa.string())


def to_table(records: list[dict], columns: list[str]) -> pa.Table:
    cols = list(columns)
    for r in records:
        for k in r:
            if k not in cols:
                cols.append(k)
    return pa.table({c: _column([r.get(c) for r in records]) for c in cols})


def _csv_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return _dumps(value)
    return "" if value is None else value


def write_records(records: list[dict], columns: list[str], path: Path, fmt: str) -> Path:
    """Write records to `path` in `fmt`. Creates parent folders. Returns the path."""
    if fmt not in EXTENSIONS:
        raise ValueError(f"unknown format {fmt!r}; known: {', '.join(EXTENSIONS)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for r in records:
                f.write(_dumps(r) + "\n")
    elif fmt == "json":
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "csv":
        cols = list(columns)
        for r in records:
            cols.extend(k for k in r if k not in cols)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in records:
                w.writerow({c: _csv_cell(r.get(c)) for c in cols})
    else:
        pq.write_table(to_table(records, columns), path)
    return path
