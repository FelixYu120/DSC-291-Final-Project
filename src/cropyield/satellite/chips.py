"""Read one record folder written by scripts/download_sentinel2.py.

A record folder holds ``record.json`` and ``aoi_mask.tif`` plus one sub-folder per accepted
scene with ``scene.json``, ``reflectance.tif``, ``scl.tif`` and ``valid_mask.tif``. Reflectance
is unitless bottom-of-atmosphere reflectance: the downloader applied the STAC scale (0.0001)
and offset (-0.1) once, so the Collection 1 "-1000" offset is already removed. Pixels the
downloader rejected are stored as -9999 and come back here as NaN.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import rasterio

from cropyield.data.cohorts import obs_id as make_obs_id


@dataclass
class Scene:
    item_id: str
    date: date                      # acquisition date (UTC)
    tile_cloud_cover: float | None  # STAC eo:cloud_cover of the whole tile, percent
    clear_fraction_aoi: float       # clear, valid fraction over the AOI (downloader check)
    reflectance: np.ndarray         # (n_bands, rows, cols) float32, NaN where not valid
    scl: np.ndarray                 # (rows, cols) uint8 scene classification
    valid: np.ndarray               # (rows, cols) bool: clear SCL class and all bands finite


@dataclass
class Chip:
    record_dir: Path
    obs_id: str
    dataset: str
    source_id: str
    source_row: int
    longitude: float
    latitude: float
    yield_kg_ha: float
    status: str                     # downloader status, e.g. "complete", "no_clear_scenes"
    aoi_type: str                   # "field_polygon" or "point_pixel"
    entire_aoi_inside_chip: bool
    start_date: date | None         # window the downloader searched
    end_date: date | None
    window_basis: str
    bands: tuple[str, ...]          # band codes in reflectance order, e.g. ("B02", ..., "B12")
    crs: str
    transform: tuple[float, ...]
    aoi: np.ndarray                 # (rows, cols) bool field or point mask
    scenes: list[Scene] = field(default_factory=list)


def read_chip(record_dir: Path) -> Chip:
    """Read record.json, the AOI mask and every accepted scene of one record folder."""
    record_dir = Path(record_dir)
    meta = json.loads((record_dir / "record.json").read_text())
    record = meta["record"]
    with rasterio.open(record_dir / "aoi_mask.tif") as src:
        aoi = src.read(1).astype(bool)
        crs, transform = str(src.crs), tuple(src.transform)[:6]
    scenes: list[Scene] = []
    bands: tuple[str, ...] | None = None
    for item_id in meta["accepted_item_ids"]:
        scene_dir = record_dir / item_id
        scene_meta = json.loads((scene_dir / "scene.json").read_text())
        with rasterio.open(scene_dir / "reflectance.tif") as src:
            reflectance = src.read().astype("float32")
            scene_bands = tuple(src.descriptions)
            if src.nodata is not None:
                reflectance[reflectance == src.nodata] = np.nan
        with rasterio.open(scene_dir / "scl.tif") as src:
            scl = src.read(1)
        with rasterio.open(scene_dir / "valid_mask.tif") as src:
            valid = src.read(1).astype(bool)
        if scene_bands != tuple(scene_meta["bands"]):
            raise ValueError(f"{scene_dir}: band order differs between reflectance.tif and scene.json")
        if bands is None:
            bands = scene_bands
        elif scene_bands != bands:
            raise ValueError(f"{scene_dir}: band order differs between scenes")
        if reflectance.shape[1:] != aoi.shape or scl.shape != aoi.shape or valid.shape != aoi.shape:
            raise ValueError(f"{scene_dir}: raster shape differs from aoi_mask.tif")
        properties = scene_meta["item"]["properties"]
        scenes.append(Scene(item_id=item_id, date=date.fromisoformat(properties["datetime"][:10]),
                            tile_cloud_cover=properties.get("eo:cloud_cover"),
                            clear_fraction_aoi=float(scene_meta["clear_fraction_aoi"]),
                            reflectance=reflectance, scl=scl, valid=valid))
    scenes.sort(key=lambda s: (s.date, s.item_id))
    return Chip(
        record_dir=record_dir,
        obs_id=make_obs_id(record["dataset"], record["source_id"]),
        dataset=record["dataset"], source_id=record["source_id"], source_row=int(record["source_row"]),
        longitude=float(record["longitude"]), latitude=float(record["latitude"]),
        yield_kg_ha=float(record["yield_kg_ha"]), status=meta["status"], aoi_type=meta["aoi_type"],
        entire_aoi_inside_chip=bool(meta["entire_aoi_inside_chip"]),
        start_date=date.fromisoformat(record["start_date"]) if record.get("start_date") else None,
        end_date=date.fromisoformat(record["end_date"]) if record.get("end_date") else None,
        window_basis=record["window_basis"], bands=bands or (), crs=crs, transform=transform,
        aoi=aoi, scenes=scenes,
    )
