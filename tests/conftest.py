"""Synthetic record folder in the exact layout scripts/download_sentinel2.py writes.

No imagery is committed, so tests build a tiny 6 x 6 pixel chip with two accepted scenes.
"""
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
NODATA = -9999.0
SIZE = 6
GRID = {"crs": "EPSG:32736", "transform": from_origin(553_000, 8_527_000, 10, 10), "width": SIZE, "height": SIZE}
# Reflectance per band inside the AOI; outside the AOI every band is 0.9 so a leaking mask shows.
AOI_REFLECTANCE = {"B02": 0.03, "B03": 0.06, "B04": 0.05, "B05": 0.09, "B06": 0.18, "B07": 0.22,
                   "B08": 0.25, "B8A": 0.27, "B11": 0.15, "B12": 0.08}
# First pilot record of the Malawi 2023 cohort (data/audit/malawi_2023_screened_candidates.csv row 1).
RECORD = {"dataset": "malawi_2023", "source_id": "506ae8b2-d085-4eeb-b807-765e03925c71", "source_row": "1",
          "year": 2023, "country": "malawi", "longitude": 33.3837, "latitude": -13.3171,
          "yield_kg_ha": 2950.0, "start_date": "2023-03-01", "end_date": "2023-06-30",
          "window_basis": "user_override"}


def write_tif(path, array, nodata, descriptions):
    if array.ndim == 2:
        array = array[np.newaxis]
    with rasterio.open(path, "w", driver="GTiff", **GRID, count=len(array), dtype=array.dtype,
                       nodata=nodata, compress="deflate") as out:
        out.write(array)
        out.descriptions = tuple(descriptions)


def write_scene(record_dir, item_id, acquired, aoi, invalid_aoi_pixels=0, cloud_cover=12.5):
    """One scene: AOI pixels hold AOI_REFLECTANCE, the rest 0.9; some AOI pixels can be invalid."""
    scene_dir = record_dir / item_id
    scene_dir.mkdir()
    reflectance = np.full((len(BANDS), SIZE, SIZE), 0.9, dtype="float32")
    for i, band in enumerate(BANDS):
        reflectance[i][aoi] = AOI_REFLECTANCE[band]
    valid = np.ones((SIZE, SIZE), dtype=bool)
    rows, cols = np.nonzero(aoi)
    for k in range(invalid_aoi_pixels):
        valid[rows[k], cols[k]] = False
    reflectance[:, ~valid] = NODATA
    scl = np.where(valid, 4, 9).astype("uint8")  # 4 vegetation, 9 cloud high probability
    write_tif(scene_dir / "reflectance.tif", reflectance, NODATA, BANDS)
    write_tif(scene_dir / "scl.tif", scl, 0, ["SCL"])
    write_tif(scene_dir / "valid_mask.tif", valid.astype("uint8"), None, ["valid_clear_pixel"])
    (scene_dir / "scene.json").write_text(json.dumps({
        "item": {"id": item_id, "properties": {"datetime": f"{acquired}T08:02:07.000000Z",
                                                "eo:cloud_cover": cloud_cover}},
        "record_key": record_dir.name, "bands": BANDS, "nodata": NODATA,
        "clear_fraction_aoi": float((aoi & valid).sum() / aoi.sum()), "files_sha256": {}}))


@pytest.fixture
def chip_dir(tmp_path):
    """Record folder with scenes in 2023-03 (all AOI pixels valid) and 2023-05 (two invalid)."""
    record_dir = tmp_path / "malawi_2023__506ae8b2__synthetic"
    record_dir.mkdir()
    aoi = np.zeros((SIZE, SIZE), dtype=bool)
    aoi[1:4, 1:4] = True  # 9 field pixels
    write_tif(record_dir / "aoi_mask.tif", aoi.astype("uint8"), None, ["field_or_point_mask"])
    write_scene(record_dir, "S2A_T36LWL_20230312T080000_L2A", "2023-03-12", aoi)
    write_scene(record_dir, "S2B_T36LWL_20230520T080000_L2A", "2023-05-20", aoi, invalid_aoi_pixels=2)
    (record_dir / "record.json").write_text(json.dumps({
        "record": RECORD, "status": "complete",
        "accepted_item_ids": ["S2B_T36LWL_20230520T080000_L2A", "S2A_T36LWL_20230312T080000_L2A"],
        "aoi_type": "field_polygon", "entire_aoi_inside_chip": True}))
    return record_dir
