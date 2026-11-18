# How the V0–V3 R² values were calculated

## v2 status (8 November): which numbers below broke a team rule

This packet audits the **v1** release. Two team rules supersede part of it:

1. **Label-free windows.** Every "V1 preharvest mean" score below (0.221860, 0.221149, 0.169061, 0.170550) uses each
   field's survey planting and harvest dates as the window anchor. These models are no longer candidates.
2. **Training rows follow `labels_v1.include_primary`.** Every `merged` score below trained on all 4,330
   feature-eligible 2024 rows, including 1,874 recorded zeros that the team excludes. The v1 step 15 index-maximum
   scores 0.180359 / 0.180568 also used 217 non-primary Lacuna rows.

Lacuna-only (`target`) scores of the label-free variants are unchanged in v2. The R² definition, the 1,504 fields and
SST = 5,921.399689832447 are unchanged. v2 pooled out-of-fold R² ([audit](../../results/aggregation_v2/r2_audit.csv),
[receipt](../../results/aggregation_v2/r2_audit.json)):

| Aggregation (v2) | 10 bands: target | 10 bands: merged | 5 indices: target | 5 indices: merged |
|---|---:|---:|---:|---:|
| V0 / V3 mean | 0.178491 | 0.178462 | 0.114127 | 0.114530 |
| V1 calendar mean (Dec–Mar) | **0.218605** | **0.219324** | 0.173661 | 0.168952 |
| V2 maximum | 0.088394 | 0.090896 | **0.178344** | **0.179048** |
| V3 median | 0.043398 | 0.043766 | 0.050714 | 0.050829 |
| V3 modal estimate | −0.030546 | −0.032472 | 0.014483 | 0.015076 |
| Index mean + max control (10 features) | — | — | 0.180013 | 0.183268 |

v2 merged arms use only the 2,456 include_primary 2024 rows; outer-fold allowed counts after the 2 km buffer are
2,367 / 2,335 / 2,354 / 2,357. In step 15 v2 all 22 broader-pool arms are identical to these step 14 v2 arms, so the
v2 index-maximum scores are 0.178344 (Lacuna) and 0.179048 (+ 2024). None of the v2 scores reproduces 0.21 either.
The label-free counterpart of the disputed 0.17 index "preharvest" score is the index calendar mean, 0.173661.

```bash
python scripts/verification/audit_zimbabwe_r2.py --release data/runs/zimbabwe_aggregation_v2 --output results/aggregation_v2
python scripts/verification/audit_zimbabwe_r2.py --release data/runs/zimbabwe_multiyear_v2 --output results/multiyear_v2
```

The rest of this packet is the original v1 audit, kept unchanged for the record.

This is a review packet for the original **step-14 aggregation experiment**,
`data/runs/zimbabwe_aggregation_v1/`. It explains the saved results before the
expanded training-pool experiment. The R² definition stays the same in step 15,
but its additional training fields can change predictions and scores.

The [step-15 expanded-training report](MULTIYEAR_RESULTS.md) is separate: its
index maximum scores are 0.180359 without 2024 and 0.180568 with 2024. Neither
reproduces 0.21. Use the experiment directory and full method name when comparing
numbers, so original and expanded training populations are not mixed.

**The reported 0.17 preharvest score is consistent with our vegetation-index
model (0.169061). Our reflectance-band preharvest model scored 0.221860. These
are different input variables.** A maximum score of 0.21 does not match either
saved maximum model. Without the other run's predictions, inputs and split IDs,
we cannot identify the remaining difference or say which implementation caused it.

An independent calculation using NumPy and `sklearn.metrics.r2_score`, with no
imports from the experiment's scoring code, reproduced all 26 saved scores to
within 1e-10. It also checked that every model uses identical evaluation IDs,
folds and target values. See [audit script](../../scripts/verification/audit_zimbabwe_r2.py),
[numeric audit](../../results/aggregation/r2_audit.csv) and
[verification receipt](../../results/aggregation/r2_audit.json).

## 1. Exact definition and a worked example

For each model, concatenate its **out-of-fold predictions for all 1,504
evaluation fields**. Each field contributes exactly once. Let `y_i` be observed
yield, `p_i` be its held-out prediction, and `mean_y` be the mean of these same
1,504 observed yields:

```text
SSE  = sum((y_i - p_i)^2)
SST  = sum((y_i - mean_y)^2)
R²   = 1 - SSE / SST
RMSE = sqrt(SSE / 1504)
```

This is unweighted, ordinary predictive R² on the original **t/ha** scale.
It is not adjusted R², squared Pearson correlation, training R², or a score on
log-transformed yields. No source weights are used when scoring. All models
have the same denominator because their evaluation fields and yields match.

For the saved prediction CSV:

| Quantity | Value |
|---|---:|
| Evaluation fields | 1,504 |
| Mean observed yield, t/ha | 3.233588430851064 |
| SST | 5,921.399689832447 |
| Population variance, SST / n | 3.937100857601361 |
| Bands V1 preharvest SSE | 4,607.678093536997 |
| Bands V1 preharvest R² | 1 − 4,607.678093536997 / 5,921.399689832447 = **0.221859976544** |
| Bands V1 preharvest RMSE, t/ha | **1.750318757736** |
| Indices V1 preharvest SSE | 4,920.323290393526 |
| Indices V1 preharvest R² | **0.169060771418** |
| Indices V2 maximum SSE | 4,865.354176213608 |
| Indices V2 maximum R² | **0.178343899911** |

The held-out mean is used only to define SST; it is not provided to the fitted
model. R² = 0 means matching the squared error of the evaluation-mean constant;
negative R² is possible and is retained. The band modal-estimate model has
negative R² because its SSE exceeds SST.

On these exact fields, `R² = 1 - RMSE² / 3.937100857601361`. Thus R² = 0.21
would imply RMSE approximately **1.763607 t/ha**. If another run reports 0.21
and a different corresponding RMSE, first compare its evaluation population
and metric aggregation. Converting both observed and predicted yields from
t/ha to kg/ha changes RMSE by 1,000 but leaves R² unchanged.

## 2. All original R² results

`target` means the original primary Lacuna 2023 training population.
`merged` means that population plus spatially permitted 2024 rows, using
adaptive Ridge and a source weight selected on inner validation folds.
**Both are evaluated only on the same 2023 fields.** The merged column is
not a score computed across both 2023 and 2024 outcomes.

| Aggregation | 10 bands: target | 10 bands: merged | 5 indices: target | 5 indices: merged |
|---|---:|---:|---:|---:|
| V0 / V3 mean | 0.178491 | 0.178386 | 0.114127 | 0.114822 |
| V1 preharvest mean | **0.221860** | **0.221149** | 0.169061 | 0.170550 |
| V1 common-calendar mean | 0.218605 | 0.219435 | 0.173661 | 0.169208 |
| V2 maximum | 0.088394 | 0.091166 | **0.178344** | **0.178803** |
| V3 median | 0.043398 | 0.043802 | 0.050714 | 0.051098 |
| V3 modal estimate | −0.030546 | −0.032401 | 0.014483 | 0.015101 |

The older **ten-feature index mean + maximum** control scored 0.180013
(target) and 0.182704 (merged). It is neither a five-feature maximum-only model
nor the ten-reflectance-band model. V3 mean is identical to V0, so it is fitted
once, rather than creating a duplicate result.

## 3. What went into each V0–V3 model

Monthly measurements are spatial **medians of clear field pixels from one
selected Sentinel-2 scene per month**. These experiments aggregate those
monthly values over time; they do not average every daily scene.

For the Zimbabwe point geometries specifically, every accepted observation has
one valid sampled grid cell, so this spatial median reduces to one value rather
than a whole-field statistic. The archived `mtci` predictor uses
`(B08 - B05) / (B05 - B04)`; substituting the Sentinel-2 MTCI definition with B06
would change the predictors. The [supplementary methods](../paper/SUPPLEMENTARY_METHODS.md)
document the exact formulas and sampling support. Whether this accounts for
another implementation's scores cannot be established without its feature code.

Two feature families are fitted separately:

- Ten reflectance bands: B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12.
- Five vegetation indices: NDVI, GCVI, MTCI, NDVI705, NDVI740, derived from
  each month's band measurements before temporal aggregation.

For harvest year 2023, the full-season window is **December 1, 2022 through
June 30, 2023**. The same relative months are used for 2024. Missing observations
are skipped, not replaced by zero, and no unavailable imagery is fabricated.
Every eligible field has at least four observed months in that full window.

| Version | Exact operation, separately for each variable |
|---|---|
| V0 / V3 mean | Arithmetic mean of finite observed values in December–June |
| V1 preharvest mean | Mean where `max(December 1, planting date) <= actual acquisition date < harvest date`, within December–June |
| V1 calendar control | Mean where `December 1 <= actual acquisition date < April 1` |
| V2 maximum | Maximum of that variable over the observed December–June months |
| V3 median | Median over the same observed December–June months |
| V3 modal estimate | Half-sample continuous-mode estimator over those months, averaging tied interval estimates |

For V1, 2024 lacks field-level planting/harvest dates, so its December–March
window is explicitly a **calendar proxy**. The common-calendar arm also applies
that window to Lacuna. Actual acquisition dates, not just month labels, determine
inclusion. We do not require four observations within the shorter V1 window:
421 evaluation fields have fewer than four, but none has zero.

V2 is a componentwise maximum: different variables may reach their maxima in
different months. It is not “select the month of peak NDVI and take all bands
from that month.” Likewise, mean NDVI is not NDVI calculated from seasonal
mean red/NIR bands; the nonlinear operations differ.

The modal estimate sorts values, repeatedly retains shortest intervals
containing `ceil(n/2)` observations, and averages for one/two observations at
the recursion base. Tied shortest intervals contribute equally. It is not
`scipy.stats.mode` on nearly unique continuous values. Mean, median and mode
are separate models; they are not concatenated.

Exact feature names and values are in
[feature_dictionary.json](../../data/runs/zimbabwe_aggregation_v1/feature_dictionary.json)
and [features.parquet](../../data/runs/zimbabwe_aggregation_v1/features.parquet).
[Monthly observations](../../data/runs/zimbabwe_aggregation_v1/monthly_observations.parquet)
and [window audit](../../data/runs/zimbabwe_aggregation_v1/window_audit.csv) allow
the aggregation to be reconstructed. These models use neither MOSAIKS nor weather.

## 4. How predictions were obtained

The original modeling population is 1,880 primary Lacuna 2023 fields.
The 376 fields assigned to historical fold 0 are excluded from fitting and
scoring in this experiment. The remaining **1,504** are in four frozen spatial
outer folds, each containing **376** fields.

For each outer fold and each model:

1. Hold out its 376 evaluation fields. The other 1,128 fields form the primary
   training pool. No random split is regenerated.
2. Use the three saved inner spatial folds to choose Ridge alpha from
   `[0.01, 0.1, 1, 10, 100, 1000]`. Choose the lowest pooled inner-validation
   mean squared error. The outer evaluation outcomes do not select alpha.
3. Within each fit, learn preprocessing from target-training rows only:
   1st/99th percentile clipping, then mean centering and population-standard-
   deviation scaling. Training-median imputation is implemented in the shared
   transformer, but **no aggregation inputs are missing in the eligible fitted
   and evaluated population**, so it does not fill any imagery in this run.
4. Fit `sklearn.linear_model.Ridge(alpha=selected_alpha)` with its intercept
   for target-only models. These are regularized linear regressions, not
   unregularized ordinary least squares. A single fixed alpha will not exactly
   reproduce the saved run.
5. Refit on the full outer training pool using its selected alpha; predict
   the 376 held-out fields. Clamp negative predicted yields to zero before
   saving and scoring. Yields are not log-transformed.
6. Repeat across the four outer folds, then concatenate the four prediction
   sets and compute the single pooled R² above.

The saved target-only alphas for the disputed models are:

| Feature/model | Fold 1 | Fold 2 | Fold 3 | Fold 4 |
|---|---:|---:|---:|---:|
| Bands V1 preharvest | 10 | 10 | 1 | 1 |
| Bands V2 maximum | 10 | 100 | 10 | 10 |
| Indices V1 preharvest | 100 | 10 | 1 | 100 |
| Indices V2 maximum | 0.1 | 10 | 10 | 0.01 |

For merged models, 4,330 eligible 2024 rows are candidates, with a 2 km buffer
against reserved/evaluation/inner-validation target fields. Outer-fold allowed
counts are 4,226 / 4,191 / 4,194 / 4,213. Source ratios `[0, 0.1, 0.3, 1]` are
tuned jointly with alpha; zero permits omitting 2024. The model uses training-only
separate source/target centering and outcome scales, shared plus provider-specific
coefficients, and source-weight normalization. It predicts on the target yield
scale. This is adaptive Ridge, not simply concatenating two tables and fitting
ordinary Ridge. See `predict_model` in
[zimbabwe_merge.py](../../src/cropyield/experiments/zimbabwe_merge.py).

Exact split IDs, selected parameters and predictions are saved in
[target_memberships.csv](../../data/runs/zimbabwe_aggregation_v1/target_memberships.csv),
[selected_parameters.csv](../../data/runs/zimbabwe_aggregation_v1/selected_parameters.csv),
and [predictions.csv](../../data/runs/zimbabwe_aggregation_v1/predictions.csv).
The [manifest](../../data/runs/zimbabwe_aggregation_v1/manifest.json) records
source/config/data hashes and package versions. Full fitting is implemented in
[zimbabwe_aggregation.py](../../src/cropyield/experiments/zimbabwe_aggregation.py).

## 5. Pooled R² is not mean fold R²

Each fold has its own yield mean and variance. Computing four R² values and
averaging them gives a different statistic, even though the four folds have
equal size. Both can be reported if clearly labeled; our headline is pooled R².
An average of `cross_val_score(..., scoring="r2")` would usually be a fold mean.

| Lacuna-only model | Pooled R², reported | Mean fold R² | Squared Pearson correlation |
|---|---:|---:|---:|
| Bands preharvest | 0.221860 | 0.220224 | 0.223358 |
| Indices preharvest | 0.169061 | 0.159791 | 0.169244 |
| Bands maximum | 0.088394 | 0.079763 | 0.091937 |
| Indices maximum | 0.178344 | 0.166745 | 0.178593 |

On our saved maximum predictions, **none of these alternatives yields 0.21**.
Squared correlation is not generally predictive R²: it can remain high despite
biased or incorrectly scaled predictions. The usual equality for some in-sample
OLS fits does not justify substituting it for held-out Ridge R².

## 6. Minimal independent recalculation

From the repository root, with the project dependencies installed:

```bash
python scripts/verification/audit_zimbabwe_r2.py
```

This reads committed CSVs; it needs no database, downloads, retraining or API
access. A minimal check for the disputed index models is:

```python
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

p = pd.read_csv("data/runs/zimbabwe_aggregation_v1/predictions.csv")
for name in ["indices_v1_preharvest_mean_target", "indices_v2_max_target"]:
    g = p.loc[p.method.eq(name)].sort_values("obs_id")
    assert len(g) == 1504 and g.obs_id.is_unique
    assert set(g.outer_fold) == {1, 2, 3, 4}
    y = g.yield_t_ha.to_numpy()
    pred = g.prediction_t_ha.to_numpy()
    sse = np.sum((y - pred) ** 2)
    sst = np.sum((y - y.mean()) ** 2)
    print(name, "R2:", 1 - sse / sst,
          "sklearn:", r2_score(y, pred),
          "RMSE:", np.sqrt(sse / len(y)))
```

Expected R² values: **0.169060771418** and **0.178343899911**.
CSV serialization can change the last few digits, not 0.178 into 0.21.

## 7. Suggested request to Claude

> Please audit `data/runs/zimbabwe_aggregation_v1/`, not a later training-pool
> expansion. First recompute R² from its committed predictions without fitting
> a new model. Match the method names `indices_v1_preharvest_mean_target` and
> `indices_v2_max_target`. Each must have the same 1,504 unique Lacuna 2023 IDs,
> the same true yields, and SST = 5921.399689832447. Expected pooled R² values
> are 0.169060771418 and 0.178343899911. Explain whether your 0.21 maximum score
> is pooled predictive R², mean fold R², or another metric. If you retrained,
> compare exact feature names, month windows/acquisition dates, evaluation IDs,
> inner folds, clipping/scaling, selected alphas and nonnegative predictions.
> Export your `obs_id`, `outer_fold`, `yield_t_ha`, `prediction_t_ha`, model name
> and feature list so the two prediction tables can be joined by ID. Do not
> align predictions by row position or compare ten reflectance bands with five
> vegetation indices as if they were the same model.

These are repeated development-fold comparisons, not a new blind test. Matching
the arithmetic verifies how the number was calculated; it does not independently
establish generalization to new years, sites or providers.
