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
    release_paths,
    run_models,
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


def v2_synthetic():
    rows = pd.DataFrame({"fold": [1, 1, 2, 2, -1], "group_id": ["a", "a", "b", "b", "auxiliary"],
                         "yield_t_ha": [1., 2., 3., 4., 5.], "domain": ["lacuna"] * 4 + ["zimbabwe_2024"],
                         "feature_eligible": True, "weather_grid_id": "cell",
                         "include_primary": [True, True, True, True, False]},
                        index=["t1", "t2", "t3", "t4", "s1"])
    membership = pd.DataFrame({"obs_id": ["t3", "t4", "t1", "t2"], "outer_fold": 1, "inner_fold": 0,
                               "role": ["fit", "fit", "evaluation", "evaluation"]})
    permission = pd.DataFrame({"obs_id": ["s1"], "outer_fold": [1], "inner_fold": [0],
                               "minimum_distance_to_protected_km": [5.], "allowed_by_spatial_rule": [True]})
    return rows, membership, permission


def test_v2_weather_fit_pool_rejects_a_source_row_outside_include_primary():
    rows, membership, permission = v2_synthetic()
    config = json.loads((CONFIG.parent/"zimbabwe_weather_v2.json").read_text())
    with pytest.raises(ValueError, match="include_primary"):
        run_models(rows, {}, membership, permission, config)


def test_v2_weather_configs_read_only_v2_releases_and_keep_v1_settings():
    v1 = json.loads(CONFIG.read_text())
    v2 = json.loads((CONFIG.parent/"zimbabwe_weather_v2.json").read_text())
    assert release_paths() == release_paths(v1)  # absent keys keep the v1 releases
    assert all(path.name.endswith("_v2") for path in [*release_paths(v2).values()][:3])
    changed = {"experiment", "training_rows", "merge_run", "diagnosis_run", "weather_release"}
    assert v2["training_rows"] == "include_primary"
    assert {k: v for k, v in v2.items() if k not in changed} == {k: v for k, v in v1.items() if k not in changed}
    compact_v1 = json.loads((CONFIG.parent/"zimbabwe_weather_compact_v1.json").read_text())
    compact_v2 = json.loads((CONFIG.parent/"zimbabwe_weather_compact_v2.json").read_text())
    assert all(path.name.endswith("_v2") for path in release_paths(compact_v2).values())
    changed |= {"weather_run"}
    assert {k: v for k, v in compact_v2.items() if k not in changed} == {k: v for k, v in compact_v1.items() if k not in changed}
