# Complete Zimbabwe results appendix

This appendix records every saved target-model arm from steps 9, 10, 12, 13, 14 and 15, plus the separate 2024 source-learnability diagnostic. It accompanies the manuscript data section and one-page team summary. Values are transcribed from the immutable release metrics and independently recomputed from their saved predictions. No models were refitted for this appendix.

## Scope and reading rules

- **149 target-arm rows** across six releases all evaluate the same 1,504 Lacuna 2023 fields; they are not 149 independent experiments. There are 106 distinct exported prediction fingerprints and 105 numerically distinct prediction vectors at an absolute tolerance of 1e-9 t/ha. These counts describe output duplication, not independent evidence or independent model-selection decisions.
- **Six additional source-diagnostic arms** evaluate 3,764 Zimbabwe 2024 fields. Their smaller RMSE values cannot be compared directly with the target scores because the outcome distribution and evaluation population differ.
- RMSE, MAE and signed bias use t/ha. R² is unweighted pooled out-of-fold predictive R², computed as 1 − SSE/SST on original-scale yields. It is not mean fold R² or squared correlation. Negative values are retained.
- **T** denotes the original 1,880-field primary Lacuna 2023 pool: 376 fold-0 fields are reserved and each outer fit uses 1,128 fields. **E** adds 217 eligible 2023 Lacuna observations; the 2 km buffer leaves 132–150 additional fields per outer fit. **S** denotes eligible 2024 auxiliary data; up to 4,226 / 4,191 / 4,194 / 4,213 rows are permitted in outer folds 1–4. A model allowing S may select source weight zero. T[0.25] and T[0.5] subsample target-training spatial groups, not source rows.
- All 169 Lacuna 2022 observations and two 2024 observations fail the four-month common-window imagery rule in step 15. The expanded model comparison therefore uses 2023 and optionally 2024 training data; it does not estimate a 2022 contribution.
- The original monthly/weather experiments allow training-fold imputation of missing monthly observations and retain missing-scene masks. Steps 14–15 aggregate observed months; step 15 explicitly rejects nonfinite aggregate predictors. These policies must not be conflated.
- All target results reuse previously inspected development folds. The reserved fold remains unused for these comparisons; the results are exploratory and retrospective, not a new blind test or a real-time 2023 forecast.

[RESULTS_LEDGER.csv](RESULTS_LEDGER.csv) gives full-precision saved scores, feature/learner/training descriptions, file hashes, exact method names and duplicate-prediction references. `same_exported_predictions_as` fingerprints ID-aligned CSV values at twelve significant digits. `numerically_equivalent_predictions_as` additionally identifies differences no larger than 1e-9 t/ha. A duplicate can be a preserved historical control or a distinct training policy that selected the same predictions; it is not another independent replication.

## Prespecified primary contrasts within each exploratory release

Each difference is method minus reference; negative ΔRMSE favors the method. Intervals resample spatial groups 2,000 times and condition on the fitted predictions. The compact-weather release additionally reports weather-cell sensitivity intervals. “Prespecified” means fixed before that release was scored, not registered before the whole sequence of development-data analyses.

| Step | Method minus reference | ΔRMSE | 95% spatial-group interval |
|---|---|---:|---|
| 9 | `pooled_adaptive` − `lacuna_only` | -0.002951 | [-0.007567, +0.001319] |
| 10 | `transfer_selector` − `target_selector` | -0.009588 | [-0.043900, +0.022618] |
| 12 | `weather_tree_transfer` − `weather_tree_target` | +0.026372 | [+0.009351, +0.045004] |
| 13 | `compact4_tree_transfer` − `compact4_tree_target` | +0.030172 | [-0.000935, +0.061152] |
| 14 | `bands_v1_preharvest_mean_target` − `bands_v0_mean_target` | -0.048115 | [-0.088485, -0.010358] |
| 15 | `bands_v1_preharvest_mean_all_zimbabwe` − `bands_v1_preharvest_mean_all_lacuna` | +0.000928 | [-0.000753, +0.002556] |

The primary compact-weather contrast does not establish a merging benefit; the full-weather tree contrast indicates worse target prediction after adding the source under that protocol. The aggregation contrast supports a better compact band summary on these development fields. Neither the original merge nor the broader-pool preharvest comparison establishes a benefit from 2024.

## Complete target results

The “Repeated predictions” column marks numerical equivalence to an earlier row. Full earlier-release references are in the ledger. All rows in the following six tables have **n = 1,504**. Feature counts are input counts before provider feature augmentation; tree models may additionally include a source indicator. Archived index names, including the implementation-specific `mtci` ratio, are defined explicitly in the [manuscript section](DATA_SOURCES_AND_PREPARATION.md).

### Step 9 Initial harmonization and source adaptation

[Saved report](../../data/runs/zimbabwe_merge_v1/RESULTS.md) · [exact metrics](../../data/runs/zimbabwe_merge_v1/metrics.csv) · [predictions](../../data/runs/zimbabwe_merge_v1/predictions.csv) · [all paired intervals](../../data/runs/zimbabwe_merge_v1/paired_differences.csv) · [manifest](../../data/runs/zimbabwe_merge_v1/manifest.json)

All models use ten index features: the mean and maximum of NDVI, GCVI, MTCI, NDVI705 and NDVI740 over December–June. `pooled_naive` uses unweighted concatenation; `pooled_intercept` separates provider intercepts; `pooled_adaptive` also permits provider-specific slopes and outcome calibration. Zero-label sensitivity policies do not establish that recorded zeros are invalid.

| Exact method | Training | RMSE | MAE | R² | Repeated predictions |
|---|---|---:|---:|---:|---|
| `train_mean` | T | 1.988053 | 1.621651 | -0.003874 | — |
| `lacuna_only` | T | 1.796767 | 1.447727 | 0.180013 | — |
| `pooled_naive` | T+S | 2.270721 | 1.724338 | -0.309637 | — |
| `pooled_intercept` | T+S | 1.793812 | 1.447755 | 0.182708 | — |
| `pooled_adaptive` | T+S | 1.793816 | 1.445975 | 0.182704 | — |
| `pooled_positive_sensitivity` | T+S | 1.793197 | 1.445710 | 0.183268 | — |
| `pooled_zero_weight_sensitivity` | T+S | 1.793386 | 1.445807 | 0.183096 | — |
| `lacuna_tree` | T | 1.802555 | 1.441286 | 0.174722 | — |
| `pooled_tree` | T+S | 1.799227 | 1.436343 | 0.177766 | — |

### Step 10 Source quality and representation diagnostics

[Saved report](../../data/runs/zimbabwe_transfer_diagnosis_v1/RESULTS.md) · [exact metrics](../../data/runs/zimbabwe_transfer_diagnosis_v1/metrics.csv) · [predictions](../../data/runs/zimbabwe_transfer_diagnosis_v1/predictions.csv) · [all paired intervals](../../data/runs/zimbabwe_transfer_diagnosis_v1/paired_differences.csv) · [manifest](../../data/runs/zimbabwe_transfer_diagnosis_v1/manifest.json)

Seasonal = ten index mean/max features; monthly = those ten plus 105 month-by-variable values and seven missing-scene masks (122 total); Presto = 128 existing frozen embedding dimensions. Presto uses different window/masking conventions, so it is not a strictly controlled representation swap. Coordinates-only uses geocentric coordinates with distance-weighted nearest-neighbor regression. The source-signal model adds a source-trained tree prediction to the monthly target Ridge input. Quality, relevance, shuffled-label and matched-subset policies change auxiliary use; the fraction experiments reduce target-training groups. Selectors choose their model using inner validation.

| Exact method | Training | RMSE | MAE | R² | Repeated predictions |
|---|---|---:|---:|---:|---|
| `seasonal_target` | T | 1.796767 | 1.447727 | 0.180013 | Yes |
| `seasonal_adaptive` | T+S | 1.793816 | 1.445975 | 0.182704 | Yes |
| `seasonal_quality` | T+S | 1.793812 | 1.445947 | 0.182708 | — |
| `seasonal_relevance` | T+S | 1.793893 | 1.446289 | 0.182634 | — |
| `monthly_target` | T | 1.692594 | 1.322254 | 0.272339 | — |
| `monthly_adaptive` | T+S | 1.689178 | 1.318411 | 0.275274 | — |
| `monthly_quality` | T+S | 1.689351 | 1.318495 | 0.275125 | — |
| `monthly_relevance` | T+S | 1.690704 | 1.319571 | 0.273963 | — |
| `presto_target` | T | 1.681456 | 1.315072 | 0.281885 | — |
| `presto_adaptive` | T+S | 1.679646 | 1.314030 | 0.283430 | — |
| `presto_quality` | T+S | 1.679505 | 1.313848 | 0.283550 | — |
| `presto_relevance` | T+S | 1.680575 | 1.314701 | 0.282637 | — |
| `monthly_tree_target` | T | 1.659352 | 1.289692 | 0.300640 | — |
| `monthly_tree_transfer` | T+S | 1.657757 | 1.296637 | 0.301984 | — |
| `monthly_source_signal` | T+S teacher | 1.692620 | 1.321812 | 0.272317 | — |
| `coordinates_only` | T | 1.878072 | 1.451341 | 0.104124 | — |
| `seasonal_shuffle_101` | T+S | 1.796434 | 1.447826 | 0.180317 | — |
| `seasonal_shuffle_202` | T+S | 1.796664 | 1.448030 | 0.180107 | — |
| `seasonal_shuffle_303` | T+S | 1.796747 | 1.447857 | 0.180031 | — |
| `seasonal_shuffle_404` | T+S | 1.796679 | 1.448095 | 0.180093 | — |
| `seasonal_shuffle_505` | T+S | 1.797000 | 1.448341 | 0.179800 | — |
| `seasonal_matched_606` | T+S | 1.793788 | 1.445926 | 0.182730 | — |
| `seasonal_matched_707` | T+S | 1.793781 | 1.445935 | 0.182736 | — |
| `seasonal_matched_808` | T+S | 1.793765 | 1.445907 | 0.182751 | — |
| `seasonal_ridge_fraction_0.25` | T[0.25] | 1.809613 | 1.465659 | 0.168246 | — |
| `seasonal_adaptive_fraction_0.25` | T[0.25]+S | 1.807835 | 1.462725 | 0.169880 | — |
| `seasonal_ridge_fraction_0.5` | T[0.5] | 1.801894 | 1.455867 | 0.175327 | — |
| `seasonal_adaptive_fraction_0.5` | T[0.5]+S | 1.800447 | 1.454070 | 0.176650 | — |
| `target_selector` | T | 1.692338 | 1.321251 | 0.272559 | — |
| `transfer_selector` | T+S | 1.682749 | 1.311751 | 0.280779 | — |

### Step 12 Full weather and interaction features

[Saved report](../../data/runs/zimbabwe_weather_v1/RESULTS.md) · [exact metrics](../../data/runs/zimbabwe_weather_v1/metrics.csv) · [predictions](../../data/runs/zimbabwe_weather_v1/predictions.csv) · [all paired intervals](../../data/runs/zimbabwe_weather_v1/paired_differences.csv) · [manifest](../../data/runs/zimbabwe_weather_v1/manifest.json)

Monthly controls retain the 122-column imagery representation. Weather adds 46 regional features (168 total); interactions add fourteen NDVI × weather terms (182 total). Weather-only uses 46 predictors. `shared` is weighted Ridge on physical yield units without provider-specific calibration; `adaptive` uses separate provider centering/scales and shared/provider-specific slopes.

| Exact method | Training | RMSE | MAE | R² | Repeated predictions |
|---|---|---:|---:|---:|---|
| `monthly_target` | T | 1.692594 | 1.322254 | 0.272339 | Yes |
| `monthly_adaptive` | T+S | 1.689178 | 1.318411 | 0.275274 | Yes |
| `monthly_tree_target` | T | 1.659352 | 1.289692 | 0.300640 | Yes |
| `monthly_tree_transfer` | T+S | 1.657757 | 1.296637 | 0.301984 | Yes |
| `weather_only_target` | T | 1.905502 | 1.512309 | 0.077764 | — |
| `weather_target` | T | 1.744311 | 1.364891 | 0.227192 | — |
| `weather_adaptive` | T+S | 1.742200 | 1.362420 | 0.229062 | — |
| `weather_shared` | T+S | 1.749902 | 1.369871 | 0.222230 | — |
| `interactions_target` | T | 1.733092 | 1.351325 | 0.237101 | — |
| `interactions_adaptive` | T+S | 1.729714 | 1.347903 | 0.240073 | — |
| `interactions_shared` | T+S | 1.745263 | 1.359906 | 0.226349 | — |
| `weather_tree_target` | T | 1.695751 | 1.311391 | 0.269622 | — |
| `weather_tree_transfer` | T+S | 1.722124 | 1.337624 | 0.246728 | — |

### Step 13 Compact weather features

[Saved report](../../data/runs/zimbabwe_weather_compact_v1/RESULTS.md) · [exact metrics](../../data/runs/zimbabwe_weather_compact_v1/metrics.csv) · [predictions](../../data/runs/zimbabwe_weather_compact_v1/predictions.csv) · [all paired intervals](../../data/runs/zimbabwe_weather_compact_v1/paired_differences.csv) · [manifest](../../data/runs/zimbabwe_weather_compact_v1/manifest.json)

The two-feature extension adds January–March rainfall percent of normal and temperature anomaly (124 predictors total). The four-feature extension also adds the previous October–December summaries (126 total). Monthly and 46-weather controls are retained from earlier releases. Compact feature-count reduction also changes seasonal encoding.

| Exact method | Training | RMSE | MAE | R² | Repeated predictions |
|---|---|---:|---:|---:|---|
| `monthly_target` | T | 1.692594 | 1.322254 | 0.272339 | Yes |
| `monthly_adaptive` | T+S | 1.689178 | 1.318411 | 0.275274 | Yes |
| `monthly_tree_target` | T | 1.659352 | 1.289692 | 0.300640 | Yes |
| `monthly_tree_transfer` | T+S | 1.657757 | 1.296637 | 0.301984 | Yes |
| `weather_target` | T | 1.744311 | 1.364891 | 0.227192 | Yes |
| `weather_adaptive` | T+S | 1.742200 | 1.362420 | 0.229062 | Yes |
| `weather_shared` | T+S | 1.749902 | 1.369871 | 0.222230 | Yes |
| `weather_tree_target` | T | 1.695751 | 1.311391 | 0.269622 | Yes |
| `weather_tree_transfer` | T+S | 1.722124 | 1.337624 | 0.246728 | Yes |
| `compact2_target` | T | 1.699398 | 1.330826 | 0.266477 | — |
| `compact2_adaptive` | T+S | 1.696023 | 1.327297 | 0.269388 | — |
| `compact2_shared` | T+S | 1.678338 | 1.302088 | 0.284545 | — |
| `compact2_tree_target` | T | 1.680642 | 1.311757 | 0.282579 | — |
| `compact2_tree_transfer` | T+S | 1.674022 | 1.308794 | 0.288220 | — |
| `compact4_target` | T | 1.728332 | 1.355323 | 0.241287 | — |
| `compact4_adaptive` | T+S | 1.724834 | 1.351755 | 0.244355 | — |
| `compact4_shared` | T+S | 1.655411 | 1.285954 | 0.303959 | — |
| `compact4_tree_target` | T | 1.672713 | 1.296116 | 0.289333 | — |
| `compact4_tree_transfer` | T+S | 1.702885 | 1.321024 | 0.263464 | — |

### Step 14 Temporal aggregation with the original training pool

[Saved report](../../data/runs/zimbabwe_aggregation_v1/RESULTS.md) · [exact metrics](../../data/runs/zimbabwe_aggregation_v1/metrics.csv) · [predictions](../../data/runs/zimbabwe_aggregation_v1/predictions.csv) · [all paired intervals](../../data/runs/zimbabwe_aggregation_v1/paired_differences.csv) · [manifest](../../data/runs/zimbabwe_aggregation_v1/manifest.json)

Bands and vegetation indices are separate feature families with ten and five inputs, respectively. V0/V3 mean, V2 maximum, V3 median and V3 modal estimate use December–June. V1 preharvest uses recorded planting ≤ actual acquisition < harvest within that season, with December–March fallback for 2024; the calendar arm applies December–March to both providers. Mode is a half-sample continuous-mode estimate with symmetric tie handling. The separate legacy control concatenates five index means and five maxima. V3 mean equals V0 and is fitted once.

| Exact method | Training | RMSE | MAE | R² | Repeated predictions |
|---|---|---:|---:|---:|---|
| `bands_v0_mean_target` | T | 1.798434 | 1.431747 | 0.178491 | — |
| `bands_v0_mean_merged` | T+S | 1.798548 | 1.432105 | 0.178386 | — |
| `bands_v1_preharvest_mean_target` | T | 1.750319 | 1.391220 | 0.221860 | — |
| `bands_v1_preharvest_mean_merged` | T+S | 1.751118 | 1.391300 | 0.221149 | — |
| `bands_v1_calendar_mean_target` | T | 1.753976 | 1.401490 | 0.218605 | — |
| `bands_v1_calendar_mean_merged` | T+S | 1.753044 | 1.399339 | 0.219435 | — |
| `bands_v2_max_target` | T | 1.894488 | 1.530775 | 0.088394 | — |
| `bands_v2_max_merged` | T+S | 1.891606 | 1.529421 | 0.091166 | — |
| `bands_v3_median_target` | T | 1.940679 | 1.572846 | 0.043398 | — |
| `bands_v3_median_merged` | T+S | 1.940270 | 1.572537 | 0.043802 | — |
| `bands_v3_mode_target` | T | 2.014290 | 1.650825 | -0.030546 | — |
| `bands_v3_mode_merged` | T+S | 2.016102 | 1.655679 | -0.032401 | — |
| `indices_v0_mean_target` | T | 1.867558 | 1.511135 | 0.114127 | — |
| `indices_v0_mean_merged` | T+S | 1.866824 | 1.509832 | 0.114822 | — |
| `indices_v1_preharvest_mean_target` | T | 1.808726 | 1.463331 | 0.169061 | — |
| `indices_v1_preharvest_mean_merged` | T+S | 1.807105 | 1.461628 | 0.170550 | — |
| `indices_v1_calendar_mean_target` | T | 1.803713 | 1.454011 | 0.173661 | — |
| `indices_v1_calendar_mean_merged` | T+S | 1.808567 | 1.457818 | 0.169208 | — |
| `indices_v2_max_target` | T | 1.798595 | 1.449927 | 0.178344 | — |
| `indices_v2_max_merged` | T+S | 1.798092 | 1.449563 | 0.178803 | — |
| `indices_v3_median_target` | T | 1.933245 | 1.576648 | 0.050714 | — |
| `indices_v3_median_merged` | T+S | 1.932853 | 1.576307 | 0.051098 | — |
| `indices_v3_mode_target` | T | 1.969791 | 1.606578 | 0.014483 | — |
| `indices_v3_mode_merged` | T+S | 1.969174 | 1.606101 | 0.015101 | — |
| `legacy_indices_mean_max_target` | T | 1.796767 | 1.447727 | 0.180013 | Yes |
| `legacy_indices_mean_max_merged` | T+S | 1.793816 | 1.445975 | 0.182704 | Yes |

### Step 15 Expanded eligible Lacuna training pool

[Saved report](../../data/runs/zimbabwe_multiyear_v1/RESULTS.md) · [exact metrics](../../data/runs/zimbabwe_multiyear_v1/metrics.csv) · [predictions](../../data/runs/zimbabwe_multiyear_v1/predictions.csv) · [all paired intervals](../../data/runs/zimbabwe_multiyear_v1/paired_differences.csv) · [manifest](../../data/runs/zimbabwe_multiyear_v1/manifest.json)

Bands and vegetation indices are separate feature families with ten and five inputs, respectively. V0/V3 mean, V2 maximum, V3 median and V3 modal estimate use December–June. V1 preharvest uses recorded planting ≤ actual acquisition < harvest within that season, with December–March fallback for 2024; the calendar arm applies December–March to both providers. Mode is a half-sample continuous-mode estimate with symmetric tie handling. The separate legacy control concatenates five index means and five maxima. V3 mean equals V0 and is fitted once.

The `_target` and `_merged` rows preserve the 26 step-14 controls; `_all_lacuna` and `_all_zimbabwe` are the 26 new E/E+S arms. E broadens management coverage with 212 intercropped rainfed and five irrigated 2023 fields, subject to spatial buffering. No 2022 fields enter a model.

| Exact method | Training | RMSE | MAE | R² | Repeated predictions |
|---|---|---:|---:|---:|---|
| `bands_v0_mean_target` | T | 1.798434 | 1.431747 | 0.178491 | Yes |
| `bands_v0_mean_merged` | T+S | 1.798548 | 1.432105 | 0.178386 | Yes |
| `bands_v1_preharvest_mean_target` | T | 1.750319 | 1.391220 | 0.221860 | Yes |
| `bands_v1_preharvest_mean_merged` | T+S | 1.751118 | 1.391300 | 0.221149 | Yes |
| `bands_v1_calendar_mean_target` | T | 1.753976 | 1.401490 | 0.218605 | Yes |
| `bands_v1_calendar_mean_merged` | T+S | 1.753044 | 1.399339 | 0.219435 | Yes |
| `bands_v2_max_target` | T | 1.894488 | 1.530775 | 0.088394 | Yes |
| `bands_v2_max_merged` | T+S | 1.891606 | 1.529421 | 0.091166 | Yes |
| `bands_v3_median_target` | T | 1.940679 | 1.572846 | 0.043398 | Yes |
| `bands_v3_median_merged` | T+S | 1.940270 | 1.572537 | 0.043802 | Yes |
| `bands_v3_mode_target` | T | 2.014290 | 1.650825 | -0.030546 | Yes |
| `bands_v3_mode_merged` | T+S | 2.016102 | 1.655679 | -0.032401 | Yes |
| `indices_v0_mean_target` | T | 1.867558 | 1.511135 | 0.114127 | Yes |
| `indices_v0_mean_merged` | T+S | 1.866824 | 1.509832 | 0.114822 | Yes |
| `indices_v1_preharvest_mean_target` | T | 1.808726 | 1.463331 | 0.169061 | Yes |
| `indices_v1_preharvest_mean_merged` | T+S | 1.807105 | 1.461628 | 0.170550 | Yes |
| `indices_v1_calendar_mean_target` | T | 1.803713 | 1.454011 | 0.173661 | Yes |
| `indices_v1_calendar_mean_merged` | T+S | 1.808567 | 1.457818 | 0.169208 | Yes |
| `indices_v2_max_target` | T | 1.798595 | 1.449927 | 0.178344 | Yes |
| `indices_v2_max_merged` | T+S | 1.798092 | 1.449563 | 0.178803 | Yes |
| `indices_v3_median_target` | T | 1.933245 | 1.576648 | 0.050714 | Yes |
| `indices_v3_median_merged` | T+S | 1.932853 | 1.576307 | 0.051098 | Yes |
| `indices_v3_mode_target` | T | 1.969791 | 1.606578 | 0.014483 | Yes |
| `indices_v3_mode_merged` | T+S | 1.969174 | 1.606101 | 0.015101 | Yes |
| `legacy_indices_mean_max_target` | T | 1.796767 | 1.447727 | 0.180013 | Yes |
| `legacy_indices_mean_max_merged` | T+S | 1.793816 | 1.445975 | 0.182704 | Yes |
| `bands_v0_mean_all_lacuna` | E | 1.794512 | 1.425971 | 0.182070 | — |
| `bands_v0_mean_all_zimbabwe` | E+S | 1.794496 | 1.426186 | 0.182084 | — |
| `bands_v1_preharvest_mean_all_lacuna` | E | 1.748027 | 1.384094 | 0.223896 | — |
| `bands_v1_preharvest_mean_all_zimbabwe` | E+S | 1.748955 | 1.384206 | 0.223072 | — |
| `bands_v1_calendar_mean_all_lacuna` | E | 1.749413 | 1.392316 | 0.222665 | — |
| `bands_v1_calendar_mean_all_zimbabwe` | E+S | 1.748110 | 1.389750 | 0.223823 | — |
| `bands_v2_max_all_lacuna` | E | 1.886191 | 1.520445 | 0.096361 | — |
| `bands_v2_max_all_zimbabwe` | E+S | 1.885014 | 1.520931 | 0.097488 | — |
| `bands_v3_median_all_lacuna` | E | 1.936756 | 1.568889 | 0.047263 | — |
| `bands_v3_median_all_zimbabwe` | E+S | 1.936423 | 1.568689 | 0.047590 | — |
| `bands_v3_mode_all_lacuna` | E | 2.018398 | 1.655655 | -0.034754 | — |
| `bands_v3_mode_all_zimbabwe` | E+S | 2.017118 | 1.654891 | -0.033442 | — |
| `indices_v0_mean_all_lacuna` | E | 1.866149 | 1.506775 | 0.115463 | — |
| `indices_v0_mean_all_zimbabwe` | E+S | 1.865498 | 1.506023 | 0.116079 | — |
| `indices_v1_preharvest_mean_all_lacuna` | E | 1.808174 | 1.458775 | 0.169568 | — |
| `indices_v1_preharvest_mean_all_zimbabwe` | E+S | 1.808017 | 1.459175 | 0.169713 | — |
| `indices_v1_calendar_mean_all_lacuna` | E | 1.808450 | 1.455160 | 0.169315 | — |
| `indices_v1_calendar_mean_all_zimbabwe` | E+S | 1.806703 | 1.450574 | 0.170919 | — |
| `indices_v2_max_all_lacuna` | E | 1.796388 | 1.444053 | 0.180359 | — |
| `indices_v2_max_all_zimbabwe` | E+S | 1.796159 | 1.443780 | 0.180568 | — |
| `indices_v3_median_all_lacuna` | E | 1.929771 | 1.572390 | 0.054123 | — |
| `indices_v3_median_all_zimbabwe` | E+S | 1.929771 | 1.572390 | 0.054123 | Yes |
| `indices_v3_mode_all_lacuna` | E | 1.965261 | 1.601871 | 0.019011 | — |
| `indices_v3_mode_all_zimbabwe` | E+S | 1.964888 | 1.601614 | 0.019384 | — |
| `legacy_indices_mean_max_all_lacuna` | E | 1.795248 | 1.443691 | 0.181399 | — |
| `legacy_indices_mean_max_all_zimbabwe` | E+S | 1.794752 | 1.442576 | 0.181851 | — |

## Separate 2024 source learnability diagnostic

This grouped nested-validation diagnostic evaluates 3,764 source fields after protecting historical source fold 0, its neighbors, and target fold 0. It asks whether useful signal exists within 2024; it does not test transfer to 2023. Its scores must be compared with the source training-mean reference. Nonzero AUC ranks zero versus positive outcomes using predicted yield, not calibrated probabilities.

[Source scores](../../data/runs/zimbabwe_transfer_diagnosis_v1/source_metrics.csv) · [source predictions](../../data/runs/zimbabwe_transfer_diagnosis_v1/source_predictions.csv) · [source splits](../../data/runs/zimbabwe_transfer_diagnosis_v1/source_splits.csv)

| Method | n | RMSE | MAE | R² | Nonzero-ranking AUC |
|---|---:|---:|---:|---:|---:|
| `coordinates` | 3764 | 0.723288 | 0.380214 | 0.263553 | 0.855262 |
| `monthly_ridge` | 3764 | 0.719817 | 0.427076 | 0.270604 | 0.758918 |
| `monthly_tree` | 3764 | 0.738247 | 0.434176 | 0.232776 | 0.750763 |
| `presto_ridge` | 3764 | 0.728739 | 0.435658 | 0.252410 | 0.759530 |
| `seasonal_ridge` | 3764 | 0.741136 | 0.457931 | 0.226759 | 0.699490 |
| `training_mean` | 3764 | 0.843337 | 0.548777 | -0.001202 | 0.468084 |

## Additional diagnostic findings and interpretation

**Distribution shift rather than a demonstrated lack of source signal.** Naive pooling worsened target RMSE from 1.796767 to 2.270721 t/ha; the squared-bias increase accounts for 99.03% of its excess MSE by the identity MSE = squared bias + centered error variance. Adaptive pooling restores RMSE to 1.793816. Within 2024, monthly Ridge improves on its own training-mean reference (0.719817 versus 0.843337; R² 0.270604). This supports the presence of source signal without showing that it transfers. Source-versus-target classifier AUC is 0.8244 for seasonal features, 0.9956 for monthly features, 0.9998 for Presto and 0.6540 for coordinates. These distinguishability scores are not label-quality scores and do not identify a causal mechanism.

**Measurement quality sensitivity.** Among 4,290 two-cut source records, cut correlation is 0.8998 overall and 0.8681 among 2,416 positive records; 250 positive pairs have absolute cut difference divided by their mean greater than one. The quality mask requires two cuts, at least six observed months and relative cut difference ≤1. Its seasonal target RMSE (1.793812) is essentially the unfiltered adaptive result (1.793816); matched random subsets are similar. Agreement cannot detect shared errors or establish moisture equivalence, and quality filtering may change the population.

**Negative controls and limited-target checks.** All five shuffled-source seasonal runs are reported, with RMSE 1.796434–1.797000. Real adaptive source labels give 1.793816, but five shuffles do not constitute a calibrated significance test. With 25% and 50% of target-training spatial groups, adaptation changes RMSE from 1.809613 to 1.807835 and from 1.801894 to 1.800447, respectively. These are small gains under target-data subsampling, not a source-dose experiment.

**Weather and overfitting evidence.** Adding 46 weather features to merged monthly trees improves training RMSE from 1.1930 to 1.0238 while worsening held-out RMSE from 1.657757 to 1.722124. There are only 30 distinct target weather cells; 1,447/1,504 evaluation fields share a cell with target-training fields. Across those cells, 20 of the 46-weather feature pairs have |correlation| ≥0.95. Every eligible 2024 January–March temperature anomaly lies outside the target-season range, as do 83.2% of rainfall percent-of-normal values. These findings support an overfitting/distribution-shift explanation but do not show that weather observations are erroneous or establish drought causality.

**Best observed score and its limits.** Four-feature shared Ridge has the lowest target point RMSE among these releases (1.655411; R² 0.303959), but it was compared post hoc with the best imagery-only benchmark. Against merged monthly trees (1.657757; R² 0.301984), ΔRMSE is −0.002347 with spatial-group interval [−0.054835, +0.052908] and weather-cell interval [−0.059869, +0.070591]. Overall superiority is unestablished. The prespecified secondary contrast against 46-feature shared Ridge is −0.094492, spatial interval [−0.1465, −0.0477]; this supports simplification for that learner, not a general advantage of weather or pooling.

**Expanded compact-model result.** Adding the extra eligible Lacuna fields changes band preharvest RMSE from 1.750319 to 1.748027 (R² from 0.221860 to 0.223896): ΔRMSE −0.002292, interval [−0.013820, +0.007266]. Adding 2024 to the expanded preharvest model gives 1.748955 (R² 0.223072); its primary interval includes zero. The best expanded merged point score is the common-calendar band mean (1.748110; R² 0.223823), effectively tied descriptively with expanded Lacuna preharvest means. These compact summaries remain worse by point score than the richer monthly baselines.

## Evidence locations and reproducibility

- Original source-quality evidence: [quality summary](../../data/runs/zimbabwe_transfer_diagnosis_v1/quality_summary.json), [error decomposition](../../data/runs/zimbabwe_transfer_diagnosis_v1/error_decomposition.csv), [domain separability](../../data/runs/zimbabwe_transfer_diagnosis_v1/domain_separability.csv).
- Weather evidence: [training diagnostics](../../data/runs/zimbabwe_weather_compact_v1/training_outer_diagnostics.csv), [feature structure](../../data/runs/zimbabwe_weather_compact_v1/feature_structure.csv), [support diagnostic](../../data/runs/zimbabwe_weather_compact_support_v1.csv), [post-hoc candidate comparisons](../../data/runs/zimbabwe_weather_compact_candidate_v1.csv).
- Metric audit: [R² review packet](../zimbabwe/R2_AUDIT.md), [original aggregation audit](../../results/aggregation/r2_audit.json), [expanded audit](../../results/multiyear/r2_audit.json), [independent model replay](../../results/multiyear/verification.json), [independent paired intervals](../../results/multiyear/interval_verification.json).
- Reproduction: [recorded-code instructions](../zimbabwe/REPRODUCING.md). Use the historical runner for steps 9–13 and direct scripts for steps 14–15 with new output destinations. Do not overwrite frozen releases or rebuild the shared database.

All 155 score rows in the ledger were verified against saved prediction files for n, uniqueness, RMSE, MAE and R² (absolute tolerance 1e-10); all 149 target rows also have identical evaluation IDs, folds and true yields. The ledger preserves original reported scores rather than silently replacing them with newly rounded calculations. File fingerprints allow any teammate to verify which artifact supplied a number.
