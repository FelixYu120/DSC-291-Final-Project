# Zimbabwe data merging weather enrichment and evaluation

The concise [data sources and preparation section](../paper/DATA_SOURCES_AND_PREPARATION.md) describes the original **v1** experiments. The [supplementary methods](../paper/SUPPLEMENTARY_METHODS.md) retain their screening tolerances, satellite support and feature formulas. For the rule-compliant v2 analysis, use the corrections below and [the results notebook](../../notebooks/lacuna_results_consensus.ipynb), section 6.1.

## v2 correction (8 November 2026): training rows follow `include_primary`

**The v1 merged numbers on this page trained on rows the team excludes.** v1 steps 9–13 pooled all 4,332 screened
2024 rows, including the 1,874 recorded zeros that `labels_v1.include_primary` excludes. The v2 reruns
(`configs/*_v2.json`, `"training_rows": "include_primary"`) train only on `include_primary` rows: 1,880 Lacuna 2023 and
2,458 Zimbabwe 2024 rows. Evaluation fields, splits, fold 0, buffer, grids, seeds, bootstrap units and the
December–June imagery and October–June weather windows are unchanged; no survey date is an input or window anchor.
Lacuna-only arms are identical in v1 and v2. RMSE in t/ha on the same 1,504 fields:

| Weather features added | Lacuna-only trees | Merged trees, v1 | Merged trees, v2 |
|---|---:|---:|---:|
| None | 1.6594 | 1.6578 | 1.6770 |
| 46 | 1.6958 | 1.7221 | 1.7164 |
| 2 | 1.6806 | 1.6740 | 1.6607 |
| 4 | 1.6727 | 1.7029 | 1.6904 |
| 4, shared-label Ridge (Lacuna-only Ridge 1.7283) | — | 1.6554 | **1.6428** |

- Full weather, primary (merged minus Lacuna-only weather trees): v2 **+0.0206 [−0.0044, +0.0443]**
  (v1 +0.0264 [+0.0094, +0.0450]). Weather × merging interaction: v2 +0.0030 [−0.0346, +0.0390] (v1 +0.0280 [+0.0025, +0.0579]).
- Compact, primary (four-feature merged minus Lacuna-only trees): v2 **+0.0177 [−0.0095, +0.0467]** (v1 +0.0302 [−0.0009, +0.0612]).
- Two-feature merged trees versus 46-feature merged trees: v2 −0.0557 [−0.1123, −0.0009] (v1 −0.0481 [−0.0995, +0.0053]).
- Best arm overall: four-feature shared Ridge, v2 1.6428 (R² 0.315; v1 1.6554, R² 0.304). Post hoc against the best
  imagery-only arm (Lacuna-only monthly trees, 1.6594): −0.0166 [−0.0583, +0.0267]. Not an established gain.
- Overfitting signal persists: merged weather trees fit training data at RMSE 0.937 (imagery only 1.128) but score 1.715 out of fold.

Without the excluded zeros, merging hurts less, but the conclusions do not change: no merged or weather arm is
clearly better than imagery-only Lacuna trees. v2 outputs: `data/processed/zimbabwe_weather_v2/`,
`data/runs/zimbabwe_weather_v2/`, `data/runs/zimbabwe_weather_compact_v2/`; small copies and independent verification
receipts (both passed) in [`results/weather_v2/`](../../results/weather_v2/).

The rest of this page describes the **v1 runs**.

## v1 findings

**Smaller weather sets recover some lost accuracy, but they do not establish a better overall model.** All comparisons use the same 1,504 Lacuna fields and frozen spatial splits. RMSE is in t/ha; lower is better.

| Weather features added | Lacuna-only trees | Merged trees |
|---|---:|---:|
| None | 1.6594 | 1.6578 |
| 46 | 1.6958 | 1.7221 |
| 2 | 1.6806 | 1.6740 |
| 4 | 1.6727 | 1.7029 |

The **two features** are January–March rainfall relative to normal and temperature anomaly. The **four features** add the same summaries for the preceding October–December.

**Why did weather hurt?** The results support overfitting as part of the explanation. Adding all 46 weather features improved merged-tree training RMSE from **1.1930 to 1.0238**, while held-out RMSE worsened from **1.6578 to 1.7221**. There are only 30 distinct target weather profiles, with 20 highly correlated feature pairs. Weather also separates the years: all eligible 2024 temperature anomalies fall outside the 2023 January–March range. These patterns can encode location or cohort differences without learning a transferable yield response. Unit, date, join and completeness checks passed; this is not evidence that the downloaded weather is erroneous.

**Did simplification help?** Two-feature merged trees improved by 0.0481 versus 46-feature trees, but the 95% spatial-group interval includes zero: [−0.0995, +0.0053]. They still trail imagery alone. Four-feature merging worsened tree RMSE by 0.0302 relative to four-feature Lacuna-only trees; that interval also includes zero.

**A useful candidate:** four-feature shared Ridge reaches **1.6554**, versus **1.7283** for Lacuna-only Ridge with those features. Its advantage over the existing best imagery-only model is just **0.0023 t/ha**, with a 95% interval of [−0.0548, +0.0529]. Keep the imagery-only tree as the reference and retain this compact Ridge model for independent validation. This candidate comparison was examined after seeing the results.

These are exploratory, retrospective results. Reserved Lacuna fold 0 was neither fitted nor scored. Methods, provenance and supporting results follow in the appendix.

# Technical appendix

## Data and merge definition

A row is one recorded field-season, with its original source identity and yield. We append the two Zimbabwe sources vertically after giving their columns consistent meanings. We do not match a 2023 farmer to a 2024 farmer or average yields across years: the files lack a verified shared farm identifier. Spatial proximity is used to protect evaluation, not to infer identity.

The catalog has **6,598 labels**: 2,266 Lacuna and 4,332 Zimbabwe 2024. The v1 comparison kept 1,880 pure-stand, rainfed Lacuna 2023 fields plus all 4,332 source fields, the 1,874 zeros included; this broke the team rule. The v2 comparison keeps the same 1,880 Lacuna fields plus the **2,458** `include_primary` source fields. Reserve 376 target fields and exclude two source fields lacking sufficient imagery; each outer fit uses 1,128 target fields and spatially allowed source fields.

| Difference | Lacuna | Zimbabwe 2024 |
|---|---|---|
| Crop cuts | One 8 × 5 m cut | Mean of up to two 40 m² boxes |
| Yield column | `Yield(Mt/H` | `Avg_yield_mt_ha` |
| Years | 2022 and 2023; model uses 2023 | 2024 |
| Moisture basis | Unreported | Unreported |
| Management and crop dates | Available | Often unknown; photos do not establish harvest dates |

## Sources and provenance

**Lacuna:** PULA Advisors, *Enhanced agriculture datasets for remote crop monitoring, crop type mapping and yield prediction – Lacuna*, version 1.1.1, published 1 November 2023, DOI [10.5281/zenodo.10060610](https://doi.org/10.5281/zenodo.10060610). The saved provider metadata records CC BY 4.0. Inputs are `data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson` and the accompanying technical manual, with release metadata in `data/metadata/zimbabwe.json`. The manual and dry-weight arithmetic support metric tonnes/Mg per hectare; the public description's “Megatonnes” wording is inconsistent with those measurements.

**Zimbabwe 2024:** Medhanie Irgau, Harrison Li, David Lobell, Nabil Janmohamed and Karen Rieckmann, *Scalable Vision-Guided Crop Yield Estimation Dataset*, published 17 November 2025, DOI [10.5281/zenodo.17626117](https://doi.org/10.5281/zenodo.17626117), CC BY 4.0 in the saved release metadata. The input is `data/raw/vision_guided_yield_estimation/metadata.csv`; record metadata and publisher/download checksums are in `data/metadata/zenodo_17626117_record.json` and `vision_guided_yield_download_manifest.json`. This is 2024 field data released in 2025. The [associated paper](https://arxiv.org/html/2511.12999v1) explains the crop-cut/photo study. Its zone-filtered sample of 4,173 Zimbabwe fields differs from our 4,332 screened public labels. We do not reproduce its zone-level estimand or infer missing zone assignments. Photos are not predictors in this experiment.

Satellite inputs are existing Sentinel-2 L2A bands and indices from Earth Search collection `sentinel-2-c1-l2a`, stored in the pinned team database. No new imagery was downloaded. A 10 m point pixel may not represent the entire field or crop cut. Earlier Presto experiments use frozen embeddings with different window/masking conventions.

**Weather:** NASA Langley Research Center POWER, funded through NASA's Earth Science Division; Monthly and Annual Point API **v2.10.0**, accessed **7 November 2026 UTC**, returning **MERRA2** and **LST** in every saved response. POWER distributes meteorological estimates on the source grid; the values are regional reanalysis estimates, not farm instruments. Source documentation: [monthly API](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/), [meteorological product and resolution](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/), and [citation guidance](https://power.larc.nasa.gov/docs/referencing/).

All source and derived-file SHA-256 hashes are recorded in the release manifests. Retain the original dataset authors, CC BY 4.0 notices and NASA POWER attribution when sharing derivatives.

## Cleaning and physical conversions

Reconcile raw IDs, coordinates and outcomes with frozen labels. Check unique source IDs, usable cuts, nonnegative dry weights, dry ≤ wet weight where both are available, conversion consistency and a coarse Zimbabwe coordinate envelope. Lacuna's raw yield screen is 0–30 t/ha; its original primary-model policy additionally excludes yields above 15 t/ha. The 2024 yield screen is 0–15 t/ha. These are validation screens, not proof of field-level accuracy.

Three Lacuna records imply dry kg × 0.5 instead of × 0.25 for 40 m². Exclude them; unknown area/weight errors cannot be repaired by guessing. Of the remaining 2,266 labels, 169 are from 2022 and 2,097 from 2023. Sequentially remove 212 intercropped and five irrigated 2023 records to obtain 1,880 primary fields. Keep 28 primary zero yields; retain nearby coordinates in shared spatial groups. The 2022 records remain catalog-only.

The 5,055 raw maize records include **723 missing labels**, which are excluded without imputation: 590 comments indicate photos only and 133 indicate wet weight without dry weight. The 4,332 retained records have reported average yields. They include **1,874 recorded zeros** and **42 single-cut records**. Recorded zero and missing measurement are distinct states. Neither a late photo date nor drought alone proves whether an individual zero is correct. `labels_v1` excludes the zeros from training (`zimbabwe_2024_zero_likely_not_measured`); v2 training pools follow that rule, v1 pools did not.

Box conversion and average comparisons use an absolute tolerance of 0.000001 t/ha. The independently screened IDs, coordinates and outcomes must reconcile with the frozen screened labels. All row-level reasons remain available in `source_2024_audit.csv`.

For reported dry mass and an area in square metres:

```text
yield_kg_ha = w × 10,000 / 40 = 250 × w
yield_t_ha  = yield_kg_ha / 1,000 = 0.25 × w
```

Both sources already report area-normalized yields. For 2024, verify each box's numerical consistency with the 40 m² conversion, then average available box yields. The released CSV has no cut-area field and the associated paper's methods section does not state 40 m², so this checks arithmetic rather than independently establishing physical sampled area. Do not divide the already averaged field yield by two. Models and metrics use t/ha; storage also preserves kg/ha. Lacuna's raw-unit provisional flag remains visible even though the arithmetic supports the chosen interpretation.

A physical moisture correction would require measured moisture values: `Y_target = Y_observed × (100 − m_observed)/(100 − m_target)`. Those values are absent, so no moisture conversion is applied. Grain/cob basis, drying completeness and sampling variability are not solved by changing units. Two cuts may reduce sampling noise, but the available evidence does not justify a universal precision multiplier. Statistical adaptation addresses some differences in distributions; it does not certify measurement equivalence.

## Season alignment and joins

| Label year | Common weather season | Common imagery window | Role |
|---|---|---|---|
| 2022 | October 2021–June 2022 | Not used in comparison | Catalog only |
| 2023 | October 2022–June 2023 | December 2022–June 2023 | Lacuna target |
| 2024 | October 2023–June 2024 | December 2023–June 2024 | Auxiliary source |

Label IDs are source-prefixed and unique. Labels and per-field features join one-to-one on `obs_id`; satellite monthly tables join on `(obs_id, month)`. Source rows append to target rows. Weather joins many-to-one on `(weather_grid_id, season_year)` or `(weather_grid_id, month)`. Repeated weather across fields is expected and must not multiply label rows. Assertions enforce key uniqueness, row counts and unchanged original labels after enrichment.

Use December–June imagery because October/November 2022 is absent from the pinned collection. Require at least four observed months and finite seasonal summaries: 1,880 targets and 4,330 sources pass. Keep missing monthly imagery values for training-fold preprocessing.

This is **retrospective estimation**. Lacuna's audit finds post-harvest scenes for 1,810 primary fields. Full-season imagery/weather and later-year training data would not have been available for a real-time 2023 forecast. Forecasting needs a separately defined cutoff and evaluation.

## Weather extraction and features

Request `PRECTOTCORR,T2M`, community `AG`, years 1991–2024 from `https://power.larc.nasa.gov/api/temporal/monthly/point`. Cache exact JSON and request metadata. Validate all 408 months per cell, units, dates, finite values and broad physical bounds; ignore annual `YYYY13` entries. All downloads were complete.

Map each WGS84 field point to the nearest native grid centre using latitude spacing **0.5°** and longitude spacing **0.625°**, with origin −90°, −180°. Round half-cell ties toward the increasing index. This is explicit nearest-centre assignment, without interpolation. Across the full catalog it produces **97 grid cells**. Median field-to-centre distance is **22.98 km**, maximum **42.92 km**. The cell dimensions are roughly 50–65 km across Zimbabwe.

Raw files are under `data/raw/nasa_power_zimbabwe_v1/<grid_id>/`. The ledger records URLs, coordinates, parameters, units, API/source/time convention, retrieval timestamps, HTTP metadata and SHA-256 hashes. All 97 responses were retrieved on 7 November 2026, 10:23:10–10:23:22 UTC. Reuse snapshots because services may revise historical estimates.

`PRECTOTCORR` is the monthly mean daily corrected precipitation rate, in **mm/day**. Multiply by actual calendar days to obtain the month's rainfall in **mm**, including 29 days for February 2024. `T2M` is monthly mean air temperature at 2 m, in **°C**. Do not sum temperatures or treat rainfall rate as already being monthly depth.

Calculate cell/calendar-month normals from **1991–2020**, independent of yield and evaluation-year weather. Temperature anomaly is observed monthly temperature minus its historical mean. Monthly rainfall z-score uses historical monthly amount and sample standard deviation; these z-scores appear only in the original large feature set.

Seasonal rainfall percent of normal is `100 × sum(actual monthly amounts)/sum(normal daily rain rate × actual month length)`. This denominator prevents leap-year duration alone from creating a seasonal deficit. Seasonal mean temperatures and temperature anomalies are weighted by days in each month.

| Set | Weather variables added to the same 122 imagery predictors |
|---|---|
| Original 46 | Nine months × rainfall amount, temperature, rainfall z-score and temperature anomaly; ten seasonal aggregates |
| Compact 2 | January–March rainfall % normal and temperature anomaly |
| Compact 4 | Compact 2 plus the same two summaries for preceding October–December |

The two compact definitions were fixed before their model results. October–December summaries are derived from the existing weather snapshots, using the preceding calendar year. No feature was selected by its correlation with yield. Four-variable reduction also changes the seasonal encoding, so it is not a pure feature-count experiment.

The original enrichment covers all 6,598 labels, 59,382 field-month rows, 39,576 historical cell-month rows and 1,164 cell/month normals. Compact feature files cover the same 6,212 comparison candidates; eligibility and fold flags must still be applied.

Weather provides monthly regional context. We do not derive consecutive dry days, heat-wave duration, hot-day counts, soil moisture or individual crop-stage stress from monthly averages. Those would require additional inputs and a new feature definition.

For descriptive drought context, average both seasons over the **same 97 cells**:

| Season | October–March rain mm | January–March rain mm | January–March rain % normal | January–March temperature anomaly °C |
|---|---:|---:|---:|---:|
| 2022/23 | 729.93 | 455.64 | 117.61 | −0.62 |
| 2023/24 | 590.18 | 259.67 | 63.70 | +1.35 |

The sampled cells were drier and hotter in January–March 2024. This confirms that the added weather captures a regional contrast; it does not establish how much of the yield difference was caused by drought.

## Predictors and training transforms

The unchanged imagery matrix has **122 columns**: ten seasonal index summaries, 105 band/index-by-month values, and seven missing-scene flags. Compact models therefore have 124 or 126 predictors; the original weather model has 168.

Within each inner/outer fit, derive imagery medians, 1st/99th percentile clipping, means and scales from target training fields only. Empty columns become zero and near-zero scales become one. Weather receives target-training imputation/scaling without percentile clipping, preserving drought extremes. Apply frozen transforms to source and held-out fields. IDs, coordinates, folds, yield components, audit flags and future outcomes are not ordinary predictors; merged trees alone receive an explicit source indicator.

## Models and transfer methods

Earlier experiments tested target-only Ridge; naive pooling; a source indicator; target-derived source reweighting; cohort outcome calibration; shared/specific slopes; within-cohort centering; and adaptive Ridge. Follow-up experiments compared monthly imagery, Presto, boosted trees, source sample sizes, quality masks, density weights and shuffled-source controls. Naive pooling suffered strong downward bias; adaptation removed much of that offset but gave little reliable gain.

Adaptive Ridge centers predictors and standardizes outcomes separately within training cohorts. It uses target `[x,x,0]/sqrt(2)` and source `[x,0,x]/sqrt(2)` to learn shared and cohort-specific slopes, then restores target yield units. This is statistical adjustment, not a moisture correction. The feature construction relates to [Daumé 2007](https://aclanthology.org/P07-1033/).

For weighted methods, let the total target weight be `n_target` and source ratio be `r`. Normalize source weights so they sum to `r × n_target`; every target row has weight one. Candidate ratios are **0, 0.1, 0.3 and 1**. This prevents the larger 2024 sample from dominating simply by row count. Ratio zero recovers target-only fitting and must be reported as no source contribution.

A source-quality experiment required two cuts, at least six observed imagery months and relative cut disagreement ≤1; both-zero pairs receive disagreement zero. It retained 4,027 labels in v1 (v2: 2,157 of the 2,458 `include_primary` rows). Random controls matched size and zero/positive composition (v2: size only, as there are no zeros). Filtering did not establish a gain in either run.

Each compact set tests five arms: target Ridge, adaptive Ridge, shared-label weighted Ridge, target boosted trees, and weighted merged boosted trees. Shared Ridge keeps physical yields with shared slopes; trees receive a cohort indicator. All select source weights using target inner validation. Ratio zero is permitted. Earlier weather experiments also tested 14 NDVI × weather-anomaly interactions and a weather-only model.

## Splits, tuning and uncertainty

Keep the original `s1_cc2km` connected-component groups unchanged. Outer development folds are 1–4; fold 0 is excluded from every new fit and score. Fold 0 had historical use, so reserving it here does not make it newly blind.

Each outer evaluation fold has 376 target fields; the other three provide 1,128 training fields. Three grouped inner folds select model parameters using only target inner-validation squared errors. Every arm produces predictions for exactly the same **1,504 target fields**. Source training points are removed if they lie within 2 km of reserved target fold 0, the current outer evaluation fields or the current inner validation fields. Source selection uses coordinates, not validation yields. Exact membership and distance-permission files are reused byte-for-byte in the weather comparison.

Tune Ridge alpha over 0.01, 0.1, 1, 10, 100, 1,000; source ratio over 0, 0.1, 0.3, 1; tree maximum leaves over 7, 15. Trees use 120 iterations, learning rate 0.05, minimum leaf size 20, L2=1 and no early stopping. Choose pooled inner-validation MSE; stable grid order breaks ties. Seed: 20261108.

Report target RMSE, MAE, bias, R² and rank correlation. Bootstrap paired errors with 2,000 identical draws, first over 232 original spatial groups and additionally over 30 weather cells. Intervals condition on fitted predictions and do not refit models. They are exploratory and not adjusted for multiple comparisons. A weather-cell bootstrap changes uncertainty, not the train/test split.

In the weather comparison, **1,447 of 1,504 outer evaluation fields (96.2%)** share a weather cell with target-training fields. Across the development sample there are 232 evaluation groups but only 30 target weather cells. The remaining 57 fields lie in cells absent from that outer target-training set. These counts are reported per outer and inner fold in `weather_cell_overlap.csv`.

All experiments reuse a previously inspected development population. They are not a new blind test or a test of wholly unseen weather regions. Shared external weather is not a target-label leak, but can act as a location proxy. Year, provider, management and measurement differences remain confounded.

## Full compact results and diagnostics

The compact protocol specified four-feature merged trees versus four-feature target trees as primary. The primary difference is **+0.0302 t/ha**, 95% spatial-group interval **[−0.0009, +0.0612]**; weather-cell interval **[−0.0012, +0.0656]**. Positive means merging worsened RMSE. The change in merging benefit relative to imagery-only trees is +0.0318, interval [−0.0023, +0.0669]. Neither establishes a benefit.

| Learner | No weather | 46 features | 2 features | 4 features |
|---|---:|---:|---:|---:|
| Target Ridge | 1.6926 | 1.7443 | 1.6994 | 1.7283 |
| Adaptive merged Ridge | 1.6892 | 1.7422 | 1.6960 | 1.7248 |
| Shared merged Ridge | Not run | 1.7499 | 1.6783 | 1.6554 |
| Target trees | 1.6594 | 1.6958 | 1.6806 | 1.6727 |
| Merged trees | 1.6578 | 1.7221 | 1.6740 | 1.7029 |

This table contains all 19 compared arms. All values are pooled held-out RMSE on identical fields. MAE, bias, R² and rank correlation are in `metrics.csv`; fold-level results are in `fold_metrics.csv`. The nine historical controls are unchanged saved predictions.

Shared Ridge with four features improves on shared Ridge with 46 features by −0.0945 t/ha, spatial-group interval [−0.1465, −0.0477]; the weather-cell interval is [−0.1637, −0.0347]. Adding 2024 to the four-feature Ridge model improves RMSE by −0.0729, spatial-group interval [−0.1181, −0.0361], weather-cell interval [−0.1287, −0.0348]. These prespecified secondary contrasts support simplification for this learner, subject to multiple comparisons and prior reuse of the development sample.

Post-hoc checks compare that best observed compact arm with existing benchmarks. Against imagery-only merged trees, the difference is −0.0023, spatial-group interval [−0.0548, +0.0529] and weather-cell interval [−0.0599, +0.0706]. Against imagery-only target Ridge, the difference is −0.0372; its spatial-group interval excludes zero but its weather-cell interval [−0.0708, +0.0032] does not. These checks do not establish overall superiority.

Two-feature merged trees versus imagery-only merged trees: +0.0163, spatial-group interval [−0.0127, +0.0445]. Versus 46-feature merged trees: −0.0481, weather-cell interval [−0.1126, +0.0178]. Point improvements from simplification should therefore not be reported as certain tree-model gains.

| Merged-tree inputs | Training RMSE | Held-out RMSE | Gap |
|---|---:|---:|---:|
| Imagery only | 1.1930 | 1.6578 | 0.4648 |
| +46 weather | 1.0238 | 1.7221 | 0.6984 |
| +2 weather | 0.9926 | 1.6740 | 0.6815 |
| +4 weather | 0.9152 | 1.7029 | 0.7877 |

| Merged model | Source total-weight ratios, folds 1–4 |
|---|---|
| 46-feature trees | 1, 0.1, 0, 0 |
| Two-feature trees | 1, 0.3, 0.1, 0.1 |
| Four-feature trees | 0.1, 1, 1, 0.3 |
| Four-feature shared Ridge | 1, 0.3, 1, 1 |

Available source counts are 4,226, 4,191, 4,194 and 4,213, respectively. Both compact tree variants and four-feature shared Ridge use source data in every outer fit. Zero weight in older controls means target-only fitting for that fold.

Training RMSE is pooled across the four fitted models; training fields recur across fits. These are descriptive fit gaps, not independent error estimates or a formal causal test. Selected leaf counts and source weights also differ. The four-feature merged trees fit training data especially closely while generalizing worse than the two-feature version. Fewer columns alone is not a guarantee against overfitting.

Across 30 unique target weather cells, the 46-column matrix has 20 pairs with absolute correlation ≥0.95. The compact sets have none. The centered numerical ranks are 29, 2 and 4; 29 is also the maximum possible rank for any centered 30-row matrix, so that rank alone is not proof of overfitting. Both variable count and seasonal encoding changed.

The support diagnostic compares eligible 2024 fields with the full 2023 development range, without outcomes or filtering. January–March temperature anomalies are −1.21 to −0.01°C in Lacuna and +0.08 to +2.37°C in 2024: **4,330/4,330 sources lie outside the target range**. Rainfall lies outside that range for **3,601/4,330 (83.2%)**. Weather can therefore encode cohort/year differences; these data alone cannot isolate a common causal weather–yield relationship.

## Interpretation limits

The merged data is usable for controlled auxiliary-training experiments, with explicit provenance and separate domain labels. It is not evidence that both protocols measure an identical latent outcome. Unknown moisture/grain basis, unknown 2024 management and crop dates, point-to-field mismatch, regional weather resolution, single-versus-double crop cuts, and year/provider confounding remain. Weather can explain part of a predictive relationship without separating these causes.

A stronger causal or deployment claim needs independent seasons and farms, a prediction-time cutoff, and preferably finer daily weather and verified crop dates. Do not claim that compact feature success or failure alone proves weather quality, drought causality, or measurement equivalence.

## Files and reproduction

After integrating the earlier quality-review work into main, shared validation modules have stronger checks and new source hashes.
Use the [recorded-code runner](REPRODUCING.md) for the published experiments; their original outputs and manifests remain unchanged.

| Location | Contents |
|---|---|
| `data/processed/zimbabwe_midterm_v1/` | Lacuna audit, cleaned data and original splits |
| `data/runs/zimbabwe_merge_v1/` | Catalog, 2024 audit, comparison candidates and frozen permissions |
| `data/runs/zimbabwe_transfer_diagnosis_v1/` | Original features, source-quality and representation experiments |
| `data/raw/nasa_power_zimbabwe_v1/` | Exact API snapshots and request records |
| `data/processed/zimbabwe_weather_v1/` | All enriched labels, monthly weather, history, normals, dictionary and provenance |
| `data/runs/zimbabwe_weather_v1/` | Original 46-feature/interaction models and immutable controls |
| `data/runs/zimbabwe_weather_compact_v1/` | Two/four-feature matrices, compact weather CSV/Parquet, 19-arm predictions/metrics, tuning, fit accounting, diagnostics and paired intervals |
| `data/runs/zimbabwe_merge_v2/`, `zimbabwe_transfer_diagnosis_v2/`, `zimbabwe_weather_v2/`, `zimbabwe_weather_compact_v2/` | v2 reruns with `include_primary` training rows (git-ignored; same file layout as v1) |
| `data/processed/zimbabwe_weather_v2/` | Weather enrichment of the v2 catalog, built offline from the same raw snapshots; weather values equal v1 |
| `results/merge_v2/`, `results/weather_v2/` | Small v2 summaries, manifests and verification receipts |

v2 commands, in order: `python scripts/step9_compare_zimbabwe_merge.py --config configs/zimbabwe_merge_v2.json`, then step 10
with `configs/zimbabwe_transfer_diagnosis_v2.json`, steps 11 and 12 with `configs/zimbabwe_weather_v2.json`, and step 13
with `configs/zimbabwe_weather_compact_v2.json`. The verifiers and `compare_compact_candidate.py` take the same `--config`.

For a GRU or another sequence model, explicitly order weather months October, November, December, January through June, and imagery months December, January through June. Lexical column order starts with January and would misorder the season. Join monthly weather by `obs_id` and actual `month`; retain imagery masks instead of treating a missing scene as zero reflectance. The weather extension supplies these data but does not train a GRU.

Pipeline: raw audit → harmonized labels and eligibility → frozen imagery/splits → weather snapshots and unit/season/grid conversion → feature tables → training-only transforms → inner tuning → outer predictions → paired metrics. Release manifests pin all inputs and outputs. Changed code/data requires a new output directory; never overwrite old results.

```bash
python scripts/verification/reproduce_zimbabwe.py weather  # offline; new output destination
python scripts/verification/reproduce_zimbabwe.py weather-models
python scripts/verification/reproduce_zimbabwe.py compact
python scripts/verification/reproduce_zimbabwe.py verify-weather
python scripts/verification/reproduce_zimbabwe.py verify-compact
python scripts/verification/reproduce_zimbabwe.py candidate  # exploratory benchmark check; no refitting
```

To rebuild earlier stages, run step 8, then step 9, then step 10 using their pinned inputs. **Do not run step 6 on the team database:** it would remove the existing Presto rows. The required database SHA-256 is `e192b9d6021fdae020f9b08123b98648dc4b5274989635927c709a5607cdcd60`; frozen label SHA-256 is `49aae383c4489aa98e9e7fe8c31cda6bf1cd752adc8e9540cffdc147a5e0ef92`.

Validation: **178 tests passed; two Windows-only checks were skipped**. The independent compact checker reconstructed 12,424 early-season weather values, checked all 19 arms and 40 parameter choices, verified 160 fit-accounting records, replayed all 52 paired intervals plus both interaction intervals, and reproduced a selected merged tree. All 16 historical tree replays matched. Original split files, nine saved controls, database and release hashes were unchanged. Earlier weather validation reconstructed every one of the 303,508 original weather values and checked raw API values and spatial permissions.
