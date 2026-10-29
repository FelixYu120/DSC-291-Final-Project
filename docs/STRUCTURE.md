# Project structure

## Layout

```
data/            raw/ audit/ processed/ (Felix's data layer, unchanged)   splits/ (frozen)   imagery/ features/ (git-ignored)
scripts/         command-line entry points by stage: get_data.py, build_database.py, labels/ imagery/ models/ features/ optional/ (scripts/README.md)
sql/             DuckDB schema, views and example queries (sql/README.md)
src/cropyield/   data/  satellite/  features/  models/  eval/   one subpackage per pipeline stage
configs/         one YAML per experiment
tests/           pytest
results/         metrics.csv, append-only
notebooks/       exploration only; nothing in the report comes from a notebook
docs/            STRUCTURE.md (this file), ROADMAP.md, project_map.html, DECISIONS.md, RESEARCH_PLAN.md, DATA_SOURCES.md
```

## Rules

1. Branch per task, pull request, one reviewer. `main` always passes `python -m pytest`.
2. Split files are created before any model is trained and never edited afterwards.
3. Every run is a config file; every metric lands in `results/metrics.csv` with its commit, config, seed and fold.
4. Models that are compared get the same inputs, the same splits and the same tuning effort.
5. Imagery, features, checkpoints and the photo archive stay off git.
6. One dated line per decision in `docs/DECISIONS.md`.

## Cohorts and season windows

| Cohort | Audit dataset | Records | Location | Season window |
|---|---|---:|---|---|
| Zimbabwe 2024 | `vision_guided_yield_estimation`, year 2024 | 4,332 audited (4,173 in Li et al.) | GPS point | 1 Oct 2023 – 30 Jun 2024 |
| Kenya OAF 2019–2020 | `one_acre_fund_full`, kenya, `intercropping == "0"` | 3,977 | GPS point | 1 Feb – 30 Sep of the year |
| Zimbabwe Lacuna 2022–2023 | `zimbabwe` | 2,266 | GPS point | 1 Oct – 30 Jun |
| Malawi 2022 / 2023 | `malawi_2022`, `malawi_2023` | 529 / 260 | walked polygon | 1 Oct – 30 Jun |

Windows are fixed per zone and season, never anchored on a row's crop-cut date. Yields are reported within cohort (moisture bases differ).

## Setup

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev,presto]"   # presto: torch and einops, only the model needs them
```
