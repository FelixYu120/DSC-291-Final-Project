# Zimbabwe data harmonization and basic Ridge results

I combined the Lacuna 2022–2023 and Zimbabwe 2024 datasets into a cleaned catalog of **6,598 yield observations**.
The objective was to determine whether adding 2024 training data improves prediction for Lacuna fields.
Harmonization made a controlled comparison possible, but adding 2024 did **not establish a reliable accuracy improvement**.

**Correction (8 November 2026).** The first run (v1) trained on rows the team excludes: all 4,332 screened 2024 rows,
including **1,874 recorded zeros** that `labels_v1.include_primary` drops (`zimbabwe_2024_zero_likely_not_measured`).
The v2 rerun trains only on `include_primary` rows (1,880 Lacuna + 2,458 Zimbabwe 2024). Evaluation fields, folds,
buffer, tuning, seeds and windows are unchanged. v2 is the current result; v1 numbers are kept beside it for reference.

The models used **10 basic Sentinel-2 vegetation features**: the seasonal mean and maximum of NDVI, GCVI, MTCI,
NDVI705 and NDVI740. These are vegetation indices, not MOSAIKS embeddings. Ridge is linear regression with a penalty
on large coefficients; these results do not include ordinary unregularized linear regression.

## What did not match, and how I addressed it

- **Imagery coverage:** all 10 features use **December–June** for both datasets, with at least four observed months.
  Two 2024 fields failed. The windows are fixed calendar windows (December 2022–June 2023, December 2023–June 2024),
  not anchored on survey dates. Individual 2024 crop dates remain unverified.
- **Yield measurements:** Lacuna uses one 40 m² crop cut; 2024 generally averages two. I checked **t/ha = dry kg × 0.25**,
  verified available-cut averages and used t/ha consistently (pooling in t/ha is a recorded team exception).
  Unknown moisture differences could not be physically corrected.
- **Missing/inconsistent labels:** I excluded three inconsistent Lacuna records and 723 missing 2024 labels.
  The 1,874 recorded 2024 zeros stay in the catalog but, under the team rule, train no v2 model.
- **Different yield distributions:** I compared naive pooling with separate source intercepts and adaptive Ridge.
  Preprocessing, calibration and source weighting used training data only.

## Evaluation and results

Every model predicted the same **1,504 Lacuna 2023 fields** using four spatial validation folds; another 376 fields
were excluded from fitting and scoring. Auxiliary 2024 observations within 2 km of evaluation or reserved fields
were excluded. Ridge penalties and source weights were selected through inner validation. These are development
results, not a new blind test.

| Training approach | v1 RMSE ↓ | v2 RMSE ↓ | v1 R² | v2 R² |
|---|---:|---:|---:|---:|
| Training-mean reference | 1.9881 | 1.9881 | −0.0039 | −0.0039 |
| Lacuna-only Ridge | 1.7968 | 1.7968 | 0.1800 | 0.1800 |
| Naively merged Ridge | 2.2707 | 2.0858 | −0.3096 | −0.1050 |
| Merged Ridge, separate intercepts | 1.7938 | 1.7923 | 0.1827 | 0.1841 |
| Adaptive merged Ridge (primary) | 1.7938 | 1.7932 | 0.1827 | 0.1833 |

RMSE in t/ha. Naive merging still worsens predictions. In v2, adaptive merging improves RMSE by only
**0.0036 t/ha (0.20%)** over Lacuna alone; the paired 95% interval is **−0.0084 to +0.0007 t/ha** (v1: −0.0030,
[−0.0076, +0.0013]). Both include no improvement. Improved prediction from adding 2024 remains unproven.

**Later experiments, v2.** With richer monthly features, adaptive Ridge gains 0.0057 t/ha [0.0021, 0.0097] from 2024
(R² 0.272 → 0.277), small and exploratory; merged monthly trees are worse than Lacuna-only trees (1.6770 vs 1.6594).
The pre-specified selector contrast is +0.0086 [−0.0336, +0.0440] (v1 −0.0096). Full weather: the best weather arm is
still Lacuna-only trees (1.6958); merging changes it by +0.0206 [−0.0044, +0.0443] (v1 +0.0264 [+0.0094, +0.0450]).
Compact weather: the best observed arm, four-feature shared Ridge, reaches 1.6428 (v1 1.6554); post hoc it is not
clearly better than Lacuna-only monthly trees (−0.0166 [−0.0583, +0.0267]).

Evidence: [merge explanation](MERGE_RESULTS.md), [transfer findings](TRANSFER_FINDINGS.md), [methods](METHODS.md);
v2 scores in [`results/merge_v2/`](../../results/merge_v2/) and [`results/weather_v2/`](../../results/weather_v2/).
