"""scripts/run_experiment.py on synthetic rows: no leakage, the buffer, scores, and repeatable numbers."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cropyield.models.baselines import Winsorize, coordinates_knn, ridge_cv, train_mean

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_experiment.py"
spec = importlib.util.spec_from_file_location("run_experiment", SCRIPT)
run_experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_experiment)

ARMS = {"R0": {"model": "train_mean"},
        "R1": {"model": "knn", "k": 3, "features": ["lat", "lon"]},
        "A1": {"model": "ridge_cv", "features": ["signal"], "alphas": {"logspace": [-3, 3, 7]}}}
CONFIG = {"arms": ARMS}


def field_rows(n: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    signal = rng.normal(size=n)
    return pd.DataFrame({"obs_id": [f"f{i}" for i in range(n)], "lat": np.arange(n) * 0.1, "lon": 0.0,
                         "signal": signal, "yield_t_ha": 3 + signal + rng.normal(scale=0.1, size=n)})


def five_folds(rows: pd.DataFrame) -> pd.DataFrame:
    groups = (np.arange(len(rows)) // 5).astype(str)
    return pd.DataFrame({"obs_id": rows["obs_id"], "group_id": groups, "fold": (np.arange(len(rows)) // 5 % 5).astype(str),
                         "repeat": 0})


def test_every_field_is_predicted_once_per_arm_from_training_rows_only():
    rows = field_rows()
    predictions = run_experiment.out_of_fold(rows, five_folds(rows), CONFIG, None)
    assert (predictions.groupby("arm")["obs_id"].nunique() == len(rows)).all()
    assert (predictions.groupby(["arm", "obs_id"]).size() == 1).all()
    assert (predictions["n_train"] == 80).all()


def test_mean_baseline_ignores_the_test_fold():
    rows = field_rows()
    split = five_folds(rows)
    rows.loc[split["fold"] == "0", "yield_t_ha"] = 1000.0
    predictions = run_experiment.out_of_fold(rows, split, CONFIG, None)
    mean = predictions[predictions["arm"] == "R0"]
    fold_zero = mean[mean["fold"] == "0"]["predicted"]
    assert fold_zero.iloc[0] < 1000.0
    train = rows[~rows["obs_id"].isin(split.loc[split["fold"] == "0", "obs_id"])]
    assert fold_zero.iloc[0] == pytest.approx(train["yield_t_ha"].mean())


def test_buffer_drops_training_fields_next_to_a_test_field():
    rows = field_rows()   # 0.1 degree apart, about 11 km
    split = five_folds(rows)
    plain = run_experiment.out_of_fold(rows, split, CONFIG, None)
    buffered = run_experiment.out_of_fold(rows, split, CONFIG, 12.0)
    assert plain["n_train"].iloc[0] == 80
    assert buffered["n_train"].max() < 80


def test_temporal_split_uses_the_train_rows_only():
    rows = field_rows(40)
    split = pd.DataFrame({"obs_id": rows["obs_id"], "group_id": "g", "repeat": 0, "test_subset": "",
                          "fold": ["train"] * 30 + ["test"] * 10})
    split["group_id"] = (np.arange(40) // 4).astype(str)
    split.loc[30:, "test_subset"] = "seen_region"
    predictions = run_experiment.out_of_fold(rows, split, CONFIG, None)
    assert set(predictions["obs_id"]) == set(rows["obs_id"].iloc[30:])
    assert (predictions["n_train"] == 30).all()


def test_scores_have_pooled_folds_and_a_paired_comparison_and_repeat_exactly():
    rows = field_rows()
    predictions = run_experiment.out_of_fold(rows, five_folds(rows), CONFIG, None)
    first = pd.DataFrame(run_experiment.score_rows(predictions, "R1", 7, {"run_id": "x"}))
    second = pd.DataFrame(run_experiment.score_rows(run_experiment.out_of_fold(rows, five_folds(rows), CONFIG, None),
                                                    "R1", 7, {"run_id": "x"}))
    pd.testing.assert_frame_equal(first, second)
    pooled = first[first["fold"] == "pooled"]
    assert {"rmse_t_ha", "r2", "spearman", "spearman_within_group", "rmse_minus_R1"} <= set(pooled["metric"])
    a1 = pooled[(pooled["arm"] == "A1") & (pooled["metric"] == "r2")]["value"].iloc[0]
    assert a1 > 0.9                                     # the signal is in the feature
    delta = pooled[(pooled["arm"] == "A1") & (pooled["metric"] == "rmse_minus_R1")].iloc[0]
    assert delta["value"] < 0 and delta["ci_high"] < 0   # and it beats the coordinates
    assert set(first.loc[first["fold"] != "pooled", "fold"]) == {"0", "1", "2", "3", "4"}


def test_noise_ceiling_reports_the_two_cuts():
    labels = pd.DataFrame({"cohort": "c", "include_primary": True, "cut1_kg_ha": [1000.0, 2000.0, 3000.0],
                           "cut2_kg_ha": [1000.0, 2000.0, 4000.0]})
    rows = run_experiment.noise_ceiling(labels, "c", {"run_id": "x"})
    values = {row["metric"]: row["value"] for row in rows}
    assert values["rmse_cut1_cut2_t_ha"] == pytest.approx(np.sqrt(1 / 3))
    assert 0.9 < values["pearson_cut1_cut2"] < 1


def test_ridge_alpha_is_chosen_inside_the_training_rows():
    rows = field_rows()
    X = rows[["signal"]].to_numpy()
    y = rows["yield_t_ha"].to_numpy()
    groups = (np.arange(100) // 5).astype(str)
    predicted, alpha = ridge_cv(X[:80], y[:80], groups[:80], X[80:], np.logspace(-3, 3, 7))
    assert alpha in np.logspace(-3, 3, 7)
    assert len(predicted) == 20
    assert np.corrcoef(predicted, y[80:])[0, 1] > 0.9


def test_coordinates_knn_is_the_mean_of_the_nearest_fields():
    train = np.array([[0.0, 0.0], [0.0, 0.1], [0.0, 10.0]])
    predicted = coordinates_knn(train, np.array([1.0, 3.0, 100.0]), np.array([[0.0, 0.05]]), k=2)
    assert predicted[0] == pytest.approx(2.0)


def test_train_mean():
    assert train_mean(np.array([1.0, 3.0]), 3).tolist() == [2.0, 2.0, 2.0]


def test_winsorize_uses_training_limits_and_tames_one_extreme_value():
    train = np.r_[np.arange(100.0), 1300.0][:, None]
    clip = Winsorize().fit(train)
    assert clip.transform(train).max() < 101
    assert clip.transform(np.array([[5000.0]]))[0, 0] == clip.high_[0]
