# Lacuna plus Zimbabwe 2024: results

## Primary comparison

The pre-specified adaptive merge has RMSE **not clearly different** than Lacuna-only Ridge under this protocol.
Paired ΔRMSE (adaptive − Lacuna only): **-0.0036 t/ha**;
95% spatial-group bootstrap interval **[-0.0084, +0.0007]**.
Source-to-target training weight ratios chosen internally: fold 1: 1, fold 2: 1, fold 3: 1, fold 4: 1.
A ratio of zero means auxiliary data were rejected for that fold, not used successfully.

This is exploratory nested spatial cross-validation, not a new blind-test result. Both methods predict the same
**1,504 Lacuna 2023 fields**. Historical fold 0 (**376 fields**) is
excluded from every model fit and score. Auxiliary rows near it are excluded too. Source observations are 2024,
so this is a retrospective data-sharing experiment, not a real-time 2023 forecasting result.

## Complete results

| Method | RMSE t/ha | MAE t/ha | Bias t/ha | R² | Spearman |
|---|---:|---:|---:|---:|---:|
| train_mean | 1.9881 | 1.6217 | -0.0000 | -0.004 | -0.083 |
| lacuna_only | 1.7968 | 1.4477 | -0.0137 | 0.180 | 0.440 |
| pooled_naive | 2.0858 | 1.5785 | -1.0589 | -0.105 | 0.439 |
| pooled_intercept | 1.7923 | 1.4478 | -0.0041 | 0.184 | 0.447 |
| pooled_adaptive | 1.7932 | 1.4457 | -0.0202 | 0.183 | 0.443 |
| lacuna_tree | 1.8026 | 1.4413 | -0.0133 | 0.175 | 0.431 |
| pooled_tree | 1.7948 | 1.4322 | -0.0408 | 0.182 | 0.439 |

All negative predictions are clipped to zero by the same rule. Metrics are within Lacuna only; no score combines
the target and source outcome distributions. `paired_differences.csv` contains every uncertainty interval;
the primary method was specified before the run. The v1 positive-only and zero-weight arms are not run: the `include_primary`
pool holds no zeros, so both would equal the primary adaptive arm. Tree comparisons are sensitivity analyses.

## What was merged and corrected

- **6,598** screened labels in the complete harmonized catalog: all
  **2,266** Lacuna 2022/2023 labels plus all screened 2024 labels.
  The controlled comparison uses **1,880** primary Lacuna 2023 labels.
  The existing three inconsistent raw Lacuna conversions remain excluded.
- **5,055** raw 2024 Zimbabwe maize records inspected. **723** have
  explicitly missing yields. These are distinguishable from **1,874** recorded zero yields.
- **4,332** 2024 labels pass the independent measurement audit. Training rows follow
  `labels_v1.include_primary`: **2,458** rows. The **1,874**
  excluded rows are the recorded zeros (`zimbabwe_2024_zero_likely_not_measured`); they stay in the catalog only.
  **42** training rows have one measured box. Their available-box averages are respected.
- No blanket multiplicative conversion was needed: available per-box yields equal dry kg × 0.25, and available-box
  averages equal reported field yield. This confirms numeric consistency, not physical moisture equivalence.
- **2,456** source rows meet common-window feature eligibility before fold-specific spatial buffering.
- Both cohorts use December–June aggregates, the same ten spectral predictors, and at least four observed months.
  `combined_data.parquet` preserves the harmonized labels, source/season/management metadata, eligibility and features.
  Every training row has `include_primary = True` (config `training_rows: include_primary`);
  the run stops if a fit pool holds another row.

## How incompatibilities were handled

The primary model centers/scales targets separately within each training cohort and learns shared plus cohort-specific
feature slopes. Predictions are restored to the Lacuna training scale. This makes the source contribution invariant
to a fixed positive affine change of source label units, while leaving the physical exported labels unchanged.
It does not identify a true moisture conversion or distinguish drought from provider effects. Source weight is
selected by inner target-only validation and may be zero. Unknown irrigation/intercropping are not fabricated.
The naive merge and intercept-only comparison quantify how much these modeling choices matter.

Every inner and outer split independently removes source points within 2 km of protected target observations.
Clipping and feature scaling use target-training rows only; cohort centering and outcome scaling use allowed training
rows only. Neither outer evaluation outcomes nor reserved outcomes enter tuning or normalization.

The full problem/action/remaining-limitation register is in `PROTOCOL.md`. Issues that cannot be inferred from
the released files are explicitly modeled or bounded through sensitivity analyses, not declared physically solved.

## Reproduce and inspect

From the repository root: `python scripts/step9_compare_zimbabwe_merge.py --config configs/zimbabwe_merge_v2.json`.
Config: `configs/zimbabwe_merge_v2.json`. Results are generated in `data/runs/zimbabwe_merge_v2/`.
Use a new `--output` directory when changing the code/config. The manifest records inputs, code and outputs.

- `source_2024_audit.csv`: all raw 2024 maize records, measurement checks and exclusion reasons.
- `source_spatial_permissions.csv`: auxiliary access and distances for every outer and inner fold (inner 0 denotes outer fit).
- `target_memberships.csv`: exact target fit, validation, evaluation and reserved memberships.
- `tuning.csv`: all inner-CV candidates and scores; `selected_parameters.csv`: chosen parameters and source counts.
- `predictions.csv`: paired out-of-fold target predictions; `metrics.csv` and `fold_metrics.csv`: results.
- `paired_differences.csv`: paired group-bootstrap intervals, with the pre-specified primary comparison marked.
- `combined_data.parquet` / `.csv`: harmonized data, including reserved rows clearly marked as fold 0.
- `harmonized_labels.parquet`: complete screened catalog, including Lacuna 2022 and non-primary management groups.
  `comparison_candidate` distinguishes inclusion in this experiment; null feature eligibility means not evaluated here.

![Comparison](comparison.png)

Sources: [Lacuna](https://doi.org/10.5281/zenodo.10060610),
[2024 paper](https://arxiv.org/html/2511.12999v1),
[shared/domain-specific feature augmentation](https://aclanthology.org/P07-1033/).
