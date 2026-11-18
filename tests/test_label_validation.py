"""Data validation must fail visibly when source links or required measurements disappear."""
import numpy as np
import pandas as pd
import pytest

from cropyield.data import labels as module


@pytest.fixture
def labels():
    return pd.read_parquet(module.LABELS_PATH)


@pytest.mark.parametrize("column,value,expected", [
    ("obs_id", "  ", "obs_id"),
    ("source_id", None, "source_id"),
    ("lat", np.inf, "coordinates"),
    ("lat", 91.0, "coordinates"),
    ("lon", -181.0, "coordinates"),
    ("lon", np.nan, "coordinates"),
    ("yield_definition", None, "missing yield_definition"),
    ("cut_area_m2", np.inf, "cut_area_m2 must be finite"),
    ("n_cuts", 0, "n_cuts must be finite"),
    ("exclusion_reason", "unexpected", "disagrees with exclusion_reason"),
])
def test_label_corruption_is_reported_without_crashing(labels, column, value, expected):
    row = labels.index[labels["include_primary"]][0]
    labels.loc[row, column] = value
    assert any(expected in problem for problem in module.check_labels(labels))


def test_missing_inclusion_is_reported(labels):
    labels["include_primary"] = labels["include_primary"].astype("boolean")
    labels.loc[0, "include_primary"] = pd.NA
    assert any("non-null boolean" in problem for problem in module.check_labels(labels))


@pytest.mark.parametrize("column,expected", [("lat", "coordinates"), ("yield_kg_ha", "yield outside")])
def test_nullable_missing_values_cannot_pass_all_reduction(labels, column, expected):
    labels[column] = labels[column].astype("Float64")
    row = labels.index[labels["include_primary"]][0]
    labels.loc[row, column] = pd.NA
    assert any(expected in problem for problem in module.check_labels(labels))


def test_missing_schema_is_reported(labels):
    assert "missing required columns" in module.check_labels(labels.drop(columns="lon"))[0]


@pytest.fixture
def raw_case(tmp_path, monkeypatch):
    """Small consistent source tables and real file hashes, with no network or workbook read."""
    labels = pd.DataFrame([
        {"cohort": "kenya_oaf_2019_2020", "source_row": 2, "source_id": "k1", "yield_kg_ha": 1000.,
         "lat": 0.5, "lon": 34.5, "admin_unit": "district", "cut1_kg_ha": np.nan, "cut2_kg_ha": np.nan},
        {"cohort": "zimbabwe_lacuna_2022_2023", "source_row": 1, "source_id": "z1", "yield_kg_ha": 2000.,
         "lat": -18., "lon": 30., "admin_unit": "region", "cut1_kg_ha": np.nan, "cut2_kg_ha": np.nan},
        {"cohort": "malawi_2023", "source_row": 1, "source_id": "m1", "yield_kg_ha": 3000.,
         "lat": -13., "lon": 33., "admin_unit": None, "cut1_kg_ha": 3000., "cut2_kg_ha": 4000.},
        {"cohort": "malawi_2022", "source_row": 1, "source_id": "m22", "yield_kg_ha": 1500.,
         "lat": -12., "lon": 33.5, "admin_unit": None, "cut1_kg_ha": np.nan, "cut2_kg_ha": np.nan},
    ])
    oaf = pd.DataFrame([{"source_row": 2, "unique_id": "k1", "yield_kg_ph": 1000.,
                         "yield_kg_pa": 1000 * module.ACRE_HA, "field_latitude": 0.5, "field_longitude": 34.5}])
    lacuna = pd.DataFrame([{"source_id": "z1", "raw_yield_t_ha": 2., "raw_dry_kg": 8.,
                            "raw_lat": -18., "raw_lon": 30.}])
    malawi = pd.DataFrame([{"source_id": "m1", "cc_ey_t": 3., "subc_ey_t": 4.}])
    monkeypatch.setattr(module, "malawi_2023_raw", lambda: malawi)
    # Data v2 also checks Malawi 2022 (AVG_YLD in t/ha) against its shapefile.
    monkeypatch.setattr(module, "malawi_2022_raw", lambda: pd.DataFrame([{"source_id": "m22", "AVG_YLD": 1.5}]))
    monkeypatch.setattr(module, "RAW_DIR", tmp_path)
    entries = []
    for name in ("OAF_WORKBOOK", "LACUNA_GEOJSON", "MALAWI_2023_ZIP", "MALAWI_2022_ZIP"):
        path = tmp_path / name
        path.write_text(name)
        monkeypatch.setattr(module, name, path)
        entries.append({"path": name, "sha256": module.sha256(path)})
    monkeypatch.setattr(module, "manifest_entries", lambda: entries)
    return labels, oaf, lacuna, malawi, entries


def test_valid_raw_sources_pass(raw_case):
    labels, oaf, lacuna, *_ = raw_case
    assert module.check_against_raw(labels, oaf, lacuna) == []


@pytest.mark.parametrize("source", ["kenya", "lacuna", "malawi"])
def test_missing_provider_match_is_not_silently_dropped(raw_case, source):
    labels, oaf, lacuna, malawi, _ = raw_case
    frame = {"kenya": oaf, "lacuna": lacuna, "malawi": malawi}[source]
    frame.drop(frame.index, inplace=True)
    assert any("no matching provider row" in p for p in module.check_against_raw(labels, oaf, lacuna))


@pytest.mark.parametrize("source,column", [("kenya", "field_longitude"), ("lacuna", "raw_lon")])
def test_longitude_is_checked_against_source(raw_case, source, column):
    labels, oaf, lacuna, *_ = raw_case
    frame = oaf if source == "kenya" else lacuna
    frame.loc[0, column] += 0.01
    assert any("longitude" in p for p in module.check_against_raw(labels, oaf, lacuna))


@pytest.mark.parametrize("value", [np.nan, np.inf])
def test_nonfinite_target_does_not_compare_equal(raw_case, value):
    labels, oaf, lacuna, *_ = raw_case
    labels.loc[0, "yield_kg_ha"] = value
    assert any("Kenya: yield_kg_ha" in p for p in module.check_against_raw(labels, oaf, lacuna))


def test_nullable_missing_source_yield_is_reported(raw_case):
    labels, oaf, lacuna, malawi, _ = raw_case
    malawi["cc_ey_t"] = pd.Series([pd.NA], dtype="Float64")
    assert any("differs from cc_ey_t" in p for p in module.check_against_raw(labels, oaf, lacuna))


def test_duplicate_raw_key_is_reported(raw_case):
    labels, oaf, lacuna, *_ = raw_case
    oaf = pd.concat([oaf, oaf], ignore_index=True)
    assert any("key source_row is missing or duplicated" in p for p in module.check_against_raw(labels, oaf, lacuna))


def test_optional_nested_cut_missing_on_both_sides_is_valid(raw_case):
    labels, oaf, lacuna, malawi, _ = raw_case
    labels.loc[2, "cut2_kg_ha"] = np.nan
    malawi.loc[0, "subc_ey_t"] = np.nan
    assert module.check_against_raw(labels, oaf, lacuna) == []


def test_lost_nested_cut_is_reported(raw_case):
    labels, oaf, lacuna, *_ = raw_case
    labels.loc[2, "cut2_kg_ha"] = np.nan
    assert any("nested cut differs" in p for p in module.check_against_raw(labels, oaf, lacuna))


def test_missing_manifest_hash_is_reported(raw_case):
    labels, oaf, lacuna, _, entries = raw_case
    entries.pop()
    assert any("no SHA-256" in p for p in module.check_against_raw(labels, oaf, lacuna))


def test_conflicting_manifest_hashes_are_reported(raw_case):
    labels, oaf, lacuna, _, entries = raw_case
    entries.append({**entries[0], "sha256": "0" * 64})
    assert any("conflicting SHA-256" in p for p in module.check_against_raw(labels, oaf, lacuna))
