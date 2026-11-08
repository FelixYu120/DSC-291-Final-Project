# Scripts

Run commands from the repository root with the project Python environment. For data/report locations,
use the [Zimbabwe project guide](../docs/zimbabwe/README.md).

## Common tasks

```bash
# Read-only integrity review of the existing team database:
python scripts/audit_data_quality.py

# Verify published Zimbabwe results using their recorded source revision:
python scripts/reproduce_zimbabwe.py verify-compact
python scripts/reproduce_zimbabwe.py verify-weather

# Generate a new Lacuna handoff with current source/documentation:
python scripts/step8_build_zimbabwe_handoff.py --output data/processed/zimbabwe_midterm_rebuild
```

These commands require the shared team database. The Zimbabwe notebook's default walkthrough does not.
The recorded-code runner requires full Git history, verifies original inputs/outputs and writes a new destination.
See [reproduction details](../docs/zimbabwe/REPRODUCING.md). Do not rebuild the shared database: step 6 would remove its Presto embeddings.

## Rule-compliant v2 runs (8 Nov 2026)

New work uses the v2 configs. Steps 8, 14 and 15 default to v2; steps 9–13 still default to their v1 config, so
pass the v2 config. Run them in this order; each writes `data/runs/<experiment>/` and refuses to overwrite a
different release.

```bash
python scripts/step8_build_zimbabwe_handoff.py                                                     # v2 is the default
python scripts/step9_compare_zimbabwe_merge.py --config configs/zimbabwe_merge_v2.json
python scripts/step10_diagnose_zimbabwe_transfer.py --config configs/zimbabwe_transfer_diagnosis_v2.json
python scripts/step11_add_zimbabwe_weather.py --config configs/zimbabwe_weather_v2.json
python scripts/step12_compare_zimbabwe_weather.py --config configs/zimbabwe_weather_v2.json
python scripts/step13_compare_compact_weather.py --config configs/zimbabwe_weather_compact_v2.json
python scripts/step14_compare_zimbabwe_aggregation.py                                              # v2 is the default
python scripts/step15_compare_zimbabwe_multiyear.py                                                # v2 is the default
```

## Zimbabwe pipeline: steps 8–13 (v1, 7 Nov)

The stage files remain the implementation entry points. Current main has newer shared validators than the published
experiments, so use the replay stage in the final column for steps 9–13. Model-training stages can take substantial time.

| Script | Purpose | Current replay command |
|---|---|---|
| [step8_build_zimbabwe_handoff.py](step8_build_zimbabwe_handoff.py) | Clean Lacuna labels; export features, dictionary, audits and splits | Direct command above, with a new output path |
| [step9_compare_zimbabwe_merge.py](step9_compare_zimbabwe_merge.py) | Common-window features; Lacuna-only vs merged models | `python scripts/reproduce_zimbabwe.py merge` |
| [step10_diagnose_zimbabwe_transfer.py](step10_diagnose_zimbabwe_transfer.py) | Quality, representation and source-usefulness diagnostics | `python scripts/reproduce_zimbabwe.py diagnosis` |
| [step11_add_zimbabwe_weather.py](step11_add_zimbabwe_weather.py) | Weather joins, normals and 46 predictors from the saved cache | `python scripts/reproduce_zimbabwe.py weather` |
| [step12_compare_zimbabwe_weather.py](step12_compare_zimbabwe_weather.py) | Full-weather comparison on unchanged splits | `python scripts/reproduce_zimbabwe.py weather-models` |
| [step13_compare_compact_weather.py](step13_compare_compact_weather.py) | Two/four weather summaries and overfitting checks | `python scripts/reproduce_zimbabwe.py compact` |
| [verify_zimbabwe_weather.py](verify_zimbabwe_weather.py) | Independently verify full-weather results | `python scripts/reproduce_zimbabwe.py verify-weather` |
| [verify_compact_weather.py](verify_compact_weather.py) | Independently verify compact-weather results | `python scripts/reproduce_zimbabwe.py verify-compact` |
| [compare_compact_candidate.py](compare_compact_candidate.py) | Post-hoc benchmark comparison from saved predictions | `python scripts/reproduce_zimbabwe.py candidate` |
| [reproduce_zimbabwe.py](reproduce_zimbabwe.py) | Extract the recorded source and protect original releases | Optional `--output NEW_PATH` for any replay |

Step 11's original `--download-only` mode fills the weather cache; the published cache is already committed.
The other replay stages use recorded upstream releases, not arbitrary newly generated replacements.

## New seasonal aggregation comparison: step 14

[step14_compare_zimbabwe_aggregation.py](step14_compare_zimbabwe_aggregation.py) runs from current main:

```bash
python scripts/step14_compare_zimbabwe_aggregation.py --output data/runs/zimbabwe_aggregation_replay
python scripts/verify_zimbabwe_aggregation.py
```

It compares V0/V3 mean, V1 crop-date preharvest mean, a common-calendar control, V2 max, V3 median and a continuous-mode estimate, separately for bands/indices and Lacuna-only/merged Ridge. Original memberships and source permissions are reused. Use a new `--output` path for any deliberately changed experiment. See the [protocol](../docs/zimbabwe/AGGREGATION_PROTOCOL.md) and [results](../docs/zimbabwe/AGGREGATION_RESULTS.md).

## Expanded training comparison and R² audit: step 15

The expanded-training comparison runs as a separate step 15:

```bash
python scripts/step15_compare_zimbabwe_multiyear.py --output data/runs/zimbabwe_multiyear_replay
python scripts/verify_zimbabwe_multiyear.py
python scripts/verify_multiyear_intervals.py
python scripts/audit_zimbabwe_r2.py
```

The [step-15 protocol](../docs/zimbabwe/MULTIYEAR_PROTOCOL.md) preserves the original 2023 evaluation fields, screens all 2022–2024 imagery and buffers additional Lacuna training observations. The standalone R² audit reads committed prediction CSVs and requires no database or model fitting; its default verifies the original step-14 scores. Use `--release data/runs/zimbabwe_multiyear_v1 --output results/multiyear` for the expanded comparison.

## Quality review and earlier baselines

The quality variant is separate from the frozen Zimbabwe experiments. Read the
[quality guide](../docs/quality/DATA_QUALITY.md) and [review methods](../docs/quality/QUALITY_REMEDIATION.md).

| Script | Purpose |
|---|---|
| [audit_data_quality.py](audit_data_quality.py) | Read database/label integrity and write local HTML/JSON review reports |
| [review_kenya_records.py](review_kenya_records.py) | Review provider dates and repeated locations |
| [review_clouds.py](review_clouds.py) | Plan/review SCL cloud masks and create separate stricter derivatives |
| [review_point_areas.py](review_point_areas.py) | Explore provisional point supports and pixel overlap |
| [review_boundary_candidates.py](review_boundary_candidates.py) | Review same-year predicted boundary candidates; do not replace source geometry |
| [assemble_quality_variant.py](assemble_quality_variant.py) | Assemble reviewed country/cohort tables in a new local directory |
| [run_baselines.py](run_baselines.py) | Reproduce earlier within-cohort R0/R1/A1 comparisons; see [baseline scope](../docs/quality/BASELINES.md) |

## Original data construction: steps 1–7

Labels, splits and the weather snapshots come with the clone. The team database is obtained separately.
These scripts remain available for deliberate source ingestion or construction of a separate database.

| Script | Purpose |
|---|---|
| [get_all_data.py](get_all_data.py) | Label checks and Sentinel-2 download orchestration; default 48-record pilot |
| [step1_download_labels.py](step1_download_labels.py) | Download original label sources |
| [step1b_download_zimbabwe2024_labels.py](step1b_download_zimbabwe2024_labels.py) | Download Zimbabwe 2024 metadata |
| [step2_audit_labels.py](step2_audit_labels.py) | Produce source audit tables |
| [step3_build_labels.py](step3_build_labels.py) | Build and validate frozen multi-country labels |
| [step4_build_splits.py](step4_build_splits.py) | Create frozen splits; refuse to change an existing frozen assignment |
| [step5_download_imagery.py](step5_download_imagery.py) | Sentinel-2 scene/chip download implementation |
| [step6_build_database.py](step6_build_database.py) | Construct a database from local inputs; leaves Presto empty |
| [step7_check_data.py](step7_check_data.py) | Print read-only cohort, coverage and feature diagnostics |

`get_all_data.py --scope all` selects all cohorts; `--batch i/n` selects a slice and `--status` reports progress.
Database schema and views are documented in [sql](../sql/README.md). Dependencies are pinned in `requirements.txt`.

## Baseline table and data v2: `step8_run_baseline.py`, `step9_compare_data_v2.py`

These two scripts share their step numbers with the Zimbabwe steps 8 and 9 above; the file names differ.
Both only read the team databases and stop if a database differs from its pin.

| Script | What it does | When |
|---|---|---|
| `step8_run_baseline.py` | Rebuilds `results/baseline_table.md` and `results/baseline_scores.csv`: Ridge on the season indices against the training mean and coordinates alone, on `s1_cc2km`. It stops on a changed labels or split file, a wrong row count or a y that differs from `labels_v1` (the v1 path does not check the database pin; `--version 2` does). | Any time; it needs only the database |
| `step9_compare_data_v2.py` | Data v2 only. Writes `results/v2/data_v2_comparison.md` and `.csv`: A1 on v2 against A1 on v1 on the same fields (folds 1–4), and the Malawi 2022 ↔ 2023 season transfer (Spearman only, fold 0 not scored). It stops if a database differs from its pin in `configs/`. | Any time; it needs both databases |

## Data v2 switches

Data v2 (`docs/DECISIONS.md`, 5 and 7 Nov 2026) is additive: every switch is off by default, so each command above still
makes v1. The v2 database is a team file like v1; you need none of these to use it.

| Script | Switch | What it does |
|---|---|---|
| `step2_audit_labels.py` | `--only malawi_2022 --out-dir data/v2/audit --datum-operation EPSG:1113` | the Malawi 2022 audit with the named datum operation |
| `step3_build_labels.py` | `--version 2` | `data/v2/processed/labels_v2.parquet`; equal to v1 outside Malawi 2022; never changes an existing file |
| `step4_build_splits.py` | `--version 2` | `data/v2/splits/`: the v1 files byte for byte, the Malawi 2022 files and `malawi_2022_2023__temporal_rank.csv` |
| `step5_download_imagery.py` | `--base-run`, `--catalog-dir`, `--collection sentinel-2-l2a`, `--candidates-per-month 24` | the top-up of cloudy months, and Malawi 2022 from the older collection (offset 0 only for the 4 measured processing-baseline cases) |
| `step6_build_database.py` | `--version 2` | `data/v2/cropyield.duckdb`; refuses v1 paths and any file that holds Presto rows. Use `--workers 8` and `OPENBLAS_NUM_THREADS=1` |
| `step7_check_data.py` | `--version 2` | the report for the `labels_v2` rows on the v2 database (with Malawi 2022) |
| `step8_run_baseline.py` | `--version 2` | `results/v2/`: folds 1–4 scored, fold 0 trains only |
