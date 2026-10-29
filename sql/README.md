# The project database (`data/cropyield.duckdb`)

All project data lives in one [DuckDB](https://duckdb.org) file: `data/cropyield.duckdb`. It is git-ignored and
built on your machine by `scripts/build_database.py`, from scratch, every time. DuckDB is a database in a single
file: no server, only `pip install duckdb` (part of the project install).

The SQL that defines it lives here, so a teammate can read what every table and column means without opening
Python:

| File | What it is |
|---|---|
| `schema.sql` | one `CREATE TABLE` per table, every column with a comment, in pipeline order |
| `views.sql` | the views `season_indices`, `master` and `monthly` (a view is a saved `SELECT`, no copied data) |
| `queries/*.sql` | short, named queries you can run from Python or the DuckDB shell (list below) |

`scripts/build_database.py` runs `schema.sql`, fills the tables from Python, then runs `views.sql`. Nothing here
is run by hand.

## The key: `obs_id`

One row of `labels` is **one field in one season**. Its id is `obs_id = "<dataset>:<source_id>"`, for example
`malawi_2023:506ae8b2-d085-4eeb-b807-765e03925c71`. Every table has an `obs_id` column, so any two tables join on
it: `... JOIN downloads USING (obs_id)`. The monthly tables (`coverage`, `monthly_bands`, `vegetation_indices`,
`mosaiks_monthly`) also have `month` (`'YYYY-MM'`): join them `USING (obs_id, month)`.

## Every table and view

| Name | One row per | What it holds |
|---|---|---|
| `labels` | field-season, **all** cohorts | yield (`yield_kg_ha`), source yield and unit, location, polygon, dates, season window |
| `downloads` | field-season with a chip folder | downloader status, pixel counts, chip CRS, searched window |
| `scenes` | accepted Sentinel-2 scene | date, satellite, tile, cloud numbers, clear field pixels |
| `coverage` | downloaded field-season x month | `state`: `clear`, `cloudy`, `no_scene` or `download_error` |
| `monthly_bands` | field-season x month (with at least one scene) | median field reflectance of the 10 bands `b02 ... b12`, `missing` flag |
| `vegetation_indices` | field-season x month (with at least one scene) | `ndvi`, `gcvi`, `mtci`, `ndvi705`, `ndvi740` |
| `presto_embeddings` | field-season with at least one clear month | `embedding FLOAT[128]`: the frozen Presto encoder output |
| `mosaiks_monthly` | field-season x month with a scene | `chip FLOAT[K]`, `field FLOAT[K]`: MOSAIKS features of the chip and of the field pixels |
| `mosaiks_season` | field-season with MOSAIKS features | season mean of the monthly MOSAIKS vectors; `months_used` counts the months in the chip mean (the field mean can use fewer) |
| `build_info` | build (exactly one row) | when, which commit, which folders, Presto and MOSAIKS settings (`mosaiks_features` = K) |
| `season_indices` (view) | field-season with at least one scene | season `max` and `mean` of each index: `ndvi_season_max`, `ndvi_season_mean`, ... |
| **`master`** (view) | field-season, **all** cohorts | every `labels` column + `has_imagery`, `download_status`, `months_with_data` + the season indices + `presto_embedding`, `mosaiks_chip`, `mosaiks_field`, `mosaiks_months_used` |
| **`monthly`** (view) | downloaded field-season x month | `cohort`, `coverage_state`, the 10 bands, the 5 indices, `mosaiks_chip`, `mosaiks_field`, `yield_kg_ha` |

`master` uses `LEFT JOIN`s, so a field without imagery keeps its label row with `has_imagery = FALSE` and `NULL` in
every feature column. For modelling: `WHERE has_imagery AND months_with_data > 0`. `monthly` is the input of
sequence models (GRU): `ORDER BY obs_id, month` gives each field's months in time order, `NULL` where a month has
no clear scene.

`season_indices` is a starting point (max and mean over the months with a value). The baseline owner may change
its statistics in `views.sql`; `master` picks the change up automatically.

### Vectors are arrays

A Presto embedding or a MOSAIKS vector is **one value** in one column, not 128 columns. In SQL: `embedding[1]` is
the first number (arrays start at 1), `len(embedding)` the length, `embedding[1:5]` a slice. In Python, the
helper `cropyield.data.database.wide` spreads one array column into numbered columns for scikit-learn:

```python
from cropyield.data.database import connect, run_query, wide

con = connect()                                        # read-only
rows = run_query(con, "modelling_table")               # one cohort, fields with imagery
y = rows["yield_kg_ha"]
X_presto = wide(rows, "presto_embedding", "presto")    # presto_000 ... presto_127
X_mosaiks = wide(rows, "mosaiks_chip", "mosaiks")      # mosaiks_0000 ... mosaiks_1023 (K columns)
con.close()
```

## Build order

From the repository root, after `python -m pip install -e ".[dev,presto]"`:

```bash
python scripts/get_data.py                    # 1. labels check, Presto weights, Sentinel-2 chips (48-record pilot)
python scripts/features/mosaiks_features.py   # 2. MOSAIKS features -> data/features/mosaiks/*.parquet
python scripts/build_database.py              # 3. data/cropyield.duckdb from 1 and 2
```

Step 3 works without step 2: it then prints one line and leaves `mosaiks_monthly` and `mosaiks_season` empty
(`build_info.mosaiks_features` is `NULL`). Options: `--no-presto` (skip the embeddings, no torch),
`--imagery-dir`, `--mosaiks-dir`, `--db`. Rebuild after every download or feature run. On Windows an open
connection locks the file: close notebooks (`con.close()`) before you rebuild.

## Run a query file

Each saved query in `queries/` starts with a comment that says what it returns:

| File | Returns |
|---|---|
| `table_overview.sql` | every table and view with its row count |
| `coverage_by_cohort.sql` | per cohort: fields with imagery, field-months by coverage state, percent clear |
| `modelling_table.sql` | one cohort (edit the `WHERE` line): label + season indices + Presto + MOSAIKS per field |
| `monthly_series.sql` | one cohort: the month-by-month rows of `monthly`, in time order |

**From Python** (a notebook or a script):

```python
from cropyield.data.database import connect, run_query

con = connect()
overview = run_query(con, "table_overview")       # a pandas DataFrame
con.sql("SELECT * FROM master LIMIT 5").df()      # or any SQL of your own
con.close()
```

**From the DuckDB shell** (install the command-line tool from https://duckdb.org/docs/installation; run from the
repository root; `-readonly` lets notebooks keep reading at the same time):

```bash
duckdb -readonly data/cropyield.duckdb ".read sql/queries/table_overview.sql"
duckdb -readonly data/cropyield.duckdb            # interactive; then:  .read sql/queries/coverage_by_cohort.sql
```

Inside the shell, `DESCRIBE master;` lists the columns of a table or view, `.tables` every table, `.quit` leaves.
