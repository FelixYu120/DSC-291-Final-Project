# Scripts

Run every command from the repository root with the project Python environment. For data and report locations,
use the [Zimbabwe project guide](../docs/zimbabwe/README.md).

```text
scripts/
  step1 ... step8         the data pipeline: labels, splits, imagery, database, checks, Zimbabwe handoff
  step9 ... step15        the Zimbabwe experiments (Felix); their paths are recorded in the v2 releases
  get_all_data.py         runs the data steps in order
  baselines/              R0/R1/A1 baseline tables and the data v1 against v2 comparison
  quality/                the data-quality audit and the review stages
  verification/           independent checkers, the R² audit and the recorded-code replay
  paper/                  builds the two DOCX files in docs/paper/ from their Markdown
```

The root of `scripts/` holds only numbered steps and `get_all_data.py`. Steps 8–15 stay at the root because the v2
releases record their exact paths and SHA-256 (`data/runs/*_v2/manifest.json`), and the code checks these again
when it runs. A move would need a new release. Everything that is not a numbered step is in a subfolder.

Do not rebuild the shared database: step 6 would remove its Presto embeddings.

## Data pipeline: steps 1–8

Labels, splits and the weather snapshots come with the clone. The team databases are obtained separately.
These scripts remain available for deliberate source ingestion or the construction of a separate database.

| Script | Purpose |
|---|---|
| [get_all_data.py](get_all_data.py) | Label checks and Sentinel-2 download orchestration; default 48-record pilot |
| [step1_download_labels.py](step1_download_labels.py) | Download the original label sources |
| [step1b_download_zimbabwe2024_labels.py](step1b_download_zimbabwe2024_labels.py) | Download the Zimbabwe 2024 metadata |
| [step2_audit_labels.py](step2_audit_labels.py) | Produce the source audit tables |
| [step3_build_labels.py](step3_build_labels.py) | Build and validate the frozen multi-country labels |
| [step4_build_splits.py](step4_build_splits.py) | Create the frozen splits; refuse to change an existing frozen assignment |
| [step5_download_imagery.py](step5_download_imagery.py) | Sentinel-2 scene and chip download |
| [step6_build_database.py](step6_build_database.py) | Construct a database from local inputs; leaves Presto empty |
| [step7_check_data.py](step7_check_data.py) | Print read-only cohort, coverage and feature diagnostics |
| [step8_build_zimbabwe_handoff.py](step8_build_zimbabwe_handoff.py) | Clean Lacuna labels; export features, dictionary, audits and splits |

`get_all_data.py --scope all` selects all cohorts; `--batch i/n` selects a slice and `--status` reports progress.
The database schema and views are documented in [sql](../sql/README.md). Dependencies are pinned in `requirements.txt`.

### Data v2 switches

Data v2 (`docs/DECISIONS.md`, 5 and 7 Nov 2026) is additive: every switch is off by default, so each command above
still makes v1. The v2 database is a team file like v1; you need none of these to use it.

| Script | Switch | What it does |
|---|---|---|
| `step2_audit_labels.py` | `--only malawi_2022 --out-dir data/v2/audit --datum-operation EPSG:1113` | the Malawi 2022 audit with the named datum operation |
| `step3_build_labels.py` | `--version 2` | `data/v2/processed/labels_v2.parquet`; equal to v1 outside Malawi 2022; never changes an existing file |
| `step4_build_splits.py` | `--version 2` | `data/v2/splits/`: the v1 files byte for byte, the Malawi 2022 files and `malawi_2022_2023__temporal_rank.csv` |
| `step5_download_imagery.py` | `--base-run`, `--catalog-dir`, `--collection sentinel-2-l2a`, `--candidates-per-month 24` | the top-up of cloudy months, and Malawi 2022 from the older collection (offset 0 only for the 4 measured processing-baseline cases) |
| `step6_build_database.py` | `--version 2` | `data/v2/cropyield.duckdb`; refuses v1 paths and any file that holds Presto rows. Use `--workers 8` and `OPENBLAS_NUM_THREADS=1` |
| `step7_check_data.py` | `--version 2` | the report for the `labels_v2` rows on the v2 database (with Malawi 2022) |
| `baselines/baseline_table.py` | `--version 2` | `results/v2/`: folds 1–4 scored, fold 0 trains only |

## Zimbabwe experiments: steps 9–15

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

| Script | Purpose | Replay of the v1 release (recorded code) |
|---|---|---|
| [step9_compare_zimbabwe_merge.py](step9_compare_zimbabwe_merge.py) | Common-window features; Lacuna-only against merged models | `python scripts/verification/reproduce_zimbabwe.py merge` |
| [step10_diagnose_zimbabwe_transfer.py](step10_diagnose_zimbabwe_transfer.py) | Quality, representation and source-usefulness diagnostics | `python scripts/verification/reproduce_zimbabwe.py diagnosis` |
| [step11_add_zimbabwe_weather.py](step11_add_zimbabwe_weather.py) | Weather joins, normals and 46 predictors from the saved cache | `python scripts/verification/reproduce_zimbabwe.py weather` |
| [step12_compare_zimbabwe_weather.py](step12_compare_zimbabwe_weather.py) | Full-weather comparison on unchanged splits | `python scripts/verification/reproduce_zimbabwe.py weather-models` |
| [step13_compare_compact_weather.py](step13_compare_compact_weather.py) | Two/four weather summaries and overfitting checks | `python scripts/verification/reproduce_zimbabwe.py compact` |
| [step14_compare_zimbabwe_aggregation.py](step14_compare_zimbabwe_aggregation.py) | Seasonal aggregation: mean, calendar window, max, median, mode | runs from the current code; see below |
| [step15_compare_zimbabwe_multiyear.py](step15_compare_zimbabwe_multiyear.py) | Expanded 2022–2024 training on the same 2023 evaluation fields | runs from the current code; see below |

Current main has newer shared validators than the published v1 experiments, so use the replay command for steps
9–13 of v1. Step 11's original `--download-only` mode fills the weather cache; the published cache is already
committed. Model-training stages can take substantial time.

Step 14 compares the V0/V3 mean, a common-calendar control, the V2 max, the V3 median and a continuous-mode estimate,
separately for bands/indices and Lacuna-only/merged Ridge. See the [protocol](../docs/zimbabwe/AGGREGATION_PROTOCOL.md)
and the [results](../docs/zimbabwe/AGGREGATION_RESULTS.md). The [step-15 protocol](../docs/zimbabwe/MULTIYEAR_PROTOCOL.md)
keeps the original 2023 evaluation fields, screens all 2022–2024 imagery and buffers additional Lacuna training
observations. Use a new `--output` path for any deliberately changed experiment.

## baselines/

Both baseline scripts only read the team databases. They stop on a changed labels or split file, a wrong row count,
a y that differs from the labels file, or (with `--version 2`, and always for `compare_data_v2.py`) a database that
differs from its pin in `configs/`.

| Script | What it does | When |
|---|---|---|
| [baseline_table.py](baselines/baseline_table.py) | Rebuilds `results/baseline_table.md` and `results/baseline_scores.csv` (v1, all five folds), or `results/v2/` with `--version 2` (folds 1–4): Ridge on the season indices against the training mean and coordinates alone, on `s1_cc2km`. The experiments load its functions. | Any time; it needs only the database |
| [compare_data_v2.py](baselines/compare_data_v2.py) | Data v2 only. Writes `results/v2/data_v2_comparison.md` and `.csv`: A1 on v2 against A1 on v1 on the same fields (folds 1–4), and the Malawi 2022 ↔ 2023 season transfer (Spearman only, fold 0 not scored). | Any time; it needs both databases |
| [spatial_baselines.py](baselines/spatial_baselines.py) | Felix's within-cohort R0/R1/A1 run with `configs/spatial_baselines_v1.yaml` into `results/spatial_baselines/`; see the [baseline scope](../docs/quality/BASELINES.md) | Earlier comparison; kept for reproduction |

## quality/

The quality variant is separate from the frozen Zimbabwe experiments. Read the
[quality guide](../docs/quality/DATA_QUALITY.md) and the [review methods](../docs/quality/QUALITY_REMEDIATION.md).

| Script | Purpose |
|---|---|
| [audit_data_quality.py](quality/audit_data_quality.py) | Read database and label integrity; write local HTML/JSON review reports |
| [review_kenya_records.py](quality/review_kenya_records.py) | Review provider dates and repeated locations |
| [review_clouds.py](quality/review_clouds.py) | Plan/review SCL cloud masks and create separate stricter derivatives |
| [review_point_areas.py](quality/review_point_areas.py) | Explore provisional point supports and pixel overlap |
| [review_boundary_candidates.py](quality/review_boundary_candidates.py) | Review same-year predicted boundary candidates; do not replace source geometry |
| [assemble_quality_variant.py](quality/assemble_quality_variant.py) | Assemble reviewed country/cohort tables in a new local directory |

```bash
python scripts/quality/audit_data_quality.py      # read-only integrity review of the team database
```

## verification/

These scripts check saved releases; they never refit a published experiment in place.

| Script | Purpose |
|---|---|
| [reproduce_zimbabwe.py](verification/reproduce_zimbabwe.py) | Extract the recorded source revision and replay a v1 stage into a new destination; protects the original releases |
| [verify_zimbabwe_weather.py](verification/verify_zimbabwe_weather.py) | Independently verify the full-weather results |
| [verify_compact_weather.py](verification/verify_compact_weather.py) | Independently verify the compact-weather results |
| [compare_compact_candidate.py](verification/compare_compact_candidate.py) | Post-hoc benchmark comparison from saved predictions (no refit) |
| [verify_zimbabwe_aggregation.py](verification/verify_zimbabwe_aggregation.py) | Verify a step-14 release against its manifest |
| [verify_zimbabwe_multiyear.py](verification/verify_zimbabwe_multiyear.py) | Verify a step-15 release against its manifest |
| [verify_multiyear_intervals.py](verification/verify_multiyear_intervals.py) | Recompute the step-15 bootstrap intervals |
| [audit_zimbabwe_r2.py](verification/audit_zimbabwe_r2.py) | Standalone R² audit from committed prediction CSVs; no database, no fitting |

```bash
python scripts/verification/reproduce_zimbabwe.py verify-compact
python scripts/verification/reproduce_zimbabwe.py verify-weather
python scripts/verification/verify_zimbabwe_aggregation.py --release data/runs/zimbabwe_aggregation_v2 --report results/aggregation_v2/verification.json
python scripts/verification/verify_zimbabwe_multiyear.py --release data/runs/zimbabwe_multiyear_v2 --report results/multiyear_v2/verification.json
python scripts/verification/audit_zimbabwe_r2.py --release data/runs/zimbabwe_multiyear_v2 --output results/multiyear_v2
```

The recorded-code runner needs the full Git history; it verifies the original inputs and outputs and writes a new
destination. See the [reproduction details](../docs/zimbabwe/REPRODUCING.md). Its replay stages keep the old flat
script names, because they run the code of the recorded revision. Most verifiers default to the v1 release or
config; `audit_zimbabwe_r2.py` and `verify_multiyear_intervals.py` then rewrite their committed v1 receipt
(`results/aggregation/`, `results/multiyear/`). Pass `--release` and `--output`/`--report` for v2.

## paper/

The document-only [build_paper_documents.py](paper/build_paper_documents.py) (Felix) creates the two editable documents in
[docs/paper](../docs/paper/README.md) from reviewed text. It requires `python-docx`; it does not fit models or modify
scientific releases. Document rendering and visual inspection remain required after changing the text. The text
quotes the v1 runs of 7 Nov; rebuild it from the v2 releases before it goes into the report.

## Moved on 8 Nov 2026

The files kept their code; only the folder (and three names) changed, together with the one `ROOT` line in each.
Receipts written before this date record the old paths and the old file hashes.

| Old name in `scripts/` | New path |
|---|---|
| `step8_run_baseline.py` | `scripts/baselines/baseline_table.py` |
| `step9_compare_data_v2.py` | `scripts/baselines/compare_data_v2.py` |
| `run_baselines.py` | `scripts/baselines/spatial_baselines.py` |
| `audit_data_quality.py`, `review_*.py` (4), `assemble_quality_variant.py` | `scripts/quality/` |
| `reproduce_zimbabwe.py`, `verify_*.py` (5), `compare_compact_candidate.py`, `audit_zimbabwe_r2.py` | `scripts/verification/` |
| `build_paper_documents.py` (Felix, added 7 Nov) | `scripts/paper/build_paper_documents.py` |
