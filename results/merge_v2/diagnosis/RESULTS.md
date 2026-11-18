# Zimbabwe transfer diagnosis: results

Training rows follow `labels_v1.include_primary` (config `training_rows`). Rows, memberships and source permissions
come from `data/runs/zimbabwe_merge_v2`, so the 2024 pool holds no recorded zeros. The source-quality statistics
below still describe all screened 2024 records, zeros included; they are data checks, not training rows.

## Primary nested comparison

Transfer selector minus target-only selector ΔRMSE: **+0.0086 t/ha**;
paired 95% spatial-group interval **[-0.0336, +0.0440]**.
All target scores use the same 1,504 Lacuna 2023 development fields. Each selector chooses its method using only
inner validation within the outer training set. This follow-up is informed by the first experiment; it is exploratory,
not a new blind test. Both target and source historical fold-0 outcomes remain unscored.

## Evidence about the cause

- **99.9% of naive pooling's extra MSE is accounted for by the increase
  in squared bias.** This is the identity MSE = squared mean error + centered error variance, not a proposed correction
  fitted using held-out labels. See `error_decomposition.csv`.
- The source's two-cut correlation is **0.900** across all paired rows and
  **0.868** among positive fields. Both-zero agreement alone is not evidence of reliability.
  **250 / 2416** positive paired records exceed the
  relative-difference threshold of 1. Agreement cannot detect shared recording errors or verify moisture equivalence.
- Source-versus-target classifier AUC (three spatial folds; chance 0.5): **seasonal: 0.787, monthly: 0.995, presto: 1.000, coordinates: 0.697**. Distinguishability measures
  distribution shift, not label quality. The year, sampling frame and provider protocol remain confounded.
- The source learnability diagnostic uses **1944** fields after removing old source fold 0 and
  neighbours, and protecting target fold 0. Its task difficulty/distribution differs from target prediction; compare its
  models with the source training mean rather than directly comparing source and target RMSE.

## All target results (lower RMSE is better)

| Method | RMSE t/ha | MAE t/ha | R² | Matched reference |
|---|---:|---:|---:|---|
| seasonal_target | 1.7968 | 1.4477 | 0.180 | seasonal_target |
| seasonal_adaptive | 1.7932 | 1.4457 | 0.183 | seasonal_target |
| seasonal_quality | 1.7932 | 1.4457 | 0.183 | seasonal_target |
| seasonal_relevance | 1.7889 | 1.4457 | 0.187 | seasonal_target |
| monthly_target | 1.6926 | 1.3223 | 0.272 | monthly_target |
| monthly_adaptive | 1.6869 | 1.3170 | 0.277 | monthly_target |
| monthly_quality | 1.6869 | 1.3168 | 0.277 | monthly_target |
| monthly_relevance | 1.6896 | 1.3202 | 0.275 | monthly_target |
| presto_target | 1.6815 | 1.3151 | 0.282 | presto_target |
| presto_adaptive | 1.6799 | 1.3141 | 0.283 | presto_target |
| presto_quality | 1.6790 | 1.3134 | 0.284 | presto_target |
| presto_relevance | 1.6798 | 1.3141 | 0.283 | presto_target |
| monthly_tree_target | 1.6594 | 1.2897 | 0.301 | monthly_tree_target |
| monthly_tree_transfer | 1.6770 | 1.3038 | 0.286 | monthly_tree_target |
| monthly_source_signal | 1.6939 | 1.3236 | 0.271 | monthly_target |
| coordinates_only | 1.8779 | 1.4513 | 0.104 | seasonal_target |
| seasonal_shuffle_101 | 1.7965 | 1.4476 | 0.180 | seasonal_target |
| seasonal_shuffle_202 | 1.7965 | 1.4478 | 0.180 | seasonal_target |
| seasonal_shuffle_303 | 1.7966 | 1.4481 | 0.180 | seasonal_target |
| seasonal_shuffle_404 | 1.7962 | 1.4476 | 0.181 | seasonal_target |
| seasonal_shuffle_505 | 1.7966 | 1.4478 | 0.180 | seasonal_target |
| seasonal_matched_606 | 1.7931 | 1.4456 | 0.183 | seasonal_target |
| seasonal_matched_707 | 1.7930 | 1.4455 | 0.183 | seasonal_target |
| seasonal_matched_808 | 1.7932 | 1.4456 | 0.183 | seasonal_target |
| seasonal_ridge_fraction_0.25 | 1.8096 | 1.4657 | 0.168 | seasonal_ridge_fraction_0.25 |
| seasonal_adaptive_fraction_0.25 | 1.8058 | 1.4620 | 0.172 | seasonal_ridge_fraction_0.25 |
| seasonal_ridge_fraction_0.5 | 1.8019 | 1.4559 | 0.175 | seasonal_ridge_fraction_0.5 |
| seasonal_adaptive_fraction_0.5 | 1.7997 | 1.4536 | 0.177 | seasonal_ridge_fraction_0.5 |
| target_selector | 1.6923 | 1.3213 | 0.273 | seasonal_target |
| transfer_selector | 1.7009 | 1.3274 | 0.265 | target_selector |

Every paired interval is in `paired_differences.csv`; within-fold metrics are in `fold_metrics.csv`.
The five shuffle seeds and three random matched subsets are all reported; none is chosen as the best control.
Shuffles destroy source feature-label pairing while retaining marginal outcomes. A transfer gain similar to shuffled
controls can arise from regularization rather than useful source relationships. Five shuffles are not a formal test.
Quality subsets may alter the population; matched controls preserve their size and zero/positive composition.

## What each selector actually used

| Outer fold | Selector | Inner-selected model | Source training rows used |
|---:|---|---|---:|
| 1 | target_selector | monthly_target | 0 |
| 1 | transfer_selector | monthly_tree_transfer | 2367 |
| 2 | target_selector | presto_target | 0 |
| 2 | transfer_selector | monthly_adaptive | 2335 |
| 3 | target_selector | presto_target | 0 |
| 3 | transfer_selector | presto_quality | 2063 |
| 4 | target_selector | presto_target | 0 |
| 4 | transfer_selector | presto_quality | 2062 |

A zero source count means that fold selected target-only fitting. Do not attribute a better representation's benefit
to adding source data. Compare each feature family's adaptation with its own target-only baseline.

## Learnability within 2024

| Source diagnostic model | RMSE t/ha | R² | Spearman | Nonzero-ranking AUC |
|---|---:|---:|---:|---:|
| coordinates | 0.9038 | 0.194 | 0.527 | nan |
| monthly_ridge | 0.9038 | 0.194 | 0.473 | nan |
| monthly_tree | 0.9006 | 0.200 | 0.491 | nan |
| presto_ridge | 0.8951 | 0.210 | 0.457 | nan |
| seasonal_ridge | 0.8979 | 0.205 | 0.464 | nan |
| training_mean | 1.0077 | -0.002 | -0.026 | nan |

Models use grouped outer validation with inner tuning. Positive/zero ranking uses predicted yield as the ranking
score; it is not a calibrated probability. Original source fold-0 IDs and any points within 2 km are excluded from
this diagnostic. Its new folds do not restore blindness to historically explored source observations.

## Scope and reproducibility

The complete design and interpretation limits are in `PROTOCOL.md`. Only training observations determine imputation,
clipping, scaling, outcome calibration, density weights, source teacher models and hyperparameters. Source permissions
and target membership are inherited from the hash-verified first release. The full catalog and source observations
are preserved; quality masks are experimental training policies, not permanent deletion decisions.

Common-window monthly features contain 122 predictors (10 seasonal statistics, 105 month/band/index values and seven
missing-scene masks). Presto uses 128 existing frozen whole-window embeddings; it has different window/mask conventions
and is not an otherwise identical monthly representation. No new imagery was downloaded and the database was read-only.

Run `python scripts/step10_diagnose_zimbabwe_transfer.py --config configs/zimbabwe_transfer_diagnosis_v2.json` from the repository root. Input/code/config/output hashes
and library versions are in `manifest.json`. Use a new `--output` directory for intentional changes.

Files include: `quality_summary.json`, `cohort_summary.csv`, `feature_correlations.csv`, `domain_separability.csv`,
`row_quality.csv`, `error_decomposition.csv`, `source_predictions.csv`, `source_metrics.csv`, `source_splits.csv`,
`source_selected_parameters.csv`, `target_memberships.csv`, `source_spatial_permissions.csv`, `fit_accounting.csv`,
`predictions.csv`, `metrics.csv`, `fold_metrics.csv`, `paired_differences.csv`, `tuning.csv`, `selected_parameters.csv`,
`features_monthly.parquet`, `features_presto.parquet` and `feature_dictionary.json`.

![Diagnosis](diagnosis.png)
