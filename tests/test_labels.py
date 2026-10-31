"""labels_v1: the checks catch what they promise, and the committed table passes them."""
import pandas as pd
import pytest

from cropyield.data.labels import EXPECTED_ROWS, LABELS_PATH, check_labels, exclusion_reasons, normal_district


@pytest.fixture(scope="module")
def labels() -> pd.DataFrame:
    if not LABELS_PATH.exists():
        pytest.skip("labels_v1 not built")
    return pd.read_parquet(LABELS_PATH)


def test_committed_table_passes_every_check(labels):
    assert check_labels(labels) == []


def test_primary_rows_per_cohort(labels):
    primary = labels[labels["include_primary"]].groupby(["cohort", "season_year"]).size().to_dict()
    assert primary == {("malawi_2023", 2023): 260, ("kenya_oaf_2019_2020", 2019): 1768,
                       ("kenya_oaf_2019_2020", 2020): 2209, ("zimbabwe_lacuna_2022_2023", 2023): 1880,
                       ("zimbabwe_2024", 2024): 2458}
    assert sum(EXPECTED_ROWS.values()) == len(labels)


def test_grouping_columns_came_back(labels):
    kenya = labels[labels["cohort"] == "kenya_oaf_2019_2020"]
    assert kenya["admin_unit"].nunique() == 50 and (kenya["admin_unit"] != "").all()
    assert kenya["site_unit"].nunique() > 1000
    lacuna = labels[(labels["cohort"] == "zimbabwe_lacuna_2022_2023") & labels["include_primary"]]
    assert lacuna["admin_unit"].nunique() == 20


def test_every_excluded_row_says_why(labels):
    assert (labels["exclusion_reason"] != "").equals(~labels["include_primary"])


def test_malawi_target_is_the_main_cut_and_the_nested_cut_stays_a_column(labels):
    malawi = labels[labels["cohort"] == "malawi_2023"]
    assert (malawi["yield_kg_ha"] == malawi["cut1_kg_ha"]).all()
    assert malawi["cut2_kg_ha"].notna().all()
    assert malawi["obs_id"].is_unique


def test_check_labels_reports_a_duplicate_id(labels):
    broken = labels.copy()
    broken.loc[broken.index[1], "obs_id"] = broken["obs_id"].iloc[0]
    assert any("obs_id" in problem for problem in check_labels(broken))


def test_check_labels_reports_an_included_lacuna_intercrop_row(labels):
    broken = labels.copy()
    row = broken.index[(broken["cohort"] == "zimbabwe_lacuna_2022_2023") & broken["include_primary"]][0]
    broken.loc[row, "intercropped"] = True
    assert any("Lacuna" in problem for problem in check_labels(broken))


def test_check_labels_reports_an_included_zimbabwe_zero(labels):
    broken = labels.copy()
    row = broken.index[broken["exclusion_reason"] == "zimbabwe_2024_zero_likely_not_measured"][0]
    broken.loc[row, "include_primary"] = True
    assert any("Zimbabwe 2024" in problem for problem in check_labels(broken))


def test_check_labels_reports_a_lost_row(labels):
    assert any("row counts" in problem for problem in check_labels(labels.iloc[1:]))


def test_normal_district_merges_the_spellings_of_both_years():
    spellings = pd.Series(["kakamega(south)", "kakamegasouth", "Kakamegab(North)", "kakameganorth"])
    assert normal_district(spellings).tolist() == ["kakamegasouth", "kakamegasouth", "kakameganorth", "kakameganorth"]


def test_exclusion_reasons_first_rule_wins():
    frame = pd.DataFrame({
        "cohort": ["zimbabwe_lacuna_2022_2023", "zimbabwe_lacuna_2022_2023", "kenya_oaf_2019_2020"],
        "season_year": [2022, 2023, 2019], "intercropped": pd.array([True, True, False], dtype="boolean"),
        "irrigated": pd.array([False, False, pd.NA], dtype="boolean"), "is_zero": [False, False, True],
        "yield_kg_ha": [1000.0, 1000.0, 0.0]})
    assert exclusion_reasons(frame).tolist() == ["dropped_year_2022_imagery_gap", "lacuna_intercropped", ""]
