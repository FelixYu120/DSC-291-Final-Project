"""Step 3 of the pass archive: read the native pixel of every band for every pass, straight from the public
Level-2A cloud-optimized files (Earth Search; Planetary Computer where Earth Search has no file). Nothing is
resampled, masked or averaged here.

The unit of work is one image block (10.24 km square of one MGRS tile) of one scene: all locations in that
block are read together, because the block must be downloaded whole (about 7 MB for all bands). The plan goes one country-year after the other
(``STEPS``), each read completely before the next, so a stop leaves whole country-years done. Inside a step, units of the
main growing season are read first (Kenya February to September of the harvest year; Malawi and Zimbabwe October
of the year before to June), then the other months of the two calendar years. Inside each part the blocks with
the most field-seasons come first, in turn for each cohort. Each finished unit is one small Parquet file; a
second run skips it. A unit that fails writes nothing and is tried again next run.

Run:      python -m cropyield.archive.sampling --minutes 30 --processes 6
Plan:     python -m cropyield.archive.sampling --plan
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
import shapely
from pyproj import Transformer
from rasterio.windows import Window
from shapely.ops import transform as shapely_transform

from cropyield.archive import paths

BLOCK = 1024                      # 10 m pixels per image block
MB_PER_UNIT = 7.4                 # measured: all Level-2A assets of one block
NEWLINE = chr(10)
GROUP_ORDER = ["kenya_oaf_2019_2020", "zimbabwe_lacuna_2022_2023", "zimbabwe_2024", "malawi_2023", "malawi_2022"]
# The read order (owner, 19 Nov 2026): one country-year after the other, each finished before the next.
STEPS = {1: "Zimbabwe 2023 (Lacuna)", 2: "Kenya 2020", 3: "Kenya 2019", 4: "Malawi 2023", 5: "Malawi 2022",
         6: "Zimbabwe 2024, measured yield", 7: "Zimbabwe 2022 (Lacuna)", 8: "Kenya 2018", 9: "Kenya 2017",
         10: "Kenya 2016", 11: "Malawi 2020", 12: "Zimbabwe 2024, recorded zero",
         13: "Zimbabwe 2024, no yield in the source", 14: "other"}
GDAL = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "2", "GDAL_HTTP_TIMEOUT": "120",
        # give up a dead request early: no connection in 15 s, or under 20 kB/s for 30 s (the unit is read again)
        "GDAL_HTTP_CONNECTTIMEOUT": "15", "GDAL_HTTP_LOW_SPEED_LIMIT": "20000", "GDAL_HTTP_LOW_SPEED_TIME": "30",
        "GDAL_INGESTED_BYTES_AT_OPEN": "65536", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "VSI_CACHE": "FALSE"}


def footprint_pixels(locations: pd.DataFrame, placed: pd.DataFrame, tiles: pd.DataFrame, cache: Path) -> pd.DataFrame:
    """The native pixels of each location in each tile grid.

    Point: the one pixel that holds the point, at 10, 20 and 60 m. Polygon: every pixel whose cell meets the
    polygon's bounding box grown by one pixel, with ``center_inside`` and the exact ``area_fraction`` of the cell
    inside the polygon, so another edge rule can be applied later.
    """
    if cache.exists():
        return pd.read_parquet(cache)
    kind = locations.set_index("location_id").geometry_type
    parts = []
    points = placed[placed.location_id.map(kind) == "point"]
    for size in (10, 20, 60):
        parts.append(pd.DataFrame({"location_id": points.location_id, "mgrs_tile": points.mgrs_tile, "res_m": size,
                                   "px_row": points[f"row{size}"], "px_col": points[f"col{size}"],
                                   "center_inside": True, "area_fraction": np.nan, "is_point_pixel": True}))
    grid = tiles.set_index("mgrs_tile")
    wkt = locations.set_index("location_id").geometry_wkt_wgs84
    rows = []
    for pair in placed[placed.location_id.map(kind) == "polygon"].itertuples():
        tile = grid.loc[pair.mgrs_tile]
        to_tile = Transformer.from_crs(4326, int(tile.epsg), always_xy=True).transform
        polygon = shapely_transform(to_tile, shapely.from_wkt(wkt[pair.location_id]))
        west, south, east, north = polygon.bounds
        for size in (10, 20, 60):
            limit = int(tile.size_m // size)
            first_col, last_col = int((west - tile.ulx) // size) - 1, int((east - tile.ulx) // size) + 1
            first_row, last_row = int((tile.uly - north) // size) - 1, int((tile.uly - south) // size) + 1
            for row in range(max(first_row, 0), min(last_row, limit - 1) + 1):
                for col in range(max(first_col, 0), min(last_col, limit - 1) + 1):
                    x0, y1 = tile.ulx + col * size, tile.uly - row * size
                    cell = shapely.box(x0, y1 - size, x0 + size, y1)
                    rows.append((pair.location_id, pair.mgrs_tile, size, row, col,
                                 bool(polygon.contains(shapely.Point(x0 + size / 2, y1 - size / 2))),
                                 polygon.intersection(cell).area / (size * size), False))
    parts.append(pd.DataFrame(rows, columns=["location_id", "mgrs_tile", "res_m", "px_row", "px_col", "center_inside",
                                             "area_fraction", "is_point_pixel"]))
    table = pd.concat(parts, ignore_index=True)
    table.to_parquet(cache, index=False)
    return table


TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
_token = {"value": "", "expires": 0.0}
_token_lock = threading.Lock()


def signed(href: str) -> str:
    """A Planetary Computer file needs a free read token in the address; other files are returned as they are."""
    if ".blob.core.windows.net/" not in href:
        return href
    with _token_lock:
        if time.time() > _token["expires"] - 600:       # renew ten minutes before the end
            answer = requests.get(TOKEN_URL, timeout=60)
            answer.raise_for_status()
            reply = answer.json()
            _token["value"] = reply["token"]
            _token["expires"] = pd.Timestamp(reply["msft:expiry"]).timestamp()
        return f"{href}?{_token['value']}"


def step_of(fields: pd.DataFrame) -> pd.Series:
    """The step (key of ``STEPS``) of each field-season, from dataset, country, harvest year and old cohort."""
    year, country, dataset = fields.harvest_year, fields.country_iso3, fields.dataset
    in_2024 = fields.legacy_cohort == "zimbabwe_2024"
    measured = fields.legacy_include_primary.fillna(False).astype(bool)
    kenya = (dataset == "one_acre_fund_full") & (country == "KEN")
    rules = [
        ((dataset == "zimbabwe") & (year == 2023), 1), (kenya & (year == 2020), 2), (kenya & (year == 2019), 3),
        (dataset == "malawi_2023", 4), (dataset == "malawi_2022", 5), (in_2024 & measured, 6),
        ((dataset == "zimbabwe") & (year == 2022), 7), (kenya & (year == 2018), 8), (kenya & (year == 2017), 9),
        (kenya & (year == 2016), 10), ((dataset == "one_acre_fund_full") & (country == "MWI"), 11),
        (in_2024 & ~measured, 12), ((dataset == "vision_guided_yield_estimation") & fields.legacy_cohort.isna(), 13)]
    return pd.Series(np.select([rule for rule, _ in rules], [step for _, step in rules], default=14), index=fields.index)


def _months(first: int, last: int) -> int:
    """Bit mask of the calendar months ``first`` to ``last`` (bit 0 = January)."""
    return sum(1 << (month - 1) for month in range(first, last + 1))


def plan(staging: Path) -> pd.DataFrame:
    """Every (tile, block, granule) unit with one readable public file, in the order it will be read."""
    survey, catalog = paths.staging_dir("survey"), paths.staging_dir("catalog")
    fields = pd.read_parquet(survey / "fields.parquet")
    fields = fields[fields.location_id.notna() & fields.harvest_year.notna()].copy()
    fields["group"] = fields.legacy_cohort.fillna(fields.dataset + "_other")
    fields["step"] = step_of(fields)
    placed = pd.read_parquet(catalog / "location_tiles.parquet")
    placed["block_row"], placed["block_col"] = placed.row10 // BLOCK, placed.col10 // BLOCK
    in_block = fields[["field_season_id", "location_id", "harvest_year", "group", "country_iso3", "step"]].merge(
        placed[["location_id", "mgrs_tile", "block_row", "block_col"]], on="location_id")
    years = pd.concat([in_block.assign(year=in_block.harvest_year), in_block.assign(year=in_block.harvest_year - 1)])
    # months of the main growing season in each block and calendar year, as a 12-bit mask (bit 0 = January)
    kenya, current = years.country_iso3 == "KEN", years.year == years.harvest_year
    years["season_months"] = np.select([kenya & current, ~kenya & current, ~kenya & ~current],
                                       [_months(2, 9), _months(1, 6), _months(10, 12)], default=0)
    season = (years.groupby(["mgrs_tile", "block_row", "block_col", "year"]).season_months
              .agg(lambda masks: int(np.bitwise_or.reduce(masks.to_numpy(dtype=np.int64)))).reset_index())
    season["year"] = season.year.astype(int)
    # a block and calendar year belongs to the earliest step among the field-seasons that need it
    first_step = years.groupby(["mgrs_tile", "block_row", "block_col", "year"]).step.min().reset_index()
    first_step["year"] = first_step.year.astype(int)
    block_years = (years.groupby(["group", "mgrs_tile", "block_row", "block_col", "year"])
                   .field_season_id.nunique().rename("n_field_seasons").reset_index())
    block_years["year"] = block_years.year.astype(int)

    granules = pd.read_parquet(catalog / "granules.parquet")[["granule_id", "mgrs_tile", "year", "sensing_time"]]
    scenes, items = pd.read_parquet(catalog / "scenes.parquet"), pd.read_parquet(catalog / "scene_items.parquet")
    if (catalog / "scene_items_pc.parquet").exists():     # the second public copy, for granules with no other file
        scenes = pd.concat([scenes, pd.read_parquet(catalog / "scenes_pc.parquet")], ignore_index=True)
        items = pd.concat([items, pd.read_parquet(catalog / "scene_items_pc.parquet")], ignore_index=True)
    items = items[items.assets_json != "{}"]              # 58 old items list no file that can be read
    items = items.merge(scenes[["scene_id", "granule_id", "level"]], on="scene_id")
    # Collection 1 first, then the older Earth Search collection, then Planetary Computer
    items["rank"] = items.collection.map({"sentinel-2-c1-l2a": 0, "sentinel-2-l2a": 1}).fillna(2).astype(int)
    best = items.sort_values(["granule_id", "rank", "processing_baseline", "item_id"],
                             ascending=[True, True, False, True]).drop_duplicates("granule_id")
    units = block_years.merge(granules, on=["mgrs_tile", "year"]).merge(
        best[["granule_id", "scene_id", "collection", "item_id"]], on="granule_id")

    # drop a unit when the catalogue footprint says the sensor swath misses every location of the block
    expected = pd.read_parquet(catalog / "location_granules.parquet")
    seen = expected.merge(placed[["location_id", "mgrs_tile", "block_row", "block_col"]], on="location_id")
    seen = seen.merge(granules[["granule_id", "mgrs_tile"]], on=["granule_id", "mgrs_tile"])
    seen["maybe"] = seen.in_catalogue_footprint.fillna(1.0) > 0
    touched = seen.groupby(["mgrs_tile", "block_row", "block_col", "granule_id"]).maybe.any().reset_index()
    units = units.merge(touched, on=["mgrs_tile", "block_row", "block_col", "granule_id"])
    units = units[units.maybe].drop(columns="maybe")

    # order: cohorts in turn, inside a cohort the block with the most field-seasons first
    size = units.groupby(["group", "mgrs_tile", "block_row", "block_col"]).n_field_seasons.max().rename("block_size")
    units = units.merge(size.reset_index(), on=["group", "mgrs_tile", "block_row", "block_col"])
    blocks = units[["group", "mgrs_tile", "block_row", "block_col", "block_size"]].drop_duplicates()
    blocks["turn"] = blocks.groupby("group").block_size.rank(method="first", ascending=False)
    order = {name: position for position, name in enumerate(GROUP_ORDER)}
    blocks["group_order"] = blocks.group.map(order).fillna(len(order)).astype(int)
    units = units.merge(blocks[["group", "mgrs_tile", "block_row", "block_col", "turn", "group_order"]],
                        on=["group", "mgrs_tile", "block_row", "block_col"])
    units = units.merge(season, on=["mgrs_tile", "block_row", "block_col", "year"], how="left")
    units = units.merge(first_step, on=["mgrs_tile", "block_row", "block_col", "year"], how="left")
    units["step"] = units.step.fillna(max(STEPS)).astype(int)
    month = pd.to_datetime(units.sensing_time, utc=True).dt.month
    units["in_season"] = ((units.season_months.fillna(0).astype("int64") // (2 ** (month - 1))) % 2).astype(bool)
    units = units.sort_values(["step", "in_season", "turn", "group_order", "group", "sensing_time"],
                              ascending=[True, False, True, True, True, True])
    units = units.drop_duplicates(["mgrs_tile", "block_row", "block_col", "item_id"]).reset_index(drop=True)
    units.to_parquet(staging / "plan.parquet", index=False)
    return units


def progress_by_step(staging: Path | None = None) -> list[dict]:
    """Units planned and read in each step of the last written plan."""
    staging = staging or paths.staging_dir("samples")
    units = pd.read_parquet(staging / "plan.parquet", columns=["step", "mgrs_tile", "block_row", "block_col", "item_id"])
    read = {(path.parts[-3], path.parts[-2], path.stem) for path in (staging / "shards").glob("*/*/*.parquet")}
    block = "b" + units.block_row.astype(str).str.zfill(2) + "_" + units.block_col.astype(str).str.zfill(2)
    units["done"] = [key in read for key in zip(units.mgrs_tile, block, units.item_id)]
    table = units.groupby("step").done.agg(["size", "sum"])
    return [{"step": int(step), "name": STEPS.get(int(step), "other"), "units": int(row["size"]), "read": int(row["sum"]),
             "complete": bool(row["size"] == row["sum"])} for step, row in table.iterrows()]


def load_assets() -> dict[str, str]:
    """Item id -> its asset links (JSON text), for every public copy in the catalogue."""
    catalog = paths.staging_dir("catalog")
    files = [catalog / "scene_items.parquet", catalog / "scene_items_pc.parquet"]
    items = pd.concat([pd.read_parquet(file, columns=["item_id", "assets_json"]) for file in files if file.exists()])
    return dict(zip(items.item_id, items.assets_json))


def shard_path(staging: Path, unit) -> Path:
    return staging / "shards" / unit.mgrs_tile / f"b{unit.block_row:02d}_{unit.block_col:02d}" / f"{unit.item_id}.parquet"


def read_asset(href: str, pixels: dict[int, pd.DataFrame]) -> tuple[int, np.ndarray]:
    """DN of every wanted pixel of one asset. ``pixels`` maps a resolution to its (px_row, px_col) table."""
    target = "/vsicurl/" + signed(href) if href.startswith("http") else href
    with rasterio.Env(**GDAL), rasterio.open(target) as source:
        size = round(source.res[0])
        wanted = pixels[size]
        rows, cols = wanted.px_row.to_numpy(), wanted.px_col.to_numpy()
        high, wide = source.block_shapes[0]
        values = np.zeros(len(wanted), dtype=np.int32)
        for block_row, block_col in sorted(set(zip(rows // high, cols // wide))):
            here = (rows // high == block_row) & (cols // wide == block_col)
            window = Window(block_col * wide, block_row * high, min(wide, source.width - block_col * wide),
                            min(high, source.height - block_row * high))
            data = source.read(1, window=window)
            values[here] = data[rows[here] - block_row * high, cols[here] - block_col * wide]
        return size, values


def run_unit(unit, assets_json: str, pixels_of_block: pd.DataFrame, pool: ThreadPoolExecutor) -> pd.DataFrame:
    assets = json.loads(assets_json)
    pixels = {size: part.reset_index(drop=True) for size, part in pixels_of_block.groupby("res_m")}
    futures = {band: pool.submit(read_asset, asset["href"], pixels) for band, asset in assets.items()}
    parts = []
    for band, future in futures.items():
        size, values = future.result()
        part = pixels[size][["location_id", "res_m", "px_row", "px_col"]].copy()
        part["band"], part["dn"] = band, values
        parts.append(part)
    table = pd.concat(parts, ignore_index=True)
    table["item_id"], table["scene_id"] = unit.item_id, unit.scene_id
    return table


def read_units(units: pd.DataFrame, minutes: float, threads: int, label: str = "",
               until: float | None = None) -> tuple[int, int]:
    """Read the open units of ``units`` in their order. Returns (read, failed).

    No new unit is started after ``minutes`` or after the clock time ``until`` (seconds since 1970)."""
    staging, catalog = paths.staging_dir("samples"), paths.staging_dir("catalog")
    locations = pd.read_parquet(paths.staging_dir("survey") / "locations.parquet")
    placed = pd.read_parquet(catalog / "location_tiles.parquet")
    tiles = pd.read_parquet(catalog / "tiles.parquet")
    pixels = footprint_pixels(locations, placed, tiles, staging / "footprint_pixels.parquet")
    placed["block_row"], placed["block_col"] = placed.row10 // BLOCK, placed.col10 // BLOCK
    pixels = pixels.merge(placed[["location_id", "mgrs_tile", "block_row", "block_col"]], on=["location_id", "mgrs_tile"])
    by_block = {key: part for key, part in pixels.groupby(["mgrs_tile", "block_row", "block_col"])}
    assets = load_assets()
    todo = [unit for unit in units.itertuples() if not shard_path(staging, unit).exists()]
    started, done, failed, skipped = time.time(), 0, 0, 0
    limits = [limit for limit in (started + minutes * 60 if minutes else None, until) if limit]
    deadline = min(limits) if limits else None
    with (open(staging / f"errors{label}.jsonl", "a", encoding="utf-8") as errors,
          ThreadPoolExecutor(threads) as asset_pool, ThreadPoolExecutor(max(2, threads // 8)) as unit_pool):
        def work(unit):
            if deadline and time.time() >= deadline:
                return "skipped"
            target = shard_path(staging, unit)
            try:
                table = run_unit(unit, assets[unit.item_id], by_block[(unit.mgrs_tile, unit.block_row, unit.block_col)],
                                 asset_pool)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(f".part{label}")
                table.to_parquet(temporary, index=False)
                temporary.replace(target)
                return None
            except Exception as error:      # noqa: BLE001 - the unit stays open and is read again next run
                return {"item_id": unit.item_id, "mgrs_tile": unit.mgrs_tile, "block_row": int(unit.block_row),
                        "block_col": int(unit.block_col), "error": str(error)[:300], "at": time.time()}
        # one continuous queue: a slow unit holds one worker and the others go on
        for count, problem in enumerate(unit_pool.map(work, todo), start=1):
            if problem == "skipped":
                skipped += 1
            elif problem:
                failed += 1
                errors.write(json.dumps(problem) + NEWLINE)
                errors.flush()
            else:
                done += 1
            if count % 250 == 0 and not skipped:
                spent = (time.time() - started) / 60
                print(f"worker{label}: {done} units read, {failed} failed, {spent:.1f} min, "
                      f"{done / max(spent, 0.01):.0f} units a minute", flush=True)
    return done, failed


def count_shards(staging: Path) -> int:
    return sum(1 for _ in (staging / "shards").glob("*/*/*.parquet")) if (staging / "shards").exists() else 0


def run(minutes: float, threads: int, limit: int | None, processes: int = 1, until: float | None = None) -> dict:
    """Plan, then read the open units. ``threads`` is per process.

    Python runs one thread at a time, so one process reads about 2 units a second however many threads it has.
    More speed needs more processes: each takes every n-th unit of the plan, so the read order stays the same.
    """
    staging = paths.staging_dir("samples")
    staging.mkdir(parents=True, exist_ok=True)
    units = plan(staging)
    before = count_shards(staging)
    is_open = [not shard_path(staging, unit).exists() for unit in units.itertuples()]
    n_open = sum(is_open)
    print(f"{len(units)} units planned, {len(units) - n_open} done, {n_open} to read "
          f"(about {n_open * MB_PER_UNIT / 1000:.0f} GB)", flush=True)
    started = time.time()
    if processes <= 1:
        todo = units[is_open]
        done, failed = read_units(todo.head(limit) if limit else todo, minutes, threads, until=until)
    else:
        command = [sys.executable, "-u", "-m", "cropyield.archive.sampling", "--threads", str(threads),
                   "--minutes", str(minutes), "--of", str(processes), *(["--until", str(until)] if until else [])]
        workers = [subprocess.Popen([*command, "--worker", str(number)]) for number in range(processes)]
        failed = sum(worker.wait() != 0 for worker in workers)      # a worker that ended badly; its units stay open
        done = count_shards(staging) - before
    return {"read_now": done, "failed_now": failed, "left": n_open - done, "planned": len(units),
            "minutes": round((time.time() - started) / 60, 1)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=30, help="stop starting new units after this time (0 = no limit)")
    parser.add_argument("--threads", type=int, default=32, help="threads in each process")
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="read at most this many units (one process only)")
    parser.add_argument("--plan", action="store_true", help="only write the plan and print its size")
    parser.add_argument("--worker", type=int, default=None, help=argparse.SUPPRESS)   # started by run(), not by hand
    parser.add_argument("--of", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--until", type=float, default=None, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.worker is not None:
        share = pd.read_parquet(paths.staging_dir("samples") / "plan.parquet").iloc[arguments.worker::arguments.of]
        read_units(share, arguments.minutes, arguments.threads, label=f"_{arguments.worker}", until=arguments.until)
    elif arguments.plan:
        folder = paths.staging_dir("samples")
        folder.mkdir(parents=True, exist_ok=True)
        table = plan(folder)
        print(f"{len(table)} units, about {len(table) * MB_PER_UNIT / 1000:.0f} GB")
        print(table.groupby("group").size().to_string())
    else:
        print(json.dumps(run(arguments.minutes, arguments.threads, arguments.limit, arguments.processes,
                             arguments.until), indent=2))
