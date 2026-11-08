# Seasonal aggregation V0–V3: protocol

Fixed before new model scoring on 7 November 2026, after inspecting coverage/dates but not new model results.
This user-requested experiment compares temporal aggregations of existing satellite data. It reuses the previously
examined development population, so all conclusions remain exploratory. It adds no weather, MOSAIKS or neural model.

## Features and versions

Monthly bands are already spatial **medians of clear field pixels**, not averages of daily images. One selected
scene supplies each month. We change only the temporal summary over those monthly measurements. Compare two
families separately: ten reflectance bands (B02/B03/B04/B05/B06/B07/B08/B8A/B11/B12) and five vegetation indices
(NDVI/GCVI/MTCI/NDVI705/NDVI740). Each single-statistic model therefore has ten or five predictors.

| Version | Definition |
|---|---|
| V0 / V3 mean | Mean of finite observed monthly values in the common December–June season |
| V1 preharvest mean | Mean within December–June and recorded planting <= actual scene acquisition < recorded harvest. Missing crop dates fall back to December 1 / April 1 of that agricultural season. All 2024 crop dates are missing; its window is a calendar proxy. |
| V1 calendar control | Mean for December 1 <= actual acquisition < April 1 for both sources. This is a pre-main-harvest proxy, not guaranteed preharvest for every field. |
| V2 max | Maximum of each variable over the same December–June observed months |
| V3 median | Median over the same December–June observed months |
| V3 mode | Half-sample continuous-mode estimate over the same months; not the smallest tied exact mode |

Mean, median and mode are separate models, as requested. V3 mean equals V0 and is not fitted twice. The earlier
10-feature **index mean + maximum** model is also retained as a control; it is not mislabeled as mean-only V0.
V1 includes the planting lower bound because the before-harvest-only window otherwise includes preplanting scenes.
The five other variants do not use crop dates. Do not combine climate, band and statistic changes into one comparison.

For the modal estimator: discard missing/nonfinite values, sort, and recursively retain a shortest interval containing
ceil(n/2) observations. Return the value/mean for one/two observations. Average the recursively computed estimates
for tied shortest intervals (a stated symmetric tie adaptation); equal-gap three-point samples return the middle value.
The [Bickel–Fruehwirth method](https://arxiv.org/abs/math/0505419) motivates the estimator. With only 1–7 observations,
a seasonal population mode is weakly determined. Save all-unique and interval-tie diagnostics. Never round values
or choose a bandwidth based on yield/evaluation scores.

## Calendar evidence and source limits

[FEWS NET, Zimbabwe February–September 2023, p. 4](https://fews.net/sites/default/files/documents/reports/ZW_February_to_September_2023_FSO_Final_jh.pdf)
shows approximate November–January planting, March green harvest and April–June main harvest. Report text describes
April/May harvest onset and some green consumption by late February. FEWS NET is not a Zimbabwe-government
field-harvest database. Its calendar motivates the April 1 cutoff; it does not supply individual crop dates.

The [Zimbabwe National Climate Change Adaptation Plan 2024, section 2.1, printed p. 5](https://unfccc.int/sites/default/files/resource/NAP-Zimbabwe-2024.pdf)
is the government source for the four climatic seasons: hot/mainly dry mid-August–mid-November, main rains
mid-November–mid-March, post-rain transition mid-March–mid-May, cool/dry mid-May–mid-August. These are approximate
climatic phases, not exact harvest boundaries. Both source links are stored in the experiment configuration.

Use December–June because the shared collection lacks October/November 2022 imagery for Lacuna. We do not silently
give 2024 extra months. Use `scenes.acquired` (the actual acquisition date), not a month label or a source photo date.
Lacuna planting/harvest dates come from the released provider labels, reconciled in the earlier audit. No 2024 field
dates are imputed as if measured. Actual harvest dates are retrospective metadata and do not establish forecast skill.

## Population, preprocessing and fitting

Read the frozen step-9 combined table and retain its eligibility: 1,880 target fields (376 fold-0 reserved) and
4,330 eligible auxiliary fields before the per-split buffer. Reuse the exact saved outer/inner memberships and 2 km
source permissions. Do not require four observations inside the shortened V1 window; that would change the target
population. Export counts and missingness for every variant. Keep all 1,504 evaluation IDs in every arm.

Use Ridge for target-only and the existing adaptive Ridge for merged training, with the same alpha grid
0.01/0.1/1/10/100/1000 and source ratios 0/0.1/0.3/1. Ratio zero permits rejecting auxiliary data. Tune using the
same three inner spatial folds in each of the four outer folds. Fit missing-value medians, 1st/99th percentile
clipping and scaling on target-training rows only. An entirely empty training feature is fixed to zero; no evaluation
values or labels may set these transforms. Source/target outcome centering and scaling use permitted training rows only.
Clip all predicted yields to >=0. No target yield, harvest date, observation count or source ID is used as a predictor.

Compare every version within each feature family and training setup. The declared primary contrast is bands V1
preharvest mean versus bands V0 mean, target-only. Also report all versions versus their same-family V0, merged versus
target-only, crop-date V1 versus common-calendar V1, and the existing mean+max control. Keep the control's saved predictions unchanged and independently replay
its selected models during this run. Report selected source weights and target train/evaluation gaps.

## Evaluation and release

Report pooled/fold RMSE, MAE, bias, R² and Spearman; paired 95% intervals resample spatial groups 2,000 times.
Use identical group draws across contrasts. Intervals are conditional on predictions and do not include full training
uncertainty. Secondary comparisons are numerous and unadjusted; the lowest observed score is not a confirmed winner.
Do not retune windows, statistics or grids after viewing these results, and never fit/score fold 0.

Publish a new `data/runs/zimbabwe_aggregation_v1/` with input hashes, config, date/window audit, monthly observations,
feature dictionary/matrix, exact memberships/permissions, predictions, tuning, fit accounting, metrics, paired intervals,
plot and `RESULTS.md`. Preserve all original releases. New source/config changes require a separate output destination.
