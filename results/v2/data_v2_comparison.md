# Data v2: the pre-registered scores

Split `s1_cc2km`, folds 1-4 scored (fold 0 trains only). Seed 20261029. Commit `a95c12c8804635afaab154112487213231c04650-dirty`.

## 1. More photos per month: A1 on v2 minus A1 on v1, same fields

| Cohort | Fields | Changed | New in v2 (apart) | Rank v1 | Rank v2 | Rank v2 - v1 | RMSE v1 | RMSE v2 | RMSE v2 - v1 | v2 wins |
|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|
| malawi_2023 | 202 | 44 | 2 | 0.445 | 0.425 | -0.021 (-0.068 to +0.035) | 1.392 | 1.409 | +0.017 (-0.019 to +0.051) | no |
| kenya_oaf_2019_2020 | 3,181 | 123 | 0 | 0.127 | 0.127 | +0.001 (-0.003 to +0.004) | 1.675 | 1.674 | -0.001 (-0.003 to +0.001) | no |
| zimbabwe_lacuna_2022_2023 | 1,504 | 166 | 0 | 0.305 | 0.299 | -0.006 (-0.012 to -0.001) | 1.786 | 1.785 | -0.001 (-0.009 to +0.006) | no, worse |

A win: the rank interval lies above 0 and the RMSE interval does not lie entirely above 0.
"no, worse": an interval excludes 0 on the worse side. "Changed": scored fields whose season values differ in v2.

## 3. Malawi season transfer (Spearman only: the crop cuts differ)

| Train -> test | Train fields | Test fields | Clusters | A1 | R1 (coordinates) | A1 - R1 |
|---|---:|---:|---:|---|---|---|
| malawi_2022 -> malawi_2023 | 184 | 204 | 44 | +0.315 (+0.190 to +0.451) | +0.102 (-0.060 to +0.262) | +0.213 (+0.057 to +0.374) |
| malawi_2023 -> malawi_2022 | 253 | 150 | 30 | +0.413 (+0.277 to +0.545) | +0.155 (-0.117 to +0.405) | +0.259 (+0.032 to +0.489) |

- Test fields in fold 0 of their own `s1_cc2km` split are not scored. Every field of the training season trains.
- This is a new season, not a new place: the 2 km groups span both seasons, and about 13 % of the 2023 test fields lie within 2 km of a 2022 training field. R1 shows what place alone gives.
- The season means cover different months: October and November are clear for every Malawi 2022 field and for no Malawi 2023 field (a catalogue gap of the newer collection). In the audit of 7 Nov, A1 on the five season maxima alone ranked the test season as well or better.

Malawi 2022 alone (R0, R1, A1, folds 1-4): `results/v2/baseline_table.md`.
