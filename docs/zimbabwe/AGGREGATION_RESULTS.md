# Satellite aggregation V0–V3: results (v2 follows the team rules)

**Use v2 numbers.** The published v1 release (7 November) broke two team rules. It stays unchanged for the record
below, but its headline model is no longer a valid candidate. v2 (`zimbabwe_aggregation_v2`, 8 November) fixes both
rules on the same 1,504 Lacuna 2023 fields, outer folds 1–4, inner folds, 2 km buffer, grids, seed and bootstrap draws.

## v2 headline

**The calendar window still helps the compact band model; adding 2024 still gives no clear gain.** With ten bands and
Lacuna-only Ridge, the December–March calendar mean scores RMSE **1.7540 t/ha**, pooled out-of-fold R² **0.2186**.
The full-season mean scores 1.7984 / 0.1785. Paired difference **−0.0445 t/ha**, 95% spatial-group interval
**[−0.0805, −0.0086]** (the v2 primary contrast). With include_primary 2024 rows the calendar model scores
**1.7532 / 0.2193**: difference −0.0008, interval [−0.0028, +0.0013]. The richer monthly Ridge (1.6926) stays stronger.

| Model (Ridge, same 1,504 fields) | v1 RMSE | v1 R² | v2 RMSE | v2 R² | v1 rule problem |
|---|---:|---:|---:|---:|---|
| 10 bands, V0 mean, Lacuna only | 1.7984 | 0.1785 | 1.7984 | 0.1785 | none; unchanged |
| 10 bands, V0 mean, + 2024 | 1.7985 | 0.1784 | 1.7985 | 0.1785 | 2: trained on 1,874 zeros |
| 10 bands, V1 crop-date window, Lacuna only | 1.7503 | 0.2219 | — | — | 1: survey dates anchor the window; removed |
| 10 bands, V1 crop-date window, + 2024 | 1.7511 | 0.2211 | — | — | 1 and 2; removed |
| 10 bands, V1 calendar (Dec–Mar), Lacuna only | 1.7540 | 0.2186 | **1.7540** | **0.2186** | none; unchanged |
| 10 bands, V1 calendar (Dec–Mar), + 2024 | 1.7530 | 0.2194 | **1.7532** | **0.2193** | 2 |
| 10 bands, V2 max, Lacuna only | 1.8945 | 0.0884 | 1.8945 | 0.0884 | none; unchanged |
| 10 bands, V2 max, + 2024 | 1.8916 | 0.0912 | 1.8919 | 0.0909 | 2 |
| 5 indices, V0 mean, Lacuna only / + 2024 | 1.8676 / 1.8668 | 0.1141 / 0.1148 | 1.8676 / 1.8671 | 0.1141 / 0.1145 | + 2024: 2 |
| 5 indices, V1 calendar, Lacuna only / + 2024 | 1.8037 / 1.8086 | 0.1737 / 0.1692 | 1.8037 / 1.8088 | 0.1737 / 0.1690 | + 2024: 2 |
| 5 indices, V2 max, Lacuna only / + 2024 | 1.7986 / 1.7981 | 0.1783 / 0.1788 | 1.7986 / 1.7978 | 0.1783 / 0.1790 | + 2024: 2 |
| Index mean + max control, Lacuna only / + 2024 | 1.7968 / 1.7938 | 0.1800 / 0.1827 | 1.7968 / 1.7932 | 0.1800 / 0.1833 | + 2024: 2 |

| Paired contrast (RMSE difference, 95% interval) | v1 | v2 |
|---|---|---|
| Primary: 10-band V1 minus V0, Lacuna only | crop-date V1: −0.0481 [−0.0885, −0.0104] (rule 1) | calendar V1: **−0.0445 [−0.0805, −0.0086]** |
| 10-band V1, + 2024 minus Lacuna only | crop-date V1: +0.0008 [−0.0013, +0.0027] (rules 1, 2) | calendar V1: **−0.0008 [−0.0028, +0.0013]** |
| 10-band calendar V1, + 2024 minus Lacuna only | −0.0009 [−0.0034, +0.0018] (rule 2) | −0.0008 [−0.0028, +0.0013] |

**Which v1 numbers broke which rule.**

1. **Label-free windows.** v1's primary model and primary contrast (1.7503 t/ha, R² 0.2219, −0.0481) use
   `v1_preharvest_mean`: each Lacuna field's survey planting date ≤ image date < survey harvest date. Survey dates
   may not be model inputs or window anchors. v2 drops this variant as a candidate; V1 is the December–March calendar
   for every source. Crop-date counts stay only as `diagnostic_` columns in the window audit.
2. **Training rows follow `labels_v1.include_primary`.** Every v1 merged (+ 2024) arm trained on all 4,330
   feature-eligible 2024 rows, including the **1,874 recorded zeros** (`zimbabwe_2024_zero_likely_not_measured`).
   v2 uses only the 2,456 include_primary 2024 rows (2,458 minus 2 without imagery); after the 2 km buffer each outer
   fit may use 2,367 / 2,335 / 2,354 / 2,357 of them (v1: 4,226 / 4,191 / 4,194 / 4,213). Lacuna-only arms already used
   only include_primary rows; their v2 predictions equal v1 (largest difference 1e-11 t/ha, CSV rounding).

Pooling Lacuna and 2024 in t/ha is the recorded team exception (`docs/DECISIONS.md`, 7 November) and is unchanged.
The calendar cutoff still includes on/after-harvest scenes for 65 evaluation fields; that count is a diagnostic from
recorded harvest dates, not a model input. All results reuse development folds and remain exploratory.

v2 files (tracked copies): [RESULTS.md](../../results/aggregation_v2/RESULTS.md), [metrics](../../results/aggregation_v2/metrics.csv),
[paired intervals](../../results/aggregation_v2/paired_differences.csv), [plot](../../results/aggregation_v2/comparison.png),
[manifest](../../results/aggregation_v2/manifest.json), [verification](../../results/aggregation_v2/verification.json),
[R² audit](../../results/aggregation_v2/r2_audit.csv). The full release is `data/runs/zimbabwe_aggregation_v2/` (local, git-ignored).
Configuration: [v2](../../configs/zimbabwe_aggregation_v2.json); protocol amendment in [AGGREGATION_PROTOCOL.md](AGGREGATION_PROTOCOL.md).

```bash
python scripts/step14_compare_zimbabwe_aggregation.py --config configs/zimbabwe_aggregation_v2.json --output data/runs/zimbabwe_aggregation_v2
python scripts/verify_zimbabwe_aggregation.py --release data/runs/zimbabwe_aggregation_v2 --report results/aggregation_v2/verification.json
python scripts/audit_zimbabwe_r2.py --release data/runs/zimbabwe_aggregation_v2 --output results/aggregation_v2
```

Step 14 v2 takes about 3 minutes on one thread. The step 14 default config is now v2. To replay v1 with current code,
pass `--config configs/zimbabwe_aggregation_v1.json` and a new `--output`: on 8 November this reproduced every v1
prediction within 1e-11 t/ha and every RMSE/R² within 1e-10 (Spearman within 5e-6 from CSV rank ties).

---

## v1 record (7 November): breaks team rules; do not cite as a headline

The text below is the original v1 report. Its crop-date V1 rows break rule 1; its merged columns break rule 2.

For exact R² values, the calculation and a copyable external-review request, see the [R² audit](R2_AUDIT.md). For the later expanded training pools on these same evaluation fields, see [step 15](MULTIYEAR_RESULTS.md).

**V1 improved the mean-only reflectance-band baseline, while median and mode were worse.** On the same 1,504 Lacuna
fields, target-only Ridge RMSE fell from **1.7984 to 1.7503 t/ha** (2.68%). The paired difference was **−0.0481**, with
95% spatial-group interval **[−0.0885, −0.0104]**. Adding 2024 still provided no clear gain.

This is an improvement within the simple aggregation experiment. It does **not** beat the earlier richer monthly
Ridge baseline (1.6926), and its apparent advantage over the old index mean+max model (1.7968) is uncertain:
paired interval **[−0.1163, +0.0281]**. All results reuse development folds and remain exploratory.

### Versions and results

RMSE in t/ha; lower is better. All models use Ridge, with separately tuned adaptive Ridge for merged training.

| Version | What is summarized | 10 bands: Lacuna | 10 bands: merged | 5 indices: Lacuna | 5 indices: merged |
|---|---|---:|---:|---:|---:|
| V0 / V3 mean | Mean of observed December–June values | 1.7984 | 1.7986 | 1.8676 | 1.8668 |
| V1 preharvest mean | Recorded planting-to-before-harvest window; calendar fallback for 2024 | **1.7503** | **1.7511** | 1.8087 | 1.8071 |
| V1 calendar control | December–March for both sources | 1.7540 | 1.7530 | 1.8037 | 1.8086 |
| V2 max | Maximum over observed December–June values | 1.8945 | 1.8916 | **1.7986** | **1.7981** |
| V3 median | Median over observed December–June values | 1.9407 | 1.9403 | 1.9332 | 1.9328 |
| V3 modal estimate | Half-sample mode over observed December–June values | 2.0143 | 2.0161 | 1.9698 | 1.9692 |

Mean, median and mode are **separate models**, not concatenated predictors. V3 mean equals V0, so it is fitted once.
The earlier baseline already combined index means and maxima; its original 1.7968 / 1.7938 predictions were reproduced
and retained as separate controls. The new study has 24 aggregation models plus those two controls.

![Comparison](../../data/runs/zimbabwe_aggregation_v1/comparison.png)

### What the season information changed

- Monthly band values are already **spatial medians of clear field pixels from one selected scene**. This experiment
  changes the aggregation **over months**. The ten reflectance bands and five vegetation indices are tested separately.
- Both sources use the common **December–June** imagery range. October/November 2022 images are absent for Lacuna;
  including those extra months only for 2024 would make the comparison unequal.
- For Lacuna V1, an image must satisfy **planting date ≤ actual acquisition date < harvest date**. We use the scene's
  acquisition day, not just its month label. The planting lower bound removes preplanting observations for 130 evaluation fields.
- All 4,332 source labels lack planting/harvest dates. Their V1 is therefore a flagged **December–March proxy**, not
  reconstructed field dates. The same-calendar control applies that window to both sources.
- The actual crop-date and common-calendar band models are close: **1.7503 versus 1.7540**, difference **−0.0037**,
  interval **[−0.0456, +0.0313]**. These data do not establish that exact field dates improve on the shared calendar cutoff.

The [FEWS NET report, p. 4](https://fews.net/sites/default/files/documents/reports/ZW_February_to_September_2023_FSO_Final_jh.pdf)
provides a typical maize calendar with main harvest approximately April–June. The four climatic seasons come from the
[Zimbabwe government National Adaptation Plan 2024, section 2.1](https://unfccc.int/sites/default/files/resource/NAP-Zimbabwe-2024.pdf).
Climatic phases are not individual harvest dates. The fixed cutoff still includes on/after-harvest scenes for **65**
evaluation fields; V1 crop dates remove those. FEWS NET itself is not a Zimbabwe-government field-harvest dataset.

### What can be concluded

**For compact band inputs, restricting the time window helped.** Target-only MAE also fell, from 1.4317 to 1.3912 t/ha,
and R² rose from 0.1785 to 0.2219. The shared calendar's similar result suggests a practical candidate when crop dates
are unavailable; the experiment does not identify the causal reason for the gain.

**Maximum depends on the variable.** It helped vegetation indices relative to their mean-only version but worsened
raw reflectance-band models. Maximum brightness in each band is not equivalent to maximum vegetation condition.
The maxima of different bands can also come from different dates.

**Median and mode are not automatically better.** Exact values almost never repeat, so taking the first exact mode
would usually select the minimum. We used a [half-sample modal estimator](https://arxiv.org/abs/math/0505419), averaging
estimates from tied shortest intervals. With only 1–7 observations it can be unstable. It performed poorly here;
that does not establish that every mode estimator is unsuitable.

**The merge remains a separate question.** Preharvest band RMSE was 1.7503 without 2024 and 1.7511 with it: difference
+0.0008, interval [−0.0013, +0.0027]. Inner validation chose source weight zero in one outer fold. Keep the harmonized
source available, but do not claim that the season adjustment unlocked a material transfer benefit.

### Fair comparison and files

Every arm keeps the same 1,504 evaluation IDs, the same four outer/three inner spatial folds and the existing 2 km source
permissions. Fold 0 is excluded. **421 fields have fewer than four crop-window observations**, but none has zero;
no target field is dropped and no aggregate feature is missing in the eligible comparison population. Training-only
imputation remains implemented for reproducibility on missing inputs. Counts and dates are audited, not model predictors.

These are retrospective crop-date windows, not a demonstrated forecasting system. Many secondary comparisons were
made; their intervals are unadjusted and conditional on the predictions. Preserve the richer monthly model as the
stronger existing benchmark and retain V1 as a compact candidate for independent validation.

- [Complete results](../../data/runs/zimbabwe_aggregation_v1/RESULTS.md), [metrics](../../data/runs/zimbabwe_aggregation_v1/metrics.csv), [paired intervals](../../data/runs/zimbabwe_aggregation_v1/paired_differences.csv).
- [Feature matrix](../../data/runs/zimbabwe_aggregation_v1/features.parquet), [feature dictionary](../../data/runs/zimbabwe_aggregation_v1/feature_dictionary.json), [date/window audit](../../data/runs/zimbabwe_aggregation_v1/window_audit.csv).
- [Fixed protocol](AGGREGATION_PROTOCOL.md), [configuration](../../configs/zimbabwe_aggregation_v1.json), [step 14](../../scripts/step14_compare_zimbabwe_aggregation.py).

Replay v1 from the repository root with the pinned team database (the default config is now v2):

```bash
python scripts/step14_compare_zimbabwe_aggregation.py --config configs/zimbabwe_aggregation_v1.json --output data/runs/zimbabwe_aggregation_replay
python scripts/verify_zimbabwe_aggregation.py
```

Choose a new `--output` destination for each replay; the manifest also records the checkout revision. Earlier releases remain unchanged.

Independent reconstruction and metric/interval checks are recorded in [the verification receipt](../../results/aggregation/verification.json).
