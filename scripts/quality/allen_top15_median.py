"""Allen's label-free monthly median of the existing top-15 quality selection.

Run after select_passarchive_imagery.py --window-kind both --crop maize.
The pass archive is never changed. Model scaling/imputation belongs inside CV.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


BANDS = ("b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12")


def q(path: Path) -> str:
    return "'" + str(path.resolve()).replace("\\", "/").replace("'", "''") + "'"


def build(database: Path, top15: Path, output: Path) -> dict:
    database, top15, output = map(Path, (database, top15, output))
    if not database.is_file() or not top15.is_file():
        raise FileNotFoundError("Need the release DuckDB and two-year maize monthly_top15.parquet")
    summary_file = top15.parent / "summary.json"
    if summary_file.is_file():
        source_summary = json.loads(summary_file.read_text(encoding="utf-8"))
        if source_summary.get("window_kind") != "both" or source_summary.get("crop") != "maize":
            raise ValueError("Screen must use --window-kind both --crop maize")
    output.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(database), read_only=True)
    try:
        reflectance = ",\n                   ".join(
            f"(d.{b} + coalesce(d.dn_add_offset,0))/10000.0 AS {b}" for b in BANDS
        )
        con.execute(f"""
            CREATE TEMP TABLE converted AS
            SELECT d.field_season_id, d.fs_key, d.country_iso3, d.dataset,
                   d.year, d.month, d.scene_id, d.acquisition_id,
                   d.sensing_time_utc, d.quality_rank,
                   d.same_overflight_rank,
                   {reflectance}
            FROM read_parquet({q(top15)}) d
            WHERE d.crop='maize' AND d.quality_rank<=15
        """)
        valid = " AND ".join(f"{b} BETWEEN 0 AND 1" for b in BANDS)
        con.execute(f"""
            CREATE TEMP TABLE valid AS SELECT * FROM converted WHERE {valid}
        """)
        con.execute("""
            CREATE TEMP TABLE chosen AS
            SELECT *, row_number() OVER (
                PARTITION BY field_season_id,year,month
                ORDER BY quality_rank ASC,scene_id ASC) AS scene_rank
            FROM converted
        """)
        median_bands = ",\n                   ".join(
            f"median(c.{b}) AS {b},\n"
            f"                   max(c.{b}) FILTER (WHERE c.scene_rank=1) AS best1_{b}"
            for b in BANDS
        )
        con.execute(f"""
            CREATE TEMP TABLE monthly AS
            SELECT f.field_season_id, f.country_iso3, f.dataset, f.harvest_year,
                   cm.window_kind, cm.year, cm.month,
                   printf('%04d-%02d',cm.year,cm.month) AS month_id,
                   count(c.scene_id) AS n_selected_scenes,
                   count(DISTINCT c.acquisition_id) AS n_independent_overflights,
                   {median_bands}
            FROM coverage_months cm JOIN fields f USING(fs_key)
            LEFT JOIN chosen c ON c.fs_key=cm.fs_key
                 AND c.year=cm.year AND c.month=cm.month
            WHERE f.crop='maize' AND cm.window_kind IN ('current','previous')
            GROUP BY ALL
        """)
        con.execute("""
            CREATE TEMP TABLE in_scope AS
            SELECT m.*, f.planting_date, f.harvest_date,
                CASE WHEN f.planting_date IS NOT NULL AND f.harvest_date IS NOT NULL
                       AND f.planting_date<=f.harvest_date
                       AND date_diff('day',f.planting_date,f.harvest_date)<=550
                     THEN 'recorded_dates' ELSE 'harvest_calendar_year' END AS window_rule,
                CASE WHEN f.planting_date IS NOT NULL AND f.harvest_date IS NOT NULL
                       AND f.planting_date<=f.harvest_date
                       AND date_diff('day',f.planting_date,f.harvest_date)<=550
                     THEN make_date(m.year,m.month,1)<=f.harvest_date
                          AND last_day(make_date(m.year,m.month,1))>=f.planting_date
                     ELSE m.year=f.harvest_year END AS in_model_window
            FROM monthly m JOIN fields f USING(field_season_id)
        """)
        arm_bands = ",\n                   ".join(
            f"{b} AS {b}" for b in BANDS
        )
        best_bands = ",\n                   ".join(
            f"best1_{b} AS {b}" for b in BANDS
        )
        con.execute(f"""
            CREATE TEMP TABLE arms AS
            SELECT * EXCLUDE ({','.join(BANDS)}), 'median_top15' AS cleaning_arm, {arm_bands}
            FROM in_scope
            UNION ALL
            SELECT * EXCLUDE ({','.join(BANDS)}), 'best1' AS cleaning_arm, {best_bands}
            FROM in_scope
        """)
        season_bands = ",\n                   ".join(
            f"avg({b}) FILTER (WHERE in_model_window) AS {b}_mean" for b in BANDS
        )
        con.execute(f"""
            CREATE TEMP TABLE seasonal AS
            SELECT field_season_id, cleaning_arm, any_value(country_iso3) AS country_iso3,
                   any_value(dataset) AS dataset, any_value(harvest_year) AS harvest_year,
                   any_value(window_rule) AS window_rule,
                   count(*) FILTER (WHERE in_model_window) AS months_in_window,
                   count(*) FILTER (WHERE in_model_window AND n_selected_scenes>0)
                       AS months_observed,
                   sum(n_selected_scenes) FILTER (WHERE in_model_window) AS scene_count,
                   {season_bands},
                   max((b08-b04)/nullif(b08+b04,0)) FILTER (WHERE in_model_window)
                       AS ndvi_max,
                   avg((b08-b04)/nullif(b08+b04,0)) FILTER (WHERE in_model_window)
                       AS ndvi_mean
            FROM arms GROUP BY 1,2
        """)
        con.execute("""
            CREATE TEMP TABLE model_ready AS
            SELECT s.*, f.geometry_type, f.location_quality, f.usable_at_field_scale,
                   f.fold0_reserved, l.label_status, l.yield_kg_ha,
                   l.yield_kg_ha/1000.0 AS yield_t_ha
            FROM seasonal s JOIN fields f USING(field_season_id)
            LEFT JOIN labels l USING(field_season_id)
        """)
        con.execute(f"COPY monthly TO {q(output / 'allen_monthly.parquet')} (FORMAT PARQUET)")
        con.execute(f"COPY chosen TO {q(output / 'allen_chosen_scenes.parquet')} (FORMAT PARQUET)")
        con.execute(f"COPY model_ready TO {q(output / 'allen_model_ready.parquet')} (FORMAT PARQUET)")
        results = {
            "source_top15": str(top15.resolve()),
            "scope": "maize; previous and current archive years",
            "converted_scenes": con.execute("SELECT count(*) FROM converted").fetchone()[0],
            "valid_reflectance_scenes": con.execute("SELECT count(*) FROM valid").fetchone()[0],
            "out_of_range_reflectance_scenes": con.execute("SELECT count(*) FROM converted").fetchone()[0] - con.execute("SELECT count(*) FROM valid").fetchone()[0],
            "selected_scenes": con.execute("SELECT count(*) FROM chosen").fetchone()[0],
            "monthly_rows": con.execute("SELECT count(*) FROM monthly").fetchone()[0],
            "field_seasons": con.execute("SELECT count(DISTINCT field_season_id) FROM monthly").fetchone()[0],
            "model_rows": con.execute("SELECT count(*) FROM model_ready").fetchone()[0],
            "window_rule_counts": dict(con.execute("SELECT window_rule,cast(count(*)/2 as bigint) FROM model_ready GROUP BY 1").fetchall()),
            "model_month_coverage": con.execute("""
                SELECT country_iso3, cleaning_arm, count(*) AS fields,
                       count(*) FILTER(WHERE months_observed>0) AS with_image,
                       round(avg(months_observed),2) AS mean_months
                FROM model_ready GROUP BY 1,2 ORDER BY 1,2
            """).fetchall(),
        }
        (output / "allen_summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return results
    finally:
        con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--top15", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.database, a.top15, a.output), indent=2))
