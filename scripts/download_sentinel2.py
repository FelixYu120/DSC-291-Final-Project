"""Plan or download Sentinel-2 patches for screened maize observations.

Uses public Earth Search Collection 1 COGs; no account or API key is required.
Run with --help. See README.md for timing assumptions and scientific caveats.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform, transform_geom
import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import Point, shape
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("one_acre_fund_full", "zimbabwe", "malawi_2022", "malawi_2023",
            "vision_guided_yield_estimation")
API = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
BANDS = {"B02": "blue", "B03": "green", "B04": "red", "B05": "rededge1",
         "B06": "rededge2", "B07": "rededge3", "B08": "nir", "B8A": "nir08",
         "B11": "swir16", "B12": "swir22"}
NODATA = -9999.0
PIPELINE_VERSION = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    # The Malawi source files use both month/day/year and year/month/day.
    for fmt, length in (("%Y-%m-%d", 10), ("%Y/%m/%d", 10)):
        try:
            return datetime.strptime(text[:length], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.strptime(text.split()[0], "%m/%d/%Y").date()
    except ValueError:
        return None


def time_window(row, policy="fallback", fallback_days=180, override=None):
    """Return inclusive dates and their provenance; never silently fix dates."""
    if override:
        start, end = map(date.fromisoformat, override)
        if not 0 < (end - start).days <= 730:
            raise ValueError("Override dates must be ordered and at most 730 days apart")
        return start, end, "user_override", []
    year = int(row["year"])
    warnings = []
    dates = {}
    for name in ("planting_date", "harvest_date", "observation_time"):
        raw = row.get(name, "")
        parsed = parse_date(raw)
        if parsed and not year - 1 <= parsed.year <= year + 1:
            parsed = None
        if raw and parsed is None:
            warnings.append(f"invalid_or_out_of_range_{name}")
        dates[name] = parsed
    planting, harvest = dates["planting_date"], dates["harvest_date"]
    if planting and harvest and 1 <= (harvest - planting).days <= 365:
        return planting, harvest, "observed_planting_to_harvest", warnings
    if planting and harvest:
        warnings.append("inconsistent_planting_harvest_pair")
    if policy == "observed-only":
        return None, None, "skipped_unresolved_dates", warnings
    if harvest:
        return harvest - timedelta(days=fallback_days), harvest, "inferred_before_harvest", warnings
    if dates["observation_time"]:
        end = dates["observation_time"]
        return end - timedelta(days=fallback_days), end, "inferred_before_crop_cut", warnings
    if planting:
        return planting, planting + timedelta(days=fallback_days), "inferred_after_planting", warnings
    return date(year, 1, 1), date(year, 12, 31), "calendar_year_fallback", warnings


def read_overrides(path):
    result = {}
    if path:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            required = {"dataset", "source_id", "start_date", "end_date"}
            if not required <= set(reader.fieldnames or []):
                raise ValueError(f"Date overrides need columns: {sorted(required)}")
            for row in reader:
                key = (row["dataset"], row["source_id"])
                if key in result:
                    raise ValueError(f"Duplicate date override: {key}")
                result[key] = (row["start_date"], row["end_date"])
    return result


def load_records(args):
    records, input_hashes = [], {}
    overrides = read_overrides(args.date_overrides)
    used_overrides = set()
    seen = set()
    for dataset in args.datasets:
        path = args.audit_dir / f"{dataset}_screened_candidates.csv"
        input_hashes[path.name] = sha256(path)
        geometries = {}
        if dataset.startswith("malawi_"):
            polygons = args.audit_dir / f"{dataset}_candidates_wgs84.geojson"
            input_hashes[polygons.name] = sha256(polygons)
            for feature in json.loads(polygons.read_text())["features"]:
                geometries[str(feature["properties"]["source_id"])] = feature["geometry"]
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if int(row["year"]) < args.min_year:
                    continue
                if row["passes_yield_and_known_location_checks"].lower() != "true":
                    continue
                if row["crop"].lower() != "maize" or row["dataset"] != dataset:
                    raise ValueError(f"Unexpected crop/dataset in {path}")
                key = (dataset, row["source_id"])
                if not key[1] or key in seen:
                    raise ValueError(f"Missing or duplicate record identifier: {key}")
                seen.add(key)
                lon, lat, y = map(float, (row["longitude"], row["latitude"], row["yield_kg_ha"]))
                if not all(math.isfinite(v) for v in (lon, lat, y)) or not (-180 <= lon <= 180 and -80 <= lat <= 84 and y >= 0):
                    raise ValueError(f"Invalid coordinate/yield or outside UTM latitude range: {key}")
                geometry = geometries.get(row["source_id"])
                if dataset.startswith("malawi_") and geometry is None:
                    raise ValueError(f"Missing audited field boundary: {key}")
                geometry = geometry or {"type": "Point", "coordinates": [lon, lat]}
                if not shape(geometry).is_valid or shape(geometry).is_empty:
                    raise ValueError(f"Invalid geometry: {key}")
                override = overrides.get(key)
                if override:
                    used_overrides.add(key)
                start, end, basis, warnings = time_window(row, args.date_policy, args.fallback_days, override)
                record = {"dataset": dataset, "source_id": row["source_id"], "source_row": row["source_row"],
                          "year": int(row["year"]), "country": row["country"], "longitude": lon, "latitude": lat,
                          "yield_kg_ha": y, "geometry": geometry, "source_record": row,
                          "start_date": start.isoformat() if start else None,
                          "end_date": end.isoformat() if end else None, "window_basis": basis,
                          "timing_requires_review": basis not in ("observed_planting_to_harvest", "user_override"),
                          "timing_warnings": warnings}
                record["fingerprint"] = digest(record)
                safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", row["source_id"])[:64]
                record["record_key"] = f"{dataset}__{safe_id}__{record['fingerprint'][:12]}"
                records.append(record)
    unused = set(overrides) - used_overrides
    if unused:
        raise ValueError(f"Date overrides did not match selected records: {sorted(unused)[:5]}")
    # Stable input order makes --offset / --limit useful for independent batches.
    return records, input_hashes


class Catalog:
    """Cache complete paginated searches per 0.25-degree cell and calendar year."""
    def __init__(self, directory, cloud_cover, refresh=False):
        self.directory = directory
        self.cloud_cover = cloud_cover
        self.refresh = refresh
        self.session = requests.Session()
        retry = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "POST"))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = "DSC-291-maize-sentinel2/1.0"

    @lru_cache(maxsize=8)
    def cell(self, x, y, year):
        params = {"collections": COLLECTION, "bbox": f"{x/4},{y/4},{(x+1)/4},{(y+1)/4}",
                  "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59Z",
                  "query": json.dumps({"eo:cloud_cover": {"lte": self.cloud_cover}}), "limit": 100}
        path = self.directory / f"{digest({'api': API, 'params': params})}.json"
        if path.exists() and not self.refresh:
            return json.loads(path.read_text())["features"]
        items = {}
        url, method, body = API + "/search", "GET", None
        visited = set()
        while url:
            page_key = digest([url, method, body, params])
            if page_key in visited:
                raise RuntimeError("STAC pagination repeated a page")
            visited.add(page_key)
            response = self.session.request(method, url, params=params, json=body, timeout=(15, 90))
            response.raise_for_status()
            page = response.json()
            for item in page["features"]:
                items[item["id"]] = item
            nxt = next((link for link in page.get("links", []) if link["rel"] == "next"), None)
            if nxt:
                url, method, body = nxt["href"], nxt.get("method", "GET"), nxt.get("body")
                if nxt.get("merge"):
                    raise RuntimeError("Unsupported STAC pagination body merge; refusing to truncate search")
                params = None
            else:
                url = None
        features = list(items.values())
        atomic_json(path, {"fetched_at": datetime.now(timezone.utc).isoformat(), "features": features})
        return features

    def search(self, record):
        start, end = record["start_date"], record["end_date"]
        point = Point(record["longitude"], record["latitude"])
        items = {}
        for year in range(int(start[:4]), int(end[:4]) + 1):
            for item in self.cell(math.floor(point.x * 4), math.floor(point.y * 4), year):
                acquired = item["properties"]["datetime"][:10]
                if start <= acquired <= end and shape(item["geometry"]).covers(point):
                    items[item["id"]] = item
        return list(items.values())


def month_candidates(items, max_scenes, candidates_per_month):
    groups = defaultdict(list)
    for item in items:
        groups[item["properties"]["datetime"][:7]].append(item)
    months = sorted(groups)
    if len(months) > max_scenes:
        indices = ([len(months) // 2] if max_scenes == 1 else
                   [round(i * (len(months) - 1) / (max_scenes - 1)) for i in range(max_scenes)])
        months = [months[i] for i in indices]
    return [(month, sorted(groups[month], key=lambda item: (
        item["properties"].get("eo:cloud_cover", 100), item["properties"]["datetime"], item["id"]
    ))[:candidates_per_month]) for month in months]


def grid_for(record, size, resolution):
    lon, lat = record["longitude"], record["latitude"]
    zone = min(60, max(1, math.floor((lon + 180) / 6) + 1))
    crs = f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"
    x, y = transform("EPSG:4326", crs, [lon], [lat])
    left = math.floor(x[0] / resolution) * resolution - (size // 2) * resolution
    top = math.floor(y[0] / resolution) * resolution + (size // 2) * resolution
    return {"crs": crs, "transform": from_origin(left, top, resolution, resolution),
            "width": size, "height": size}


def aoi_for(record, grid):
    geom = transform_geom("EPSG:4326", grid["crs"], record["geometry"])
    mask = rasterize([(geom, 1)], out_shape=(grid["height"], grid["width"]),
                     transform=grid["transform"], all_touched=True, dtype="uint8").astype(bool)
    if not mask.any():
        raise ValueError("AOI contains no chip pixels")
    bounds = rasterio.transform.array_bounds(grid["height"], grid["width"], grid["transform"])
    from shapely.geometry import box
    return mask, box(*bounds).covers(shape(geom))


def read_asset(asset, grid, categorical=False):
    """Read only intersecting COG blocks, on the same grid for every band/date."""
    info = asset.get("raster:bands", [{}])[0]
    nodata = info.get("nodata", 0)
    if not categorical and ("scale" not in info or "offset" not in info):
        raise ValueError("Missing STAC reflectance scale/offset; refusing to guess")
    with rasterio.open(asset["href"]) as src:
        with WarpedVRT(src, **grid, src_nodata=nodata, nodata=NODATA, dtype="float32",
                       resampling=Resampling.nearest if categorical else Resampling.bilinear) as vrt:
            raw = vrt.read(1, masked=True)
    if categorical:
        return raw.filled(0).astype("uint8")
    result = raw.astype("float32") * float(info["scale"]) + float(info["offset"])
    return result.filled(np.nan)


def write_tif(path, array, grid, nodata, descriptions):
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    with rasterio.open(temporary, "w", driver="GTiff", **grid, count=len(array),
                       dtype=array.dtype, nodata=nodata, compress="deflate") as out:
        out.write(array)
        out.descriptions = tuple(descriptions)
    temporary.replace(path)


def verified_scene(directory):
    path = directory / "scene.json"
    if not path.exists():
        return None
    try:
        metadata = json.loads(path.read_text())
        for name, checksum in metadata["files_sha256"].items():
            if sha256(directory / name) != checksum:
                return None
        return metadata
    except (OSError, ValueError, KeyError):
        return None


def download_scene(item, directory, record, grid, aoi, args):
    cached = verified_scene(directory)
    if cached:
        return {"status": "accepted", "item_id": item["id"], "reused": True,
                "clear_fraction_aoi": cached["clear_fraction_aoi"]}
    assets = item["assets"]
    scl = read_asset(assets["scl"], grid, categorical=True)
    clear = np.isin(scl, (4, 5, 6))  # vegetation, bare/nonvegetated, water
    fraction = float(clear[aoi].mean())
    if fraction < args.min_clear_fraction:
        return {"status": "rejected_cloud_or_nodata", "item_id": item["id"], "clear_fraction_aoi": fraction}
    reflectance = np.stack([read_asset(assets[BANDS[band]], grid) for band in args.bands])
    valid = clear & np.isfinite(reflectance).all(axis=0)
    fraction = float(valid[aoi].mean())
    if fraction < args.min_clear_fraction:
        return {"status": "rejected_band_nodata", "item_id": item["id"], "clear_fraction_aoi": fraction}
    reflectance[:, ~valid] = NODATA
    write_tif(directory / "reflectance.tif", reflectance, grid, NODATA, args.bands)
    write_tif(directory / "scl.tif", scl, grid, 0, ["SCL"])
    write_tif(directory / "valid_mask.tif", valid.astype("uint8"), grid, None, ["valid_clear_pixel"])
    files = {name: sha256(directory / name) for name in ("reflectance.tif", "scl.tif", "valid_mask.tif")}
    atomic_json(directory / "scene.json", {
        "item": item, "record_key": record["record_key"], "bands": args.bands,
        "reflectance_units": "unitless BOA reflectance; STAC scale and offset applied once",
        "nodata": NODATA, "clear_scl_classes": [4, 5, 6], "clear_fraction_aoi": fraction,
        "clear_fraction_chip": float(valid.mean()), "files_sha256": files,
        "downloaded_at": datetime.now(timezone.utc).isoformat()})
    return {"status": "accepted", "item_id": item["id"], "reused": False, "clear_fraction_aoi": fraction}


def process_record(record, run_dir, catalog, args):
    directory = run_dir / "records" / record["record_key"]
    if not record["start_date"]:
        return {"record_key": record["record_key"], "status": "skipped_dates", "scenes": 0}
    previous = directory / "record.json"
    if previous.exists() and not args.refresh_catalog:
        old = json.loads(previous.read_text())
        if (old["status"] == "complete" and
                (directory / "aoi_mask.tif").exists() and
                sha256(directory / "aoi_mask.tif") == old.get("aoi_sha256") and
                all(verified_scene(directory / item_id) for item_id in old["accepted_item_ids"])):
            return {"record_key": record["record_key"], "status": "complete", "scenes": len(old["accepted_item_ids"]), "reused": True}
    grid = grid_for(record, args.chip_size, args.resolution)
    aoi, contained = aoi_for(record, grid)
    write_tif(directory / "aoi_mask.tif", aoi.astype("uint8"), grid, None, ["field_or_point_mask"])
    items = catalog.search(record)
    attempts, accepted, unresolved_errors = [], [], False
    for month, candidates in month_candidates(items, args.max_scenes, args.candidates_per_month):
        month_ok, month_error = False, False
        for item in candidates:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", item["id"]) or item["id"] in (".", ".."):
                raise ValueError("Unsafe STAC item identifier")
            try:
                attempt = download_scene(item, directory / item["id"], record, grid, aoi, args)
            except Exception as exc:
                attempt = {"status": "error", "item_id": item["id"], "error": str(exc)}
                month_error = True
            attempts.append({"month": month, **attempt})
            if attempt["status"] == "accepted":
                accepted.append(item["id"])
                month_ok = True
                break
        unresolved_errors |= month_error and not month_ok
    status = ("partial_error" if accepted else "error") if unresolved_errors else (
        "complete" if accepted else "no_clear_scenes" if items else "no_scenes")
    atomic_json(previous, {"record": record, "status": status, "accepted_item_ids": accepted,
                          "catalog_matches": len(items), "attempts": attempts,
                          "grid": {**grid, "transform": list(grid["transform"])[:6]},
                          "aoi_type": "field_polygon" if record["geometry"]["type"] != "Point" else "point_pixel",
                          "entire_aoi_inside_chip": contained,
                          "aoi_sha256": sha256(directory / "aoi_mask.tif")})
    return {"record_key": record["record_key"], "status": status, "scenes": len(accepted)}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "download"), help="plan is offline; download retrieves image patches")
    parser.add_argument("--audit-dir", type=Path, default=ROOT / "data/audit")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/imagery/sentinel2")
    parser.add_argument("--datasets", nargs="+", choices=DATASETS, default=list(DATASETS))
    parser.add_argument("--min-year", type=int, default=2019, help="minimum observation year, not imagery acquisition year")
    parser.add_argument("--limit", type=int, help="maximum records in this batch")
    parser.add_argument("--offset", type=int, default=0, help="skip this many eligible records before applying limit")
    parser.add_argument("--bands", nargs="+", choices=list(BANDS), default=list(BANDS))
    parser.add_argument("--chip-size", type=int, default=64, help="square patch width in pixels")
    parser.add_argument("--resolution", type=float, default=10, help="output pixel size in metres")
    parser.add_argument("--max-scenes", type=int, default=12, help="at most one accepted scene per selected month")
    parser.add_argument("--candidates-per-month", type=int, default=3, help="try this many scenes per month in tile cloud-cover order")
    parser.add_argument("--max-cloud-cover", type=float, default=80, help="STAC tile cloud cover threshold (percent)")
    parser.add_argument("--min-clear-fraction", type=float, default=0.8, help="minimum clear, valid fraction over the field/point AOI")
    parser.add_argument("--date-policy", choices=("fallback", "observed-only"), default="fallback")
    parser.add_argument("--fallback-days", type=int, default=180)
    parser.add_argument("--date-overrides", type=Path, help="CSV: dataset,source_id,start_date,end_date (ISO dates)")
    parser.add_argument("--refresh-catalog", action="store_true", help="refresh cached searches and reconsider completed records")
    args = parser.parse_args(argv)
    if (args.min_year < 2019 or args.offset < 0 or (args.limit is not None and args.limit < 1)
            or not 8 <= args.chip_size <= 1024 or not 1 <= args.resolution <= 60
            or not 1 <= args.max_scenes <= 24 or not 1 <= args.candidates_per_month <= 100
            or not 1 <= args.fallback_days <= 365 or not 0 <= args.max_cloud_cover <= 100
            or not 0 < args.min_clear_fraction <= 1):
        parser.error("Invalid numeric option; see --help (min-year must be >=2019)")
    if len(set(args.datasets)) != len(args.datasets) or len(set(args.bands)) != len(args.bands):
        parser.error("Datasets and bands must not be repeated")
    return args


def main(argv=None):
    args = arguments(argv)
    config = {k: getattr(args, k) for k in ("bands", "chip_size", "resolution", "max_scenes",
        "candidates_per_month", "max_cloud_cover", "min_clear_fraction", "date_policy", "fallback_days")}
    config.update(pipeline_version=PIPELINE_VERSION, api=API, collection=COLLECTION)
    records, input_hashes = load_records(args)
    eligible = len(records)
    records = records[args.offset:args.offset + args.limit if args.limit else None]
    if not records:
        raise ValueError("No records selected; check min-year, datasets, offset and audit inputs")
    run_dir = args.output_dir / f"run-{digest(config)[:16]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    batch = {"config": config, "input_sha256": input_hashes, "selected_datasets": args.datasets,
             "min_year": args.min_year, "offset": args.offset, "limit": args.limit}
    # Separate invocation manifests so disjoint batches do not overwrite one another.
    batch_id = digest({**batch, "record_fingerprints": [r["fingerprint"] for r in records]})[:16]
    plan_path = run_dir / f"plan-{batch_id}.jsonl"
    with plan_path.with_suffix(".jsonl.part").open("w") as f:
        for record in records:
            f.write(json.dumps(record, allow_nan=False) + "\n")
    plan_path.with_suffix(".jsonl.part").replace(plan_path)
    ready = sum(r["start_date"] is not None for r in records)
    # Reflectance bands (4 bytes each), SCL, valid mask, and AOI mask.
    estimated = ready * args.max_scenes * args.chip_size ** 2 * (4 * len(args.bands) + 3)
    summary = {**batch, "eligible_records": eligible, "selected_records": len(records), "ready_records": ready,
               "window_basis_counts": dict(Counter(r["window_basis"] for r in records)),
               "upper_bound_uncompressed_image_bytes": estimated, "plan": str(plan_path)}
    atomic_json(run_dir / f"plan-{batch_id}.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if args.command == "plan":
        return 0
    catalog = Catalog(args.output_dir / "catalog_cache", args.max_cloud_cover, args.refresh_catalog)
    results, failures = [], 0
    # HTTP range reads avoid downloading whole scenes. Serial operation limits load.
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_MAX_RETRY=2, GDAL_HTTP_RETRY_DELAY=1, GDAL_HTTP_TIMEOUT=45,
                      GDAL_CACHEMAX=64 * 1024 * 1024, AWS_NO_SIGN_REQUEST="YES"):
        for i, record in enumerate(records, 1):
            try:
                result = process_record(record, run_dir, catalog, args)
            except Exception as exc:
                result = {"record_key": record["record_key"], "status": "error", "scenes": 0, "error": str(exc)}
            failures += result["status"] in ("error", "partial_error")
            results.append(result)
            print(f"[{i}/{len(records)}] {record['dataset']} {record['source_id']}: {result}", flush=True)
            atomic_json(run_dir / f"results-{batch_id}.json", {
                "batch": batch, "updated_at": datetime.now(timezone.utc).isoformat(),
                "processed_records": len(results), "selected_records": len(records),
                "status_counts": dict(Counter(r["status"] for r in results)), "records": results})
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
