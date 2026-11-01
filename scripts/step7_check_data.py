"""What the database holds for the labels_v1 model rows: the numbers behind the imagery section of docs/DATA.md.

    python scripts/step7_check_data.py [--db data/cropyield.duckdb] [--min-clear-months 4]

Reads the database only. Run it after every rebuild. It prints the coverage, the clear share per
calendar month, the range of each index, how much haze is left in the "clear" months, which month is
the greenest, and how strongly the season indices follow yield inside each cohort.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.labels import LABELS_PATH  # noqa: E402

COHORT_ORDER = ["malawi_2023", "kenya_oaf_2019_2020", "zimbabwe_lacuna_2022_2023", "zimbabwe_2024", "malawi_2022"]
INDICES = ["ndvi", "gcvi", "mtci", "ndvi705", "ndvi740"]
SEASON_FEATURES = [f"{index}_season_{stat}" for index in INDICES for stat in ("max", "mean")]
HAZE_BLUE = 0.15  # field-median blue reflectance above this in a "clear" month is likely haze or thin cloud
MODEL_ROWS = f"""
    CREATE TEMP VIEW model_rows AS
    SELECT v.obs_id, v.cohort, v.season_year, v.yield_kg_ha, coalesce(m.has_imagery, FALSE) AS has_imagery,
           m.download_status, coalesce(m.months_with_data, 0) AS months_with_data, {", ".join(SEASON_FEATURES)}
    FROM read_parquet('{{labels}}') v LEFT JOIN master m USING (obs_id) WHERE v.include_primary
"""


def spearman(y: np.ndarray, p: np.ndarray) -> float:
    """Rank correlation; NaN when one side is constant."""
    if np.ptp(y) == 0 or np.ptp(p) == 0:
        return float("nan")
    return float(np.corrcoef(rankdata(y), rankdata(p))[0, 1])


def coverage_table(con: duckdb.DuckDBPyConnection, min_clear: int) -> pd.DataFrame:
    """Fields, chips and clear months per cohort, on the rows the models use."""
    rows = con.execute("""
        SELECT cohort, season_year, count(*) AS primary_rows,
               count(*) FILTER (WHERE has_imagery) AS with_chip,
               count(*) FILTER (WHERE download_status = 'complete') AS complete,
               count(*) FILTER (WHERE months_with_data >= ?) AS usable,
               min(months_with_data) FILTER (WHERE has_imagery) AS min_months,
               median(months_with_data) FILTER (WHERE has_imagery) AS median_months,
               max(months_with_data) FILTER (WHERE has_imagery) AS max_months,
               avg(yield_kg_ha) / 1000 AS mean_t_ha, stddev(yield_kg_ha) / 1000 AS sd_t_ha
        FROM model_rows GROUP BY cohort, season_year ORDER BY cohort, season_year
    """, [min_clear]).df()
    return rows.round(2)


def clear_share_by_month(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Share of primary fields with a clear scene, per month of the season window."""
    frame = con.execute("""
        SELECT l.cohort, l.season_year, c.month, avg(CAST(c.state = 'clear' AS DOUBLE)) AS clear,
               avg(CAST(c.state = 'no_scene' AS DOUBLE)) AS no_scene
        FROM coverage c JOIN model_rows l USING (obs_id)
        GROUP BY ALL ORDER BY l.cohort, l.season_year, c.month
    """).df()
    return frame.round(2)


def index_ranges(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Percentiles of each season feature; a far tail is what the Winsorize step of B0 clips."""
    frame = con.execute(f"""
        SELECT cohort, {", ".join(SEASON_FEATURES)} FROM model_rows WHERE has_imagery
    """).df()
    long = frame.melt("cohort", var_name="feature").dropna()
    table = long.groupby(["feature", "cohort"], sort=False)["value"].describe(percentiles=[0.01, 0.5, 0.99])
    return table[["min", "1%", "50%", "99%", "max"]].round(3)


def haze(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Share of clear months whose field median looks hazy, and whether months like that raise the season max."""
    frame = con.execute(f"""
        SELECT l.cohort, l.season_year, count(*) AS clear_months,
               avg(CAST(b.b02 > {HAZE_BLUE} AS DOUBLE)) AS share_blue_high,
               quantile_cont(b.b02, 0.5) AS blue_median, quantile_cont(b.b02, 0.99) AS blue_p99
        FROM monthly_bands b JOIN model_rows l USING (obs_id)
        WHERE NOT b.missing GROUP BY ALL ORDER BY l.cohort, l.season_year
    """).df()
    return frame.round(3)


def greenest_month(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """In which month the NDVI of each field peaks: a peak on the last month of the window means it was cut off."""
    frame = con.execute("""
        WITH peak AS (
            SELECT v.obs_id, l.cohort, l.season_year, v.month,
                   row_number() OVER (PARTITION BY v.obs_id ORDER BY v.ndvi DESC) AS place
            FROM vegetation_indices v JOIN model_rows l USING (obs_id)
            WHERE v.ndvi IS NOT NULL
        )
        SELECT cohort, season_year, month, count(*) AS fields FROM peak WHERE place = 1 GROUP BY ALL
    """).df()
    frame["share"] = frame["fields"] / frame.groupby(["cohort", "season_year"])["fields"].transform("sum")
    return frame.sort_values(["cohort", "season_year", "month"]).round(2)


def signal(con: duckdb.DuckDBPyConnection, min_clear: int) -> pd.DataFrame:
    """Spearman of each season feature with yield inside a cohort-year, and of one with the cloud count."""
    frame = con.execute(f"""
        SELECT cohort, season_year, yield_kg_ha, months_with_data, {", ".join(SEASON_FEATURES)}
        FROM model_rows WHERE months_with_data >= ?
    """, [min_clear]).df()
    rows = []
    for (cohort, year), part in frame.groupby(["cohort", "season_year"]):
        if len(part) < 100:
            continue
        rows.append({"cohort": cohort, "year": year, "n": len(part),
                     **{name: spearman(part["yield_kg_ha"].to_numpy(), part[name].to_numpy())
                        for name in ["months_with_data", *SEASON_FEATURES]}})
    return pd.DataFrame(rows).round(3).set_index(["cohort", "year"]).T


def cohort_levels(con: duckdb.DuckDBPyConnection, min_clear: int) -> pd.DataFrame:
    """Mean yield next to mean greenness: if greenness ranks the cohorts as yield does, a shared model has a chance."""
    frame = con.execute("""
        SELECT cohort, season_year, count(*) AS n, avg(yield_kg_ha) / 1000 AS mean_t_ha,
               avg(ndvi_season_max) AS ndvi_max, avg(gcvi_season_max) AS gcvi_max, avg(ndvi705_season_max) AS ndvi705_max
        FROM model_rows WHERE months_with_data >= ? GROUP BY ALL ORDER BY cohort, season_year
    """, [min_clear]).df()
    return frame.round(3)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "cropyield.duckdb")
    parser.add_argument("--min-clear-months", type=int, default=4)
    args = parser.parse_args(argv)
    pd.set_option("display.width", 200, "display.max_rows", 500, "display.max_columns", 50)
    with duckdb.connect(str(args.db), read_only=True) as con:
        con.execute(MODEL_ROWS.format(labels=LABELS_PATH.as_posix()))
        sections = {
            "Coverage of the primary rows": coverage_table(con, args.min_clear_months),
            "Clear share per month": clear_share_by_month(con),
            "Season feature ranges": index_ranges(con),
            f"Haze in clear months (field-median blue > {HAZE_BLUE})": haze(con),
            "Greenest month": greenest_month(con),
            "Spearman with yield, inside a cohort-year": signal(con, args.min_clear_months),
            "Cohort level: yield and greenness": cohort_levels(con, args.min_clear_months),
        }
    for title, table in sections.items():
        print(f"\n## {title}\n{table.to_string()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
