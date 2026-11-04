"""Cloud policies preserve uncertainty and remove complete monthly aggregates."""
import numpy as np
import pandas as pd
import pytest
from rasterio.transform import rowcol

from cropyield.satellite.cloud_review import (
    BANDS,
    chip_grid,
    cloud_masks,
    derived_tables,
    policy,
    review_chip,
    write_once,
)


def point_example():
    row = {"lon": 33.55840171875, "lat": -13.1221575, "geometry_wkt": None,
           "crs": "EPSG:32736", "field_pixels": 1, "aoi_pixels": 1}
    grid, halo = chip_grid(row["lon"], row["lat"])
    from rasterio.warp import transform
    x, y = transform("EPSG:4326", grid["crs"], [row["lon"]], [row["lat"]])
    r, c = rowcol(grid["transform"], x[0], y[0])
    return row, grid, halo, r, c


def test_buffer_is_physical_and_does_not_treat_water_as_cloud():
    scl = np.full((21, 21), 4, dtype="uint8")
    scl[10, 10] = 9
    scl[1, 1] = 6
    keep, cloud, unknown = cloud_masks(scl, buffer_m=60)
    assert cloud[10, 16] and not cloud[10, 17]
    assert not keep[1, 1] and not cloud[1, 1]
    assert not unknown.any()
    assert keep[20, 20]


def test_unknown_buffer_never_passes_as_clear():
    scl = np.full((21, 21), 5, dtype="uint8")
    scl[10, 10] = 0
    keep, cloud, unknown = cloud_masks(scl, buffer_m=20)
    assert unknown[10, 12] and not keep[10, 12]
    assert not cloud.any()


def test_review_point_and_nearby_cloud_on_reconstructed_original_grid():
    row, grid, halo, r, c = point_example()
    scl = np.full((grid["height"], grid["width"]), 5, dtype="uint8")
    clear, masks = review_chip(scl, grid, halo, row)
    assert clear["assessment"] == "verified_scl" and clear["keep_whole_month"]
    assert masks["field_mask"].shape == (64, 64) and masks["field_mask"].sum() == 1
    scl[r, c + 6] = 3
    rejected, _ = review_chip(scl, grid, halo, row)
    assert rejected["assessment"] == "verified_scl" and not rejected["keep_whole_month"]
    assert rejected["direct_cloud_shadow_aoi_pixels"] == 0
    assert rejected["buffered_cloud_shadow_aoi_pixels"] == 1
    scl[r, c + 6] = 0
    unknown, _ = review_chip(scl, grid, halo, row)
    assert unknown["assessment"] == "unverified_scl" and not unknown["keep_whole_month"]


def test_geometry_reconstruction_mismatch_stops_review():
    row, grid, halo, _, _ = point_example()
    row["field_pixels"] = 2
    with pytest.raises(ValueError, match="field-pixel count"):
        review_chip(np.full((grid["height"], grid["width"]), 4), grid, halo, row)


def test_missing_cloudy_and_unreviewed_months_become_null_not_zero():
    monthly = pd.DataFrame({"obs_id": ["f"] * 4, "month": ["2023-01", "2023-02", "2023-03", "2023-04"],
                            **{b: [0.2, 0.3, 0.4, np.nan] for b in BANDS},
                            "field_pixels": [1, 1, 1, 0], "missing": [False, False, False, True]})
    monthly["b08"] = [0.6, 0.9, 0.8, np.nan]
    reviews = pd.DataFrame({"obs_id": ["f", "f"], "month": ["2023-01", "2023-02"],
                            "item_id": ["scene1", "scene2"], "assessment": ["verified_scl", "verified_scl"],
                            "keep_whole_month": [True, False]})
    selected = pd.DataFrame({"obs_id": ["f"], "cohort": ["malawi_2023"], "country_iso3": ["MWI"],
                             "include_primary": [True]})
    original = monthly.copy(deep=True)
    clean, indices, season, coverage = derived_tables(monthly, reviews, selected)
    pd.testing.assert_frame_equal(monthly, original)
    assert clean.loc[1:, list(BANDS)].isna().all().all()
    assert clean.missing.tolist() == [False, True, True, True]
    assert clean.review_state.tolist() == ["verified_scl", "verified_scl", "unverified_not_reviewed", "originally_missing"]
    assert indices.ndvi.iloc[0] == pytest.approx(0.5)
    assert season.ndvi_season_mean.iloc[0] == pytest.approx(0.5)
    assert coverage.retained_months.iloc[0] == 1 and coverage.original_months_with_data.iloc[0] == 3
    assert not coverage.retains_four_months.iloc[0]


def test_all_months_rejected_have_null_season_values():
    monthly = pd.DataFrame({"obs_id": ["f"], "month": ["2023-01"],
                            **{b: [0.2] for b in BANDS}, "field_pixels": [1], "missing": [False]})
    reviews = pd.DataFrame({"obs_id": ["f"], "month": ["2023-01"], "item_id": ["s"],
                            "assessment": ["unverified_failure"], "keep_whole_month": [False]})
    selected = pd.DataFrame({"obs_id": ["f"], "cohort": ["malawi_2023"], "country_iso3": ["MWI"],
                             "include_primary": [True]})
    _, _, season, _ = derived_tables(monthly, reviews, selected)
    assert season.filter(regex="season_(max|mean)").isna().all().all()


def test_cache_never_overwrites_existing_file(tmp_path):
    path = tmp_path / "entry"
    write_once(path, b"original")
    with pytest.raises(FileExistsError):
        write_once(path, b"replacement")
    assert path.read_bytes() == b"original"


@pytest.mark.parametrize("value", [-1, 301, float("nan")])
def test_invalid_buffer_rejected(value):
    with pytest.raises(ValueError):
        policy(value)


def scene_fixture(tmp_path, monkeypatch, acquisition="2023-01-01"):
    """A local native 20 m SCL asset exercises the same reader/cache as the network."""
    import json

    import rasterio

    import cropyield.satellite.cloud_review as module
    row, grid, _, _, _ = point_example()
    source = tmp_path / "SCL.tif"
    with rasterio.open(source, "w", driver="GTiff", width=grid["width"] // 2,
                       height=grid["height"] // 2, count=1, dtype="uint8", crs=grid["crs"],
                       transform=grid["transform"] @ rasterio.Affine.scale(2), nodata=0) as dst:
        dst.write(np.full((grid["height"] // 2, grid["width"] // 2), 5, dtype="uint8"), 1)
    item = {"properties": {"datetime": acquisition + "T10:00:00Z"}, "assets": {"scl": {"href": str(source)}}}
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"item": item}))
    monkeypatch.setattr(module, "get_metadata", lambda *args: ({"item": item}, metadata))
    row.update(obs_id="f", item_id="scene", month="2023-01", acquired=pd.Timestamp("2023-01-01"),
               cohort="malawi_2023", country_iso3="MWI", include_primary=True, season_year=2023,
               geometry_wkt=np.nan)
    return module, pd.DataFrame([row]), metadata


def test_scene_cache_is_reused_and_metadata_changes_rejected(tmp_path, monkeypatch):
    module, rows, metadata = scene_fixture(tmp_path, monkeypatch)
    output, cached = module.scene_job("scene", rows, tmp_path / "cache", policy())
    assert not cached and output[0]["keep_whole_month"]
    again, cached = module.scene_job("scene", rows, tmp_path / "cache", policy())
    assert cached and again == output
    metadata.write_text("changed metadata")
    with pytest.raises(ValueError, match="Corrupt cloud-review cache"):
        module.scene_job("scene", rows, tmp_path / "cache", policy())


def test_same_month_wrong_acquisition_day_is_rejected(tmp_path, monkeypatch):
    module, rows, _ = scene_fixture(tmp_path, monkeypatch, acquisition="2023-01-02")
    with pytest.raises(ValueError, match="acquisition date"):
        module.scene_job("scene", rows, tmp_path / "cache", policy())


def test_completed_mask_without_manifest_recovers_without_overwrite(tmp_path, monkeypatch):
    module, rows, _ = scene_fixture(tmp_path, monkeypatch)
    output, _ = module.scene_job("scene", rows, tmp_path / "cache", policy())
    from pathlib import Path
    mask = Path(output[0]["mask_path"])
    original_hash = module.sha256(mask)
    (mask.parent / "review.json").unlink()
    resumed, cached = module.scene_job("scene", rows, tmp_path / "cache", policy())
    assert not cached and resumed == output and module.sha256(mask) == original_hash
