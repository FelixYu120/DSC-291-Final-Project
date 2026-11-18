"""Check date-safe aggregation, missingness and a defensible continuous mode estimate."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cropyield.experiments.zimbabwe_aggregation import (
    BANDS,
    INDICES,
    aggregate_monthly,
    half_sample_mode,
    make_context,
)
from cropyield.experiments.zimbabwe_merge import predict_model


@pytest.fixture
def config():
    path = Path(__file__).parents[1] / "configs/zimbabwe_aggregation_v1.json"
    return json.loads(path.read_text())


def seasonal_inputs(values=(1., 2., 3., 4., 5., 6., 7.)):
    """One comparable season in each domain, with all monthly spine rows present."""
    rows = pd.DataFrame({
        "obs_id": ["target", "source"],
        "domain": ["lacuna", "zimbabwe_2024"],
        "season_year": [2023, 2024],
        "harvest_date": pd.to_datetime(["2023-04-15", None]),
        "yield_t_ha": [3., 1.],
    }).set_index("obs_id")
    monthly = []
    for obs_id, row in rows.iterrows():
        for month, value in zip([12, 1, 2, 3, 4, 5, 6], values, strict=True):
            year = row.season_year - int(month == 12)
            monthly.append({"obs_id": obs_id, "month": f"{year}-{month:02}",
                            "acquired": pd.Timestamp(year, month, 15),
                            "missing": False,
                            **{column: value for column in BANDS + INDICES}})
    return pd.DataFrame(monthly), rows


@pytest.mark.parametrize("values, expected", [
    ([5.], 5.), ([2., 8.], 5.),
    ([0., 1., 2., 3., 4.], 2.),
    # Three equally narrow intervals have estimates 0.5, 3.5 and 3.5.
    ([0., 1., 3., 4., 6.], 2.5),
    ([0., 2., 3., 4., 10., 20., 40.], 3.),
    ([0., 1., 1., 1., 1., 10., 100.], 1.),
])
def test_half_sample_mode_handles_small_samples_ties_and_a_dense_cluster(values, expected):
    assert half_sample_mode(values) == pytest.approx(expected)
    assert half_sample_mode(list(reversed(values))) == pytest.approx(expected)


def test_mode_ignores_missing_values_without_turning_them_into_zeros():
    assert np.isnan(half_sample_mode([np.nan, np.inf, -np.inf]))
    assert half_sample_mode([np.nan, 2., np.inf, 8.]) == pytest.approx(5.)


def test_mode_is_equivariant_to_positive_unit_conversion():
    values = np.array([0., 2., 3., 4., 10., 20., 40.])
    assert half_sample_mode(values * 7 + 100) == pytest.approx(half_sample_mode(values) * 7 + 100)


def test_year_alignment_and_separate_statistics_preserve_the_same_fields(config):
    monthly, rows = seasonal_inputs()
    features, _ = aggregate_monthly(monthly, rows, config)
    expected = {"v0_mean": 4., "v1_preharvest_mean": 2.5,
                "v1_calendar_mean": 2.5, "v2_max": 7.,
                "v3_median": 4., "v3_mode": 4.}
    assert set(features) == {f"{family}_{version}" for family in ["bands", "indices"] for version in expected}
    for family, width in [("bands", len(BANDS)), ("indices", len(INDICES))]:
        for version, value in expected.items():
            frame = features[f"{family}_{version}"]
            assert frame.index.equals(rows.index)
            assert frame.shape == (2, width)
            np.testing.assert_allclose(frame.to_numpy(), value)


def test_preharvest_selection_uses_scene_date_not_its_month_label(config):
    monthly, rows = seasonal_inputs()
    # A scene in the harvest month is still usable if it precedes the harvest day.
    ix = monthly.obs_id.eq("target") & monthly.month.eq("2023-04")
    monthly.loc[ix, "acquired"] = pd.Timestamp("2023-04-10")
    features, _ = aggregate_monthly(monthly, rows, config)
    for family in ["bands", "indices"]:
        np.testing.assert_allclose(features[f"{family}_v1_preharvest_mean"].loc["target"], 3.)
        np.testing.assert_allclose(features[f"{family}_v0_mean"].loc["target"], 4.)
        np.testing.assert_allclose(features[f"{family}_v1_preharvest_mean"].loc["source"], 2.5)


def test_after_harvest_values_cannot_change_preharvest_features(config):
    monthly, rows = seasonal_inputs()
    original, _ = aggregate_monthly(monthly, rows, config)
    after = monthly.obs_id.eq("target") & monthly.acquired.ge(pd.Timestamp("2023-04-15"))
    monthly.loc[after, BANDS + INDICES] = 1e12
    altered, _ = aggregate_monthly(monthly, rows, config)
    for family in ["bands", "indices"]:
        pd.testing.assert_frame_equal(original[f"{family}_v1_preharvest_mean"],
                                      altered[f"{family}_v1_preharvest_mean"])
        assert not original[f"{family}_v2_max"].equals(altered[f"{family}_v2_max"])


def test_unknown_dates_use_calendar_fallback_and_actual_harvest_can_differ(config):
    monthly, rows = seasonal_inputs()
    rows.loc["target", "harvest_date"] = pd.Timestamp("2023-05-01")
    features, _ = aggregate_monthly(monthly, rows, config)
    for family in ["bands", "indices"]:
        np.testing.assert_allclose(features[f"{family}_v1_preharvest_mean"].loc["target"], 3.)
        np.testing.assert_allclose(features[f"{family}_v1_calendar_mean"].loc["target"], 2.5)
        np.testing.assert_allclose(features[f"{family}_v1_preharvest_mean"].loc["source"], 2.5)


def test_known_planting_date_excludes_preplant_scenes_but_includes_planting_day(config):
    monthly, rows = seasonal_inputs()
    rows["plant_date"] = pd.to_datetime(["2023-01-15", None])
    features, audit = aggregate_monthly(monthly, rows, config)
    for family in ["bands", "indices"]:
        np.testing.assert_allclose(features[f"{family}_v1_preharvest_mean"].loc["target"], 3.)
        np.testing.assert_allclose(features[f"{family}_v1_calendar_mean"].loc["target"], 2.5)
        np.testing.assert_allclose(features[f"{family}_v1_preharvest_mean"].loc["source"], 2.5)
    assert audit.loc["target", "n_season"] == 7
    assert audit.loc["target", "n_preharvest"] == 3
    assert audit.loc["target", "n_calendar"] == 4
    assert audit.loc["target", "has_plant_date"]
    assert not audit.loc["source", "has_plant_date"]


def test_empty_preharvest_window_retains_field_with_missing_features(config):
    monthly, rows = seasonal_inputs()
    rows.loc["target", "harvest_date"] = pd.Timestamp("2022-12-01")
    features, _ = aggregate_monthly(monthly, rows, config)
    for family in ["bands", "indices"]:
        frame = features[f"{family}_v1_preharvest_mean"]
        assert frame.index.equals(rows.index)
        assert frame.loc["target"].isna().all()
        assert frame.loc["source"].notna().all()


def test_missing_months_are_skipped_and_not_replaced_with_zero(config):
    monthly, rows = seasonal_inputs()
    missing = monthly.month.str.endswith("-12")
    monthly.loc[missing, "missing"] = True
    monthly.loc[missing, "acquired"] = pd.NaT
    monthly.loc[missing, BANDS + INDICES] = np.nan
    features, _ = aggregate_monthly(monthly, rows, config)
    for family in ["bands", "indices"]:
        np.testing.assert_allclose(features[f"{family}_v0_mean"], 4.5)
        np.testing.assert_allclose(features[f"{family}_v1_preharvest_mean"], 3.)
        np.testing.assert_allclose(features[f"{family}_v3_median"], 4.5)


def test_missing_one_variable_does_not_discard_other_observed_variables(config):
    monthly, rows = seasonal_inputs()
    monthly.loc[monthly.month.str.endswith("-12"), BANDS[0]] = np.nan
    features, _ = aggregate_monthly(monthly, rows, config)
    bands = features["bands_v0_mean"]
    np.testing.assert_allclose(bands.iloc[:, 0], 4.5)
    np.testing.assert_allclose(bands.iloc[:, 1:], 4.)
    np.testing.assert_allclose(features["indices_v0_mean"], 4.)


def test_duplicate_month_keys_are_rejected(config):
    monthly, rows = seasonal_inputs()
    duplicate = pd.concat([monthly, monthly.iloc[[0]]], ignore_index=True)
    with pytest.raises((ValueError, AssertionError), match="[Dd]uplicate|unique"):
        aggregate_monthly(duplicate, rows, config)


def test_yield_values_cannot_affect_features_or_date_selection(config):
    monthly, rows = seasonal_inputs()
    original, audit = aggregate_monthly(monthly, rows, config)
    rows["yield_t_ha"] = [np.nan, 1e100]
    altered, changed_audit = aggregate_monthly(monthly, rows, config)
    for name in original:
        pd.testing.assert_frame_equal(original[name], altered[name])
    pd.testing.assert_frame_equal(audit, changed_audit)


@pytest.fixture
def model_context():
    rng = np.random.default_rng(20261107)
    x = pd.DataFrame(rng.normal(size=(90, 4)))
    rows = pd.DataFrame({"domain": ["lacuna"] * 30 + ["zimbabwe_2024"] * 50 + ["lacuna"] * 10,
                         "fold": [1] * 30 + [-1] * 50 + [2] * 10,
                         "yield_t_ha": 3 + .2 * x[0]})
    return rows, x, list(range(30)), list(range(30, 80)), list(range(80, 90))


def test_query_outcomes_cannot_change_preprocessing_or_fitted_predictions(model_context, config):
    rows, x, fit_ids, source_ids, query_ids = model_context
    original = make_context(rows, x, fit_ids, source_ids, query_ids)
    changed = rows.copy()
    changed.loc[query_ids, "yield_t_ha"] = np.linspace(-1e100, 1e100, len(query_ids))
    altered = make_context(changed, x, fit_ids, source_ids, query_ids)
    for name in original:
        np.testing.assert_array_equal(original[name], altered[name])
    for method, ratio in [("lacuna_only", 0.), ("pooled_adaptive", .3)]:
        params = {"alpha": 10., "source_ratio": ratio}
        np.testing.assert_array_equal(predict_model(original, method, params, config),
                                      predict_model(altered, method, params, config))


@pytest.mark.parametrize("role", ["fit", "query"])
def test_reserved_fold_zero_cannot_be_fitted_or_predicted(model_context, role):
    rows, x, fit_ids, source_ids, query_ids = model_context
    rows.loc[fit_ids[0] if role == "fit" else query_ids[0], "fold"] = 0
    with pytest.raises((ValueError, AssertionError), match="Fold zero"):
        make_context(rows, x, fit_ids, source_ids, query_ids)


# ---- v2 team rules: label-free windows and include_primary training rows ----

from cropyield.experiments.zimbabwe_aggregation import (  # noqa: E402
    CROP_DATE_VARIANT,
    model_variants,
    require_training_rows,
    training_rows,
    window_anchor,
)


@pytest.fixture
def config_v2():
    path = Path(__file__).parents[1] / "configs/zimbabwe_aggregation_v2.json"
    return json.loads(path.read_text())


def test_v2_config_applies_both_team_rules(config_v2):
    assert window_anchor(config_v2) == "calendar"
    assert training_rows(config_v2) == "include_primary"
    assert CROP_DATE_VARIANT not in config_v2["variants"]
    assert CROP_DATE_VARIANT not in config_v2["primary_method"] + config_v2["primary_reference"]
    assert config_v2["primary_method"] == "bands_v1_calendar_mean_target"


def test_absent_switches_keep_v1_behaviour(config):
    assert "window_anchor" not in config and "training_rows" not in config
    assert window_anchor(config) == "crop_dates" and training_rows(config) == "all_screened"
    assert CROP_DATE_VARIANT in model_variants(config)


def test_calendar_rule_rejects_a_crop_date_model_candidate(config_v2):
    bad = {**config_v2, "variants": config_v2["variants"] + [CROP_DATE_VARIANT]}
    with pytest.raises(ValueError, match="crop dates"):
        model_variants(bad)
    monthly, rows = seasonal_inputs()
    with pytest.raises(ValueError, match="crop dates"):
        aggregate_monthly(monthly, rows, bad)


def test_v2_model_candidates_never_use_planting_or_harvest_dates(config_v2):
    monthly, rows = seasonal_inputs()
    rows["plant_date"] = pd.to_datetime(["2023-01-15", None])
    original, audit = aggregate_monthly(monthly, rows, config_v2)
    assert not any("preharvest" in name for name in original)
    assert set(original) == {f"{f}_{v}" for f in ["bands", "indices"] for v in config_v2["variants"]}
    # Moving or deleting every survey date must leave every model feature unchanged.
    for plant, harvest in [(["2022-12-20", None], ["2023-02-01", None]), ([None, None], [None, None]),
                           (["2023-03-01", "2024-01-01"], ["2023-06-20", "2024-02-01"])]:
        changed = rows.copy()
        changed["plant_date"] = pd.to_datetime(plant)
        changed["harvest_date"] = pd.to_datetime(harvest)
        altered, _ = aggregate_monthly(monthly, changed, config_v2)
        for name in original:
            pd.testing.assert_frame_equal(original[name], altered[name])
    # Crop-date counts survive only as explicitly labelled diagnostics.
    dated = [c for c in audit if "harvest" in c or "plant" in c or "crop_date" in c]
    assert dated and all(c.startswith("diagnostic_") for c in dated)


def test_v2_calendar_window_is_december_to_march_for_every_source(config_v2):
    monthly, rows = seasonal_inputs()
    features, _ = aggregate_monthly(monthly, rows, config_v2)
    for family in ["bands", "indices"]:
        np.testing.assert_allclose(features[f"{family}_v1_calendar_mean"], 2.5)


@pytest.mark.parametrize("role", ["fit", "source"])
def test_v2_training_pool_rejects_rows_outside_include_primary(model_context, config_v2, role):
    rows, x, fit_ids, source_ids, query_ids = model_context
    rows["include_primary"] = True
    make_context(rows, x, fit_ids, source_ids, query_ids, config=config_v2)  # all primary: accepted
    rows.loc[(fit_ids if role == "fit" else source_ids)[0], "include_primary"] = False
    with pytest.raises(ValueError, match="include_primary"):
        make_context(rows, x, fit_ids, source_ids, query_ids, config=config_v2)
    # The v1 config keeps its published pool (2024 zeros included).
    make_context(rows, x, fit_ids, source_ids, query_ids, config={"training_rows": "all_screened"})


def test_v2_training_guard_requires_the_include_primary_column(model_context, config_v2):
    rows, x, fit_ids, source_ids, query_ids = model_context
    with pytest.raises(ValueError, match="include_primary"):
        require_training_rows(rows, fit_ids + source_ids, config_v2)
