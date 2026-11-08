# Fold 0: zimbabwe_lacuna_2022_2023

Run 20261108T162116Z, commit `archive/felix-branch-2026-11-07-9-gaf7eac7d844cb7ddc4dcdc281d22fa894174edc8-dirty`. Reason: First repeatable fold-0 scoring of the main Lacuna arms after the owner ruling of 8 Nov (fold 0 may be scored more than once; every look is logged)

Every model trains on folds 1-4 (1,504 fields) and predicts fold 0 (376 fields, 57 clusters). Paired cluster bootstrap against A1, 2,000 draws, seed 20261029. `p Holm` corrects the rank p-value over every arm except R0, R1 and A1. A win needs the rank interval above 0, the RMSE interval not entirely worse, and p Holm < 0.05. This is look 1 at fold 0 recorded in `looks.csv`.

| Arm | RMSE | MAE | Bias | R² | Rank inside clusters | Rank vs A1 | RMSE vs A1 | p Holm | Win |
|---|---:|---:|---:|---:|---:|---|---|---:|---|
| R0 training mean | 2.061 | 1.644 | -0.562 | -0.080 |  |  |  |  |  |
| R1 coordinates only (10 nearest fields) | 1.891 | 1.464 | -0.532 | 0.091 | 0.087 | -0.274 (-0.418 to -0.133) | +0.104 (-0.199 to +0.415) |  |  |
| A1 5 indices, season max + mean | 1.787 | 1.402 | -0.351 | 0.188 | 0.361 |  |  |  |  |
| V0 mean, whole window | 1.947 | 1.534 | -0.499 | 0.037 | 0.284 | -0.077 (-0.141 to -0.034) | +0.159 (+0.077 to +0.241) | 0.000 |  |
| V1 mean, pre-harvest months | 1.891 | 1.492 | -0.465 | 0.091 | 0.342 | -0.019 (-0.083 to +0.025) | +0.103 (+0.030 to +0.179) | 1.000 |  |
| V2 max (peak value) | 1.800 | 1.404 | -0.382 | 0.176 | 0.385 | +0.024 (-0.006 to +0.053) | +0.013 (-0.029 to +0.047) | 1.000 |  |
| V3 mean + median + max | 1.780 | 1.398 | -0.352 | 0.194 | 0.361 | -0.000 (-0.014 to +0.008) | -0.007 (-0.018 to +0.008) | 1.000 |  |
| L1 GCVI peak only (Li et al. 2022) | 1.856 | 1.455 | -0.469 | 0.125 | 0.345 | -0.016 (-0.104 to +0.066) | +0.068 (+0.016 to +0.114) | 1.000 |  |
| M1 monthly index curve | 1.752 | 1.384 | -0.390 | 0.220 | 0.350 | -0.011 (-0.088 to +0.037) | -0.035 (-0.124 to +0.088) | 1.000 |  |
| M2 monthly band curve | 1.542 | 1.203 | -0.327 | 0.396 | 0.454 | +0.093 (-0.023 to +0.160) | -0.246 (-0.363 to -0.089) | 1.000 |  |
| M2-pre monthly band curve, pre-harvest | 1.581 | 1.225 | -0.356 | 0.364 | 0.435 | +0.074 (-0.037 to +0.137) | -0.206 (-0.303 to -0.072) | 1.000 |  |
| S10 Presto frozen embedding (128) | 1.632 | 1.299 | -0.354 | 0.323 | 0.387 | +0.026 (-0.115 to +0.106) | -0.156 (-0.265 to +0.005) | 1.000 |  |
| X1 raw monthly inputs (10 bands + NDVI x 9 months, mean fill + missing flags) | 1.596 | 1.234 | -0.388 | 0.352 | 0.412 | +0.051 (-0.089 to +0.137) | -0.191 (-0.330 to -0.008) | 1.000 |  |
