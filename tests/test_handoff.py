"""Release safety: independent reconciliation, spatial leakage, and immutable outputs."""
import json

import numpy as np
import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.handoff import (
    COHORT,
    explicit_split,
    load_handoff,
    publish_release,
    read_raw,
    reconcile_labels,
)
from cropyield.data.labels import sha256
from cropyield.data.xy import FEATURES
from cropyield.eval.splits import new_village

RAW = ROOT / "data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson"
ROLES = {"0": "test", "1": "validation", "2": "train", "3": "train", "4": "train"}


@pytest.fixture(scope="module")
def raw_and_labels():
    raw, _ = read_raw(RAW)
    labels = pd.read_parquet(ROOT / "data/processed/labels_v1.parquet")
    return raw, reconcile_labels(raw, labels)


def test_independent_source_accounting_retains_zeros_and_rejects_three_conversions(raw_and_labels):
    raw, labels = raw_and_labels
    assert len(raw) == 2269 and len(labels) == 2266
    assert raw.screened_in.sum() == 2266
    assert raw.include_primary_rederived.sum() == labels.include_primary.sum() == 1880
    invalid = raw[raw.yield_conversion_mismatch]
    assert len(invalid) == 3
    np.testing.assert_allclose(invalid.source_yield_t_ha, invalid.expected_t_ha_from_dry_weight * 2)
    assert not invalid.screened_in.any()
    assert raw.loc[raw.include_primary_rederived, "is_zero"].sum() == 28


@pytest.mark.parametrize("column,value", [("lon", 0.0), ("yield_kg_ha", 99999),
                                         ("admin_unit", "wrong"), ("harvest_date", pd.Timestamp("2000-01-01"))])
def test_reconciliation_rejects_corruption_in_both_numeric_and_metadata_fields(raw_and_labels, column, value):
    raw, labels = raw_and_labels
    broken = labels.copy()
    broken.loc[0, column] = value
    with pytest.raises(ValueError, match="mismatch"):
        reconcile_labels(raw, broken)


def test_reconciliation_rejects_dropped_join_rows_and_changed_inclusion(raw_and_labels):
    raw, labels = raw_and_labels
    with pytest.raises(ValueError, match="IDs disagree"):
        reconcile_labels(raw, labels.iloc[1:])
    broken = labels.copy()
    broken.loc[0, "include_primary"] = not broken.loc[0, "include_primary"]
    with pytest.raises(ValueError, match="Inclusion"):
        reconcile_labels(raw, broken)


def test_unknown_management_is_not_silently_treated_as_rainfed(tmp_path):
    source = json.loads(RAW.read_text())
    maize = next(f for f in source["features"] if f["properties"]["Crop_Type"] == "Maize/Corn")
    maize["properties"]["Field_Irri"] = None
    path = tmp_path / "raw.json"
    path.write_text(json.dumps({"features": [maize]}))
    with pytest.raises(ValueError, match="Unknown irrigation_raw"):
        read_raw(path)


def test_explicit_splits_keep_existing_folds_and_historical_test_status(raw_and_labels):
    _, labels = raw_and_labels
    primary = labels[labels.include_primary]
    for family in ["s1_cc2km", "s2_region"]:
        source = pd.read_csv(ROOT / f"data/splits/{COHORT}__{family}.csv", dtype={"fold": str, "group_id": str})
        explicit, stats = explicit_split(source, primary, ROLES, family)
        expected = source.set_index("obs_id").fold.sort_index()
        pd.testing.assert_series_equal(explicit.set_index("obs_id").fold, expected)
        assert stats["test_status"] == "historical_previously_evaluated"
        assert stats["new_models_may_score_test"] is False
        if family == "s1_cc2km":
            assert stats["rows"] == {"train": 1128, "validation": 376, "test": 376}
            assert min(stats["minimum_distance_km"].values()) >= 2


def test_spatial_check_rejects_neighbours_even_when_group_ids_are_different():
    rows = pd.DataFrame({"obs_id": list("abcde"), "cohort": COHORT, "season_year": 2023,
                         "lat": 0., "lon": np.arange(5) * 0.1,
                         "cluster_2km": np.arange(5), "admin_unit": list("abcde")})
    split = new_village(rows)
    # Move one point beside another after assignment: groups look distinct, geometry exposes leakage.
    test_row = split.index[split.fold.eq("0")][0]
    val_row = split.index[split.fold.eq("1")][0]
    rows.loc[val_row, "lon"] = rows.loc[test_row, "lon"] + 0.00001
    with pytest.raises(ValueError, match="near-duplicate leakage"):
        explicit_split(split, rows, ROLES, "s1_cc2km")


def test_publication_is_idempotent_and_will_not_overwrite_a_changed_release(tmp_path):
    staged, output = tmp_path / "staged", tmp_path / "release"
    staged.mkdir()
    (staged / "value.txt").write_text("original")
    publish_release(staged, output)
    publish_release(staged, output)
    (staged / "value.txt").write_text("changed")
    with pytest.raises(ValueError, match="No files overwritten"):
        publish_release(staged, output)
    assert (output / "value.txt").read_text() == "original"


def test_loader_verifies_hashes_aligns_ids_and_never_includes_leakage_columns(tmp_path):
    frame = pd.DataFrame({"obs_id": ["b", "a", "c"], "yield_t_ha": [2., 1., 3.],
                          "dry_weight_kg": [8., 4., 12.], **{f: [2., 1., 3.] for f in FEATURES}})
    frame.to_parquet(tmp_path / "model_table.parquet", index=False)
    split = pd.DataFrame({"obs_id": ["a", "c", "b"], "partition": ["train", "test", "train"], "group_id": ["A", "C", "B"]})
    split.to_csv(tmp_path / "split_s1_cc2km.csv", index=False)
    manifest = {"outputs": {name: {"sha256": sha256(tmp_path / name)}
                             for name in ["model_table.parquet", "split_s1_cc2km.csv"]}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    x, y, groups = load_handoff(tmp_path)
    assert x.index.tolist() == y.index.tolist() == groups.index.tolist() == ["a", "b"]
    assert x.columns.tolist() == FEATURES and "dry_weight_kg" not in x
    assert y.tolist() == [1., 2.]
    with pytest.raises(ValueError, match="restricted"):
        load_handoff(tmp_path, partition="test")
    assert len(load_handoff(tmp_path, partition="test", allow_historical_test=True)[0]) == 1
    frame.to_parquet(tmp_path / "model_table.parquet", index=True)
    with pytest.raises(ValueError, match="hash mismatch"):
        load_handoff(tmp_path)
