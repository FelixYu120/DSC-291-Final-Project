# Presto fine-tune: malawi_2022

Folds 1-4 of `s1_cc2km` (423 fields, 78 clusters). Fold 0 trains but is never scored. Paired cluster-bootstrap 95 % intervals, 2,000 draws, seed 20261029. Rules: PLAN.md.

| Arm | RMSE, t/ha | R2 | Rank inside clusters | RMSE minus A1 | Rank minus A1 | RMSE minus R1 | Rank minus R1 | Wins vs A1 |
|---|---:|---:|---:|---|---|---|---|---|
| R0 | 2.071 | -0.082 |  |  |  |  |  |  |
| R1 | 1.624 | 0.335 | -0.072 |  |  |  |  |  |
| A1 | 1.551 | 0.393 | 0.299 |  |  |  |  |  |
| P0 | 1.462 | 0.461 | 0.260 | -0.090 (-0.166 to -0.014) | -0.040 (-0.119 to +0.033) | -0.162 (-0.293 to -0.036) | +0.332 (+0.183 to +0.495) | no |
| P0_noloc | 1.523 | 0.415 | 0.244 | -0.029 (-0.108 to +0.063) | -0.056 (-0.137 to +0.026) | -0.101 (-0.257 to +0.046) | +0.316 (+0.169 to +0.481) | no |
| P1 | 1.449 | 0.470 | 0.276 | -0.102 (-0.175 to -0.027) | -0.024 (-0.119 to +0.065) | -0.175 (-0.310 to -0.044) | +0.348 (+0.189 to +0.526) | no |
| P1_noloc | 1.486 | 0.443 | 0.244 | -0.066 (-0.149 to +0.021) | -0.055 (-0.153 to +0.035) | -0.138 (-0.286 to +0.002) | +0.316 (+0.155 to +0.500) | no |
| P2 | 1.741 | 0.236 | 0.022 | +0.189 (+0.067 to +0.316) | -0.277 (-0.423 to -0.134) | +0.117 (-0.018 to +0.252) | +0.095 (-0.076 to +0.288) | no |

| Pair | Question | RMSE, a minus b | Rank, a minus b |
|---|---|---|---|
| P1 minus P2 | what pre-training adds | -0.292 (-0.405 to -0.178) | +0.253 (+0.109 to +0.399) |
| P1 minus P1_noloc | place, fine-tuned | -0.037 (-0.084 to +0.006) | +0.032 (-0.006 to +0.069) |
| P0 minus P0_noloc | place, frozen | -0.061 (-0.115 to -0.013) | +0.016 (-0.026 to +0.057) |
| P1 minus P0 | fine-tuning vs frozen | -0.012 (-0.042 to +0.024) | +0.016 (-0.028 to +0.058) |

Inner choices (the test fold plays no part):

| Arm | Fold | Learning rate | Inner RMSE | Best epochs of the 5 inner models |
|---|---|---:|---:|---|
| P1 | 1 | 3e-05 | 1.307 | 10 28 8 13 20 |
| P1 | 2 | 0.0001 | 1.246 | 3 16 8 7 28 |
| P1 | 3 | 0.0003 | 1.435 | 1 9 4 10 6 |
| P1 | 4 | 0.0001 | 1.369 | 4 20 7 2 7 |
| P1_noloc | 1 | 3e-05 | 1.346 | 16 36 7 13 20 |
| P1_noloc | 2 | 0.0001 | 1.278 | 4 16 6 5 13 |
| P1_noloc | 3 | 0.0001 | 1.467 | 31 18 4 11 14 |
| P1_noloc | 4 | 0.0001 | 1.458 | 9 29 3 9 8 |
| P2 | 1 | 0.0003 | 1.693 | 7 5 28 17 3 |
| P2 | 2 | 0.001 | 1.586 | 2 19 28 10 17 |
| P2 | 3 | 0.0003 | 1.790 | 4 3 27 5 3 |
| P2 | 4 | 0.0003 | 1.661 | 2 33 2 27 33 |

Lower RMSE is better: a negative RMSE difference favours the Presto arm. A higher rank is better.
Win vs A1 = rank interval above 0 and RMSE interval not entirely above 0 (PLAN.md).
