# Baseline result

Ridge on the 10 season indices (A1) against the training mean (R0) and coordinates alone (R1). Each cohort has its own model.
Split `s1_cc2km`: five folds, whole 2 km clusters held out. Seed 20261029. Commit `archive/felix-branch-2026-11-07-9-gaf7eac7d844cb7ddc4dcdc281d22fa894174edc8-dirty`.

| Cohort | Fields | Clusters | Arm | RMSE, t/ha | MAE, t/ha | Bias, t/ha | R2 inside the cohort | Rank inside clusters |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| malawi_2023 | 251 | 53 | R0 | 1.544 | 1.224 | -0.001 | -0.007 |  |
| malawi_2023 | 251 | 53 | R1 | 1.625 | 1.261 | +0.010 | -0.116 | 0.031 |
| malawi_2023 | 251 | 53 | A1 | 1.400 | 1.085 | -0.008 | 0.172 | 0.441 |
| kenya_oaf_2019_2020 | 3,977 | 849 | R0 | 1.746 | 1.356 | +0.000 | -0.002 |  |
| kenya_oaf_2019_2020 | 3,977 | 849 | R1 | 1.537 | 1.194 | -0.006 | 0.224 | 0.034 |
| kenya_oaf_2019_2020 | 3,977 | 849 | A1 | 1.696 | 1.318 | -0.001 | 0.054 | 0.125 |
| zimbabwe_lacuna_2022_2023 | 1,880 | 289 | R0 | 2.006 | 1.641 | -0.000 | -0.009 |  |
| zimbabwe_lacuna_2022_2023 | 1,880 | 289 | R1 | 1.861 | 1.440 | -0.162 | 0.131 | -0.023 |
| zimbabwe_lacuna_2022_2023 | 1,880 | 289 | A1 | 1.786 | 1.440 | -0.003 | 0.200 | 0.316 |

| Cohort | A1 minus R0, RMSE | A1 minus R1, RMSE | A1 minus R1, rank | Against coordinates |
|---|---|---|---|---|
| malawi_2023 | -0.144 (-0.243 to -0.050) | -0.225 (-0.386 to -0.072) | +0.410 (+0.229 to +0.571) | A1 wins |
| kenya_oaf_2019_2020 | -0.050 (-0.072 to -0.029) | +0.159 (+0.077 to +0.256) | +0.092 (+0.038 to +0.149) | R1 wins |
| zimbabwe_lacuna_2022_2023 | -0.220 (-0.292 to -0.155) | -0.075 (-0.205 to +0.050) | +0.340 (+0.266 to +0.419) | no clear winner |

Kenya A1, R2 inside each year: 2019: 0.076, 2020: 0.023.

## How to read this

- Each cohort stands alone. Yield definitions differ, so never compare t/ha or R2 across cohorts.
- A win needs a paired interval that excludes 0. The primary comparison is A1 minus R1 on RMSE, per cohort.
- MAE is the mean absolute error. Bias is the mean of prediction minus yield: above 0 means the arm predicts too high.
- A cluster is a chain of fields with gaps under 2 km. It is not a surveyed village. The widest Kenya cluster spans about 30 km.
- Kenya yield keeps spatial structure to about 50 km, so coordinates still know the neighbourhood in a new cluster.
- R1 is coordinates with 10 neighbours. It is one measure of place, not the best one.
- Rank inside clusters takes out the mean of each cluster and year, on clusters of at least 3 fields. This removes most of place, not all: in Kenya about a third of these fields sit in clusters that cross a district line. It does not show what a sensor can or cannot see.
- Each result is an end-of-season estimate. It is not a forecast. Clear months after the cut: Kenya 19 %, Malawi 20 %, Lacuna 33 %.
- These scores were first seen on 30 Oct 2026. This table is a rebuild, not a fresh test.
- Malawi: villages were chosen by NDVI strata, so the score describes this sample, not a district.
- Lacuna: the unit is provisional, and 36 % of its scenes are warped from the next UTM zone.
