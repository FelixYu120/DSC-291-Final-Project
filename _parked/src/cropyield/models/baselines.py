"""Reference models and the Ridge head of the arms in docs/ROADMAP.md.

Every function fits on the training rows only and predicts the test rows; scaling and the choice
of alpha happen inside the training fold, with the same grouping as the outer split.
"""
from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class Winsorize(TransformerMixin, BaseEstimator):
    """Clip each feature at its training 1st and 99th percentile.

    MTCI divides by B05 - B04, which can be near zero: one month reached 1300 where the median is
    about 4.5, and a single such value would decide a Ridge fit.
    """

    def fit(self, X, y=None):
        self.low_, self.high_ = np.quantile(X, [0.01, 0.99], axis=0)
        return self

    def transform(self, X):
        return np.clip(X, self.low_, self.high_)


def train_mean(y_train: np.ndarray, n_test: int) -> np.ndarray:
    """R0: the training-fold mean for every test field."""
    return np.full(n_test, float(np.mean(y_train)))


def coordinates_knn(train_latlon: np.ndarray, y_train: np.ndarray, test_latlon: np.ndarray, k: int) -> np.ndarray:
    """R1: mean yield of the k nearest training fields, great-circle distance, no imagery."""
    model = KNeighborsRegressor(n_neighbors=min(k, len(y_train)), metric="haversine", algorithm="ball_tree")
    return model.fit(np.radians(train_latlon), y_train).predict(np.radians(test_latlon))


def ridge_cv(X_train: np.ndarray, y_train: np.ndarray, groups_train: np.ndarray, X_test: np.ndarray,
             alphas: np.ndarray) -> tuple[np.ndarray, float]:
    """Clip, standardise, choose alpha by grouped CV on the training rows, predict. Returns (predictions, alpha)."""
    pipeline = make_pipeline(Winsorize(), StandardScaler(), Ridge())
    splits = min(5, len(np.unique(groups_train)))
    search = GridSearchCV(pipeline, {"ridge__alpha": alphas}, cv=GroupKFold(n_splits=splits),
                          scoring="neg_mean_squared_error")
    search.fit(X_train, y_train, groups=groups_train)
    return search.predict(X_test), float(search.best_params_["ridge__alpha"])
