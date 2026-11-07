"""A compact weather calculation must respect season alignment and weighted units."""
import numpy as np
import pandas as pd
import pytest

from cropyield.experiments.zimbabwe_weather_compact import early_weather, select_inner


def sample():
    return pd.DataFrame({"weather_grid_id":["cell"]*3,"season_year":[2024]*3,"year":[2023]*3,
                         "calendar_month":[10,11,12],"days_in_month":[31,30,31],
                         "rain_total_mm":[20.,60.,100.],"rain_expected_current_days_mm":[40.,50.,60.],
                         "t2m_anomaly_c":[1.,2.,3.]})


def test_compact_rain_uses_ratio_of_sums_and_temperature_is_day_weighted():
    x = sample()
    result = early_weather(x).iloc[0]
    assert result.wx_rain_percent_normal_oct_dec==pytest.approx(120)
    assert result.wx_rain_percent_normal_oct_dec!=pytest.approx(np.mean(100*x.rain_total_mm/x.rain_expected_current_days_mm))
    x.loc[0,"t2m_anomaly_c"] = 4
    assert early_weather(x).iloc[0].wx_t2m_anomaly_c_oct_dec==pytest.approx((4*31+2*30+3*31)/92)


@pytest.mark.parametrize("error",["wrong_year","missing_month","duplicate"])
def test_invalid_season_cannot_silently_produce_features(error):
    x = sample()
    if error=="wrong_year":
        x.loc[0,"year"] = 2024
    elif error=="missing_month":
        x = x.iloc[:2]
    else:
        x = pd.concat([x,x.iloc[:1]])
    with pytest.raises(ValueError):
        early_weather(x)


def test_yield_columns_cannot_affect_compact_features():
    x = sample()
    before = early_weather(x.assign(yield_t_ha=[0,1,100]))
    after = early_weather(x.assign(yield_t_ha=[-999,999,0]))
    pd.testing.assert_frame_equal(before,after)


def test_inner_selection_ignores_any_outer_score_metadata():
    trials = [(2.,{"ratio":0,"outer_error":0}), (1.,{"ratio":.1,"outer_error":100})]
    assert select_inner(trials)[1]["ratio"]==.1
    assert select_inner([(1.,{"ratio":0}),(1.,{"ratio":1})])[1]["ratio"]==0
