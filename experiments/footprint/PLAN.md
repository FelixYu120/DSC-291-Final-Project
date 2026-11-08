# Field footprint: plan and win rule

Written on 8 Nov 2026, before any footprint score was computed. The rules below do not change after the first score.
If a rule must change, the change gets a dated line at the end of this file, and the README says so.
`footprint.py` writes the SHA-256 of this file into `run.json` when it scores.

## Question

Point fields use 1 Sentinel-2 pixel (10 m). Does a bigger footprint around the point add signal? We test the median of
the clear pixels in a 3 x 3, 5 x 5 and 7 x 7 window (30, 50 and 70 m), and the spread (standard deviation) of the
pixels inside the window as extra features.

Expectation: a small gain at best. Lacuna points are GPS fixes of unknown accuracy (Q-03), and about a third of the
Lacuna scenes are resampled from the next UTM zone (Q-16), so a small window may cut noise. A big window also takes in
other fields, paths and houses, which adds noise.

## Data

- Cohorts: `zimbabwe_lacuna_2022_2023` first (main). Then `zimbabwe_2024` (robustness: parked cohort, positive rows
  only). Both are point cohorts. Each cohort has its own model. No pooling, no t/ha comparison across cohorts.
- Rows: the rows of `load_xy(cohort, data/v2)` (`include_primary`, at least 4 clear months): Lacuna 1,880,
  Zimbabwe 2024 2,458. No row is dropped. Never-green fields stay in (in Lacuna they are real poor fields).
- Checks before any model: the v2 database matches `configs/team_database_v2.json`; the labels and the split files
  match `data/v2/splits/manifest.json` (the functions of `scripts/step8_run_baseline.py`).
- Folds: `data/v2/splits/<cohort>__s1_cc2km.csv`, joined on `obs_id` only, read as text. Folds 1-4 are scored. Fold 0
  is kept back: its fields train, and no fold-0 field is ever scored.
- Every DuckDB file opens with `read_only=True`. No v1 or v2 data, database or split file changes. All new files go
  under `experiments/footprint/`. Nothing is committed.

## Inputs (label-free)

- The chips of data v2 that the database names in `downloads.record_dir` (under `data/imagery/sentinel2_v2/`). No new
  download.
- Same monthly photo: for each month with `coverage.state = 'clear'`, the scene in `coverage.item_id`. No other scene
  and no other month is used. A month that is cloudy at the point stays out, even if its neighbours are clear.
- Same clear-pixel rule: a pixel counts when `valid_mask.tif` is 1, which is SCL 4, 5 or 6 and all 10 bands finite.
  The code checks this against `scl.tif` and stops on a difference.
- Window: w x w pixels (w = 1, 3, 5, 7), centred on the point pixel of `aoi_mask.tif`, on the chip grid.
- Per month and window: the median of each band over the clear pixels (as `monthly_series` does today), the five
  Lobell indices from those medians (as `vegetation_indices` does today), the standard deviation (ddof 0) of each band
  over the clear pixels, and the standard deviation of each index computed pixel by pixel.
- The point pixel is clear in every clear month (the downloader needs it), so each window has at least one pixel.

## Arms

| Arm | Features |
|---|---|
| R1 | Coordinates only, 10 nearest neighbours (step 8). |
| A1-w | Season max and season mean of the 5 indices (10), from the window medians. A1-1 is today's A1. |
| A1-w+sd | A1-w plus season max and season mean of the 5 within-window index std (20). w = 3, 5, 7. |
| X1-w | The 10 bands per month of the season, from the window medians. Gaps between clear months are filled linearly, edges with the nearest clear month (the M2 curve of `experiments/time_features`, which the step-up ladder calls S7). X1-1 is today's M2. |
| X1-w+sd | X1-w plus the 10 band std per month, gap-filled the same way. w = 3, 5, 7. |

Model: the step 8 Ridge (`ridge_cv`: winsorize at the training 1st and 99th percentile, scale, 17 alphas 1e-3 to 1e5,
inner `GroupKFold` on `group_id` inside the training folds). No other head and no other tuning.

## Scores

- On the pooled out-of-fold predictions of folds 1-4: RMSE (t/ha), R2 inside the cohort, and rank inside clusters
  (Spearman after the cluster-year mean is taken out, clusters of at least 3 fields), as in step 8.
- Paired cluster bootstrap over `group_id`, 2,000 draws, seed 20261029, 95 % interval (2.5 and 97.5 percentiles).
- Pairs: each window arm minus its 1-pixel arm (RMSE, R2, rank); each `+sd` arm minus the same window without sd
  (RMSE, R2, rank); each A1 and X1 arm minus R1 (RMSE, rank).
- Several pairs share the folds. So for the 12 "window minus 1 pixel" pairs of each cohort, a two-sided bootstrap p
  value is Holm-corrected, per metric.

## Win rule

- **Primary test (one):** Lacuna, A1-3 minus A1-1 on RMSE. A win needs a 95 % interval below 0.
- A window "adds signal" when its RMSE difference against the 1-pixel arm has a 95 % interval below 0 and its rank
  difference does not have an interval below 0. A clear win in the secondary pairs also needs a Holm p below 0.05.
- The std "adds signal" when `+sd` minus the same window without sd on RMSE has a 95 % interval below 0.
- Zimbabwe 2024 is a robustness check. It cannot make a win on its own.

## Stop rules

- Before any window score, the 1-pixel arms must give back today's numbers: the 1-pixel bands equal the database
  `monthly_bands` (largest absolute difference below 1e-6), A1-1 features equal `load_xy` (below 1e-9), Lacuna A1-1
  scores equal `results/v2/baseline_scores.csv` (RMSE 1.785, R2 0.191, rank 0.299, to 1e-6), Lacuna X1-1 equals the
  time-features M2 row (RMSE 1.634, R2 0.322, rank 0.342), and R1 equals step 8. If not, stop and find out why.
- A test (`test_footprint.py`) checks this.

## Not in this plan

- No polygon cohort (Malawi), no Kenya, no fold 0, no other split family, no new photo, no other month.
- No buffer that follows the field shape, and no weighting of the centre pixel.
