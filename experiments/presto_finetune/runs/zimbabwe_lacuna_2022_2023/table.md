# Presto fine-tune: zimbabwe_lacuna_2022_2023

Folds 1-4 of `s1_cc2km` (1,504 fields, 232 clusters). Fold 0 trains but is never scored. Paired cluster-bootstrap 95 % intervals, 2,000 draws, seed 20261029. Rules: PLAN.md.

| Arm | RMSE, t/ha | R2 | Rank inside clusters | RMSE minus A1 | Rank minus A1 | RMSE minus R1 | Rank minus R1 | Wins vs A1 |
|---|---:|---:|---:|---|---|---|---|---|
| R0 | 1.992 | -0.008 |  |  |  |  |  |  |
| R1 | 1.854 | 0.127 | -0.054 |  |  |  |  |  |
| A1 | 1.785 | 0.191 | 0.299 |  |  |  |  |  |
| P0 | 1.657 | 0.302 | 0.358 | -0.128 (-0.200 to -0.057) | +0.059 (+0.014 to +0.105) | -0.197 (-0.318 to -0.075) | +0.412 (+0.319 to +0.496) | yes |
| P0_noloc | 1.654 | 0.305 | 0.335 | -0.132 (-0.199 to -0.067) | +0.036 (-0.005 to +0.077) | -0.200 (-0.330 to -0.073) | +0.389 (+0.295 to +0.470) | no |
| P1 | 1.652 | 0.307 | 0.353 | -0.133 (-0.206 to -0.061) | +0.054 (+0.006 to +0.100) | -0.202 (-0.332 to -0.067) | +0.407 (+0.306 to +0.493) | yes |
| P1_noloc | 1.652 | 0.307 | 0.339 | -0.133 (-0.202 to -0.067) | +0.041 (-0.004 to +0.083) | -0.202 (-0.324 to -0.077) | +0.393 (+0.299 to +0.473) | no |
| P2 | 1.756 | 0.217 | 0.314 | -0.029 (-0.074 to +0.014) | +0.015 (-0.035 to +0.063) | -0.098 (-0.237 to +0.048) | +0.368 (+0.280 to +0.441) | no |

| Pair | Question | RMSE, a minus b | Rank, a minus b |
|---|---|---|---|
| P1 minus P2 | what pre-training adds | -0.104 (-0.170 to -0.037) | +0.039 (-0.000 to +0.081) |
| P1 minus P1_noloc | place, fine-tuned | -0.000 (-0.028 to +0.031) | +0.014 (-0.001 to +0.029) |
| P0 minus P0_noloc | place, frozen | +0.004 (-0.024 to +0.034) | +0.023 (+0.007 to +0.040) |
| P1 minus P0 | fine-tuning vs frozen | -0.005 (-0.040 to +0.031) | -0.005 (-0.025 to +0.015) |

Inner choices (the test fold plays no part):

| Arm | Fold | Learning rate | Inner RMSE | Best epochs of the 5 inner models |
|---|---|---:|---:|---|
| P1 | 1 | 3e-05 | 1.568 | 26 15 24 9 16 |
| P1 | 2 | 3e-05 | 1.591 | 34 3 16 20 8 |
| P1 | 3 | 3e-05 | 1.570 | 12 19 6 16 15 |
| P1 | 4 | 3e-05 | 1.592 | 19 26 3 14 9 |
| P1_noloc | 1 | 0.0001 | 1.596 | 23 5 11 7 13 |
| P1_noloc | 2 | 0.0001 | 1.603 | 13 4 16 8 3 |
| P1_noloc | 3 | 0.0001 | 1.582 | 7 6 2 8 5 |
| P1_noloc | 4 | 0.0003 | 1.593 | 8 1 4 3 8 |
| P2 | 1 | 0.0003 | 1.730 | 12 15 24 10 17 |
| P2 | 2 | 0.0003 | 1.696 | 18 19 16 22 18 |
| P2 | 3 | 0.0003 | 1.678 | 12 40 21 11 26 |
| P2 | 4 | 0.0003 | 1.779 | 13 16 3 12 12 |

Lower RMSE is better: a negative RMSE difference favours the Presto arm. A higher rank is better.
Win vs A1 = rank interval above 0 and RMSE interval not entirely above 0 (PLAN.md).
