# Results directory

This page indexes the results across the repository. Zimbabwe experiment reports stay with their frozen datasets
under `data/runs/`; each report is named **`RESULTS.md`**. They are linked here rather than duplicated or relocated.

## Zimbabwe experiments

| Experiment | Readable report | Scores | Predictions |
|---|---|---|---|
| Basic features: Lacuna-only vs merged | [RESULTS.md](../data/runs/zimbabwe_merge_v1/RESULTS.md) · [explanation](../docs/zimbabwe/MERGE_RESULTS.md) | [metrics.csv](../data/runs/zimbabwe_merge_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_merge_v1/predictions.csv) |
| Why transfer helps little | [RESULTS.md](../data/runs/zimbabwe_transfer_diagnosis_v1/RESULTS.md) · [explanation](../docs/zimbabwe/TRANSFER_FINDINGS.md) | [metrics.csv](../data/runs/zimbabwe_transfer_diagnosis_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_transfer_diagnosis_v1/predictions.csv) |
| Full weather feature set | [RESULTS.md](../data/runs/zimbabwe_weather_v1/RESULTS.md) | [metrics.csv](../data/runs/zimbabwe_weather_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_weather_v1/predictions.csv) |
| Two/four weather features | [RESULTS.md](../data/runs/zimbabwe_weather_compact_v1/RESULTS.md) | [metrics.csv](../data/runs/zimbabwe_weather_compact_v1/metrics.csv) | [predictions.csv](../data/runs/zimbabwe_weather_compact_v1/predictions.csv) |

Latest satellite follow-up: [aggregation V0–V3 results](../data/runs/zimbabwe_aggregation_v1/RESULTS.md), [scores](../data/runs/zimbabwe_aggregation_v1/metrics.csv), [predictions](../data/runs/zimbabwe_aggregation_v1/predictions.csv), and [short explanation](../docs/zimbabwe/AGGREGATION_RESULTS.md).

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
