# Spatial baseline results — 3 November 2026

Run: [`spatial_baselines_v1-20261103T225758673365Z`](spatial_baselines_v1-20261103T225758673365Z).
Implementation commit: `d4b99d6`. The shared database, labels and existing `s1_cc2km` splits were verified
before and after fitting. Each dataset has its own models and pooled held-out predictions.

R0 predicts the training mean; R1 averages the 10 nearest training locations; A1 fits Ridge regression
on ten seasonal vegetation-index features. A1 clips and scales inside nested grouped validation.

| Dataset | Fields | R0 RMSE | R1 RMSE | A1 RMSE | A1 R² |
|---|---:|---:|---:|---:|---:|
| Kenya | 3,977 | 1.746 | **1.536** | 1.696 | 0.054 |
| Malawi | 251 | 1.544 | 1.625 | **1.400** | 0.172 |
| Lacuna | 1,880 | 2.006 | 1.861 | **1.786** | 0.200 |

RMSE is in tonnes per hectare; lower is better. Bold identifies the lowest point estimate, not a
claim that every difference is established. Paired 95% cluster-bootstrap intervals for **A1 RMSE − R1 RMSE**:

| Dataset | Difference (t/ha) | 95% interval | Interpretation |
|---|---:|---|---|
| Kenya | +0.159 | [+0.077, +0.255] | Coordinates perform better than these satellite-index summaries |
| Malawi | −0.225 | [−0.386, −0.072] | Satellite-index summaries improve on coordinates |
| Lacuna | −0.075 | [−0.205, +0.050] | Lower A1 point estimate, but the difference from coordinates is inconclusive |

These results evaluate the previously inspected research folds, not an untouched final test. They do
not establish future-season, new-country or broad regional performance. The frozen split's minimum
2 km test–training separation was checked; geographic dependence can extend farther than 2 km.

## Files and reproduction

- [`summary.csv`](spatial_baselines_v1-20261103T225758673365Z/summary.csv): all nine model/dataset rows.
- [`metrics.csv`](spatial_baselines_v1-20261103T225758673365Z/metrics.csv): pooled metrics, confidence intervals,
  and per-fold metrics where the minimum-size reporting rule permits them.
- [`fold_fits.csv`](spatial_baselines_v1-20261103T225758673365Z/fold_fits.csv): 45 fitted model/fold combinations
  and each A1 fold's selected alpha. Malawi and Lacuna selected 31.6228 in all folds; Kenya selected
  0.3162, 1, 3.1623, 3.1623 and 3.1623.
- [`run.json`](spatial_baselines_v1-20261103T225758673365Z/run.json): input/source hashes, Git state and versions.
  It points to 18,324 per-field predictions stored locally under ignored `data/runs/`.
- [`verification.json`](spatial_baselines_v1-20261103T225758673365Z/verification.json): tests, exact repeat check
  and comparison with the archived results.
- [`historical_comparison.csv`](spatial_baselines_v1-20261103T225758673365Z/historical_comparison.csv): current
  and archived pooled metrics side by side.

From the repository root:

```bash
python scripts/run_baselines.py
```

A second full run produced **exactly identical predictions, scores, confidence intervals and selected
alphas**. The project suite passed 157 tests, with two Windows-only tests skipped on macOS. The baseline
code and new tests passed Ruff. See [`docs/quality/BASELINES.md`](../../docs/quality/BASELINES.md) for the code walkthrough.

## Comparison with the archive

R0 and A1 reproduce archived scores to floating-point precision. R1's RMSE differs by +0.0000331 t/ha
in Kenya and −0.0000052 t/ha in Lacuna; Malawi matches. These differences do not change the conclusions.

We verified identical observation ordering and coordinates between the archived loader and the current
loader. Exact ties at the 10th/11th-neighbor boundary, with unequal yields, occur for 82 Kenya and 8 Lacuna
test observations (none in Malawi). Reversing training order as a diagnostic changes 48 Kenya and 4 Lacuna
predictions, all at tied boundaries. This supports tie sensitivity as a possible explanation. The exact
historical cause cannot be established without the original per-field predictions and runtime; no data,
model settings or splits were changed to force agreement.
