"""Hand-checked cases for the two pieces of time_features.py that are not library code."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location("time_features", Path(__file__).with_name("time_features.py"))
tf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tf)


def test_peak_features_by_hand():
    # months 2..6, month 4 cloudy (NaN); values 1, 3, -, 5, 2 -> peak 5 in month 5
    cube = pd.DataFrame([[1.0, 3.0, np.nan, 5.0, 2.0]], columns=[2, 3, 4, 5, 6], index=["f"])
    row = tf.peak_features(cube).loc["f"]
    assert row["peak"] == 5.0 and row["peak_month"] == 5.0
    # gap month 4 filled linearly with 4.0; trapezoid over 2..5 of [1, 3, 4, 5] = 2 + 3.5 + 4.5
    assert row["area_before_peak"] == pytest.approx(10.0)
    assert row["peak_window_mean"] == pytest.approx((5.0 + 2.0) / 2)   # clear months 5 and 6 (month 4 is cloudy)


def test_peak_in_first_clear_month_has_zero_area():
    cube = pd.DataFrame([[np.nan, 6.0, 1.0]], columns=[0, 1, 2], index=["f"])
    assert tf.peak_features(cube).loc["f", "area_before_peak"] == 0.0


def test_holm_matches_the_textbook():
    p = pd.Series({"a": 0.01, "b": 0.04, "c": 0.03})
    # sorted 0.01, 0.03, 0.04 -> 3*0.01, 2*0.03, 1*0.04 = 0.03, 0.06, 0.04 -> running max 0.03, 0.06, 0.06
    assert tf.holm(p).to_dict() == pytest.approx({"a": 0.03, "b": 0.06, "c": 0.06})
