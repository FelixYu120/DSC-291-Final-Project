# Presto fine-tune: malawi_2023

Folds 1-4 of `s1_cc2km` (204 fields, 44 clusters). Fold 0 trains but is never scored. Paired cluster-bootstrap 95 % intervals, 2,000 draws, seed 20261029. Rules: PLAN.md.

| Arm | RMSE, t/ha | R2 | Rank inside clusters | RMSE minus A1 | Rank minus A1 | RMSE minus R1 | Rank minus R1 | Wins vs A1 |
|---|---:|---:|---:|---|---|---|---|---|
| R0 | 1.536 | -0.008 |  |  |  |  |  |  |
| R1 | 1.634 | -0.142 | 0.048 |  |  |  |  |  |
| A1 | 1.406 | 0.154 | 0.425 |  |  |  |  |  |
| P0 | 1.459 | 0.090 | 0.299 | +0.052 (-0.038 to +0.130) | -0.126 (-0.226 to -0.010) | -0.175 (-0.385 to +0.017) | +0.251 (+0.039 to +0.478) | no |
| P0_noloc | 1.458 | 0.090 | 0.321 | +0.052 (-0.031 to +0.125) | -0.103 (-0.204 to +0.007) | -0.176 (-0.382 to +0.016) | +0.274 (+0.069 to +0.489) | no |
| P1 | 1.405 | 0.156 | 0.390 | -0.001 (-0.092 to +0.080) | -0.034 (-0.150 to +0.103) | -0.229 (-0.431 to -0.049) | +0.342 (+0.142 to +0.555) | no |
| P1_noloc | 1.420 | 0.137 | 0.379 | +0.014 (-0.073 to +0.089) | -0.045 (-0.163 to +0.088) | -0.214 (-0.405 to -0.046) | +0.332 (+0.131 to +0.541) | no |
| P2 | 1.546 | -0.022 | -0.175 | +0.140 (+0.037 to +0.251) | -0.600 (-0.797 to -0.390) | -0.088 (-0.282 to +0.082) | -0.223 (-0.390 to -0.018) | no |

| Pair | Question | RMSE, a minus b | Rank, a minus b |
|---|---|---|---|
| P1 minus P2 | what pre-training adds | -0.141 (-0.242 to -0.057) | +0.566 (+0.358 to +0.746) |
| P1 minus P1_noloc | place, fine-tuned | -0.015 (-0.052 to +0.021) | +0.011 (-0.035 to +0.060) |
| P0 minus P0_noloc | place, frozen | +0.000 (-0.021 to +0.018) | -0.023 (-0.056 to +0.013) |
| P1 minus P0 | fine-tuning vs frozen | -0.054 (-0.105 to +0.002) | +0.091 (+0.024 to +0.156) |

Inner choices (the test fold plays no part):

| Arm | Fold | Learning rate | Inner RMSE | Best epochs of the 5 inner models |
|---|---|---:|---:|---|
| P1 | 1 | 3e-05 | 1.348 | 32 36 38 11 2 |
| P1 | 2 | 0.0003 | 1.418 | 11 8 7 12 4 |
| P1 | 3 | 0.0003 | 1.394 | 19 2 8 1 4 |
| P1 | 4 | 0.0001 | 1.250 | 10 2 13 15 7 |
| P1_noloc | 1 | 0.0001 | 1.343 | 19 7 21 17 2 |
| P1_noloc | 2 | 3e-05 | 1.442 | 26 1 17 27 15 |
| P1_noloc | 3 | 0.001 | 1.355 | 18 9 14 1 10 |
| P1_noloc | 4 | 0.0001 | 1.262 | 8 2 20 15 13 |
| P2 | 1 | 0.0003 | 1.521 | 2 11 19 11 9 |
| P2 | 2 | 0.0001 | 1.566 | 6 3 26 1 9 |
| P2 | 3 | 0.001 | 1.527 | 2 2 16 10 3 |
| P2 | 4 | 0.001 | 1.441 | 15 5 12 3 1 |

Lower RMSE is better: a negative RMSE difference favours the Presto arm. A higher rank is better.
Win vs A1 = rank interval above 0 and RMSE interval not entirely above 0 (PLAN.md).
