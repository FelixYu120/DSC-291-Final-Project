# Broader Zimbabwe training (zimbabwe_multiyear_v2): results

All scores use the same 1,504 original Lacuna 2023 development fields and unchanged nested spatial folds. RMSE is in t/ha (lower is better); R² is pooled out-of-fold (higher is better). Fold 0 remains reserved.

## Team-rule changes from v1

- **Label-free windows.** The crop-date window is gone; survey dates no longer affect any feature, the eligibility rule or the prespecified comparison, which now uses the December–March calendar mean.
- **Training rows follow `labels_v1.include_primary`.** Imagery-eligible rows that leave the pools: 1,874 `zimbabwe_2024_zero_likely_not_measured`, 212 `lacuna_intercropped`, 5 `lacuna_irrigated`. All 169 Lacuna 2022 rows were already imagery-ineligible. Extra Lacuna rows left: **0**.

**Result of the rule fix: 22 of 22 new arms are identical to a step 14 v2 control.** All-Lacuna now trains on exactly the primary Lacuna fit rows (= step 14 `_target`); full-Zimbabwe trains on those plus the include_primary 2024 rows (= step 14 `_merged`). Under the team rules there is no broader training pool to test. `arm_identity.csv` gives the largest prediction difference per arm.

Prespecified ten-band calendar comparison, full-Zimbabwe minus all-Lacuna: RMSE difference **-0.0008** (95% spatial-group interval **[-0.0028, +0.0013]**); R² difference **+0.0007** (interval [-0.0012, +0.0025]).

| Predictors | Aggregation | All-Lacuna RMSE | R² | Full-Zimbabwe RMSE | R² | Identical to |
|---|---|---:|---:|---:|---:|---|
| 10 bands | V0 / V3 mean | 1.7984 | 0.1785 | 1.7985 | 0.1785 | bands_v0_mean_target / bands_v0_mean_merged |
| 10 bands | V1 calendar mean (Dec–Mar) | 1.7540 | 0.2186 | 1.7532 | 0.2193 | bands_v1_calendar_mean_target / bands_v1_calendar_mean_merged |
| 10 bands | V2 maximum | 1.8945 | 0.0884 | 1.8919 | 0.0909 | bands_v2_max_target / bands_v2_max_merged |
| 10 bands | V3 median | 1.9407 | 0.0434 | 1.9403 | 0.0438 | bands_v3_median_target / bands_v3_median_merged |
| 10 bands | V3 modal estimate | 2.0143 | -0.0305 | 2.0162 | -0.0325 | bands_v3_mode_target / bands_v3_mode_merged |
| 5 indices | V0 / V3 mean | 1.8676 | 0.1141 | 1.8671 | 0.1145 | indices_v0_mean_target / indices_v0_mean_merged |
| 5 indices | V1 calendar mean (Dec–Mar) | 1.8037 | 0.1737 | 1.8088 | 0.1690 | indices_v1_calendar_mean_target / indices_v1_calendar_mean_merged |
| 5 indices | V2 maximum | 1.7986 | 0.1783 | 1.7978 | 0.1790 | indices_v2_max_target / indices_v2_max_merged |
| 5 indices | V3 median | 1.9332 | 0.0507 | 1.9331 | 0.0508 | indices_v3_median_target / indices_v3_median_merged |
| 5 indices | V3 modal estimate | 1.9698 | 0.0145 | 1.9692 | 0.0151 | indices_v3_mode_target / indices_v3_mode_merged |
| 10 index features | Legacy mean + maximum | 1.7968 | 0.1800 | 1.7932 | 0.1833 | legacy_indices_mean_max_target / legacy_indices_mean_max_merged |

Ten-band calendar mean minus V0 mean, all-Lacuna: **-0.0445** (interval [-0.0805, -0.0086]).

R² = 1 − SSE/SST over all 1,504 out-of-fold predictions together; `metrics.csv` includes SSE and SST. Intervals resample 232 spatial groups 2,000 times and condition on the saved predictions. Many comparisons were made; the best observed score is not a confirmed winner.

Files: `coverage_summary.csv` (with `training_pool_rows`), `eligibility_audit.csv`, `observations.csv` (with `training_pool`), `fit_memberships.csv`, `extra_lacuna_spatial_permissions.csv` (empty under the rule), `arm_identity.csv`, `method_metadata.csv`, `predictions.csv`, `metrics.csv`, `fold_metrics.csv`, `paired_differences.csv`, `selected_parameters.csv`, `tuning.csv`, `PROTOCOL.md`, `manifest.json`.
