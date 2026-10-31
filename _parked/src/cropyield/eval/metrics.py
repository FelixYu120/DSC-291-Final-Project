"""Scores of docs/EVALUATION.md, within one cohort, on pooled out-of-fold predictions.

Yields go in as t/ha. Uncertainty comes from a cluster bootstrap: resample held-out groups, not
fields, because fields in one group are not independent. A model difference uses the same draws
for both models, so it is a paired interval.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.stats import rankdata

BOOTSTRAP_DRAWS = 2000


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y - p) ** 2)))


def mae(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(y - p)))


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


def bottom_recall(y: np.ndarray, p: np.ndarray, share: float = 0.2) -> float:
    """Of the true bottom `share` of fields, the part the model also places in its bottom `share`."""
    n = max(1, round(len(y) * share))
    true_bottom = set(np.argsort(y, kind="stable")[:n])
    return len(true_bottom & set(np.argsort(p, kind="stable")[:n])) / n


def pearson(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.corrcoef(y, p)[0, 1])


SCORES: dict[str, Callable] = {"rmse_t_ha": rmse, "mae_t_ha": mae, "bias_t_ha": bias, "r2": r2,
                               "spearman": spearman, "bottom20_recall": bottom_recall}
BOOTSTRAPPED = ("rmse_t_ha", "r2", "spearman")


def within_group_spearman(y: np.ndarray, p: np.ndarray, groups: np.ndarray, min_fields: int = 10) -> float:
    """Median Spearman inside held-out groups with at least `min_fields`; NaN when there are none."""
    values = [spearman(y[groups == g], p[groups == g]) for g in np.unique(groups) if (groups == g).sum() >= min_fields]
    values = [v for v in values if np.isfinite(v)]
    return float(np.median(values)) if values else float("nan")


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


def bootstrap_ci(y, p, groups, score: Callable, draws: int = BOOTSTRAP_DRAWS, seed: int = 0) -> tuple[float, float]:
    """95 % interval of one score."""
    return _interval([score(y[i], p[i]) for i in group_draws(groups, draws, seed)])


def paired_difference_ci(y, p_a, p_b, groups, score: Callable, draws: int = BOOTSTRAP_DRAWS,
                         seed: int = 0) -> tuple[float, float]:
    """95 % interval of score(a) - score(b) on the same draws. Excluding 0 means a real difference."""
    return _interval([score(y[i], p_a[i]) - score(y[i], p_b[i]) for i in group_draws(groups, draws, seed)])
