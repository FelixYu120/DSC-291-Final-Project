# DSC-291 Final Project: field-level maize yield from Sentinel-2 in sub-Saharan Africa

Felix Yu, Florian Saewert, Liuan Lu, Pamely Zantou, Zida Jin. UCSD DSC 291, Fall 2026.

**Start with the data guide: [`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb).** It teaches the data from
zero: which files make it, where it comes from, how it is matched and split, and what X and Y look like.

**The first result: [`results/baseline_table.md`](results/baseline_table.md).** Rebuild it with
`python scripts/step8_run_baseline.py`. It takes seconds, and it needs only the database.

**Question.** Within one smallholder cohort, which Sentinel-2 representation predicts field-level maize yield best,
and how much of that skill survives in new villages, new districts and a new season? The plan is
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Get started

Clone **outside OneDrive** (for example `C:\Dev\`). Use Python 3.12 or newer. Run these commands once, from the
repository root:

```bash
python -m venv .venv
.venv\Scripts\activate                   # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt   # the exact package versions, and this repository
python -m pytest -q                      # small checks, no imagery needed
```

Labels and splits come with the clone. Then get the team database: download the file from the link in the team chat,
and put it at `data/cropyield.duckdb`. Do not rebuild it. Open
[`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb) with the `.venv` kernel, for example in VS Code, and press
Run All. Step 2 of the guide checks that your file is the team copy.

You need the chips only to draw pixels or to build new image features. In Step 2 of the guide, set `DOWNLOAD = True` in
the pilot cell and press its Run arrow, then do the same for all the data. Each cell then asks for a typed `yes`, shows
a loading bar, continues after a stop, and builds a database of your own.

Without the notebook, the same steps are:

```bash
python scripts/get_all_data.py           # labels check and Sentinel-2 chips (48-record pilot, one process)
python scripts/step6_build_database.py   # data/cropyield.duckdb
python scripts/step7_check_data.py       # what the database holds, per cohort
```

### Data v2 (7 Nov 2026)

Data v2 sits next to v1 and changes nothing in it. It adds Malawi 2022 (529 walked polygons, photos from the older
`sentinel-2-l2a` collection) and tries up to 24 photos for each cloudy month (522 more clear field-months). Its labels,
audit and splits come with the clone in `data/v2/`. Get the v2 database from the same team link and put it at
`data/v2/cropyield.duckdb` (22,818,816 bytes; the SHA-256 is in `configs/team_database_v2.json`). Keep the v1 file too.

- The v2 database has **no Presto and no MOSAIKS rows**. Never join v1 Presto or MOSAIKS rows to v2 rows: they were made
  from other photos (Malawi 2022 most of all).
- Leave `CROPYIELD_DATA_DIR` unset and use the `--version 2` switch. Steps 8 and 9 stop if a database differs from its pin.

```bash
python scripts/step8_run_baseline.py --version 2   # results/v2/baseline_table.md (folds 1-4 scored)
python scripts/step9_compare_data_v2.py            # results/v2/data_v2_comparison.md: v2 against v1, and the Malawi season transfer
python scripts/step7_check_data.py --version 2     # what the v2 database holds, per cohort
```

The rules written before any v2 score: [`docs/DATA_V2_PLAN.md`](docs/DATA_V2_PLAN.md). The results: `docs/DECISIONS.md`
(7 Nov 2026). The whole dataset, its cleaning, its known problems and its splits: [`docs/DATASET.md`](docs/DATASET.md).

## Where things are

| Path | What it holds |
|---|---|
| [`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb) | the one guide to the data |
| [`scripts/`](scripts/README.md) | the data path, one script per step |
| [`sql/`](sql/README.md) | the database schema, views and example queries |
| `src/cropyield/` | the package that the scripts and the notebook import |
| `data/` | labels and splits are frozen and committed; the database is one shared file; chips stay local. `data/v2/` holds data v2 |
| `results/` | the baseline table and each of its numbers; `results/v2/` the data v2 scores |
| `docs/` | the dataset deliverable (`DATASET.md`), plan, data notes, evaluation, related work, decisions and structure |
| `_parked/` | everything that is not on the data path, safe and listed in `_parked/MANIFEST.csv` |

Licences and attribution: `data/README.txt`. Keep the provider citations when you use or share the data.
