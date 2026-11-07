"""Training isolation and geographic distances for the three baseline models."""

import numpy as np
import pytest

from cropyield.baselines import models


def test_r0_is_the_training_mean_for_every_test_observation():
    np.testing.assert_array_equal(models.train_mean(np.array([0.0, 2.0, 7.0]), 4), [3.0] * 4)


def test_r1_uses_great_circle_distances_and_converts_degrees_to_radians():
    # The nearest field crosses the date line in case 1; longitude contracts near the pole in case 2.
    train = np.array([[0, 179.9], [0, 170], [80, 10], [78, 0], [34, -118], [-20, 130]])
    test = np.array([[0, -179.9], [80, 0], [33, -117], [-21, 129]])
    predicted = models.coordinates_knn(train, np.arange(1.0, 7.0), test, k=1)
    np.testing.assert_array_equal(predicted, [1.0, 3.0, 5.0, 6.0])


def test_r1_averages_the_nearest_training_yields():
    train = np.array([[0.0, 0.0], [0.0, 0.1], [0.0, 10.0]])
    predicted = models.coordinates_knn(train, np.array([1.0, 3.0, 100.0]), np.array([[0.0, 0.05]]), k=2)
    assert predicted[0] == pytest.approx(2.0)


def test_winsorization_learns_limits_from_training_data_only():
    train = np.column_stack([np.arange(101.0), np.arange(101.0) * 2])
    clip = models.Winsorize().fit(train)
    low_before, high_before = clip.low_.copy(), clip.high_.copy()
    transformed = clip.transform(np.array([[-1e9, 1e9], [1e9, -1e9]]))
    np.testing.assert_allclose(transformed, [[1.0, 198.0], [99.0, 2.0]])
    np.testing.assert_array_equal(clip.low_, low_before)
    np.testing.assert_array_equal(clip.high_, high_before)


def test_ridge_inner_validation_keeps_whole_groups_and_refits_preprocessing(monkeypatch):
    rng = np.random.default_rng(17)
    X = rng.normal(size=(40, 3))
    y = 3 + 0.7 * X[:, 0] - 0.2 * X[:, 1]
    groups = np.repeat(np.arange(20).astype(str), 2)
    held_out = np.full((3, 3), 1e6)
    splits_seen, fit_sizes = [], []
    original_group_kfold, original_winsorize = models.GroupKFold, models.Winsorize

    class RecordingGroupKFold(original_group_kfold):
        def split(self, X, y=None, groups=None):
            assert groups is not None
            for train, valid in super().split(X, y, groups):
                assert set(groups[train]).isdisjoint(groups[valid])
                splits_seen.append((len(train), len(valid)))
                yield train, valid

    class RecordingWinsorize(original_winsorize):
        def fit(self, X, y=None):
            fit_sizes.append(len(X))
            assert np.abs(X).max() < 1e6, "Held-out features entered preprocessing.fit"
            return super().fit(X, y)

    monkeypatch.setattr(models, "GroupKFold", RecordingGroupKFold)
    monkeypatch.setattr(models, "Winsorize", RecordingWinsorize)
    predicted, alpha = models.ridge_cv(X, y, groups, held_out, np.array([0.01, 10.0]), inner_folds=5)
    assert len(splits_seen) == 5
    assert all(train == 32 and valid == 8 for train, valid in splits_seen)
    assert fit_sizes.count(32) == 10  # Two alpha choices, independently fitted in each inner fold.
    assert fit_sizes.count(40) == 1   # The chosen model is then refitted on the whole outer training set.
    assert len(predicted) == 3 and np.isfinite(predicted).all()
    assert alpha in [0.01, 10.0]


def test_ridge_refuses_to_tune_without_separate_groups():
    with pytest.raises(ValueError):
        models.ridge_cv(np.arange(12.0).reshape(-1, 1), np.arange(12.0), np.zeros(12),
                        np.array([[4.0]]), np.array([0.1, 1.0]), inner_folds=5)
