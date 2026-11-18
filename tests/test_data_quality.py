"""Synthetic contradictions in monthly satellite data and geometry, without model fitting."""

import hashlib
import importlib.util
import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.quality import (
    BANDS,
    REVIEW_RULES,
    Checks,
    check_database,
    check_geometries,
    check_monthly_tables,
    review_records,
    summarize_reviews,
)


@pytest.fixture
def monthly_db():
    """One valid point observation, one month, one accepted scene, and five hand-calculated indices."""
    with duckdb.connect(":memory:") as con:
        con.execute((ROOT / "sql/schema.sql").read_text())
        con.execute("""INSERT INTO labels
            (obs_id, cohort, dataset, source_id, source_row, country, year, yield_kg_ha,
             source_yield, source_yield_units, latitude, longitude, geometry_type,
             season_start, season_end, include_primary, exclusion_reason)
            VALUES ('test:f1', 'malawi_2023', 'test', 'f1', 1, 'malawi', 2023, 2000,
                    2, 't/ha', -13, 33, 'Point', '2023-03-01', '2023-03-31', TRUE, '')""")
        con.execute("""INSERT INTO downloads
            (obs_id, record_dir, status, aoi_type, aoi_pixels, field_pixels, aoi_inside_chip,
             catalog_scenes, accepted_months, crs, search_start, search_end)
            VALUES ('test:f1', 'synthetic', 'complete', 'point_pixel', 1, 1, TRUE,
                    1, 1, 'EPSG:32736', '2023-03-01', '2023-03-31')""")
        con.execute("""INSERT INTO scenes VALUES
            ('test:f1', 'scene1', '2023-03-15', '2023-03', 'S2A', '36LWL', 10, 1, 1)""")
        con.execute("INSERT INTO coverage VALUES ('test:f1', '2023-03', 'clear', 'scene1')")
        con.execute("""INSERT INTO monthly_bands VALUES
            ('test:f1', '2023-03', .03, .1, .2, .3, .4, .45, .6, .65, .3, .25, 1, FALSE)""")
        con.execute("""INSERT INTO vegetation_indices VALUES
            ('test:f1', '2023-03', .5, 5, 3, ?, .2)""", [1 / 3])
        yield con


def monthly_checks(con):
    checks = Checks()
    check_monthly_tables(con, checks)
    return checks


def by_rule(checks):
    return {row["rule"]: row for row in checks.rows}


def mark_month_missing(con):
    con.execute("DELETE FROM scenes")
    con.execute("UPDATE coverage SET state='cloudy', item_id=NULL")
    con.execute("UPDATE downloads SET accepted_months=0")
    assignments = ", ".join(f"{band}=NULL" for band in BANDS)
    con.execute(f"UPDATE monthly_bands SET missing=TRUE, field_pixels=0, {assignments}")
    con.execute("UPDATE vegetation_indices SET ndvi=NULL, gcvi=NULL, mtci=NULL, ndvi705=NULL, ndvi740=NULL")


def test_consistent_monthly_data_passes_every_integrity_check(monthly_db):
    checks = monthly_checks(monthly_db)
    assert checks.passed
    assert checks.rows and all(row["failed_rows"] == 0 for row in checks.rows)


def test_missing_month_requires_null_bands_not_zero_imputation(monthly_db):
    mark_month_missing(monthly_db)
    assert monthly_checks(monthly_db).passed
    zeros = ", ".join(f"{band}=0" for band in BANDS)
    monthly_db.execute(f"UPDATE monthly_bands SET {zeros}")
    checks = monthly_checks(monthly_db)
    assert not checks.passed
    assert by_rule(checks)["monthly_band_null_and_finite_contract"]["failed_rows"] == 1


@pytest.mark.parametrize("mutation,rule", [
    ("UPDATE coverage SET item_id='wrong_scene'", "coverage_matches_accepted_scenes"),
    ("UPDATE scenes SET acquired='2023-04-15'", "scene_dates_match_month_and_window"),
    ("UPDATE scenes SET month='2023-04'", "scene_dates_match_month_and_window"),
    ("UPDATE vegetation_indices SET ndvi=.9", "index_formula_ndvi"),
    ("DELETE FROM coverage", "coverage_expected_calendar"),
    ("UPDATE downloads SET accepted_months=2", "download_accepted_month_count"),
    ("UPDATE monthly_bands SET field_pixels=2", "monthly_field_pixel_count"),
    ("UPDATE downloads SET search_start='2023-02-01'", "download_window_and_pixel_contract"),
    ("UPDATE scenes SET clear_fraction_aoi=.5", "accepted_scene_quality_contract"),
])
def test_corruption_is_reported_by_the_relevant_check(monthly_db, mutation, rule):
    monthly_db.execute(mutation)
    checks = monthly_checks(monthly_db)
    assert not checks.passed
    assert by_rule(checks)[rule]["failed_rows"] == 1


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_nonfinite_reflectance_in_an_observed_month_fails(monthly_db, bad_value):
    monthly_db.execute("UPDATE monthly_bands SET b02=?", [bad_value])
    checks = monthly_checks(monthly_db)
    assert not checks.passed
    assert by_rule(checks)["monthly_band_null_and_finite_contract"]["failed_rows"] == 1


def test_zero_index_denominator_requires_null_and_rejects_a_numeric_substitute(monthly_db):
    monthly_db.execute("UPDATE monthly_bands SET b05=b04")
    monthly_db.execute("UPDATE vegetation_indices SET mtci=NULL, ndvi705=.5")
    assert monthly_checks(monthly_db).passed
    monthly_db.execute("UPDATE vegetation_indices SET mtci=0")
    checks = monthly_checks(monthly_db)
    assert not checks.passed
    assert by_rule(checks)["index_formula_mtci"]["failed_rows"] == 1


def test_slight_negative_reflectance_is_not_itself_corruption(monthly_db):
    # Atmospheric correction can give negative reflectance. B02 enters none of the five indices.
    monthly_db.execute("UPDATE monthly_bands SET b02=-.001")
    assert monthly_checks(monthly_db).passed


def polygon_labels(wkt, lon=.5, lat=.5):
    return pd.DataFrame({"obs_id": ["test:f1"], "geometry_type": ["Polygon"],
                         "geometry_wkt": [wkt], "lon": [lon], "lat": [lat]})


@pytest.mark.parametrize("lon,lat", [(.5, .5), (0.0, .5)])
def test_polygon_covers_interior_and_boundary_representative_points(lon, lat):
    labels = polygon_labels("POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))", lon, lat)
    checks = Checks()
    check_geometries(labels, checks)
    assert checks.passed


def test_representative_point_outside_its_polygon_fails():
    labels = polygon_labels("POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))", lon=2, lat=2)
    checks = Checks()
    check_geometries(labels, checks)
    result = by_rule(checks)
    assert result["field_geometry_valid"]["status"] == "pass"
    assert result["representative_point_in_polygon"]["failed_rows"] == 1


@pytest.mark.parametrize("wkt", ["POLYGON EMPTY", "not a geometry", "POINT (0 0)",
                                "POLYGON ((0 0, 1 1, 1 0, 0 1, 0 0))", None])
def test_empty_malformed_or_invalid_polygon_is_reported_without_crashing(wkt):
    checks = Checks()
    check_geometries(polygon_labels(wkt), checks)
    assert not checks.passed
    assert by_rule(checks)["field_geometry_valid"]["failed_rows"] == 1


def test_review_summary_counts_unknown_dates_separately_from_unflagged_fields():
    records = pd.DataFrame({"cohort": ["kenya_oaf_2019_2020"] * 3,
                            "usable_under_existing_rule": [True, True, False]})
    for rule in REVIEW_RULES:
        records[rule] = pd.array([False, False, False], dtype="boolean")
    records["post_observation_scene"] = pd.array([True, False, pd.NA], dtype="boolean")
    records["missing_observation_date"] = pd.array([False, False, True], dtype="boolean")
    records["missing_march"] = pd.array([pd.NA] * 3, dtype="boolean")
    before = records.copy(deep=True)
    summary = summarize_reviews(records)[0]
    assert summary["eligible_fields"] == 3 and summary["usable_fields"] == 2
    assert summary["flags"]["post_observation_scene"] == {
        "flagged": 1, "assessed": 2, "unknown_or_not_applicable": 1}
    assert summary["flags"]["missing_observation_date"] == {
        "flagged": 1, "assessed": 3, "unknown_or_not_applicable": 0}
    assert summary["flags"]["missing_march"] == {
        "flagged": 0, "assessed": 0, "unknown_or_not_applicable": 3}
    pd.testing.assert_frame_equal(records, before)


def frozen_labels_for_db(con):
    """The frozen-label column names needed to compare and review this synthetic database."""
    labels = con.execute("SELECT * FROM labels").df().rename(
        columns={"year": "season_year", "latitude": "lat", "longitude": "lon"})
    for column in ["near_dup_10m", "polygon_overlap_dup", "date_outside_window",
                   "unit_provisional", "impossible_date"]:
        labels[column] = False
    for column, value in [("plant_date", "2023-03-01"), ("harvest_date", "2023-03-10"),
                          ("obs_date", "2023-03-10")]:
        labels[column] = pd.to_datetime([value] * len(labels))
    return labels


def test_missing_observation_and_harvest_dates_stay_unknown_in_timing_reviews(monthly_db):
    monthly_db.execute((ROOT / "sql/views.sql").read_text())
    labels = frozen_labels_for_db(monthly_db)
    labels["cohort"] = "kenya_oaf_2019_2020"
    labels["obs_date"] = pd.NaT
    labels["harvest_date"] = pd.NaT
    labels["plant_date"] = pd.NaT
    reviewed = review_records(monthly_db, labels)
    row = reviewed.iloc[0]
    assert row.missing_observation_date
    for column in ["observation_outside_window", "harvest_after_window", "impossible_date",
                   "post_observation_scene", "post_observation_scene_months"]:
        assert pd.isna(row[column]), column
    summary = summarize_reviews(reviewed)[0]
    for column in ["observation_outside_window", "harvest_after_window", "post_observation_scene"]:
        assert summary["flags"][column] == {
            "flagged": 0, "assessed": 0, "unknown_or_not_applicable": 1}


def test_missing_ndvi_peak_is_unknown_not_a_certified_non_low_peak(monthly_db):
    mark_month_missing(monthly_db)
    monthly_db.execute((ROOT / "sql/views.sql").read_text())
    reviewed = review_records(monthly_db, frozen_labels_for_db(monthly_db))
    assert pd.isna(reviewed.iloc[0].low_peak_ndvi)
    assert summarize_reviews(reviewed)[0]["flags"]["low_peak_ndvi"] == {
        "flagged": 0, "assessed": 0, "unknown_or_not_applicable": 1}


@pytest.mark.parametrize("state,expected", [(None, None), ("clear", False), ("cloudy", True), ("no_scene", True)])
def test_malawi_march_review_distinguishes_missing_coverage_from_known_clouds(monthly_db, state, expected):
    if state is None:
        monthly_db.execute("DELETE FROM coverage")
    elif state != "clear":
        mark_month_missing(monthly_db)
        monthly_db.execute("UPDATE coverage SET state=?", [state])
    monthly_db.execute((ROOT / "sql/views.sql").read_text())
    reviewed = review_records(monthly_db, frozen_labels_for_db(monthly_db))
    actual = reviewed.iloc[0].missing_march
    if expected is None:
        assert pd.isna(actual)
    else:
        assert bool(actual) is expected


@pytest.mark.parametrize("march_chip_missing", [True, False])
def test_monthly_mosaiks_null_vectors_are_allowed_and_month_count_uses_available_chips(monthly_db, march_chip_missing):
    # March can lack usable convolution windows despite having a clear point pixel.
    # April supplies valid features; seasonal values remain available in both cases.
    monthly_db.execute("UPDATE labels SET season_end='2023-04-30'")
    monthly_db.execute("UPDATE downloads SET search_end='2023-04-30', catalog_scenes=2, accepted_months=2")
    monthly_db.execute("""INSERT INTO scenes SELECT obs_id, 'scene2', DATE '2023-04-15', '2023-04',
        satellite, tile, tile_cloud_cover, clear_fraction_aoi, field_valid_pixels FROM scenes""")
    monthly_db.execute("INSERT INTO coverage VALUES ('test:f1', '2023-04', 'clear', 'scene2')")
    monthly_db.execute("INSERT INTO monthly_bands SELECT * REPLACE ('2023-04' AS month) FROM monthly_bands")
    monthly_db.execute("INSERT INTO vegetation_indices SELECT * REPLACE ('2023-04' AS month) FROM vegetation_indices")
    monthly_db.execute("INSERT INTO presto_embeddings VALUES ('test:f1', ?)", [[1.0] * 128])
    vector = [1.0] * 1024
    monthly_db.execute("INSERT INTO mosaiks_monthly VALUES ('test:f1', '2023-03', ?, NULL)",
                       [None if march_chip_missing else vector])
    monthly_db.execute("INSERT INTO mosaiks_monthly VALUES ('test:f1', '2023-04', ?, ?)", [vector, vector])
    monthly_db.execute("INSERT INTO mosaiks_season VALUES ('test:f1', ?, ?, ?)",
                       [1 if march_chip_missing else 2, vector, vector])
    monthly_db.execute((ROOT / "sql/views.sql").read_text())
    labels = frozen_labels_for_db(monthly_db)
    checks = Checks()
    check_database(monthly_db, labels, checks)
    assert checks.passed, [row for row in checks.rows if row["status"] != "pass"]

    monthly_db.execute("UPDATE mosaiks_season SET months_used=months_used+1")
    wrong_count = Checks()
    check_database(monthly_db, labels, wrong_count)
    assert by_rule(wrong_count)["mosaiks_season_month_count"]["failed_rows"] == 1


def test_a_null_mosaiks_vector_element_is_corrupt_even_though_whole_missing_vectors_are_allowed(monthly_db):
    # Use only the vector-related results: this minimal fixture deliberately has no season features.
    monthly_db.execute((ROOT / "sql/views.sql").read_text())
    monthly_db.execute("INSERT INTO mosaiks_monthly VALUES ('test:f1', '2023-03', NULL, ?)",
                       [[None] + [0.0] * 1023])
    checks = Checks()
    check_database(monthly_db, frozen_labels_for_db(monthly_db), checks)
    results = by_rule(checks)
    assert results["mosaiks_monthly_chip_finite_dimensions"]["status"] == "pass"
    assert results["mosaiks_monthly_field_finite_dimensions"]["failed_rows"] == 1


def test_cli_saves_failure_report_without_deduplicating_corrupt_database(monthly_db, tmp_path, monkeypatch):
    script = ROOT / "scripts/quality/audit_data_quality.py"
    spec = importlib.util.spec_from_file_location("quality_audit_failure_test", script)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    project = tmp_path / "project"
    database = project / "data/cropyield.duckdb"
    database.parent.mkdir(parents=True)

    # Copy the real schema and tiny fixture to a file that the CLI opens read-only.
    with duckdb.connect(str(database)) as disk:
        disk.execute((ROOT / "sql/schema.sql").read_text())
        for (table,) in monthly_db.execute("SHOW TABLES").fetchall():
            disk.register("fixture_rows", monthly_db.execute(f"SELECT * FROM {table}").df())
            disk.execute(f"INSERT INTO {table} SELECT * FROM fixture_rows")
            disk.unregister("fixture_rows")
        disk.execute("INSERT INTO labels SELECT * FROM labels")
        disk.execute((ROOT / "sql/views.sql").read_text())

    def write(relative, content):
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    source = write("data/audit/test_screened_candidates.csv", "source_id,yield_kg_ha\nf1,2000\n")
    labels = frozen_labels_for_db(monthly_db)
    labels["source_sha256"] = digest(source)
    labels_path = project / "data/processed/labels_v1.parquet"
    labels_path.parent.mkdir(parents=True)
    labels.to_parquet(labels_path, index=False)
    write("data/splits/manifest.json", json.dumps({"labels_sha256": digest(labels_path), "files": {}}))
    write("configs/team_database_v1.json", json.dumps({"bytes": database.stat().st_size, "sha256": digest(database)}))
    monthly_db.execute("SELECT obs_id, month, item_id FROM scenes").df().to_parquet(
        project / "configs/sentinel2_scenes_v1.parquet", index=False)
    write("data/metadata/download_manifest.json", "{}")
    for constant, filename in [("OAF_WORKBOOK", "oaf.xlsx"), ("LACUNA_GEOJSON", "lacuna.geojson"),
                               ("MALAWI_2023_ZIP", "malawi.zip")]:
        monkeypatch.setattr(audit, constant, write(f"data/raw/{filename}", "synthetic provider fixture"))
    for relative in ["scripts/quality/audit_data_quality.py", "src/cropyield/data/quality.py", "src/cropyield/data/labels.py"]:
        write(relative, (ROOT / relative).read_text())

    monkeypatch.setattr(audit, "ROOT", project)
    # Provider reconciliation is independent of this database-join failure scenario.
    monkeypatch.setattr(audit, "check_labels", lambda labels: [])
    monkeypatch.setattr(audit, "check_against_raw", lambda *args: [])
    monkeypatch.setattr(audit, "oaf_groups", lambda: pd.DataFrame())
    monkeypatch.setattr(audit, "lacuna_groups", lambda: pd.DataFrame())

    def git_metadata(command, **kwargs):
        assert command[0] == "git"
        return "fixture\n" if command[1] == "branch" else "0" * 40 + "\n" if command[1] == "rev-parse" else ""

    monkeypatch.setattr(audit.subprocess, "check_output", git_metadata)
    before = digest(database)
    output = tmp_path / "quality-report"
    assert audit.main(["--db", str(database), "--output", str(output)]) == 1
    report = json.loads((output / "summary.json").read_text())
    checks = {row["rule"]: row for row in report["checks"]}
    assert not report["integrity_passed"]
    assert checks["labels_unique_keys"]["status"] == "fail"
    assert checks["detailed_review_available"]["status"] == "fail"
    assert report["cohorts"] == []
    assert report["tables"]["labels"] == 2
    assert report["observations_modified_or_removed"] == 0
    assert checks["all_protected_inputs_unchanged"]["status"] == "pass"
    assert (output / "report.html").is_file()
    assert "Detailed reviews unavailable" in (output / "report.html").read_text()
    assert digest(database) == before
    with duckdb.connect(str(database), read_only=True) as disk:
        assert disk.execute("SELECT count(*) FROM labels").fetchone()[0] == 2
