"""Open the project database and run the saved queries in sql/queries.

The database is data/cropyield.duckdb, built by scripts/build_database.py (schema in sql/).
Every table is keyed by ``obs_id`` (one field in one season); the view ``master`` has one row
per labelled observation with every feature, the view ``monthly`` one row per observation x
month. Vectors are stored as arrays; ``wide`` spreads one array column into numbered columns.

Usage:
    from cropyield.data.database import connect, run_query, wide
    con = connect()                                   # read-only: several notebooks may read at once
    rows = run_query(con, "modelling_table")          # runs sql/queries/modelling_table.sql
    X = wide(rows, "presto_embedding", "presto")      # columns presto_000 ... presto_127
    y = rows["yield_kg_ha"]
    con.close()                                       # Windows: an open connection locks the file
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from cropyield import ROOT

DATABASE = ROOT / "data" / "cropyield.duckdb"
QUERIES = ROOT / "sql" / "queries"


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Connection to data/cropyield.duckdb; read-only unless you really mean to write.

    Example: ``con = connect(); con.sql("SELECT count(*) FROM master").fetchone()``
    """
    if not DATABASE.exists():
        raise FileNotFoundError(f"{DATABASE} is missing; run: python scripts/build_database.py")
    return duckdb.connect(str(DATABASE), read_only=read_only)


def query_text(name: str) -> str:
    """The SQL of sql/queries/<name>.sql. Example: ``print(query_text("coverage_by_cohort"))``"""
    path = QUERIES / f"{name}.sql"
    if not path.exists():
        names = ", ".join(sorted(p.stem for p in QUERIES.glob("*.sql")))
        raise FileNotFoundError(f"{path} is missing; the saved queries are: {names}")
    return path.read_text(encoding="utf-8")


def run_query(con: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    """Run sql/queries/<name>.sql and return its rows as a DataFrame.

    Example: ``run_query(con, "table_overview")`` gives the row count of every table and view.
    """
    return con.execute(query_text(name)).df()


def wide(frame: pd.DataFrame, column: str, prefix: str) -> pd.DataFrame:
    """Spread one array column into numbered columns ``<prefix>_000, <prefix>_001, ...`` for scikit-learn.

    A row whose array is NULL becomes a row of NaN; the index of ``frame`` is kept, so the result
    lines up with ``frame[y_column]``. Example: ``X = wide(rows, "mosaiks_chip", "mosaiks")``.
    """
    vectors = [np.asarray(value, dtype="float64") if isinstance(value, (list, tuple, np.ndarray)) else None
               for value in frame[column]]
    lengths = {len(vector) for vector in vectors if vector is not None}
    if not lengths:
        raise ValueError(f"{column} holds no values in these rows (is the feature built? see sql/README.md)")
    if len(lengths) > 1:
        raise ValueError(f"{column} holds arrays of different lengths: {sorted(lengths)}")
    length = lengths.pop()
    matrix = np.full((len(frame), length), np.nan)
    for row, vector in enumerate(vectors):
        if vector is not None:
            matrix[row] = vector
    digits = max(3, len(str(length - 1)))
    columns = [f"{prefix}_{i:0{digits}d}" for i in range(length)]
    return pd.DataFrame(matrix, index=frame.index, columns=columns)
