# Data sources and preparation for Zimbabwe v1

## Yield data and harmonization

The original v1 experiments (7 November 2026) combined crop-cut observations, satellite reflectance and gridded weather to estimate maize yield retrospectively in Zimbabwe. The observational unit was a provider-recorded field-season. Yield data came from the PULA Advisors Lacuna release v1.1.1, covering 2022–2023 [1], and the Zimbabwe 2024 subset of the Scalable Vision-Guided Crop Yield Estimation Dataset [2]. Records were concatenated using source-prefixed identifiers, retaining provider and harvest year; proximity alone was not treated as evidence of a shared farm.

Preparation checked identifiers, coordinates, nonnegative yields and crop-cut arithmetic. Lacuna's initial yield screen was 0–30 t ha⁻¹; the original primary-model population and 2024 source used a 15 t ha⁻¹ upper limit. Three inconsistent Lacuna records and 723 unmeasured 2024 yields were excluded. The screened catalog contained 6,598 observations: 169 Lacuna 2022, 2,097 Lacuna 2023 and 4,332 Zimbabwe 2024. Recorded zeros were retained, including 1,874 in 2024. Restricting Lacuna 2023 to rainfed, sole-cropped maize produced 1,880 primary observations; 217 additional records were considered in expanded-training experiments.

Outcomes were expressed in tonnes per hectare. Lacuna's documented 40 m² cut implies yield equal to 0.25 times dry mass in kilograms. Reported 2024 per-cut yields followed the same arithmetic, but the physical cut area was not independently documented. Available cut yields were checked against the reported average without dividing an already averaged outcome again. Neither source reported the moisture percentages needed for moisture-basis correction. Provider-specific measurement flags were therefore retained; statistical source adjustment did not establish physical equivalence.

## Satellite features and seasonal coverage

Sentinel-2 Collection 1 Level-2A reflectance was obtained through Earth Search [3]. Ten bands were sampled on a 10 m grid, with radiometric scale and offset applied once. Each field-month retained one acceptable acquisition; scene-classification codes 4, 5 and 6 were allowed. All Zimbabwe geometries were points, and each accepted observation contained one valid grid cell, rather than a whole-field average. Monthly bands and five vegetation-index features were retained; the archived MTCI-labelled feature uses B08 instead of B06 and is not standard Sentinel-2 MTCI.

The common window was December–June relative to harvest year. Aggregation comparisons required at least four observed full-season months and finite predictors across all variants. All 169 Lacuna 2022 records had only one or two months in the retained collection and were excluded from modeling; two 2024 records also failed eligibility. The latest aggregation models did not impute missing imagery predictors. Earlier monthly-sequence models used training-fold median imputation and missing-scene indicators.

We compared full-season mean (V0), preharvest mean (V1), seasonal maximum (V2), and separate median and half-sample modal estimates (V3); V3 mean equals V0. Within December–June, Lacuna V1 retained observations from the later of December 1 and recorded planting until, but excluding, recorded harvest. Missing 2024 crop dates required a December–March proxy, informed by the typical maize calendar [4]; a control used this window for both sources. Band and index feature families were evaluated separately.

## Weather enrichment

Monthly precipitation rate and 2 m temperature were obtained from NASA POWER's MERRA2-based API for 1991–2024 [5]. Fields were matched to the nearest 0.5° × 0.625° grid centre. Precipitation rates were multiplied by actual month lengths; temperature summaries were weighted by days. Cell-specific 1991–2020 normals supported rainfall anomalies, percentages of normal and temperature anomalies. October–June weather produced 46 predictors; compact alternatives used January–March rainfall percent of normal and temperature anomaly, with two additional October–December variables in the four-feature version. These coarse monthly estimates describe regional conditions, not field-level weather or daily extremes.

## Spatial evaluation and reproducibility

The 1,880 primary observations were grouped by 2 km spatial connectivity and assigned to five balanced folds. Current comparisons excluded historical fold 0 (376 fields) and evaluated the same 1,504 Lacuna 2023 fields across four outer folds, with three inner group-based folds for model selection. Additional Lacuna and 2024 training observations were buffered by 2 km from reserved and evaluation fields, with inner-validation points additionally protected. Reused development folds were not an untouched blind test.

Joins checked unique identifiers, row counts and outcome preservation. Imputation where applicable, imagery clipping and feature scaling were fitted only to permitted target-training observations; weather was not percentile-clipped. Held-out predictions were clipped to be nonnegative, then pooled to compute RMSE (t ha⁻¹) and R². Versioned outputs preserve exclusions, features, split memberships, predictions and SHA-256 manifests [6]. Detailed screening rules, formulas and source-specific transformations are provided in the supplementary methods. Unknown moisture, point-to-field mismatch, coarse weather cells and provider/year confounding limit interpretation. Because full-season predictors can extend beyond harvest and auxiliary observations postdate 2023, these comparisons concern retrospective estimation rather than operational forecasting.

## References

[1] PULA Advisors. 2023. Lacuna enhanced agriculture datasets, v1.1.1. Zenodo. [doi:10.5281/zenodo.10060610](https://doi.org/10.5281/zenodo.10060610).

[2] Irgau, M., et al. 2025. Scalable Vision-Guided Crop Yield Estimation Dataset. Zenodo. [doi:10.5281/zenodo.17626117](https://doi.org/10.5281/zenodo.17626117).

[3] Copernicus Sentinel-2, processed by ESA. 2021. MSI Level-2A BOA Reflectance, Collection 1. [doi:10.5270/S2_-znk9xsj](https://doi.org/10.5270/S2_-znk9xsj); [Earth Search collection](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a).

[4] FEWS NET. 2023. Zimbabwe Food Security Outlook, February–September 2023. Seasonal calendar, p. 4. [Report](https://fews.net/sites/default/files/documents/reports/ZW_February_to_September_2023_FSO_Final_jh.pdf).

[5] NASA Langley Research Center POWER. [Monthly and Annual API](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/), v2.10.0; accessed 7 November 2026 UTC. Funded through NASA's Earth Science Division.

[6] DSC 291 project team. 2026. Zimbabwe maize-yield data and experiments. [Analysis snapshot a8f31fb](https://github.com/FelixYu120/DSC-291-Final-Project/tree/a8f31fb).
