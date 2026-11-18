# Field footprint: does a bigger window around the point add signal?

8 Nov 2026. Data v2, split `s1_cc2km`, folds 1-4 scored. Fold 0 trains and is never scored. Rules: [PLAN.md](PLAN.md),
written before any score (SHA-256 `09dcdbe3…`, recorded in `run.json`). Full tables: [results.md](results.md).

## Answer

**No.** A bigger footprint does not add clear signal in Lacuna or in Zimbabwe 2024. Keep 1 pixel.

- **Primary test** (Lacuna, A1-3 minus A1-1, RMSE): -0.003 t/ha (-0.022 to +0.015). No win.
- **A1 (season indices):** every window is a little better on RMSE, but no interval is below 0. The best is
  A1-5 with the std: RMSE -0.038 (-0.076 to +0.001), rank +0.040 (+0.006 to +0.073), Holm p 0.56 / 0.21. A hint, not a win.
- **X1 (monthly bands):** bigger windows make it worse. X1-7 with the std: RMSE +0.040 (+0.014 to +0.066),
  rank -0.051 (-0.082 to -0.021), Holm p 0.048 / 0.000. X1 on 1 pixel stays the best arm (RMSE 1.634, R2 0.322).
- **The std inside the window:** in A1 at 3 x 3 and 5 x 5 it lifts the rank inside clusters by +0.032 and +0.037
  (intervals above 0), but the RMSE intervals touch 0, so it fails the plan's rule. In X1 it adds nothing.
- **Zimbabwe 2024** (robustness, parked, positive rows only): changes of 0.01 t/ha or less. X1-3 minus X1-1 on RMSE
  is -0.006 (-0.010 to -0.001), but Holm p is 0.11 and the rank does not move. No win.

## Lacuna (`zimbabwe_lacuna_2022_2023`, main)

1,504 scored fields in 232 clusters. All 1,880 model rows train or score; never-green fields stay in.

| Arm | Features | RMSE, t/ha | R2 | Rank inside clusters |
|---|---:|---:|---:|---:|
| R1 (coordinates) | 2 | 1.854 | 0.127 | -0.054 |
| A1-1 (today) | 10 | 1.785 | 0.191 | 0.299 |
| A1-3 | 10 | 1.782 | 0.194 | 0.289 |
| A1-5 | 10 | 1.763 | 0.211 | 0.303 |
| A1-7 | 10 | 1.776 | 0.199 | 0.294 |
| A1-3+sd | 20 | 1.763 | 0.210 | 0.321 |
| A1-5+sd | 20 | 1.747 | 0.224 | 0.339 |
| A1-7+sd | 20 | 1.759 | 0.214 | 0.308 |
| X1-1 (today) | 70 | 1.634 | 0.322 | 0.342 |
| X1-3 | 70 | 1.638 | 0.319 | 0.336 |
| X1-5 | 70 | 1.653 | 0.306 | 0.320 |
| X1-7 | 70 | 1.666 | 0.295 | 0.305 |
| X1-3+sd | 140 | 1.651 | 0.308 | 0.334 |
| X1-5+sd | 140 | 1.667 | 0.294 | 0.311 |
| X1-7+sd | 140 | 1.674 | 0.288 | 0.291 |

Window minus 1 pixel (paired cluster bootstrap, 2,000 draws, seed 20261029; Holm over the 12 pairs, per metric):

| Pair | RMSE | Rank inside clusters | Holm p (RMSE / rank) |
|---|---|---|---|
| A1-3 minus A1-1 (primary) | -0.003 (-0.022 to +0.015) | -0.010 (-0.031 to +0.010) | 1.000 / 1.000 |
| A1-5 minus A1-1 | -0.022 (-0.059 to +0.013) | +0.004 (-0.027 to +0.032) | 1.000 / 1.000 |
| A1-7 minus A1-1 | -0.009 (-0.053 to +0.034) | -0.005 (-0.046 to +0.033) | 1.000 / 1.000 |
| A1-3+sd minus A1-1 | -0.022 (-0.054 to +0.009) | +0.022 (-0.005 to +0.047) | 1.000 / 0.752 |
| A1-5+sd minus A1-1 | -0.038 (-0.076 to +0.001) | +0.040 (+0.006 to +0.073) | 0.558 / 0.209 |
| A1-7+sd minus A1-1 | -0.026 (-0.069 to +0.018) | +0.009 (-0.035 to +0.051) | 1.000 / 1.000 |
| X1-3 minus X1-1 | +0.004 (-0.013 to +0.020) | -0.006 (-0.026 to +0.013) | 1.000 / 1.000 |
| X1-5 minus X1-1 | +0.019 (-0.003 to +0.039) | -0.021 (-0.047 to +0.005) | 0.720 / 0.777 |
| X1-7 minus X1-1 | +0.032 (+0.004 to +0.061) | -0.037 (-0.071 to -0.002) | 0.260 / 0.310 |
| X1-3+sd minus X1-1 | +0.017 (-0.012 to +0.047) | -0.008 (-0.036 to +0.017) | 1.000 / 1.000 |
| X1-5+sd minus X1-1 | +0.034 (+0.007 to +0.061) | -0.031 (-0.063 to -0.000) | 0.132 / 0.450 |
| X1-7+sd minus X1-1 | +0.040 (+0.014 to +0.066) | -0.051 (-0.082 to -0.021) | 0.048 / 0.000 |

Below 0 on RMSE and above 0 on rank means the window is better. R2 and the pairs against R1 are in `results.md`:
every arm keeps the same story against R1 as today (A1 ties R1 on RMSE and wins on rank; X1 wins on both).

## Zimbabwe 2024 (`zimbabwe_2024`, robustness)

1,966 scored fields in 797 clusters. Parked cohort, positive rows only; its t/ha is not comparable with Lacuna.
A1-1 0.895 t/ha, R2 0.206, rank 0.233; X1-1 0.889, 0.217, 0.248 (today's numbers). The best window arms, X1-7 and
X1-7+sd, have RMSE 0.880 and R2 0.233 and 0.234. No window-minus-1-pixel pair has a Holm p below 0.05.

## What the window sees (label-free, `checks.json`)

| | Lacuna 3 x 3 | 5 x 5 | 7 x 7 | Zimbabwe 2024 3 x 3 | 5 x 5 | 7 x 7 |
|---|---:|---:|---:|---:|---:|---:|
| Clear share of the window pixels | 99.7 % | 99.5 % | 99.3 % | 99.8 % | 99.7 % | 99.6 % |
| Median NDVI gap to the point pixel | 0.011 | 0.025 | 0.036 | 0.012 | 0.023 | 0.031 |
| Correlation of season NDVI max with 1 pixel | 0.980 | 0.931 | 0.878 | 0.971 | 0.921 | 0.873 |
| Fields with NDVI max below 0.5 (1 pixel: 174 / 918) | 179 | 183 | 182 | 908 | 883 | 850 |

So the window is almost always clear, and it changes the values only a little. At 7 x 7 (70 m) it mixes in a lot of
the surroundings, and that hurts the monthly-band model.

## Checks

- The 1-pixel arms give back today's numbers (`test_footprint.py`, and again inside `footprint.py` before any window
  score): the 1-pixel bands and indices equal the database `monthly_bands` and `vegetation_indices` (difference 0),
  with the same photo in every month; A1-1 equals `load_xy` (largest gap 6e-14); X1-1 equals the time-features M2
  curve; Lacuna R1, A1-1 and X1-1 equal `results/v2/baseline_scores.csv` and `experiments/time_features/results.csv`
  (gap below 1e-6, the rounding of the csv), and the A1 minus R1 intervals equal step 8.
- Same clear-pixel rule: `valid_mask.tif` equals SCL 4/5/6 with finite bands in every window read (the code stops if not).
- Same months: a window month exists only where the database month is `clear`. The point pixel is clear in each of them.
- The database matched its pin, and the labels and split files matched the v2 manifest. No v1 or v2 file was changed.
- Fold 0: never predicted, never scored (`predictions.csv` holds folds 1-4 only; a test checks it).
- `python -m pytest -q experiments/footprint/test_footprint.py`: 11 passed.

## Limits

- Several pairs on the same folds. The intervals are not corrected; the Holm p is, for the 12 window pairs per metric.
- Point accuracy is unknown, so a window can be "the field" for one point and "the neighbour's field" for another.
  This test cannot tell those apart.
- The std arms add many inputs to X1 (140 and 180). Ridge handles this, but it may need its own tuning to help.
- Scored on 8 Nov from HEAD `af7eac7`. `experiments/footprint/` is not committed, so no commit holds this code yet.
  During the run, another change moved `step8_run_baseline.py` (then in `scripts/`) to `scripts/baselines/baseline_table.py`
  (same code, only paths changed); `footprint.py` now loads the moved file, and the tests pass on it.

## Files and commands

```bash
python experiments/footprint/windows.py      # window stats from the chips, label-free (about 8 min, 12 processes)
python experiments/footprint/footprint.py    # scores (about 20 min)
python -m pytest -q experiments/footprint/test_footprint.py
```

| File | What it holds |
|---|---|
| `PLAN.md` | the rules, written before any score |
| `windows.py` | reads the 7 x 7 window of each clear month; writes `windows.parquet` (no yields) |
| `footprint.py` | builds the arms, checks today's numbers, scores, writes the outputs below |
| `test_footprint.py` | hand-checked window math, and the 1-pixel reproduction tests |
| `windows.parquet` | one row per field, clear month and window size: band medians, indices, std, clear-pixel count |
| `results.csv`, `pairs.csv`, `results.md` | scores per arm, paired differences with intervals and p values, the tables |
| `predictions.csv` | out-of-fold predictions, folds 1-4 (holds y) |
| `checks.json`, `run.json` | label-free data checks and reproduction gaps; hashes, seed, commit, times |
| `windows.log`, `run.log` | console output |
