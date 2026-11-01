# Project structure

## Layout

```
data/            raw/ metadata/ audit/ processed/ (labels, committed)   splits/ (frozen)   imagery/ features/ runs/ (git-ignored)
scripts/         the data path in step order: get_all_data.py, then step1 to step7 (scripts/README.md)
sql/             DuckDB schema, views and example queries (sql/README.md)
src/cropyield/   data/  satellite/  features/  eval/   one subpackage per pipeline stage
configs/         the Sentinel-2 window file of the pilot, and the frozen scene list sentinel2_scenes_v1.parquet
tests/           pytest
notebooks/       data_guide.ipynb: the one guide to the data
docs/            ROADMAP.md (plan), DATA.md, EVALUATION.md, RELATED_WORK.md, DECISIONS.md, STRUCTURE.md (this file)
_parked/         what is not on the data path; MANIFEST.csv lists it, LANDING.md says how to take a file back
requirements.txt the exact package versions; pyproject.toml names the packages
```

## Rules

1. Branch per task, pull request, one reviewer. `main` always passes `python -m pytest`.
2. Models read `labels_v1` only (`docs/DATA.md`), never a raw or audit CSV.
3. Split files are created before any model is trained and never edited afterwards (`docs/EVALUATION.md`).
4. One model per cohort; every metric is reported within cohort. No pooled R².
5. Every run is a config file; every metric lands in the results table with its commit, config, split
   file, seed and fold.
6. Models that are compared get the same rows, the same splits, the same head and the same tuning effort,
   and each is reported next to the coordinates-only baseline R1.
7. MOSAIKS filters are refitted once after the core download, before the first MOSAIKS result, then frozen.
8. No stretch item starts before gate G3 (`docs/ROADMAP.md`).
9. Imagery, features, checkpoints and the photo archive stay off git.
10. One dated line per decision in `docs/DECISIONS.md`.

## Cohorts and season windows

| Cohort | Role | Audit dataset and filter | Fields | Location | Season window |
|---|---|---|---:|---|---|
| Kenya OAF 2019–2020 | core | `one_acre_fund_full`, kenya, `intercropping == "0"` | 3,977 | GPS point | 1 Feb – 30 Sep of the year |
| Malawi 2023 | core | `malawi_2023` | 260 | walked polygon | 1 Oct 2022 – 30 Jun 2023 |
| Zimbabwe Lacuna 2023 | second | `zimbabwe`, year 2023, `intercropping == "no"`, rainfed (in `include_primary` of `labels_v1`) | 1,880 | GPS point | 1 Oct 2022 – 30 Jun 2023 |
| Zimbabwe 2024 | parked | `vision_guided_yield_estimation`, year 2024, positive yields | 2,458 | GPS point | 1 Oct 2023 – 30 Jun 2024 |
| Malawi 2022, Lacuna 2022 | dropped | – | – | – | 2022 imagery gap |

Windows are fixed per zone and season, never anchored on a row's crop-cut date. `src/cropyield/data/cohorts.py`
still defines all five original cohorts so the pilot and the database keep working.

## Setup

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
```
