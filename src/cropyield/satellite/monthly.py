"""One value per band per calendar month over the field or point AOI.

The downloader keeps at most one clear scene per month. For each month of the season window
the series holds the median reflectance of the field pixels that are valid (clear SCL class,
all bands finite) in that month's scene. Field pixels are those whose centres fall inside the
polygon (``Chip.aoi_interior``); only a polygon too thin to contain a pixel centre falls back
to the downloader's all-touched mask. A point record has its single pixel. Months without an
accepted scene, or without a single valid field pixel, are NaN. Bands keep their Sentinel-2 codes so the same
series feeds Presto and the NDVI/GCVI ridge baseline (B03 green, B04 red, B08 nir).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from cropyield.satellite.chips import Chip, Scene


@dataclass
class MonthlySeries:
    obs_id: str
    months: list[str]           # "YYYY-MM", consecutive from the window start to its end
    bands: tuple[str, ...]      # Sentinel-2 band codes, same order as ``values`` columns
    values: np.ndarray          # (n_months, n_bands) float32 reflectance, NaN when missing
    n_pixels: np.ndarray        # (n_months,) valid field pixels behind each row (0 when NaN)
    item_ids: list[str | None]  # scene used for each month
    pixel_rule: str             # "interior" (pixel centres inside the field) or "touched" (fallback)

    def band(self, code: str) -> np.ndarray:
        return self.values[:, self.bands.index(code)]

    @property
    def missing(self) -> np.ndarray:
        """True for months with no value (no scene, or no valid AOI pixel)."""
        return np.isnan(self.values).all(axis=1)


def month_range(start: date, end: date) -> list[str]:
    """Calendar months from ``start`` to ``end`` inclusive, as "YYYY-MM"."""
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def monthly_series(chip: Chip, start: date, end: date, min_pixels: int = 1) -> MonthlySeries:
    """Median reflectance over valid field pixels for each month of [start, end].

    The chip must have been downloaded for a window covering [start, end]; otherwise months
    the downloader never searched would look like cloudy months.
    """
    if chip.status in ("error", "partial_error"):
        raise ValueError(f"{chip.obs_id}: downloader status {chip.status!r}; months that failed to "
                         "download would be indistinguishable from cloudy months")
    if chip.start_date is None or chip.end_date is None or chip.start_date > start or chip.end_date < end:
        raise ValueError(f"{chip.obs_id}: chip window {chip.start_date}..{chip.end_date} "
                         f"does not cover the requested {start}..{end}")
    months = month_range(start, end)
    field, pixel_rule = (chip.aoi_interior, "interior") if chip.aoi_interior.any() else (chip.aoi, "touched")
    chosen: list[Scene | None] = [None] * len(months)
    for scene in chip.scenes:
        key = scene.date.strftime("%Y-%m")
        if key not in months:
            continue  # scene outside the requested window
        i = months.index(key)
        # The downloader accepts at most one scene per month. If a folder ever holds more,
        # keep the scene with the larger clear AOI fraction (earlier date on ties).
        if chosen[i] is None or scene.clear_fraction_aoi > chosen[i].clear_fraction_aoi:
            chosen[i] = scene
    values = np.full((len(months), len(chip.bands)), np.nan, dtype="float32")
    n_pixels = np.zeros(len(months), dtype=int)
    item_ids: list[str | None] = [None] * len(months)
    for i, scene in enumerate(chosen):
        if scene is None:
            continue
        pixels = field & scene.valid
        if pixels.sum() < min_pixels:
            continue  # month stays NaN: no usable pixel over the field or point
        values[i] = np.nanmedian(scene.reflectance[:, pixels], axis=1)
        n_pixels[i] = int(pixels.sum())
        item_ids[i] = scene.item_id
    return MonthlySeries(chip.obs_id, months, chip.bands, values, n_pixels, item_ids, pixel_rule)
