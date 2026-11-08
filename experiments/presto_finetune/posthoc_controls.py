"""Post-hoc controls, NOT part of PLAN.md: written on 7 Nov 2026 after the first scores were seen.

    python experiments/presto_finetune/posthoc_controls.py --cohort zimbabwe_lacuna_2022_2023

Question: does the P0 gain come from Presto's pre-training, or only from giving Ridge more input numbers?

- X1: Ridge on the raw Presto inputs: 10 bands + NDVI for each of the 9 months (99 numbers). A masked month is
  NaN, filled with the training mean, plus one missing flag per column. Same alpha search as A1.
- X2: frozen embedding of a Presto with random weights (seed 20261029) + the step 8 Ridge. Same inputs as P0.

Same folds and scores as run_cohort.py. Writes runs/<cohort>/posthoc_controls.md and posthoc_controls.csv.
Needs runs/<cohort>/predictions.csv from run_cohort.py.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import presto_lib as lib
import run_cohort
from cropyield.baselines.models import Winsorize

step8 = lib.step8
S2_AND_NDVI = list(range(2, 12)) + [16]  # B2..B12 and NDVI in Presto's NORMED_BANDS order


def raw_features(arrays: lib.Arrays) -> np.ndarray:
    x = arrays.x.numpy()[:, :, S2_AND_NDVI].copy()
    x[arrays.mask.numpy()[:, :, S2_AND_NDVI] == 1] = np.nan
    return x.reshape(len(x), -1)


def ridge_impute_cv(X_train, y_train, groups_train, X_test) -> np.ndarray:
    pipeline = make_pipeline(SimpleImputer(strategy="mean", add_indicator=True, keep_empty_features=True),
                             Winsorize(), StandardScaler(), Ridge())
    search = GridSearchCV(pipeline, {"ridge__alpha": step8.ALPHAS},
                          cv=GroupKFold(n_splits=min(5, len(np.unique(groups_train)))),
                          scoring="neg_mean_squared_error")
    search.fit(X_train, y_train, groups=groups_train)
    return search.predict(X_test)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cohort", default="zimbabwe_lacuna_2022_2023", choices=sorted(lib.WINDOWS))
    args = parser.parse_args(argv)
    out = lib.RUNS / args.cohort
    X, y_series, fields = lib.cohort_rows(args.cohort)
    y = y_series.to_numpy()
    arrays = lib.build_arrays(args.cohort, fields)
    saved = pd.read_csv(out / "predictions.csv", dtype={"fold": str, "group_id": str}).set_index("obs_id")
    groups, folds = fields["group_id"].to_numpy(), fields["fold"].to_numpy()

    raw = raw_features(arrays)
    torch.manual_seed(lib.SEED)
    random_encoder = lib.Presto.construct().encoder.eval()
    random_embedding = lib.embed(random_encoder, arrays, np.arange(len(y)))
    predicted = {arm: np.full(len(y), np.nan) for arm in ("X1", "X2")}
    for fold in lib.SCORED_FOLDS:
        test, train = folds == fold, folds != fold
        predicted["X1"][test] = ridge_impute_cv(raw[train], y[train], groups[train], raw[test])
        predicted["X2"][test] = step8.ridge_cv(random_embedding[train], y[train], groups[train],
                                               random_embedding[test], step8.ALPHAS)[0]
    tested = fields["fold"].isin(lib.SCORED_FOLDS).to_numpy()
    rows = fields.index[tested]
    if not np.allclose(saved.loc[rows, "y_t_ha"].to_numpy(), y[tested]):
        raise RuntimeError("predictions.csv is not on the same fields")
    scored = {arm: saved.loc[rows, arm].to_numpy() for arm in ("A1", "R1", "P0", "P1")}
    scored |= {arm: values[tested] for arm, values in predicted.items()}
    sub = fields[tested]
    arms = run_cohort.arm_scores(y[tested], scored, sub)
    cluster_years = run_cohort.cluster_years_of(sub)
    pairs = pd.DataFrame([{"a": a, "b": b} | run_cohort.pair(y[tested], scored[a], scored[b],
                                                             sub["group_id"].to_numpy(), cluster_years)
                          for a, b in (("X1", "A1"), ("X2", "A1"), ("P0", "X1"), ("P0", "X2"), ("P1", "X1"))])
    pd.concat([arms.assign(kind="arm"), pairs.assign(kind="pair")]).to_csv(out / "posthoc_controls.csv",
                                                                           index=False, lineterminator="\n")
    lines = [f"# Post-hoc controls: {args.cohort}", "",
             "Not in PLAN.md. Written after the first scores were seen, so read them as exploration.", "",
             "X1 = Ridge on the 99 raw monthly inputs (10 bands + NDVI x 9 months, mean-filled + missing flags). "
             "X2 = frozen random-weights Presto + Ridge.", "",
             "| Arm | RMSE, t/ha | MAE, t/ha | Bias, t/ha | R2 | Rank inside clusters |", "|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {r.arm} | {r.rmse:.3f} | {r.mae:.3f} | {r.bias:+.3f} | {r.r2:.3f} | {r.rank_inside_clusters:.3f} |"
              for r in arms.itertuples()]
    lines += ["", "| Pair | RMSE, a minus b | Rank, a minus b |", "|---|---|---|"]
    lines += [f"| {r.a} minus {r.b} | {run_cohort.interval(r.rmse_diff, r.rmse_low, r.rmse_high)} | "
              f"{run_cohort.interval(r.rank_diff, r.rank_low, r.rank_high)} |" for r in pairs.itertuples()]
    text = "\n".join(lines) + "\n"
    (out / "posthoc_controls.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
