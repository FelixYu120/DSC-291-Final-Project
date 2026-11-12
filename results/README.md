# Results directory

This page indexes the results across the repository. The v1 Zimbabwe reports stay with their frozen datasets under
`data/runs/`; each report is named **`RESULTS.md`**. The v2 releases in `data/runs/*_v2/` are not tracked in Git, so
`results/*_v2/` hold byte copies of their reports and scores; do not edit those copies.

| Folder or file | What it holds | Written by | Status |
|---|---|---|---|
| [Visual atlas](visual_atlas/README.md) | Zimbabwe yield, weather, imagery and model figures, with a source index for the repository gallery | [Atlas notebook](../notebooks/zimbabwe_visual_atlas.ipynb) | descriptive figures and archived model predictions |
| [baseline_table.md](baseline_table.md), `baseline_scores.csv` | R0/R1/A1 on `s1_cc2km`, data v1, all five folds | `scripts/baselines/baseline_table.py` | history (scores fold 0) |
| [v2/](v2/baseline_table.md) | R0/R1/A1 on data v2, folds 1–4; [v1 against v2 comparison](v2/data_v2_comparison.md) | `scripts/baselines/baseline_table.py --version 2`, `scripts/baselines/compare_data_v2.py` | current |
| [merge_v2/](merge_v2/README.md), [weather_v2/](weather_v2/README.md), [aggregation_v2/](aggregation_v2/RESULTS.md), [multiyear_v2/](multiyear_v2/RESULTS.md) | Zimbabwe experiments, rule-compliant runs | steps 9–15, `scripts/verification/` | current |
| `aggregation/`, `multiyear/` | R² audit and verification receipts of the v1 releases | `scripts/verification/` | history |
| [data_quality/](data_quality/README.md), [quality_remediation/](quality_remediation/README.md) | Quality review evidence | `scripts/quality/` | reference |
| [spatial_baselines/](spatial_baselines/README.md) | Earlier within-cohort baselines | `scripts/baselines/spatial_baselines.py` | history |
| [integration/](integration/main_merge_20261107/README.md) | Receipts from consolidating the branches | merge checks of 7 Nov | reference |

The Lacuna experiments of 7–8 Nov (step-up ladder, time features, Presto) keep their results next to their code in
[experiments/](../experiments/), each with a README.

For the paper and team handoff, Felix's [one-page results summary](../docs/paper/RESULTS_SUMMARY.md), [complete appendix](../docs/paper/RESULTS_APPENDIX.md) and [full-precision ledger](../docs/paper/RESULTS_LEDGER.csv) quote the v1 runs of 7 Nov; use the v2 values in the [results notebook](../notebooks/lacuna_results_consensus.ipynb), section 6.1. The ledger distinguishes reused controls from different predictions and keeps the separate 2024 source-diagnostic population explicit.

## Zimbabwe experiments

**Use the v2 results (8 Nov).** They follow the team rules (`include_primary` training rows, label-free calendar
windows, folds 1–4 cross-validated): [merge and diagnosis](merge_v2/README.md), [weather](weather_v2/README.md),
[aggregation](aggregation_v2/RESULTS.md), [expanded training](multiyear_v2/RESULTS.md). The v1 table below is kept as
history; see `docs/DECISIONS.md` (8 Nov) for what each v1 run broke.

| Experiment | Readable report | Scores | Predictions |
|---|---|---|---|
| Basic features: Lacuna-only vs merged | [RESULTS.md](../data/runs/zimbabwe_merge_v1/RESULTS.md) · [explanation](../docs/zimbabwe/MERGE_RESULTS.md) | [metrics.csv](../data/runs/zimbabwe_merge_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_merge_v1/predictions.csv) |
| Why transfer helps little | [RESULTS.md](../data/runs/zimbabwe_transfer_diagnosis_v1/RESULTS.md) · [explanation](../docs/zimbabwe/TRANSFER_FINDINGS.md) | [metrics.csv](../data/runs/zimbabwe_transfer_diagnosis_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_transfer_diagnosis_v1/predictions.csv) |
| Full weather feature set | [RESULTS.md](../data/runs/zimbabwe_weather_v1/RESULTS.md) | [metrics.csv](../data/runs/zimbabwe_weather_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_weather_v1/predictions.csv) |
| Two/four weather features | [RESULTS.md](../data/runs/zimbabwe_weather_compact_v1/RESULTS.md) | [metrics.csv](../data/runs/zimbabwe_weather_compact_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_weather_compact_v1/predictions.csv) |

Original satellite follow-up: [aggregation V0–V3 results](../data/runs/zimbabwe_aggregation_v1/RESULTS.md), [scores](../data/runs/zimbabwe_aggregation_v1/metrics.csv), [predictions](../data/runs/zimbabwe_aggregation_v1/predictions.csv), and [short explanation](../docs/zimbabwe/AGGREGATION_RESULTS.md).

Latest comparison: [expanded Lacuna/2024 training results](../data/runs/zimbabwe_multiyear_v1/RESULTS.md), [scores](../data/runs/zimbabwe_multiyear_v1/metrics.csv), [predictions](../data/runs/zimbabwe_multiyear_v1/predictions.csv), and [coverage/results explanation](../docs/zimbabwe/MULTIYEAR_RESULTS.md). Evaluation remains the same 1,504 Lacuna 2023 fields; 2022 has insufficient imagery and is excluded.

For the R² discrepancy review, use the [full calculation and Claude review packet](../docs/zimbabwe/R2_AUDIT.md), [independent recalculation](aggregation/r2_audit.csv), and [receipt](aggregation/r2_audit.json). These identify reflectance-band and vegetation-index models separately.

The [current methods report](../docs/zimbabwe/METHODS.md) compares the experiments and explains the uncertainty.
Within each release, `fold_metrics.csv` gives fold-level scores, `paired_differences.csv` gives paired uncertainty,
`selected_parameters.csv` / `tuning.csv` document model selection, and `manifest.json` records provenance.
The basic merge comparison uses vegetation indices with Ridge; it is not a MOSAIKS/ordinary-linear-regression result.

The aggregation [verification receipt](aggregation/verification.json) checks every feature variant, original split/permission files, model metrics and the primary confidence interval.

## Data quality, earlier baselines and verification

| Directory/report | Contents |
|---|---|
| [Lacuna audit](../data/processed/zimbabwe_midterm_v1/audit_report.md) | Cleaning, exclusions, features and split checks |
| [data_quality/](data_quality/README.md) | Aggregate integrity-review evidence |
| [quality_remediation/](quality_remediation/README.md) | Separate cloud/date/location-review evidence |
| [spatial_baselines/](spatial_baselines/README.md) | Earlier within-cohort mean, coordinates and Ridge comparisons |
| [integration/main_merge_20261107/](integration/main_merge_20261107/README.md) | Verification receipts from consolidating the branches; not a new model comparison |

Historical experiments are in [_parked/results/](../_parked/results/README.md).
To reproduce current published Zimbabwe experiments, use [the reproduction guide](../docs/zimbabwe/REPRODUCING.md).
