"""Run one experiment config: frozen splits in, a row per score in results/metrics.csv out.

    python scripts/run_experiment.py configs/b0_seasonal_indices_ridge.yaml
    python scripts/run_experiment.py configs/b0_seasonal_indices_ridge.yaml --cohorts malawi_2023

One model per cohort, never pooled. Every arm of a cohort is scored on the same rows: labels_v1
rows with include_primary, enough clear months and every feature of every arm. Predictions go to
data/runs/<experiment>/ (git-ignored); the same inputs give identical numbers on every run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.database import connect, wide  # noqa: E402
from cropyield.data.labels import sha256  # noqa: E402
from cropyield.eval.metrics import (BOOTSTRAPPED, SCORES, bootstrap_ci, paired_difference_ci,  # noqa: E402
                                    pearson, rmse, within_group_spearman)
from cropyield.eval.splits import nearest_km  # noqa: E402
from cropyield.models.baselines import coordinates_knn, ridge_cv, train_mean  # noqa: E402

METRICS_PATH = ROOT / "results" / "metrics.csv"
SPLITS_DIR = ROOT / "data" / "splits"
METRIC_COLUMNS = ["run_id", "timestamp", "git_commit", "config", "cohort", "split_family", "split_sha256", "arm",
                  "repeat", "subset", "fold", "seed", "n_train", "n_test", "metric", "value", "ci_low", "ci_high"]
MIN_ROWS = 100


def alphas_of(arm: dict) -> np.ndarray:
    low, high, count = arm["alphas"]["logspace"]
    return np.logspace(low, high, count)


def feature_sources(config: dict) -> set[str]:
    """Database columns the arms need."""
    names = set()
    for arm in config["arms"].values():
        names |= set(arm.get("features", []))
        names |= {arm["vector"]} if "vector" in arm else set()
    return names - {"lat", "lon"}


def load_rows(config: dict, cohort: str) -> pd.DataFrame:
    """labels_v1 rows of the cohort joined to their features; every arm is scored on exactly these."""
    labels = pd.read_parquet(ROOT / config["labels"])
    rows = labels[(labels["cohort"] == cohort) & labels["include_primary"]]
    columns = ", ".join(sorted(feature_sources(config) | {"months_with_data"}))
    con = connect()
    try:
        features = con.execute(f"SELECT obs_id, {columns} FROM master WHERE has_imagery").df()
    finally:
        con.close()
    rows = rows.merge(features, on="obs_id", how="inner")
    rows = rows[rows["months_with_data"] >= config["rows"]["min_clear_months"]]
    for name in feature_sources(config):
        rows = rows[rows[name].map(lambda v: v is not None and np.all(np.isfinite(v)))]
    return rows.reset_index(drop=True)


def design_matrix(rows: pd.DataFrame, arm: dict) -> np.ndarray:
    """The arm's features as a float matrix: scalar columns, or one array column spread out."""
    if "vector" in arm:
        return wide(rows, arm["vector"], "x").to_numpy()
    return rows[arm["features"]].to_numpy(dtype=float)


def fit_predict(arm: dict, rows: pd.DataFrame, train: np.ndarray, test: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Predictions for the test rows from one arm, fitted on the training rows only."""
    y = rows["yield_t_ha"].to_numpy()
    if arm["model"] == "train_mean":
        return train_mean(y[train], int(test.sum()))
    if arm["model"] == "knn":
        latlon = rows[["lat", "lon"]].to_numpy()
        return coordinates_knn(latlon[train], y[train], latlon[test], arm["k"])
    if arm["model"] == "ridge_cv":
        X = design_matrix(rows, arm)
        return ridge_cv(X[train], y[train], groups[train], X[test], alphas_of(arm))[0]
    raise ValueError(f"unknown model {arm['model']}")


def out_of_fold(rows: pd.DataFrame, split: pd.DataFrame, config: dict, buffer_km: float | None) -> pd.DataFrame:
    """Long table of predictions: one row per test field, arm and repeat."""
    frames = []
    columns = ["obs_id", "group_id", "fold", "repeat"] + (["test_subset"] if "test_subset" in split else [])
    joined = rows.merge(split[columns], on="obs_id", how="inner", validate="one_to_many")
    for repeat, table in joined.groupby("repeat"):
        table = table.reset_index(drop=True)
        groups = table["group_id"].astype(str).to_numpy()
        lat, lon = table["lat"].to_numpy(), table["lon"].to_numpy()
        tests = ["test"] if (table["fold"] == "test").any() else sorted(table["fold"].unique())
        for fold in tests:
            test = (table["fold"] == fold).to_numpy()
            train = (table["fold"] == "train").to_numpy() if fold == "test" else ~test
            if buffer_km:  # drop training fields right next to a test field
                near = np.zeros(len(table), dtype=bool)
                near[np.flatnonzero(train)] = nearest_km(lat, lon, train, test) < buffer_km
                train &= ~near
            for name, arm in config["arms"].items():
                predicted = fit_predict(arm, table, train, test, groups)
                frames.append(table.loc[test, columns + ["yield_t_ha"]].assign(arm=name, predicted=predicted,
                                                                                n_train=int(train.sum())))
    return pd.concat(frames, ignore_index=True)


def score_rows(predictions: pd.DataFrame, reference: str, seed: int, base: dict) -> list[dict]:
    """Per-fold and pooled scores of every arm, pooled ones with a cluster-bootstrap interval."""
    out = []
    subsets = [("all", predictions)]
    if "test_subset" in predictions:
        subsets += [(name, part) for name, part in predictions.groupby("test_subset")]
    for (repeat, arm), table in predictions.groupby(["repeat", "arm"]):
        for subset, part in subsets:
            part = part[(part["repeat"] == repeat) & (part["arm"] == arm)]
            if part.empty:
                continue
            y, p = part["yield_t_ha"].to_numpy(), part["predicted"].to_numpy()
            groups = part["group_id"].astype(str).to_numpy()
            row = {**base, "arm": arm, "repeat": repeat, "subset": subset, "n_train": int(part["n_train"].median()), "n_test": len(y)}
            for metric, score in SCORES.items():
                interval = bootstrap_ci(y, p, groups, score, seed=seed) if metric in BOOTSTRAPPED else (None, None)
                out.append({**row, "fold": "pooled", "metric": metric, "value": score(y, p),
                            "ci_low": interval[0], "ci_high": interval[1]})
            out.append({**row, "fold": "pooled", "metric": "spearman_within_group",
                        "value": within_group_spearman(y, p, groups), "ci_low": None, "ci_high": None})
            if arm != reference:
                other = predictions[(predictions["repeat"] == repeat) & (predictions["arm"] == reference)]
                other = other.set_index("obs_id").loc[part["obs_id"], "predicted"].to_numpy()
                low, high = paired_difference_ci(y, p, other, groups, rmse, seed=seed)
                out.append({**row, "fold": "pooled", "metric": f"rmse_minus_{reference}", "value": rmse(y, p) - rmse(y, other),
                            "ci_low": low, "ci_high": high})
            if subset == "all":
                for fold, piece in part.groupby("fold"):
                    a, b = piece["yield_t_ha"].to_numpy(), piece["predicted"].to_numpy()
                    out += [{**row, "fold": fold, "n_test": len(a), "n_train": int(piece["n_train"].iloc[0]), "metric": metric,
                             "value": score(a, b), "ci_low": None, "ci_high": None} for metric, score in SCORES.items()]
    return out


def noise_ceiling(labels: pd.DataFrame, cohort: str, base: dict) -> list[dict]:
    """Agreement of the two cuts on the same fields: the limit no satellite model can pass."""
    rows = labels[(labels["cohort"] == cohort) & labels["include_primary"] & labels["cut2_kg_ha"].notna()]
    a, b = rows["cut1_kg_ha"].to_numpy() / 1000, rows["cut2_kg_ha"].to_numpy() / 1000
    row = {**base, "arm": "noise_ceiling", "repeat": 0, "subset": "all", "fold": "pooled", "n_train": 0, "n_test": len(a),
           "ci_low": None, "ci_high": None}
    return [{**row, "metric": "pearson_cut1_cut2", "value": pearson(a, b)},
            {**row, "metric": "rmse_cut1_cut2_t_ha", "value": rmse(a, b)},
            {**row, "metric": "sd_difference_t_ha", "value": float(np.std(a - b, ddof=1))}]


def git_commit() -> str:
    """HEAD, with "-dirty" when tracked files differ from it: such a run is not reproducible from the commit alone."""
    run = subprocess.run(["git", "describe", "--always", "--dirty", "--abbrev=40"], cwd=ROOT, capture_output=True, text=True, check=False)
    return run.stdout.strip() or "unknown"


def arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path)
    parser.add_argument("--cohorts", nargs="+", help="run only these cohorts of the config")
    parser.add_argument("--no-save", action="store_true", help="print the scores, write nothing (for a pipeline test)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = arguments(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{config['experiment']}-{stamp}"
    run = {"run_id": run_id, "timestamp": stamp, "git_commit": git_commit(),
           "config": args.config.as_posix(), "seed": config["seed"]}
    labels = pd.read_parquet(ROOT / config["labels"])
    manifest = json.loads((SPLITS_DIR / "manifest.json").read_text(encoding="utf-8"))
    if manifest["labels_sha256"] != sha256(ROOT / config["labels"]):
        print("labels_v1 changed after the splits were frozen; stopping.", file=sys.stderr)
        return 1
    rows_out, predictions_out = [], []
    for cohort in args.cohorts or config["cohorts"]:
        rows = load_rows(config, cohort).assign(yield_t_ha=lambda f: f["yield_kg_ha"] / 1000)
        if len(rows) < MIN_ROWS:
            print(f"{cohort}: only {len(rows)} rows with imagery; skipped (minimum {MIN_ROWS})", file=sys.stderr)
            continue
        print(f"{cohort}: {len(rows)} rows")
        for family in config["splits"]:
            path = SPLITS_DIR / f"{cohort}__{family}.csv"
            if not path.exists():
                continue
            digest = sha256(path)
            if digest != manifest["files"][path.name]["sha256"]:
                print(f"{path.name} differs from the manifest; stopping.", file=sys.stderr)
                return 1
            split = pd.read_csv(path, dtype={"group_id": str, "fold": str}, keep_default_na=False)
            buffer_km = config.get("buffer_km", {}).get(cohort, {}).get(family)
            predictions = out_of_fold(rows, split, config, buffer_km)
            base = {**run, "cohort": cohort, "split_family": family, "split_sha256": digest}
            rows_out += score_rows(predictions, config["reference_arm"], config["seed"], base)
            predictions_out.append(predictions.assign(cohort=cohort, family=family))
        if cohort in config.get("noise_ceiling", []):
            rows_out += noise_ceiling(labels, cohort, {**run, "cohort": cohort, "split_family": "none", "split_sha256": ""})
    if not rows_out:
        print("nothing to score", file=sys.stderr)
        return 1
    table = pd.DataFrame(rows_out)[METRIC_COLUMNS]
    print_summary(table)
    if args.no_save:
        return 0
    METRICS_PATH.parent.mkdir(exist_ok=True)
    table.to_csv(METRICS_PATH, mode="a", header=not METRICS_PATH.exists(), index=False, lineterminator="\n")
    out_dir = ROOT / "data" / "runs" / config["experiment"]
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.concat(predictions_out, ignore_index=True).to_parquet(out_dir / f"predictions_{stamp}.parquet", index=False)
    return 0


def print_summary(table: pd.DataFrame) -> None:
    """Pooled scores, one line per cohort, family, repeat and arm."""
    pooled = table[(table["fold"] == "pooled") & (table["subset"] == "all")]
    wanted = ["rmse_t_ha", "r2", "spearman", "spearman_within_group", "bottom20_recall"]
    shown = pooled[pooled["metric"].isin(wanted)].pivot_table(
        index=["cohort", "split_family", "repeat", "arm"], columns="metric", values="value")[wanted]
    print(shown.round(3).to_string())
    deltas = pooled[pooled["metric"].str.startswith("rmse_minus_")]
    print(deltas[["cohort", "split_family", "repeat", "arm", "metric", "value", "ci_low", "ci_high"]].round(3).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
