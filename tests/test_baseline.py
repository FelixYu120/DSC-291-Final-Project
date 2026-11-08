"""The baseline: scores on hand-checked cases, the models, the join on obs_id, and the stored numbers."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cropyield.baselines import Winsorize, coordinates_knn, ridge_cv, train_mean
from cropyield.data.labels import sha256
from cropyield.eval.scores import (centred, group_draws, paired_difference_ci, r2, rank_inside_clusters, rmse,
                                   spearman)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("step8_run_baseline", ROOT / "scripts" / "step8_run_baseline.py")
run_baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_baseline)

Y = np.array([1.0, 2.0, 3.0, 4.0])
P = np.array([1.0, 2.0, 3.0, 8.0])
RUN_OF_30_OCT = {("malawi_2023", "R0"): 1.54420, ("malawi_2023", "R1"): 1.62531, ("malawi_2023", "A1"): 1.40030,
                 ("kenya_oaf_2019_2020", "R0"): 1.74573, ("kenya_oaf_2019_2020", "R1"): 1.53641,
                 ("kenya_oaf_2019_2020", "A1"): 1.69594, ("zimbabwe_lacuna_2022_2023", "R0"): 2.00603,
                 ("zimbabwe_lacuna_2022_2023", "R1"): 1.86140, ("zimbabwe_lacuna_2022_2023", "A1"): 1.78640}


def test_rmse_by_hand():
    assert rmse(Y, P) == pytest.approx(2.0)


def test_r2_is_zero_for_the_test_mean_and_negative_when_worse():
    assert r2(Y, np.full(4, Y.mean())) == pytest.approx(0.0)
    assert r2(Y, Y) == pytest.approx(1.0)
    assert r2(Y, Y[::-1]) < 0


def test_spearman_uses_ranks_and_is_nan_for_a_constant():
    assert spearman(Y, P) == pytest.approx(1.0)
    assert spearman(Y, -P) == pytest.approx(-1.0)
    assert np.isnan(spearman(Y, np.zeros(4)))


def test_group_draws_resample_whole_groups():
    groups = np.repeat(["a", "b", "c"], [2, 3, 4])
    for rows in group_draws(groups, 50, seed=1):
        counts = np.bincount(rows, minlength=9)
        assert len(set(counts[:2])) == len(set(counts[2:5])) == len(set(counts[5:])) == 1


def test_paired_difference_excludes_zero_only_for_a_real_difference():
    rng = np.random.default_rng(0)
    y = rng.normal(size=300)
    good = y + rng.normal(scale=0.2, size=300)
    bad = y + rng.normal(scale=1.0, size=300)
    groups = np.repeat(np.arange(30), 10).astype(str)
    assert paired_difference_ci(y, good, bad, groups, rmse, draws=300)[1] < 0
    assert paired_difference_ci(y, good, good, groups, rmse, draws=50) == (0.0, 0.0)


def test_rank_inside_clusters_ignores_levels_between_clusters_and_drops_small_clusters():
    clusters = np.repeat(["a", "b", "small"], [4, 4, 2])
    y = np.array([1.0, 2.0, 3.0, 4.0, 101.0, 102.0, 103.0, 104.0, 0.0, 1.0])
    p = np.array([51.0, 52.0, 53.0, 54.0, 1.0, 2.0, 3.0, 4.0, 1.0, 0.0])  # right inside a and b, wrong between them
    assert spearman(y, p) < 0.5
    assert rank_inside_clusters(y, p, clusters) == pytest.approx(1.0)
    assert rank_inside_clusters(y, p, clusters, min_size=2) < 1.0


def test_a_model_that_is_constant_inside_each_cluster_has_no_rank():
    clusters = np.repeat(["a", "b", "c"], 4)
    means = np.repeat([1 / 3, 7 / 3, 100 / 7], 4)  # means that leave rounding noise when they are subtracted
    assert (centred(means, clusters) == 0).all()
    assert np.isnan(rank_inside_clusters(np.arange(12.0), means, clusters))


def test_ridge_alpha_is_chosen_inside_the_training_rows():
    rng = np.random.default_rng(1)
    signal = rng.normal(size=100)
    y = 3 + signal + rng.normal(scale=0.1, size=100)
    X = signal[:, None]
    groups = (np.arange(100) // 5).astype(str)
    predicted, alpha = ridge_cv(X[:80], y[:80], groups[:80], X[80:], np.logspace(-3, 3, 7))
    assert alpha in np.logspace(-3, 3, 7)
    assert len(predicted) == 20
    assert np.corrcoef(predicted, y[80:])[0, 1] > 0.9


def test_ridge_clips_one_extreme_test_value_to_the_training_range():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(200, 2))
    y = 3 + X[:, 0] + rng.normal(scale=0.1, size=200)
    groups = (np.arange(200) % 20).astype(str)
    predicted, _ = ridge_cv(X, y, groups, np.array([[10_000.0, 0.0]]), np.logspace(-3, 3, 7))
    assert y.min() <= predicted[0] <= y.max()


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


def test_split_rows_follow_the_fields_by_obs_id_and_drop_rows_without_x():
    split = pd.DataFrame({"obs_id": ["c", "a", "no_x", "b"], "fold": ["2", "0", "1", "1"]})
    rows = run_baseline.split_on_rows(split, pd.Index(["a", "b", "c"], name="obs_id"))
    assert rows["fold"].tolist() == ["0", "1", "2"]


def test_a_test_field_never_enters_its_own_training():
    n = 60
    rng = np.random.default_rng(3)
    index = pd.Index([f"f{i}" for i in range(n)], name="obs_id")
    X = pd.DataFrame(rng.normal(size=(n, 2)), index=index)
    y = pd.Series(rng.normal(size=n) + 3, index=index)
    fields = pd.DataFrame({"fold": (np.arange(n) // 12).astype(str), "group_id": (np.arange(n) // 4).astype(str),
                           "lat": np.arange(n) * 0.1, "lon": 0.0}, index=index)
    held_out = (fields["fold"] == "0").to_numpy()
    y[held_out] = 1000.0
    predicted = run_baseline.out_of_fold(X, y, fields)
    assert predicted["R0"][held_out] == pytest.approx(y[~held_out].mean())
    assert predicted["R1"][held_out].max() < 100
    assert predicted["A1"][held_out].max() < 100


def test_a_changed_frozen_file_stops_the_run(tmp_path):
    (tmp_path / "processed").mkdir()
    (tmp_path / "splits").mkdir()
    labels = tmp_path / "processed" / "labels_v1.parquet"
    labels.write_bytes(b"labels")
    names = [f"{cohort}__{run_baseline.FAMILY}.csv" for cohort in run_baseline.COHORTS]
    for name in names:
        (tmp_path / "splits" / name).write_bytes(name.encode())
    manifest = {"labels_sha256": sha256(labels), "files": {name: {"sha256": sha256(tmp_path / "splits" / name)} for name in names}}
    (tmp_path / "splits" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    run_baseline.check_frozen(tmp_path)
    (tmp_path / "splits" / names[0]).write_bytes(b"changed")
    with pytest.raises(SystemExit):
        run_baseline.check_frozen(tmp_path)


def test_a_wrong_row_count_or_a_changed_y_stops_the_run(monkeypatch, tmp_path):
    index = pd.Index([f"f{i}" for i in range(run_baseline.COHORTS["malawi_2023"])], name="obs_id")
    X = pd.DataFrame({"feature": 0.0}, index=index)
    y = pd.Series(1.0, index=index)
    labels = pd.DataFrame({"yield_kg_ha": 1000.0, "lat": 0.0, "lon": 0.0}, index=index)
    monkeypatch.setattr(run_baseline, "load_xy", lambda cohort, data: (X.iloc[:-1], y.iloc[:-1]))
    with pytest.raises(SystemExit, match="expected"):
        run_baseline.cohort_rows("malawi_2023", tmp_path, labels)
    monkeypatch.setattr(run_baseline, "load_xy", lambda cohort, data: (X, y + 0.001))
    with pytest.raises(SystemExit, match="differs from labels_v1"):
        run_baseline.cohort_rows("malawi_2023", tmp_path, labels)


def test_the_stored_scores_equal_the_run_of_30_october():
    scores = pd.read_csv(ROOT / "results" / "baseline_scores.csv")
    rmse_of = scores[scores["metric"] == "rmse_t_ha"].set_index(["cohort", "arm"])["value"]
    for key, value in RUN_OF_30_OCT.items():
        assert rmse_of[key] == pytest.approx(value, abs=0.001 if key[1] == "R1" else 0.0001)  # R1 has ties in distance
