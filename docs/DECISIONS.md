# Decision log

One line per decision: date, what, why. Newest on top.

- 2026-10-26 Project structure added (package folders, configs, tests, results, splits); data layer unchanged.
- 2026-10-26 Kenya pure-stand filter is `intercropping == "0"` in the audit CSV (3,977 rows); `1` is intercropped, empty is unknown.
- 2026-10-25 Four cohorts: Zimbabwe 2024, OAF Kenya 2019–2020, Zimbabwe Lacuna 2022–23, Malawi 2022/2023. Parked: curated OAF, GROW-Africa, Nigeria 2022, Zindi/CGIAR, TAMASA, LSMS, USDA.
- 2026-10-25 Season windows fixed per agro-zone (Kenya Feb–Sep; Malawi and Zimbabwe Oct–Jun), never anchored on crop-cut dates.
- 2026-10-25 Splits are spatially blocked and frozen before training; random field splits only as a labelled diagnostic.
- 2026-10-25 RMSE in t/ha is the primary metric, reported within cohort; targeting metrics and the two-cut noise ceiling are added.
- 2026-10-24 Imagery is Sentinel-2 L2A only. The UCSD Planet licence expired and the free tier charges 100 km² per clip (Amy Work, UCSD Library).
- 2026-10-21 Data snapshot and audit committed (Felix). Screened candidates are not imagery-validated labels.
