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
| `scripts/labels/` | `audit_datasets.py`, `organize_country_data.py` | Turn the provider files into the audited label CSVs in `data/audit/` and `data/processed/`. | Rarely: the outputs are committed |
| `scripts/optional/` | `download_usda_nass.py` | U.S. county corn yields (needs an API key). Not part of the main pipeline. | Only for the U.S. extension |
| `scripts/cluster/` | `run_batches.sh`, `download_all.sbatch`, `after_download.sh` | The full download in parallel slices (any Linux machine, or a SLURM array), then steps 2 and 3. See `scripts/cluster/README.md`. | For `--scope all` |

`labels/requirements.txt` and `imagery/requirements.txt` list the extra packages of those stages; the main
install (`python -m pip install -e ".[dev,presto]"`) covers steps 1–3.
