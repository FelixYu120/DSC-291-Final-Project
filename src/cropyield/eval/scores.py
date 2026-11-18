"""Scores of docs/EVALUATION.md, within one cohort, on pooled out-of-fold predictions.

Yields go in as t/ha. Uncertainty comes from a cluster bootstrap: resample held-out groups, not
fields, because fields in one group are not independent. A model difference uses the same draws
for both models, so it is a paired interval.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.stats import rankdata

BOOTSTRAP_DRAWS = 2000


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - p) ** 2)))


def mae(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(p - y)))


def bias(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(p - y))


def r2(y: np.ndarray, p: np.ndarray) -> float:
    """1 - SSE/SST. Negative when the model is worse than predicting the test mean."""
    total = np.sum((y - y.mean()) ** 2)
    return float(1 - np.sum((y - p) ** 2) / total) if total > 0 else float("nan")


def spearman(y: np.ndarray, p: np.ndarray) -> float:
    """Rank correlation; NaN when one side is constant (for example a mean baseline)."""
    if np.ptp(y) == 0 or np.ptp(p) == 0:
        return float("nan")
    return float(np.corrcoef(rankdata(y), rankdata(p))[0, 1])


def centred(values: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    """Each value minus the mean of its cluster. Rounded, so that a constant inside a cluster gives exactly 0."""
    return np.round(values - pd.Series(values).groupby(clusters).transform("mean").to_numpy(), 9)


def in_large_clusters(clusters: np.ndarray, min_size: int = 3) -> np.ndarray:
    """True for the rows of clusters with at least `min_size` rows."""
    return pd.Series(clusters).groupby(clusters).transform("size").to_numpy() >= min_size


def rank_inside_clusters(y: np.ndarray, p: np.ndarray, clusters: np.ndarray, min_size: int = 3) -> float:
    """One Spearman after the mean of each cluster is taken out of y and of p, so place cannot help."""
    keep = in_large_clusters(clusters, min_size)
    return spearman(centred(y[keep], clusters[keep]), centred(p[keep], clusters[keep]))


def group_draws(groups: np.ndarray, draws: int, seed: int):
    """Row indices of `draws` cluster-bootstrap samples: groups drawn with replacement."""
    members = [np.flatnonzero(groups == g) for g in np.unique(groups)]
    rng = np.random.default_rng(seed)
    for _ in range(draws):
        yield np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))])


def _interval(values: list[float]) -> tuple[float, float]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) == 0:
        return float("nan"), float("nan")
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))


def paired_difference_ci(y, p_a, p_b, groups, score: Callable, draws: int = BOOTSTRAP_DRAWS,
                         seed: int = 0) -> tuple[float, float]:
    """95 % interval of score(a) - score(b) on the same draws. Excluding 0 means a real difference."""
    return _interval([score(y[i], p_a[i]) - score(y[i], p_b[i]) for i in group_draws(groups, draws, seed)])
