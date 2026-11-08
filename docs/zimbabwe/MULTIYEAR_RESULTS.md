# Expanded Zimbabwe training: same 2023 evaluation fields (v2 follows the team rules)

**Use v2 numbers.** The published v1 release (7 November) broke two team rules. It stays unchanged in the record
below. v2 (`zimbabwe_multiyear_v2`, 8 November) keeps the same 1,504 Lacuna 2023 fields, outer folds 1–4, inner folds,
2 km buffer, four-month imagery rule, grids, seed and bootstrap draws.

## v2 headline: under the team rules there is no broader pool to add

Every v1 "extra" training row is outside `labels_v1.include_primary`:

| Cohort | Screened | Imagery-eligible | include_primary training pool (v2) | Leaves the v1 pools because |
|---|---:|---:|---:|---|
| Lacuna 2022 | 169 | 0 | 0 | already excluded: imagery gap (`dropped_year_2022_imagery_gap`) |
| Lacuna 2023 | 2,097 | 2,097 | 1,880 | 212 `lacuna_intercropped`, 5 `lacuna_irrigated` |
| Zimbabwe 2024 | 4,332 | 4,330 | 2,456 | 1,874 `zimbabwe_2024_zero_likely_not_measured` (all recorded zeros) |

So v2 all-Lacuna trains on exactly the primary Lacuna fit rows, and v2 full-Zimbabwe on those plus the include_primary
2024 rows. These are the step 14 v2 Lacuna-only and merged pools. We still fitted all 22 new arms: **all 22 are identical
to their step 14 v2 twin** (largest difference 5e-12 t/ha before CSV rounding, 0 after). They are marked `identical_to` in
[arm_identity.csv](../../results/multiyear_v2/arm_identity.csv) and are not new evidence.

**Prespecified comparison** (ten bands, full-Zimbabwe minus all-Lacuna; pooled out-of-fold scores):

| | v1 (breaks rules 1 and 2) | v2 (team rules) |
|---|---|---|
| Window | crop-date V1: survey planting ≤ image < survey harvest | calendar V1: 1 December ≤ image < 1 April |
| All-Lacuna pool | 1,128 primary + 132–150 non-primary per outer fit | 1,128 primary per outer fit |
| Full-Zimbabwe pool adds | 4,191–4,226 2024 rows per outer fit, zeros included | 2,335–2,367 include_primary 2024 rows per outer fit |
| All-Lacuna RMSE / R² | 1.7480 / 0.2239 | **1.7540 / 0.2186** |
| Full-Zimbabwe RMSE / R² | 1.7490 / 0.2231 | **1.7532 / 0.2193** |
| RMSE difference, 95% spatial-group interval | +0.0009 [−0.0008, +0.0026] | **−0.0008 [−0.0028, +0.0013]** |
| R² difference, 95% interval | −0.0008 [−0.0023, +0.0007] | **+0.0007 [−0.0012, +0.0025]** |

**Which v1 numbers broke which rule.**

1. **Label-free windows.** v1's prespecified comparison, its best arm (1.7480 / 0.2239) and every `v1_preharvest_mean`
   row use survey planting and harvest dates as the window anchor. The crop-date window also entered the shared
   eligibility rule (finite predictors in every arm), so survey dates could remove a training row. On this data it
   removed none. v2 has no crop-date feature set, so dates touch neither features nor eligibility.
2. **Training rows follow include_primary.** Every v1 `_all_lacuna` arm added the 217 non-primary 2023 Lacuna rows;
   every v1 `_all_zimbabwe` arm added those plus all 4,330 imagery-eligible 2024 rows, including the 1,874 zeros. Every
   v1 `_merged` control (copied from step 14 v1) also used the zeros. All of these numbers are superseded.

Conclusion: the v1 finding "expanded Lacuna helps a little (−0.0023)" depended on non-primary rows and does not survive the
rule. Adding include_primary 2024 rows changes ten-band calendar RMSE by −0.0008 (uncertain). The best v2 score is ten-band
calendar mean + 2024, 1.7532 / 0.2193, identical to step 14 v2. The richer monthly Ridge result (1.6926) remains stronger.

v2 files (tracked copies): [RESULTS.md](../../results/multiyear_v2/RESULTS.md), [metrics](../../results/multiyear_v2/metrics.csv),
[paired intervals](../../results/multiyear_v2/paired_differences.csv), [arm identity](../../results/multiyear_v2/arm_identity.csv),
[manifest](../../results/multiyear_v2/manifest.json), [verification](../../results/multiyear_v2/verification.json),
[interval verification](../../results/multiyear_v2/interval_verification.json), [R² audit](../../results/multiyear_v2/r2_audit.csv).
The full release is `data/runs/zimbabwe_multiyear_v2/` (local, git-ignored). Configuration: [v2](../../configs/zimbabwe_multiyear_v2.json);
protocol amendment in [MULTIYEAR_PROTOCOL.md](MULTIYEAR_PROTOCOL.md).

```bash
python scripts/step15_compare_zimbabwe_multiyear.py --config configs/zimbabwe_multiyear_v2.json --output data/runs/zimbabwe_multiyear_v2
python scripts/verification/verify_zimbabwe_multiyear.py --release data/runs/zimbabwe_multiyear_v2 --report results/multiyear_v2/verification.json
python scripts/verification/verify_multiyear_intervals.py --release data/runs/zimbabwe_multiyear_v2 --output results/multiyear_v2/interval_verification.json
python scripts/verification/audit_zimbabwe_r2.py --release data/runs/zimbabwe_multiyear_v2 --output results/multiyear_v2
```

Step 15 v2 needs the step 14 v2 release first and takes under a minute. The step 15 default config is now v2; pass
`--config configs/zimbabwe_multiyear_v1.json` and a new `--output` to replay v1.

---

## v1 record (7 November): breaks team rules; do not cite as a headline

The text below is the original v1 report. Its crop-date rows break rule 1; its `_all_lacuna`, `_all_zimbabwe` and `_merged`
columns break rule 2.

**The best observed compact model is the preharvest mean of ten reflectance bands with expanded Lacuna training: RMSE 1.7480 t/ha, R² 0.2239.** Adding 2024 gives 1.7490 and 0.2231 for that model. The common-calendar merged model is almost tied at 1.7481 and 0.2238. These small differences do not establish a benefit from 2024.

**2022 could not be included.** We audited all 6,598 screened labels. Every 2022 field has only one or two observed December–June months, below the existing four-month minimum. Missing imagery was not filled, invented or taken from another season. The requested 2022–2024 comparison therefore becomes a comparison of eligible **2023 versus 2023 + 2024 training**, with the same 1,504 original Lacuna 2023 fields used for evaluation.

| Label cohort | Screened fields | Imagery-eligible pool | Excluded |
|---|---:|---:|---:|
| Lacuna 2022 | 169 | 0 | 169 |
| Lacuna 2023 | 2,097 | 2,097 | 0 |
| Zimbabwe 2024 | 4,332 | 4,330 | 2 |

Eligible pool counts include fields later withheld or spatially excluded in each fit. They are not simultaneous training counts. Individual missing months are omitted; all actual aggregate predictors entering the models are finite.

### Results

Every row uses the same evaluation IDs, true yields and nested spatial folds. RMSE is in t/ha (lower is better); R² is pooled across all 1,504 out-of-fold predictions (higher is better). The two metrics rank models identically here because the evaluation outcomes are identical. Both training choices use Ridge; the merged choice additionally uses provider adaptation and a tuned 2024 weight.

#### Ten reflectance bands

| Aggregation | All eligible Lacuna: RMSE | R² | Lacuna + 2024: RMSE | R² |
|---|---:|---:|---:|---:|
| V0 / V3 mean | 1.7945 | 0.1821 | 1.7945 | 0.1821 |
| V1 preharvest mean | 1.7480 | 0.2239 | 1.7490 | 0.2231 |
| V1 calendar mean | 1.7494 | 0.2227 | 1.7481 | 0.2238 |
| V2 maximum | 1.8862 | 0.0964 | 1.8850 | 0.0975 |
| V3 median | 1.9368 | 0.0473 | 1.9364 | 0.0476 |
| V3 modal estimate | 2.0184 | -0.0348 | 2.0171 | -0.0334 |

#### Five vegetation indices

| Aggregation | All eligible Lacuna: RMSE | R² | Lacuna + 2024: RMSE | R² |
|---|---:|---:|---:|---:|
| V0 / V3 mean | 1.8661 | 0.1155 | 1.8655 | 0.1161 |
| V1 preharvest mean | 1.8082 | 0.1696 | 1.8080 | 0.1697 |
| V1 calendar mean | 1.8085 | 0.1693 | 1.8067 | 0.1709 |
| V2 maximum | 1.7964 | 0.1804 | 1.7962 | 0.1806 |
| V3 median | 1.9298 | 0.0541 | 1.9298 | 0.0541 |
| V3 modal estimate | 1.9653 | 0.0190 | 1.9649 | 0.0194 |

V3 mean equals V0 and is fitted once. Median and mode are separate models. The historical index mean + maximum control uses ten predictors: expanded Lacuna scores **1.7952 / 0.1814**, and expanded Lacuna + 2024 scores **1.7948 / 0.1819** (RMSE / R²).

### What the additional data changed

The expanded Lacuna pool adds **217 screened 2023 fields: 212 intercropped rainfed and five irrigated**. This broadens management coverage; it is not evidence about 2022. After a 2 km buffer against reserved, evaluation and validation fields, each outer fit adds 132 / 149 / 138 / 150 fields to its original 1,128 training fields. Original evaluation membership is unchanged and the 376 fold-0 fields remain reserved.

For the band preharvest model, adding these Lacuna fields changes RMSE from **1.7503 to 1.7480**: difference **−0.0023**, 95% spatial-group interval **[−0.0138, +0.0073]**. This small improvement is uncertain.

Adding 2024 to the expanded band preharvest model changes RMSE by **+0.0009**, interval **[−0.0008, +0.0026]**. Inner validation selected zero 2024 weight in one of four folds. The larger source still provides no clear gain. Median-index merged predictions are identical to Lacuna-only predictions because all four fits select zero source weight.

Within the expanded Lacuna band models, preharvest mean improves on full-season mean by **−0.0465 t/ha**, interval **[−0.0904, −0.0051]**. Its difference from the common-calendar mean is uncertain: **−0.0014**, interval **[−0.0460, +0.0362]**. These are exploratory secondary contrasts, not evidence that exact crop dates beat a calendar rule. The earlier richer monthly Ridge result, **1.6926 t/ha**, remains stronger than these compact summaries.

### Details and limitations

- **Unavailable imagery:** the pinned collection supplies December 2, 2021 for all 169 fields in the 2022 cohort and March 22, 2022 for 68. January, February, April, May and June are absent. October/November 2021 observations fall outside the common window and do not rescue the four-month rule. Ninety-one fields have no observation in their recorded planting-to-harvest window. The two excluded 2024 IDs and every per-feature exclusion are recorded in the eligibility audit. No additional imagery was downloaded.
- **Windows:** V0, V2 and V3 use December–June. V1 uses planting ≤ actual scene acquisition < harvest, inside that season. All 2024 field crop dates are missing, so its V1 uses December–March; the common-calendar control applies December–March to both providers. The four-month threshold applies to the full season; shortened windows need actual observations and finite predictors, not four months.
- **Fitting:** the same alpha grid, inner-validation objective, clipping/scaling and nonnegative prediction rule are retained. Preprocessing uses only permitted Lacuna training rows. Source calibration uses only permitted training rows. Explicit finite checks prevent imagery imputation. Counts, years, management flags and yields are not added as predictors.
- **Interpretation:** all scores concern the original 2023 target population, not accuracy across every year or management system. Harvest-date models are retrospective estimates. Confidence intervals resample 232 spatial groups 2,000 times and condition on fitted predictions. Many comparisons were made; the best observed score is not a confirmed winner on a fresh blind test.

### Files and reproduction

The new [release directory](../../data/runs/zimbabwe_multiyear_v1/) contains:

| File | Purpose |
|---|---|
| [RESULTS.md](../../data/runs/zimbabwe_multiyear_v1/RESULTS.md) | Concise, frozen score table |
| [observations.csv](../../data/runs/zimbabwe_multiyear_v1/observations.csv) | All 6,598 label records, management/date metadata and new eligibility flags |
| [coverage_summary.csv](../../data/runs/zimbabwe_multiyear_v1/coverage_summary.csv), [eligibility_audit.csv](../../data/runs/zimbabwe_multiyear_v1/eligibility_audit.csv) | Cohort coverage and per-field/per-feature exclusions |
| [monthly_observations.parquet](../../data/runs/zimbabwe_multiyear_v1/monthly_observations.parquet), [window_audit.csv](../../data/runs/zimbabwe_multiyear_v1/window_audit.csv) | Observed monthly values, missing flags, acquisition dates and aggregation counts |
| [features.parquet](../../data/runs/zimbabwe_multiyear_v1/features.parquet), [feature_dictionary.json](../../data/runs/zimbabwe_multiyear_v1/feature_dictionary.json) | Explicit predictor matrices for all thirteen feature sets |
| [fit_memberships.csv](../../data/runs/zimbabwe_multiyear_v1/fit_memberships.csv), [extra_lacuna_spatial_permissions.csv](../../data/runs/zimbabwe_multiyear_v1/extra_lacuna_spatial_permissions.csv) | Ordered fitting rows and additional-field 2 km permissions |
| [metrics.csv](../../data/runs/zimbabwe_multiyear_v1/metrics.csv), [predictions.csv](../../data/runs/zimbabwe_multiyear_v1/predictions.csv) | RMSE/R²/SSE/SST and predictions for 26 new arms plus 26 unchanged controls |
| [selected_parameters.csv](../../data/runs/zimbabwe_multiyear_v1/selected_parameters.csv), [paired_differences.csv](../../data/runs/zimbabwe_multiyear_v1/paired_differences.csv) | Model choices, source use and paired uncertainty |
| [manifest.json](../../data/runs/zimbabwe_multiyear_v1/manifest.json), [PROTOCOL.md](../../data/runs/zimbabwe_multiyear_v1/PROTOCOL.md) | Input/output fingerprints, software and fixed design |

Run `python scripts/step15_compare_zimbabwe_multiyear.py --output data/runs/zimbabwe_multiyear_replay` with the pinned team database and a new destination. Run `python scripts/verification/verify_zimbabwe_multiyear.py --report results/multiyear/verification.json` to independently reconstruct features, check memberships/distances and replay the selected fits. Original releases and the shared database are unchanged.

For the R² discrepancy with Claude, read the [detailed R² review packet](R2_AUDIT.md). The [standalone R² audit](../../scripts/verification/audit_zimbabwe_r2.py) needs only committed CSVs; expanded results are recorded in [its receipt](../../results/multiyear/r2_audit.json). Scientific checks and paired interval reconstruction are recorded in [verification](../../results/multiyear/verification.json) and [interval verification](../../results/multiyear/interval_verification.json).
