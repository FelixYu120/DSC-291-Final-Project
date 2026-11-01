# Evaluation protocol: generalization across space and time

Answers the feedback "How will you measure generalization across time and space?". Everything here is
fixed before the first model is trained. Evidence: semivariograms computed on the screened audit CSVs on
29 October 2026, and arm R1 on the frozen folds and the `load_xy` rows, checked on 1 November 2026.

## Why the protocol matters: location alone already "predicts" yield

A kNN on coordinates only (10 neighbours, no imagery), out-of-fold R²:

| Cohort | Random 5-fold | New village (2 km clusters) | New region |
|---|---:|---:|---:|
| Kenya OAF | 0.28 | 0.22 | 0.11 (district) |
| Malawi 2023 | −0.04 | −0.12 | −0.37 (5 km clusters) |
| Lacuna | 0.40 | 0.13 | −0.39 (`Admin1`) |
| Zimbabwe 2024 | 0.26 | 0.21 | −0.04 (20 k-means blocks) |

Random splits give R² up to 0.4 for knowing where a field is (the optimism gap of Ploton et al. 2020).
So every model is compared with this coordinates-only baseline (arm R1) **on the same split**, and a random
split is reported only as a labelled diagnostic.

## 1. Split families

| Family | File suffix | Meaning | Rule |
|---|---|---|---|
| New village | `s1_cc2km` | no test field within 2 km of a training field | 5 folds over single-linkage connected components at 2 km |
| New region | `s2_region` | whole districts held out | leave-group-out on the region unit, grouped into 5 folds |
| New season | `temporal` | train one year, test the next | Kenya only (see below) |
| Diagnostic | `random_diag` | random 5-fold | reported, labelled, never in the abstract |

**Per cohort.**

| Cohort | Spatial structure (evidence) | New village | New region | New season |
|---|---|---|---|---|
| Kenya OAF (3,977) | about half of the variance sits below 50 m, and the rest builds up to 50–100 km (semivariance over variance: 0.55 below 50 m, 0.60 at 1–2 km, 0.78 at 20–50 km, 0.99 at 50–100 km); district ICC 0.30 | 849 clusters, 5 folds, about 795 test fields per fold | leave-district-out over 50 normalised districts, 5 folds; no split file drops training fields near a test field, because that rule lived in the runner, which is parked (median test–train gap is only 4.6 km) | 2019 (1,768) → 2020 (2,209) and the reverse; split the 2020 test into districts seen in 2019 (1,849) and unseen (360, 11 districts) to separate time from space |
| Malawi 2023 (260) | range about 1–2 km; one district | 53 clusters, 5 folds, about 52 per fold; pooled scores only | no region scale; stress test with 5 km clusters (21), 5 folds | none (Kasungu 2022 → 2023 needs the 2022 imagery) |
| Lacuna 2023 (second) | structure is between districts (`Admin1` ICC 0.41, range about 50 km) | 289 clusters, 5 folds | **leave-`Admin1`-out**, 5 folds: the key test for this cohort | none (2022 has 169 rows and no imagery) |

Hyperparameters are tuned only inside the training fold, with the same grouping (nested group CV).

**Minimum sizes.** Per-fold numbers only when a fold has ≥ 100 test fields and ≥ 10 groups; otherwise
pooled out-of-fold only (Malawi 2023). Telling R² = 0.15 from 0 needs about 50 test fields; compare models
only on pooled sets of ≥ 200.

## 2. Metrics

Within cohort only, on pooled out-of-fold predictions, with fold mean ± SD alongside:

- **Accuracy:** RMSE in t/ha (primary), MAE, bias, R² = 1 − SSE/SST.
- **Ranking:** Spearman ρ, pooled and within each held-out group (median over groups with ≥ 10 fields),
  because pooled scores across districts reward getting district means right.
- **Targeting:** recall of the bottom 20 % of fields at a 20 % quota, and AUC for bottom 20 % (the "quota
  method" of Aiken et al. 2023).

**Uncertainty.** 95 % CIs by cluster bootstrap over held-out groups (2,000 draws; resample groups, not
fields). Model differences (ΔRMSE, Δρ) by **paired** bootstrap on the same draws: a model wins only when the
CI excludes 0.

**Noise ceiling.**

| Cohort | Two measurements | Agreement | Implied limit |
|---|---|---|---|
| Malawi 2023 | 10×10 m main cut vs nested 5×5 m cut (disjoint, adjacent) | r = 0.904; nested reads +0.45 t/ha higher; SD of difference 0.78 t/ha | single-cut reliability ≈ 0.90; RMSE floor ≈ 0.78 / √2 ≈ 0.55 t/ha |
| Zimbabwe 2024 | box 1 vs box 2 (label = their mean) | r = 0.87 on the 2,416 `include_primary` rows with both boxes (0.90 with the zero rows) | reliability of the mean ≈ 0.93 |

Kenya and Lacuna release one value per field, so they have no ceiling. These ceilings are upper bounds:
they ignore GPS-to-field mismatch and the gap between a small cut and the whole field (Lobell et al. 2020:
an 8×8 m cut vs full-plot harvest gave r = 0.51). Realistic field-level R² is 0.15–0.30.

## 3. Paragraph for the midterm report

> We evaluate generalization with spatially blocked splits that are frozen before any model is trained.
> Semivariograms of yield show that spatial dependence ends within 1–2 km in Malawi, runs to about 50 km in
> Kenya, and sits at the district scale in Lacuna Zimbabwe. We therefore report two split families per cohort. "New village" is
> 5-fold cross-validation over 2 km connected clusters, so no test field lies within 2 km of a training
> field. "New region" holds out whole units: One Acre Fund districts and Lacuna
> `Admin1` units. Temporal generalization is tested by training on Kenya 2019 and testing on 2020 and the
> reverse, with the 2020 test split into districts seen and unseen in 2019. All models share the same folds
> and are compared with a training-mean baseline and a coordinates-only kNN baseline, which reaches R² of
> 0.26–0.40 under random splits in the point cohorts but falls to 0.11 or below when regions are held out. We report RMSE (t/ha),
> R², within-group Spearman ρ and bottom-20 % recall with cluster-bootstrap confidence intervals, and a noise
> ceiling from the paired crop cuts in Malawi 2023.

**Cross-cohort transfer (X1, a side test, not a core question).** Yield definitions differ, so transfer is
scored at three levels, each a weaker claim: raw t/ha, calibrated (10 % of the target groups fix the mean level
only), and rank (Spearman, bottom-20 % recall). Each runs with source-scaled and target-scaled features.
The transfer runner needs no new data and only A1 features, so it costs one run; arms A2–A5 enter it only
after G3. Adjei (2026) found negative R² for every feature set in leave-one-country-out tests in five SSA
countries; compare with that.

## 4. Freezing the splits

- One CSV per cohort and family: `data/splits/<cohort>__<family>.csv`, family one of `s1_cc2km`,
  `s2_region`, `temporal`, `random_diag`.
- Columns: `obs_id`, `cohort`, `season_year`, `cluster_id`, `group_id` (the unit held out together),
  `fold` (integer; `train`/`test` for `temporal`), `repeat`, `family`, and for `temporal` also `test_subset`
  (`seen_region` or `new_region`).
- Rows: **every** `include_primary` row of the cohort, not only rows with imagery, so a split never changes
  when coverage changes. Each comparison is scored on the rows that all compared arms can predict.
- Assignment: seed `20261029`; seeded shuffle of groups, then greedy size balancing (largest group first,
  into the smallest fold).
- `data/splits/manifest.json`: generator commit, SHA-256 of `labels_v1` and of each split file, parameters,
  row counts.
- Tests: each `obs_id` once per repeat; no `group_id` in two folds; `s1_cc2km` minimum test–train distance
  ≥ 2 km; hashes match the manifest.
- Commit with one line in `DECISIONS.md` and the git tag `splits-v1`. After that, splits are never edited.

## References (each opened on 29 October 2026)

- Roberts et al. 2017, *Ecography* 40:913–929, doi:10.1111/ecog.02881
- Ploton et al. 2020, *Nat. Commun.* 11:4540, doi:10.1038/s41467-020-18321-y
- Meyer & Pebesma 2021, *Methods Ecol. Evol.* 12:1620–1633, doi:10.1111/2041-210X.13650
- Meyer & Pebesma 2022, *Nat. Commun.* 13:2208, doi:10.1038/s41467-022-29838-9
- Wadoux et al. 2021, *Ecol. Model.* 457:109692, doi:10.1016/j.ecolmodel.2021.109692
- Linnenbrink et al. 2024, *Geosci. Model Dev.* 17:5897–5912, doi:10.5194/gmd-17-5897-2024
- Kattenborn et al. 2022, *ISPRS Open J. Photogramm. Remote Sens.* 5:100018, doi:10.1016/j.ophoto.2022.100018
- Rolf et al. 2021, *Nat. Commun.* 12:4392, doi:10.1038/s41467-021-24638-z
- Lobell et al. 2020, *Am. J. Agric. Econ.* 102(1):202–219, doi:10.1093/ajae/aaz051
- Aiken et al. 2023, *J. Dev. Econ.* 161:103016, doi:10.1016/j.jdeveco.2022.103016
- Adjei 2026, arXiv:2605.08113
