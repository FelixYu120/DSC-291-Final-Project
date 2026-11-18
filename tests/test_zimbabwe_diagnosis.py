"""Meaningful transfer controls: training-only transforms, matched subsets and weighted calibration."""
import json

import numpy as np
import pandas as pd
import pytest

from cropyield.experiments.zimbabwe_diagnosis import (
    CONFIG,
    TrainingTransform,
    choose_target_groups,
    make_context,
    predict,
    run_target_models,
    source_mask,
)
from cropyield.experiments.zimbabwe_merge import predict_model


@pytest.fixture
def config():
    return json.loads(CONFIG.read_text())


def test_missing_and_extreme_queries_cannot_change_training_transform():
    x = np.array([[1., np.nan, 2.], [3., np.nan, 4.], [5., np.nan, np.nan]])
    transformer = TrainingTransform().fit(x)
    before = transformer.transform(x)
    query = transformer.transform([[np.nan, 1e20, -1e20]])
    assert np.isfinite(query).all()
    assert query[0, 0] == pytest.approx(0.)
    assert query[0, 1] == 0.
    np.testing.assert_array_equal(before, transformer.transform(x))


def test_matched_subsets_preserve_quality_subset_size_and_zero_composition():
    source = pd.DataFrame({"yield_t_ha": [0., 0., 0., 0., 1., 2., 3., 4., 5., 6.],
                           "quality_subset": [True, False, True, False, False, True, True, True, False, False]})
    clean = source[source_mask(source, "quality", 0)]
    for seed in [606, 707, 808]:
        random = source[source_mask(source, "matched", seed)]
        assert len(random) == len(clean) == 5
        assert random.yield_t_ha.eq(0).sum() == clean.yield_t_ha.eq(0).sum() == 2


def test_learning_curve_subsamples_complete_groups_without_using_yields():
    frame = pd.DataFrame({"group_id": ["a", "a", "b", "b", "c", "c", "d", "d"], "yield_t_ha": range(8)})
    selected = choose_target_groups(frame.index.tolist(), frame, .5, 123)
    altered = frame.assign(yield_t_ha=np.arange(8)*100000)
    assert selected == choose_target_groups(frame.index.tolist(), altered, .5, 123)
    assert frame.loc[selected].group_id.value_counts().eq(2).all()
    assert len(selected) == 4


@pytest.fixture
def synthetic():
    rng = np.random.default_rng(876)
    x = rng.normal(size=(90, 10))
    metadata = pd.DataFrame({"yield_t_ha": 2+x[:, 0]*.2, "group_id": np.arange(90).astype(str),
                             "quality_subset": np.arange(90)%2 == 0})
    return metadata, {"seasonal": pd.DataFrame(x)}


def test_density_weights_use_features_not_query_or_source_outcomes(synthetic, config):
    rows, x = synthetic
    spec = {"kind": "adaptive", "family": "seasonal", "policy": "relevance"}
    original = make_context(rows, x, list(range(30)), list(range(30, 80)), list(range(80, 90)), spec, config)
    changed = rows.copy()
    changed.loc[30:, "yield_t_ha"] = 1e12
    corrupted = make_context(changed, x, list(range(30)), list(range(30, 80)), list(range(80, 90)), spec, config)
    for key in ["xt", "xs", "xq", "yt", "weights"]:
        np.testing.assert_array_equal(original[key], corrupted[key])
    assert original["weights"].min() >= .05 and original["weights"].max() <= 20


def test_shuffle_changes_source_pairings_only_and_is_reproducible(synthetic, config):
    rows, x = synthetic
    spec = {"kind": "adaptive", "family": "seasonal", "policy": "shuffle", "policy_seed": 101}
    args = (rows, x, list(range(30)), list(range(30, 80)), list(range(80, 90)))
    shuffled = make_context(*args, spec, config)
    repeated = make_context(*args, spec, config)
    true = make_context(*args, {**spec, "policy": "all"}, config)
    np.testing.assert_array_equal(np.sort(shuffled["ys"]), np.sort(true["ys"]))
    assert not np.array_equal(shuffled["ys"], true["ys"])
    for key in ["xt", "xs", "xq", "yt"]:
        np.testing.assert_array_equal(shuffled[key], true[key])
    np.testing.assert_array_equal(shuffled["ys"], repeated["ys"])


def test_weighted_adaptation_invariant_to_source_units_and_weight_scale(synthetic, config):
    rows, x = synthetic
    data = make_context(rows, x, list(range(30)), list(range(30, 80)), list(range(80, 90)),
                        {"kind": "adaptive", "family": "seasonal", "policy": "relevance"}, config)
    params = {"alpha": 10., "ratio": .3}
    original = predict(data, "adaptive", params, config)
    shifted = {**data, "ys": data["ys"]*1000+10, "weights": data["weights"]*50}
    np.testing.assert_allclose(original, predict(shifted, "adaptive", params, config), atol=1e-11)
    baseline = predict(data, "ridge", {"alpha": 10., "ratio": 0}, config)
    np.testing.assert_array_equal(baseline, predict(shifted, "adaptive", {"alpha": 10., "ratio": 0}, config))


def test_new_unweighted_adaptation_reproduces_previous_model(synthetic, config):
    rows, x = synthetic
    data = make_context(rows, x, list(range(30)), list(range(30, 80)), list(range(80, 90)),
                        {"kind": "adaptive", "family": "seasonal"}, config)
    new = predict(data, "adaptive", {"alpha": 10., "ratio": .3}, config)
    old = predict_model(data, "pooled_adaptive", {"alpha": 10., "source_ratio": .3},
                        {**config, "zero_sensitivity_weight": .25})
    np.testing.assert_allclose(new, old, atol=1e-12)


V2 = CONFIG.parent / "zimbabwe_transfer_diagnosis_v2.json"


def test_v2_diagnosis_reads_the_v2_merge_and_keeps_every_other_setting(config):
    v2 = json.loads(V2.read_text())
    assert v2["training_rows"] == "include_primary" and v2["merge_run"] == "data/runs/zimbabwe_merge_v2"
    changed = {"experiment", "training_rows", "merge_run"}
    assert {k: v for k, v in v2.items() if k not in changed} == {k: v for k, v in config.items() if k not in changed}


def test_v2_fit_pool_rejects_a_source_row_outside_include_primary():
    rows = pd.DataFrame({"fold": [1, 1, 2, 2, -1], "group_id": ["a", "a", "b", "b", "auxiliary"],
                         "yield_t_ha": [1., 2., 3., 4., 5.], "domain": ["lacuna"] * 4 + ["zimbabwe_2024"],
                         "include_primary": [True, True, True, True, False]},
                        index=["t1", "t2", "t3", "t4", "s1"])
    membership = pd.DataFrame({"obs_id": ["t3", "t4", "t1", "t2"], "outer_fold": 1, "inner_fold": 0,
                               "role": ["fit", "fit", "evaluation", "evaluation"]})
    permission = pd.DataFrame({"obs_id": ["s1"], "outer_fold": [1], "inner_fold": [0],
                               "minimum_distance_to_protected_km": [5.], "allowed_by_spatial_rule": [True]})
    with pytest.raises(ValueError, match="include_primary"):
        run_target_models(rows, {}, membership, permission, json.loads(V2.read_text()))


def test_matched_subsets_still_work_when_the_source_has_no_zeros():
    source = pd.DataFrame({"yield_t_ha": [1., 2., 3., 4., 5., 6.],
                           "quality_subset": [True, False, True, False, True, False]})
    for seed in [606, 707, 808]:
        random = source[source_mask(source, "matched", seed)]
        assert len(random) == 3 and random.yield_t_ha.gt(0).all()
