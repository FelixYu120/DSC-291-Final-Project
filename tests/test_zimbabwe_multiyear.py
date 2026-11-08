"""Expanded training must preserve imagery, split and geographic eligibility rules."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cropyield.experiments.zimbabwe_merge import predict_model, purge_source
from cropyield.experiments.zimbabwe_multiyear import (
    build_eligibility,
    build_permissions,
    evaluate,
    make_context,
)


@pytest.fixture
def config():
    return {"minimum_clear_months": 4, "auxiliary_buffer_km": 2.,
            "reserved_fold": 0, "target_folds": [1],
            "zero_sensitivity_weight": .25}


def eligibility_inputs():
    ids = ["sparse_2022", "three_months", "four_months", "seven_months"]
    rows = pd.DataFrame({"season_year": [2022, 2024, 2023, 2023],
                         "domain": ["lacuna", "zimbabwe_2024", "lacuna", "lacuna"],
                         "yield_t_ha": [3., 0., 2., 1.]}, index=pd.Index(ids, name="obs_id"))
    audit = pd.DataFrame({"n_season": [2, 3, 4, 7], "n_preharvest": [1, 1, 1, 3],
                          "n_calendar": [1, 1, 2, 4]}, index=rows.index)
    variants = ["v0_mean", "v1_preharvest_mean", "v1_calendar_mean", "v2_max", "v3_median", "v3_mode"]
    names = [f"{family}_{variant}" for family in ["bands", "indices"] for variant in variants]
    names += ["legacy_indices_mean_max"]
    features = {name: pd.DataFrame({"reflectance": [1., 2., 3., 4.], "index": [4., 3., 2., 1.]},
                                  index=rows.index) for name in names}
    return rows, features, audit


def test_common_eligibility_requires_four_season_months_not_four_preharvest_months(config):
    rows, features, audit = eligibility_inputs()
    eligible, _ = build_eligibility(rows, features, audit, config)
    assert eligible.to_dict() == {"sparse_2022": False, "three_months": False,
                                 "four_months": True, "seven_months": True}


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("variant", ["bands_v1_preharvest_mean", "indices_v3_mode", "legacy_indices_mean_max"])
def test_missing_one_feature_excludes_the_field_from_every_model(config, bad, variant):
    rows, features, audit = eligibility_inputs()
    features[variant].loc["seven_months", "reflectance"] = bad
    original = features[variant].copy(deep=True)
    eligible, _ = build_eligibility(rows, features, audit, config)
    assert eligible.loc["four_months"]
    assert not eligible.loc["seven_months"]
    # The eligibility check must not fill the missing value in-place.
    pd.testing.assert_frame_equal(features[variant], original)


def test_imagery_eligibility_does_not_depend_on_recorded_yield_or_calendar_year(config):
    rows, features, audit = eligibility_inputs()
    expected, _ = build_eligibility(rows, features, audit, config)
    changed = rows.copy()
    changed["yield_t_ha"] = [np.nan, 1e99, -1e99, 0.]
    changed["season_year"] = [2024, 2023, 2022, 2024]
    actual, _ = build_eligibility(changed, features, audit, config)
    pd.testing.assert_series_equal(expected, actual)


@pytest.fixture
def model_context():
    rng = np.random.default_rng(197)
    ids = [f"field_{i}" for i in range(50)]
    x = pd.DataFrame(rng.normal(size=(50, 4)), index=ids)
    rows = pd.DataFrame({"domain": ["lacuna"] * 25 + ["zimbabwe_2024"] * 20 + ["lacuna"] * 5,
                         "fold": [2] * 20 + [-1] * 25 + [1] * 5,
                         "model_eligible": True,
                         "yield_t_ha": 3 + .5 * x[0]}, index=ids)
    return rows, x, ids[:25], ids[25:45], ids[45:]


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("role", ["fit", "source", "query"])
def test_model_context_rejects_missing_imagery_instead_of_imputing(model_context, bad, role):
    rows, x, fit, source, query = model_context
    ids = {"fit": fit, "source": source, "query": query}
    x.loc[ids[role][0], 0] = bad
    with pytest.raises((AssertionError, ValueError), match="[Ff]inite|[Mm]issing|[Ii]magery"):
        make_context(rows, x, fit, source, query)


@pytest.mark.parametrize("role", ["fit", "query"])
def test_fold_zero_is_rejected_before_model_fitting(model_context, role):
    rows, x, fit, source, query = model_context
    rows.loc[(fit if role == "fit" else query)[0], "fold"] = 0
    with pytest.raises((AssertionError, ValueError), match="[Ff]old|[Rr]eserv"):
        make_context(rows, x, fit, source, query)


def test_fitting_a_query_observation_is_rejected(model_context):
    rows, x, fit, source, query = model_context
    with pytest.raises((AssertionError, ValueError), match="[Oo]verlap|[Ll]eak|[Dd]isjoint|[Ii]ntersect"):
        make_context(rows, x, fit + query[:1], source, query)


def test_query_outcomes_do_not_change_expanded_training_predictions(model_context, config):
    rows, x, fit, source, query = model_context
    context = make_context(rows, x, fit, source, query)
    altered = rows.copy()
    altered.loc[query, "yield_t_ha"] = np.linspace(-1e100, 1e100, len(query))
    changed = make_context(altered, x, fit, source, query)
    for key in context:
        np.testing.assert_array_equal(context[key], changed[key])
    for kind, ratio in [("lacuna_only", 0.), ("pooled_adaptive", .3)]:
        params = {"alpha": 10., "source_ratio": ratio}
        np.testing.assert_array_equal(predict_model(context, kind, params, config),
                                      predict_model(changed, kind, params, config))


def test_source_and_query_features_do_not_fit_the_target_scaler(model_context):
    rows, x, fit, source, query = model_context
    context = make_context(rows, x, fit, source, query)
    altered = x.copy()
    altered.loc[source + query] = 1e20
    changed = make_context(rows, altered, fit, source, query)
    np.testing.assert_array_equal(context["xt"], changed["xt"])
    np.testing.assert_array_equal(context["yt"], changed["yt"])


def test_two_kilometre_buffer_uses_kilometres_and_handles_dateline():
    # Analytic equatorial arc lengths: no KD-tree/chord formula reused here.
    radius_km = 6371.0088
    distances_km = np.array([0., .5, 1.999, 2.001, 3.])
    longitudes = (179.999 + np.degrees(distances_km / radius_km) + 180) % 360 - 180
    source = pd.DataFrame({"lat": 0., "lon": longitudes}, index=list("abcde"))
    protected = pd.DataFrame({"lat": [0.], "lon": [179.999]})
    allowed, measured = purge_source(source, protected, 2.)
    np.testing.assert_allclose(measured, distances_km, atol=1e-8, rtol=0)
    assert allowed.index.tolist() == ["d", "e"]


def spatial_inputs():
    # Every primary location is >10 km from the next. Extra rows duplicate a
    # training/protected coordinate to make allowed/blocked cases unambiguous.
    ids = ["train", "inner_validation", "outer_evaluation", "reserved",
           "near_train", "near_inner", "near_outer", "near_reserved", "far_extra", "ineligible_extra", "source"]
    rows = pd.DataFrame({"domain": ["lacuna"] * 10 + ["zimbabwe_2024"],
                         "fold": [2, 3, 1, 0] + [-1] * 7,
                         "group_id": ids,
                         "lat": 0.,
                         "lon": [0., .1, .2, .3, 0., .1, .2, .3, .4, .5, .6],
                         "include_primary": [True] * 4 + [False] * 7,
                         "model_eligible": [True] * 9 + [False, True]}, index=pd.Index(ids, name="obs_id"))
    membership = pd.DataFrame([
        {"obs_id": "train", "outer_fold": 1, "inner_fold": 0, "role": "fit"},
        {"obs_id": "inner_validation", "outer_fold": 1, "inner_fold": 0, "role": "fit"},
        {"obs_id": "outer_evaluation", "outer_fold": 1, "inner_fold": 0, "role": "evaluation"},
        {"obs_id": "reserved", "outer_fold": 1, "inner_fold": 0, "role": "reserved"},
        {"obs_id": "train", "outer_fold": 1, "inner_fold": 1, "role": "fit"},
        {"obs_id": "inner_validation", "outer_fold": 1, "inner_fold": 1, "role": "validation"},
    ])
    # The nearest protected coordinate for the only source is longitude .3.
    distance = 6371.0088 * np.radians(.3)
    source_permission = pd.DataFrame({"obs_id": ["source", "source"], "outer_fold": 1,
                                      "inner_fold": [0, 1], "minimum_distance_to_protected_km": distance,
                                      "allowed_by_spatial_rule": True})
    return rows, membership, source_permission


def test_extra_lacuna_is_buffered_against_reserved_outer_and_inner_fields(config):
    rows, membership, source_permission = spatial_inputs()
    original = membership.copy(deep=True)
    permissions, fit_membership = build_permissions(rows, membership, source_permission, config)
    selected = permissions[permissions.allowed_by_spatial_rule]
    assert set(selected[selected.inner_fold.eq(0)].obs_id) == {"near_train", "near_inner", "far_extra"}
    assert set(selected[selected.inner_fold.eq(1)].obs_id) == {"near_train", "far_extra"}
    assert "ineligible_extra" not in set(permissions.obs_id)
    fits = fit_membership[fit_membership.role.eq("extra_lacuna_fit")]
    for inner in [0, 1]:
        assert set(fits[fits.inner_fold.eq(inner)].obs_id) == set(selected[selected.inner_fold.eq(inner)].obs_id)
    assert "reserved" not in set(fit_membership.obs_id)
    pd.testing.assert_frame_equal(original, membership)


@pytest.mark.parametrize("corruption", ["distance", "permission"])
def test_changed_source_permissions_are_rejected(config, corruption):
    rows, membership, source_permission = spatial_inputs()
    if corruption == "distance":
        source_permission.loc[0, "minimum_distance_to_protected_km"] = 1000.
    else:
        source_permission.loc[0, "allowed_by_spatial_rule"] = False
    with pytest.raises((AssertionError, ValueError), match="[Ss]ource|[Pp]ermission|[Dd]istance|[Ss]patial|[Mm]ismatch"):
        build_permissions(rows, membership, source_permission, config)


def paired_predictions():
    truth = np.linspace(0., 8., 1504)
    rows = pd.DataFrame({"obs_id": [f"evaluation_{i:04}" for i in range(1504)],
                         "group_id": [f"group_{i // 8:03}" for i in range(1504)],
                         "outer_fold": np.repeat([1, 2, 3, 4], 376),
                         "yield_t_ha": truth})
    return pd.concat([rows.assign(method="legacy_indices_mean_max_target", prediction_t_ha=truth + .5),
                      rows.assign(method="legacy_indices_mean_max_merged", prediction_t_ha=truth + .25)],
                     ignore_index=True)


def evaluation_config():
    return {"seed": 42, "bootstrap_draws": 50,
            "primary_method": "legacy_indices_mean_max_merged",
            "primary_reference": "legacy_indices_mean_max_target"}


def test_same_target_rmse_r2_and_paired_difference_are_consistent():
    predictions = paired_predictions()
    metrics, folds, contrasts = evaluate(predictions, evaluation_config())
    scores = metrics.set_index("method")
    target = scores.loc["legacy_indices_mean_max_target"]
    merged = scores.loc["legacy_indices_mean_max_merged"]
    variance = np.var(np.linspace(0., 8., 1504))
    assert target.rmse_t_ha == pytest.approx(.5)
    assert merged.rmse_t_ha == pytest.approx(.25)
    assert target.r2 == pytest.approx(1 - .25 / variance)
    assert merged.r2 == pytest.approx(1 - .0625 / variance)
    assert folds.groupby("method").n.sum().eq(1504).all()
    assert len(contrasts) == 1
    assert contrasts.iloc[0].delta_rmse_t_ha == pytest.approx(-.25)
    assert contrasts.iloc[0].delta_r2 == pytest.approx(.1875 / variance)
    assert contrasts.iloc[0].ci_low == pytest.approx(-.25)
    assert contrasts.iloc[0].ci_high == pytest.approx(-.25)


@pytest.mark.parametrize("column, value", [("obs_id", "new_evaluation_field"),
                                            ("yield_t_ha", 500.), ("group_id", "changed_group"),
                                            ("outer_fold", 2)])
def test_evaluation_comparisons_require_identical_fields_outcomes_groups_and_folds(column, value):
    predictions = paired_predictions()
    predictions.loc[1504, column] = value
    with pytest.raises((AssertionError, ValueError)):
        evaluate(predictions, evaluation_config())


@pytest.mark.parametrize("corruption", ["duplicate", "missing", "reserved"])
def test_evaluation_rejects_duplicates_missing_fields_and_reserved_fold(corruption):
    predictions = paired_predictions()
    if corruption == "duplicate":
        predictions.loc[0, "obs_id"] = predictions.loc[1, "obs_id"]
    elif corruption == "missing":
        predictions = predictions.drop(index=0)
    else:
        predictions.loc[0, "outer_fold"] = 0
    with pytest.raises((AssertionError, ValueError), match="evaluation membership"):
        evaluate(predictions, evaluation_config())


# ---- v2 team rules: include_primary pools, label-free eligibility, identical arms ----

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from cropyield.experiments.zimbabwe_aggregation import BANDS, INDICES, aggregate_monthly  # noqa: E402
from cropyield.experiments.zimbabwe_multiyear import arm_identity, training_pool  # noqa: E402


@pytest.fixture
def config_v2():
    path = Path(__file__).parents[1] / "configs/zimbabwe_multiyear_v2.json"
    return json.loads(path.read_text())


def test_v2_config_uses_calendar_comparison_and_v2_controls(config_v2):
    assert config_v2["window_anchor"] == "calendar" and config_v2["training_rows"] == "include_primary"
    assert "preharvest" not in config_v2["primary_method"] + config_v2["primary_reference"]
    assert "v1_preharvest_mean" not in config_v2["variants"]
    assert config_v2["controls_release"].endswith("zimbabwe_aggregation_v2")


def test_v2_pools_admit_only_include_primary_rows(config, config_v2):
    rows, membership, source_permission = spatial_inputs()
    v2 = {**config, "training_rows": "include_primary"}
    # v1 keeps the published broader pools.
    _, v1_fits = build_permissions(rows, membership, source_permission, config)
    assert {"near_train", "source"} <= set(v1_fits.obs_id)
    permissions, fits = build_permissions(rows, membership, source_permission, v2)
    assert permissions.empty
    trained = fits[fits.role.ne("query")]
    assert rows.loc[trained.obs_id, "include_primary"].all()
    assert not {"near_train", "near_inner", "far_extra", "source"} & set(fits.obs_id)
    # A primary 2024 row stays available under the rule.
    rows.loc["source", "include_primary"] = True
    _, fits = build_permissions(rows, membership, source_permission, v2)
    assert "source" in set(fits[fits.role.eq("source_allowed")].obs_id)
    assert training_pool(rows, v2).loc["far_extra"] == np.False_


@pytest.mark.parametrize("role", ["fit", "source"])
def test_v2_model_context_rejects_non_primary_training_rows(model_context, config_v2, role):
    rows, x, fit, source, query = model_context
    rows["include_primary"] = True
    make_context(rows, x, fit, source, query, config=config_v2)
    rows.loc[(fit if role == "fit" else source)[0], "include_primary"] = False
    with pytest.raises(ValueError, match="include_primary"):
        make_context(rows, x, fit, source, query, config=config_v2)


def test_v2_eligibility_does_not_depend_on_crop_dates(config_v2):
    rows = pd.DataFrame({"season_year": [2023, 2023], "domain": ["lacuna", "lacuna"],
                         "plant_date": pd.to_datetime(["2023-03-20", None]),
                         "harvest_date": pd.to_datetime(["2023-03-25", None])},
                        index=pd.Index(["late_dates", "no_dates"], name="obs_id"))
    monthly = pd.DataFrame([{"obs_id": obs_id, "month": f"{2022 + (m != 12)}-{m:02}", "missing": False,
                             "acquired": pd.Timestamp(2022 + (m != 12), m, 15), **{c: float(m) for c in BANDS + INDICES}}
                            for obs_id in rows.index for m in [12, 1, 2, 3, 4, 5, 6]])
    features, audit = aggregate_monthly(monthly, rows, config_v2)
    eligible, _ = build_eligibility(rows, features, audit, config_v2)
    # Under v1 the 20–25 March crop-date window is empty for "late_dates", so v1 drops it.
    v1 = {**config_v2, "window_anchor": "crop_dates", "variants": config_v2["variants"] + ["v1_preharvest_mean"]}
    v1_features, v1_audit = aggregate_monthly(monthly, rows, v1)
    v1_eligible, _ = build_eligibility(rows, v1_features, v1_audit, v1)
    assert eligible.all() and not v1_eligible.loc["late_dates"]
    moved = rows.assign(plant_date=pd.NaT, harvest_date=pd.NaT)
    again, _ = build_eligibility(moved, *aggregate_monthly(monthly, moved, config_v2), config_v2)
    pd.testing.assert_series_equal(eligible, again)


def test_arm_identity_marks_only_true_twins():
    base = pd.DataFrame({"obs_id": ["a", "b"], "prediction_t_ha": [1.0, 2.0]})
    controls = pd.concat([base.assign(method="bands_v0_mean_target"), base.assign(method="bands_v0_mean_merged")])
    new = pd.concat([base.assign(method="bands_v0_mean_all_lacuna"),
                     base.assign(method="bands_v0_mean_all_zimbabwe", prediction_t_ha=[1.0, 2.5])])
    identity = arm_identity(new, controls, 1e-9).set_index("method")
    assert identity.loc["bands_v0_mean_all_lacuna", "identical_to"] == "bands_v0_mean_target"
    assert identity.loc["bands_v0_mean_all_zimbabwe", "identical_to"] == ""
    assert identity.loc["bands_v0_mean_all_zimbabwe", "max_abs_prediction_difference_t_ha"] == pytest.approx(.5)
