#!/usr/bin/env python3
"""Recompute pooled R² independently from committed out-of-fold predictions.

Does not import experiment/scoring code, fit models, or require the shared database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(release, output):
    predictions = pd.read_csv(release / "predictions.csv")
    recorded = pd.read_csv(release / "metrics.csv").set_index("method")
    membership = pd.read_csv(release / "target_memberships.csv")
    expected = membership[membership.inner_fold.eq(0) & membership.role.eq("evaluation")]
    assert len(expected) == 1504 and expected.obs_id.is_unique
    expected = expected.set_index("obs_id").outer_fold.sort_index()
    assert not predictions.duplicated(["method", "obs_id"]).any()
    assert set(predictions.method) == set(recorded.index)
    reference = None
    scores, fold_rows = [], []
    for name, part in predictions.groupby("method", sort=False):
        part = part.set_index("obs_id").sort_index()
        pd.testing.assert_series_equal(part.outer_fold, expected, check_names=False)
        assert part.outer_fold.value_counts().to_dict() == {1: 376, 2: 376, 3: 376, 4: 376}
        if reference is None:
            reference = part.yield_t_ha
        pd.testing.assert_series_equal(part.yield_t_ha, reference)
        y = part.yield_t_ha.to_numpy(float)
        pred = part.prediction_t_ha.to_numpy(float)
        assert np.isfinite(y).all() and np.isfinite(pred).all()
        assert (pred >= 0).all()
        sse = float(np.square(y - pred).sum())
        sst = float(np.square(y - y.mean()).sum())
        assert sst > 0
        r2 = 1 - sse / sst
        rmse = float(np.sqrt(sse / len(y)))
        np.testing.assert_allclose(r2, r2_score(y, pred), atol=1e-13, rtol=0)
        np.testing.assert_allclose(r2, recorded.loc[name, "r2"], atol=1e-10, rtol=0)
        np.testing.assert_allclose(rmse, recorded.loc[name, "rmse_t_ha"], atol=1e-10, rtol=0)
        fold_r2 = []
        for fold, group in part.groupby("outer_fold"):
            fy, fp = group.yield_t_ha.to_numpy(), group.prediction_t_ha.to_numpy()
            value = float(r2_score(fy, fp))
            fold_r2.append(value)
            fold_rows.append({"method": name, "fold": int(fold), "n": len(group), "r2": value})
        corr2 = float(np.corrcoef(y, pred)[0, 1] ** 2) if np.ptp(pred) > 0 else None
        scores.append({"method": name, "n": len(y), "yield_mean_t_ha": float(y.mean()),
                       "sst": sst, "sse": sse, "pooled_r2": r2, "rmse_t_ha": rmse,
                       "mean_fold_r2_not_reported_metric": float(np.mean(fold_r2)),
                       "pearson_squared_not_reported_metric": corr2})
    table = pd.DataFrame(scores)
    output.mkdir(parents=True, exist_ok=True)
    table.to_csv(output / "r2_audit.csv", index=False, float_format="%.15g")
    pd.DataFrame(fold_rows).to_csv(output / "r2_audit_folds.csv", index=False, float_format="%.15g")
    receipt = {"all_checks_passed": True, "method_count": len(table), "evaluation_fields": len(reference),
               "metric": "1 - pooled SSE / pooled SST; unweighted, original yield scale",
               "yield_mean_t_ha": float(reference.mean()),
               "yield_population_variance": float(reference.to_numpy().var(ddof=0)),
               "inputs": {name: digest(release / name) for name in
                          ["predictions.csv", "metrics.csv", "target_memberships.csv", "manifest.json"]},
               "audit_script_sha256": digest(Path(__file__)),
               "outputs": {name: digest(output / name) for name in ["r2_audit.csv", "r2_audit_folds.csv"]}}
    (output / "r2_audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(table[["method", "pooled_r2", "rmse_t_ha", "mean_fold_r2_not_reported_metric"]].to_string(index=False))
    print(f"PASS: {len(table)} methods; identical {len(reference)} evaluation IDs and labels; saved metrics reproduced.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=ROOT / "data/runs/zimbabwe_aggregation_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "results/aggregation")
    args = parser.parse_args()
    audit(args.release.resolve(), args.output.resolve())
