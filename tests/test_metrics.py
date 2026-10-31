"""Scores and the cluster bootstrap on small hand-checked cases."""
import numpy as np
import pytest

from cropyield.eval.metrics import (bias, bootstrap_ci, bottom_recall, group_draws, mae, paired_difference_ci, pearson,
                                    r2, rmse, spearman, within_group_spearman)

Y = np.array([1.0, 2.0, 3.0, 4.0])
P = np.array([1.0, 2.0, 3.0, 8.0])


def test_error_scores_by_hand():
    assert rmse(Y, P) == pytest.approx(2.0)
    assert mae(Y, P) == pytest.approx(1.0)
    assert bias(Y, P) == pytest.approx(1.0)


def test_r2_is_zero_for_the_test_mean_and_negative_when_worse():
    assert r2(Y, np.full(4, Y.mean())) == pytest.approx(0.0)
    assert r2(Y, Y) == pytest.approx(1.0)
    assert r2(Y, Y[::-1]) < 0


def test_spearman_uses_ranks_and_is_nan_for_a_constant():
    assert spearman(Y, P) == pytest.approx(1.0)
    assert spearman(Y, -P) == pytest.approx(-1.0)
    assert np.isnan(spearman(Y, np.zeros(4)))


def test_pearson_by_hand():
    assert pearson(Y, 2 * Y + 1) == pytest.approx(1.0)


def test_bottom_recall_finds_the_true_bottom_fields():
    y = np.arange(10.0)
    assert bottom_recall(y, y) == 1.0
    assert bottom_recall(y, -y) == 0.0
    assert bottom_recall(y, np.r_[9.0, 8.0, y[2:]]) == 0.0


def test_within_group_spearman_ignores_small_groups_and_between_group_levels():
    groups = np.repeat(["a", "b", "small"], [10, 10, 3])
    y = np.r_[np.arange(10.0), np.arange(10.0) + 100, 0, 1, 2]
    p = np.r_[np.arange(10.0) + 50, np.arange(10.0), 2, 1, 0]
    assert within_group_spearman(y, p, groups) == pytest.approx(1.0)
    assert np.isnan(within_group_spearman(y[:3], p[:3], groups[:3]))


def test_group_draws_resample_whole_groups():
    groups = np.repeat(["a", "b", "c"], [2, 3, 4])
    for rows in group_draws(groups, 50, seed=1):
        counts = np.bincount(rows, minlength=9)
        assert len(set(counts[:2])) == len(set(counts[2:5])) == len(set(counts[5:])) == 1


def test_bootstrap_interval_is_seeded_and_brackets_the_estimate():
    rng = np.random.default_rng(0)
    y = rng.normal(size=300)
    p = y + rng.normal(scale=0.5, size=300)
    groups = np.repeat(np.arange(30), 10).astype(str)
    low, high = bootstrap_ci(y, p, groups, rmse, draws=300, seed=3)
    assert low < rmse(y, p) < high
    assert (low, high) == bootstrap_ci(y, p, groups, rmse, draws=300, seed=3)


def test_paired_difference_excludes_zero_only_for_a_real_difference():
    rng = np.random.default_rng(0)
    y = rng.normal(size=300)
    good = y + rng.normal(scale=0.2, size=300)
    bad = y + rng.normal(scale=1.0, size=300)
    groups = np.repeat(np.arange(30), 10).astype(str)
    assert paired_difference_ci(y, good, bad, groups, rmse, draws=300)[1] < 0
    assert paired_difference_ci(y, good, good, groups, rmse, draws=50) == (0.0, 0.0)
