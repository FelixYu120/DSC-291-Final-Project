"""Read-only quality checks and review flags. No filtering, fitting or source-data edits.

Integrity checks detect contradictions in stored data. Review flags identify uncertainties;
they are not a quality score and must not be used as an automatic exclusion list.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from shapely import from_wkt
from shapely.errors import GEOSException
from shapely.geometry import Point

CORE = ("kenya_oaf_2019_2020", "malawi_2023", "zimbabwe_lacuna_2022_2023")
BANDS = ("b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12")
FORMULAS = {
    "ndvi": ("b08 - b04", "b08 + b04"),
    "gcvi": ("b08 - b03", "b03"),
    "mtci": ("b08 - b05", "b05 - b04"),
    "ndvi705": ("b08 - b05", "b08 + b05"),
    "ndvi740": ("b08 - b06", "b08 + b06"),
}
TABLE_KEYS = {
    "labels": "obs_id", "downloads": "obs_id", "scenes": "obs_id, month",
    "coverage": "obs_id, month", "monthly_bands": "obs_id, month",
    "vegetation_indices": "obs_id, month", "presto_embeddings": "obs_id",
    "mosaiks_monthly": "obs_id, month", "mosaiks_season": "obs_id",
}


class Checks:
    """Machine-readable deterministic results, separate from scientific review flags."""

    def __init__(self):
        self.rows = []

    def add(self, rule: str, passed: bool, detail: str = "", failed_rows: int | None = None):
        self.rows.append({"rule": rule, "status": "pass" if passed else "fail",
                          "failed_rows": failed_rows, "detail": detail})

    def sql(self, con, rule: str, query: str, detail: str = ""):
        """Query must return one count of violating rows (not a sample)."""
        count = int(con.execute(query).fetchone()[0])
        self.add(rule, count == 0, detail, count)

    @property
    def passed(self):
        return all(row["status"] == "pass" for row in self.rows)


def check_monthly_tables(con, checks: Checks):
    """Independent checks of the monthly grid, scene links, nulls and index arithmetic."""
    checks.sql(con, "coverage_expected_calendar", """
        WITH expected AS (
          SELECT l.obs_id, strftime(t.month, '%Y-%m') AS month
          FROM labels l JOIN downloads d USING(obs_id),
          LATERAL generate_series(date_trunc('month', l.season_start),
                                  date_trunc('month', l.season_end), INTERVAL '1 month') t(month)
        )
        SELECT count(*) FROM expected e FULL JOIN coverage c USING(obs_id, month)
        WHERE e.obs_id IS NULL OR c.obs_id IS NULL
    """, "Each downloaded field has exactly its declared season's months.")
    checks.sql(con, "coverage_states", """SELECT count(*) FROM coverage
        WHERE state NOT IN ('clear', 'cloudy', 'no_scene', 'download_error') OR state IS NULL""")
    checks.sql(con, "coverage_matches_monthly_missingness", """
        SELECT count(*) FROM coverage c FULL JOIN monthly_bands b USING(obs_id, month)
        WHERE c.obs_id IS NULL OR b.obs_id IS NULL OR b.missing IS NULL
           OR (c.state = 'clear') IS DISTINCT FROM (NOT b.missing)
    """)
    checks.sql(con, "coverage_matches_accepted_scenes", """
        SELECT count(*) FROM coverage c FULL JOIN scenes s USING(obs_id, month)
        WHERE c.obs_id IS NULL OR (c.state = 'clear' AND
              (s.obs_id IS NULL OR c.item_id IS DISTINCT FROM s.item_id))
           OR (c.state <> 'clear' AND (s.obs_id IS NOT NULL OR c.item_id IS NOT NULL))
    """)
    present = " OR ".join(f"{band} IS NOT NULL" for band in BANDS)
    bad = " OR ".join(f"{band} IS NULL OR NOT isfinite({band})" for band in BANDS)
    checks.sql(con, "monthly_band_null_and_finite_contract", f"""
        SELECT count(*) FROM monthly_bands WHERE missing IS NULL
          OR (missing AND (field_pixels <> 0 OR {present}))
          OR (NOT missing AND (field_pixels <= 0 OR {bad}))
    """, "Missing months contain NULL bands, not zeros; present months contain finite bands.")
    checks.sql(con, "accepted_scene_quality_contract", """
        SELECT count(*) FROM scenes s JOIN downloads d USING(obs_id)
        WHERE NOT isfinite(clear_fraction_aoi) OR clear_fraction_aoi IS NULL
           OR clear_fraction_aoi < 0.8 OR clear_fraction_aoi > 1
           OR tile_cloud_cover IS NULL OR NOT isfinite(tile_cloud_cover)
           OR tile_cloud_cover < 0 OR tile_cloud_cover > 80
           OR field_valid_pixels <= 0 OR field_valid_pixels > d.field_pixels
    """)
    checks.sql(con, "scene_dates_match_month_and_window", """
        SELECT count(*) FROM scenes s JOIN labels l USING(obs_id)
        WHERE acquired IS NULL OR month IS DISTINCT FROM strftime(acquired, '%Y-%m')
           OR acquired < season_start OR acquired > season_end
    """)
    checks.sql(con, "download_window_and_pixel_contract", """
        SELECT count(*) FROM downloads d JOIN labels l USING(obs_id)
        WHERE search_start IS DISTINCT FROM season_start OR search_end IS DISTINCT FROM season_end
           OR NOT aoi_inside_chip OR aoi_pixels < field_pixels OR field_pixels <= 0
           OR (aoi_type = 'point_pixel' AND field_pixels <> 1)
           OR aoi_type NOT IN ('point_pixel', 'field_polygon')
    """)
    checks.sql(con, "download_accepted_month_count", """
        SELECT count(*) FROM downloads d LEFT JOIN
          (SELECT obs_id, count(*) AS n FROM scenes GROUP BY obs_id) s USING(obs_id)
        WHERE accepted_months IS DISTINCT FROM coalesce(s.n, 0)
    """)
    checks.sql(con, "monthly_field_pixel_count", """
        SELECT count(*) FROM monthly_bands b JOIN scenes s USING(obs_id, month)
        WHERE b.field_pixels IS DISTINCT FROM s.field_valid_pixels
    """)
    checks.sql(con, "index_month_keys", """
        SELECT count(*) FROM monthly_bands b FULL JOIN vegetation_indices v USING(obs_id, month)
        WHERE b.obs_id IS NULL OR v.obs_id IS NULL
    """)
    for index, (numerator, denominator) in FORMULAS.items():
        checks.sql(con, f"index_formula_{index}", f"""
            WITH compared AS (
              SELECT v.{index} AS actual, ({numerator}) / nullif(({denominator}), 0) AS expected
              FROM monthly_bands b JOIN vegetation_indices v USING(obs_id, month)
            ) SELECT count(*) FROM compared WHERE
              CASE WHEN expected IS NULL OR NOT isfinite(expected) THEN actual IS NOT NULL
              ELSE actual IS NULL OR NOT isfinite(actual)
                   OR abs(actual - expected) > 1e-9 + 1e-7 * abs(expected) END
        """, "Recomputed from stored reflectance; zero denominator must become NULL.")


def check_database(con, labels: pd.DataFrame, checks: Checks) -> dict[str, int]:
    """Audit all retained rows, including parked/excluded cohorts; never opens writable DB."""
    tables = {}
    for table, keys in TABLE_KEYS.items():
        tables[table] = int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        checks.sql(con, f"{table}_unique_keys", f"""SELECT count(*) FROM (
            SELECT {keys} FROM {table} GROUP BY {keys} HAVING count(*) <> 1)""")
        empty = " OR ".join(f"{key.strip()} IS NULL OR trim({key.strip()}) = ''" for key in keys.split(","))
        checks.sql(con, f"{table}_nonnull_keys", f"SELECT count(*) FROM {table} WHERE {empty}")
        checks.sql(con, f"{table}_label_links", f"""SELECT count(*) FROM {table} t
            LEFT JOIN labels l USING(obs_id) WHERE l.obs_id IS NULL""")

    actual = con.execute("SELECT * FROM labels").df()
    can_align = (labels.obs_id.is_unique and actual.obs_id.is_unique
                 and set(labels.obs_id) == set(actual.obs_id))
    checks.add("database_labels_same_ids", can_align)
    if can_align:
        frozen = labels.set_index("obs_id")
        actual = actual.set_index("obs_id").loc[frozen.index]
        for db_col, frozen_col in (("yield_kg_ha", "yield_kg_ha"), ("latitude", "lat"), ("longitude", "lon")):
            same = np.isclose(actual[db_col], frozen[frozen_col], atol=1e-8, rtol=0, equal_nan=False)
            checks.add(f"database_matches_{frozen_col}", same.all(), failed_rows=int((~same).sum()))
        for db_col, frozen_col in (("cohort", "cohort"), ("year", "season_year"),
                                   ("source_id", "source_id"), ("source_row", "source_row"),
                                   ("include_primary", "include_primary"), ("exclusion_reason", "exclusion_reason"),
                                   ("season_start", "season_start"), ("season_end", "season_end")):
            same = actual[db_col].eq(frozen[frozen_col]).fillna(False)
            checks.add(f"database_matches_{frozen_col}", same.all(), failed_rows=int((~same).sum()))
    checks.sql(con, "valid_yield_and_coordinates", """SELECT count(*) FROM labels
        WHERE NOT isfinite(yield_kg_ha) OR yield_kg_ha < 0 OR yield_kg_ha IS NULL
        OR NOT isfinite(latitude) OR latitude NOT BETWEEN -90 AND 90 OR latitude IS NULL
        OR NOT isfinite(longitude) OR longitude NOT BETWEEN -180 AND 180 OR longitude IS NULL""")
    checks.sql(con, "source_yield_unit_conversion", """SELECT count(*) FROM labels
        WHERE source_yield IS NULL OR NOT isfinite(source_yield)
        OR source_yield_units IS NULL OR source_yield_units NOT IN ('kg/ha', 't/ha')
        OR abs(yield_kg_ha - source_yield * CASE source_yield_units WHEN 't/ha' THEN 1000 ELSE 1 END) > 1e-6""")
    checks.sql(con, "valid_season_windows", """SELECT count(*) FROM labels
        WHERE season_start IS NULL OR season_end IS NULL OR season_start > season_end""")
    check_monthly_tables(con, checks)
    for table, column, width in (("presto_embeddings", "embedding", 128),
                                 ("mosaiks_season", "chip", 1024), ("mosaiks_season", "field", 1024),
                                 ("mosaiks_monthly", "chip", 1024), ("mosaiks_monthly", "field", 1024)):
        # A clear field pixel is insufficient for a fully valid 3x3 convolution window.
        # The archived extractor legitimately stores NULL monthly vectors in that case.
        missing = f"{column} IS NULL OR " if table != "mosaiks_monthly" else ""
        checks.sql(con, f"{table}_{column}_finite_dimensions", f"""SELECT count(*) FROM {table}
            WHERE {missing}len({column}) <> {width}
            OR len(list_filter({column}, x -> x IS NULL OR NOT isfinite(x))) > 0""",
                   "Monthly MOSAIKS NULL vectors are allowed and counted separately as unavailable features."
                   if table == "mosaiks_monthly" else "")
    for table in ("downloads", "presto_embeddings", "mosaiks_season"):
        checks.sql(con, f"team_copy_complete_{table}", f"""SELECT count(*) FROM labels l
            LEFT JOIN {table} t USING(obs_id) WHERE t.obs_id IS NULL""",
                   "Completeness requirement for this shared team database, not a partial download.")
    checks.sql(con, "mosaiks_months_match_scenes", """SELECT count(*) FROM mosaiks_monthly m
        FULL JOIN scenes s USING(obs_id, month) WHERE m.obs_id IS NULL OR s.obs_id IS NULL""")
    checks.sql(con, "mosaiks_season_month_count", """SELECT count(*) FROM mosaiks_season s LEFT JOIN
        (SELECT obs_id, count(chip) n FROM mosaiks_monthly GROUP BY obs_id) m USING(obs_id)
        WHERE s.months_used IS DISTINCT FROM coalesce(m.n,0)""")
    # Independent pandas aggregates also check the SQL views used by downstream readers.
    values = con.execute("SELECT * FROM vegetation_indices").df()
    season = con.execute("SELECT * FROM season_indices").df().set_index("obs_id")
    grouped = values.groupby("obs_id")
    expected_ids = set(values.obs_id)
    aligned = season.index.is_unique and set(season.index) == expected_ids
    checks.add("season_summary_ids", aligned)
    if aligned:
        for index in FORMULAS:
            for stat in ("max", "mean"):
                expected = getattr(grouped[index], stat)().reindex(season.index)
                same = np.isclose(season[f"{index}_season_{stat}"], expected, rtol=1e-7, atol=1e-9, equal_nan=True)
                checks.add(f"season_{index}_{stat}", same.all(), failed_rows=int((~same).sum()))
    checks.sql(con, "master_clear_month_count", """SELECT count(*) FROM master m LEFT JOIN
        (SELECT obs_id, count(*) FILTER(WHERE NOT missing) n FROM monthly_bands GROUP BY obs_id) b USING(obs_id)
        WHERE m.months_with_data IS DISTINCT FROM coalesce(b.n,0)""")
    checks.add("master_row_count", con.execute("SELECT count(*) FROM master").fetchone()[0] == len(labels))
    return tables


def check_geometries(labels: pd.DataFrame, checks: Checks):
    """Geometry failures are structural; overlaps are separately retained as review flags."""
    invalid, outside = [], []
    for row in labels.itertuples():
        if row.geometry_type not in ("Polygon", "MultiPolygon"):
            continue
        try:
            geometry = from_wkt(row.geometry_wkt)
            if geometry is None or geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                invalid.append(row.obs_id)
            elif not geometry.covers(Point(row.lon, row.lat)):
                outside.append(row.obs_id)
        except (TypeError, ValueError, GEOSException):
            invalid.append(row.obs_id)
    checks.add("field_geometry_valid", not invalid, failed_rows=len(invalid))
    checks.add("representative_point_in_polygon", not outside, failed_rows=len(outside))


REVIEW_RULES = {
    "insufficient_clear_months": "Fewer than four nonmissing field-months; availability flag, not a bad yield.",
    "zero_yield": "Measured zero retained under the core cohort policy; do not drop automatically.",
    "exact_coordinates_repeated": "Coordinates repeat within the cohort, possibly across years; check field identity.",
    "near_coordinates_10m": "Frozen near_dup_10m flag, computed on the whole original cohort (including excluded rows).",
    "polygon_overlap": "Frozen overlap flag: more than 50% of the smaller polygon overlaps another polygon.",
    "impossible_date": "Known planting/harvest dates violate ordering or year rules; comparisons requiring missing dates remain unverified.",
    "missing_observation_date": "No usable harvest or crop-cut observation date; timing comparisons are unknown.",
    "observation_outside_window": "Recorded harvest/cut date lies outside the fixed imagery season.",
    "harvest_after_window": "Harvest date is later than the end of the imagery season.",
    "post_observation_scene": "At least one scene follows harvest/crop-cut; restrict claims to retrospective estimation.",
    "low_peak_ndvi": "Seasonal NDVI max < 0.5: possible location, timing or vegetation issue; not a crop-validity test.",
    "high_blue_reflectance": "At least one nonmissing month has B02 > 0.15; possible haze or bright ground.",
    "extreme_mtci": "At least one month has absolute MTCI > 100; inspect its denominator.",
    "reflectance_outside_0_1": "At least one finite reflectance is outside [0,1]; possible atmospheric/processing effect, not automatic corruption.",
    "missing_march": "Malawi only: March is not clear. Other cohorts are not assessed by this rule.",
    "provisional_yield_units": "Lacuna product/moisture conventions require provider confirmation.",
    "malawi_cut_area_unresolved": "Provider must clarify whether the main harvested area was 75 or 100 square metres.",
    "kenya_2020_protocol_inferred": "The 2020 cut-size interpretation is inferred; explicit provider confirmation remains useful.",
}


def review_records(con, labels: pd.DataFrame) -> pd.DataFrame:
    """Core eligible fields, including the nine Malawi fields without enough clear months."""
    records = labels.loc[labels.cohort.isin(CORE) & labels.include_primary].copy().set_index("obs_id")
    summary = con.execute("SELECT obs_id, months_with_data, ndvi_season_max FROM master").df().set_index("obs_id")
    records = records.join(summary, validate="one_to_one")
    records["usable_under_existing_rule"] = records.months_with_data.ge(4)
    records["insufficient_clear_months"] = records.months_with_data.lt(4) | records.months_with_data.isna()
    records["zero_yield"] = records.yield_kg_ha.eq(0)
    records["exact_coordinates_repeated"] = records.duplicated(["cohort", "lat", "lon"], keep=False)
    for dest, source in (("near_coordinates_10m", "near_dup_10m"), ("polygon_overlap", "polygon_overlap_dup"),
                          ("observation_outside_window", "date_outside_window"), ("provisional_yield_units", "unit_provisional")):
        records[dest] = records[source]
    records["missing_observation_date"] = records.obs_date.isna()
    records["impossible_date"] = records.impossible_date.astype("boolean").mask(records.plant_date.isna() & records.harvest_date.isna())
    records["observation_outside_window"] = records.observation_outside_window.astype("boolean").mask(records.obs_date.isna())
    records["harvest_after_window"] = records.harvest_date.gt(records.season_end).astype("boolean").mask(records.harvest_date.isna())
    records["low_peak_ndvi"] = records.ndvi_season_max.lt(0.5).astype("boolean").mask(records.ndvi_season_max.isna())
    records["malawi_cut_area_unresolved"] = records.cohort.eq("malawi_2023")
    records["kenya_2020_protocol_inferred"] = records.cohort.eq("kenya_oaf_2019_2020") & records.season_year.eq(2020)
    con.register("quality_dates", records.reset_index()[["obs_id", "obs_date"]])
    try:
        after = con.execute("""SELECT obs_id, count(*) AS n FROM scenes JOIN quality_dates USING(obs_id)
            WHERE acquired > obs_date GROUP BY obs_id""").df().set_index("obs_id")["n"]
    finally:
        con.unregister("quality_dates")
    records["post_observation_scene_months"] = records.index.to_series().map(after).fillna(0).astype(int)
    # Missing dates cannot be certified as having no post-observation scenes.
    records["post_observation_scene_months"] = records.post_observation_scene_months.astype("Int64").mask(records.obs_date.isna())
    records["post_observation_scene"] = records.post_observation_scene_months.gt(0)
    outside = " OR ".join(f"{b} < 0 OR {b} > 1" for b in BANDS)
    for flag, table, condition in (("high_blue_reflectance", "monthly_bands", "NOT missing AND b02 > 0.15"),
                                    ("extreme_mtci", "vegetation_indices", "abs(mtci) > 100"),
                                    ("reflectance_outside_0_1", "monthly_bands", f"NOT missing AND ({outside})"),
                                    ("missing_march", "coverage", "month = '2023-03' AND state <> 'clear'")):
        ids = con.execute(f"SELECT DISTINCT obs_id FROM {table} WHERE {condition}").df().obs_id
        records[flag] = records.index.isin(ids)
    march = con.execute("SELECT obs_id, state FROM coverage WHERE month='2023-03'").df().set_index("obs_id")["state"]
    march_state = records.index.to_series().map(march)
    records["missing_march"] = march_state.ne("clear").astype("boolean").mask(
        records.cohort.ne("malawi_2023") | march_state.isna())
    return records.reset_index()


def summarize_reviews(records: pd.DataFrame) -> list[dict]:
    result = []
    for cohort, rows in records.groupby("cohort", sort=True):
        result.append({"cohort": cohort, "eligible_fields": len(rows),
                       "usable_fields": int(rows.usable_under_existing_rule.sum()),
                       "flags": {rule: {"flagged": int(rows[rule].fillna(False).sum()),
                                        "assessed": int(rows[rule].notna().sum()),
                                        "unknown_or_not_applicable": int(rows[rule].isna().sum())}
                                 for rule in REVIEW_RULES}})
    return result
