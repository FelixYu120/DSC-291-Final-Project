# DSC-291 Final Project: field-level maize yield from Sentinel-2 in sub-Saharan Africa

Felix Yu, Florian Saewert, Liuan Lu, Pamely Zantou, Zida Jin. UCSD DSC 291, Fall 2026.

**Question.** Within one smallholder cohort, which Sentinel-2 representation predicts field-level maize
yield best (hand-crafted seasonal indices, MOSAIKS random convolutional features, a small temporal network
trained from scratch, or frozen foundation-model embeddings), and how much of that skill survives in new
villages, new districts and a new season? Core cohorts: One Acre Fund Kenya 2019–2020 (3,977 crop-cut
points) and FAO/NASA Harvest Malawi 2023 (260 walked polygons). Scope and plan:
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Status (30 October 2026)

| Part | State |
|---|---|
| Labels | `labels_v1` frozen: 11,364 field-seasons, 8,575 `include_primary` rows in 4 cohorts (`data/processed/`) |
| Imagery | Sentinel-2 L2A chips complete: 11,364 of 11,364 records (`docs/DATA.md`) |
| Splits | frozen for 4 cohorts (`data/splits/`, hashes in `manifest.json`) |
| Features | seasonal indices, MOSAIKS (K = 1024) and frozen Presto for every record (`data/cropyield.duckdb`) |
| Results | B0 on new villages: R² 0.20 in Lacuna, 0.17 in Malawi, 0.05 in Kenya; transfer test X1 (`docs/ROADMAP.md`, section 2) |

## Read this first

| File | What it holds |
|---|---|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | scope, model arms, the B0 baseline, stages with gates and fallbacks, answers to the proposal feedback |
| [`docs/DATA.md`](docs/DATA.md) | how each cohort measures yield, why we never pool, the `labels_v1` table and its checks, red flags |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | split families (new village, new region, new season), metrics, noise ceilings, how splits are frozen |
| [`docs/RELATED_WORK.md`](docs/RELATED_WORK.md) | verified papers on foundation models for yield, how we differ, the CNN question |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | one dated line per decision |
| [`docs/STRUCTURE.md`](docs/STRUCTURE.md) | folder layout and team rules |

## Quick start

Clone **outside OneDrive** (for example `C:\Dev\`): inside OneDrive, chip paths pass the 260-character
Windows limit and OneDrive locks files while the downloader writes them. Python 3.10 or newer, from the
repository root, in a virtual environment:

```bash
python -m pip install -e ".[dev,presto]"     # once
python scripts/get_data.py                   # 1. labels check, Presto weights, Sentinel-2 chips (48-record pilot)
python scripts/features/mosaiks_features.py  # 2. MOSAIKS features from the chips
python scripts/build_database.py             # 3. data/cropyield.duckdb: every table and the views master, monthly
python scripts/check_data.py                 # 4. what the database holds, per cohort
python scripts/run_experiment.py configs/b0_seasonal_indices_ridge.yaml  # 5. B0: rows in results/metrics.csv
python -m pytest                             # small checks, no imagery needed
```

Core cohorts instead of the pilot: `python scripts/get_data.py --scope cohorts --cohorts malawi_2023
kenya_oaf_2019_2020` (`--plan` for an offline size and time estimate, `--status` for progress, `--batch i/n`
for parallel slices; see [`scripts/cluster/README.md`](scripts/cluster/README.md)). Rebuild the database
after every download and close notebook connections first: an open DuckDB connection locks the file on
Windows. Every script is listed in [`scripts/README.md`](scripts/README.md); the database tables in
[`sql/README.md`](sql/README.md).

| Notebook | What it shows |
|---|---|
| `00_data_tour.ipynb` | one field from its label row to the input of every model |
| `01_presto_first_run.ipynb` | the pinned Presto model runs on our chips |
| `02_pilot48.ipynb` | the week-0 pilot gate and one inspection card per record |
| `03_how_the_data_works.ipynb` | bands, the data cube, and how Presto, MOSAIKS and AlphaEarth read it |
| `04_database.ipynb` | every database table with `SELECT *`, and the joins you need |

## Repository layout

```text
configs/     one YAML per experiment, plus the Sentinel-2 window files of the pilot
data/        raw/ metadata/ audit/ processed/ (labels, committed)   splits/ (frozen)   imagery/ features/ models/ runs/ (git-ignored)
docs/        the files above; archive/ keeps superseded plans
notebooks/   exploration only; nothing in the paper comes from a notebook
results/     metrics.csv, append-only
scripts/     command-line entry points by stage (scripts/README.md)
sql/         DuckDB schema, views and example queries
src/cropyield/  data/ satellite/ features/ models/ eval/: the package the scripts and notebooks import
tests/       pytest
```

## Data and attribution

Label sources: [One Acre Fund full release](https://data.harvestportal.org/dataset/oaf_mel) (CC BY),
[FAO / NASA Harvest Malawi crop cuts](https://data.harvestportal.org/dataset/fao-bha-nasa-harvest-public-yield-datasets)
(CC BY), [Zimbabwe Lacuna](https://doi.org/10.5281/zenodo.10060610) (CC BY 4.0),
[vision-guided crop-yield dataset](https://zenodo.org/records/17626117) (CC BY 4.0; the 4.9 GB photo archive
stays off git). Imagery: Copernicus Sentinel-2 L2A via the
[Earth Search STAC API](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a) and the
[AWS Sentinel-2 COG archive](https://registry.opendata.aws/sentinel-2-l2a-cogs/). Presto model code is MIT
(`src/cropyield/models/PRESTO_LICENSE`). Download URLs and checksums: `data/metadata/download_manifest.json`;
data-use notes: `data/README.txt`. Keep the provider citations when using or sharing the data.

The central references are Burke and Lobell (2017, [PNAS](https://doi.org/10.1073/pnas.1616919114)),
Rolf et al. (2021, [MOSAIKS](https://doi.org/10.1038/s41467-021-24638-z)) and Tseng et al.
([Presto](https://arxiv.org/abs/2304.14065)); the full list is in `docs/RELATED_WORK.md`.
