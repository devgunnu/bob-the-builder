"""Export (CONTRACTS section 11). Owner: A4.

`export()` writes one preset in the given formats under `<runs_dir>/<job_id>/export/<preset>/`:
  <split>/<split>.<ext>     one data file per folder (train 95% / eval 5%, stratified by cell)
  bob_manifest.json         job, plan, counts, cost, checks, model ids, effective settings
  provenance.parquet        row id, cell, coords, spans, checks, confidence (dpo: + row_id, mode, rejected_checks)
It returns {key: download path}; key = path relative to the job export folder (e.g.
`openai-chat/train/train.jsonl`). A1 copies it into `Job.files` and uploads the tree; A4 never calls S3.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Hashable, Sequence
from pathlib import Path

from bob.config import settings_for
from bob.core.models import DPOPair, Job, Row
from bob.export.formats import EXTENSIONS, write_records
from bob.export.manifest import build_manifest, write_manifest
from bob.export.presets import get_preset

SPLITS = ("train", "eval")
EVAL_SHARE = 0.05


def split_stratified[T](
    items: Sequence[T],
    cell_of: Callable[[T], Hashable],
    id_of: Callable[[T], str],
    eval_share: float = EVAL_SHARE,
) -> dict[str, list[T]]:
    """Stratified train/eval split by cell. Total eval = round(n * eval_share); each cell gets its share by
    largest remainder; a cell never gives all its rows to eval (so 1-row cells stay in train). Stable order."""
    by_cell: dict[Hashable, list[T]] = defaultdict(list)
    for it in items:
        by_cell[cell_of(it)].append(it)
    for rows in by_cell.values():
        rows.sort(key=lambda it: hashlib.sha1(id_of(it).encode()).hexdigest())
    total_eval = round(len(items) * eval_share)
    quota = {c: len(r) * eval_share for c, r in by_cell.items()}
    alloc = {c: min(int(q), len(by_cell[c]) - 1) for c, q in quota.items()}
    left = total_eval - sum(alloc.values())
    for c in sorted(quota, key=lambda c: (-(quota[c] - int(quota[c])), str(c))):
        if left <= 0:
            break
        if alloc[c] < len(by_cell[c]) - 1:
            alloc[c] += 1
            left -= 1
    out: dict[str, list[T]] = {"train": [], "eval": []}
    for c in sorted(by_cell, key=str):
        rows = by_cell[c]
        out["eval"].extend(rows[: alloc[c]])
        out["train"].extend(rows[alloc[c] :])
    return out


def _j(v: object) -> str:
    return json.dumps(v, ensure_ascii=False)


def provenance_records(rows: list[Row]) -> list[dict]:
    return [
        {
            "row_id": r.id,
            "cell_id": r.cell_id,
            "case_type": r.case_type,
            "round": r.round,
            "coords": _j(r.coords),
            "spans": _j([s.model_dump(mode="json") for s in r.spans]),
            "checks": _j([c.model_dump(mode="json") for c in r.checks]),
            "confidence": float(r.confidence),
            "verdict": r.verdict,
            "routed_to_judge": r.routed_to_judge,
            "audited": r.audited,
            "spot_check": None if r.spot_check is None else str(r.spot_check).lower(),
        }
        for r in rows
    ]


PROVENANCE_COLUMNS = [
    "row_id",
    "cell_id",
    "case_type",
    "round",
    "coords",
    "spans",
    "checks",
    "confidence",
    "verdict",
    "routed_to_judge",
    "audited",
    "spot_check",
]
DPO_PROVENANCE_COLUMNS = ["pair_id", "mode", "rejected_checks", "rejection_reason", *PROVENANCE_COLUMNS]


def export_dir(job: Job) -> Path:
    return Path(settings_for(job).runs_dir) / job.id / "export"


def export(
    job: Job,
    rows: list[Row],
    pairs: list[DPOPair],
    preset: str,
    formats: list[str],
    out_dir: Path | None = None,
) -> dict[str, str]:
    """Write one preset in `formats`. `out_dir` = the job export folder (default `<runs_dir>/<job_id>/export`)."""
    p = get_preset(preset)
    fmts = list(dict.fromkeys(formats or ["jsonl"]))
    for f in fmts:
        if f not in EXTENSIONS:
            raise ValueError(f"unknown format {f!r}; known: {', '.join(EXTENSIONS)}")
    root = Path(out_dir) if out_dir is not None else export_dir(job)
    base = root / preset
    system_prompt = job.plan.system_prompt if job.plan else ""
    kept = [r for r in rows if r.verdict == "kept"]

    if p.source == "pairs":
        row_by_id = {r.id: r for r in rows}
        usable = [pr for pr in pairs if pr.row_id in row_by_id]
        split = split_stratified(usable, lambda pr: row_by_id[pr.row_id].cell_id, lambda pr: pr.id)
        records = {s: [p.fn(pr, system_prompt) for pr in split[s]] for s in SPLITS}
        prov = []
        for s in SPLITS:
            for pr in split[s]:
                rec = provenance_records([row_by_id[pr.row_id]])[0]
                prov.append(
                    {
                        "pair_id": pr.id,
                        "mode": pr.mode,
                        "rejected_checks": _j(pr.rejected_checks),
                        "rejection_reason": pr.rejection_reason,
                        **rec,
                    }
                )
        prov_cols = DPO_PROVENANCE_COLUMNS
    else:
        exportable = [r for r in kept if p.fn(r, system_prompt) is not None]
        split = split_stratified(exportable, lambda r: r.cell_id, lambda r: r.id)
        records = {s: [p.fn(r, system_prompt) for r in split[s]] for s in SPLITS}
        prov = provenance_records(split["train"] + split["eval"])
        prov_cols = PROVENANCE_COLUMNS

    files: dict[str, str] = {}

    def add(path: Path) -> None:
        key = path.relative_to(root).as_posix()
        files[key] = f"/api/jobs/{job.id}/files/{key}"

    for s in SPLITS:
        for f in fmts:
            add(write_records(records[s], p.columns, base / s / f"{s}.{EXTENSIONS[f]}", f))
    add(write_records(prov, prov_cols, base / "provenance.parquet", "parquet"))
    manifest_path = base / "bob_manifest.json"
    files[manifest_path.relative_to(root).as_posix()] = f"/api/jobs/{job.id}/files/{preset}/bob_manifest.json"
    write_manifest(
        manifest_path,
        build_manifest(
            job,
            rows,
            preset=preset,
            formats=fmts,
            splits={s: len(records[s]) for s in SPLITS},
            files=sorted(files),
        ),
    )
    return files


__all__ = ["export", "export_dir", "split_stratified", "provenance_records"]
