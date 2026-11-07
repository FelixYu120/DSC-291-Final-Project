"""X and y of one cohort: the one input every baseline model starts from.

X holds the season values of the view ``master``, and y the yield in t/ha, on the same index. A row
needs ``include_primary`` and MIN_CLEAR_MONTHS clear months. Each cohort keeps its own yield
definition (docs/DATA.md), so a model stays inside one cohort.

Usage:
    from cropyield.data.xy import load_xy
    X, y = load_xy("malawi_2023")
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import duckdb
import pandas as pd

from cropyield import ROOT
from cropyield.data.cohorts import COHORTS

MIN_CLEAR_MONTHS = 4
FEATURES = ["ndvi_season_max", "ndvi_season_mean", "gcvi_season_max", "gcvi_season_mean", "mtci_season_max",
            "mtci_season_mean", "ndvi705_season_max", "ndvi705_season_mean", "ndvi740_season_max", "ndvi740_season_mean"]


def load_xy(cohort: str, data_dir: Path | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """X indexed by ``obs_id`` and y as ``yield_t_ha``, sorted by ``obs_id``.

    ``data_dir`` defaults to CROPYIELD_DATA_DIR, then to <repository root>/data. On a partial copy the
    result holds only the rows with a chip, and a warning gives the count of the others.

    Example: ``X, y = load_xy("kenya_oaf_2019_2020")``
    """
    if cohort not in COHORTS:
        raise ValueError(f"{cohort!r} is not a cohort; the names are: {', '.join(COHORTS)}")
    database = Path(data_dir or os.environ.get("CROPYIELD_DATA_DIR") or ROOT / "data") / "cropyield.duckdb"
    if not database.exists():
        raise FileNotFoundError(f"{database} is missing; download the shared team cropyield.duckdb "
                                "described in README.md and place it here. Do not rebuild the team "
                                "database: rebuilding removes its Presto embeddings.")
    with duckdb.connect(str(database), read_only=True) as con:  # closes at once: an open file blocks a later build
        primary, no_chip = con.execute("""SELECT count(*), count(*) FILTER (WHERE NOT has_imagery)
                                          FROM master WHERE cohort = ? AND include_primary""", [cohort]).fetchone()
        rows = con.execute(f"""SELECT obs_id, yield_kg_ha / 1000 AS yield_t_ha, {", ".join(FEATURES)}
                               FROM master
                               WHERE cohort = ? AND include_primary AND months_with_data >= ?
                               ORDER BY obs_id""", [cohort, MIN_CLEAR_MONTHS]).df()
    if not primary:
        raise ValueError(f"{cohort} has no include_primary rows, so no model uses it")
    if no_chip:
        warnings.warn(f"{cohort}: {no_chip:,} of {primary:,} include_primary rows have no chip on this copy, "
                      "so X and y are partial.", stacklevel=2)
    rows = rows.set_index("obs_id")
    return rows[FEATURES].astype("float64"), rows["yield_t_ha"].astype("float64")
