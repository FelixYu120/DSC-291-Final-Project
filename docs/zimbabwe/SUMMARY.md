# Zimbabwe data harmonization and basic Ridge results

I combined the Lacuna 2022–2023 and Zimbabwe 2024 datasets into a cleaned catalog of **6,598 yield observations**.
The objective was to determine whether adding 2024 training data improves prediction for Lacuna fields.
Harmonization made a controlled comparison possible, but adding 2024 did **not establish a reliable accuracy improvement**.

The models used **10 basic Sentinel-2 vegetation features**: the seasonal mean and maximum of NDVI, GCVI, MTCI,
NDVI705 and NDVI740. These are vegetation indices, not MOSAIKS embeddings. Ridge is linear regression with a penalty
on large coefficients; these results do not include ordinary unregularized linear regression.

## What did not match, and how I addressed it

- **Imagery coverage:** I recalculated all 10 features using **December–June** for both datasets and required at least
  four observed months. Two 2024 fields failed. The windows are December 2022–June 2023 and December 2023–June 2024:
  corresponding seasonal windows in different years. Individual 2024 crop dates remain unverified.
- **Yield measurements:** Lacuna uses one 40 m² crop cut; 2024 generally averages two. I checked **t/ha = dry kg × 0.25**,
  verified available-cut averages and used t/ha consistently. Already averaged yields were not divided again.
  Unknown moisture differences could not be physically corrected.
- **Missing/inconsistent labels:** I excluded three inconsistent Lacuna records and 723 missing 2024 labels.
  I retained 1,874 recorded 2024 zeros because zero yield differs from missing data.
- **Different yield distributions:** I compared naive pooling with separate source intercepts and adaptive Ridge,
  allowing different yield means, scales and feature relationships. Preprocessing, calibration and source weighting
  used training data only.

## Evaluation and results

Every model predicted the same **1,504 Lacuna 2023 fields** using four spatial validation folds; another 376 fields
were excluded from fitting and scoring. Auxiliary 2024 observations within 2 km of evaluation or reserved fields
were excluded. Ridge penalties and source weights were selected through inner validation. These are development
results, not a new blind test.

| Training approach | RMSE ↓, t/ha | MAE ↓, t/ha | R² ↑ |
|---|---:|---:|---:|
| Training-mean reference | 1.9881 | 1.6217 | −0.0039 |
| Lacuna-only Ridge | 1.7968 | 1.4477 | 0.1800 |
| Naively merged Ridge | 2.2707 | 1.7243 | −0.3096 |
| Merged Ridge, separate intercepts | 1.7938 | 1.4478 | 0.1827 |
| Adaptive merged Ridge | 1.7938 | 1.4460 | 0.1827 |

Naive merging substantially worsened predictions. Source adjustment removed most of that damage, but adaptive merging
improved RMSE by only **0.0030 t/ha (0.16%)** over Lacuna alone. Its 95% interval, **−0.0076 to +0.0013 t/ha**,
includes no improvement. The result is a reproducible merged dataset and a fair baseline; improved prediction from
adding 2024 remains unproven.

Evidence: [merge explanation](MERGE_RESULTS.md), [exact scores](../../data/runs/zimbabwe_merge_v1/metrics.csv),
[paired uncertainty](../../data/runs/zimbabwe_merge_v1/paired_differences.csv).
