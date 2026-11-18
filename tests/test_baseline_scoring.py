"""Hand-check scores, paired comparisons, and whole-group uncertainty estimates."""

import numpy as np
import pandas as pd
import pytest

from cropyield.baselines.scoring import group_draws, metrics, score_predictions


def test_error_metrics_match_hand_calculation_and_constant_ranks_are_undefined():
    values = metrics(np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.0, 2.0, 3.0, 8.0]))
    assert values["rmse_t_ha"] == pytest.approx(2.0)
    assert values["mae_t_ha"] == pytest.approx(1.0)
    assert values["bias_t_ha"] == pytest.approx(1.0)
    assert values["r2"] == pytest.approx(-2.2)
    assert values["spearman"] == pytest.approx(1.0)
    assert np.isnan(metrics(np.arange(4.0), np.ones(4))["spearman"])
    assert np.isnan(metrics(np.ones(4), np.arange(4.0))["r2"])


def test_bootstrap_keeps_every_member_of_a_group_together_and_repeats_by_seed():
    groups = np.repeat(["a", "b", "c"], [2, 3, 4])
    first = list(group_draws(groups, draws=50, seed=17))
    second = list(group_draws(groups, draws=50, seed=17))
    for selected, repeated in zip(first, second):
        np.testing.assert_array_equal(selected, repeated)
        counts = np.bincount(selected, minlength=len(groups))
        for group in np.unique(groups):
            assert np.unique(counts[groups == group]).size == 1


def prediction_table(fold_shapes):
    """Two identical predictors, with configurable field/group counts per fold."""
    parts = []
    offset = 0
    for fold, (n_fields, n_groups) in enumerate(fold_shapes):
        ids = np.arange(offset, offset + n_fields)
        y = 1 + ids / 100
        parts.append(pd.DataFrame({
            "obs_id": [f"field:{i}" for i in ids], "fold": str(fold),
            "group_id": [f"fold{fold}:g{i}" for i in np.arange(n_fields) % n_groups],
            "yield_t_ha": y, "predicted": y + 0.2 * np.sin(ids),
            "n_train": sum(n for n, _ in fold_shapes) - n_fields,
        }))
        offset += n_fields
    base = pd.concat(parts, ignore_index=True)
    return pd.concat([base.assign(arm="R0"), base.assign(arm="R1")], ignore_index=True)


def test_paired_comparison_aligns_ids_even_when_reference_rows_are_shuffled():
    predictions = prediction_table([(20, 5), (20, 5), (20, 5)])
    reference = predictions[predictions.arm == "R1"].sample(frac=1, random_state=13)
    reordered = pd.concat([predictions[predictions.arm == "R0"], reference], ignore_index=True)
    scored = pd.DataFrame(score_predictions(reordered, seed=23, draws=50))
    delta = scored[(scored.arm == "R0") & (scored.metric == "rmse_minus_R1")].iloc[0]
    assert delta["value"] == pytest.approx(0.0)
    assert delta.ci_low == pytest.approx(0.0)
    assert delta.ci_high == pytest.approx(0.0)
    again = pd.DataFrame(score_predictions(reordered, seed=23, draws=50))
    pd.testing.assert_frame_equal(scored, again)


def test_small_folds_are_suppressed_by_both_field_and_group_count():
    # Fold 0 lacks 100 fields, fold 1 lacks 10 groups; only fold 2 meets both thresholds.
    predictions = prediction_table([(99, 11), (108, 9), (100, 10)])
    scored = pd.DataFrame(score_predictions(predictions, seed=29, draws=50))
    assert set(scored.fold) == {"pooled", "2"}
    assert set(scored.loc[scored.fold == "pooled", "arm"]) == {"R0", "R1"}
    assert (scored.loc[scored.fold == "pooled", "n_test"] == 307).all()
    assert (scored.loc[scored.fold == "2", "n_test"] == 100).all()
    assert (scored.loc[scored.fold == "2", "n_groups"] == 10).all()
