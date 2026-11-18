"""Window features from the data v2 chips. Label-free: no yield is read.

    python experiments/footprint/windows.py              # -> experiments/footprint/windows.parquet

For each model row of the Zimbabwe point cohorts and each clear month of the database, this reads the accepted scene
of that month (`coverage.item_id`) in a 7 x 7 pixel window around the point pixel, and keeps, for w = 1, 3, 5, 7:
the median of each band over the clear pixels (`valid_mask.tif`: SCL 4, 5 or 6 and all bands finite), the five indices
from those medians, the std (ddof 0) of each band over the clear pixels, and the std of each index pixel by pixel.
w = 1 is today's point value: `monthly_series` takes the median of the single point pixel.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.xy import MIN_CLEAR_MONTHS
from cropyield.features.indices import INDICES, vegetation_indices
from cropyield.longpath import filesystem_path
from cropyield.satellite.monthly import MonthlySeries

DATABASE = ROOT / "data" / "v2" / "cropyield.duckdb"
OUT = HERE / "windows.parquet"
COHORTS = ("zimbabwe_lacuna_2022_2023", "zimbabwe_2024")
SIZES = (1, 3, 5, 7)
HALF = max(SIZES) // 2
BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
BAND_COLUMNS = tuple(b.lower() for b in BANDS)
CLEAR_SCL = (4, 5, 6)


def jobs(cohort: str, database: Path = DATABASE) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """(obs_id, record_dir, [(month, item_id), ...]) for every model row of the cohort, clear months only."""
    with duckdb.connect(str(database), read_only=True) as con:
        rows = con.execute("""SELECT m.obs_id, d.record_dir, c.month, c.item_id
                              FROM master m JOIN downloads d USING (obs_id) JOIN coverage c USING (obs_id)
                              WHERE m.cohort = ? AND m.include_primary AND m.months_with_data >= ?
                                AND c.state = 'clear'
                              ORDER BY m.obs_id, c.month""", [cohort, MIN_CLEAR_MONTHS]).df()
    return [(obs_id, part.record_dir.iloc[0], list(zip(part.month, part.item_id)))
            for obs_id, part in rows.groupby("obs_id", sort=True)]


def indices_of(pixels: np.ndarray) -> pd.DataFrame:
    """The five indices of each column of `pixels` (10 bands x n), with the library formula (inf becomes NaN)."""
    series = MonthlySeries(obs_id="", months=[str(i) for i in range(pixels.shape[1])], bands=BANDS,
                           values=pixels.T, n_pixels=np.ones(pixels.shape[1], dtype=int), item_ids=[None] * pixels.shape[1],
                           pixel_rule="window")
    return vegetation_indices(series)


def window_stats(reflectance: np.ndarray, valid: np.ndarray, sizes=SIZES) -> list[dict]:
    """Stats of the clear pixels in each centred w x w window of a (10, 2h+1, 2h+1) block.

    The median runs in float32, as `monthly_series` does. The std runs in float64. The centre must be clear.
    """
    half = reflectance.shape[1] // 2
    if not valid[half, half]:
        raise ValueError("the point pixel is not clear in a clear month")
    out = []
    for w in sizes:
        k = w // 2
        part = slice(half - k, half + k + 1)
        pixels = reflectance[:, part, part][:, valid[part, part]]           # (10, n) float32, all finite
        median = np.nanmedian(pixels, axis=1)                                # float32, like monthly_series
        row = {"w": w, "n_valid": pixels.shape[1], "n_window": w * w}
        row |= {c: float(v) for c, v in zip(BAND_COLUMNS, median)}
        row |= indices_of(median[:, None]).iloc[0].to_dict()
        row |= {f"sd_{c}": float(v) for c, v in zip(BAND_COLUMNS, pixels.astype("float64").std(axis=1))}
        per_pixel = indices_of(pixels).to_numpy()
        with np.errstate(invalid="ignore"):
            sd = [float(np.nanstd(per_pixel[:, j])) if np.isfinite(per_pixel[:, j]).any() else float("nan")
                  for j in range(len(INDICES))]
        row |= {f"sd_{i}": v for i, v in zip(INDICES, sd)}
        out.append(row)
    return out


def record_rows(job: tuple[str, str, list[tuple[str, str]]]) -> list[dict]:
    """Window stats of one record, one row per clear month and window size."""
    obs_id, record_dir, months = job
    folder = ROOT / record_dir
    with rasterio.open(filesystem_path(folder / "aoi_mask.tif")) as src:
        aoi = src.read(1).astype(bool)
    points = np.argwhere(aoi)
    if len(points) != 1:
        raise ValueError(f"{obs_id}: the AOI has {len(points)} pixels, not one point pixel")
    r, c = points[0]
    if r - HALF < 0 or c - HALF < 0 or r + HALF >= aoi.shape[0] or c + HALF >= aoi.shape[1]:
        raise ValueError(f"{obs_id}: the 7 x 7 window leaves the chip")
    window = Window(int(c) - HALF, int(r) - HALF, 2 * HALF + 1, 2 * HALF + 1)
    rows = []
    for month, item_id in months:
        scene = folder / item_id
        with rasterio.open(filesystem_path(scene / "reflectance.tif")) as src:
            if tuple(src.descriptions) != BANDS:
                raise ValueError(f"{scene}: band order {src.descriptions}")
            reflectance = src.read(window=window).astype("float32")
            if src.nodata is not None:
                reflectance[reflectance == src.nodata] = np.nan
        with rasterio.open(filesystem_path(scene / "scl.tif")) as src:
            scl = src.read(1, window=window)
        with rasterio.open(filesystem_path(scene / "valid_mask.tif")) as src:
            valid = src.read(1, window=window).astype(bool)
        if not np.array_equal(valid, np.isin(scl, CLEAR_SCL) & np.isfinite(reflectance).all(axis=0)):
            raise ValueError(f"{scene}: valid_mask.tif differs from SCL 4/5/6 and finite bands")
        rows += [{"obs_id": obs_id, "month": month, "item_id": item_id, **row}
                 for row in window_stats(reflectance, valid)]
    return rows


def extract(cohort: str, workers: int = 12) -> pd.DataFrame:
    todo = jobs(cohort)
    with ProcessPoolExecutor(workers) as pool:
        parts = list(pool.map(record_rows, todo, chunksize=20))
    frame = pd.DataFrame([row for part in parts for row in part])
    return frame.assign(cohort=cohort)


def main() -> int:
    frames = []
    for cohort in COHORTS:
        frame = extract(cohort)
        print(f"{cohort}: {frame.obs_id.nunique():,} fields, {len(frame) // len(SIZES):,} clear field-months", flush=True)
        frames.append(frame)
    table = pd.concat(frames, ignore_index=True)
    table.to_parquet(OUT, index=False)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(table):,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
