"""Hand-checked cases for the new logic in stepup.py: the between/within R2 split and the pairwise rank model."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location("stepup", Path(__file__).with_name("stepup.py"))
su = importlib.util.module_from_spec(spec)
spec.loader.exec_module(su)

Y = np.array([1.0, 2.0, 3.0, 5.0, 6.0, 7.0])
C = np.array(["a", "a", "a", "b", "b", "b"])


def test_perfect_prediction_is_one_between_and_within():
    between, within, share = su.decompose(Y, Y.copy(), C)
    assert between == pytest.approx(1.0) and within == pytest.approx(1.0)
    # cluster means 2 and 6 around 4: between SS 6*4 = 24 of total SS 28
    assert share == pytest.approx(24 / 28)


def test_predicting_only_the_village_mean_has_no_within_skill():
    village_mean = np.array([2.0, 2.0, 2.0, 6.0, 6.0, 6.0])
    between, within, _ = su.decompose(Y, village_mean, C)
    assert between == pytest.approx(1.0)
    assert within == pytest.approx(0.0)


def test_pairwise_rank_model_learns_the_right_order():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, 2))
    y = 3 * X[:, 0] + rng.normal(scale=0.1, size=60)          # yield follows the first feature
    clusters = np.repeat(np.arange(6), 10)
    score, n_pairs = su.bradley_terry(X, y, clusters, X)
    assert n_pairs == 6 * 45                                   # all pairs inside each cluster of 10
    assert np.corrcoef(score, y)[0, 1] > 0.9


def test_holm_family_keeps_every_scored_step_but_the_coordinates_baseline():
    frame = pd.DataFrame({"step": ["S0 R0 training mean", "S1 R1 coordinates only (10 nearest fields)", "S2 GCVI peak",
                                   "S5 A1: 5 indices, max + mean", "S10 Presto frozen embedding (128)",
                                   "S11 10 bands monthly + Presto", "S12 MOSAIKS field + chip (v1, 2,048)"],
                          "p_rank": [np.nan, 0.01, 0.02, np.nan, 0.03, 0.04, 0.05]})
    assert su.holm_family(frame).tolist() == [False, False, True, False, True, True, True]
