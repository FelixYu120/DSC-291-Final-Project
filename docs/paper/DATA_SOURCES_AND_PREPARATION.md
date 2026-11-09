# Data sources and preparation for Zimbabwe v1

## Yield data and cleaning

For our original v1 experiments (7 November 2026), we brought together crop-cut yields, satellite measurements and NASA weather data to estimate maize yield in Zimbabwe. Each row represented one recorded field in one growing season. The yield sources were PULA Advisors' Lacuna release v1.1.1 for 2022–2023 [1] and the Zimbabwe 2024 portion of the Scalable Vision-Guided Crop Yield Estimation Dataset [2]. We added a source prefix to each record ID so the two datasets could be combined without confusing their records. Nearby coordinates were not assumed to identify the same farm.

We checked IDs, coordinates, yield ranges and whether crop-cut weights agreed with reported yields. Lacuna's initial screen allowed 0–30 t/ha; the primary models and 2024 source used a 15 t/ha upper limit. We removed three inconsistent Lacuna records and 723 missing 2024 yields. This left 6,598 records: 169 from Lacuna 2022, 2,097 from Lacuna 2023 and 4,332 from Zimbabwe 2024. The v1 analysis kept recorded zeros, including 1,874 in 2024. The main target dataset contained 1,880 rainfed, sole-cropped Lacuna 2023 fields; 217 other screened 2023 records were considered in expanded-training experiments.

We used tonnes per hectare throughout. For Lacuna's documented 40 m² cut, 1 kg of dry mass represents 0.25 t/ha. The 2024 values followed the same arithmetic, although its physical cut area was not independently documented. We checked the reported field average against available cuts and did not divide an already averaged yield again. Moisture contents were unavailable, so we could not adjust both sources to a common moisture basis. We kept source and measurement flags to make this uncertainty traceable.

## Satellite data and seasonal summaries

We used Sentinel-2 Collection 1 Level-2A reflectance from Earth Search [3]. Ten bands were sampled on a 10 m grid, with their scale and offset applied once. One acceptable scene was kept per field-month, allowing scene classes 4–6. Each Zimbabwe observation represented one valid grid cell at the recorded point, not a whole-field average. We calculated five vegetation-index features from the monthly bands before summarizing them over time. The archived MTCI-labelled ratio uses B08 instead of B06 and is not standard Sentinel-2 MTCI.

Both sources used a December–June window relative to harvest year. Aggregation comparisons required at least four observed full-season months and complete summary features. All 169 Lacuna 2022 records had only one or two months in the retained collection, so they did not enter the models; two 2024 records also failed. These aggregation models used available observations without filling missing predictors. Earlier monthly models filled gaps using training-set medians and included missing-scene indicators.

We compared seasonal mean (V0), preharvest mean (V1), seasonal maximum (V2), and separate median and half-sample modal estimates (V3); V3 mean equals V0. Within December–June, Lacuna V1 started at the later of December 1 and recorded planting, and stopped before recorded harvest. Because 2024 crop dates were missing, we used December–March as a calendar proxy [4], also testing this window for both sources. Bands and indices were compared separately.

## NASA rainfall and temperature data

We added weather so the models could use seasonal rainfall and temperature differences that satellite summaries might miss. NASA Langley POWER supplied monthly MERRA2 reanalysis estimates for 1991–2024 [5]: corrected precipitation rate (PRECTOTCORR, mm/day) and air temperature at 2 m (T2M, °C). Using latitude and longitude, we matched each field to the nearest 0.5° latitude × 0.625° longitude grid centre. The full catalog covered 97 weather cells.

We multiplied each monthly rainfall rate by the actual number of days in that month, including leap days, to obtain rainfall totals in millimetres. For each cell and calendar month, we calculated 1991–2020 reference averages. These let us express rainfall as a percentage of normal and temperature as degrees above or below normal; the full feature set also included standardized rainfall anomalies. We summed rainfall across seasonal windows and weighted temperature averages by month length. Seasonal rainfall percentages also adjusted the reference total for actual month lengths.

Weather covered October before harvest year through June. The full set had 46 monthly and seasonal features. A smaller set used January–March rainfall percent of normal and temperature anomaly; a four-feature version added the same measures for October–December. We joined these features to fields by weather cell and harvest season. Several fields therefore shared weather values: these are regional estimates, not field weather-station measurements or daily dry-spell records.

## Preparing the final model inputs

We joined yield and satellite tables by record ID, then checked row counts, unique keys and unchanged yields. To reduce overlap between nearby training and evaluation fields, we grouped the 1,880 primary fields using 2 km spatial connectivity. We set aside historical fold 0 (376 fields) and compared models on the same remaining 1,504 fields across four outer folds, with three inner group-based folds for tuning. Extra training records had to be at least 2 km from reserved and evaluation fields, including inner-validation fields during tuning. These reused development folds were not an untouched blind test.

Within each fit, we estimated gap filling where needed, imagery clipping thresholds and feature scaling from permitted Lacuna training data only. Weather extremes were not percentile-clipped. After setting negative predictions to zero, we pooled held-out predictions to calculate RMSE (t/ha) and R². We saved source responses, exclusions, features, splits and checksums for reproducibility [6]; implementation details are in the supplement. Unknown moisture, point sampling, coarse weather and provider/year differences limit interpretation. Because some inputs come after harvest or from 2024, this is retrospective yield estimation, not a test of real-time 2023 forecasting.

## References

[1] PULA Advisors. 2023. Lacuna enhanced agriculture datasets, v1.1.1. Zenodo. [doi:10.5281/zenodo.10060610](https://doi.org/10.5281/zenodo.10060610).

[2] Irgau, M., et al. 2025. Scalable Vision-Guided Crop Yield Estimation Dataset. Zenodo. [doi:10.5281/zenodo.17626117](https://doi.org/10.5281/zenodo.17626117).

[3] Copernicus Sentinel-2, processed by ESA. 2021. MSI Level-2A BOA Reflectance, Collection 1. [doi:10.5270/S2_-znk9xsj](https://doi.org/10.5270/S2_-znk9xsj); [Earth Search collection](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a).

[4] FEWS NET. 2023. Zimbabwe Food Security Outlook, February–September 2023. Seasonal calendar, p. 4. [Report](https://fews.net/sites/default/files/documents/reports/ZW_February_to_September_2023_FSO_Final_jh.pdf).

[5] NASA Langley Research Center POWER. [Monthly and Annual API](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/), v2.10.0; accessed 7 November 2026 UTC. Funded through NASA's Earth Science Division.

[6] DSC 291 project team. 2026. Zimbabwe maize-yield data and experiments. [Analysis snapshot a8f31fb](https://github.com/FelixYu120/DSC-291-Final-Project/tree/a8f31fb).
