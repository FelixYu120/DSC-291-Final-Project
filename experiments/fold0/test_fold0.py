import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location("score_fold0", Path(__file__).with_name("score_fold0.py"))
f0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f0)


def fields_and_data(seed: int = 0):
    rng = np.random.default_rng(seed)
    folds = np.repeat(["0", "1", "2", "3", "4"], 30)
    groups = np.array([f"{fold}-{i // 10}" for i, fold in enumerate(folds)])
    fields = pd.DataFrame({"fold": folds, "group_id": groups, "season_year": 2023,
                           "lat": rng.uniform(-20, -17, len(folds)), "lon": rng.uniform(28, 32, len(folds))},
                          index=[f"f{i}" for i in range(len(folds))])
    X = pd.DataFrame(rng.normal(size=(len(folds), 3)), index=fields.index)
    y = pd.Series(2 * X[0] + rng.normal(scale=0.1, size=len(folds)), index=fields.index)
    return X, y, fields


def test_fold0_labels_never_reach_the_training_rows():
    X, y, fields = fields_and_data()
    changed = y.copy()
    changed[fields["fold"] == "0"] = 1e6
    a, b = f0.fold0_predict(X, y, fields), f0.fold0_predict(X, changed, fields)
    assert len(a) == 30 and np.allclose(a, b)


def test_holm_family_leaves_out_the_three_baselines():
    X, y, fields = fields_and_data()
    test = (fields["fold"] == "0").to_numpy()
    yt, sub = y.to_numpy()[test], fields[test]
    good = f0.fold0_predict(X, y, fields)
    predicted = {"R0": np.full(30, y[~test].mean()), "R1": good + 0.5, "A1": good, "M2": good + 0.01, "X1": good - 0.01}
    frame = f0.score(yt, predicted, sub).set_index("arm")
    assert frame["p_rank_holm"].notna().to_dict() == {"R0": False, "R1": False, "A1": False, "M2": True, "X1": True}
    assert frame.loc["A1", "mae"] < frame.loc["R1", "mae"]
    assert frame.loc["R1", "bias"] > 0.4


def test_fold0_labels_never_reach_the_baseline_arms():
    X, y, fields = fields_and_data(1)
    changed = y.copy()
    changed[fields["fold"] == "0"] = 1e6
    test = (fields["fold"] == "0").to_numpy()
    a = f0.step8.out_of_fold(X, y, fields, f0.TRAIN_FOLDS)
    b = f0.step8.out_of_fold(X, changed, fields, f0.TRAIN_FOLDS)
    for arm in ("R0", "R1", "A1"):
        assert np.isfinite(a[arm][test]).all() and np.isnan(a[arm][~test]).all()
        assert np.allclose(a[arm][test], b[arm][test]), arm
    assert np.allclose(a["A1"][test], f0.fold0_predict(X, y, fields))


def test_a_blank_reason_is_refused():
    with pytest.raises(SystemExit):
        f0.main(["--reason", "   "])
