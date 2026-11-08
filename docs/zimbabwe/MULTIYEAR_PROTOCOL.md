# Broader Zimbabwe training populations: fixed protocol

## v2 amendment: team rules (8 November 2026, before any v2 score)

The v1 release (`configs/zimbabwe_multiyear_v1.json`) broke two team rules. It stays published and unchanged.
`configs/zimbabwe_multiyear_v2.json` fixes both and writes `data/runs/zimbabwe_multiyear_v2/`.

1. **Label-free windows (`window_anchor: calendar`).** v1's prespecified comparison used the crop-date window
   `v1_preharvest_mean`, anchored on each Lacuna field's survey planting and harvest dates. That window also entered the
   shared eligibility rule, so survey dates could remove training rows. In v2 the crop-date variant is not a feature set,
   so dates touch neither predictors nor eligibility. The prespecified comparison becomes ten-band **calendar V1**
   (December 1 <= acquisition < April 1) full-Zimbabwe minus all-Lacuna.
2. **Training rows follow `labels_v1.include_primary` (`training_rows: include_primary`).** v1 all-Lacuna added 217
   non-primary 2023 Lacuna rows (212 intercropped, 5 irrigated); v1 full-Zimbabwe also added all 4,330 imagery-eligible
   2024 rows, including the 1,874 recorded zeros (`zimbabwe_2024_zero_likely_not_measured`). In v2 every pool is
   include_primary rows only: no extra Lacuna rows and 2,456 Zimbabwe 2024 rows. The 169 Lacuna 2022 rows are excluded
   both by imagery and by `dropped_year_2022_imagery_gap`. Every fit asserts that its rows are include_primary.

Consequence, stated before fitting: all-Lacuna now uses exactly the step 14 Lacuna-only rows, and full-Zimbabwe exactly the
step 14 v2 merged rows. The controls come from `data/runs/zimbabwe_aggregation_v2/` (`controls_release`). The 22 new arms
are still fitted, then compared with their step 14 twin; an arm whose predictions differ by at most 1e-9 t/ha is marked
`identical_to` in `arm_identity.csv` and `method_metadata.csv`. It is not presented as new evidence.

Unchanged: the 1,504 evaluation fields, outer folds 1–4 of `s1_cc2km`, fold 0 never fitted or scored, inner folds, the
2 km buffer, the four-month imagery rule, no imputation, grids, seed 20261107 and 2,000 bootstrap draws. Lacuna + 2024
pooling in t/ha remains the recorded team exception (`docs/DECISIONS.md`, 7 November).

The sections below are the original v1 protocol.

This protocol is written before fitting the step 15 models. The question is whether more eligible Lacuna observations, and then Zimbabwe 2024 observations, improve prediction on the same 1,504 primary Lacuna 2023 development fields used in step 14. This is an exploratory comparison on previously used development folds, not a new blind test. Fold 0 (376 fields) remains reserved and contributes neither fitting nor scoring outcomes.

## Requested populations and actual imagery support

Audit every one of the 6,598 screened Zimbabwe labels in the frozen step 9 catalog: 169 Lacuna 2022, 2,097 Lacuna 2023 and 4,332 Zimbabwe 2024. Preserve original labels, management flags, measurement metadata and exclusion flags. The new experiment deliberately broadens the old pure-stand rainfed training population to include screened intercropped and irrigated Lacuna fields. This does not undo the original label-quality screening.

Use only the pinned team DuckDB, with actual satellite acquisition dates. The common season is December of the previous year through June of the harvest year. A row must have at least four observed months in that window and finite aggregate predictors in every model arm. This shared-support rule prevents variant comparisons from changing the training population. Individual missing months remain missing; aggregate available observations only. Do not fill an empty imagery window or any missing model predictor. The context builder asserts that all raw predictor matrices are finite before preprocessing.

The pre-fit coverage audit finds only one or two observed common-window months for every 2022 row, so all 169 are excluded. Two 2024 rows also fail the four-month rule. The available modeling populations are therefore 2,097 Lacuna 2023 and 4,330 Zimbabwe 2024, rather than an actual 2022–2024 imagery comparison. Report this limitation prominently; do not describe absent 2022 imagery as added training information. Outside-window imagery and other archives are not evidence of usable observations in this pinned experiment.

## Features and dates

Reuse the step 14 aggregation implementation without changing windows, feature families or estimators. Evaluate ten reflectance bands and five vegetation indices separately. The six aggregations are V0 full-season mean (also V3 mean), V1 crop-date preharvest mean, V1 common-calendar mean, V2 full-season maximum, V3 median and V3 half-sample modal estimate. Include the historical ten-feature vegetation-index mean-plus-maximum control, giving thirteen feature sets.

Crop-date V1 uses recorded planting <= actual acquisition < recorded harvest, restricted to the common season. Missing planting falls back to December 1; missing harvest falls back to April 1. Zimbabwe 2024 lacks both dates, so its V1 window is December–March. The common-calendar V1 arm uses December–March for both providers. A four-month threshold is applied to full-season support, not to every shorter window; each shorter window must nevertheless supply a finite value for every predictor. Actual crop dates are retrospective information and this design does not establish forecasting skill.

The seasonal-calendar sources are [FEWS NET, February–September 2023, page 4](https://fews.net/sites/default/files/documents/reports/ZW_February_to_September_2023_FSO_Final_jh.pdf) and [Zimbabwe National Adaptation Plan 2024, section 2.1](https://unfccc.int/sites/default/files/resource/NAP-Zimbabwe-2024.pdf). These describe typical calendars, not missing field-specific dates. The continuous mode estimator is the existing half-sample estimator with symmetric averaging of tied shortest-interval branches; see [Bickel and Frühwirth](https://arxiv.org/abs/math/0505419). With few months, it is an unstable modal estimate rather than an exact categorical mode.

## Training arms and protected observations

Keep the original target outer and inner membership CSV byte-for-byte. Each of four outer folds evaluates exactly 376 original primary Lacuna 2023 fields; three fixed inner folds tune each outer fit. Preserve the 26 step 14 control arms and their predictions exactly after verifying their immutable output hashes. They retain their original `_target` and `_merged` method names.

Fit 26 new arms: each feature set with `_all_lacuna` and `_all_zimbabwe`. All-Lacuna fitting starts with the original target fit IDs and adds eligible non-primary Lacuna IDs. In this release those extras are 217 fields from 2023: 212 intercropped rainfed and five irrigated fields. For each outer fit, exclude extras within 2 km of reserved or outer evaluation fields. For each inner fit, additionally exclude extras within 2 km of the inner validation fields. Distances use coordinates only and are recomputed independently of outcomes. Do not use other development evaluation labels as extra training rows.

The full-Zimbabwe arm uses the same expanded Lacuna fit and adds the 2024 observations allowed by the original source spatial permissions. Recompute all source distances and assert equality to the frozen permission decisions and recorded distances. Copy the original source permission CSV byte-for-byte. Export every extra-Lacuna permission decision, distance and final ordered fitting membership. Counts of extras vary by split because of these buffers.

## Models and tuning

Use the same Ridge implementation, nonnegative predictions and training-only preprocessing as step 14. Fit clipping thresholds (1st/99th percentiles) and scaling only on the permitted Lacuna training rows. The reused transform has missing-value support, but no missing value can reach it in this experiment; the finite-input assertion is mandatory.

All-Lacuna uses ordinary Ridge on the expanded Lacuna training rows. Full-Zimbabwe uses the existing separate-provider adaptive Ridge: separate training-provider feature means and yield means/standard deviations, shared and provider-specific coefficients, and predictions restored to the Lacuna training yield scale. Intercropped and irrigated Lacuna rows share the Lacuna calibration distribution; this experiment does not add a distinct management-domain model. Zimbabwe 2024 remains a separate provider. A source ratio of zero is exactly the Lacuna-only model.

Tune alpha over 0.01, 0.1, 1, 10, 100 and 1,000. Tune total 2024 weight relative to Lacuna over 0, 0.1, 0.3 and 1; individual 2024 weights divide this total equally. Select by pooled inner-validation RMSE, retaining the existing deterministic tie order. Do not adjust grids or windows after inspecting outer scores. Export all trials and selected parameters, including permitted and actually used source counts.

## Evaluation and uncertainty

All 52 arms must contain identical, unique evaluation IDs and outcomes; require 1,504 predictions per arm and no fold 0 predictions. Report pooled out-of-fold R², RMSE in t/ha, MAE and bias, plus each outer fold's metrics. A lower RMSE and higher R² rank models identically on this fixed target population. The results answer a training-population question; they do not estimate an all-years national population score.

Pair model comparisons using 2,000 bootstrap resamples of the existing spatial groups with seed 20261107. Reuse the same bootstrap draw across all methods. Export RMSE and R² differences with percentile intervals. These intervals condition on the saved fitted predictions; they do not refit or account for tuning uncertainty. Comparisons include expanded versus historical training pools, with versus without 2024, aggregation versus V0, historical mean-plus-maximum, and crop-date versus common-calendar V1. The fixed primary contrast is ten-band crop-date V1 full-Zimbabwe minus all-Lacuna. Other comparisons are descriptive and unadjusted for multiplicity; selecting the best score does not establish superiority on an independent test set.

## Reproducibility and publication

The runner pins config, this protocol, implementation sources, raw provider metadata, labels, database, split files and all prior release artifacts with SHA-256 hashes before fitting, then verifies them again before publication. It records the current Git commit, actual working-tree source hashes, software versions and output hashes. Export the full catalog, monthly observations, feature dictionary and matrix, long eligibility audit, window and coverage audits, ordered memberships, all 52 predictions, metrics, bootstrap comparisons, and model choices. Frozen controls also retain their original prediction file as a byte-for-byte copy. Publication is immutable: existing different release contents cannot be overwritten.

Independent verification programs are not model-fitting dependencies. Their separate receipts record their own source hashes and the release hashes they checked, allowing stronger verification without changing model inputs or rewriting a published release. Floating-point CSV exports retain twelve significant digits; metric checks account for roundoff, including small Spearman differences when export rounding creates prediction ties.
