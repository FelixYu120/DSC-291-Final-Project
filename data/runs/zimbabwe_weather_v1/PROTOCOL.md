# Zimbabwe weather augmentation and transfer comparison

Felix requested rainfall and temperature, complete source provenance, enrichment of the merged data, the same-split
Lacuna-only versus pooled comparison, and one comprehensive methods Page. This protocol is specified before scoring
weather models. The previous results informed this extension, so it remains exploratory.

## Source and matching

Use NASA POWER Monthly Point API, community AG, parameters PRECTOTCORR (corrected precipitation, mm/day) and T2M
(2 m air temperature, Celsius). These are MERRA-2 grid estimates, not field rain gauges or thermometers. Fetch
1991–2024 for each distinct grid centre needed by the full 6,598-label catalog. Retain exact response bytes, request URL,
UTC retrieval time, headers, parameter units, API version, source identifier, source time standard, fill value, response
messages and SHA-256. Cache requests and fail rather than silently substituting missing values.

Assign each original WGS84 point to the nearest native centre on a 0.5 degree latitude by 0.625 degree longitude grid
(origin −90, −180, equivalently integer multiples of each spacing here; half-way ties round toward increasing index).
Download only coarse centres, not farm identifiers or yields. Preserve actual field coordinates, grid indices/centre,
grid ID, and great-circle distance. Weather is constant within a cell/month. This mapping is explicit nearest-centre
assignment, not an interpolation or a claim of field-level measurement.

Select October of year−1 through June of the label year for each observation, consistently for 2022, 2023 and 2024.
This is a common seasonal convention, not verified individual crop dates for 2024. Actual source monthly values use
NASA's returned LST convention. Discard annual month-13 summaries. Monthly rain amount = reported mean daily rate ×
actual days in that calendar month, accounting for leap years. Monthly temperature is already a monthly mean.
Do not derive dry-spell lengths or hot-day counts from monthly averages.

Use each cell's 1991–2020 calendar-month history for fixed climate normals: rain mean/standard deviation and temperature
mean. Rain z-score = (actual monthly total−normal mean)/normal standard deviation. Temperature anomaly = actual−normal
mean in degrees C. A zero normal rain variance requires zero difference or an explicit failure; do not manufacture a
finite anomaly for an undefined case. These external historical normals use no yield data or post-2020 observations.

## Predictors and exports

For each of nine months export rain total, temperature mean, rainfall z-score and temperature anomaly (36 predictors).
Add rain totals and percent-of-normal rainfall for October–June, October–March and January–March, and day-weighted
mean temperature/anomaly for October–June and January–March (10 predictors). Percent-of-normal uses the expected
rain rate times the actual current calendar-month day count, so leap-year duration alone does not create a deficit.
Monthly rain z-scores compare calendar-month amounts with the 30 actual historical monthly totals.

Join these 46 weather predictors to all 6,598 screened labels. Also export long field-month and cell-month tables,
the historical grid series, climate normals, grid mapping, a weather dictionary, retrieval ledger and enriched
comparison tables for the existing 6,212 candidates. Keep the two original imagery failures and 376 reserved target
rows flagged; exporting them does not permit fitting/scoring them.

For modeling, augment the previous 122 monthly imagery predictors with 46 weather predictors. A secondary linear
interaction family adds NDVI × rain z-score and NDVI × temperature anomaly for each December–June month (14 terms).
No target-derived drought category or post-outcome variable is created. Report matched-cell 2023 versus 2024 weather
contrasts over the same footprint, separately from observation-weighted cohort summaries, which confound locations.

## Evaluation and preprocessing

Reuse every outer/inner target membership and source spatial permission from the original merge experiment. Every
target model predicts the same 1,504 Lacuna 2023 development fields, with 1,128 target rows per outer fit. Fold 0 is
never fit/scored; 2024 points within 2 km of protected target fields remain excluded in every inner/outer fit.

Retain the previous training-only 1st/99th percentile clipping, imputation and scaling for imagery. Weather and its
interaction terms are imputed/scaled using target-training statistics but **not percentile-clipped**: authentic 2024
drought conditions outside the 2023 range must remain distinguishable. Validate physical units/ranges before fitting.
No year, grid ID, source row, harvest measurement or yield-derived feature is a predictor. Pooled trees explicitly
receive a source indicator; shared-label Ridge deliberately does not.

Tune on pooled inner target-validation squared errors only, with the same alpha/source-weight/leaf-count grids and
tree settings as the previous comparison. All predictions are clipped nonnegative. Source weight zero is a permitted
target-only fallback and is reported as no source use.

Arms: weather-only target Ridge as a diagnostic; imagery+weather target Ridge, cohort-adaptive Ridge, shared-label
weighted Ridge, target boosted trees and pooled boosted trees; imagery+weather+interactions target Ridge, adaptive Ridge
and shared-label weighted Ridge. Shared-label Ridge tests whether physical weather predictors can explain some source
level differences without imposing separate standardized target scales. It does not assume those differences were
entirely caused by weather. All source weights are normalized relative to target total weight.

Use hash-verified saved no-weather predictions for the matching monthly Ridge/adaptive/tree arms, keeping their exact
already-tuned models and splits. The primary comparison is pooled versus target-only **monthly trees with weather**.
Also pre-specify the transfer-benefit interaction:

`(RMSE pooled_weather − RMSE target_weather) − (RMSE pooled_no_weather − RMSE target_no_weather)`.

Negative values mean weather increased the benefit of merging. This separates a general weather improvement from
making 2024 more useful. Report both weather changes within each training population, all model arms, paired group
bootstrap intervals (2,000 draws), fold scores, tuning choices and actual source counts. Secondary intervals are
exploratory and not adjusted for multiple comparisons. Preserve group IDs as strings for seeded bootstrap replay.

## What the comparison can establish

Weather cells are much larger than 2 km; target training/evaluation fields can share weather cells under the required
unchanged splits. Report that overlap explicitly. This is prediction at new spatial groups within sampled regions,
not an independent weather-cell/region test. The shared meteorological predictor is not a label leak, but can act as a
location proxy. Gains do not isolate a causal drought effect, and an absence of gains does not prove weather is irrelevant.
Full-season retrospective inputs, coarse reanalysis, unknown 2024 crop dates/management and uncertain moisture basis
remain limitations. A fresh future season and better local measurements would be needed for stronger transfer claims.

Sources: [POWER monthly API](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/),
[POWER meteorological source and validation](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/),
[POWER data services and native resolution](https://power.larc.nasa.gov/docs/services/).
