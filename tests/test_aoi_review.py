"""Proxy areas must be physically sized, explicitly provisional, and evaluated fairly."""
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box
from shapely.ops import transform

from cropyield.data.aoi_review import (
    candidate_features,
    metric_transforms,
    overlap_metrics,
    summarize_validation,
    support_circle,
)


def test_circle_uses_metres_not_degrees():
    forward, _, _ = metric_transforms(34.7, 0.2)
    circle = transform(forward, support_circle(34.7, 0.2, 20))
    assert circle.area == pytest.approx(np.pi * 20 ** 2, rel=.01)
    assert circle.centroid.x == pytest.approx(forward(34.7, .2)[0], abs=.01)


@pytest.mark.parametrize("radius", [0, -1, float("nan"), float("inf")])
def test_invalid_radius_rejected(radius):
    with pytest.raises(ValueError):
        support_circle(34, 0, radius)


def test_overlap_quantifies_background_inclusion_and_field_coverage():
    result = overlap_metrics(box(0, 0, 2, 2), box(0, 0, 1, 2))
    assert result["fraction_support_inside_field"] == .5
    assert result["fraction_field_covered"] == 1
    assert result["intersection_over_union"] == .5


def test_candidates_never_infer_boundary_or_use_reported_area():
    labels = pd.DataFrame({"obs_id": ["test:1"], "cohort": ["kenya_oaf_2019_2020"], "include_primary": [True],
                           "geometry_type": ["Point"], "country_iso3": ["KEN"], "lat": [.2], "lon": [34.7],
                           "season_year": [2019], "field_area_ha": [999]})
    original = labels.copy(deep=True)
    features = list(candidate_features(labels))
    assert len(features) == 3
    for _, _, feature in features:
        assert feature["properties"]["status"] == "unvalidated_proxy_not_field_boundary"
        assert not feature["properties"]["reported_area_used"]
        assert feature["properties"]["original_longitude"] == 34.7
    pd.testing.assert_frame_equal(original, labels)


def test_summary_averages_directions_per_field_before_median():
    metrics = pd.DataFrame({"obs_id": ["a"] * 4 + ["b"], "radius_m": [10] * 5,
                            "synthetic_offset_m": [10] * 5, "fraction_support_inside_field": [0, 0, 0, 0, 1],
                            "fraction_field_covered": [.2] * 5, "intersection_over_union": [.1] * 5,
                            "shifted_point_inside_field": [False] * 4 + [True]})
    summary = summarize_validation(metrics)[0]
    assert summary["fields"] == 2
    assert summary["median_fraction_support_inside_field"] == .5
    assert summary["mean_share_directions_point_inside"] == .5
