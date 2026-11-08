"""Focused checks of the Presto fine-tune experiment. They read data/v2 read-only and write nothing.

    python -m pytest experiments/presto_finetune/test_presto_finetune.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import presto_lib as lib  # noqa: E402

COHORT = "zimbabwe_lacuna_2022_2023"


@pytest.fixture(scope="module")
def cohort():
    X, y, fields = lib.cohort_rows(COHORT)
    sample = fields.iloc[np.random.default_rng(0).choice(len(fields), 120, replace=False)].sort_index()
    return y, fields, sample, lib.build_arrays(COHORT, sample)


def test_parked_files_match_the_manifest():
    hashes = lib.check_parked()
    assert set(hashes) == set(lib.PARKED_MODULES.values())


def test_rows_window_and_folds():
    X, y, fields = lib.cohort_rows(COHORT)
    assert len(y) == 1880 and list(fields.index) == list(y.index)
    assert sorted(fields["fold"].unique()) == ["0", "1", "2", "3", "4"]
    assert lib.WINDOWS[COHORT] == ("2022-10", "2023-06")


def test_only_clear_months_carry_values(cohort):
    y, fields, sample, arrays = cohort
    series = lib.monthly_series(COHORT, sample.index)
    with duckdb.connect(str(lib.DATABASE), read_only=True) as con:
        rows = con.execute("SELECT obs_id, month, coverage_state, b08 FROM monthly WHERE cohort = ?", [COHORT]).df()
    rows = rows[rows["obs_id"].isin(sample.index) & rows["month"].between(*lib.WINDOWS[COHORT])]
    for row in rows.itertuples():
        value = series[row.obs_id].band("B08")[series[row.obs_id].months.index(row.month)]
        if row.coverage_state == "clear":
            assert value == pytest.approx(row.b08, abs=1e-6)
        else:
            assert np.isnan(value)


def test_inputs_keep_reflectance_and_mask_missing_months(cohort):
    y, fields, sample, arrays = cohort
    series = lib.monthly_series(COHORT, sample.index)
    first = sample.index[0]
    s, x, mask = series[first], arrays.x[0].numpy(), arrays.mask[0].numpy()
    b8 = lib.presto_inputs.__globals__["NORMED_BANDS"].index("B8")
    present = ~s.missing
    np.testing.assert_allclose(x[present, b8], s.band("B08")[present], atol=1e-7)  # no second -0.1 offset
    assert (mask[s.missing] == 1).all()
    assert (mask[:, :2] == 1).all() and (mask[:, 12:16] == 1).all()  # S1, ERA5, SRTM masked
    assert arrays.month == 9  # October, 0-based


def test_kept_tokens_equal_presto_own_count(cohort):
    y, fields, sample, arrays = cohort
    encoder = lib.load_presto().encoder
    for count in np.unique(arrays.kept):
        block = np.flatnonzero(arrays.kept == count)[:4]
        with torch.no_grad():
            _, kept, _ = encoder(**arrays.batch(block), eval_task=False)
        assert kept.shape[1] == count


def test_batched_embedding_equals_parked_encode(cohort):
    y, fields, sample, arrays = cohort
    model = lib.load_presto()
    series = lib.monthly_series(COHORT, sample.index[:20])
    single = np.stack([lib.encode(model, lib.presto_inputs(series[i], float(sample.loc[i, "lat"]),
                                                             float(sample.loc[i, "lon"])))
                       for i in sample.index[:20]])
    batched = lib.embed(model.encoder, arrays, np.arange(20))
    np.testing.assert_allclose(batched, single, atol=1e-5)


def test_no_location_zeroes_only_latlons(cohort):
    y, fields, sample, arrays = cohort
    a, b = arrays.batch(np.arange(5)), arrays.batch(np.arange(5), no_location=True)
    assert torch.equal(b["latlons"], torch.zeros_like(a["latlons"])) and torch.equal(a["x"], b["x"])
    assert a["latlons"].abs().sum() > 0


def test_inner_splits_hold_out_groups_and_never_touch_the_test_fold():
    X, y, fields = lib.cohort_rows(COHORT)
    groups, folds = fields["group_id"].to_numpy(), fields["fold"].to_numpy()
    for fold in lib.SCORED_FOLDS:
        test, train = np.flatnonzero(folds == fold), np.flatnonzero(folds != fold)
        assert (folds[train] == "0").any()  # fold 0 trains
        seen_val = []
        for inner_train, inner_val in lib.inner_splits(train, groups):
            assert not set(groups[inner_train]) & set(groups[inner_val])
            assert not (set(inner_train) | set(inner_val)) & set(test)
            seen_val += list(inner_val)
        assert sorted(seen_val) == sorted(train)


def test_models_pretrained_and_random(cohort):
    pretrained, random = lib.new_model("P1", 1), lib.new_model("P2", 1)
    stored = lib.load_presto().encoder.state_dict()
    for name, value in pretrained.encoder.state_dict().items():
        assert torch.equal(value, stored[name])
    assert not torch.equal(random.encoder.blocks[0].attn.qkv.weight, stored["blocks.0.attn.qkv.weight"])
    assert pretrained.encoder.pos_embed.requires_grad is False


def test_test_labels_never_change_a_prediction(cohort, monkeypatch):
    """Scramble the test-fold yields: the inner model, its best epoch and its test predictions stay the same."""
    y, fields, sample, arrays = cohort
    monkeypatch.setattr(lib, "MAX_EPOCHS", 2)
    values = y.loc[sample.index].to_numpy()
    index = np.arange(len(values))
    train, val, test = index[:70], index[70:95], index[95:]
    job = {"arm": "P1", "fold": "1", "lr": 1e-4, "inner": 0, "seed": 7, "arrays": arrays,
           "train": train, "val": val, "test": test}
    scrambled = values.copy()
    scrambled[test] = np.random.default_rng(1).normal(50, 20, len(test))
    first, second = lib.train_one(job | {"y": values}), lib.train_one(job | {"y": scrambled})
    assert first["best_epoch"] == second["best_epoch"] and first["curve"] == second["curve"]
    np.testing.assert_array_equal(first["test_pred"], second["test_pred"])
    assert np.isfinite(first["test_pred"]).all()


def test_never_finite_validation_falls_back_to_start_weights(cohort, monkeypatch):
    y, fields, sample, arrays = cohort
    monkeypatch.setattr(lib, "MAX_EPOCHS", 2)
    real_predict = lib.predict
    index = np.arange(len(sample))
    train, val, test = index[:70], index[70:95], index[95:]
    monkeypatch.setattr(lib, "predict", lambda model, arrays_, rows, no_location, size=256:
                        np.full(len(rows), np.nan) if rows is val else real_predict(model, arrays_, rows, no_location))
    result = lib.train_one({"arm": "P2", "fold": "1", "lr": 1e-4, "inner": 0, "seed": 3, "arrays": arrays,
                            "y": y.loc[sample.index].to_numpy(), "train": train, "val": val, "test": test})
    assert result["best_epoch"] == 0 and np.isfinite(result["test_pred"]).all()


def test_baselines_match_step8_before_training():
    import run_cohort
    for cohort in ("zimbabwe_lacuna_2022_2023", "malawi_2022", "malawi_2023"):
        X, y, fields = lib.cohort_rows(cohort)
        tested = fields["fold"].isin(lib.SCORED_FOLDS).to_numpy()
        predicted = lib.step8.out_of_fold(X, y, fields, skip=("0",))
        arms = run_cohort.arm_scores(y.to_numpy()[tested], {a: predicted[a][tested] for a in lib.step8.ARMS},
                                     fields[tested])
        run_cohort.check_baselines(cohort, arms)  # exits on a mismatch


def test_posthoc_raw_features_mask_missing_months(cohort):
    import posthoc_controls
    y, fields, sample, arrays = cohort
    raw = posthoc_controls.raw_features(arrays)
    assert raw.shape == (len(sample), 9 * 11)
    missing_months = arrays.mask.numpy()[:, :, 2].reshape(len(sample), 9) == 1
    assert np.isnan(raw.reshape(len(sample), 9, 11)[missing_months]).all()
    assert np.isfinite(raw.reshape(len(sample), 9, 11)[~missing_months]).all()


def test_a3ft_recipe_runs_and_ignores_test_labels(cohort, monkeypatch):
    import posthoc_a3ft as a3
    y, fields, sample, arrays = cohort
    monkeypatch.setattr(a3, "PROBE_EPOCHS", 1)
    monkeypatch.setattr(a3, "MAX_EPOCHS", 4)
    index = np.arange(len(sample))
    train, val, test = index[:70], index[70:95], index[95:]
    values = y.loc[sample.index].to_numpy()
    scrambled = values.copy()
    scrambled[test] = 99.0
    a3._STATE["arrays"] = arrays
    a3._STATE["y"] = values
    inner = a3.fit({"kind": "inner", "fold": "1", "inner": 0, "seed": 5, "train": train, "val": val})
    assert len(inner["curve"]) == 5 and 0 <= inner["best_epoch"] <= 4
    refit = a3.fit({"kind": "refit", "fold": "1", "seed": 5, "train": train, "test": test, "epochs": 2})
    a3._STATE["y"] = scrambled
    again = a3.fit({"kind": "refit", "fold": "1", "seed": 5, "train": train, "test": test, "epochs": 2})
    np.testing.assert_array_equal(refit["test_pred"], again["test_pred"])
    assert a3.schedule(1) == pytest.approx(1 / 3) and a3.schedule(a3.MAX_EPOCHS) == pytest.approx(0, abs=1e-12)


def test_saved_predictions_never_hold_fold_0():
    path = lib.RUNS / COHORT / "predictions.csv"
    if not path.exists():
        pytest.skip("run run_cohort.py first")
    predictions = pd.read_csv(path, dtype={"fold": str})
    assert set(predictions["fold"]) == set(lib.SCORED_FOLDS)
    assert len(predictions) == 1504
