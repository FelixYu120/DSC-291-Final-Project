"""Kenya date cleanup is conservative and repeated points remain separate records."""
from datetime import datetime

import pandas as pd
import pytest

from cropyield.data.kenya_review import (
    coordinate_review,
    date_proposal,
    review_dates,
    unambiguous_date,
)


@pytest.mark.parametrize("value", ["04/03/2019", 43527, "2019-02-30"])
def test_ambiguous_or_invalid_source_dates_are_not_guessed(value):
    parsed, evidence = unambiguous_date(value)
    assert pd.isna(parsed)
    assert evidence == "unresolved_source_format"


def test_typed_excel_and_iso_dates_are_safe():
    assert unambiguous_date(datetime(2019, 3, 4))[0] == pd.Timestamp("2019-03-04")
    assert unambiguous_date("2019-03-04T00:00:00")[0] == pd.Timestamp("2019-03-04")


def test_invalid_plant_year_does_not_destroy_valid_harvest():
    plant, harvest, reason = date_proposal("2100-04-30", "2019-08-01", 2019)
    assert pd.isna(plant)
    assert harvest == pd.Timestamp("2019-08-01")
    assert reason == "quarantine_plant_year_outside_season_range"


def test_reversed_plausible_dates_quarantine_both_without_guessing():
    plant, harvest, reason = date_proposal("2020-06-25", "2020-06-23", 2020)
    assert pd.isna(plant) and pd.isna(harvest)
    assert reason == "quarantine_both_ambiguous_date_order"


def test_missing_date_and_valid_late_harvest_are_retained():
    plant, harvest, reason = date_proposal(pd.NaT, "2019-12-15", 2019)
    assert pd.isna(plant)
    assert harvest == pd.Timestamp("2019-12-15")
    assert reason == "retain_source_dates"


def test_review_dates_preserves_inputs_and_recovers_only_source_evidenced_date():
    rows = pd.DataFrame({"obs_id": ["k1"], "season_year": [2019],
                         "plant_date": [pd.NaT], "harvest_date": [pd.Timestamp("2019-08-01")],
                         "raw_plant_date_parsed": [pd.Timestamp("2019-03-01")],
                         "raw_harvest_date_parsed": [pd.Timestamp("2019-08-01")],
                         "season_start": [pd.Timestamp("2019-02-01")], "season_end": [pd.Timestamp("2019-09-30")]})
    original = rows.copy(deep=True)
    reviewed = review_dates(rows)
    pd.testing.assert_frame_equal(rows, original)
    assert reviewed.date_recovered_from_source.iloc[0] == "plant_date"
    assert reviewed.proposed_plant_date.iloc[0] == pd.Timestamp("2019-03-01")
    assert pd.isna(reviewed.plant_date.iloc[0])


def test_coordinate_repeats_do_not_drop_distinct_yields_or_cross_years():
    rows = pd.DataFrame({"obs_id": ["k1", "k2", "k3"], "source_id": ["1", "2", "3"],
                         "lat": [0., 0., 0.00005], "lon": [34., 34., 34.], "season_year": [2019, 2019, 2020],
                         "raw_district": ["a"] * 3, "raw_site": ["site"] * 3, "raw_plot_acres": [1., 2., 3.],
                         "yield_kg_ha": [1000., 2000., 3000.], "raw_row_sha256": ["a", "b", "c"],
                         "raw_payload_sha256_excluding_unique_id": ["a", "b", "c"],
                         "group_id": ["g"] * 3, "fold": ["1"] * 3})
    original = rows.copy(deep=True)
    result, pairs = coordinate_review(rows)
    pd.testing.assert_frame_equal(rows, original)
    assert len(result) == 3 and result.coordinate_group_id.nunique() == 1
    assert len(pairs) == 3 and pairs.exact_coordinates.sum() == 1
    assert (~pairs.same_year).sum() == 2
    assert not pairs.same_source_id.any() and not pairs.same_yield.any()
    assert not pairs.identical_full_source_row.any()
    assert pairs.same_spatial_group.all()
