"""Export existing aggregate experiment metrics to TensorBoard; never refit models."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

from torch.utils.tensorboard import SummaryWriter

METRICS = {
    "rmse_t_ha": "rmse_t_ha", "rmse": "rmse_t_ha",
    "mae_t_ha": "mae_t_ha", "mae": "mae_t_ha", "bias_t_ha": "bias_t_ha", "bias": "bias_t_ha",
    "r2": "r2", "spearman": "spearman_overall",
    "rank_inside_clusters": "rank_centered_clusters",
}
LABELS = {
    "fresh_teamDBv1_merge_fold0excluded": "fresh_merge",
    "fresh_teamDBv1_diagnosis_fold0excluded": "fresh_diagnosis",
    "fresh_teamDBv1_weather_fold0excluded": "fresh_weather",
    "fresh_teamDBv1_compact_fold0excluded": "fresh_compact",
    "fresh_teamDBv1_aggregation_fold0excluded": "fresh_temporal",
    "fresh_teamDBv1_multiyear_fold0excluded": "fresh_multiyear",
    "saved_teamDBv1_weather_fold0excluded": "saved_weather",
    "saved_teamDBv1_compact_fold0excluded": "saved_compact",
    "saved_teamDBv1_aggregation_fold0excluded": "saved_temporal",
    "saved_teamDBv1_multiyear_fold0excluded": "saved_multiyear",
    "saved_data_v2_footprint_fold0_in_training": "saved_footprint",
    "saved_data_v2_presto_main_fold0_in_training": "saved_presto",
    "saved_data_v2_presto_posthoc_fold0_in_training": "saved_controls",
}


def safe(value):
    raw = str(value)
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw).strip("._") or "unknown"
    if len(clean) > 14:
        return clean[:14] + "_" + hashlib.sha256(raw.encode()).hexdigest()[:6]
    return clean


def export_table(path, output, label, scope, *, fold=False, cohort_column=None, cohort_name=None):
    written = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row.get("kind") and row["kind"] != "arm":
            continue
        method = row.get("method") or row.get("arm")
        if not method:
            raise ValueError(f"Missing method/arm in {path}")
        cohort = safe(row.get(cohort_column, "lacuna_2023")) if cohort_column else safe(cohort_name or "lacuna_2023")
        run = output / LABELS.get(label, safe(label)) / cohort / safe(method)
        writer = SummaryWriter(str(run))
        try:
            writer.add_text("info/experiment_protocol", label, 0)
            writer.add_text("info/full_model_name", str(method), 0)
            step = int(row["fold"]) if fold else 0
            for col, metric in METRICS.items():
                raw = row.get(col)
                if raw is None or raw == "":
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if math.isfinite(value):
                    writer.add_scalar(f"{scope}/{metric}", value, step)
                    written += 1
        finally:
            writer.close()
    return written


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True, help="Isolated current replay repository")
    p.add_argument("--archive-root", type=Path, required=True, help="Original repository for saved comparison results")
    p.add_argument("--logdir", type=Path, required=True, help="New directory; never overwritten")
    a = p.parse_args(argv)
    a.logdir.mkdir(parents=True, exist_ok=False)
    # Labels encode data, evaluation policy, and whether the result is historical.
    fresh = a.root / "data/runs"
    archive = a.archive_root / "results"
    sources = [
        (fresh/"zimbabwe_merge_v2", "fresh_teamDBv1_merge_fold0excluded", None),
        (fresh/"zimbabwe_transfer_diagnosis_v2", "fresh_teamDBv1_diagnosis_fold0excluded", None),
        (fresh/"zimbabwe_weather_v2", "fresh_teamDBv1_weather_fold0excluded", None),
        (fresh/"zimbabwe_weather_compact_v2", "fresh_teamDBv1_compact_fold0excluded", None),
        (fresh/"zimbabwe_aggregation_v2", "fresh_teamDBv1_aggregation_fold0excluded", None),
        (fresh/"zimbabwe_multiyear_v2", "fresh_teamDBv1_multiyear_fold0excluded", None),
        (archive/"weather_v2/full", "saved_teamDBv1_weather_fold0excluded", None),
        (archive/"weather_v2/compact", "saved_teamDBv1_compact_fold0excluded", None),
        (archive/"aggregation_v2", "saved_teamDBv1_aggregation_fold0excluded", None),
        (archive/"multiyear_v2", "saved_teamDBv1_multiyear_fold0excluded", None),
    ]
    records = []
    for folder, label, cohort in sources:
        for filename, fold in (("metrics.csv", False), ("fold_metrics.csv", True)):
            path = folder / filename
            rec = {"path": str(path), "label": label, "status": "missing"}
            if path.exists():
                try:
                    rec["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    rec["scalars"] = export_table(path, a.logdir, label, "by_fold" if fold else "overall", fold=fold, cohort_column=cohort)
                    rec["status"] = "exported"
                except (OSError, ValueError, KeyError) as exc:
                    rec["status"] = "error"
                    rec["error"] = str(exc)
            records.append(rec)
            print(f"{rec['status']}: {label}/{filename}", flush=True)
    path = a.archive_root / "experiments/footprint/results.csv"
    rec = {"path": str(path), "label": "saved_data_v2_footprint_fold0_in_training", "status": "missing"}
    if path.exists():
        try:
            rec["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            rec["scalars"] = export_table(path, a.logdir, rec["label"], "overall", cohort_column="cohort")
            rec["status"] = "exported"
        except (OSError, ValueError, KeyError) as exc:
            rec.update(status="error", error=str(exc))
    records.append(rec)
    print(f"{rec['status']}: {rec['label']}/results.csv", flush=True)
    for cohort in ("zimbabwe_lacuna_2022_2023", "malawi_2022", "malawi_2023"):
        for file, suffix in (("scores.csv", "main"), ("posthoc_controls.csv", "posthoc")):
            path = a.archive_root/"experiments/presto_finetune/runs"/cohort/file
            label = f"saved_data_v2_presto_{suffix}_fold0_in_training"
            rec = {"path": str(path), "label": label, "cohort": cohort, "status": "missing"}
            if path.exists():
                try:
                    rec["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    rec["scalars"] = export_table(path, a.logdir, label, "overall", cohort_name=cohort)
                    rec["status"] = "exported"
                except (OSError, ValueError, KeyError) as exc:
                    rec.update(status="error", error=str(exc))
            records.append(rec)
            print(f"{rec['status']}: {label}/{cohort}/{file}", flush=True)
    (a.logdir/"manifest.json").write_text(json.dumps({
        "warning": "Retrospective estimates. Fold steps are fold IDs, not training epochs. Different protocols are not directly interchangeable.",
        "sources": records,
    }, indent=2), encoding="utf-8")
    return 1 if any(r["status"] == "error" for r in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
