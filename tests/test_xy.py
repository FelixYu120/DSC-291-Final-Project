"""cropyield.data.xy.load_xy: rows, columns, unit and errors, on a small database built from sql/."""
import duckdb
import pytest

from cropyield import ROOT
from cropyield.data import xy
from cropyield.data.xy import FEATURES, load_xy

COHORT = "malawi_2023"


def add_field(con, name, months, primary=True, kg_ha=2500.0, chip=True, cohort=COHORT):
    obs_id = f"d:{name}"
    con.execute("""INSERT INTO labels (obs_id, cohort, dataset, source_id, source_row, country, year, yield_kg_ha,
                                       latitude, longitude, season_start, season_end, include_primary, exclusion_reason)
                   VALUES (?, ?, 'd', ?, 1, 'malawi', 2023, ?, 0, 0, DATE '2022-10-01', DATE '2023-06-30', ?, '')""",
                [obs_id, cohort, name, kg_ha, primary])
    if chip:
        con.execute("""INSERT INTO downloads (obs_id, record_dir, status, aoi_type, aoi_pixels, field_pixels,
                                              aoi_inside_chip, accepted_months, crs)
                       VALUES (?, 'x', 'complete', 'point_pixel', 1, 1, TRUE, ?, 'EPSG:32736')""", [obs_id, months])
    for month in range(1, months + 1):
        con.execute("INSERT INTO monthly_bands (obs_id, month, b08, field_pixels, missing) VALUES (?, ?, 0.3, 1, FALSE)",
                    [obs_id, f"2023-{month:02d}"])
        con.execute("INSERT INTO vegetation_indices VALUES (?, ?, ?, 2.0, 3.0, 0.4, 0.2)",
                    [obs_id, f"2023-{month:02d}", 0.1 * month])


@pytest.fixture
def data_dir(tmp_path):
    with duckdb.connect(str(tmp_path / "cropyield.duckdb")) as con:
        con.execute((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        con.execute((ROOT / "sql" / "views.sql").read_text(encoding="utf-8"))
        add_field(con, "b_four_months", 4, kg_ha=2500.0)
        add_field(con, "a_five_months", 5, kg_ha=1000.0)
        add_field(con, "c_three_months", 3)
        add_field(con, "d_not_primary", 6, primary=False)
        add_field(con, "e_other_cohort", 6, cohort="kenya_oaf_2019_2020")
        add_field(con, "f_dropped_cohort", 6, primary=False, cohort="malawi_2022")
    return tmp_path


def test_x_and_y_follow_the_interface(data_dir):
    X, y = load_xy(COHORT, data_dir)
    assert list(X.columns) == FEATURES and len(FEATURES) == 10
    assert X.index.name == "obs_id" and list(X.index) == list(y.index)
    assert y.name == "yield_t_ha"
    assert (X.dtypes == "float64").all() and y.dtype == "float64"


def test_rows_need_include_primary_and_four_clear_months_and_come_in_obs_id_order(data_dir):
    X, _ = load_xy(COHORT, data_dir)
    assert list(X.index) == ["d:a_five_months", "d:b_four_months"]


def test_y_is_in_tonnes_per_hectare(data_dir):
    _, y = load_xy(COHORT, data_dir)
    assert y["d:b_four_months"] == pytest.approx(2.5)
    assert y["d:a_five_months"] == pytest.approx(1.0)


def test_x_holds_the_season_values_of_the_view(data_dir):
    X, _ = load_xy(COHORT, data_dir)
    assert X.loc["d:a_five_months", "ndvi_season_max"] == pytest.approx(0.5)
    assert X.loc["d:a_five_months", "ndvi_season_mean"] == pytest.approx(0.3)


def test_data_dir_comes_from_the_argument_then_the_variable_then_the_repository(data_dir, tmp_path_factory, monkeypatch):
    empty = tmp_path_factory.mktemp("no_database")
    monkeypatch.setenv("CROPYIELD_DATA_DIR", str(empty))
    assert len(load_xy(COHORT, data_dir)[0]) == 2
    with pytest.raises(FileNotFoundError):
        load_xy(COHORT)
    monkeypatch.setenv("CROPYIELD_DATA_DIR", str(data_dir))
    assert len(load_xy(COHORT)[0]) == 2
    monkeypatch.delenv("CROPYIELD_DATA_DIR")
    monkeypatch.setattr(xy, "ROOT", data_dir.parent)
    (data_dir.parent / "data").mkdir()
    (data_dir / "cropyield.duckdb").replace(data_dir.parent / "data" / "cropyield.duckdb")
    assert len(load_xy(COHORT)[0]) == 2


def test_an_unknown_cohort_names_the_valid_ones(data_dir):
    with pytest.raises(ValueError, match="kenya_oaf_2019_2020"):
        load_xy("kenya", data_dir)


def test_a_cohort_with_no_model_rows_is_an_error_not_empty_data(data_dir):
    with pytest.raises(ValueError, match="include_primary"):
        load_xy("malawi_2022", data_dir)


def test_no_database_explains_how_to_get_the_shared_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="download the shared team cropyield.duckdb"):
        load_xy(COHORT, tmp_path / "nowhere")


def test_a_partial_copy_warns_and_returns_its_rows(data_dir):
    with duckdb.connect(str(data_dir / "cropyield.duckdb")) as con:
        add_field(con, "g_no_chip", 0, chip=False)
    with pytest.warns(UserWarning, match="1 of 4 include_primary rows have no chip"):
        X, _ = load_xy(COHORT, data_dir)
    assert len(X) == 2


def test_a_full_copy_does_not_warn(data_dir, recwarn):
    load_xy(COHORT, data_dir)
    assert not recwarn.list


def test_the_database_stays_as_it_was_and_is_free_after_the_call(data_dir):
    path = data_dir / "cropyield.duckdb"
    before = path.read_bytes()
    load_xy(COHORT, data_dir)
    assert path.read_bytes() == before
    path.unlink()  # Windows refuses this while a connection is open
