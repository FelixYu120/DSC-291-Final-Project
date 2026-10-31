# Roadmap (scope reset, 29 October 2026)

This replaces the 25 October roadmap. It answers the proposal feedback (Emily, Prabhmeet) by cutting the
project to what five people can finish by 7 December, with one runnable baseline first and a fallback at
every step. Details live in three companion files:

- [`DATA.md`](DATA.md): which labels we use, how each cohort measures yield, the one labels table.
- [`EVALUATION.md`](EVALUATION.md): splits, metrics, noise ceilings, how splits are frozen.
- [`RELATED_WORK.md`](RELATED_WORK.md): verified papers, how we differ, the CNN question.

## 1. Scope

**Research questions (rewritten).**

- **RQ1 (core).** Within one cohort, which Sentinel-2 representation predicts field-level maize yield best:
  hand-crafted seasonal indices, MOSAIKS random convolutional features, a small temporal network trained from
  scratch, or frozen foundation-model embeddings (Presto; AlphaEarth as second)? Every arm uses the same
  labels, the same frozen splits and the same Ridge head, and is compared with a coordinates-only baseline and
  the crop-cut noise ceiling.
- **RQ2 (core, was RQ3).** How much skill is left when the test fields are in a new village, a new district,
  or a new season (Kenya 2019 to 2020)?
- **Stretch only.** Field photos (Li et al. 2026; hand-held harvest photos, Zimbabwe 2024, **not UAV**),
  cross-cohort transfer with rank metrics, Presto fine-tuning, a 2D CNN.

**Cohorts.**

| Role | Cohort | Fields | Why |
|---|---|---:|---|
| CORE | Kenya OAF 2019–2020, pure stand | 3,977 points | Largest, one protocol, two years (temporal test), 50 districts. Imagery coverage passed the pilot. |
| CORE | Malawi 2023 | 260 polygons | Best labels: walked boundaries, 10×10 m cut at 13 % moisture, nested cut gives a noise ceiling. |
| SECOND | Zimbabwe Lacuna 2023, pure stand | 1,880 points | Second country, 20 `Admin1` units for a district holdout. Unit still provisional. Starts after the core is green. |
| PARKED | Zimbabwe 2024 (vision-guided) | 2,458 positive | 43 % zeros whose share follows the visit month (13 % March, 100 % July): most zeros look like "not measured". Only for the photo stretch, positive rows only. |
| DROPPED | Malawi 2022, Lacuna 2022, Nigeria 2022, curated OAF, other OAF countries, USDA, GROW-Africa | – | 2022 Collection-1 imagery gap, coarse coordinates, or the wrong scale. |

**Model arms** (one row each in the results table, parked with the model code, see `_parked/MANIFEST.csv`; the 9-cell whiteboard grid is cut to these):

| Arm | Features | Head | Status |
|---|---|---|---|
| R0 | none (training-fold mean) | – | core reference |
| R1 | coordinates only (kNN, k = 10, on lat/lon) | – | core reference: the model to beat |
| R2 | `months_with_data` only | Ridge | core check: is a model only learning cloud cover? |
| **A1 = B0** | 10 seasonal index features (max and mean of NDVI, GCVI, MTCI, NDVI705, NDVI740) | RidgeCV | **core, first** |
| A2 | MOSAIKS, field pooling, K = 1024 | RidgeCV | core |
| A3 | Presto frozen encoder, 128-d | RidgeCV | core |
| A4 | monthly 10-band series + mask, small GRU (or 1D CNN) trained from scratch | itself | core: the learned deep-learning arm |
| A5 | AlphaEarth annual 64-d (Source Cooperative copy, no Earth Engine account needed) | RidgeCV | second |
| H | A1–A3 features | HistGradientBoosting | second: the "tree-based" row of the whiteboard |
| – | MOSAIKS+GRU, Presto+GRU, AlphaEarth+GRU, SkySat, photo fusion, Jin et al. replication, label-budget curves | – | cut |

Why there is no 2D CNN in the core: see [`RELATED_WORK.md`](RELATED_WORK.md#the-cnn-question). In one line:
MOSAIKS *is* a one-layer CNN with random filters (Rolf et al. 2021), and on our labels (one 10 m pixel per
point, 0.4–0.6 ha polygons, a few thousand noisy labels) a trained 2D CNN would mostly see neighbours' land.

## 2. The absolute minimum baseline (B0)

B0 is arm A1 on the core cohorts, next to R0, R1 and R2. It needs no new model code beyond a small runner.

| Item | Specification |
|---|---|
| Rows | `labels_v1` rows with `include_primary` (see [`DATA.md`](DATA.md)) and at least 4 clear months. Malawi 2023 first, Kenya as soon as its chips are in. All arms are scored on exactly these rows. |
| Features | The 10 columns of the `season_indices` view in `sql/views.sql`, clipped at the training 1st and 99th percentile, then standardised with training-fold statistics. The clip is there because MTCI reaches 1,300 where its median is about 4.5. |
| Model | `Pipeline(Winsorize, StandardScaler, Ridge)`, alpha from `logspace(-3, 5, 17)` chosen by grouped CV inside the training fold only. |
| Split | `s1_cc2km` (new village: 5 folds over 2 km clusters) from `data/splits/`, plus `s2_region`, `temporal` and `random_diag` (labelled as a diagnostic). |
| Metrics | Pooled out-of-fold RMSE (t/ha), MAE, bias, R², Spearman; per-fold rows in the results table. |
| Config | The B0 config, parked (`_parked/MANIFEST.csv`) |
| Done when | The results table holds A1, R0, R1, R2 for Malawi 2023 under `s1_cc2km` (5 folds each); a second run gives identical numbers; the split file hash matches `data/splits/manifest.json`; the Malawi noise-ceiling row is there. A weak or negative R² is a finished B0, not a failure. |

**Result (30 October, the results table).** The "Done when" items hold: a second run gives the same numbers,
the hashes match, the noise-ceiling row is there. Pooled out-of-fold scores, 95 % cluster-bootstrap CI in
brackets:

| Cohort, split | R² A1 | R² R1 | Spearman A1 | RMSE A1 − R1 (t/ha) |
|---|---:|---:|---:|---:|
| Malawi, new village (251) | 0.17 [0.06, 0.27] | −0.12 | 0.38 | −0.23 [−0.39, −0.07] |
| Malawi, 5 km clusters | 0.15 [0.07, 0.25] | −0.37 | 0.34 | −0.38 [−0.50, −0.27] |
| Kenya, new village (3,977) | 0.05 [0.03, 0.07] | 0.22 | 0.23 | +0.16 [0.08, 0.26] |
| Kenya, new district | 0.03 [−0.02, 0.06] | 0.11 | 0.18 | +0.07 [−0.05, 0.22] |
| Kenya, 2019 to 2020 | −0.08 [−0.17, −0.02] | −0.55 | 0.17 | −0.32 [−0.59, −0.10] |
| Kenya, 2020 to 2019 | 0.06 [−0.10, 0.08] | 0.24 | 0.28 | +0.19 [0.02, 0.40] |
| Lacuna, new village (1,880) | 0.20 [0.14, 0.25] | 0.13 | 0.46 | −0.08 [−0.21, 0.05] |
| Lacuna, new district | 0.12 [−0.08, 0.18] | −0.39 | 0.36 | −0.48 [−0.79, −0.19] |

Read it like this. In Malawi the indices beat coordinates, so gate G2 is already met by A1. In Kenya coordinates
beat the indices: where a field is says more than how green it is. Inside one held-out group A1 still ranks
fields better (within-group Spearman 0.14 against 0.05). Between years the level does not carry over (A1 is off
by −0.36 t/ha from 2019 to 2020, and nothing beats the training mean), but the ranking does. The Malawi noise
ceiling is r = 0.90 and RMSE 0.90 t/ha between its two cuts, so A1 (RMSE 1.40 t/ha) is far from that limit.
Lacuna gives the strongest signal, and it holds in new districts where coordinates fail. Lacuna is also point
data, so points alone do not explain the weak Kenya score; location quality is the likely cause (`DATA.md`).

**X1, transfer between cohorts (30 October, parked config).** Ridge on A1 features,
trained on all rows of one cohort, tested on all rows of another, with no target label:

| Train on | Test on | Spearman | R² in raw t/ha | Spearman of the target's own model (new village) |
|---|---|---:|---:|---:|
| Kenya | Lacuna | 0.40 [0.33, 0.46] | 0.09 | 0.46 |
| Kenya | Malawi | 0.31 [0.20, 0.43] | 0.11 | 0.38 |
| Lacuna | Malawi | 0.30 [0.18, 0.43] | 0.01 | 0.38 |
| Malawi | Lacuna | 0.18 [0.13, 0.23] | −0.09 | 0.46 |
| Lacuna | Kenya | 0.17 [0.13, 0.22] | −0.08 | 0.23 |
| Malawi | Kenya | 0.14 [0.10, 0.19] | −0.11 | 0.23 |

So the ranking of fields carries over to another country; the yield level mostly does not. The model trained on
the most fields (Kenya) carries best. The two harmonization steps did not help: rescaling features to the target
lowered Spearman in 5 of 6 pairs, and matching the level on 10 % of target groups did not raise R² in a useful
way. These Spearman values are pooled over the whole target, so they also reward getting its regions right.
Three of six pairs reach R² ≥ 0, unlike the negative R² in Adjei (2026).

## 3. Stages, gates and fallbacks

Owners are roles; the team assigns names at kickoff. Every stage has one MVP: the smallest result that
counts as done.

| Stage | Dates | MVP | Done test | Owner | Fallback |
|---|---|---|---|---|---|
| **0 Data foundation** | Thu 29 Oct – Mon 2 Nov | `labels_v1` built and frozen; split files for Malawi 2023, Kenya, Lacuna 2023 frozen; Malawi 2023 chips complete; Kenya download running | the checks in `DATA.md` pass; hashes recorded in `DECISIONS.md` | data lead + imagery | Kenya chips late: B0 runs on Malawi alone, Kenya joins when ready |
| **1 B0** | Tue 3 – Wed 4 Nov | B0 runner (config in, result rows out) on Malawi 2023 | "Done when" in section 2 | baselines | runner bug: run B0 from a notebook once, then port it |
| **2 Core arms** | Thu 5 – Sun 8 Nov | B0 on Kenya; A2 (after the one MOSAIKS refit) and A3 on both core cohorts; region and temporal splits run for A1 | rows in the results table, same folds | representations + evaluation | MOSAIKS refit late: A3 first, A2 in stage 3 |
| **Gate G2: signal** | Sun 8 Nov | Does any satellite arm beat R1 on pooled RMSE under `s1_cc2km` (paired bootstrap CI excludes 0) in at least one core cohort? | | all | **No:** the paper becomes a measured negative result: noise ceiling, point vs polygon, label quality, coverage. A4 and A5 are skipped. |
| **Midterm** | Mon 9 – Thu 12 Nov | Report (contents below) | submitted | writing lead | – |
| **3 Complete the table** | Fri 13 – Sun 22 Nov | A4 GRU; head swap H; A5 AlphaEarth; Lacuna 2023 through all arms; point 3×3-pixel ablation; robustness rows (zeros, OAF site distance, harvest after window) | every core arm × core cohort × {new village, new region, temporal} in the results table | all | A4 unstable: report it with its training curve; never tune on test folds |
| **Gate G3: scope** | Sun 22 Nov | Core table complete? | | all | **No:** no stretch item starts; finish the core |
| **4 Freeze** | Mon 23 – Wed 25 Nov | Results frozen Wed 25 Nov (Thanksgiving is Thu 26 Nov); stretch only if G3 passed | every figure rebuilds from the results table | evaluation | drop the stretch section, never the core table |
| **5 Talk and paper** | Thu 26 Nov – Mon 7 Dec | Talk 1 or 3 Dec (each member presents one result); paper and oral 7 Dec | submitted | all | – |

Stage 0 and stage 1 finished on 30 October, ahead of the dates above.

**Midterm report (12 Nov) contains:** the cohort table with yield definitions (answer to "same
measurement?"); the no-pooling rule; the pipeline figure; the split protocol (paste the paragraph in
`EVALUATION.md`); B0, A2, A3 against R0/R1/R2 with CIs and the noise ceiling; the CNN paragraph; the related
work paragraph; this stage plan with its gates; and the list of experiments we will not run.

## 4. What changed after the feedback

| Comment | Answer | Where |
|---|---|---|
| Emily: ambitious for one quarter | RQ2 (photos/UAV) moved to stretch; 2 core cohorts instead of 4; the 9 grid cells cut to 4 core arms plus references | sections 1, 3 |
| Emily: other papers using foundation models for yield? | Yes. Closest: Adjei 2026 (frozen Prithvi vs spectral features, five SSA countries, negative cross-country R²), Ma et al. 2026 (AlphaEarth, US), Kamangir et al. 2026, Nejadshamsi et al. 2025, Nedungadi et al. 2026. We differ: crop-cut field labels, MOSAIKS vs Presto vs AlphaEarth under one head, within-cohort spatial and temporal holdouts, noise ceilings | `RELATED_WORK.md` |
| Emily: MOSAIKS + Ridge vs CNN vs foundation model? | Yes, three-way, with the "CNN" split honestly: MOSAIKS is the random-filter CNN, A4 is the network trained from scratch, A3/A5 are the pretrained models | `RELATED_WORK.md` |
| Emily: same yield measurement? exact field boundaries? | No and no. Cut size, number of cuts and moisture basis differ; only Malawi has polygons. So we never pool: one model per cohort, metrics within cohort | `DATA.md` |
| Emily: how to measure generalization? | Two pre-registered split families (new village, new region) plus Kenya 2019 to 2020, all frozen before training | `EVALUATION.md` |
| Prabhmeet: 5 weeks may be too short | Stage plan with gates; stretch work cannot start before G3 (22 Nov) | section 3 |
| Prabhmeet: no Planet licence; Sentinel-2 / Landsat via GEE | Sentinel-2 L2A only (Earth Search). Landsat at 30 m is coarser than most fields. GEE only as an option to fill the 2022 gap, not needed for the core | `DATA.md` |
| Prabhmeet: harmonization will take long | Not pooling removes most harmonization: each cohort keeps its own yield definition | `DATA.md` |

## 5. State and next actions

Done by 30 October: `labels_v1` and the split files are frozen, the chips are complete for all five cohorts, the
one MOSAIKS refit and the Presto embeddings are in `data/cropyield.duckdb`, and B0 and X1 are in
the results table. Next:

1. **Representations.** A2 and A3 on the core cohorts and Lacuna, on the same folds.
2. **Robustness rows.** Fill the Malawi cloud months; Kenya without far points (`DATA.md`).
3. **Writing.** Overleaf skeleton for the midterm with the sections listed above.
