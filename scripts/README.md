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

## Zimbabwe pipeline: steps 8–13

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
