"""Safety of transfer: units, label missingness, spatial barriers and training-only calibration."""
import json

import numpy as np
import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.xy import FEATURES
from cropyield.experiments.zimbabwe_merge import (
    CONFIG,
    audit_2024,
    predict_model,
    prepare_training,
    purge_source,
    run_folds,
)


@pytest.fixture(scope="module")
def config():
    return json.loads(CONFIG.read_text())


def test_provider_missing_labels_are_distinct_from_recorded_zeros_and_single_boxes():
    rows = audit_2024(ROOT / "data/raw/vision_guided_yield_estimation/metadata.csv")
    assert len(rows) == 5055
    assert rows.yield_t_ha.isna().sum() == 723
    valid = rows[rows.label_eligible]
    assert len(valid) == 4332
    assert valid.yield_t_ha.eq(0).sum() == 1874
    single = valid[valid.n_cuts_observed.eq(1)]
    assert len(single) == 42
    np.testing.assert_allclose(single.yield_t_ha, single.recomputed_yield_t_ha)
    assert single[["box1_yield_t_ha", "box2_yield_t_ha"]].isna().sum(axis=1).eq(1).all()


def test_raw_measurement_corruption_rejected_without_converting_missing_box_to_zero(tmp_path):
    frame = pd.DataFrame({"cce_id": ["ok", "wrong_mean", "wrong_unit", "missing"],
                          "country": "Zimbabwe", "crop": "Maize/Corn", "data_collection_year": 2024,
                          "latitude": -18., "longitude": 30., "Box used": "only box1 used",
                          "Avg_yield_mt_ha": [2., 1., 4., np.nan],
                          "box1_dry_weight_confirmation": [8., 8., 8., np.nan],
                          "box1_wet_weight_confirmation": [9., 9., 9., np.nan],
                          "box1_into_mt_ha": [2., 2., 4., np.nan],
                          "box2_dry_weight_confirmation": np.nan,
                          "box2_wet_weight_confirmation": np.nan, "box2_into_mt_ha": np.nan})
    frame.to_csv(tmp_path / "source.csv", index=False)
    audit = audit_2024(tmp_path / "source.csv").set_index("source_id")
    assert audit.loc["ok", "label_eligible"]
    assert audit.loc["ok", "recomputed_yield_t_ha"] == 2.
    assert "average_mismatch" in audit.loc["wrong_mean", "exclusion_reason"]
    assert "conversion_mismatch" in audit.loc["wrong_unit", "exclusion_reason"]
    assert audit.loc["missing", "outcome_status"] == "missing"
    assert not audit.loc[["wrong_mean", "wrong_unit", "missing"], "label_eligible"].any()


def test_geographic_buffer_covers_every_protected_field():
    source = pd.DataFrame({"lat": [0., 0., 0.], "lon": [.001, 1.001, 2.]}, index=[11, 22, 33])
    protected = pd.DataFrame({"lat": [0., 0.], "lon": [0., 1.]})
    allowed, distances = purge_source(source, protected, 2.)
    assert allowed.index.tolist() == [33]
    np.testing.assert_allclose(distances[:2], [.1112, .1112], atol=.0001)
    assert 111 < distances[2] < 112


@pytest.fixture
def synthetic_data():
    rng = np.random.default_rng(123)
    xt, xs, xq = rng.normal(size=(30, 10)), rng.normal(size=(40, 10)), rng.normal(size=(8, 10))
    yt = 4 + xt[:, 0] * .5
    ys = 2 + xs[:, 0] * .2
    return {"xt": xt, "xs": xs, "xq": xq, "yt": yt, "ys": ys}


def test_adaptive_transfer_invariant_to_positive_affine_source_unit_change(synthetic_data, config):
    params = {"alpha": 10., "source_ratio": .3}
    original = predict_model(synthetic_data, "pooled_adaptive", params, config)
    converted = {**synthetic_data, "ys": synthetic_data["ys"] * 1000 + 42}
    np.testing.assert_allclose(original, predict_model(converted, "pooled_adaptive", params, config), atol=1e-12)


def test_validation_can_reject_transfer_exactly_and_source_labels_cannot_affect_zero_weight(synthetic_data, config):
    params = {"alpha": 10., "source_ratio": 0.}
    reference = predict_model(synthetic_data, "lacuna_only", params, config)
    changed = {**synthetic_data, "ys": np.full(40, 1e9), "xs": np.full((40, 10), -1e9)}
    for method in ["pooled_adaptive", "pooled_positive_sensitivity", "pooled_zero_weight_sensitivity"]:
        np.testing.assert_array_equal(reference, predict_model(changed, method, params, config))


def test_query_outcomes_never_enter_preprocessing_or_calibration(synthetic_data, config):
    target = pd.DataFrame(synthetic_data["xt"], columns=FEATURES).assign(yield_t_ha=synthetic_data["yt"])
    source = pd.DataFrame(synthetic_data["xs"], columns=FEATURES).assign(yield_t_ha=synthetic_data["ys"])
    query = pd.DataFrame(synthetic_data["xq"], columns=FEATURES).assign(yield_t_ha=0.)
    original = prepare_training(target, source, query)
    query["yield_t_ha"] = 1e12
    poisoned = prepare_training(target, source, query)
    for name in original:
        np.testing.assert_array_equal(original[name], poisoned[name])
    # Extreme auxiliary features also cannot change the target scaler.
    source.loc[:, FEATURES] = 1e20
    changed = prepare_training(target, source, query)
    np.testing.assert_array_equal(original["xt"], changed["xt"])
    np.testing.assert_array_equal(original["xq"], changed["xq"])


def test_fold_zero_cannot_be_opted_into_comparison(config):
    combined = pd.DataFrame({"domain": ["lacuna"], "feature_eligible": [True], "fold": [0]})
    with pytest.raises(ValueError, match="Fold 0"):
        run_folds(combined, {**config, "target_folds": [0, 1, 2, 3, 4]})
