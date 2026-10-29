"""Synthetic record folder in the exact layout scripts/imagery/download_sentinel2.py writes.

No imagery is committed, so tests build a tiny 6 x 6 pixel chip with two accepted scenes. The
field polygon touches a 3 x 3 block of pixels (the downloader's all_touched mask) but only a
2 x 2 block of pixel centres lies inside it.
"""
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely import transform as shapely_transform
from shapely.geometry import box, mapping

from cropyield.longpath import filesystem_path

BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
NODATA = -9999.0
SIZE = 6
GRID = {"crs": "EPSG:32736", "transform": from_origin(553_000, 8_527_000, 10, 10), "width": SIZE, "height": SIZE}
# Field in chip coordinates: x 18..38 m, y 62..82 m below the top-left corner. Touches pixels
# rows 1-3 x cols 1-3 (9 pixels); pixel centres inside: rows 2-3 x cols 2-3 (4 pixels).
FIELD_UTM = box(553_018, 8_526_962, 553_038, 8_526_982)
_to_wgs84 = Transformer.from_crs("EPSG:32736", "EPSG:4326", always_xy=True).transform
FIELD_WGS84 = mapping(shapely_transform(FIELD_UTM, lambda xy: np.column_stack(_to_wgs84(xy[:, 0], xy[:, 1]))))
FIELD_LON, FIELD_LAT = _to_wgs84(FIELD_UTM.centroid.x, FIELD_UTM.centroid.y)
# Reflectance per band inside the field; boundary (touched-only) pixels are 0.5 and the rest of
# the chip 0.9, so any leak of non-field pixels into a monthly value shows up.
FIELD_REFLECTANCE = {"B02": 0.03, "B03": 0.06, "B04": 0.05, "B05": 0.09, "B06": 0.18, "B07": 0.22,
                     "B08": 0.25, "B8A": 0.27, "B11": 0.15, "B12": 0.08}
AOI_REFLECTANCE = FIELD_REFLECTANCE
BOUNDARY_REFLECTANCE = 0.5
# Identity of the first pilot record of the Malawi 2023 cohort (audit CSV row 1); the synthetic
# polygon sits at the fixture grid, so its coordinates are the polygon centroid, not the real field.
RECORD = {"dataset": "malawi_2023", "source_id": "506ae8b2-d085-4eeb-b807-765e03925c71", "source_row": "1",
          "year": 2023, "country": "malawi", "longitude": float(FIELD_LON), "latitude": float(FIELD_LAT),
          "yield_kg_ha": 2950.0, "geometry": FIELD_WGS84, "start_date": "2023-03-01", "end_date": "2023-06-30",
          "window_basis": "user_override"}


def write_tif(path, array, nodata, descriptions):
    if array.ndim == 2:
        array = array[np.newaxis]
    with rasterio.open(filesystem_path(path), "w", driver="GTiff", **GRID, count=len(array),
                       dtype=array.dtype, nodata=nodata, compress="deflate") as out:
        out.write(array)
        out.descriptions = tuple(descriptions)


def write_scene(record_dir, item_id, acquired, touched, interior, invalid=(), cloud_cover=12.5):
    """One scene: interior pixels hold FIELD_REFLECTANCE, boundary pixels 0.5, the rest 0.9."""
    scene_dir = record_dir / item_id
    Path(filesystem_path(scene_dir)).mkdir(parents=True, exist_ok=True)
    reflectance = np.full((len(BANDS), SIZE, SIZE), 0.9, dtype="float32")
    reflectance[:, touched & ~interior] = BOUNDARY_REFLECTANCE
    for i, band in enumerate(BANDS):
        reflectance[i][interior] = FIELD_REFLECTANCE[band]
    valid = np.ones((SIZE, SIZE), dtype=bool)
    for row, col in invalid:
        valid[row, col] = False
    reflectance[:, ~valid] = NODATA
    scl = np.where(valid, 4, 9).astype("uint8")  # 4 vegetation, 9 cloud high probability
    write_tif(scene_dir / "reflectance.tif", reflectance, NODATA, BANDS)
    write_tif(scene_dir / "scl.tif", scl, 0, ["SCL"])
    write_tif(scene_dir / "valid_mask.tif", valid.astype("uint8"), None, ["valid_clear_pixel"])
    Path(filesystem_path(scene_dir / "scene.json")).write_text(json.dumps({
        "item": {"id": item_id, "properties": {"datetime": f"{acquired}T08:02:07.000000Z",
                                                "eo:cloud_cover": cloud_cover}},
        "record_key": record_dir.name, "bands": BANDS, "nodata": NODATA,
        "clear_fraction_aoi": float((touched & valid).sum() / touched.sum()), "files_sha256": {}}))


def make_record_dir(tmp_path, record, aoi_type="field_polygon"):
    """Record folder with the downloader's all_touched mask and record.json; no scenes yet."""
    record_dir = tmp_path / f"{record['dataset']}__{record['source_id'][:8]}__synthetic"
    Path(filesystem_path(record_dir)).mkdir(parents=True, exist_ok=True)
    geometry = record["geometry"]
    if geometry["type"] == "Point":
        touched = np.zeros((SIZE, SIZE), dtype=bool)
        touched[2, 2] = True
    else:
        touched = rasterize([(FIELD_UTM, 1)], out_shape=(SIZE, SIZE), transform=GRID["transform"],
                            all_touched=True, dtype="uint8").astype(bool)
    write_tif(record_dir / "aoi_mask.tif", touched.astype("uint8"), None, ["field_or_point_mask"])
    Path(filesystem_path(record_dir / "record.json")).write_text(json.dumps({
        "record": record, "status": "complete", "accepted_item_ids": [],
        "aoi_type": aoi_type, "entire_aoi_inside_chip": True}))
    return record_dir, touched


def add_scenes(record_dir, item_ids):
    record_json = record_dir / "record.json"
    meta = json.loads(Path(filesystem_path(record_json)).read_text())
    meta["accepted_item_ids"] = list(item_ids)
    Path(filesystem_path(record_json)).write_text(json.dumps(meta))


@pytest.fixture
def chip_dir(tmp_path):
    """Record folder with scenes in 2023-03 (all pixels valid) and 2023-05 (two interior pixels invalid)."""
    record_dir, touched = make_record_dir(tmp_path, RECORD)
    interior = np.zeros((SIZE, SIZE), dtype=bool)
    interior[2:4, 2:4] = True
    assert touched.sum() == 9 and (interior & touched).sum() == 4
    write_scene(record_dir, "S2A_T36LWL_20230312T080000_L2A", "2023-03-12", touched, interior)
    write_scene(record_dir, "S2B_T36LWL_20230520T080000_L2A", "2023-05-20", touched, interior, invalid=[(2, 2), (3, 3)])
    add_scenes(record_dir, ["S2B_T36LWL_20230520T080000_L2A", "S2A_T36LWL_20230312T080000_L2A"])
    return record_dir
