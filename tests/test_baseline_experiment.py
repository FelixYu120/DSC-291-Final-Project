"""The spatial baseline loop on synthetic fields; no shared data are scored here."""

import numpy as np
import pandas as pd
import pytest

from cropyield.baselines.experiment import out_of_fold
from cropyield.data.xy import FEATURES


@pytest.fixture
def config():
    return {"arms": ["R0", "R1", "A1"], "knn_neighbors": 10,
            "ridge": {"alphas_logspace": [-3, 3, 3], "inner_folds": 5}, "seed": 20261029}


@pytest.fixture
def rows():
    rng = np.random.default_rng(29)
    n = 50
    group = np.arange(n) // 2
    frame = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=FEATURES,
                         index=pd.Index([f"field:{i:03d}" for i in range(n)], name="obs_id"))
    frame["yield_t_ha"] = 3 + 0.4 * frame[FEATURES[0]] - 0.2 * frame[FEATURES[1]]
    frame["lat"] = -12 + group * 0.05 + (np.arange(n) % 2) * 0.0001
    frame["lon"] = 33.0
    frame["group_id"] = [f"g{i:02d}" for i in group]
    frame["fold"] = (group % 5).astype(str)
    return frame


def test_each_field_has_one_prediction_per_arm_and_correct_training_size(rows, config):
    predictions, fits = out_of_fold(rows, config)
    assert len(predictions) == len(rows) * 3
    assert set(predictions.arm) == {"R0", "R1", "A1"}
    assert (predictions.groupby(["obs_id", "arm"]).size() == 1).all()
    assert set(predictions.obs_id) == set(rows.index)
    assert (predictions.n_train == 40).all()
    assert len(fits) == 15
    assert (fits.n_train == 40).all() and (fits.n_test == 10).all()
    assert (fits.n_train_groups == 20).all() and (fits.n_test_groups == 5).all()
    assert fits.loc[fits.arm == "A1", "selected_alpha"].isin([0.001, 1.0, 1000.0]).all()
    assert fits.loc[fits.arm != "A1", "selected_alpha"].isna().all()
    joined = predictions.join(rows[["fold", "yield_t_ha"]], on="obs_id", rsuffix="_source")
    assert (joined.fold == joined.fold_source).all()
    np.testing.assert_array_equal(joined.yield_t_ha, joined.yield_t_ha_source)


def test_test_labels_cannot_change_that_folds_predictions_or_selected_alpha(rows, config):
    original, original_fits = out_of_fold(rows, config)
    changed_rows = rows.copy()
    changed_rows.loc[changed_rows.fold == "0", "yield_t_ha"] += 1000
    changed, changed_fits = out_of_fold(changed_rows, config)
    columns = ["obs_id", "arm", "predicted", "n_train"]
    sort = ["arm", "obs_id"]
    first = original.loc[original.fold == "0", columns].sort_values(sort).reset_index(drop=True)
    second = changed.loc[changed.fold == "0", columns].sort_values(sort).reset_index(drop=True)
    pd.testing.assert_frame_equal(first, second)
    assert original_fits.loc[(original_fits.fold == "0") & (original_fits.arm == "A1"), "selected_alpha"].item() == \
        changed_fits.loc[(changed_fits.fold == "0") & (changed_fits.arm == "A1"), "selected_alpha"].item()
    expected_mean = rows.loc[rows.fold != "0", "yield_t_ha"].mean()
    np.testing.assert_allclose(first.loc[first.arm == "R0", "predicted"], expected_mean)


def test_same_inputs_produce_identical_predictions_and_tuning_choices(rows, config):
    predictions, fits = out_of_fold(rows, config)
    again, again_fits = out_of_fold(rows, config)
    pd.testing.assert_frame_equal(predictions, again)
    pd.testing.assert_frame_equal(fits, again_fits)


def test_repeated_observation_ids_are_rejected(rows, config):
    with pytest.raises(ValueError):
        out_of_fold(pd.concat([rows, rows.iloc[[0]]]), config)


def test_a_geographic_group_cannot_cross_outer_folds(rows, config):
    rows.loc[rows.index[2], "group_id"] = rows.iloc[0].group_id
    with pytest.raises(ValueError):
        out_of_fold(rows, config)


def test_a_missing_outer_fold_is_rejected(rows, config):
    with pytest.raises(ValueError):
        out_of_fold(rows[rows.fold != "4"], config)


@pytest.mark.parametrize("column,value", [(FEATURES[0], np.inf), ("yield_t_ha", np.nan),
                                          ("lat", np.nan), ("lon", np.inf)])
def test_nonfinite_model_inputs_are_rejected(rows, config, column, value):
    rows.loc[rows.index[0], column] = value
    with pytest.raises(ValueError):
        out_of_fold(rows, config)
