"""Pooled yield errors and paired confidence intervals over geographic groups.

The bootstrap resamples already-held-out predictions; it does not retrain models
or capture every source of uncertainty in model fitting or yield measurement.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import rankdata

METRICS = ('rmse_t_ha', 'mae_t_ha', 'bias_t_ha', 'r2', 'spearman')


def metrics(y, predicted) -> dict[str, float]:
    y, predicted = np.asarray(y), np.asarray(predicted)
    error = predicted - y
    total = np.sum((y - y.mean()) ** 2)
    rank_correlation = (float(np.corrcoef(rankdata(y), rankdata(predicted))[0, 1])
                        if np.ptp(y) > 0 and np.ptp(predicted) > 0 else float('nan'))
    return {
        'rmse_t_ha': float(np.sqrt(np.mean(error ** 2))),
        'mae_t_ha': float(np.mean(np.abs(error))),
        'bias_t_ha': float(np.mean(error)),
        'r2': float(1 - np.sum(error ** 2) / total) if total > 0 else float('nan'),
        'spearman': rank_correlation,
    }


def group_draws(groups, draws, seed):
    """Sample whole groups with replacement, preserving all their observations."""
    groups = np.asarray(groups)
    members = [np.flatnonzero(groups == group) for group in np.unique(groups)]
    rng = np.random.default_rng(seed)
    for _ in range(draws):
        yield np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))])


def interval(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    return tuple(np.quantile(values, [0.025, 0.975])) if len(values) else (float('nan'), float('nan'))


def score_predictions(predictions, seed=20261029, draws=2000):
    """Long metric rows, pooled CIs, and paired RMSE differences against R1.

    Individual fold scores require at least 100 fields and 10 groups. Malawi
    therefore has pooled scores only, while its predictions remain available.
    """
    output = []
    reference = predictions[predictions.arm == 'R1'].set_index('obs_id')['predicted']
    for arm, part in predictions.groupby('arm', sort=False):
        y = part.yield_t_ha.to_numpy()
        p = part.predicted.to_numpy()
        groups = part.group_id.to_numpy()
        other = reference.loc[part.obs_id].to_numpy()
        values = metrics(y, p)
        bootstrap = {name: [] for name in METRICS}
        differences = []
        for selected in group_draws(groups, draws, seed):
            sampled = metrics(y[selected], p[selected])
            for name in METRICS:
                bootstrap[name].append(sampled[name])
            differences.append(sampled['rmse_t_ha'] - float(np.sqrt(np.mean((other[selected] - y[selected]) ** 2))))
        common = {'arm': arm, 'n_train_min': int(part.n_train.min()), 'n_train_max': int(part.n_train.max()),
                  'n_test': len(part), 'n_groups': len(np.unique(groups)), 'fold': 'pooled'}
        for name, value in values.items():
            low, high = interval(bootstrap[name])
            output.append({**common, 'metric': name, 'value': value, 'ci_low': low, 'ci_high': high})
        if arm != 'R1':
            low, high = interval(differences)
            output.append({**common, 'metric': 'rmse_minus_R1',
                           'value': values['rmse_t_ha'] - metrics(y, other)['rmse_t_ha'],
                           'ci_low': low, 'ci_high': high})
        for fold, piece in part.groupby('fold', sort=True):
            if len(piece) < 100 or piece.group_id.nunique() < 10:
                continue
            for name, value in metrics(piece.yield_t_ha, piece.predicted).items():
                output.append({**common, 'fold': fold, 'n_test': len(piece),
                               'n_groups': int(piece.group_id.nunique()),
                               'n_train_min': int(piece.n_train.iloc[0]), 'n_train_max': int(piece.n_train.iloc[0]),
                               'metric': name, 'value': value, 'ci_low': None, 'ci_high': None})
    return output
