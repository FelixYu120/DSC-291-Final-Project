"""Cross-cohort transfer: can a model trained in one cohort say anything about another?

    python scripts/run_transfer.py configs/x1_cross_cohort_transfer.yaml

The cohorts measure yield differently (docs/DATA.md), so "harmonization" is tested at three levels,
each one a weaker claim than the one before:

    raw          source t/ha are taken at face value in the target cohort
    calibrated   a few labelled target fields fix the mean level; the rest are scored in t/ha
    rank         only the order of the target fields is scored: no yield unit is assumed at all

Each level runs with source-scaled features, and with target-scaled ones (features standardised
with the target's own unlabelled mean and std, which absorbs a shift in season window or sensor).
Rows go to results/metrics.csv with split_family "transfer" and subset "<source>><target>|<scaling>".
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from cropyield.eval.metrics import bootstrap_ci, r2, rmse, spearman, bottom_recall  # noqa: E402
from cropyield.models.baselines import Winsorize, ridge_cv  # noqa: E402
from run_experiment import METRIC_COLUMNS, METRICS_PATH, alphas_of, git_commit, load_rows  # noqa: E402

CALIBRATION_SHARE = 0.10
CALIBRATION_DRAWS = 20


def scaled(frame_features: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Standardise with the mean and std of `reference`, after clipping at its 1st and 99th percentile."""
    clip = Winsorize().fit(reference)
    centre = clip.transform(reference)
    return (clip.transform(frame_features) - centre.mean(axis=0)) / centre.std(axis=0)


def transfer_predictions(source: pd.DataFrame, target: pd.DataFrame, features: list[str], alphas: np.ndarray,
                         target_scaled: bool) -> np.ndarray:
    """Fit Ridge on the source cohort and predict the target; no target label is used."""
    X_source = source[features].to_numpy(dtype=float)
    X_target = target[features].to_numpy(dtype=float)
    X_source = scaled(X_source, X_source)
    X_target = scaled(X_target, target[features].to_numpy(dtype=float) if target_scaled else source[features].to_numpy(dtype=float))
    return ridge_cv(X_source, source["yield_t_ha"].to_numpy(), source["cluster_2km"].astype(str).to_numpy(), X_target, alphas)[0]


def calibrated_scores(y: np.ndarray, p: np.ndarray, groups: np.ndarray, seed: int) -> dict[str, float]:
    """Mean RMSE and R2 on the target fields left after matching the mean level on 10 % of its groups.

    Only the level is fitted: with a few fields a free slope is unstable, and it is the cohort's level
    that a different cut size or moisture basis moves.
    """
    names = np.unique(groups)
    rmses, r2s = [], []
    for draw in range(CALIBRATION_DRAWS):
        rng = np.random.default_rng(seed + draw)
        chosen = rng.choice(names, size=max(2, round(len(names) * CALIBRATION_SHARE)), replace=False)
        calibration = np.isin(groups, chosen)
        corrected = p[~calibration] + y[calibration].mean() - p[calibration].mean()
        rmses.append(rmse(y[~calibration], corrected))
        r2s.append(r2(y[~calibration], corrected))
    return {"calibrated_rmse_t_ha": float(np.mean(rmses)), "calibrated_r2": float(np.mean(r2s))}


def pair_rows(source_name: str, target_name: str, source: pd.DataFrame, target: pd.DataFrame, config: dict, base: dict) -> list[dict]:
    """Scores of one source -> target pair, for both feature scalings."""
    arm = config["arm"]
    features, alphas = arm["features"], alphas_of(arm)
    y = target["yield_t_ha"].to_numpy()
    groups = target["cluster_2km"].astype(str).to_numpy()
    rows = []
    for scaling, target_scaled in (("source_scaled", False), ("target_scaled", True)):
        p = transfer_predictions(source, target, features, alphas, target_scaled)
        common = {**base, "arm": "A1", "repeat": 0, "subset": f"{source_name}>{target_name}|{scaling}", "fold": "pooled",
                  "n_train": len(source), "n_test": len(y)}
        low, high = bootstrap_ci(y, p, groups, spearman, seed=config["seed"])
        rows.append({**common, "metric": "spearman", "value": spearman(y, p), "ci_low": low, "ci_high": high})
        rows.append({**common, "metric": "bottom20_recall", "value": bottom_recall(y, p), "ci_low": None, "ci_high": None})
        rows.append({**common, "metric": "raw_rmse_t_ha", "value": rmse(y, p), "ci_low": None, "ci_high": None})
        rows.append({**common, "metric": "raw_r2", "value": r2(y, p), "ci_low": None, "ci_high": None})
        for metric, value in calibrated_scores(y, p, groups, config["seed"]).items():
            rows.append({**common, "metric": metric, "value": value, "ci_low": None, "ci_high": None})
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path)
    parser.add_argument("--no-save", action="store_true", help="print the scores, write nothing")
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    frame_config = {**config, "arms": {"A1": config["arm"]}}
    cohorts = {name: load_rows(frame_config, name).assign(yield_t_ha=lambda f: f["yield_kg_ha"] / 1000) for name in config["cohorts"]}
    for name, rows in cohorts.items():
        print(f"{name}: {len(rows)} rows, mean {rows['yield_t_ha'].mean():.2f} t/ha")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = {"run_id": f"{config['experiment']}-{stamp}", "timestamp": stamp, "git_commit": git_commit(), "config": args.config.as_posix(),
            "cohort": "all", "split_family": "transfer", "split_sha256": "", "seed": config["seed"]}
    rows = []
    for source_name in cohorts:
        for target_name in cohorts:
            if source_name != target_name:
                rows += pair_rows(source_name, target_name, cohorts[source_name], cohorts[target_name], config, base)
    table = pd.DataFrame(rows)[METRIC_COLUMNS]
    print(table.pivot_table(index="subset", columns="metric", values="value", sort=False).round(3).to_string())
    if not args.no_save:
        table.to_csv(METRICS_PATH, mode="a", header=not METRICS_PATH.exists(), index=False, lineterminator="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
