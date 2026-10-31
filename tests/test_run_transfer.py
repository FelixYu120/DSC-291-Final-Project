"""scripts/run_transfer.py: no target label reaches the model, and calibration only moves the level."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("run_transfer", SCRIPTS / "run_transfer.py")
run_transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_transfer)

ALPHAS = np.logspace(-3, 3, 7)


def cohort(seed: int, shift: float, n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return pd.DataFrame({"x": x, "yield_t_ha": 3 + shift + x + rng.normal(scale=0.2, size=n),
                         "cluster_2km": np.arange(n) // 4})


def test_target_labels_do_not_reach_the_prediction():
    source, target = cohort(1, 0.0), cohort(2, 5.0)
    shuffled = target.assign(yield_t_ha=target["yield_t_ha"].to_numpy()[::-1])
    for target_scaled in (False, True):
        first = run_transfer.transfer_predictions(source, target, ["x"], ALPHAS, target_scaled)
        second = run_transfer.transfer_predictions(source, shuffled, ["x"], ALPHAS, target_scaled)
        assert (first == second).all()


def test_target_scaling_absorbs_a_shift_in_the_features():
    source, target = cohort(1, 0.0), cohort(2, 0.0)
    moved = target.assign(x=target["x"] * 3 + 10)
    plain = run_transfer.transfer_predictions(source, target, ["x"], ALPHAS, True)
    assert run_transfer.transfer_predictions(source, moved, ["x"], ALPHAS, True) == pytest.approx(plain)
    assert run_transfer.transfer_predictions(source, moved, ["x"], ALPHAS, False) != pytest.approx(plain)


def test_calibration_removes_a_constant_offset_between_cohorts():
    target = cohort(2, 5.0)
    y = target["yield_t_ha"].to_numpy()
    p = y - 5.0 + np.random.default_rng(3).normal(scale=0.1, size=len(y))
    scores = run_transfer.calibrated_scores(y, p, target["cluster_2km"].astype(str).to_numpy(), seed=1)
    assert scores["calibrated_rmse_t_ha"] < 0.2
    assert scores["calibrated_r2"] > 0.9
