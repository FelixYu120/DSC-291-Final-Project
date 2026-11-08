# Zimbabwe project guide

This is the entry point for Felix's data preparation and the subsequent merge/weather experiments.
Read the [one-page Ridge summary](SUMMARY.md), then follow [Data Guide 2](../../notebooks/data_guide_2_zimbabwe.ipynb)
for the complete walkthrough. [METHODS.md](METHODS.md) contains the current concise findings and technical appendix.

The [paper folder](../paper/README.md) contains Felix and Florian's manuscript section, a one-page team summary and every saved result with repeated controls identified.

## Work added, in order

Paths below are relative to the repository root. Scripts are the original stage entry points;
use the [recorded-code runner](REPRODUCING.md) to reproduce steps 9–13 on current main.

| Step | Added work | Data and results | Implementation |
|---|---|---|---|
| 8 | Audit Lacuna, clean labels, export features/dictionary and explicit splits | [Handoff](../../data/processed/zimbabwe_midterm_v1/README.md), [audit](../../data/processed/zimbabwe_midterm_v1/audit_report.md) | [Script](../../scripts/step8_build_zimbabwe_handoff.py), [handoff.py](../../src/cropyield/data/handoff.py) |
| 9 | Align units and imagery windows; compare Lacuna-only and merged training | [RESULTS.md](../../data/runs/zimbabwe_merge_v1/RESULTS.md), [explanation](MERGE_RESULTS.md) | [Script](../../scripts/step9_compare_zimbabwe_merge.py), [zimbabwe_merge.py](../../src/cropyield/experiments/zimbabwe_merge.py) |
| 10 | Diagnose source quality, representation limits and weak transfer | [RESULTS.md](../../data/runs/zimbabwe_transfer_diagnosis_v1/RESULTS.md), [explanation](TRANSFER_FINDINGS.md) | [Script](../../scripts/step10_diagnose_zimbabwe_transfer.py), [zimbabwe_diagnosis.py](../../src/cropyield/experiments/zimbabwe_diagnosis.py) |
| 11 | Add NASA POWER rainfall/temperature with exact provenance | [Weather data](../../data/processed/zimbabwe_weather_v1/README.md), [raw snapshots](../../data/raw/nasa_power_zimbabwe_v1/) | [Script](../../scripts/step11_add_zimbabwe_weather.py), [weather.py](../../src/cropyield/data/weather.py) |
| 12 | Compare full-weather models using the same splits | [RESULTS.md](../../data/runs/zimbabwe_weather_v1/RESULTS.md) | [Script](../../scripts/step12_compare_zimbabwe_weather.py), [zimbabwe_weather.py](../../src/cropyield/experiments/zimbabwe_weather.py) |
| 13 | Test two/four weather summaries and overfitting | [RESULTS.md](../../data/runs/zimbabwe_weather_compact_v1/RESULTS.md) | [Script](../../scripts/step13_compare_compact_weather.py), [zimbabwe_weather_compact.py](../../src/cropyield/experiments/zimbabwe_weather_compact.py) |

Step 14 adds [seasonal aggregation V0–V3](AGGREGATION_RESULTS.md): [script](../../scripts/step14_compare_zimbabwe_aggregation.py), [fixed protocol](AGGREGATION_PROTOCOL.md), [complete results](../../data/runs/zimbabwe_aggregation_v1/RESULTS.md). This new experiment runs directly from current main and compares each aggregation separately on bands and indices.

Step 15 adds [expanded Lacuna/2024 training](MULTIYEAR_RESULTS.md): [script](../../scripts/step15_compare_zimbabwe_multiyear.py), [protocol](MULTIYEAR_PROTOCOL.md), [complete results](../../data/runs/zimbabwe_multiyear_v1/RESULTS.md). It audits all 6,598 labels, excludes fields with insufficient imagery, and keeps the same 1,504 evaluation fields. The [R² review packet](R2_AUDIT.md) explains the calculation and the difference between band and index scores.

## Choose the dataset you need

| Purpose | File | Contents |
|---|---|---|
| Original cleaned Lacuna handoff | [cleaned_labels.csv](../../data/processed/zimbabwe_midterm_v1/cleaned_labels.csv) | 2,266 screened 2022/2023 labels |
| Original primary Lacuna modeling table | [model_table.csv](../../data/processed/zimbabwe_midterm_v1/model_table.csv) | 1,880 2023 fields and 10 seasonal predictors, before the merge experiment's common-window rebuild |
| Complete combined label catalog | [harmonized_labels.parquet](../../data/runs/zimbabwe_merge_v1/harmonized_labels.parquet) | 6,598 screened Lacuna/2024 labels with provenance |
| Basic-feature merge comparison | [combined_data.csv](../../data/runs/zimbabwe_merge_v1/combined_data.csv) | 6,212 candidates with 10 common December–June vegetation features and eligibility flags |
| All labels enriched with weather | [harmonized_labels_weather.csv](../../data/processed/zimbabwe_weather_v1/harmonized_labels_weather.csv) | 6,598 labels and 46 weather predictors |
| Model comparison with full weather | [combined_data_weather.csv](../../data/runs/zimbabwe_weather_v1/combined_data_weather.csv) | Candidate rows, metadata, monthly imagery and weather |
| Small weather feature sets | [compact_weather.csv](../../data/runs/zimbabwe_weather_compact_v1/compact_weather.csv) | Candidate IDs and compact weather values; full predictors are in the adjacent `features_compact2.parquet` / `features_compact4.parquet` |

CSV is the inspection copy; Parquet preserves types. Join by `obs_id`, and by `(obs_id, month)` for monthly tables.
Do not train on every row of a candidate table: apply eligibility flags and the recorded per-fit memberships/permissions.
The merge comparisons evaluate 1,504 Lacuna 2023 fields; 376 historical fold-0 fields remain excluded from fitting/scoring.

The [aggregation release](../../data/runs/zimbabwe_aggregation_v1/) contains `observations.csv`, `monthly_observations.parquet`, `features.parquet`, an explicit `feature_dictionary.json` and `window_audit.csv`. It preserves the same candidate IDs and per-fit memberships.

The [expanded-training release](../../data/runs/zimbabwe_multiyear_v1/) adds all-label eligibility and monthly coverage audits plus fold-specific permissions for the 217 additional Lacuna 2023 fields. Its eligible pools contain 2,097 Lacuna 2023 fields and 4,330 Zimbabwe 2024 fields before reserved/evaluation exclusions and spatial buffering. All 169 Lacuna 2022 fields are audited but excluded for inadequate common-window imagery.

## Find the evidence

Each modeling release has `RESULTS.md`, `metrics.csv`, `fold_metrics.csv`, `predictions.csv`, tuning records,
`target_memberships.csv`, `source_spatial_permissions.csv` and `manifest.json`. The manifest records input/output hashes.
The [results index](../../results/README.md) links directly to the scores and reports.

Settings are in [configs](../../configs/README.md); the prespecified protocols are indexed in [docs](../README.md).
Existing release files stay in their original directories so hashes, scripts and notebooks continue to agree.
The shared DuckDB remains the input database; the cleaned/enriched tables are separate versioned exports.

The [quality-review work](../quality/QUALITY_REMEDIATION.md) from the earlier branch is also on main.
Its cloud/date/location variant is separate from these frozen experiment inputs.
