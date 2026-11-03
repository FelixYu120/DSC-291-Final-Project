# DSC-291 Final Project: field-level maize yield from Sentinel-2 in sub-Saharan Africa

Felix Yu, Florian Saewert, Liuan Lu, Pamely Zantou, Zida Jin. UCSD DSC 291, Fall 2026.

**Start with the data guide: [`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb).** It teaches the data from
zero: which files make it, where it comes from, how it is matched and split, and what X and Y look like.

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

## Run the spatial baselines

With the shared database in place, run:

```bash
python scripts/run_baselines.py
```

This compares R0 (training mean), R1 (10 nearest training locations), and A1 (seasonal vegetation indices
with Ridge regression) separately for Malawi, Kenya and Lacuna, using the existing `s1_cc2km` folds.
It verifies the database/label/split checksums, tunes A1 inside each training fold, and saves score tables
under `results/spatial_baselines/` and field predictions under `data/runs/spatial_baselines/`.
See [the code walkthrough and interpretation guide](docs/BASELINES.md). The command reads the database;
it does not need imagery downloads or a database rebuild.

## Optional imagery download

You need the chips only to draw pixels or to build new image features. In Step 2 of the guide, set `DOWNLOAD = True` in
the pilot cell and press its Run arrow, then do the same for all the data. Each cell then asks for a typed `yes`, shows
a loading bar, continues after a stop, and builds a database of your own.

Without the notebook, the same steps are:

```bash
python scripts/get_all_data.py           # labels check and Sentinel-2 chips (48-record pilot, one process)
python scripts/step6_build_database.py   # data/cropyield.duckdb
python scripts/step7_check_data.py       # what the database holds, per cohort
```

## Where things are

| Path | What it holds |
|---|---|
| [`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb) | the one guide to the data |
| [`scripts/`](scripts/README.md) | the data path, one script per step |
| [`sql/`](sql/README.md) | the database schema, views and example queries |
| `src/cropyield/` | the package that the scripts and the notebook import |
| `data/` | labels and splits are frozen and committed; the database is one shared file; chips stay local |
| `docs/` | plan, data notes, evaluation, related work, decisions and structure |
| `_parked/` | everything that is not on the data path, safe and listed in `_parked/MANIFEST.csv` |

Licences and attribution: `data/README.txt`. Keep the provider citations when you use or share the data.
