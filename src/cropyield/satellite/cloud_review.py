"""Review frozen Sentinel-2 scenes using SCL pixels; never edit source data.

SCL is a classifier, not proof of a cloud-free image. The conservative derivative
keeps an original field-month only when every touched field pixel is land (4/5)
and outside a configurable cloud/shadow buffer. It never invents reflectance.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

import duckdb
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform, transform_geom
import requests
from scipy.ndimage import distance_transform_edt
from shapely import from_wkt
from shapely.geometry import mapping

from cropyield import ROOT

API = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
CORE = ("kenya_oaf_2019_2020", "malawi_2023", "zimbabwe_lacuna_2022_2023")
BANDS = ("b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12")
POLICY_VERSION = 1
POLICY_SOURCES = [
    "https://sentiwiki.copernicus.eu/web/s2-processing",
    "https://documentation.dataspace.copernicus.eu/APIs/openEO/openeo-community-examples/python/30_openeo-processing/scl-dilation-mask/scl-dilation-mask.html",
]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_once(path: Path, value: bytes):
    """Atomically publish a new cache file; never replace an existing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(value)
        temporary = Path(stream.name)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()


def json_once(path, value):
    write_once(Path(path), (json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


def policy(buffer_m=60.0):
    if not np.isfinite(buffer_m) or not 0 <= buffer_m <= 300:
        raise ValueError("buffer_m must be finite and between 0 and 300 metres")
    return {"version": POLICY_VERSION, "allowed_scl": [4, 5], "cloud_shadow_scl": [3, 8, 9, 10],
            "unknown_scl": [0, 1, 7], "buffer_metres": float(buffer_m),
            "grid_metres": 10, "native_scl_metres": 20,
            "month_rule": "every touched field pixel must pass; otherwise original monthly values become NULL",
            "unknown_rule": "unknown classification within the buffer is unverified, never clear",
            "buffer_note": "Conservative project choice, not a validated universal cloud-free guarantee",
            "sources": POLICY_SOURCES}


def dilated(mask, buffer_m, resolution=10):
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return mask.copy()
    return distance_transform_edt(~mask, sampling=resolution) <= buffer_m


def cloud_masks(scl, buffer_m=60.0, resolution=10):
    """Land mask with physical cloud/shadow and unknown-context buffers."""
    policy(buffer_m)
    scl = np.asarray(scl)
    clouds = np.isin(scl, [3, 8, 9, 10])
    unknown = np.isin(scl, [0, 1, 7]) | (scl > 11)
    cloud_buffer = dilated(clouds, buffer_m, resolution)
    unknown_buffer = dilated(unknown, buffer_m, resolution)
    keep = np.isin(scl, [4, 5]) & ~cloud_buffer & ~unknown_buffer
    return keep, cloud_buffer, unknown_buffer


def chip_grid(lon, lat, buffer_m=60.0):
    """Reconstruct the original 64×64, 10 m grid, with an SCL context halo."""
    if not (np.isfinite(lon) and np.isfinite(lat) and -180 <= lon <= 180 and -90 < lat < 90):
        raise ValueError("Invalid field coordinates")
    zone = min(60, max(1, math.floor((lon + 180) / 6) + 1))
    crs = f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"
    x, y = transform("EPSG:4326", crs, [lon], [lat])
    halo = math.ceil(buffer_m / 10) + 2
    left = math.floor(x[0] / 10) * 10 - 320 - halo * 10
    top = math.floor(y[0] / 10) * 10 + 320 + halo * 10
    return {"crs": crs, "transform": from_origin(left, top, 10, 10),
            "height": 64 + 2 * halo, "width": 64 + 2 * halo}, halo


def review_chip(scl, grid, halo, row, buffer_m=60.0):
    """Return statistics and 64×64 masks on the original chip grid."""
    if str(grid["crs"]) != row["crs"]:
        raise ValueError("Reconstructed chip CRS differs from frozen download CRS")
    geometry = (mapping(from_wkt(row["geometry_wkt"])) if row.get("geometry_wkt")
                else {"type": "Point", "coordinates": [row["lon"], row["lat"]]})
    projected = transform_geom("EPSG:4326", grid["crs"], geometry)
    shape = (grid["height"], grid["width"])
    touched = rasterize([(projected, 1)], out_shape=shape, transform=grid["transform"],
                        all_touched=True, dtype="uint8").astype(bool)
    interior = rasterize([(projected, 1)], out_shape=shape, transform=grid["transform"],
                         all_touched=False, dtype="uint8").astype(bool)
    field = interior if interior.any() else touched
    crop = np.s_[halo:halo + 64, halo:halo + 64]
    if not touched.any() or touched[crop].sum() != touched.sum():
        raise ValueError("Field is empty or extends outside original chip")
    if int(field[crop].sum()) != int(row["field_pixels"]):
        raise ValueError("Reconstructed field-pixel count differs from frozen download")
    if int(touched[crop].sum()) != int(row["aoi_pixels"]):
        raise ValueError("Reconstructed touched-pixel count differs from frozen download")
    if tuple(np.shape(scl)) != shape:
        raise ValueError("SCL array does not match reconstructed grid")
    keep, buffered, unknown = cloud_masks(scl, buffer_m)
    assess = "unverified_scl" if unknown[touched].any() else "verified_scl"
    kept = assess == "verified_scl" and bool(keep[touched].all())
    stats = {"assessment": assess, "keep_whole_month": kept,
             "aoi_pixels": int(touched.sum()), "field_pixels": int(field.sum()),
             "kept_aoi_pixels": int((keep & touched).sum()),
             "kept_field_pixels": int((keep & field).sum()),
             "direct_cloud_shadow_aoi_pixels": int((np.isin(scl, [3, 8, 9, 10]) & touched).sum()),
             "buffered_cloud_shadow_aoi_pixels": int((buffered & touched).sum()),
             "unknown_context_aoi_pixels": int((unknown & touched).sum()),
             "water_aoi_pixels": int(((scl == 6) & touched).sum()),
             "other_excluded_aoi_pixels": int((~np.isin(scl, [0, 1, 3, 4, 5, 6, 7, 8, 9, 10]) & touched).sum()),
             "retained_aoi_fraction": float(keep[touched].mean()),
             "class_counts_aoi": {str(c): int(((scl == c) & touched).sum()) for c in np.unique(scl[touched])}}
    arrays = {"scl": scl[crop].astype("uint8"), "keep_mask": keep[crop],
              "field_mask": field[crop], "aoi_mask": touched[crop],
              "cloud_shadow_buffer": buffered[crop], "unknown_buffer": unknown[crop]}
    return stats, arrays


def get_metadata(item_id, cache):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", item_id):
        raise ValueError("Invalid frozen item ID")
    path = cache / "metadata" / f"{item_id}.json"
    if path.exists():
        wrapper = json.loads(path.read_text())
    else:
        url = f"{API}/collections/{COLLECTION}/items/{item_id}"
        last_error = None
        for attempt in range(3):
            try:
                response = requests.get(url, timeout=(15, 60))
                response.raise_for_status()
                item = response.json()
                wrapper = {"retrieved_at": datetime.now(UTC).isoformat(), "url": url, "item": item}
                json_once(path, wrapper)
                break
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt == 2:
                    raise RuntimeError(f"STAC metadata unavailable: {last_error}") from error
                time.sleep(attempt + 1)
    item = wrapper["item"]
    if item.get("id") != item_id or item.get("collection") != COLLECTION:
        raise ValueError("Returned STAC item differs from frozen selection")
    asset = item.get("assets", {}).get("scl")
    if not asset or not asset.get("href", "").startswith("https://"):
        raise ValueError("No public HTTPS SCL asset for frozen item")
    return wrapper, path


def load_inputs(db_path, labels_path, scope="all-retained"):
    labels = pd.read_parquet(labels_path)
    if not labels.obs_id.is_unique:
        raise ValueError("Frozen labels contain duplicate IDs")
    selected = labels if scope == "all-retained" else labels[labels.cohort.isin(CORE) & labels.include_primary]
    with duckdb.connect(str(db_path), read_only=True) as con:
        scenes = con.execute("""SELECT s.obs_id, s.item_id, s.month, s.acquired, d.crs,
            d.field_pixels, d.aoi_pixels FROM scenes s JOIN downloads d USING(obs_id)""").df()
        monthly = con.execute("SELECT * FROM monthly_bands").df()
    if scenes.duplicated(["obs_id", "month"]).any() or monthly.duplicated(["obs_id", "month"]).any():
        raise ValueError("Duplicate monthly keys in frozen database")
    columns = ["obs_id", "cohort", "country_iso3", "season_year", "include_primary", "lon", "lat", "geometry_wkt"]
    scenes = scenes.merge(selected[columns], on="obs_id", how="inner", validate="many_to_one")
    scenes["geometry_wkt"] = scenes.geometry_wkt.where(scenes.geometry_wkt.notna(), None)
    monthly = monthly[monthly.obs_id.isin(selected.obs_id)].copy()
    return selected, scenes.sort_values(["item_id", "obs_id"]), monthly


def scene_job(item_id, rows, cache, mask_policy):
    frame = rows.copy()
    frame["acquired"] = pd.to_datetime(frame.acquired).dt.strftime("%Y-%m-%d")
    frame = frame.astype(object)
    records = frame.where(frame.notna(), None).to_dict("records")
    implementation_sha256 = sha256(Path(__file__))
    key = digest({"policy": mask_policy, "records": records, "implementation_sha256": implementation_sha256})
    directory = cache / "scenes" / item_id / key
    result_path = directory / "review.json"
    if result_path.exists():
        cached = json.loads(result_path.read_text())
        if (cached["policy"] != mask_policy or cached["implementation_sha256"] != implementation_sha256
                or sha256(directory / "masks.npz") != cached["mask_sha256"]
                or sha256(Path(cached["metadata_path"])) != cached["metadata_sha256"]):
            raise ValueError(f"Corrupt cloud-review cache: {directory}")
        return cached["rows"], True
    metadata, metadata_path = get_metadata(item_id, cache)
    item = metadata["item"]
    asset = item["assets"]["scl"]
    acquisition = item["properties"]["datetime"][:10]
    if any(row["acquired"] != acquisition or row["month"] != acquisition[:7] for row in records):
        raise ValueError("STAC acquisition date differs from frozen scene date")
    results, arrays = [], {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_TIMEOUT="45", GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_RETRY_DELAY="1",
                      GDAL_CACHEMAX=256 * 1024 * 1024):
        with rasterio.open(asset["href"]) as source:
            if not np.allclose(source.res, [20, 20]):
                raise ValueError(f"Unexpected native SCL resolution: {source.res}")
            for number, row in enumerate(records):
                grid, halo = chip_grid(row["lon"], row["lat"], mask_policy["buffer_metres"])
                with WarpedVRT(source, **grid, src_nodata=0, nodata=0, dtype="uint8",
                               resampling=Resampling.nearest) as vrt:
                    scl = vrt.read(1)
                stats, masks = review_chip(scl, grid, halo, row, mask_policy["buffer_metres"])
                prefix = f"r{number:05d}"
                arrays.update({f"{prefix}_{name}": value for name, value in masks.items()})
                results.append({"obs_id": row["obs_id"], "item_id": item_id, "month": row["month"],
                                "cohort": row["cohort"], "country_iso3": row["country_iso3"],
                                "include_primary": row["include_primary"], **stats,
                                "mask_prefix": prefix, "mask_path": str(directory / "masks.npz"),
                                "metadata_path": str(metadata_path), "error": None})
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".npz", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        np.savez_compressed(temporary, **arrays)
        destination = directory / "masks.npz"
        if destination.exists():
            # An interruption can leave an atomically completed mask file before
            # its review manifest. Reuse only if its arrays are identical.
            with np.load(destination) as existing:
                if set(existing.files) != set(arrays) or any(not np.array_equal(existing[k], v) for k, v in arrays.items()):
                    raise ValueError(f"Incomplete cache has different masks: {destination}")
        else:
            os.link(temporary, destination)
    finally:
        temporary.unlink()
    payload = {"policy": mask_policy, "implementation_sha256": implementation_sha256,
               "metadata_path": str(metadata_path), "metadata_sha256": sha256(metadata_path),
               "source_asset": asset, "finished_at": datetime.now(UTC).isoformat(),
               "mask_sha256": sha256(directory / "masks.npz"), "rows": results}
    json_once(result_path, payload)
    return results, False


def run_reviews(scenes, cache, mask_policy, workers=8):
    """Each frozen source scene is opened once; failures remain explicitly unverified."""
    grouped = list(scenes.groupby("item_id", sort=True))
    results, failures = [], []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = {executor.submit(scene_job, item, rows, cache, mask_policy): (item, rows)
                for item, rows in grouped}
        for complete, future in enumerate(as_completed(jobs), 1):
            item, rows = jobs[future]
            try:
                output, cached = future.result()
                results.extend(output)
                status = "cached" if cached else "reviewed"
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                failures.append({"item_id": item, "error": message})
                for row in rows.itertuples():
                    results.append({"obs_id": row.obs_id, "item_id": item, "month": row.month,
                                    "cohort": row.cohort, "country_iso3": row.country_iso3,
                                    "include_primary": bool(row.include_primary), "assessment": "unverified_failure",
                                    "keep_whole_month": False, "error": message})
                status = "UNVERIFIED " + message[:150]
            print(f"{complete}/{len(grouped)} scenes; {len(results)}/{len(scenes)} field-months; "
                  f"{time.monotonic()-started:.0f}s; {item}: {status}", flush=True)
    result = pd.DataFrame(results).sort_values(["obs_id", "month"])
    if len(result) != len(scenes) or result.duplicated(["obs_id", "month"]).any():
        raise ValueError("Review results do not cover frozen scene-field rows exactly once")
    return result, failures


def derived_tables(monthly, reviews, selected):
    """Drop whole rejected/unverified months; no recomputed pixel median or imputation."""
    if reviews.duplicated(["obs_id", "month"]).any():
        raise ValueError("Duplicate review keys")
    columns = ["obs_id", "month", "item_id", "assessment", "keep_whole_month"]
    clean = monthly.merge(reviews[columns], on=["obs_id", "month"], how="left", validate="one_to_one")
    clean["original_missing"] = clean.missing
    clean["original_field_pixels"] = clean.field_pixels
    clean["review_state"] = np.where(clean.original_missing, "originally_missing",
                                    clean.assessment.fillna("unverified_not_reviewed"))
    clean["kept_by_cloud_policy"] = clean.keep_whole_month.eq(True) & ~clean.original_missing
    rejected = ~clean.kept_by_cloud_policy
    clean.loc[rejected, list(BANDS)] = np.nan
    clean.loc[rejected, "field_pixels"] = 0
    clean["missing"] = rejected
    clean = clean.drop(columns=["assessment", "keep_whole_month"])
    indices = clean[["obs_id", "month"]].copy()
    formulas = {"ndvi": (clean.b08-clean.b04, clean.b08+clean.b04),
                "gcvi": (clean.b08, clean.b03), "mtci": (clean.b08-clean.b05, clean.b05-clean.b04),
                "ndvi705": (clean.b08-clean.b05, clean.b08+clean.b05),
                "ndvi740": (clean.b08-clean.b06, clean.b08+clean.b06)}
    for name, (numerator, denominator) in formulas.items():
        values = numerator / denominator.replace(0, np.nan)
        if name == "gcvi":
            values = values - 1
        indices[name] = values.where(np.isfinite(values))
    season = indices.groupby("obs_id")[list(formulas)].agg(["max", "mean"])
    season.columns = [f"{name}_season_{stat}" for name, stat in season.columns]
    counts = clean.groupby("obs_id").agg(original_months_with_data=("original_missing", lambda x: int((~x).sum())),
                                         retained_months=("kept_by_cloud_policy", "sum"))
    counts["retains_four_months"] = counts.retained_months >= 4
    season = season.join(counts).reset_index()
    fields = selected[["obs_id", "cohort", "country_iso3", "include_primary"]].merge(
        counts.reset_index(), on="obs_id", how="left", validate="one_to_one")
    for col in ["original_months_with_data", "retained_months"]:
        fields[col] = fields[col].fillna(0).astype(int)
    fields["retains_four_months"] = fields.retained_months >= 4
    return clean, indices, season, fields
