"""Three reference models, adapted from the archived baseline implementation.

Every function sees training labels only. A1's entire preprocessing pipeline is
refitted inside each inner validation fold, then on the full outer training set.
"""
from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import check_is_fitted


class Winsorize(TransformerMixin, BaseEstimator):
    """Limit each feature to its training 1st–99th percentile range.

    MTCI can become very large when its denominator is close to zero. These
    limits are fitted within the pipeline; test fields never set the limits.
    """

    def fit(self, X, y=None):
        self.low_, self.high_ = np.quantile(X, [0.01, 0.99], axis=0)
        return self

    def transform(self, X):
        check_is_fitted(self, ['low_', 'high_'])
        return np.clip(X, self.low_, self.high_)


def train_mean(y_train: np.ndarray, n_test: int) -> np.ndarray:
    """R0: predict the average training yield for every test field."""
    return np.full(n_test, float(np.mean(y_train)))


def coordinates_knn(train_latlon, y_train, test_latlon, k=10) -> np.ndarray:
    """R1: average the k nearest training yields using great-circle distance.

    Haversine expects [latitude, longitude] in radians, not degrees.
    Equal-distance ties follow the deterministic input row order.
    """
    model = KNeighborsRegressor(n_neighbors=min(k, len(y_train)), metric='haversine', algorithm='ball_tree')
    return model.fit(np.radians(train_latlon), y_train).predict(np.radians(test_latlon))


def ridge_cv(X_train, y_train, groups_train, X_test, alphas, inner_folds=5) -> tuple[np.ndarray, float]:
    """A1: choose regularisation by grouped validation inside the training set."""
    if len(np.unique(groups_train)) < inner_folds:
        raise ValueError(f'A1 needs at least {inner_folds} distinct training groups')
    pipeline = make_pipeline(Winsorize(), StandardScaler(), Ridge())
    search = GridSearchCV(
        pipeline, {'ridge__alpha': np.asarray(alphas)},
        cv=GroupKFold(n_splits=inner_folds), scoring='neg_mean_squared_error',
        n_jobs=1, error_score='raise', refit=True,
    )
    search.fit(X_train, y_train, groups=groups_train)
    return search.predict(X_test), float(search.best_params_['ridge__alpha'])
