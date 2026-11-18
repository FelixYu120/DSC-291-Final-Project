"""Checks of the footprint code: window math by hand, and the 1-pixel arms give today's v2 numbers again.

    python -m pytest -q experiments/footprint/test_footprint.py

The data tests need data/v2/cropyield.duckdb, the v2 chips and windows.parquet (run windows.py first).
"""
import importlib.util
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import windows as W


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


fp = module("footprint", HERE / "footprint.py")
REPO = fp.REPO
LACUNA = "zimbabwe_lacuna_2022_2023"
NEEDS_DATA = pytest.mark.skipif(not (W.DATABASE.exists() and W.OUT.exists()),
                                reason="needs data/v2/cropyield.duckdb and experiments/footprint/windows.parquet")


# ---------- hand-checked cases ---------------------------------------------------------------------------------------

def block_with_clouds():
    rng = np.random.default_rng(0)
    reflectance = rng.uniform(0.01, 0.5, (10, 7, 7)).astype("float32")
    valid = np.ones((7, 7), dtype=bool)
    valid[0, :] = False          # a cloud along the top row
    valid[2, 2] = False          # one shadow pixel inside the 3 x 3 window
    reflectance[:, ~valid] = np.nan
    return reflectance, valid


def test_window_stats_by_hand():
    reflectance, valid = block_with_clouds()
    rows = {row["w"]: row for row in W.window_stats(reflectance, valid)}
    # w = 1 is the centre pixel, as monthly_series reads it today
    assert rows[1]["n_valid"] == 1 and rows[1]["b08"] == float(reflectance[6, 3, 3]) and rows[1]["sd_b08"] == 0.0
    # w = 3: rows and columns 2..4 without the shadow pixel -> 8 clear pixels
    block = reflectance[:, 2:5, 2:5][:, valid[2:5, 2:5]]
    assert rows[3]["n_valid"] == 8 and rows[3]["n_window"] == 9
    red, nir = np.median(block[2]), np.median(block[6])           # float32 medians
    assert rows[3]["b04"] == float(red) and rows[3]["b08"] == float(nir)
    assert rows[3]["ndvi"] == pytest.approx((float(nir) - float(red)) / (float(nir) + float(red)), rel=1e-12)
    assert rows[3]["sd_b04"] == pytest.approx(float(block[2].astype("float64").std()), rel=1e-12)
    ndvi = (block[6].astype("float64") - block[2]) / (block[6].astype("float64") + block[2])
    assert rows[3]["sd_ndvi"] == pytest.approx(float(ndvi.std()), rel=1e-12)
    # w = 5 and w = 7: the cloudy top row is outside the 5 x 5 window, inside the 7 x 7 window
    assert rows[5]["n_valid"] == 24 and rows[7]["n_valid"] == 49 - 7 - 1


def test_a_cloudy_point_pixel_stops():
    reflectance, valid = block_with_clouds()
    valid[3, 3] = False
    with pytest.raises(ValueError, match="point pixel"):
        W.window_stats(reflectance, valid)


def test_curve_fills_gaps_like_time_features():
    frame = pd.DataFrame({"obs_id": ["a", "a", "b"], "k": [2, 4, 3], "b08": [0.2, 0.4, 0.3]})
    out = fp.curve(frame, ["b08"], pd.Index(["a", "b"]), [2, 3, 4])
    assert out.loc["a"].tolist() == pytest.approx([0.2, 0.3, 0.4])      # linear between clear months
    assert out.loc["b"].tolist() == pytest.approx([0.3, 0.3, 0.3])      # edges take the nearest clear month


def test_holm_matches_the_textbook():
    p = pd.Series({"a": 0.01, "b": 0.04, "c": 0.03})
    assert fp.holm(p).to_dict() == pytest.approx({"a": 0.03, "b": 0.06, "c": 0.06})


def test_pairs_cover_the_plan():
    pairs = fp.pairs_of()
    kinds = pd.Series([kind for _, _, kind in pairs]).value_counts().to_dict()
    assert kinds == {"window_vs_1px": 12, "sd_vs_window": 6, "vs_R1": 14}


# ---------- data: the windows file is the chips, and 1 pixel is today -------------------------------------------------

@NEEDS_DATA
def test_windows_parquet_matches_the_chips():
    table = pd.read_parquet(W.OUT)
    rng = np.random.default_rng(20261029)
    for cohort in W.COHORTS:
        todo = W.jobs(cohort)
        for i in rng.choice(len(todo), 15, replace=False):
            fresh = pd.DataFrame(W.record_rows(todo[i])).set_index(["month", "w"]).sort_index()
            saved = table[table.obs_id == todo[i][0]].set_index(["month", "w"]).sort_index()[fresh.columns]
            pd.testing.assert_frame_equal(fresh, saved, check_exact=True)


@NEEDS_DATA
def test_one_pixel_equals_the_database():
    table = pd.read_parquet(W.OUT)
    one = table[table.w == 1].set_index(["obs_id", "month"])
    with duckdb.connect(str(W.DATABASE), read_only=True) as con:
        db = con.execute("""SELECT b.*, v.ndvi, v.gcvi, v.mtci, v.ndvi705, v.ndvi740, c.item_id
                            FROM monthly_bands b JOIN vegetation_indices v USING (obs_id, month)
                            JOIN coverage c USING (obs_id, month)
                            JOIN master m USING (obs_id)
                            WHERE m.cohort IN ('zimbabwe_lacuna_2022_2023', 'zimbabwe_2024')
                              AND m.include_primary AND m.months_with_data >= 4
                              AND c.state = 'clear'""").df().set_index(["obs_id", "month"])
    assert set(one.index) == set(db.index)                     # the same clear months, no month more or less
    db = db.loc[one.index]
    assert (one.item_id == db.item_id).all()                   # the same photo in every month
    for column in list(W.BAND_COLUMNS) + list(W.INDICES):
        assert np.nanmax(np.abs(one[column].to_numpy() - db[column].to_numpy())) < 1e-12, column
    assert (one.n_valid == 1).all() and (one.sd_b08 == 0).all()


@NEEDS_DATA
@pytest.mark.parametrize("cohort", list(fp.COHORTS))
def test_one_pixel_arms_equal_todays_features(cohort):
    expected = fp.COHORTS[cohort][0]
    labels = pd.read_parquet(fp.V2 / "processed" / fp.LABELS_FILE).set_index("obs_id")
    X_a1, y, _, win = fp.load(cohort, expected, labels, pd.read_parquet(W.OUT))
    arms = fp.arms_for(win, y.index)
    assert np.abs(arms["A1-1"].to_numpy() - X_a1.to_numpy()).max() < 1e-9          # today's A1 (load_xy)
    tf = module("time_features", REPO / "experiments" / "time_features" / "time_features.py")
    _, y_tf, _, monthly = tf.load(cohort, expected, labels)
    variants, _ = tf.build(cohort, X_a1, y_tf, monthly, tf.COHORTS[cohort][1])
    m2 = variants["M2 monthly band curve"]
    assert list(arms["X1-1"].columns) == list(m2.columns)
    assert np.abs(arms["X1-1"].to_numpy() - m2.to_numpy()).max() < 1e-12           # today's monthly band curve


@NEEDS_DATA
def test_one_pixel_gives_the_v2_numbers_again():
    """Lacuna: R1, A1-1 and X1-1 scores, and the A1 minus R1 intervals, equal the v2 tables."""
    expected = fp.COHORTS[LACUNA][0]
    labels = pd.read_parquet(fp.V2 / "processed" / fp.LABELS_FILE).set_index("obs_id")
    _, y_series, fields, win = fp.load(LACUNA, expected, labels, pd.read_parquet(W.OUT))
    arms = fp.arms_for(win, y_series.index)
    y = y_series.to_numpy()
    tested = fields["fold"].isin(fp.SCORED).to_numpy()
    assert tested.sum() == 1504 and fields.loc[tested, "group_id"].nunique() == 232    # the v2 table's counts
    sub, cy = fields[tested], fp.cluster_years_of(fields[tested])
    predicted = {"R1": fp.r1_out_of_fold(y, fields)[tested]}
    for arm in ("A1-1", "X1-1"):
        p = fp.out_of_fold(arms[arm].to_numpy(), y, fields)
        assert np.isnan(p[~tested]).all()                                            # fold 0 is never predicted
        predicted[arm] = p[tested]
    ref = fp.references(LACUNA)
    assert ref["A1-1"]["source"] == "results/v2/baseline_scores.csv"
    for arm in ("R1", "A1-1", "X1-1"):
        score = fp.arm_score(y[tested], predicted[arm], cy)
        for metric in ("rmse", "r2", "rank_inside_clusters"):
            assert score[metric] == pytest.approx(ref[arm][metric], abs=1e-6), (arm, metric)
    assert fp.arm_score(y[tested], predicted["A1-1"], cy)["rmse"] == pytest.approx(1.785, abs=5e-4)
    # the paired bootstrap gives the step 8 intervals: A1 minus R1, RMSE and rank
    pair = {row["metric"]: row for row in fp.Draws(y[tested], sub).pair(predicted["A1-1"], predicted["R1"])}
    base = pd.read_csv(REPO / "results" / "v2" / "baseline_scores.csv")
    base = base[(base.cohort == LACUNA) & (base.arm == "A1")].set_index("metric")
    for ours, theirs in (("rmse", "rmse_minus_R1"), ("rank", "rank_minus_R1")):
        for a, b in (("diff", "value"), ("lo", "ci_low"), ("hi", "ci_high")):
            assert pair[ours][a] == pytest.approx(base.loc[theirs, b], abs=1e-6), (ours, a)


@NEEDS_DATA
def test_saved_predictions_never_score_fold_0():
    path = HERE / "predictions.csv"
    if not path.exists():
        pytest.skip("footprint.py has not run yet")
    saved = pd.read_csv(path, dtype={"fold": str})
    assert set(saved.fold) == set(fp.SCORED)
