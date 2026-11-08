"""Weather unit, time alignment and source-validation safeguards."""
import calendar
import json

import numpy as np
import pandas as pd
import pytest

from cropyield.data.weather import (
    CONFIG,
    climate_normals,
    grid_mapping,
    parse_response,
    seasonal_weather,
)


@pytest.fixture
def config():
    return json.loads(CONFIG.read_text())


def payload(config):
    values = {"PRECTOTCORR": {}, "T2M": {}}
    for year in range(config["start_year"], config["end_year"]+1):
        for month in range(1,14):
            values["PRECTOTCORR"][f"{year}{month:02}"] = 2+(year-1991)*.01
            values["T2M"][f"{year}{month:02}"] = 20+(year-1991)*.01
    return {"type": "Feature", "header": {"sources": ["MERRA2"], "time_standard": "LST", "fill_value": -999},
            "parameters": {"PRECTOTCORR": {"units": "mm/day"}, "T2M": {"units": "C"}},
            "properties": {"parameter": values}}


def test_grid_match_and_half_cell_ties(config):
    labels = pd.DataFrame({"obs_id": ["a","b","c"], "lat": [-18.,-18.25,-18.25001],
                           "lon": [30.,30.3125,30.31249], "season_year": [2024]*3})
    mapped = grid_mapping(labels,config)
    assert mapped.weather_grid_lat.tolist() == [-18.,-18.,-18.5]
    assert mapped.weather_grid_lon.tolist() == [30.,30.625,30.]
    assert mapped.weather_grid_distance_km.iloc[0] == 0
    assert mapped.weather_grid_distance_km.between(0,45).all()


def test_rain_rate_to_monthly_amount_and_annual_record_exclusion(config):
    data = payload(config)
    data["properties"]["parameter"]["PRECTOTCORR"]["202402"] = 2
    data["properties"]["parameter"]["PRECTOTCORR"]["202302"] = 2
    # Annual API record is not another month, and must never enter the season.
    data["properties"]["parameter"]["PRECTOTCORR"]["202413"] = -999
    out = parse_response(json.dumps(data), "cell", config).set_index("month")
    assert len(out) == 34*12
    assert out.loc["2024-02", "rain_total_mm"] == 58
    assert out.loc["2023-02", "rain_total_mm"] == 56
    assert out.loc["2024-02", "t2m_c"] == pytest.approx(20.33)


@pytest.mark.parametrize("problem", ["fill", "unit", "month"])
def test_corrupt_source_fails_instead_of_silent_imputation(config, problem):
    data = payload(config)
    if problem == "fill":
        data["properties"]["parameter"]["T2M"]["202402"] = -999
    elif problem == "unit":
        data["parameters"]["PRECTOTCORR"]["units"] = "mm/month"
    else:
        del data["properties"]["parameter"]["T2M"]["202402"]
    with pytest.raises(ValueError):
        parse_response(json.dumps(data),"cell",config)


def test_baseline_excludes_recent_weather_and_season_crosses_calendar_year(config):
    history = parse_response(json.dumps(payload(config)),"cell",config)
    normal = climate_normals(history,config)
    changed = history.copy()
    changed.loc[changed.year.gt(2020), "t2m_c"] += 20
    pd.testing.assert_frame_equal(normal,climate_normals(changed,config))
    season,wide,features = seasonal_weather(history,normal,config)
    selected = season[season.season_year.eq(2024)]
    assert selected.month.tolist() == ["2023-10","2023-11","2023-12","2024-01","2024-02","2024-03","2024-04","2024-05","2024-06"]
    assert len(features) == 46 and len(wide) == 3
    assert selected.days_in_month.sum() == sum(calendar.monthrange(2023 if m>=10 else 2024,m)[1] for m in config["weather_months"])
    assert np.isfinite(wide[features]).all().all()
    with pytest.raises(ValueError,match="Duplicate"):
        climate_normals(pd.concat([history,history.iloc[:1]]),config)


def test_zero_historical_variance_is_not_silently_divided(config):
    history = parse_response(json.dumps(payload(config)),"cell",config)
    normal = climate_normals(history,config)
    normal["rain_normal_sd_mm"] = 0.
    with pytest.raises(ValueError,match="Undefined rainfall"):
        seasonal_weather(history,normal,config)
