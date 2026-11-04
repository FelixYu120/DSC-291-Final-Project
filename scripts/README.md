# Scripts

Run everything from the repository root. The file names follow the data path, step by step.

**With the team database, start with `python scripts/audit_data_quality.py`.** This checks the stored data
and writes review reports; it does not train a model. Read [the quality guide](../docs/DATA_QUALITY.md)
before interpreting flags or starting an experiment. No data-building step is needed.
Labels and splits are frozen, and step 6 removes the Presto rows of the team database. The download/build
commands below are only for deliberately obtaining chips or building another database. Step 7 is read-only.

```bash
python scripts/get_all_data.py           # labels check and Sentinel-2 chips
python scripts/step6_build_database.py   # data/cropyield.duckdb: every table plus the views
python scripts/step7_check_data.py       # what the database holds, per cohort
```

Each step reuses what is already on disk, so running it again is cheap. `get_all_data.py` defaults to the 48-record
pilot; `--scope all` takes every cohort, and `--batch i/n` runs one of n parallel slices. The download cells of
[`notebooks/data_guide.ipynb`](../notebooks/data_guide.ipynb) start those slices for you, show a loading bar and then
run step 6. `--status` shows the progress at any time. The SQL behind step 6 lives in [`sql/`](../sql/README.md).

## Every script

| Script | What it does | When to run it |
|---|---|---|
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

The main install (`python -m pip install -r requirements.txt`) covers everything.
