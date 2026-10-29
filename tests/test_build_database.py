"""scripts/build_database.py on the synthetic chip folder: every table and view exists and holds the right values."""
import importlib.util
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from conftest import FIELD_REFLECTANCE, RECORD, SIZE, add_scenes, make_record_dir, write_scene

from cropyield.data.cohorts import COHORTS, load_cohort
from cropyield.data.database import wide
from cropyield.longpath import filesystem_path
from cropyield.models.presto_weights import weights_verified

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_database.py"
spec = importlib.util.spec_from_file_location("build_database", SCRIPT)
build_database = importlib.util.module_from_spec(spec)
sys.modules["build_database"] = build_database  # the script's dataclass needs its module importable
spec.loader.exec_module(build_database)

OBS_ID = f"{RECORD['dataset']}:{RECORD['source_id']}"
# Audit row 2 of Malawi 2023: a download that found no usable scene.
EMPTY_OBS_ID = "malawi_2023:626290f6-99b2-4a44-b233-8df0e13d3e63"
# Audit row 3 of Malawi 2023: a download that failed part-way (one scene accepted, then an error).
FAILED_OBS_ID = "malawi_2023:10738537-aded-4abe-bc18-e3d8ce52f7f7"
# The Malawi 2023 season window (cohorts.py); the fixture chip is downloaded for exactly this window.
SEASON = {"start_date": "2022-10-01", "end_date": "2023-06-30"}
MONTHS = ["2022-10", "2022-11", "2022-12", "2023-01", "2023-02", "2023-03", "2023-04", "2023-05", "2023-06"]
CLEAR_MONTHS = ("2023-03", "2023-05")
TABLES = {"labels", "downloads", "scenes", "coverage", "monthly_bands", "vegetation_indices",
          "presto_embeddings", "mosaiks_monthly", "mosaiks_season", "build_info"}
VIEWS = {"season_indices", "master", "monthly"}
K = 8  # length of the synthetic MOSAIKS vectors


def set_status(record_dir: Path, status: str, attempts: list[dict]) -> None:
    """Overwrite the downloader status and attempts of a synthetic record folder."""
    record_json = Path(filesystem_path(record_dir / "record.json"))
    meta = json.loads(record_json.read_text())
    meta.update(status=status, attempts=attempts)
    record_json.write_text(json.dumps(meta))


def imagery_dir(root: Path) -> Path:
    """data/imagery/sentinel2 layout (run-*/records/<folder>) with three records:
    OBS_ID with scenes in March and May; EMPTY_OBS_ID with Dec and Jan rejected for clouds and no
    scene accepted; FAILED_OBS_ID with March accepted, then a failed download in April.
    """
    imagery = root / "imagery"
    records = imagery / "run-synthetic" / "records"
    interior = np.zeros((SIZE, SIZE), dtype=bool)
    interior[2:4, 2:4] = True
    record_dir, touched = make_record_dir(records, {**RECORD, **SEASON})
    write_scene(record_dir, "S2A_T36LWL_20230312T080000_L2A", "2023-03-12", touched, interior)
    write_scene(record_dir, "S2B_T36LWL_20230520T080000_L2A", "2023-05-20", touched, interior, invalid=[(2, 2), (3, 3)])
    add_scenes(record_dir, ["S2A_T36LWL_20230312T080000_L2A", "S2B_T36LWL_20230520T080000_L2A"])

    empty_dir, _ = make_record_dir(records, {**RECORD, "source_id": EMPTY_OBS_ID.split(":")[1], "source_row": "2", **SEASON})
    set_status(empty_dir, "no_clear_scenes", [{"month": "2022-12", "status": "rejected_cloud_or_nodata"},
                                              {"month": "2023-01", "status": "rejected_cloud_or_nodata"}])

    failed_dir, touched = make_record_dir(records, {**RECORD, "source_id": FAILED_OBS_ID.split(":")[1], "source_row": "3", **SEASON})
    write_scene(failed_dir, "S2A_T36LWL_20230313T080000_L2A", "2023-03-13", touched, interior)
    add_scenes(failed_dir, ["S2A_T36LWL_20230313T080000_L2A"])
    set_status(failed_dir, "partial_error", [{"month": "2023-03", "status": "accepted"},
                                            {"month": "2023-04", "status": "error"}])
    return imagery


def mosaiks_vector(value: float) -> list[float]:
    return [float(value)] * K


def mosaiks_dir(root: Path) -> Path:
    """data/features/mosaiks layout: monthly.parquet (the two clear months), season.parquet, params.json."""
    folder = root / "mosaiks"
    folder.mkdir()
    vectors = pa.list_(pa.float32())
    pq.write_table(pa.table({
        "obs_id": [OBS_ID, OBS_ID],
        "month": list(CLEAR_MONTHS),
        "chip": pa.array([mosaiks_vector(0.25), mosaiks_vector(0.75)], type=vectors),
        "field": pa.array([mosaiks_vector(1.0), None], type=vectors),   # a NULL vector stays NULL
    }), folder / "monthly.parquet")
    pq.write_table(pa.table({
        "obs_id": [OBS_ID],
        "months_used": pa.array([2], type=pa.int64()),
        "chip": pa.array([mosaiks_vector(0.5)], type=vectors),
        "field": pa.array([mosaiks_vector(1.0)], type=vectors),
    }), folder / "season.parquet")
    (folder / "params.json").write_text(json.dumps({"k_features": K, "seed": 291}), encoding="utf-8")
    return folder


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    root = tmp_path_factory.mktemp("build")
    path = root / "cropyield.duckdb"
    assert build_database.main(["--db", str(path), "--imagery-dir", str(imagery_dir(root)),
                                "--mosaiks-dir", str(mosaiks_dir(root)), "--no-presto"]) == 0
    con = duckdb.connect(str(path), read_only=True)
    yield con
    con.close()


def test_every_table_and_view_exists(db):
    kinds = db.sql("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = 'main'").fetchall()
    assert {name for name, kind in kinds if kind == "BASE TABLE"} == TABLES
    assert {name for name, kind in kinds if kind == "VIEW"} == VIEWS
    assert db.sql("SELECT n_labels, n_downloads, n_embeddings, presto_embeddings_built, mosaiks_features FROM build_info") \
        .fetchone() == (db.sql("SELECT count(*) FROM labels").fetchone()[0], 3, 0, False, K)
    assert json.loads(db.sql("SELECT mosaiks_params FROM build_info").fetchone()[0]) == {"k_features": K, "seed": 291}


def test_vectors_are_stored_as_array_columns(db):
    types = dict(db.sql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'presto_embeddings'").fetchall())
    assert types == {"obs_id": "VARCHAR", "embedding": "FLOAT[128]"}
    types = dict(db.sql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'mosaiks_monthly'").fetchall())
    assert types == {"obs_id": "VARCHAR", "month": "VARCHAR", "chip": "FLOAT[]", "field": "FLOAT[]"}


def test_run_sql_file_reports_the_failing_statement(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("CREATE TABLE ok (x INT);  -- a ; inside a comment is fine\nSELECT * FROM missing_table;\n")
    with duckdb.connect() as con, pytest.raises(RuntimeError, match="bad.sql, statement 2"):
        build_database.run_sql_file(con, bad)


def test_labels_hold_every_cohort_row_with_proper_types(db):
    assert db.sql("SELECT count(*) FROM labels").fetchone()[0] == sum(len(load_cohort(name)) for name in COHORTS)
    types = dict(db.sql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'labels'").fetchall())
    assert types["label_date"] == types["season_start"] == "DATE" and types["yield_kg_ha"] == "DOUBLE"
    row = db.sql("SELECT cohort, yield_kg_ha, season_start, label_date, field_polygon FROM labels WHERE obs_id = ?",
                 params=[OBS_ID]).fetchone()
    assert row[0] == "malawi_2023" and row[1] == 2950.0
    assert str(row[2]) == "2022-10-01" and str(row[3]) == "2023-05-17"  # observation_time 2023/05/17 08:55
    assert row[4].startswith('{"type": "Polygon"')


def test_monthly_bands_match_the_fixture_reflectance_and_are_null_elsewhere(db):
    rows = db.sql("SELECT month, b04, b08, field_pixels, missing FROM monthly_bands WHERE obs_id = ? ORDER BY month",
                  params=[OBS_ID]).fetchall()
    assert [r[0] for r in rows] == MONTHS
    by_month = {r[0]: r[1:] for r in rows}
    for month, pixels in (("2023-03", 4), ("2023-05", 2)):
        b04, b08, field_pixels, missing = by_month[month]
        assert b04 == pytest.approx(FIELD_REFLECTANCE["B04"]) and b08 == pytest.approx(FIELD_REFLECTANCE["B08"])
        assert (field_pixels, missing) == (pixels, False)
    for month in set(MONTHS) - set(CLEAR_MONTHS):
        assert by_month[month] == (None, None, 0, True)


def test_ndvi_is_computed_from_the_stored_bands(db):
    ndvi, b04, b08 = db.sql("""
        SELECT v.ndvi, m.b04, m.b08
        FROM vegetation_indices AS v
        JOIN monthly_bands AS m USING (obs_id, month)
        WHERE obs_id = ? AND month = '2023-03'
    """, params=[OBS_ID]).fetchone()
    assert ndvi == pytest.approx((b08 - b04) / (b08 + b04))
    assert db.sql("SELECT count(*) FILTER (WHERE ndvi IS NULL) FROM vegetation_indices").fetchone()[0] == len(MONTHS) - 2


def test_coverage_and_scenes_describe_the_two_accepted_months(db):
    states = dict(db.sql("SELECT month, state FROM coverage WHERE obs_id = ?", params=[OBS_ID]).fetchall())
    assert states == {m: ("clear" if m in CLEAR_MONTHS else "no_scene") for m in MONTHS}
    scenes = db.sql("SELECT satellite, tile, month, field_valid_pixels FROM scenes WHERE obs_id = ? ORDER BY acquired",
                    params=[OBS_ID]).fetchall()
    assert scenes == [("S2A", "36LWL", "2023-03", 4), ("S2B", "36LWL", "2023-05", 2)]


def test_a_download_without_scenes_has_coverage_but_no_band_rows(db):
    states = dict(db.sql("SELECT month, state FROM coverage WHERE obs_id = ?", params=[EMPTY_OBS_ID]).fetchall())
    assert states == {m: ("cloudy" if m in ("2022-12", "2023-01") else "no_scene") for m in MONTHS}
    for table in ("monthly_bands", "vegetation_indices", "scenes"):
        assert db.sql(f"SELECT count(*) FROM {table} WHERE obs_id = ?", params=[EMPTY_OBS_ID]).fetchone()[0] == 0
    assert db.sql("SELECT has_imagery, download_status, months_with_data FROM master WHERE obs_id = ?",
                  params=[EMPTY_OBS_ID]).fetchone() == (True, "no_clear_scenes", 0)


def test_a_failed_download_is_download_error_in_every_month_even_the_accepted_one(db):
    states = db.sql("SELECT DISTINCT state, item_id FROM coverage WHERE obs_id = ?", params=[FAILED_OBS_ID]).fetchall()
    assert states == [("download_error", None)]
    for table in ("monthly_bands", "vegetation_indices"):
        assert db.sql(f"SELECT count(*) FROM {table} WHERE obs_id = ?", params=[FAILED_OBS_ID]).fetchone()[0] == 0
    assert db.sql("SELECT count(*) FROM scenes WHERE obs_id = ?", params=[FAILED_OBS_ID]).fetchone()[0] == 1
    assert db.sql("SELECT DISTINCT coverage_state, b04 FROM monthly WHERE obs_id = ?",
                  params=[FAILED_OBS_ID]).fetchall() == [("download_error", None)]


def test_mosaiks_tables_hold_the_parquet_vectors_as_arrays(db):
    rows = db.sql("SELECT month, len(chip), chip[1], field IS NULL FROM mosaiks_monthly ORDER BY month").fetchall()
    assert rows == [("2023-03", K, 0.25, False), ("2023-05", K, 0.75, True)]
    assert db.sql("SELECT obs_id, months_used, len(chip), field[1] FROM mosaiks_season").fetchall() == [(OBS_ID, 2, K, 1.0)]


def test_master_has_one_row_per_label_and_imagery_only_for_the_synthetic_records(db):
    assert db.sql("SELECT count(*) FROM master").fetchone()[0] == db.sql("SELECT count(*) FROM labels").fetchone()[0]
    assert db.sql("SELECT obs_id FROM master WHERE has_imagery ORDER BY obs_id").fetchall() \
        == sorted([(OBS_ID,), (EMPTY_OBS_ID,), (FAILED_OBS_ID,)])
    row = db.sql("""
        SELECT download_status, months_with_data, ndvi_season_max, presto_embedding,
               len(mosaiks_chip), mosaiks_field[1], mosaiks_months_used
        FROM master
        WHERE obs_id = ?
    """, params=[OBS_ID]).fetchone()
    expected_ndvi = (FIELD_REFLECTANCE["B08"] - FIELD_REFLECTANCE["B04"]) / (FIELD_REFLECTANCE["B08"] + FIELD_REFLECTANCE["B04"])
    assert row == ("complete", 2, pytest.approx(expected_ndvi), None, K, 1.0, 2)  # no Presto: built with --no-presto
    without_imagery = db.sql("""
        SELECT count(*)
        FROM master
        WHERE NOT has_imagery AND months_with_data = 0
          AND ndvi_season_max IS NULL AND presto_embedding IS NULL AND mosaiks_chip IS NULL
    """).fetchone()[0]
    assert without_imagery == db.sql("SELECT count(*) FROM labels").fetchone()[0] - 3


def test_season_indices_view_takes_max_and_mean_over_the_months_with_a_value(db):
    assert db.sql("SELECT count(*) FROM season_indices").fetchone()[0] == 1
    ndvi_max, ndvi_mean, gcvi_max = db.sql("SELECT ndvi_season_max, ndvi_season_mean, gcvi_season_max FROM season_indices").fetchone()
    expected_ndvi = (FIELD_REFLECTANCE["B08"] - FIELD_REFLECTANCE["B04"]) / (FIELD_REFLECTANCE["B08"] + FIELD_REFLECTANCE["B04"])
    assert ndvi_max == pytest.approx(expected_ndvi) and ndvi_mean == pytest.approx(expected_ndvi)  # both months equal
    assert gcvi_max == pytest.approx(FIELD_REFLECTANCE["B08"] / FIELD_REFLECTANCE["B03"] - 1)


def test_monthly_view_has_one_row_per_downloaded_observation_and_month(db):
    assert db.sql("SELECT count(*) FROM monthly").fetchone()[0] == 3 * len(MONTHS)
    rows = db.sql("""
        SELECT month, cohort, coverage_state, b04, ndvi,
               len(mosaiks_chip) AS chip_length, mosaiks_field IS NULL AS field_is_null, yield_kg_ha
        FROM monthly
        WHERE obs_id = ?
        ORDER BY month
    """, params=[OBS_ID]).df()
    assert list(rows["month"]) == MONTHS and set(rows["cohort"]) == {"malawi_2023"} and set(rows["yield_kg_ha"]) == {2950.0}
    clear = rows.set_index("month").loc[list(CLEAR_MONTHS)]
    assert list(clear["coverage_state"]) == ["clear", "clear"]
    assert clear["b04"].tolist() == pytest.approx([FIELD_REFLECTANCE["B04"]] * 2) and clear["ndvi"].notna().all()
    assert clear["chip_length"].tolist() == [K, K] and clear["field_is_null"].tolist() == [False, True]
    other = rows.set_index("month").drop(list(CLEAR_MONTHS))
    assert set(other["coverage_state"]) == {"no_scene"} and other[["b04", "ndvi", "chip_length"]].isna().all().all()


def test_wide_spreads_an_array_column_into_numbered_columns(db):
    rows = db.sql("SELECT obs_id, yield_kg_ha, mosaiks_chip FROM master WHERE has_imagery ORDER BY obs_id").df()
    X = wide(rows, "mosaiks_chip", "mosaiks")
    assert X.shape == (3, K) and list(X.columns) == [f"mosaiks_{i:03d}" for i in range(K)]
    assert X.index.equals(rows.index)
    with_features = X.loc[rows["obs_id"] == OBS_ID].to_numpy()
    without = X.loc[rows["obs_id"] != OBS_ID].to_numpy()
    assert (with_features == 0.5).all() and np.isnan(without).all()
    with pytest.raises(ValueError, match="presto_embedding holds no values"):
        wide(rows.assign(presto_embedding=None), "presto_embedding", "presto")


def test_without_mosaiks_files_the_tables_stay_empty_and_a_hint_is_printed(tmp_path, capsys):
    path = tmp_path / "no_mosaiks.duckdb"
    assert build_database.main(["--db", str(path), "--imagery-dir", str(imagery_dir(tmp_path)),
                                "--mosaiks-dir", str(tmp_path / "nowhere"), "--no-presto"]) == 0
    assert "python scripts/features/mosaiks_features.py" in capsys.readouterr().out
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.sql("SELECT count(*) FROM mosaiks_monthly").fetchone()[0] == 0
        assert con.sql("SELECT count(*) FROM mosaiks_season").fetchone()[0] == 0
        assert con.sql("SELECT mosaiks_features, mosaiks_params FROM build_info").fetchone() == (None, None)
        assert con.sql("SELECT mosaiks_chip, mosaiks_months_used FROM master WHERE obs_id = ?", params=[OBS_ID]).fetchone() \
            == (None, None)


@pytest.mark.skipif(not weights_verified(), reason="run scripts/models/get_presto.py first")
def test_presto_embeddings_fill_the_master_view(tmp_path):
    pytest.importorskip("torch")
    path = tmp_path / "with_presto.duckdb"
    assert build_database.main(["--db", str(path), "--imagery-dir", str(imagery_dir(tmp_path)),
                                "--mosaiks-dir", str(mosaiks_dir(tmp_path))]) == 0
    with duckdb.connect(str(path), read_only=True) as con:
        embeddings = con.sql("SELECT obs_id, len(embedding), embedding FROM presto_embeddings").fetchall()
        assert len(embeddings) == 1 and embeddings[0][:2] == (OBS_ID, 128) and np.isfinite(embeddings[0][2]).all()
        assert con.sql("SELECT presto_embedding[1] IS NOT NULL, len(presto_embedding) FROM master WHERE obs_id = ?",
                       params=[OBS_ID]).fetchone() == (True, 128)
        rows = con.sql("SELECT presto_embedding FROM master WHERE has_imagery AND presto_embedding IS NOT NULL").df()
        X = wide(rows, "presto_embedding", "presto")
        assert X.shape == (1, 128) and list(X.columns[[0, -1]]) == ["presto_000", "presto_127"]
