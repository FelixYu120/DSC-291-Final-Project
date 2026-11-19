"""Step 2 of the pass archive: list every Sentinel-2 product over every usable location.

No cloud filter, no cap, no "best scene". For each MGRS tile that holds a location and each calendar year a
field-season there needs (harvest year and the year before), the step saves:

    cdse/<tile>_<year>.json           the Copernicus Data Space catalogue (every L1C and L2A product it lists)
    earthsearch/<coll>_<tile>_<year>.jsonl   Earth Search items (the public COG copies that can be read)

and builds ``tiles``, ``location_tiles``, ``scenes``, ``scene_items`` and ``location_granules`` (the expected
passes: location x granule, with the catalogue footprint test). Saved pages are reused, so a second run only
fetches what is missing. Run: ``python -m cropyield.archive.catalog``
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import shapely
from pyproj import Transformer

from cropyield.archive import ids, paths

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
CDSE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
TILE_SIZE_M = 109_800
COLLECTIONS = ("sentinel-2-c1-l2a", "sentinel-2-l2a")
PLANETARY = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PLANETARY_COLLECTION = "planetary-computer/sentinel-2-l2a"
PLANETARY_BANDS = ("B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12", "SCL", "AOT", "WVP")
ASSET_BAND = {"coastal": "B01", "blue": "B02", "green": "B03", "red": "B04", "rededge1": "B05", "rededge2": "B06",
              "rededge3": "B07", "nir": "B08", "nir08": "B8A", "nir09": "B09", "swir16": "B11", "swir22": "B12",
              "scl": "SCL", "aot": "AOT", "wvp": "WVP", "cloud": "CLD", "snow": "SNW"}
_session = requests.Session()


def call(method: str, url: str, **kwargs) -> dict:
    """One JSON request with retries. A failure after all retries raises: it is a service error, not 'zero'."""
    wait = 2.0
    for attempt in range(7):
        try:
            response = _session.request(method, url, timeout=180, **kwargs)
            if response.status_code == 200:
                return response.json()
            if response.status_code not in (429, 500, 502, 503, 504):
                response.raise_for_status()
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(wait)
        wait = min(wait * 2, 60)
    raise RuntimeError(f"no answer after 7 tries: {url}")


# ------------------------------------------------------------------------------------------------- tiles
def discover_tiles(locations: pd.DataFrame, cache: Path) -> pd.DataFrame:
    """Every MGRS tile seen over a 0.25 degree cell that holds a location, with its grid origin."""
    if cache.exists():
        return pd.read_parquet(cache)
    cells = sorted({(int(np.floor(lon * 4)), int(np.floor(lat * 4))) for lon, lat in
                    zip(locations.longitude, locations.latitude)})

    def one(cell):
        west, south = cell[0] / 4, cell[1] / 4
        body = {"collections": ["sentinel-2-l2a"], "bbox": [west, south, west + 0.25, south + 0.25],
                "datetime": "2021-06-01T00:00:00Z/2021-06-25T00:00:00Z", "limit": 100}
        found = {}
        while body:
            page = call("POST", EARTH_SEARCH, json=body)
            for item in page["features"]:
                origin = item["assets"]["red"]["proj:transform"]
                found[item["properties"]["grid:code"][5:]] = (int(item["properties"]["proj:epsg"]),
                                                             float(origin[2]), float(origin[5]))
            body = next((link.get("body") for link in page.get("links", []) if link["rel"] == "next"), None)
        return found

    tiles = {}
    with ThreadPoolExecutor(8) as pool:
        for found in pool.map(one, cells):
            tiles.update(found)
    table = pd.DataFrame([{"mgrs_tile": tile, "epsg": epsg, "ulx": x, "uly": y, "size_m": TILE_SIZE_M}
                          for tile, (epsg, x, y) in sorted(tiles.items())])
    table.to_parquet(cache, index=False)
    return table


def place_locations(locations: pd.DataFrame, tiles: pd.DataFrame) -> pd.DataFrame:
    """Every (location, tile) whose tile square holds the location, with the native pixel at 10, 20 and 60 m."""
    parts = []
    for tile in tiles.itertuples():
        x, y = Transformer.from_crs(4326, tile.epsg, always_xy=True).transform(locations.longitude.to_numpy(),
                                                                              locations.latitude.to_numpy())
        inside = (x >= tile.ulx) & (x < tile.ulx + TILE_SIZE_M) & (y <= tile.uly) & (y > tile.uly - TILE_SIZE_M)
        if not inside.any():
            continue
        part = pd.DataFrame({"location_id": locations.location_id.to_numpy()[inside], "mgrs_tile": tile.mgrs_tile,
                             "x": x[inside], "y": y[inside]})
        for size in (10, 20, 60):
            part[f"row{size}"] = np.floor((tile.uly - part.y) / size).astype("int32")
            part[f"col{size}"] = np.floor((part.x - tile.ulx) / size).astype("int32")
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


# -------------------------------------------------------------------------------------------- catalogues
def fetch_cdse(tile: str, year: int, folder: Path) -> Path:
    path = folder / f"{tile}_{year}.json"
    if path.exists():
        return path
    where = ("Collection/Name eq 'SENTINEL-2' and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'tileId' "
             f"and att/OData.CSC.StringAttribute/Value eq '{tile}') and ContentDate/Start ge {year}-01-01T00:00:00.000Z "
             f"and ContentDate/Start lt {year + 1}-01-01T00:00:00.000Z")
    rows, skip, total, pages = [], 0, None, 0
    while total is None or len(rows) < total:
        page = call("GET", CDSE, params={"$filter": where, "$top": 1000, "$skip": skip, "$count": "true",
                                         "$orderby": "ContentDate/Start asc", "$expand": "Attributes"})
        total, pages = int(page["@odata.count"]), pages + 1
        if not page["value"]:
            break
        for product in page["value"]:
            attributes = {entry["Name"]: entry["Value"] for entry in product.get("Attributes", [])}
            rows.append({"name": product["Name"], "cdse_id": product["Id"], "start": product["ContentDate"]["Start"],
                         "footprint": product.get("Footprint"), "online": product.get("Online"),
                         "cloud_cover": attributes.get("cloudCover"), "absolute_orbit": attributes.get("orbitNumber"),
                         "relative_orbit": attributes.get("relativeOrbitNumber"),
                         "processing_baseline": attributes.get("processorVersion"),
                         "product_type": attributes.get("productType")})
        skip += 1000
    if len(rows) != total:
        raise RuntimeError(f"CDSE {tile} {year}: got {len(rows)} of {total} rows")
    record = {"provider": "cdse", "tile": tile, "year": year, "fetched_at": datetime.now(UTC).isoformat(),
              "request_filter": where, "pages": pages, "count": total, "products": rows}
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(record), encoding="utf-8")
    temporary.replace(path)
    return path


def fetch_earth_search(collection: str, tile: str, year: int, folder: Path) -> Path:
    path = folder / f"{collection}_{tile}_{year}.jsonl"
    if path.exists():
        return path
    body = {"collections": [collection], "query": {"grid:code": {"eq": f"MGRS-{tile}"}}, "limit": 100,
            "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59.999Z"}
    lines, pages = [], 0
    while body:
        page = call("POST", EARTH_SEARCH, json=body)
        pages += 1
        for item in page["features"]:
            props = item["properties"]
            assets = {}
            for key, band in ASSET_BAND.items():
                asset = item["assets"].get(key)
                if asset and asset["href"].startswith("https://"):
                    raster = (asset.get("raster:bands") or [{}])[0]
                    assets[band] = {"href": asset["href"], "scale": raster.get("scale"), "offset": raster.get("offset")}
            lines.append(json.dumps({
                "item_id": item["id"], "collection": collection, "datetime": props["datetime"],
                "product_uri": props.get("s2:product_uri"), "processing_baseline": props.get("s2:processing_baseline"),
                "boa_offset_applied": props.get("earthsearch:boa_offset_applied"),
                "cloud_cover": props.get("eo:cloud_cover"), "nodata_percent": props.get("s2:nodata_pixel_percentage"),
                "sun_elevation": props.get("view:sun_elevation"), "sun_azimuth": props.get("view:sun_azimuth"),
                "pages": pages, "fetched_at": datetime.now(UTC).isoformat(), "assets": assets}))
        body = next((link.get("body") for link in page.get("links", []) if link["rel"] == "next"), None)
    temporary = path.with_suffix(".part")
    temporary.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    temporary.replace(path)
    return path


def dn_add_offset(collection: str, baseline: str | None, removed: bool | None) -> float | None:
    """What to add to a stored spectral DN before dividing by 10000; None when it was not verified."""
    if baseline is None:
        return None
    new = tuple(int(part) for part in baseline.split(".")) >= (4, 0)
    if collection in ("sentinel-2-c1-l2a", PLANETARY_COLLECTION):     # both hold the DN exactly as ESA wrote it
        return -1000.0 if new else 0.0
    if not new or removed or baseline == "04.00":     # older collection: measured pairs hold no offset in the file
        return 0.0
    return None


# ------------------------------------------------------------------------------------------------ build
def build(workers: int = 6) -> dict:
    survey, out = paths.staging_dir("survey"), paths.staging_dir("catalog")
    (out / "cdse").mkdir(parents=True, exist_ok=True)
    (out / "earthsearch").mkdir(parents=True, exist_ok=True)
    locations = pd.read_parquet(survey / "locations.parquet")
    fields = pd.read_parquet(survey / "fields.parquet")
    fields = fields[fields.location_id.notna() & fields.harvest_year.notna()]

    tiles = discover_tiles(locations, out / "tiles.parquet")
    placed = place_locations(locations, tiles)
    placed.to_parquet(out / "location_tiles.parquet", index=False)
    print(f"{len(tiles)} tiles; {len(placed)} location-tile pairs for {placed.location_id.nunique()} of "
          f"{len(locations)} locations")

    years = pd.concat([fields[["location_id", "harvest_year"]].rename(columns={"harvest_year": "year"}),
                       fields[["location_id", "harvest_year"]].assign(year=fields.harvest_year - 1)[["location_id", "year"]]])
    years = years.drop_duplicates()
    years["year"] = years.year.astype(int)
    location_years = years.copy()
    needed = (placed[["location_id", "mgrs_tile"]].merge(years, on="location_id")[["mgrs_tile", "year"]]
              .drop_duplicates().sort_values(["mgrs_tile", "year"]))
    needed = needed[needed.year >= 2015]
    jobs = [(row.mgrs_tile, int(row.year)) for row in needed.itertuples()]
    print(f"{len(jobs)} tile-years to list")

    errors = []

    def safe(function, *arguments):
        try:
            return function(*arguments)
        except Exception as error:      # noqa: BLE001 - recorded, the tile-year stays 'catalogue_error'
            errors.append({"what": function.__name__, "arguments": [str(a) for a in arguments[:3]], "error": str(error)})
            return None

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda job: safe(fetch_cdse, job[0], job[1], out / "cdse"), jobs))
    with ThreadPoolExecutor(workers + 2) as pool:
        list(pool.map(lambda job: safe(fetch_earth_search, job[0], job[1], job[2], out / "earthsearch"),
                      [(collection, tile, year) for tile, year in jobs for collection in COLLECTIONS]))

    # ---- scenes: every product version, from the Copernicus list and from the Earth Search copies
    products, queries = {}, []
    for tile, year in jobs:
        path = out / "cdse" / f"{tile}_{year}.json"
        if not path.exists():
            queries.append({"provider": "cdse", "mgrs_tile": tile, "year": year, "status": "error", "items": None})
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        queries.append({"provider": "cdse", "mgrs_tile": tile, "year": year, "status": "ok", "items": record["count"],
                        "pages": record["pages"], "fetched_at": record["fetched_at"]})
        for product in record["products"]:
            try:
                name = ids.parse_product_name(product["name"])
            except ValueError:
                continue
            products[name.scene_id] = {
                "scene_id": name.scene_id, "level": name.level, "platform": name.platform, "mgrs_tile": name.tile,
                "acquisition_id": name.acquisition_id, "granule_id": f"{name.acquisition_id}_T{name.tile}",
                "relative_orbit": name.relative_orbit, "processing_baseline": name.baseline,
                "sensing_time": product["start"], "cloud_cover_percent": product["cloud_cover"],
                "absolute_orbit": product["absolute_orbit"], "footprint_wkt": _wkt(product["footprint"]),
                "in_cdse": True, "cdse_id": product["cdse_id"]}
    items = []
    for tile, year in jobs:
        for collection in COLLECTIONS:
            path = out / "earthsearch" / f"{collection}_{tile}_{year}.jsonl"
            if not path.exists():
                queries.append({"provider": f"earth-search/{collection}", "mgrs_tile": tile, "year": year,
                                "status": "error", "items": None})
                continue
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            queries.append({"provider": f"earth-search/{collection}", "mgrs_tile": tile, "year": year, "status": "ok",
                            "items": len(rows), "pages": max((row["pages"] for row in rows), default=1),
                            "fetched_at": rows[0]["fetched_at"] if rows else None})
            for row in rows:
                try:
                    name = ids.parse_product_name(row["product_uri"] or "")
                except ValueError:
                    continue
                if name.scene_id not in products:
                    products[name.scene_id] = {
                        "scene_id": name.scene_id, "level": name.level, "platform": name.platform,
                        "mgrs_tile": name.tile, "acquisition_id": name.acquisition_id,
                        "granule_id": f"{name.acquisition_id}_T{name.tile}", "relative_orbit": name.relative_orbit,
                        "processing_baseline": name.baseline, "sensing_time": row["datetime"],
                        "cloud_cover_percent": row["cloud_cover"], "absolute_orbit": None, "footprint_wkt": None,
                        "in_cdse": False, "cdse_id": None}
                items.append({"scene_id": name.scene_id, "provider": "earth-search", "collection": collection,
                              "item_id": row["item_id"], "processing_baseline": row["processing_baseline"],
                              "boa_offset_applied": row["boa_offset_applied"],
                              "dn_add_offset": dn_add_offset(collection, row["processing_baseline"], row["boa_offset_applied"]),
                              "cloud_cover_percent": row["cloud_cover"], "nodata_percent": row["nodata_percent"],
                              "sun_elevation": row["sun_elevation"], "sun_azimuth": row["sun_azimuth"],
                              "assets_json": json.dumps(row["assets"])})
    scenes = pd.DataFrame(products.values())
    scenes["sensing_time"] = pd.to_datetime(scenes.sensing_time, utc=True, format="ISO8601")
    scenes["cloud_cover_percent"] = pd.to_numeric(scenes.cloud_cover_percent, errors="coerce")
    scenes["absolute_orbit"] = pd.to_numeric(scenes.absolute_orbit, errors="coerce").astype("Int64")
    scenes["year"], scenes["month"] = scenes.sensing_time.dt.year, scenes.sensing_time.dt.month
    scene_items = pd.DataFrame(items).drop_duplicates(["collection", "item_id"])
    scenes.to_parquet(out / "scenes.parquet", index=False)
    scene_items.to_parquet(out / "scene_items.parquet", index=False)
    pd.DataFrame(queries).to_parquet(out / "catalog_queries.parquet", index=False)

    # ---- expected passes: location x granule (tile square holds the location, year is needed there)
    granules = (scenes.sort_values(["granule_id", "in_cdse"], ascending=[True, False])
                .groupby("granule_id", as_index=False)
                .agg(mgrs_tile=("mgrs_tile", "first"), acquisition_id=("acquisition_id", "first"),
                     platform=("platform", "first"), relative_orbit=("relative_orbit", "first"),
                     sensing_time=("sensing_time", "min"), year=("year", "first"), month=("month", "first"),
                     footprint_wkt=("footprint_wkt", "first")))
    granules.to_parquet(out / "granules.parquet", index=False)
    parts = []
    wanted = set(map(tuple, location_years[["location_id", "year"]].to_numpy()))
    lon_lat = locations.set_index("location_id")[["longitude", "latitude"]]
    for tile, group in granules.groupby("mgrs_tile"):
        here = placed.loc[placed.mgrs_tile == tile, "location_id"].to_numpy()
        if not len(here):
            continue
        lon, lat = lon_lat.loc[here, "longitude"].to_numpy(), lon_lat.loc[here, "latitude"].to_numpy()
        for year, of_year in group.groupby("year"):
            keep = np.array([(location, year) in wanted for location in here])
            if not keep.any():
                continue
            for granule in of_year.itertuples():
                if granule.footprint_wkt:
                    inside = shapely.contains_xy(shapely.from_wkt(granule.footprint_wkt), lon[keep], lat[keep])
                else:
                    inside = np.full(int(keep.sum()), np.nan)
                parts.append(pd.DataFrame({"location_id": here[keep], "granule_id": granule.granule_id,
                                           "in_catalogue_footprint": inside}))
    expected = pd.concat(parts, ignore_index=True)
    expected.to_parquet(out / "location_granules.parquet", index=False)
    summary = {"tiles": len(tiles), "tile_years": len(jobs), "scenes": len(scenes),
               "scenes_by_level": scenes.level.value_counts().to_dict(), "granules": len(granules),
               "earth_search_items": len(scene_items), "location_granules": len(expected),
               "catalogue_errors": errors}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def fetch_planetary(tile: str, year: int, folder: Path) -> Path:
    """Planetary Computer Level-2A items of one tile and year (a second public copy, read with a free token)."""
    path = folder / f"{tile}_{year}.jsonl"
    if path.exists():
        return path
    body = {"collections": ["sentinel-2-l2a"], "query": {"s2:mgrs_tile": {"eq": tile}}, "limit": 1000,
            "datetime": f"{year}-01-01T00:00:00Z/{year}-12-31T23:59:59.999Z"}
    lines, pages = [], 0
    while body:
        page = call("POST", PLANETARY, json=body)
        pages += 1
        for item in page["features"]:
            props = item["properties"]
            assets = {band: {"href": item["assets"][band]["href"]} for band in PLANETARY_BANDS if band in item["assets"]}
            lines.append(json.dumps({
                "item_id": item["id"], "datetime": props["datetime"], "product_uri": props.get("s2:product_uri"),
                "processing_baseline": props.get("s2:processing_baseline"), "cloud_cover": props.get("eo:cloud_cover"),
                "nodata_percent": props.get("s2:nodata_pixel_percentage"), "pages": pages,
                "fetched_at": datetime.now(UTC).isoformat(), "assets": assets}))
        body = next((link.get("body") for link in page.get("links", []) if link["rel"] == "next"), None)
    temporary = path.with_suffix(".part")
    temporary.write_text("".join(line + chr(10) for line in lines), encoding="utf-8")
    temporary.replace(path)
    return path


def add_planetary(workers: int = 4) -> dict:
    """Give the granules that have no Earth Search file a Planetary Computer file, where one exists.

    Writes ``scenes_pc`` and ``scene_items_pc`` beside the first catalogue tables and changes none of them. Only
    granules that the first catalogue already lists are used; an item of an unlisted granule is counted and left.
    """
    out = paths.staging_dir("catalog")
    folder = out / "planetary"
    folder.mkdir(parents=True, exist_ok=True)
    granules = pd.read_parquet(out / "granules.parquet")
    scenes = pd.read_parquet(out / "scenes.parquet")
    items = pd.read_parquet(out / "scene_items.parquet")
    readable = set(scenes[scenes.scene_id.isin(items.scene_id)].granule_id)
    open_granules = granules[~granules.granule_id.isin(readable)]
    jobs = sorted(set(zip(open_granules.mgrs_tile, open_granules.year.astype(int))))
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda job: fetch_planetary(job[0], job[1], folder), jobs))
    wanted, known = set(open_granules.granule_id), set(scenes.scene_id)
    sensing = granules.set_index("granule_id").sensing_time
    new_scenes, new_items, unlisted, queries = {}, [], 0, []
    for tile, year in jobs:
        rows = [json.loads(line) for line in (folder / f"{tile}_{year}.jsonl").read_text(encoding="utf-8").splitlines() if line]
        queries.append({"provider": "planetary-computer/sentinel-2-l2a", "mgrs_tile": tile, "year": year, "status": "ok",
                        "items": len(rows), "pages": max((row["pages"] for row in rows), default=1),
                        "fetched_at": rows[0]["fetched_at"] if rows else None})
        for row in rows:
            try:
                name = ids.parse_product_name(row["product_uri"] or "")
            except ValueError:
                continue
            granule = f"{name.acquisition_id}_T{name.tile}"
            if granule not in sensing.index:
                unlisted += 1
                continue
            if granule not in wanted:
                continue
            if name.scene_id not in known:
                new_scenes[name.scene_id] = {
                    "scene_id": name.scene_id, "level": name.level, "platform": name.platform, "mgrs_tile": name.tile,
                    "acquisition_id": name.acquisition_id, "granule_id": granule, "relative_orbit": name.relative_orbit,
                    "processing_baseline": name.baseline, "sensing_time": sensing[granule],
                    "cloud_cover_percent": row["cloud_cover"], "absolute_orbit": None, "footprint_wkt": None,
                    "in_cdse": False, "cdse_id": None, "year": int(sensing[granule].year), "month": int(sensing[granule].month)}
            new_items.append({"scene_id": name.scene_id, "provider": "planetary-computer", "collection": PLANETARY_COLLECTION,
                              "item_id": row["item_id"], "processing_baseline": row["processing_baseline"],
                              "boa_offset_applied": None,
                              "dn_add_offset": dn_add_offset(PLANETARY_COLLECTION, row["processing_baseline"], None),
                              "cloud_cover_percent": row["cloud_cover"], "nodata_percent": row["nodata_percent"],
                              "sun_elevation": None, "sun_azimuth": None, "assets_json": json.dumps(row["assets"])})
    scene_table = pd.DataFrame(list(new_scenes.values()), columns=list(scenes.columns))
    scene_table["absolute_orbit"] = scene_table.absolute_orbit.astype("Int64")
    item_table = pd.DataFrame(new_items, columns=list(items.columns)).drop_duplicates("item_id")
    scene_table.to_parquet(out / "scenes_pc.parquet", index=False)
    item_table.to_parquet(out / "scene_items_pc.parquet", index=False)
    pd.DataFrame(queries).to_parquet(out / "catalog_queries_pc.parquet", index=False)
    gained = scene_table.granule_id.nunique() if len(scene_table) else 0
    return {"granules_without_file_before": len(open_granules), "tile_years_asked": len(jobs),
            "granules_with_a_planetary_file": int(gained), "still_without_file": len(open_granules) - int(gained),
            "planetary_items_of_unlisted_granules": unlisted}


def _wkt(footprint: str | None) -> str | None:
    """CDSE writes ``geography'SRID=4326;POLYGON ((...))'``; keep the plain WKT."""
    if not footprint:
        return None
    text = footprint.split(";", 1)[-1].rstrip("'")
    return text or None


if __name__ == "__main__":
    import sys
    result = add_planetary() if "--planetary" in sys.argv else build()
    print(json.dumps(result, indent=2, default=str))
