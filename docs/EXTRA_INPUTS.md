# Extra inputs for Zimbabwe Presto and field-level models

Checked 10 November 2026. Scope: 2,266 Zimbabwe point observations (169 in
season 2022 and 2,097 in season 2023), each represented by nine months from
October through June. There are no field polygons. Therefore, a 10–30 m point
pixel or 3×3 summary is feasible, but it must not be described as an exact
field mean.

| Source | Resolution | How to get it | Licence | Differences inside a ~2 km village? | Fit to our places and times | Current status |
|---|---:|---|---|---|---|---|
| **Sentinel-1 GRD: VV, VH** | 10 m for IW high-resolution scenes | Earth Engine `COPERNICUS/S1_GRD` or Copernicus Data Space. The extraction uses the Presto/OpenMapFlow midpoint rule and exports ascending and descending passes separately. | Free/open under Copernicus Sentinel Data Terms; attribution required. | **Yes where acquired.** Backscatter can differ between nearby fields; viewing directions must not be mixed within one season. | **Only partially.** Coverage falls sharply after the Sentinel-1B failure on 23 Dec 2021. | **Extracted and audited, but sparse:** 704/20,394 monthly rows (3.45%); only 31/2,266 observations have all nine months. Keep missing S1 channels masked. Do not use the 31-point complete subset as the main experiment. |
| **ERA5-Land: temperature and rainfall** | 11,132 m in Earth Engine (~9–11 km depending on convention) | Earth Engine `ECMWF/ERA5_LAND/MONTHLY_AGGR` or Copernicus CDS. Use `temperature_2m` and monthly `total_precipitation_sum`. | Copernicus licence; free with acknowledgement and citation. | **No.** A 2 km village normally shares one cell; 10 m resampling adds no information. | **Yes.** Every requested month exists. This is the weather input used by Presto; NASA POWER is not a substitute for exact compatibility. | **Extracted and matched: 20,394/20,394 monthly rows.** Temperature range is 286.13–301.88 K; monthly precipitation range is 0.000036–0.568954 m. |
| **SRTM elevation and slope** | 30 m | Public SRTMGL1 tiles; slope derived from the DEM. The GEE script also exports `ee.Terrain.slope` for an exact pipeline check. | NASA/USGS/JPL open-use terms; cite SRTM. | **Yes where terrain changes;** weak in flat villages. | **Yes; static.** Repeat the two values through the nine Presto months. | **Downloaded and matched: 2,266/2,266.** Twenty source tiles, point and 3×3 values, hashes and audit saved. |
| **PlanetScope / NICFI mosaics** | ~3 m PlanetScope scenes; 4.77 m NICFI mosaics | Planet Education & Research application for scenes; NICFI signup for Earth Engine collection `projects/planet-nicfi/assets/basemaps/africa`. | Account-dependent. E&R is non-commercial/research and restricts redistribution. NICFI is non-commercial and purpose-restricted to program goals. | **Yes—strongest optical candidate** for neighboring small fields. | **Likely/conditional.** The official Africa catalog covers Zimbabwe and includes monthly 2022–2023 mosaics, but point-level coverage and account permission must be checked after signup. | **Information and browser steps ready; no authorized Planet account yet.** It is optional, not a dependency. |
| **CHIRPS v2 rainfall** | 0.05°, about 5–6 km | UCSB Climate Hazards Center files or Earth Engine. | Public domain / CC0 statement; cite CHC. | **No.** Most fields inside a 2 km village share a cell. | **Yes.** Monthly rainfall aligns to all observation months. Do not mix v2 and v3 in one time series. | **Downloaded and matched: 20,394/20,394 rows, 2,266/2,266 observations, 416 grid cells.** |
| **SoilGrids 2.0** | 250 m | ISRIC WCS subsets (more stable than the paused beta REST API). Seven properties at 0–5 and 5–15 cm were selected: bulk density, CEC, clay, sand, nitrogen, pH and SOC. | CC BY 4.0; ISRIC attribution required. | **Limited yes.** Several predicted pixels can occur within 2 km, but they are smoothed model outputs, not field samples. | **Yes; static.** Join by `obs_id`, outside the pretrained Presto channel set. | **Downloaded and matched: 2,265/2,266.** One point near Lake Kariba is genuinely masked and remains missing. |
| **AlphaEarth annual embeddings** | 10 m, 64 dimensions | Earth Engine `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`; public COGs are an alternative. | CC BY 4.0 with Google/DeepMind attribution. | **Yes.** 10 m vectors can vary field to field, but individual dimensions are not interpretable. | **Yes, with leakage caution.** Calendar-year embeddings can include observations after an October–June season's harvest. Use as a separate annual baseline, not a monthly Presto input. | **Extracted and matched: 2,266/2,266 observations, all 64 dimensions.** Vector norms are approximately one, as expected. |

## Integration rule

Sentinel-1 and ERA5 form one row per `obs_id × month`. SRTM is repeated across
months. The exact Presto normalization is applied: `(VV+25)/25`, `(VH+25)/25`,
`(temperature_2m-272.15)/35`, `precipitation/0.03`, `elevation/2000`, and
`slope/50`. Missing values remain missing and masked; they are never silently
replaced by zero.

CHIRPS is a separate rainfall sensitivity analysis. SoilGrids and AlphaEarth
are joined as field-level covariates or separate model arms because they are not
Presto input channels. PlanetScope/NICFI remains optional until account access
and actual coverage are verified.

## Completion criterion

The core extraction task is complete: the six Earth Engine exports contain
20,394 unique `obs_id × month` rows, every observation has nine months, ERA5
and SRTM are complete, AlphaEarth is complete, and Sentinel-1 missingness is
explicitly reported. The assembler produces `model_ready_monthly_extra_inputs.csv`,
`model_ready_static_extra_inputs.csv`, `monthly_source_coverage.csv`,
`s1_observation_coverage.csv`, and the JSON audit reports.
