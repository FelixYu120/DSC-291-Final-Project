# Broader Zimbabwe training: results

All scores use the same 1,504 original Lacuna 2023 development fields and unchanged nested spatial folds. RMSE is in t/ha (lower is better); R² is pooled out-of-fold (higher is better). Fold 0 remains reserved.

**2022 imagery is insufficient:** all 169 Lacuna 2022 rows have fewer than four observed December–June months and are excluded. Two 2024 rows also fail this requirement. No missing imagery predictors were imputed. The actual eligible training pools are 2,097 Lacuna 2023 fields, or those fields plus 4,330 Zimbabwe 2024 fields, before fold-specific buffers. These results cannot establish the benefit of adding 2022.

All-Lacuna adds 212 intercropped rainfed and five irrigated 2023 fields to the original primary pool. Only 132–150 of these extras are allowed in an outer fit after the 2 km buffer. The comparison therefore changes management coverage.

| Predictors | Aggregation | All-Lacuna RMSE | All-Lacuna R² | Full-Zimbabwe RMSE | Full-Zimbabwe R² |
|---|---|---:|---:|---:|---:|
| 10 bands | V0 / V3 mean | 1.7945 | 0.1821 | 1.7945 | 0.1821 |
| 10 bands | V1 crop-date mean | 1.7480 | 0.2239 | 1.7490 | 0.2231 |
| 10 bands | V1 calendar mean | 1.7494 | 0.2227 | 1.7481 | 0.2238 |
| 10 bands | V2 maximum | 1.8862 | 0.0964 | 1.8850 | 0.0975 |
| 10 bands | V3 median | 1.9368 | 0.0473 | 1.9364 | 0.0476 |
| 10 bands | V3 modal estimate | 2.0184 | -0.0348 | 2.0171 | -0.0334 |
| 5 indices | V0 / V3 mean | 1.8661 | 0.1155 | 1.8655 | 0.1161 |
| 5 indices | V1 crop-date mean | 1.8082 | 0.1696 | 1.8080 | 0.1697 |
| 5 indices | V1 calendar mean | 1.8085 | 0.1693 | 1.8067 | 0.1709 |
| 5 indices | V2 maximum | 1.7964 | 0.1804 | 1.7962 | 0.1806 |
| 5 indices | V3 median | 1.9298 | 0.0541 | 1.9298 | 0.0541 |
| 5 indices | V3 modal estimate | 1.9653 | 0.0190 | 1.9649 | 0.0194 |
| 10 index features | Legacy mean + maximum | 1.7952 | 0.1814 | 1.7948 | 0.1819 |

Best observed new arm: **bands_v1_preharvest_mean_all_lacuna**, RMSE **1.7480**, R² **0.2239**. This ranking is exploratory; many methods share the same development data.

Prespecified ten-band preharvest comparison, full-Zimbabwe minus all-Lacuna: RMSE difference **+0.0009** (95% spatial-group interval **[-0.0008, +0.0026]**); R² difference **-0.0008**.

The full-Zimbabwe model uses separate provider calibration and a tuned 2024 weight that may be zero. Actual crop dates are available for Lacuna; 2024 uses a December–March proxy. The calendar arm applies that proxy to both providers.

R² = 1 − SSE/SST, using all 1,504 out-of-fold predictions together. `metrics.csv` includes SSE and SST for an exact audit. A mean of fold-level R² values is a different statistic.

Files: `coverage_summary.csv` and `eligibility_audit.csv` document exclusions; `features.parquet` and `monthly_observations.parquet` contain actual features and their observations; `fit_memberships.csv` and `extra_lacuna_spatial_permissions.csv` document training access. `metrics.csv` contains all 52 arms, including 26 unchanged step 14 controls. `predictions.csv`, `fold_metrics.csv`, `paired_differences.csv`, `selected_parameters.csv` and `tuning.csv` preserve results and choices. `PROTOCOL.md` and `manifest.json` record methods, sources, pinned inputs and output hashes.
