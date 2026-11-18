"""Predicted boundary candidates are review evidence, never replacement field truth."""
from types import SimpleNamespace

import pandas as pd
import pytest
from shapely.geometry import box

from cropyield.data.boundary_candidates import (
    candidate_evidence,
    describe_candidates,
    reference_rows,
)


def test_containing_predictions_remain_ambiguous_and_rank_independent_of_score():
    row = SimpleNamespace(obs_id="k1", lat=0.1, lon=34., zone=36, season_year=2019, geometry_wkt=None)
    polygon = box(33.9999, 0.0999, 34.0001, 0.1001)
    candidates = pd.DataFrame({"id": ["b", "a"], "collection": ["ftw"] * 2,
                               "geometry": [polygon.wkb] * 2, "score": [0.99, 0.01]})
    evidence = candidate_evidence(row, candidates)
    assert [item["candidate_id"] for item in evidence] == ["a", "b"]
    assert describe_candidates(evidence)["status"] == "ambiguous_multiple_candidates"
    assert all(item["malawi_polygon_iou"] is None for item in evidence)


def test_known_polygon_overlap_is_measured_without_replacement():
    polygon = box(32.9999, -13.0001, 33.0001, -12.9999)
    row = SimpleNamespace(obs_id="m1", lat=-13., lon=33., zone=36, season_year=2023, geometry_wkt=polygon.wkt)
    candidates = pd.DataFrame({"id": ["a"], "collection": ["ftw"], "geometry": [polygon.wkb], "score": [0.1]})
    evidence = candidate_evidence(row, candidates)
    assert evidence[0]["malawi_polygon_iou"] == pytest.approx(1.)
    assert "no_coordinate_or_boundary_replacement" in describe_candidates(evidence)["decision"]


def test_missing_match_is_unknown_not_proof_point_is_wrong():
    assert describe_candidates([])["status"] == "no_candidate_unknown"


def test_selection_keeps_only_repeated_kenya_points_and_primary_malawi():
    labels = pd.DataFrame({"cohort": ["kenya_oaf_2019_2020"] * 3 + ["malawi_2023"] * 2,
                           "obs_id": ["k1", "k2", "k3", "m1", "m2"], "season_year": [2019] * 3 + [2023] * 2,
                           "lat": [0., 0., 1., -13., -13.1], "lon": [34., 34., 34., 33., 33.],
                           "include_primary": [True, True, True, True, False]})
    assert set(reference_rows(labels, None).obs_id) == {"k1", "k2", "m1"}
