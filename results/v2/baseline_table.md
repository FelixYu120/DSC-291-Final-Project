# Baseline result

Ridge on the 10 season indices (A1) against the training mean (R0) and coordinates alone (R1). Each cohort has its own model.
Split `s1_cc2km`: five folds, folds 1-4 scored, whole 2 km clusters held out. Seed 20261029. Commit `archive/felix-branch-2026-11-07-9-gaf7eac7d844cb7ddc4dcdc281d22fa894174edc8-dirty`.

Data v2: folds 1-4 only. Fold 0 is kept back for the end of the project; its fields still train.

| Cohort | Fields | Clusters | Arm | RMSE, t/ha | MAE, t/ha | Bias, t/ha | R2 inside the cohort | Rank inside clusters |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| malawi_2023 | 204 | 44 | R0 | 1.536 | 1.223 | -0.018 | -0.008 |  |
| malawi_2023 | 204 | 44 | R1 | 1.634 | 1.282 | -0.000 | -0.142 | 0.048 |
| malawi_2023 | 204 | 44 | A1 | 1.406 | 1.103 | -0.043 | 0.154 | 0.425 |
| kenya_oaf_2019_2020 | 3,181 | 680 | R0 | 1.723 | 1.343 | -0.011 | -0.003 |  |
| kenya_oaf_2019_2020 | 3,181 | 680 | R1 | 1.529 | 1.185 | -0.008 | 0.211 | 0.026 |
| kenya_oaf_2019_2020 | 3,181 | 680 | A1 | 1.674 | 1.307 | -0.011 | 0.054 | 0.127 |
| zimbabwe_lacuna_2022_2023 | 1,504 | 232 | R0 | 1.992 | 1.640 | +0.140 | -0.008 |  |
| zimbabwe_lacuna_2022_2023 | 1,504 | 232 | R1 | 1.854 | 1.434 | -0.069 | 0.127 | -0.054 |
| zimbabwe_lacuna_2022_2023 | 1,504 | 232 | A1 | 1.785 | 1.449 | +0.081 | 0.191 | 0.299 |
| malawi_2022 | 423 | 78 | R0 | 2.071 | 1.700 | -0.095 | -0.082 |  |
| malawi_2022 | 423 | 78 | R1 | 1.624 | 1.174 | -0.087 | 0.335 | -0.072 |
| malawi_2022 | 423 | 78 | A1 | 1.551 | 1.191 | -0.015 | 0.393 | 0.299 |

| Cohort | A1 minus R0, RMSE | A1 minus R1, RMSE | A1 minus R1, rank | Against coordinates |
|---|---|---|---|---|
| malawi_2023 | -0.129 (-0.240 to -0.023) | -0.228 (-0.428 to -0.052) | +0.377 (+0.175 to +0.580) | A1 wins |
| kenya_oaf_2019_2020 | -0.049 (-0.077 to -0.023) | +0.145 (+0.052 to +0.255) | +0.101 (+0.041 to +0.168) | R1 wins |
| zimbabwe_lacuna_2022_2023 | -0.207 (-0.285 to -0.127) | -0.069 (-0.217 to +0.082) | +0.353 (+0.260 to +0.433) | no clear winner |
| malawi_2022 | -0.520 (-0.673 to -0.364) | -0.073 (-0.237 to +0.078) | +0.371 (+0.232 to +0.530) | no clear winner |

Kenya A1, R2 inside each year: 2019: 0.077, 2020: 0.020.

## How to read this

- Each cohort stands alone. Yield definitions differ, so never compare t/ha or R2 across cohorts. Malawi 2022 and Malawi 2023 come from different crop cuts: never pool them or compare their t/ha.
- A win needs a paired interval that excludes 0. The primary comparison is A1 minus R1 on RMSE, per cohort.
- MAE is the mean absolute error. Bias is the mean of prediction minus yield: above 0 means the arm predicts too high.
- A cluster is a chain of fields with gaps under 2 km, measured point to point. It is not a surveyed village.
- R1 is coordinates with 10 neighbours. It is one measure of place, not the best one.
- Rank inside clusters takes out the mean of each cluster and year, on clusters of at least 3 fields. This removes most of place, not all.
- Each result is an end-of-season estimate. It is not a forecast. Clear months after the cut: Kenya 19.5 %, Malawi 2023 19.0 %, Malawi 2022 20.6 %, Lacuna 32.2 %.
- First run on 7 Nov 2026. Malawi 2022 is a new test. The other rows differ from results/baseline_table.md by the folds scored and by the cloudy months that v2 filled; results/v2/data_v2_comparison.md compares v2 with v1 on the same fields.
- Malawi 2023: villages were chosen by NDVI strata, so the score describes this sample, not a district. Malawi 2022: AVG_YLD in t/ha is inferred (it equals the mean of its two 5 x 5 m cuts at 13 % moisture), not confirmed by the provider.
- Lacuna: the unit is provisional, and about 36 % of its v1 scenes are warped from the next UTM zone.
