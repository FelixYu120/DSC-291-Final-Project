"""Safety of transfer: units, label missingness, spatial barriers and training-only calibration."""
import json

import numpy as np
import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.xy import FEATURES
from cropyield.experiments.zimbabwe_merge import (
    CONFIG,
    ZERO_POLICY_METHODS,
    audit_2024,
    predict_model,
    prepare_training,
    purge_source,
    require_training_rows,
    run_experiment,
    run_folds,
    training_rows,
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


V2 = ROOT / "configs/zimbabwe_merge_v2.json"


def test_v2_config_changes_only_the_training_rows_and_the_identical_arms(config):
    v2 = json.loads(V2.read_text())
    assert training_rows(config) == "all_screened" and training_rows(v2) == "include_primary"
    assert not set(v2["methods"]) & set(ZERO_POLICY_METHODS)
    assert set(v2["dropped_from_v1"]) == set(ZERO_POLICY_METHODS)
    assert v2["methods"] == [m for m in config["methods"] if m not in ZERO_POLICY_METHODS]
    changed = {"experiment", "training_rows", "methods", "dropped_from_v1", "zero_sensitivity_weight"}
    assert {k: v for k, v in v2.items() if k not in changed} == {k: v for k, v in config.items() if k not in changed}


def test_v2_training_pool_rejects_a_row_outside_include_primary():
    combined = pd.DataFrame({"domain": ["lacuna", "zimbabwe_2024"], "feature_eligible": [True, True],
                             "fold": [1, -1], "include_primary": [True, False]})
    v2 = json.loads(V2.read_text())
    with pytest.raises(ValueError, match="include_primary"):
        run_folds(combined, v2)
    with pytest.raises(ValueError, match="include_primary"):
        require_training_rows(combined.drop(columns="include_primary"), v2)
    require_training_rows(combined, {})  # the v1 legacy pool keeps its old behaviour


def test_v2_refuses_zero_policy_arms_that_would_duplicate_the_primary(tmp_path):
    v2 = json.loads(V2.read_text())
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**v2, "methods": [*v2["methods"], "pooled_positive_sensitivity"]}))
    with pytest.raises(ValueError, match="Zero-policy"):
        run_experiment(tmp_path / "out", path)
    path.write_text(json.dumps({**v2, "training_rows": "everything"}))
    with pytest.raises(ValueError, match="Unknown training_rows"):
        run_experiment(tmp_path / "out", path)


V2_RUNS = ["data/runs/zimbabwe_merge_v2", "data/runs/zimbabwe_transfer_diagnosis_v2",
           "data/runs/zimbabwe_weather_v2", "data/runs/zimbabwe_weather_compact_v2"]


@pytest.mark.parametrize("name", V2_RUNS)
def test_saved_v2_training_pools_hold_only_include_primary_rows(name):
    run = ROOT / name
    if not (run / "manifest.json").is_file():
        pytest.skip(f"{name} is not built on this copy (data/runs is git-ignored)")
    assert training_rows(json.loads((run / "manifest.json").read_text())["config"]) == "include_primary"
    labels = pd.read_parquet(ROOT / "data/processed/labels_v1.parquet").set_index("obs_id")
    permission = pd.read_csv(run / "source_spatial_permissions.csv")
    membership = pd.read_csv(run / "target_memberships.csv")
    pool = set(permission.loc[permission.allowed_by_spatial_rule, "obs_id"]) | set(membership.loc[membership.role.eq("fit"), "obs_id"])
    assert len(pool) > 3000 and labels.loc[sorted(pool), "include_primary"].all()
    assert labels.loc[sorted(set(permission.obs_id) | set(membership.obs_id)), "include_primary"].all()
    # Nothing else is withheld: every include_primary 2024 row with imagery features is a source candidate.
    eligible = pd.read_parquet(ROOT / "data/runs/zimbabwe_merge_v2/combined_data.parquet").query("feature_eligible")
    primary_2024 = labels.index[labels.cohort.eq("zimbabwe_2024") & labels.include_primary]
    assert set(permission.obs_id) == set(primary_2024) & set(eligible.obs_id)
