# Scripts

Run everything from the repository root. Three commands give a teammate all the data:

```bash
python scripts/get_data.py                    # 1. labels check, Presto weights, Sentinel-2 chips
python scripts/features/mosaiks_features.py   # 2. MOSAIKS features from the chips
python scripts/build_database.py              # 3. data/cropyield.duckdb: every table plus the views
```

Each step reuses what is already on disk, so running it again is cheap. Step 1 defaults to the 48-record
pilot; `--scope all` takes every cohort (use the cluster and `--batch i/n` for that). The SQL behind step 3
lives in [`sql/`](../sql/README.md).

## Every script

| Folder | Script | What it does | When to run it |
|---|---|---|---|
| `scripts/` | `get_data.py` | One command for steps 1a–1c below: checks the label files, fetches the Presto weights, writes the window file and downloads the chips. | Always; first |
| `scripts/features/` | `mosaiks_features.py` | MOSAIKS random convolutional features for every downloaded chip: one vector per field and month, and a season mean. | After every download |
| `scripts/` | `build_database.py` | Builds `data/cropyield.duckdb` from the labels, the chips, the Presto embeddings and the MOSAIKS features. | After step 2 |
| `scripts/imagery/` | `download_sentinel2.py` | The Sentinel-2 downloader (1c). `get_data.py` calls it; run it alone only for special cases. | Called by step 1 |
| `scripts/imagery/` | `select_pilot.py` | Writes `configs/sentinel2_windows_pilot48.csv`, the 48-record pilot and its windows (1b). | Called by step 1 |
| `scripts/models/` | `get_presto.py` | Downloads and verifies the pretrained Presto weights (1a). | Called by step 1 |
| `scripts/labels/` | `download_datasets.py`, `download_vision_guided_yield_data.py` | Download the original provider files into `data/raw/`. | Rarely: the labels are committed |
| `scripts/labels/` | `audit_datasets.py` | Turns the provider files into the audited label CSVs in `data/audit/`. | Rarely: the outputs are committed |
| `scripts/labels/` | `build_labels.py` | Builds `data/processed/labels_v1.parquet`, the one modelling table, and runs its checks. | Rarely: the output is committed and frozen |
| `scripts/` | `build_splits.py` | Writes the frozen split files in `data/splits/` from `labels_v1`. | Once; refuses to change a frozen file |
| `scripts/` | `check_data.py` | Prints what the database holds for the model rows: coverage, clear share per month, feature ranges, haze, greenest month, signal per cohort-year. | After every database build |
| `scripts/` | `run_experiment.py` | Runs one config from `configs/`: frozen splits in, rows in `results/metrics.csv` out. | For every result |
| `scripts/` | `run_transfer.py` | Trains on one cohort and scores another, at three harmonization levels: raw t/ha, calibrated level, rank only. | After B0 on every cohort it names |
| `scripts/cluster/` | `run_batches.sh`, `download_all.sbatch`, `after_download.sh` | The full download in parallel slices (any Linux machine, or a SLURM array), then steps 2 and 3. See `scripts/cluster/README.md`. | For `--scope all` |

The main install (`python -m pip install -e ".[dev,presto]"`) covers everything.
