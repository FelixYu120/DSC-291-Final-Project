"""scripts/check_data.py on a tiny database: it reads the model rows and counts what it promises."""
import importlib.util
from pathlib import Path

import duckdb
import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_data.py"
spec = importlib.util.spec_from_file_location("check_data", SCRIPT)
check_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_data)


@pytest.fixture
def con(tmp_path):
    labels = pd.DataFrame({"obs_id": ["a", "b", "c", "left_out"], "cohort": "kenya", "season_year": 2020,
                           "yield_kg_ha": [1000.0, 2000.0, 3000.0, 9000.0], "include_primary": [True, True, True, False]})
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path)
    connection = duckdb.connect()
    features = pd.DataFrame({"obs_id": ["a", "b", "left_out"], "has_imagery": True, "download_status": "complete",
                             "months_with_data": [5, 2, 5], **{name: [0.1, 0.2, 0.9] for name in check_data.SEASON_FEATURES}})
    connection.register("features", features)
    connection.execute("CREATE TABLE master AS SELECT * FROM features")
    connection.execute("""CREATE TABLE coverage AS SELECT * FROM (VALUES ('a', '2020-03', 'clear'), ('a', '2020-04', 'cloudy'),
                          ('b', '2020-03', 'no_scene'), ('left_out', '2020-03', 'clear')) t(obs_id, month, state)""")
    connection.execute("""CREATE TABLE monthly_bands AS SELECT * FROM (VALUES ('a', 0.05, FALSE), ('a', 0.30, FALSE), ('b', 0.05, TRUE))
                          t(obs_id, b02, missing)""")
    connection.execute("""CREATE TABLE vegetation_indices AS SELECT * FROM (VALUES ('a', '2020-03', 0.3), ('a', '2020-04', 0.7),
                          ('b', '2020-03', 0.6), ('b', '2020-04', NULL)) t(obs_id, month, ndvi)""")
    connection.execute(check_data.MODEL_ROWS.format(labels=path.as_posix()))
    yield connection
    connection.close()


def test_coverage_counts_primary_rows_only_and_a_row_without_a_chip(con):
    row = check_data.coverage_table(con, 4).iloc[0]
    assert (row["primary_rows"], row["with_chip"], row["usable"]) == (3, 2, 1)


def test_clear_share_is_per_month_of_the_model_rows(con):
    table = check_data.clear_share_by_month(con).set_index("month")
    assert table.loc["2020-03", "clear"] == 0.5 and table.loc["2020-03", "no_scene"] == 0.5
    assert table.loc["2020-04", "clear"] == 0


def test_haze_counts_clear_months_with_a_high_blue_value(con):
    row = check_data.haze(con).iloc[0]
    assert (row["clear_months"], row["share_blue_high"]) == (2, 0.5)


def test_greenest_month_skips_a_month_without_a_value(con):
    table = check_data.greenest_month(con).set_index("month")
    assert table["fields"].to_dict() == {"2020-03": 1, "2020-04": 1}
