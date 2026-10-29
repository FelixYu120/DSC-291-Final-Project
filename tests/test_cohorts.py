from datetime import date

import pandas as pd

from cropyield import ROOT
from cropyield.data.cohorts import COHORTS, date_overrides, load_cohort, obs_id, season_window
from cropyield.satellite.chips import read_chip


def test_malawi_2023_cohort_keeps_source_rows_with_stable_ids():
    cohort = load_cohort("malawi_2023")
    assert len(cohort) == 260  # README: 260 screened Malawi 2023 candidates
    assert cohort.columns[0] == "obs_id" and cohort["obs_id"].is_unique
    first = cohort.iloc[0]
    assert first["obs_id"] == obs_id("malawi_2023", first["source_id"]) == "malawi_2023:" + first["source_id"]
    assert first["source_row"] == 1 and cohort["source_row"].dtype.kind == "i"
    assert {"source_yield", "observation_time", "quality_flags"} <= set(cohort.columns)  # source columns kept
    assert (first["season_start"], first["season_end"]) == ("2022-10-01", "2023-06-30")


def test_kenya_pure_stand_filter_matches_decision_log():
    assert len(load_cohort("kenya_oaf_2019_2020")) == 3977  # DECISIONS.md 2026-10-26


def test_season_windows_are_fixed_per_zone():
    assert season_window(COHORTS["kenya_oaf_2019_2020"], 2020) == (date(2020, 2, 1), date(2020, 9, 30))
    assert season_window(COHORTS["zimbabwe_2024"], 2024) == (date(2023, 10, 1), date(2024, 6, 30))


def test_pilot_date_overrides_file_is_the_first_ten_cohort_rows():
    expected = date_overrides(load_cohort("malawi_2023").head(10))
    committed = pd.read_csv(ROOT / "configs" / "sentinel2_windows_malawi_2023_pilot.csv", dtype=str)
    pd.testing.assert_frame_equal(committed, expected)


def test_chip_obs_id_joins_the_cohort_row(chip_dir):
    chip = read_chip(chip_dir)
    cohort = load_cohort("malawi_2023").set_index("obs_id")
    assert chip.obs_id in cohort.index
    row = cohort.loc[chip.obs_id]
    assert (row["source_row"], row["source_id"]) == (chip.source_row, chip.source_id)
    assert row["yield_kg_ha"] == chip.yield_kg_ha == 2950.0
