"""Fetch the public map files for notebooks/midterm_figures.ipynb into data/imagery/basemap/ (git-ignored, about 45 MB).

    python notebooks/midterm_get_basemap.py ne gb dem

Stages: ne (Natural Earth 1:10m vectors, public domain), gb (geoBoundaries ADM2 of Zimbabwe, Malawi and Kenya,
CC BY 3.0 IGO), dem (Copernicus DEM GLO-90 relief mosaics, read at overview level from AWS open data),
demtest (one DEM tile, to test the connection). Each file is recorded with its URL and SHA-256 in sources.json.
"""
import hashlib
import json
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "imagery" / "basemap"
UA = {"User-Agent": "python-requests (course project map figures)"}

NATURAL_EARTH = {
    "ne_10m_admin_0_countries": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
    "ne_10m_admin_1_states_provinces": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip",
    "ne_10m_populated_places_simple": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places_simple.zip",
    "ne_10m_lakes": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip",
    "ne_10m_rivers_lake_centerlines": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_lake_centerlines.zip",
}
GEOBOUNDARIES = {"ZWE": "ADM2", "MWI": "ADM2", "KEN": "ADM2"}
# name: (first lon tile, last lon tile, first lat tile, last lat tile, pixels per degree)
DEM_REGIONS = {"zimbabwe": (25, 33, -23, -16, 300), "malawi": (32, 35, -18, -10, 300), "kenya": (33, 41, -5, 5, 300)}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def record(entry):
    path = OUT / "sources.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    rows = [r for r in rows if r["file"] != entry["file"]] + [entry]
    path.write_text(json.dumps(sorted(rows, key=lambda r: r["file"]), indent=1), encoding="utf-8")


def fetch(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=UA, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(target, "wb") as handle:
            handle.writelines(response.iter_content(1 << 20))
    return target.stat().st_size


def natural_earth():
    for name, url in NATURAL_EARTH.items():
        folder = OUT / "naturalearth" / name
        archive = OUT / "naturalearth" / f"{name}.zip"
        size = fetch(url, archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(folder)
        record({"file": f"naturalearth/{name}.zip", "url": url, "bytes": size, "sha256": sha256(archive),
                "licence": "public domain (Natural Earth)", "fetched": datetime.now(UTC).isoformat(timespec="seconds")})
        print(f"{name}: {size / 1e6:.1f} MB, {len(list(folder.iterdir()))} files", flush=True)


def fetch_lfs(url, target):
    """The geoBoundaries files are Git LFS objects. If the media host cannot be reached, ask the LFS batch API of the
    same repository for the download link (this is what `git lfs` does) and check the SHA-256 against the pointer."""
    pointer = requests.get(url.replace("https://github.com/wmgeolab/geoBoundaries/raw/",
                                       "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/"),
                           headers=UA, timeout=60).text
    fields = dict(line.split(" ", 1) for line in pointer.strip().splitlines())
    oid, size = fields["oid"].removeprefix("sha256:"), int(fields["size"])
    lfs = {"Accept": "application/vnd.git-lfs+json", "Content-Type": "application/vnd.git-lfs+json", **UA}
    batch = requests.post("https://github.com/wmgeolab/geoBoundaries.git/info/lfs/objects/batch", headers=lfs, timeout=60,
                          json={"operation": "download", "transfers": ["basic"], "objects": [{"oid": oid, "size": size}]})
    batch.raise_for_status()
    action = batch.json()["objects"][0]["actions"]["download"]
    target.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(action["href"], headers={**action.get("header", {}), **UA}, stream=True, timeout=180) as response:
        response.raise_for_status()
        with open(target, "wb") as handle:
            handle.writelines(response.iter_content(1 << 20))
    assert sha256(target) == oid and target.stat().st_size == size, "the file differs from its LFS pointer"
    return size


def geoboundaries():
    for iso, level in GEOBOUNDARIES.items():
        api = f"https://www.geoboundaries.org/api/current/gbOpen/{iso}/{level}/"
        meta = requests.get(api, headers=UA, timeout=60).json()
        url = meta["simplifiedGeometryGeoJSON"]
        target = OUT / "geoboundaries" / f"{iso}_{level}_simplified.geojson"
        try:
            size = fetch(url, target)
        except requests.exceptions.RequestException as error:
            print(f"  direct link failed ({type(error).__name__}); using the Git LFS batch API", flush=True)
            size = fetch_lfs(url, target)
        record({"file": f"geoboundaries/{target.name}", "url": url, "api": api, "bytes": size, "sha256": sha256(target),
                "licence": meta.get("boundaryLicense"), "source": meta.get("boundarySource"),
                "year": meta.get("boundaryYearRepresented"), "units": meta.get("admUnitCount"),
                "fetched": datetime.now(UTC).isoformat(timespec="seconds")})
        print(f"{iso} {level}: {size / 1e6:.2f} MB, {meta.get('admUnitCount')} units, licence {meta.get('boundaryLicense')}, "
              f"source {meta.get('boundarySource')}", flush=True)


def tile_url(lat, lon):
    ns = f"S{abs(lat):02d}" if lat < 0 else f"N{lat:02d}"
    ew = f"W{abs(lon):03d}" if lon < 0 else f"E{lon:03d}"
    name = f"Copernicus_DSM_COG_30_{ns}_00_{ew}_00_DEM"
    return f"https://copernicus-dem-90m.s3.amazonaws.com/{name}/{name}.tif"


ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MAX_RETRY": "4",
           "GDAL_HTTP_RETRY_DELAY": "1", "VSI_CACHE": "TRUE", "GDAL_HTTP_USERAGENT": "GDAL (course project map figures)"}


def read_tile(job):
    import rasterio
    from rasterio.enums import Resampling
    lat, lon, ppd = job
    try:
        with rasterio.Env(**ENV), rasterio.open(tile_url(lat, lon)) as src:
            return lat, lon, src.read(1, out_shape=(ppd, ppd), resampling=Resampling.average).astype("float32")
    except rasterio.errors.RasterioIOError as error:  # a tile that is all ocean does not exist
        return lat, lon, str(error)[:80]


def dem_test():
    import rasterio
    start = time.time()
    with rasterio.Env(**ENV), rasterio.open(tile_url(-18, 30)) as src:
        print("size", src.width, src.height, "dtype", src.dtypes, "overviews", src.overviews(1), "block", src.block_shapes,
              "compress", src.compression, "crs", src.crs)
        print("bounds", src.bounds)
    _, _, tile = read_tile((-18, 30, 300))
    print("tile", getattr(tile, "shape", tile), "min/max", float(np.nanmin(tile)), float(np.nanmax(tile)),
          f"{time.time() - start:.1f} s")


def dem():
    import rasterio
    from rasterio.transform import from_origin
    for name, (lon0, lon1, lat0, lat1, ppd) in DEM_REGIONS.items():
        jobs = [(lat, lon, ppd) for lat in range(lat0, lat1 + 1) for lon in range(lon0, lon1 + 1)]
        start = time.time()
        with ThreadPoolExecutor(12) as pool:
            tiles = list(pool.map(read_tile, jobs))
        rows, cols = (lat1 - lat0 + 1) * ppd, (lon1 - lon0 + 1) * ppd
        mosaic = np.zeros((rows, cols), dtype="float32")
        missing = 0
        for lat, lon, tile in tiles:
            if isinstance(tile, str):
                missing += 1
                continue
            r = (lat1 - lat) * ppd  # row 0 is the northern edge
            c = (lon - lon0) * ppd
            mosaic[r:r + ppd, c:c + ppd] = tile
        target = OUT / "dem" / f"copdem90_{name}_{ppd}ppd.tif"
        target.parent.mkdir(parents=True, exist_ok=True)
        profile = {"driver": "GTiff", "height": rows, "width": cols, "count": 1, "dtype": "int16", "crs": "EPSG:4326",
                       "transform": from_origin(lon0, lat1 + 1, 1 / ppd, 1 / ppd), "compress": "deflate", "predictor": 2, "tiled": True}
        with rasterio.open(target, "w", **profile) as dst:
            dst.write(np.round(mosaic).astype("int16"), 1)
        record({"file": f"dem/{target.name}", "url": "https://copernicus-dem-90m.s3.amazonaws.com/ (overview reads)",
                "bytes": target.stat().st_size, "sha256": sha256(target), "tiles": len(jobs), "missing_tiles": missing,
                "licence": "Copernicus DEM GLO-90, free with attribution (ESA, Airbus, DLR)",
                "fetched": datetime.now(UTC).isoformat(timespec="seconds")})
        print(f"{name}: {len(jobs)} tiles ({missing} missing), {cols} x {rows} px, {target.stat().st_size / 1e6:.1f} MB, "
              f"elevation {mosaic.min():.0f} to {mosaic.max():.0f} m, {time.time() - start:.0f} s", flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for stage in sys.argv[1:]:
        print(f"== {stage} ==", flush=True)
        {"ne": natural_earth, "gb": geoboundaries, "demtest": dem_test, "dem": dem}[stage]()
