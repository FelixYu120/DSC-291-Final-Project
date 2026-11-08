# Scripts

Run everything from the repository root. The file names follow the data path, step by step.

**With the team database you run none of the data steps.** Labels and splits are frozen, and step 6 never fills Presto:
it refuses to overwrite a database that holds Presto rows, such as the v1 team copy (build into another `--db` path).
Run the data steps only to get the chips or to rebuild the data on purpose. Step 8 only reads the data:
`python scripts/step8_run_baseline.py` rebuilds the baseline table.

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
| `get_all_data.py` | One command for the data steps: checks the label files, writes the window file and downloads the chips. | Only if you need the chips |
| `step1_download_labels.py` | Downloads the original provider files into `data/raw/`. | Rarely: the labels are committed |
| `step1b_download_zimbabwe2024_labels.py` | Downloads the Zimbabwe 2024 label files. | Rarely: the labels are committed |
| `step2_audit_labels.py` | Turns the provider files into the audited label CSVs in `data/audit/`. | Rarely: the outputs are committed |
| `step3_build_labels.py` | Builds `data/processed/labels_v1.parquet`, the one modelling table, and runs its checks. | Rarely: the output is committed and frozen |
| `step4_build_splits.py` | Writes the frozen split files in `data/splits/` from `labels_v1`. | Once; refuses to change a frozen file |
| `step5_download_imagery.py` | The Sentinel-2 downloader. `get_all_data.py` calls it; run it alone only for special cases. | Called by `get_all_data.py` |
| `step6_build_database.py` | Builds `data/cropyield.duckdb` from the labels, the chips and the MOSAIKS feature files that are already in `data/features/mosaiks/`. It leaves `presto_embeddings` empty. | After a download; never on the team database |
| `step7_check_data.py` | Prints what the database holds for the model rows: coverage, clear share per month, feature ranges, haze, greenest month, signal per cohort-year. | After every database build |
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

The main install (`python -m pip install -r requirements.txt`) covers everything.
