from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


su = module("stepup", REPO / "experiments" / "stepup" / "stepup.py")
tf, step8 = su.tf, su.step8

COHORT = "zimbabwe_lacuna_2022_2023"
TEST, BASE = "0", "A1"
TRAIN_FOLDS = ("1", "2", "3", "4")
NAMES = {
    "R0": "R0 training mean",
    "R1": "R1 coordinates only (10 nearest fields)",
    "A1": "A1 5 indices, season max + mean",
    "V0": "V0 mean, whole window",
    "V1": "V1 mean, pre-harvest months",
    "V2": "V2 max (peak value)",
    "V3": "V3 mean + median + max",
    "L1": "L1 GCVI peak only (Li et al. 2022)",
    "M1": "M1 monthly index curve",
    "M2": "M2 monthly band curve",
    "M2-pre": "M2-pre monthly band curve, pre-harvest",
    "P0": "S10 Presto frozen embedding (128)",
    "X1": "X1 raw monthly inputs (10 bands + NDVI x 9 months, mean fill + missing flags)",
}
BASELINES = ("R0", "R1", "A1")
VARIANTS = ("V0", "V1", "V2", "V3", "L1", "M1", "M2", "M2-pre")
LOOKS = HERE / "looks.csv"


def fold0_predict(X: pd.DataFrame, y: pd.Series, fields: pd.DataFrame) -> np.ndarray:
    test = (fields["fold"] == TEST).to_numpy()
    groups = fields["group_id"].to_numpy()
    values, target = X.to_numpy(dtype=float), y.to_numpy()
    return su.fit_predict("Ridge", values[~test], target[~test], groups[~test], values[test])[0]


def features(labels: pd.DataFrame):
    expected, pre_months, _ = tf.COHORTS[COHORT]
    X_a1, y, fields, monthly = tf.load(COHORT, expected, labels)
    variants, _ = tf.build(COHORT, X_a1, y, monthly, pre_months)
    return X_a1, y, fields, {key: variants[NAMES[key]] for key in VARIANTS} | {"P0": presto_embedding(y.index)}


def presto_embedding(index: pd.Index) -> pd.DataFrame:
    path = su.PRESTO / COHORT / "p0_embeddings.npz"
    if not path.exists():
        sys.exit(f"{path} is missing; run the Presto P0 step first.")
    saved = np.load(path, allow_pickle=True)
    p0 = pd.DataFrame(saved["P0"], index=saved["obs_id"].astype(str)).add_prefix("presto_").reindex(index)
    if p0.isna().any().any():
        sys.exit(f"{path} does not cover every field; run the Presto P0 step again.")
    return p0


def x1_predict(y: pd.Series, fields: pd.DataFrame) -> np.ndarray:
    sys.path.insert(0, str(REPO / "experiments" / "presto_finetune"))
    import posthoc_controls
    lib = posthoc_controls.lib
    _, _, lib_fields = lib.cohort_rows(COHORT)
    if set(lib_fields.index) != set(fields.index):
        raise RuntimeError("the Presto rows differ from the step-up rows")
    arrays = lib.build_arrays(COHORT, lib_fields)
    raw = pd.DataFrame(posthoc_controls.raw_features(arrays), index=arrays.obs_ids).reindex(fields.index).to_numpy()
    test = (fields["fold"] == TEST).to_numpy()
    groups, target = fields["group_id"].to_numpy(), y.to_numpy()
    return posthoc_controls.ridge_impute_cv(raw[~test], target[~test], groups[~test], raw[test])


def score(y: np.ndarray, predicted: dict[str, np.ndarray], fields: pd.DataFrame) -> pd.DataFrame:
    groups = fields["group_id"].to_numpy()
    cluster_years = (fields["group_id"] + "|" + fields["season_year"].astype(str)).to_numpy()
    keep = su.in_large_clusters(cluster_years, step8.MIN_CLUSTER_FIELDS)
    rows = []
    for key, p in predicted.items():
        row = {"arm": key, "name": NAMES[key], "rmse": su.rmse(y, p), "mae": su.mae(y, p), "bias": su.bias(y, p),
               "r2": su.r2(y, p), "rank_inside_clusters": su.rank_inside_clusters(y, p, cluster_years,
                                                                                 step8.MIN_CLUSTER_FIELDS)}
        if key not in ("R0", BASE):
            row |= su.versus(y, p, predicted[BASE], groups, cluster_years, keep, False)
        rows.append(row)
    frame = pd.DataFrame(rows)
    family = frame["p_rank"].notna() & ~frame["arm"].isin(BASELINES)
    frame.loc[family, "p_rank_holm"] = tf.holm(frame.loc[family, "p_rank"])
    frame["wins_vs_A1"] = (frame["rank_lo"] > 0) & ~(frame["rmse_lo"] > 0) & (frame["p_rank_holm"] < 0.05)
    return frame


def interval(value: float, low: float, high: float) -> str:
    return "" if pd.isna(value) else f"{value:+.3f} ({low:+.3f} to {high:+.3f})"


def result_text(frame: pd.DataFrame, run: dict) -> str:
    lines = [f"# Fold 0: {COHORT}", "",
             f"Run {run['utc']}, commit `{run['commit']}`. Reason: {run['reason']}", "",
             f"Every model trains on folds 1-4 ({run['n_train']:,} fields) and predicts fold 0 ({run['n_test']:,} fields, "
             f"{run['test_clusters']} clusters). Paired cluster bootstrap against A1, 2,000 draws, seed {run['seed']}. "
             "`p Holm` corrects the rank p-value over every arm except R0, R1 and A1. A win needs the rank interval "
             "above 0, the RMSE interval not entirely worse, and p Holm < 0.05. This is look "
             f"{run['look']} at fold 0 recorded in `looks.csv`.", "",
             "| Arm | RMSE | MAE | Bias | R² | Rank inside clusters | Rank vs A1 | RMSE vs A1 | p Holm | Win |",
             "|---|---:|---:|---:|---:|---:|---|---|---:|---|"]
    for r in frame.itertuples():
        holm = "" if pd.isna(r.p_rank_holm) else f"{r.p_rank_holm:.3f}"
        rank = "" if pd.isna(r.rank_inside_clusters) else f"{r.rank_inside_clusters:.3f}"
        lines.append(f"| {r.name} | {r.rmse:.3f} | {r.mae:.3f} | {r.bias:+.3f} | {r.r2:.3f} | {rank} | "
                     f"{interval(r.rank_vs_A1, r.rank_lo, r.rank_hi)} | {interval(r.rmse_vs_A1, r.rmse_lo, r.rmse_hi)} | "
                     f"{holm} | {'yes' if r.wins_vs_A1 else ''} |")
    return "\n".join(lines) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Score the fixed Lacuna arms on fold 0 (train on folds 1-4).")
    parser.add_argument("--reason", required=True, help="why this look at fold 0 is needed; stored in looks.csv")
    args = parser.parse_args(argv)
    if not args.reason.strip():
        parser.error("--reason must not be empty")
    pin = REPO / "configs" / "team_database_v2.json"
    step8.check_database(tf.V2, pin)
    step8.check_frozen(tf.V2, "labels_v2.parquet", {COHORT: tf.COHORTS[COHORT][0]})
    labels = pd.read_parquet(tf.V2 / "processed" / "labels_v2.parquet").set_index("obs_id")
    X_a1, y, fields, arms = features(labels)
    test = (fields["fold"] == TEST).to_numpy()
    if not set(fields.loc[~test, "fold"]) == set(TRAIN_FOLDS):
        raise RuntimeError("the training rows must be exactly folds 1-4")
    reference = step8.out_of_fold(X_a1, y, fields, TRAIN_FOLDS)
    predicted = {key: reference[key][test] for key in BASELINES}
    if not np.allclose(fold0_predict(X_a1, y, fields), predicted[BASE]):
        raise RuntimeError("the Ridge head must equal the baseline A1")
    predicted |= {key: fold0_predict(X, y, fields) for key, X in arms.items()}
    predicted["X1"] = x1_predict(y, fields)
    if any(np.isnan(p).any() for p in predicted.values()):
        raise RuntimeError("a fold-0 field has no prediction")
    sub = fields[test]
    frame = score(y.to_numpy()[test], predicted, sub)

    utc = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = HERE / "runs" / utc
    out.mkdir(parents=True, exist_ok=False)
    looks = pd.read_csv(LOOKS) if LOOKS.exists() else pd.DataFrame()
    run = {"utc": utc, "commit": step8.git_commit(), "reason": args.reason, "look": len(looks) + 1, "cohort": COHORT,
           "n_train": int((~test).sum()), "n_test": int(test.sum()), "test_clusters": int(sub["group_id"].nunique()),
           "seed": step8.SEED, "arms": list(predicted), "names": {key: NAMES[key] for key in predicted},
           "labels_sha256": sha256(tf.V2 / "processed" / "labels_v2.parquet"),
           "split_sha256": sha256(tf.V2 / "splits" / f"{COHORT}__{step8.FAMILY}.csv"),
           "database_pin_sha256": json.loads(pin.read_text(encoding="utf-8"))["sha256"],
           "script_sha256": sha256(Path(__file__)), "python": sys.version.split()[0]}
    frame.round(6).to_csv(out / "scores.csv", index=False, lineterminator="\n")
    sub[["group_id", "season_year"]].assign(y_t_ha=y.to_numpy()[test], **predicted).to_csv(
        out / "predictions.csv", index_label="obs_id", lineterminator="\n")
    (out / "run.json").write_text(json.dumps(run, indent=1) + "\n", encoding="utf-8")
    text = result_text(frame, run)
    (out / "RESULT.md").write_text(text, encoding="utf-8", newline="\n")
    line = pd.DataFrame([{"look": run["look"], "utc": utc, "commit": run["commit"], "reason": args.reason,
                          "arms": "|".join(predicted), "n_test": run["n_test"], "run": f"runs/{utc}"}])
    pd.concat([looks, line], ignore_index=True).to_csv(LOOKS, index=False, lineterminator="\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
