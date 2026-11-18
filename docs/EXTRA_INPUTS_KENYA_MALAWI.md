# Kenya and Malawi extra inputs

Checked 18 November 2026. This extends the Zimbabwe input audit to the Kenya
OAF 2019–2020 point cohort and the Malawi 2022–2023 polygon cohorts. The large
Earth Engine exports and model-ready feature tables remain outside Git; the
executed notebooks and small audit receipts are committed.

## Final coverage

| Source | Kenya | Malawi | Recommended use |
|---|---:|---:|---|
| Sentinel-1 VV/VH | 31,816/31,816 monthly rows | 7,101/7,101 monthly rows | Additional monthly Presto radar channels |
| ERA5-Land temperature/rainfall | 31,816/31,816 | 7,101/7,101 | Additional monthly Presto weather channels |
| CHIRPS rainfall | 31,816/31,816 | 7,101/7,101 | Independent rainfall sensitivity analysis |
| SRTM elevation/slope | 3,977/3,977 observations | 789/789 fields | Static Presto terrain channels, repeated by month |
| SoilGrids, 14 layers | 3,904/3,977 observations | 789/789 fields | Optional static context with a missing-value mask |
| AlphaEarth, 64 dimensions | 3,977/3,977 | 789/789 | Separate annual representation baseline |

Kenya contains 3,977 observations and eight months per observation (31,816
rows). Malawi contains 789 fields and nine months per field (7,101 rows). All
required additional Presto channels are complete. The feature tables contain
no yield target; labels join later by `obs_id`.

## Can a source distinguish fields inside a 2 km village?

| Source | Kenya multi-field clusters varying | Malawi multi-field clusters varying |
|---|---:|---:|
| Sentinel-1 seasonal VV | 97.9% | 100.0% |
| SRTM elevation | 94.4% | 99.3% |
| AlphaEarth A00 | 95.8% | 99.3% |
| SoilGrids SOC, 0–5 cm | 86.8% | 93.0% |
| SoilGrids pH, 0–5 cm | 65.3% | 69.9% |
| CHIRPS seasonal rainfall | 48.4% | 23.8% |
| ERA5-Land seasonal rainfall | 40.1% | 13.3% |

These percentages show whether at least two values occur in a multi-field
cluster; they do not measure causal usefulness or prediction accuracy. The
coarse weather products remain contextual inputs even where interpolation or a
grid boundary produces different values inside a cluster.

## Important interpretation limits

- **Kenya has points, not field boundaries.** Some provider coordinates may be
  homesteads. The selected Sentinel-1 3×3 median is robust local support, not a
  field mean. Point versus 3×3 mean absolute differences are 0.311 dB for VV
  and 0.336 dB for VH.
- **Malawi has walked field polygons.** Sentinel-1, SRTM and AlphaEarth use
  polygon medians and therefore have a defensible field-level spatial support.
- **SoilGrids is modeled at 250 m.** It is not a soil sample. Kenya has 73
  genuine all-layer no-data observations; keep them missing and impute only
  within training folds or use a missingness mask.
- **AlphaEarth is annual.** The Kenya calendar-year vectors include months
  after the February–September window, and the Malawi season-year vectors can
  include observations after the October–June harvest. Evaluate AlphaEarth as
  a separate representation baseline, not as a causal monthly Presto channel.
- **Weather is coarse.** ERA5-Land is roughly 11 km and CHIRPS roughly 5.5 km.
  Their monthly rainfall correlation is 0.529 in Kenya and 0.928 in Malawi.

## Model-ready decision

Sentinel-1 VV/VH, ERA5-Land temperature/rainfall and SRTM elevation/slope can
replace the additional Presto inputs that were previously set to zero. CHIRPS
and SoilGrids are optional contextual model arms. AlphaEarth is a separate
annual baseline. The remaining question is empirical: whether these additions
improve yield prediction under the frozen village, regional and temporal
splits.

## Reproduction

- Kenya notebook: [`../notebooks/07_kenya_extra_inputs_analysis.ipynb`](../notebooks/07_kenya_extra_inputs_analysis.ipynb)
- Malawi notebook: [`../notebooks/08_malawi_extra_inputs_analysis.ipynb`](../notebooks/08_malawi_extra_inputs_analysis.ipynb)
- Audit receipts: [`../data/audit/extra_inputs/`](../data/audit/extra_inputs/)
- Scripts: [`../scripts/optional/extra_inputs/`](../scripts/optional/extra_inputs/)

See [`EXTRA_INPUTS.md`](EXTRA_INPUTS.md) for source access, licence and
attribution details shared with the Zimbabwe extraction.
