"""Guard the new weather experiment against information loss and validation leakage."""
import json

import numpy as np
import pandas as pd
import pytest

from cropyield.experiments.zimbabwe_weather import (
    CONFIG,
    WeatherTransform,
    make_context,
    predict,
)


def test_real_weather_extremes_are_preserved_and_queries_do_not_refit_scaler():
    transform = WeatherTransform().fit([[10,20,np.nan],[20,20,np.nan],[30,20,np.nan]])
    before = transform.transform([[10,20,np.nan]])
    query = transform.transform([[100,25,np.nan]])
    assert query[0,0] == pytest.approx(80/np.std([10,20,30]))
    assert query[0,0] > 9
    assert query[0,1] == 5  # a constant training column must not erase future changes
    assert query[0,2] == 0
    np.testing.assert_array_equal(before,transform.transform([[10,20,np.nan]]))


def synthetic():
    rng = np.random.default_rng(151)
    x = pd.DataFrame(rng.normal(size=(80,3)),columns=["ndvi_month_01","wx_rain_z_m01","interaction_ndvi_rain_z_m01"])
    rows = pd.DataFrame({"yield_t_ha":3+x.iloc[:,0]*.5-x.iloc[:,1]*.1})
    return rows,x


def test_query_outcomes_do_not_influence_any_weather_model():
    config = json.loads(CONFIG.read_text())
    rows,x = synthetic()
    args = (x,list(range(30)),list(range(30,70)),list(range(70,80)))
    original = make_context(rows,*args)
    rows.loc[70:,'yield_t_ha'] = -1e20
    changed = make_context(rows,*args)
    for kind in ["ridge","adaptive","shared","tree"]:
        params = {"alpha":10,"leaves":7,"ratio":.3}
        np.testing.assert_array_equal(predict(original,kind,params,config),predict(changed,kind,params,config))


def test_zero_source_weight_recovers_target_only_and_weights_normalize_source_size():
    config = json.loads(CONFIG.read_text())
    rows,x = synthetic()
    data = make_context(rows,x,list(range(30)),list(range(30,70)),list(range(70,80)))
    corrupted = {**data,"ys":data["ys"]+1000}
    baseline = predict(data,"ridge",{"alpha":10,"ratio":0},config)
    for kind in ["adaptive","shared"]:
        np.testing.assert_array_equal(baseline,predict(corrupted,kind,{"alpha":10,"ratio":0},config))
    duplicated = {**data, **{key:np.concatenate([data[key],data[key]]) for key in ["xs","ys","weights"]}}
    np.testing.assert_allclose(predict(data,"shared",{"alpha":10,"ratio":.3},config),
                               predict(duplicated,"shared",{"alpha":10,"ratio":.3},config),atol=1e-12)
