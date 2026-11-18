"""Draw the atlas's offline, georeferenced EOxCloudless 2016 satellite imagery."""

from __future__ import annotations

import json
from functools import lru_cache
from math import ceil, floor
from pathlib import Path

import rasterio
from matplotlib.colors import LinearSegmentedColormap
from rasterio.enums import Resampling
from rasterio.windows import Window, from_bounds
from rasterio.windows import bounds as window_bounds

BASEMAP_CREDIT = (
    "Grayscale EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH "
    "(Contains modified Copernicus Sentinel data 2016) · CC BY 4.0"
)
SOURCES = Path("results/visual_atlas/sources")
RAMPS = {
    "dark": LinearSegmentedColormap.from_list(
        "satellite_charcoal", ["#11161a", "#62686a", "#b6b8b3"]
    ),
    "light": LinearSegmentedColormap.from_list(
        "satellite_silver", ["#879093", "#c5c9c7", "#f1f0e9"]
    ),
}


@lru_cache(maxsize=2)
def _regions(root):
    provenance = json.loads(
        (root / SOURCES / "satellite_basemap_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    return sorted(
        provenance["regions"].values(), key=lambda item: item["pixel_spacing_metres"]
    )


def draw_basemap(ax, root, bounds=None, *, tone="dark"):
    """Draw imagery with existing axis limits preserved.

    Bounds, when supplied, are (west, south, east, north) in atlas LAEA metres.
    A regional inset automatically uses the highest-resolution raster covering
    its full requested view. Both tones use the same fixed luminance stretch.
    """
    root = Path(root).resolve()
    regions = _regions(root)
    region = regions[-1]
    if bounds is None:
        bounds = region["laea_bounds_left_bottom_right_top"]
    west, south, east, north = bounds
    if west >= east or south >= north:
        raise ValueError(
            "Pass ordered (west, south, east, north) bounds in LAEA metres."
        )
    for candidate in regions:
        left, bottom, right, top = candidate["laea_bounds_left_bottom_right_top"]
        if left <= west and south >= bottom and right >= east and north <= top:
            region = candidate
            break
    cmap = RAMPS[tone]
    with rasterio.open(root / SOURCES / region["file"]) as raster:
        requested = from_bounds(west, south, east, north, raster.transform)
        left = max(0, floor(requested.col_off))
        top = max(0, floor(requested.row_off))
        right = min(raster.width, ceil(requested.col_off + requested.width))
        bottom = min(raster.height, ceil(requested.row_off + requested.height))
        if right <= left or bottom <= top:
            raise ValueError(
                "Map extent lies outside the bundled Zimbabwe satellite imagery."
            )
        window = Window(left, top, right - left, bottom - top)
        factor = min(1.0, 1600 / max(window.height, window.width))
        pixels = raster.read(
            1,
            window=window,
            out_shape=(
                max(1, round(window.height * factor)),
                max(1, round(window.width * factor)),
            ),
            resampling=Resampling.average,
        )
        x0, y0, x1, y1 = window_bounds(window, raster.transform)

    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    autoscale_x, autoscale_y = ax.get_autoscalex_on(), ax.get_autoscaley_on()
    artist = ax.imshow(
        pixels,
        extent=(x0, x1, y0, y1),
        origin="upper",
        interpolation="bilinear",
        cmap=cmap,
        vmin=35,
        vmax=150,
        aspect=ax.get_aspect(),
        zorder=-5,
    )
    ax.set_xlim(xlim, auto=autoscale_x)
    ax.set_ylim(ylim, auto=autoscale_y)
    return artist
