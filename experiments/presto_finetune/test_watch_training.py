"""watch_training.py must train exactly like presto_lib.train_one, so its TensorBoard curves show the real runs.

    C:\\Users\\flori\\.venvs\\presto-tb\\Scripts\\python.exe -m pytest experiments/presto_finetune/test_watch_training.py -q -p no:cacheprovider
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("tensorboard")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import presto_lib as lib  # noqa: E402
import watch_training  # noqa: E402

COHORT = "zimbabwe_lacuna_2022_2023"


def test_watch_curve_equals_train_one(tmp_path, monkeypatch):
    X, y, fields = lib.cohort_rows(COHORT)
    sample = fields.iloc[np.random.default_rng(3).choice(len(fields), 90, replace=False)].sort_index()
    arrays = lib.build_arrays(COHORT, sample)
    values = y.loc[sample.index].to_numpy()
    index = np.arange(len(values))
    train, val, test = index[:60], index[60:80], index[80:]
    monkeypatch.setattr(lib, "MAX_EPOCHS", 3)
    monkeypatch.setattr(lib, "PATIENCE", 99)  # train_one runs all epochs, like the watch run
    monkeypatch.setitem(lib._WORKER, "arrays", arrays)
    monkeypatch.setitem(lib._WORKER, "y", values)
    job = {"arm": "P1", "lr": 1e-4, "seed": 11, "train": train, "val": val}
    real = lib.train_one(job | {"fold": "1", "inner": 0, "arrays": arrays, "y": values, "test": test})
    watched = watch_training.watch(job | {"epochs": 3, "logdir": tmp_path / "run"})
    np.testing.assert_allclose(watched["curve"], real["curve"], rtol=1e-6)
    assert watched["best_epoch"] == real["best_epoch"]
    assert any((tmp_path / "run").rglob("events.out.tfevents.*"))
