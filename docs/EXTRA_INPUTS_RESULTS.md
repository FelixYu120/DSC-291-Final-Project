# Zimbabwe extra inputs: final results

Completed 10 November 2026. The canonical sample contains 2,266 point
observations and 20,394 observation-month rows (nine months per observation).
The source database does not contain field polygons, so 10–30 m values are
point pixels or 3×3 summaries rather than exact field means.

| Source | Resolution | Access and licence | Varies inside ~2 km? | Actual match | Recommended use |
|---|---:|---|---|---:|---|
| Sentinel-1 VV/VH | 10 m | Earth Engine/Copernicus; free Copernicus terms | Yes, where acquired | 704/20,394 monthly rows; only 31 observations have all 9 months | Retain partial values with masks; do not use the 31-point complete subset as the main experiment |
| ERA5-Land temperature/rain | 11,132 m | Earth Engine/CDS; free Copernicus licence | No | 20,394/20,394 | Fill Presto's two weather channels for the full sample |
| SRTM elevation/slope | 30 m | Public SRTMGL1; NASA/USGS/JPL terms | Yes where terrain changes | 2,266/2,266 | Fill Presto's two static terrain channels |
| CHIRPS v2 rain | 0.05° (~5–6 km) | UCSB CHC; public domain | No | 20,394/20,394; 416 grid cells | Separate rainfall sensitivity analysis; do not present as field-scale weather |
| SoilGrids | 250 m | ISRIC WCS; CC BY 4.0 | Limited yes | 2,265/2,266 | Separate static covariate model arm; one genuine non-land mask near Lake Kariba |
| AlphaEarth | 10 m, 64 dimensions | Earth Engine/public COGs; CC BY 4.0 | Yes | 2,266/2,266; all 64 dimensions | Separate annual baseline; calendar-year embeddings have a possible post-harvest leakage risk |
| PlanetScope/NICFI | ~3 m / 4.77 m | Planet account; restricted non-commercial licences | Yes | Not downloaded; account-dependent | Optional high-resolution extension only after coverage and licence checks |

## Quality checks

- The six Earth Engine files contain exactly 20,394 unique `obs_id × month`
  keys; every observation has nine months.
- ERA5-Land temperature spans 286.13–301.88 K. Monthly precipitation spans
  0.000036–0.568954 m.
- CHIRPS and ERA5 monthly precipitation have correlation 0.851, supporting
  consistency while retaining their different construction and resolution.
- AlphaEarth vectors have norms 0.994–1.006 (median 1.000), as expected for
  unit-length embeddings.
- Earth Engine SRTM and the independently downloaded SRTM agree closely:
  elevation mean absolute difference 0.162 m and slope mean absolute difference
  0.437 degrees.
- Sentinel-1 coverage falls sharply after December 2021. This timing is
  consistent with the [Sentinel-1B failure on 23 December 2021](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-1/Mission_ends_for_Copernicus_Sentinel-1B_satellite)
  and the subsequent one-satellite acquisition plan; it is not a failed table
  join or missing Earth Engine export.

## Modelling decision

The strongest full-sample Presto comparison is:

1. existing Sentinel-2-only Presto;
2. Sentinel-2 + complete ERA5-Land + complete SRTM;
3. the same model with partial Sentinel-1 values and explicit masks.

SoilGrids and AlphaEarth should be evaluated as separate feature/model arms,
not inserted into pretrained Presto channels. CHIRPS should be a weather
sensitivity analysis. Sentinel-1 complete-case evaluation is exploratory only
because 31 observations are insufficient for the primary geographic
generalization result.

## Delivered files

- `derived/model_ready_monthly_extra_inputs.csv`: 20,394 rows; Presto-ready
  monthly values, masks and normalization.
- `derived/model_ready_static_extra_inputs.csv`: 2,266 rows; SRTM, SoilGrids
  and AlphaEarth field-level features.
- `reports/monthly_source_coverage.csv`: source completeness by month.
- `reports/s1_observation_coverage.csv`: selected orbit and valid-month count
  for every observation.
- `reports/feature_quality_summary.json` and
  `reports/combined_inputs_summary.json`: machine-readable audit results.
