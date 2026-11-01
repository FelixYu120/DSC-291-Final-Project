"""Frozen splits: fold assignment, the 2 km guarantee, the temporal split, and the committed files."""
import json

import numpy as np
import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.labels import sha256
from cropyield.eval.splits import (assign_folds, check_split, connected_clusters, nearest_km, new_region, new_season,
                                   new_village, random_diagnostic)

KM_PER_DEGREE = 111.19


def rows_on_a_line(spacing_km: float, n: int = 40) -> pd.DataFrame:
    """Fields along the equator with a growing year and two districts."""
    return pd.DataFrame({"obs_id": [f"f{i}" for i in range(n)], "cohort": "test",
                         "season_year": [2019 if i % 2 else 2020 for i in range(n)],
                         "cluster_2km": range(n), "lat": 0.0, "lon": np.arange(n) * spacing_km / KM_PER_DEGREE,
                         "admin_unit": ["west" if i < n / 2 else "east" for i in range(n)]})


def test_clusters_join_fields_within_the_distance_only():
    lon = np.array([0.0, 1.5, 4.0]) / KM_PER_DEGREE
    clusters = connected_clusters(np.zeros(3), lon, 2.0)
    assert clusters[0] == clusters[1] != clusters[2]


def test_clusters_chain_through_a_middle_field():
    lon = np.array([0.0, 1.9, 3.8]) / KM_PER_DEGREE
    assert len(set(connected_clusters(np.zeros(3), lon, 2.0))) == 1


def test_assign_folds_is_seeded_balanced_and_keeps_groups_whole():
    groups = np.repeat(np.arange(30), 3).astype(str)
    first, second = assign_folds(groups), assign_folds(groups)
    assert (first == second).all()
    assert pd.Series(first).groupby(groups).nunique().max() == 1
    assert sorted(pd.Series(first).value_counts()) == [18] * 5
    assert not (assign_folds(groups, seed=1) == first).all()


def test_new_village_keeps_test_fields_two_km_from_training():
    rows = rows_on_a_line(1.0, 30).iloc[list(range(10)) + list(range(20, 30))].reset_index(drop=True)
    split = new_village(rows)
    assert check_split(split, rows) == []
    for fold in split["fold"].unique():
        test = (split["fold"] == fold).to_numpy()
        assert nearest_km(rows["lat"].to_numpy(), rows["lon"].to_numpy(), test, ~test).min() >= 2.0


def test_check_split_reports_a_group_in_two_folds_and_a_missing_row():
    rows = rows_on_a_line(5.0)
    split = new_region(rows, "admin_unit")
    broken = split.copy()
    broken.loc[broken.index[0], "fold"] = "9"
    assert any("two folds" in problem for problem in check_split(broken, rows))
    assert any("exactly the eligible" in problem for problem in check_split(split.iloc[1:], rows))


def test_check_split_reports_a_test_field_next_to_training():
    rows = rows_on_a_line(1.0, 20)
    split = random_diagnostic(rows).assign(family="s1_cc2km")
    assert any("within 2 km" in problem for problem in check_split(split, rows))


def test_new_season_trains_on_one_year_and_marks_new_regions():
    rows = rows_on_a_line(5.0)
    rows.loc[rows["admin_unit"] == "east", "season_year"] = 2020
    split = new_season(rows, 2019, 2020)
    first = split[split["repeat"] == 0]
    assert set(first.loc[first["fold"] == "train", "season_year"]) == {2019}
    assert set(first.loc[first["fold"] == "test", "season_year"]) == {2020}
    assert set(first.loc[first["fold"] == "test", "test_subset"]) == {"seen_region", "new_region"}
    second = split[split["repeat"] == 1]
    assert set(second.loc[second["fold"] == "train", "season_year"]) == {2020}


def test_committed_split_files_match_their_manifest_and_the_labels():
    manifest_path = ROOT / "data" / "splits" / "manifest.json"
    if not manifest_path.exists():
        pytest.skip("splits not built")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["labels_sha256"] == sha256(ROOT / "data" / "processed" / "labels_v1.parquet")
    labels = pd.read_parquet(ROOT / "data" / "processed" / "labels_v1.parquet")
    for name, entry in manifest["files"].items():
        path = ROOT / "data" / "splits" / name
        assert sha256(path) == entry["sha256"], name
        split = pd.read_csv(path, dtype={"group_id": str, "fold": str}, keep_default_na=False)
        cohort = name.split("__")[0]
        rows = labels[(labels["cohort"] == cohort) & labels["include_primary"]]
        assert check_split(split, rows) == [], name
