# Scripts

Run everything from the repository root. The file names follow the data path, step by step.

**With the team database, steps 1–6 are unnecessary.** Labels and splits are frozen, and step 6 removes the Presto rows of the
team database. Step 7 reads diagnostics; step 8 creates the verified Zimbabwe handoff through a read-only connection.
Step 9 independently audits Zimbabwe 2024 and runs the user-requested pooled-data comparison, also read-only.
Step 10 diagnoses transfer limits using the step-9 release, richer predictors, quality/relevance policies and controls.
Step 11 caches NASA POWER weather and enriches all screened labels. Step 12 runs the weather comparison on unchanged
splits; `verify_zimbabwe_weather.py` independently checks the release, units, joins, permissions, metrics and a model replay.
Step 13 tests fixed two- and four-variable weather sets with the same folds and saved controls;
`verify_compact_weather.py` reconstructs features, checks selection/accounting, replays intervals and a selected model.

Start with `python scripts/audit_data_quality.py` for a current integrity review. This checks the stored data
and writes review reports; it does not train a model. Read [the quality guide](../docs/DATA_QUALITY.md)
before interpreting flags or starting an experiment. No data-building step is needed.
The download/build commands below are only for deliberately obtaining chips or building another database.

**Historical Zimbabwe reproduction after the merge:** use `python scripts/reproduce_zimbabwe.py verify-compact`
or the other stages in [the reproduction guide](../docs/ZIMBABWE_REPRODUCTION.md). This runs the recorded source revision
without weakening its input-hash checks. The direct step-9–13 and verifier entry points below describe that historical
implementation; the stronger shared validators on current main have intentionally different source hashes.

```bash
python scripts/get_all_data.py           # labels check and Sentinel-2 chips
python scripts/step6_build_database.py   # data/cropyield.duckdb: every table plus the views
python scripts/step7_check_data.py       # what the database holds, per cohort
```

Downloads reuse what is already on disk; model-training stages can still take substantial time. `get_all_data.py` defaults to the 48-record
pilot; `--scope all` takes every cohort, and `--batch i/n` runs one of n parallel slices. The download cells of
[`notebooks/data_guide.ipynb`](../notebooks/data_guide.ipynb) start those slices for you, show a loading bar and then
run step 6. `--status` shows the progress at any time. The SQL behind step 6 lives in [`sql/`](../sql/README.md).

## Every script

| Script | What it does | When to run it |
|---|---|---|
| `reproduce_zimbabwe.py` | Extracts recorded source into a temporary directory, verifies the historical input/output hash chain, and replays steps 9–13 or their verifiers into a new destination. | For historical Zimbabwe reproduction from current main; stages and new-output rules are in the reproduction guide |
| `review_kenya_records.py` | Reconcile Kenya dates/locations with raw workbook; write proposed date fields and duplicate-location evidence. | For the separate quality variant |
| `review_clouds.py` | Read SCL pixels for frozen scenes; cache masks and create strict monthly/seasonal derivatives by country/cohort. | `plan` first, then `review`; no reflectance archive download or source edits |
| `review_point_areas.py` | Create labelled buffer supports and measure their geometry against Malawi polygons under synthetic offsets. | For point-area sensitivity, not field-boundary recovery |
| `review_boundary_candidates.py` | Fetch same-year FTW predictions by bounded HTTP range reads; report nearby/ambiguous matches. | Pilot first; predictions never replace source boundaries |
| `assemble_quality_variant.py` | Combine completed reviews into separate country/cohort tables and an HTML report. | After reviews; see `docs/QUALITY_REMEDIATION.md` |
| `audit_data_quality.py` | Reads the shared database and source labels; checks integrity and writes HTML/JSON summaries plus country/cohort review tables. Does not change inputs or run models. | First, after obtaining the team database; see `docs/DATA_QUALITY.md` |
| `run_baselines.py` | R0/R1/A1 on the frozen spatial folds for Malawi, Kenya and Lacuna; saves predictions, tuning choices, metrics and provenance. | When intentionally running the baseline experiment, after reviewing data quality; see `docs/BASELINES.md` |
| `get_all_data.py` | One command for the data steps: checks the label files, writes the window file and downloads the chips. | Only if you need the chips |
| `step1_download_labels.py` | Downloads the original provider files into `data/raw/`. | Rarely: the labels are committed |
| `step1b_download_zimbabwe2024_labels.py` | Downloads the Zimbabwe 2024 label files. | Rarely: the labels are committed |
| `step2_audit_labels.py` | Turns the provider files into the audited label CSVs in `data/audit/`. | Rarely: the outputs are committed |
| `step3_build_labels.py` | Builds `data/processed/labels_v1.parquet`, the one modelling table, and runs its checks. | Rarely: the output is committed and frozen |
| `step4_build_splits.py` | Writes the frozen split files in `data/splits/` from `labels_v1`. | Once; refuses to change a frozen file |
| `step5_download_imagery.py` | The Sentinel-2 downloader. `get_all_data.py` calls it; run it alone only for special cases. | Called by `get_all_data.py` |
| `step6_build_database.py` | Builds `data/cropyield.duckdb` from the labels, the chips and the MOSAIKS feature files that are already in `data/features/mosaiks/`. It leaves `presto_embeddings` empty. | After a download; never on the team database |
| `step7_check_data.py` | Prints what the database holds for the model rows: coverage, clear share per month, feature ranges, haze, greenest month, signal per cohort-year. | After every database build |
| `step8_build_zimbabwe_handoff.py` | Independently checks raw Zimbabwe labels against frozen data; exports cleaned labels, allowlisted seasonal/monthly features, explicit splits, dictionary, audit and hashes. | For the midterm data handoff; `--output` chooses a separate release directory |
| `step9_compare_zimbabwe_merge.py` | Exports the complete harmonized Zimbabwe label catalog and compares Lacuna-only versus pooled training using nested spatial CV, common features, cohort adaptation and zero sensitivities. | For the merge experiment; fold 0 is never fit/scored; `--output` selects a new immutable release |
| `step10_diagnose_zimbabwe_transfer.py` | Tests why pooling helps little: error decomposition, cut agreement, source learnability, monthly/Presto features, quality/relevance filtering, shuffled labels, matched subsets and learning curves. | Requires the step-9 release; nested method selection, historical fold-0 protection and separate immutable outputs |
| `step11_add_zimbabwe_weather.py` | Downloads 1991–2024 NASA POWER MERRA-2 rain/temperature for 97 cells; exports 46 weather features on all 6,598 labels, monthly tables, normals, grid mapping and exact request provenance. | `--download-only` fills the cache; default build is offline; `--output` chooses another immutable release |
| `step12_compare_zimbabwe_weather.py` | Tests nine weather models against four unchanged saved controls on the original target/source split permissions. | Requires steps 9–11 and the pinned database for hash verification; never fits/scores target fold 0 |
| `verify_zimbabwe_weather.py` | Independently reconstructs weather features, checks source distances and identical controls, replays paired bootstrap intervals and a selected model. | After step 12; optional `--report PATH` saves the verification receipt |
| `step13_compare_compact_weather.py` | Tests two/four fixed weather summaries across ten new arms, retains nine controls, and exports training gaps and spatial-group/weather-cell intervals. | Requires steps 9–12; same splits, no fold-0 fitting/scoring; `--output` chooses a new immutable release |
| `verify_compact_weather.py` | Independently reconstructs early-season weather, checks all 19 arms and frozen splits, replays both bootstrap schemes and a selected merged tree. | After step 13; `--output PATH` selects the verification receipt |
| `compare_compact_candidate.py` | Compares the best observed compact arm with existing benchmarks without refitting; reports spatial-group and weather-cell intervals. | After step 13; explicitly post-hoc, not the primary comparison |

The main install (`python -m pip install -r requirements.txt`) covers everything.
