"""One fold-0 test of R0, R1, A1 and X1 on Lacuna (see PLAN.md). Train on folds 1-4, predict fold 0.

    python experiments/fold0_final/run_fold0.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "presto_finetune"))

import posthoc_controls  # noqa: E402
import presto_lib as lib  # noqa: E402
import run_cohort  # noqa: E402

COHORT = "zimbabwe_lacuna_2022_2023"
ARMS = ("R0", "R1", "A1", "X1")
PAIRS = (("X1", "A1"), ("X1", "R1"), ("A1", "R1"))


def main() -> int:
    X, y_series, fields = lib.cohort_rows(COHORT)
    y = y_series.to_numpy()
    arrays = lib.build_arrays(COHORT, fields)
    if arrays.obs_ids != list(fields.index):
        raise RuntimeError("inputs are not in the order of the fields")
    test = (fields["fold"] == "0").to_numpy()
    train = ~test
    predicted = lib.step8.out_of_fold(X, y_series, fields, skip=lib.SCORED_FOLDS)  # only fold 0 is tested
    raw = posthoc_controls.raw_features(arrays)
    groups = fields["group_id"].to_numpy()
    predicted["X1"] = np.full(len(y), np.nan)
    predicted["X1"][test] = posthoc_controls.ridge_impute_cv(raw[train], y[train], groups[train], raw[test])

    scored = {arm: predicted[arm][test] for arm in ARMS}
    if any(np.isnan(p).any() for p in scored.values()):
        raise RuntimeError("a fold-0 field has no prediction")
    sub = fields[test]
    arms = run_cohort.arm_scores(y[test], scored, sub)
    cluster_years = run_cohort.cluster_years_of(sub)
    pairs = pd.DataFrame([{"a": a, "b": b} | run_cohort.pair(y[test], scored[a], scored[b],
                                                             sub["group_id"].to_numpy(), cluster_years)
                          for a, b in PAIRS])
    pd.concat([arms.assign(kind="arm"), pairs.assign(kind="pair")]).to_csv(HERE / "scores.csv", index=False,
                                                                           lineterminator="\n")
    sub[["fold", "group_id", "season_year"]].assign(y_t_ha=y[test], **scored).to_csv(
        HERE / "predictions.csv", index_label="obs_id", lineterminator="\n")

    x1a1 = pairs.iloc[0]
    win = x1a1.rank_low > 0 and x1a1.rmse_low <= 0
    lines = [f"# Fold 0 final test: {COHORT}", "",
             f"{int(test.sum())} fields, {sub['group_id'].nunique()} clusters. Trained on folds 1-4. Run once.", "",
             "| Arm | RMSE, t/ha | R2 | Rank inside clusters |", "|---|---:|---:|---:|"]
    lines += [f"| {r.arm} | {r.rmse:.3f} | {r.r2:.3f} | {r.rank_inside_clusters:.3f} |" for r in arms.itertuples()]
    lines += ["", "| Pair | RMSE, a minus b | Rank, a minus b |", "|---|---|---|"]
    lines += [f"| {r.a} minus {r.b} | {run_cohort.interval(r.rmse_diff, r.rmse_low, r.rmse_high)} | "
              f"{run_cohort.interval(r.rank_diff, r.rank_low, r.rank_high)} |" for r in pairs.itertuples()]
    lines += ["", f"X1 beats A1 under the PLAN.md rule: {'yes' if win else 'no'}."]
    text = "\n".join(lines) + "\n"
    (HERE / "RESULT.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
