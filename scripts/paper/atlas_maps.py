"""Rebuild the Zimbabwe atlas maps from checked-in data, without external services."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import ConnectionPatch
from pyproj import Transformer
from scipy.ndimage import distance_transform_edt, map_coordinates
from shapely.geometry import box, shape
from shapely.ops import transform

if __package__:
    from .atlas_basemap import BASEMAP_CREDIT, draw_basemap
else:  # Supports direct execution from the repository root.
    from atlas_basemap import BASEMAP_CREDIT, draw_basemap

YEARS = (2022, 2023, 2024)
DETAIL_CANDIDATE_GRID_METRES = 25_000
CALLOUT = "#ffdb91"
INK = "#213b42"
MUTED = "#52666a"
YIELD_LIMIT = 8
YIELD_CMAP = LinearSegmentedColormap.from_list(
    "zimbabwe_yield",
    ["#3974c1", "#3cb5d0", "#86d4b9", "#fae591", "#f5a04d", "#dc5341", "#a72149"],
)
PROJECT = Transformer.from_crs(
    "EPSG:4326",
    "+proj=laea +lat_0=-19 +lon_0=29.5 +datum=WGS84 +units=m",
    always_xy=True,
)
WEATHER = Path("data/processed/zimbabwe_weather_v2")
PREDICTIONS = Path(
    "experiments/presto_finetune/runs/zimbabwe_lacuna_2022_2023/predictions.csv"
)


def _basemap(root):
    path = root / "results/visual_atlas/sources/zimbabwe_natural_earth.geojson"
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    country = next(
        shape(f["geometry"]) for f in features if f["properties"]["role"] == "country"
    )
    cities = {
        f["properties"]["name"]: PROJECT.transform(*f["geometry"]["coordinates"])
        for f in features
        if f["properties"]["role"] == "city"
    }
    return country, transform(PROJECT.transform, country), cities


def _field_grid(fields, country):
    if (
        not fields.obs_id.is_unique
        or not np.isfinite(fields[["lat", "lon", "yield_t_ha"]]).all().all()
    ):
        raise ValueError("Expected one finite location and yield per field observation")
    inside = shapely.covers(country, shapely.points(fields.lon, fields.lat))
    selected = fields.loc[inside].copy()
    x, y = PROJECT.transform(selected.lon, selected.lat)
    selected["x"], selected["y"] = x, y
    return selected


def _point_means(frame, columns):
    """Keep recorded positions; average measurements only at exactly matching coordinates."""
    groups = frame.groupby(["lat", "lon"], sort=True)
    means = groups[columns].mean()
    coordinates = groups[["x", "y"]].first()
    points = means.join(coordinates).join(groups.size().rename("n")).reset_index()
    # A fixed, value-independent layer order keeps the comparison panels aligned in dense clusters.
    return points.sample(frac=1, random_state=190, ignore_index=True)


def _draw_field_points(ax, points, column, cmap, norm, *, size=7):
    """Draw a single unshifted symbol per measured position in the equal-area projection."""
    return ax.scatter(
        points.x,
        points.y,
        c=points[column],
        s=size,
        cmap=cmap,
        norm=norm,
        marker="o",
        linewidths=0.28 if size >= 10 else 0.18,
        edgecolors="#fff9e3bb",
        zorder=4,
    )


def _national_bounds(country):
    xmin, ymin, xmax, ymax = country.bounds
    return xmin - 20000, ymin - 20000, xmax + 20000, ymax + 20000


def _scale(ax, bounds, distance, *, ink="white"):
    xmin, ymin, xmax, ymax = bounds
    x = xmin + 0.055 * (xmax - xmin)
    y = ymin + 0.068 * (ymax - ymin)
    (line,) = ax.plot(
        [x, x + distance], [y, y], color=ink, lw=2, zorder=8, solid_capstyle="butt"
    )
    halo = [pe.withStroke(linewidth=3.2, foreground="#223031c0")]
    line.set_path_effects(halo)
    label = ax.annotate(
        f"{distance // 1000} km",
        (x + distance / 2, y),
        xytext=(0, 3),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=7,
        color=ink,
        zorder=8,
    )
    label.set_path_effects(halo)


def _base(ax, country, cities, *, root, bounds=None, locator=False, tone="dark"):
    bounds = _national_bounds(country) if bounds is None else bounds
    xmin, ymin, xmax, ymax = bounds
    ax.set(xlim=(xmin, xmax), ylim=(ymin, ymax), aspect="equal", xticks=[], yticks=[])
    draw_basemap(ax, root, bounds, tone=tone)
    edge = "white" if tone == "dark" else "#263b40"
    (outline,) = ax.plot(*country.exterior.xy, color=edge, lw=0.78, zorder=3)
    outline.set_path_effects(
        [
            pe.withStroke(
                linewidth=1.7, foreground="#3a494b99" if tone == "dark" else "#ffffffb0"
            )
        ]
    )
    for spine in ax.spines.values():
        spine.set_linewidth(0.55)
        spine.set_edgecolor("#526266")
        spine.set_zorder(8)
    for name, (cx, cy) in cities.items():
        if not (xmin <= cx <= xmax and ymin <= cy <= ymax):
            continue
        ax.scatter(
            cx, cy, s=13, color="white", edgecolors="#17282e", linewidths=0.85, zorder=6
        )
        label = ax.annotate(
            name,
            (cx, cy),
            xytext=(3, 3),
            textcoords="offset points",
            fontsize=7.2,
            color="white",
            weight="bold",
            zorder=7,
        )
        label.set_path_effects([pe.withStroke(linewidth=2.0, foreground="#17282ebd")])
    if locator:
        _scale(ax, bounds, 100000)
        arrow = ax.annotate(
            "N",
            xy=(0.07, 0.94),
            xytext=(0.07, 0.865),
            xycoords="axes fraction",
            color="white",
            fontsize=8,
            ha="center",
            va="top",
            zorder=7,
            arrowprops={"arrowstyle": "-|>", "color": "white", "lw": 0.9},
        )
        arrow.set_path_effects([pe.withStroke(linewidth=2.0, foreground="#263334ac")])


def _colorbar(fig, rect, cmap, norm, label, ticks, *, extend="neither"):
    bar = fig.colorbar(
        mpl.cm.ScalarMappable(norm=norm, cmap=cmap),
        cax=fig.add_axes(rect),
        orientation="horizontal",
        ticks=ticks,
        extend=extend,
    )
    bar.outline.set_visible(False)
    bar.ax.tick_params(length=2.5, labelsize=8, color=MUTED, labelcolor=INK, pad=1.5)
    bar.set_label(label, fontsize=9, color=INK, labelpad=3)
    return bar


def _panel_title(ax, title, detail):
    ax.set_title(title, fontsize=11.2, loc="left", weight="bold", color=INK, pad=13)
    ax.text(
        0, 1.007, detail, transform=ax.transAxes, fontsize=7.8, color=MUTED, va="bottom"
    )


def _support(source_count, frame, points):
    repeated = points.n.gt(1)
    return {
        "screened_or_scored_records": int(source_count),
        "inside_outline": len(frame),
        "outside_outline": int(source_count - len(frame)),
        "unique_locations": len(points),
        "locations_with_repeat_records": int(repeated.sum()),
        "records_at_repeat_locations": int(points.loc[repeated, "n"].sum()),
    }


def _select_detail_windows(frame):
    """Find the most-populated 60 × 30 km window on each side of latitude 19°S.

    Candidate centers are the coordinate-wise medians in occupied 25 km cells.
    Stable grid order breaks ties, so the choice depends only on survey locations.
    """
    width, height = 60000, 30000
    candidate_cells = [np.floor(frame.x / DETAIL_CANDIDATE_GRID_METRES),
                       np.floor(frame.y / DETAIL_CANDIDATE_GRID_METRES)]
    centers = frame.groupby(candidate_cells, sort=True)[["x", "y"]].median()
    inverse = Transformer.from_crs(PROJECT.target_crs, "EPSG:4326", always_xy=True)
    windows = []
    for north in (True, False):
        best_count = 0
        best = None
        for row in centers.itertuples():
            _, lat = inverse.transform(row.x, row.y)
            if (lat >= -19) != north:
                continue
            bounds = (
                row.x - width / 2,
                row.y - height / 2,
                row.x + width / 2,
                row.y + height / 2,
            )
            in_window = frame.x.between(bounds[0], bounds[2]) & frame.y.between(
                bounds[1], bounds[3]
            )
            count = int(in_window.sum())
            if count > best_count:
                best_count = count
                best = (bounds, frame.loc[in_window])
        if best is None:
            raise ValueError(
                "Both northern and southern survey windows require observations."
            )
        windows.append(best)
    return windows


def _observed_map(root, fields, mapped, country, cities):
    fig = plt.figure(figsize=(12.5, 11.3), facecolor="white")
    fig.text(
        0.045,
        0.982,
        "Maize yield across Zimbabwe",
        fontsize=27,
        family="DejaVu Serif",
        color=INK,
        weight="bold",
        va="top",
    )
    fig.text(
        0.046,
        0.935,
        "Crop cuts recorded at field locations  ·  2023 national survey and local detail",
        fontsize=12,
        color=MUTED,
    )
    norm = Normalize(0, YIELD_LIMIT)
    yearly = {year: mapped.loc[mapped.season_year.eq(year)] for year in YEARS}
    yearly_points = {
        year: _point_means(frame, ["yield_t_ha"]) for year, frame in yearly.items()
    }
    summary = {
        str(year): _support(
            fields.season_year.eq(year).sum(), yearly[year], yearly_points[year]
        )
        for year in YEARS
    }

    def draw_locations(ax, year, locator=False):
        _base(ax, country, cities, root=root, locator=locator)
        _draw_field_points(
            ax, yearly_points[year], "yield_t_ha", YIELD_CMAP, norm, size=8.5 if locator else 4.1
        )

    overview = fig.add_axes([0.045, 0.452, 0.459, 0.433])
    draw_locations(overview, 2023, locator=True)
    _panel_title(
        overview,
        "A   Lacuna 2023",
        f"National view  ·  {len(yearly_points[2023]):,} recorded locations",
    )
    zoom_summary = []
    windows = _select_detail_windows(yearly[2023])
    for letter, (bounds, records), bottom in zip(
        ("B", "C"), windows, (0.687, 0.449), strict=True
    ):
        left, low, right, high = bounds
        zoom = fig.add_axes([0.561, bottom, 0.393, 0.190])
        _base(zoom, country, cities, root=root, bounds=bounds)
        points = _point_means(records, ["yield_t_ha"])
        _draw_field_points(zoom, points, "yield_t_ha", YIELD_CMAP, norm, size=18)
        _scale(zoom, bounds, 10000)
        area = str(records.admin_unit.mode().iat[0]).title()
        _panel_title(
            zoom,
            f"{letter}   {area}",
            f"{len(records):,} crop cuts  ·  {len(points):,} plotted locations  ·  60 × 30 km",
        )
        frame = mpl.patches.Rectangle(
            (left, low),
            right - left,
            high - low,
            fill=False,
            lw=1.3,
            color=CALLOUT,
            zorder=7,
        )
        frame.set_path_effects([pe.withStroke(linewidth=2.4, foreground="#20292dcc")])
        overview.add_patch(frame)
        tag = overview.annotate(
            letter,
            (left, high),
            xytext=(0, 2),
            textcoords="offset points",
            color="#20292d",
            fontsize=8.5,
            weight="bold",
            zorder=8,
            bbox={"boxstyle": "round,pad=.16", "fc": CALLOUT, "ec": "none"},
        )
        tag.set_clip_on(True)
        connector = ConnectionPatch(
            xyA=(right, (low + high) / 2),
            coordsA=overview.transData,
            xyB=(0, 0.50),
            coordsB=zoom.transAxes,
            color="#a97342",
            linewidth=0.85,
            alpha=0.85,
            zorder=2,
            clip_on=False,
        )
        connector.set_path_effects(
            [pe.withStroke(linewidth=1.7, foreground="#ffffff8c")]
        )
        fig.add_artist(connector)
        zoom_summary.append(
            {
                "panel": letter,
                "provider_area": area,
                "records": len(records),
                "unique_locations": len(points),
                "bounds_laea_m": [float(v) for v in bounds],
            }
        )

    _colorbar(
        fig,
        [0.049, 0.398, 0.438, 0.011],
        YIELD_CMAP,
        norm,
        "Measured maize yield (t/ha)",
        [0, 2, 4, 6, 8],
        extend="max",
    )
    fig.text(
        0.552,
        0.41,
        "Each dot marks a recorded crop-cut location.",
        fontsize=9.2,
        color=INK,
    )
    fig.text(
        0.552,
        0.39,
        "Where coordinates repeat, the dot shows their mean.",
        fontsize=8.8,
        color=MUTED,
    )
    for i, year in enumerate(YEARS):
        ax = fig.add_axes([0.043 + i * 0.318, 0.083, 0.283, 0.235])
        draw_locations(ax, year)
        provider = "Lacuna" if year < 2024 else "Vision-Guided"
        _panel_title(
            ax,
            f"{year}   {provider}",
            f"{len(yearly[year]):,} records  ·  {len(yearly_points[year]):,} distinct locations",
        )
    fig.text(
        0.046,
        0.054,
        "Dots show sampled field positions. Closely spaced dots overlap at national scale. "
        "The detail panels enlarge two dense clusters on the same yield scale.",
        fontsize=8.7,
        color=INK,
    )
    fig.text(
        0.046,
        0.034,
        f"The 2024 catalog includes {fields.loc[fields.season_year.eq(2024), 'yield_t_ha'].eq(0).sum():,} recorded zeros. "
        f"Its national map excludes {summary['2024']['outside_outline']} records outside the generalized boundary.",
        fontsize=8.1,
        color=MUTED,
    )
    fig.text(
        0.046,
        0.014,
        f"PULA/Lacuna and Scalable Vision-Guided crop cuts  ·  Natural Earth boundaries and cities  ·  {BASEMAP_CREDIT}",
        fontsize=7.25,
        color=MUTED,
    )
    return fig, summary, zoom_summary


def _weather_values(root, locations):
    monthly = pd.read_parquet(root / WEATHER / "weather_cell_months.parquet")
    m = monthly.loc[
        monthly.calendar_month.between(1, 3) & monthly.season_year.isin(YEARS)
    ].copy()
    keys = ["season_year", "weather_grid_id"]
    if (
        m.duplicated([*keys, "calendar_month"]).any()
        or not m.groupby(keys).size().eq(3).all()
    ):
        raise ValueError("Expected three distinct January–March records per cell-year")
    m["weighted_temperature_anomaly"] = m.t2m_anomaly_c * m.days_in_month
    sums = m.groupby(keys)[
        [
            "rain_total_mm",
            "rain_expected_current_days_mm",
            "weighted_temperature_anomaly",
            "days_in_month",
        ]
    ].sum()
    if (sums.rain_expected_current_days_mm <= 0).any():
        raise ValueError(
            "Positive expected rainfall is required for the percent-of-normal map"
        )
    sums["rain_pct"] = 100 * sums.rain_total_mm / sums.rain_expected_current_days_mm
    sums["temp_anomaly"] = sums.weighted_temperature_anomaly / sums.days_in_month
    coords = locations[
        ["weather_grid_id", "weather_grid_lon", "weather_grid_lat"]
    ].drop_duplicates()
    table = sums.reset_index().merge(
        coords, on="weather_grid_id", how="left", validate="many_to_one"
    )
    expected = set(coords.weather_grid_id)
    if table.isna().any().any() or any(
        set(t.weather_grid_id) != expected for _, t in table.groupby("season_year")
    ):
        raise ValueError(
            "Every season must use the same archived weather cells with finite values"
        )
    return table


def _weather_shading(weather, country):
    """Interpolate adjacent POWER cell centers for display within their archived footprint."""
    cells = weather.drop_duplicates("weather_grid_id").set_index("weather_grid_id")
    lon_min, lat_min = cells.weather_grid_lon.min(), cells.weather_grid_lat.min()
    # Pad the native array so the outer half of each edge cell remains in view.
    col = np.rint((cells.weather_grid_lon.to_numpy() - lon_min) / 0.625).astype(int) + 1
    row = np.rint((cells.weather_grid_lat.to_numpy() - lat_min) / 0.5).astype(int) + 1
    native = np.zeros((row.max() + 2, col.max() + 2), dtype=float)
    native[row, col] = 1
    if native.sum() != len(cells):
        raise ValueError("A native POWER cell has more than one grid ID.")

    xmin, ymin, xmax, ymax = country.bounds
    width = 640
    height = round(width * (ymax - ymin) / (xmax - xmin))
    dx, dy = (xmax - xmin) / width, (ymax - ymin) / height
    x, y = np.meshgrid(xmin + (np.arange(width) + .5) * dx,
                       ymin + (np.arange(height) + .5) * dy)
    inverse = Transformer.from_crs(PROJECT.target_crs, "EPSG:4326", always_xy=True)
    lon, lat = inverse.transform(x, y)
    positions = np.stack(((lat - lat_min) / .5 + 1, (lon - lon_min) / .625 + 1))
    footprint = map_coordinates(native, positions, order=0, prefilter=False) > 0
    weights = map_coordinates(native, positions, order=1, prefilter=False)
    inside_country = shapely.intersects_xy(country, x, y)
    # A soft shoulder inside the footprint keeps the gaps legible against the imagery.
    edge_distance = distance_transform_edt(footprint, sampling=(dy, dx))
    alpha = .87 * (1 - np.exp(-(edge_distance / 24_000) ** 2)) * weights * inside_country
    layers = {}
    for year, group in weather.groupby("season_year"):
        aligned = group.set_index("weather_grid_id").loc[cells.index]
        for name in ("rain_pct", "temp_anomaly"):
            values = np.zeros_like(native)
            values[row, col] = aligned[name].to_numpy()
            weighted = map_coordinates(values, positions, order=1, prefilter=False)
            layers[year, name] = np.divide(weighted, weights, out=np.zeros_like(weighted), where=weights > 0)

    cx, cy = PROJECT.transform(cells.weather_grid_lon.to_numpy(), cells.weather_grid_lat.to_numpy())
    mark = shapely.intersects_xy(country, cx, cy)
    return (xmin, xmax, ymin, ymax), alpha, layers, (cx[mark], cy[mark])


def _weather_map(root, fields, country, cities):
    weather = _weather_values(root, fields)
    cells = weather.drop_duplicates("weather_grid_id")
    extent, alpha, layers, centers = _weather_shading(weather, country)
    visible = 0
    for cell in cells.itertuples():
        lon, lat = cell.weather_grid_lon, cell.weather_grid_lat
        rect = box(lon - .3125, lat - .25, lon + .3125, lat + .25)
        visible += transform(PROJECT.transform, rect.segmentize(.05)).intersects(country)
    fig = plt.figure(figsize=(12.4, 8.7), facecolor="white")
    fig.text(
        0.045,
        0.97,
        "Rainfall and temperature across sampled areas",
        family="DejaVu Serif",
        fontsize=18.5,
        weight="bold",
        color=INK,
    )
    fig.text(
        0.046,
        0.927,
        f"January–March conditions in {len(cells)} NASA POWER cells, relative to their 1991–2020 average",
        fontsize=10,
        color=MUTED,
    )
    grid = fig.add_gridspec(
        2, 3, left=0.045, right=0.974, top=0.84, bottom=0.20, wspace=0.07, hspace=0.10
    )
    rain_norm, temp_norm = Normalize(0, 200), Normalize(-2.5, 2.5)
    rain_cmap, temp_cmap = "BrBG", "RdBu_r"
    for col, year in enumerate(YEARS):
        for level, (name, cmap, norm) in enumerate(
            [("rain_pct", rain_cmap, rain_norm), ("temp_anomaly", temp_cmap, temp_norm)]
        ):
            ax = fig.add_subplot(grid[level, col])
            _base(
                ax,
                country,
                cities,
                root=root,
                locator=level == 0 and col == 0,
                tone="light",
            )
            ax.imshow(
                layers[year, name], extent=extent, origin="lower", interpolation="nearest",
                cmap=cmap, norm=norm, alpha=alpha, zorder=2, aspect="equal",
            )
            ax.scatter(*centers, s=2.1, color="#29434980", edgecolors="white",
                       linewidths=.16, zorder=2.5)
            if level == 0:
                ax.set_title(
                    str(year),
                    fontsize=12,
                    weight="bold",
                    loc="center",
                    color=INK,
                    pad=9,
                )
    fig.text(0.045, 0.858, "Rainfall", fontsize=11.5, weight="bold", color=INK)
    fig.text(0.045, 0.517, "Temperature", fontsize=11.5, weight="bold", color=INK)
    _colorbar(
        fig,
        [0.05, 0.141, 0.38, 0.019],
        rain_cmap,
        rain_norm,
        "Rainfall (% of normal)",
        [0, 50, 100, 150, 200],
    )
    _colorbar(
        fig,
        [0.535, 0.141, 0.38, 0.019],
        temp_cmap,
        temp_norm,
        "Air temperature anomaly (°C)",
        [-2, -1, 0, 1, 2],
    )
    last_year = weather[weather.season_year.eq(2024)]
    fig.text(
        0.046,
        0.075,
        f"Across these cells in 2024, median January–March rainfall was {last_year.rain_pct.median():.0f}% of normal and median temperature was {last_year.temp_anomaly.median():.2f} °C above normal.",
        fontsize=8.4,
        color=MUTED,
    )
    fig.text(
        0.046,
        0.043,
        "Dots mark POWER cell centers inside Zimbabwe (0.5° latitude × 0.625° longitude). Color blends adjacent values and fades at the archived coverage edge.",
        fontsize=8.2,
        color=MUTED,
    )
    fig.text(
        0.046,
        0.02,
        f"NASA POWER / MERRA-2  ·  Natural Earth boundaries and cities  ·  {BASEMAP_CREDIT}",
        fontsize=7.25,
        color=MUTED,
    )
    summary = {
        "grid_latitude_degrees": 0.5,
        "grid_longitude_degrees": 0.625,
        "archived_cells_each_year": len(cells),
        "cells_intersecting_boundary": visible,
        "native_centers_inside_boundary": len(centers[0]),
        "display_interpolation": "Local bilinear weights among available neighboring native centers, restricted to archived cell footprints inside Zimbabwe.",
        "reference_years": [1991, 2020],
        "months": [1, 2, 3],
        "years": {},
    }
    for year, data in weather.groupby("season_year"):
        summary["years"][str(year)] = {
            k: {s: float(getattr(data[k], s)()) for s in ("min", "median", "max")}
            for k in ("rain_pct", "temp_anomaly")
        }
    return fig, summary


def _prediction_map(root, fields, country_ll, country, cities, detail):
    p = pd.read_csv(
        root / PREDICTIONS, usecols=["obs_id", "fold", "season_year", "y_t_ha", "A1"]
    )
    p = p.merge(
        fields[["obs_id", "lat", "lon", "yield_t_ha", "include_primary"]],
        on="obs_id",
        how="left",
        validate="one_to_one",
    )
    if (
        p.isna().any().any()
        or not np.allclose(p.y_t_ha, p.yield_t_ha)
        or not p.include_primary.all()
        or set(p.fold) != {1, 2, 3, 4}
        or set(p.season_year) != {2023}
    ):
        raise ValueError(
            "Prediction observations, target yields or development folds do not match the mapping source"
        )
    mapped = _field_grid(p, country_ll)
    points = _point_means(mapped, ["yield_t_ha", "A1"])
    points["error"] = points.A1 - points.yield_t_ha
    y_norm = Normalize(0, YIELD_LIMIT)
    error_limit = max(1, np.ceil(points.error.abs().quantile(0.95)))
    error_norm = Normalize(-error_limit, error_limit)
    bounds = detail["bounds_laea_m"]
    west, south, east, north = bounds
    zoom_points = points.loc[points.x.between(west, east) & points.y.between(south, north)]
    zoom_records = int(zoom_points.n.sum())
    fig = plt.figure(figsize=(12.4, 9.0), facecolor="white")
    fig.text(.045, .947, "Measured and predicted maize yield on the same fields",
             fontsize=21, family="DejaVu Serif", weight="bold", color=INK)
    fig.text(.046, .906, f"Lacuna 2023  ·  {len(p):,} spatially held-out records  ·  "
             f"{len(points):,} measured locations  ·  seasonal vegetation-index Ridge (A1)", fontsize=10, color=MUTED)
    grid = fig.add_gridspec(2, 3, left=.045, right=.97, top=.815, bottom=.222,
                            height_ratios=[1.8, 1], wspace=.06, hspace=.28)
    for i, (title, subtitle, key, cmap, norm) in enumerate([
            ("Measured", "Crop-cut yield at the recorded position", "yield_t_ha", YIELD_CMAP, y_norm),
            ("Predicted", "Held-out estimate at the same position", "A1", YIELD_CMAP, y_norm),
            ("Prediction error", "Predicted minus measured yield", "error", "RdBu_r", error_norm)]):
        ax = fig.add_subplot(grid[0, i])
        _base(ax, country, cities, root=root, locator=i == 0)
        _draw_field_points(ax, points, key, cmap, norm, size=5.8)
        _panel_title(ax, title, subtitle)
        ax.add_patch(mpl.patches.Rectangle((west, south), east - west, north - south,
                                           fill=False, edgecolor=CALLOUT, lw=1, zorder=7))
        zoom = fig.add_subplot(grid[1, i])
        _base(zoom, country, cities, root=root, bounds=bounds)
        _draw_field_points(zoom, zoom_points, key, cmap, norm, size=17)
        if i == 0:
            _scale(zoom, bounds, 10000)
        zoom.set_title(f"{detail['provider_area']} detail" if i == 0 else title + " detail",
                       loc="left", fontsize=9.6, weight="bold", color=INK, pad=5)
    _colorbar(
        fig,
        [0.048, 0.151, 0.39, 0.015],
        YIELD_CMAP,
        y_norm,
        "Observed and predicted yield (t/ha)",
        np.arange(0, YIELD_LIMIT + 1, 2),
        extend="max",
    )
    _colorbar(
        fig,
        [0.53, 0.151, 0.39, 0.015],
        "RdBu_r",
        error_norm,
        "Prediction error (t/ha)",
        np.linspace(-error_limit, error_limit, 5),
        extend="both",
    )
    s = _support(len(p), mapped, points)
    fig.text(
        0.046,
        0.065,
        f"The lower row enlarges {zoom_records} held-out records at {len(zoom_points)} locations in {detail['provider_area']}. "
        "Each dot averages records sharing its exact coordinates. Red indicates overprediction and blue underprediction.",
        fontsize=8.3,
        color=MUTED,
    )
    fig.text(
        0.046,
        0.032,
        f"PULA/Lacuna and archived A1 predictions (folds 1–4)  ·  Natural Earth boundaries and cities  ·  {BASEMAP_CREDIT}",
        fontsize=8,
        color=MUTED,
    )
    s.update(
        {
            "prediction_file": PREDICTIONS.as_posix(),
            "prediction_column": "A1",
            "error_sign": "predicted minus measured",
            "error_palette_limit_t_ha": float(error_limit),
            "error_palette_rule": "95th percentile of absolute location errors, rounded up to a whole t/ha; colors extend at both ends",
            "error_locations_outside_palette_limits": int(points.error.abs().gt(error_limit).sum()),
            "detail_window": {"provider_area": detail["provider_area"], "records": zoom_records,
                              "unique_locations": len(zoom_points), "bounds_laea_m": bounds},
            "field_rmse_t_ha": float(np.sqrt(((p.A1 - p.y_t_ha) ** 2).mean())),
            "field_r2": float(
                1
                - ((p.A1 - p.y_t_ha) ** 2).sum()
                / ((p.y_t_ha - p.y_t_ha.mean()) ** 2).sum()
            ),
        }
    )
    return fig, s


def build_maps(repo_root, output_dir=None):
    """Return the three Matplotlib figures. An output directory also saves the figures and support counts."""
    root = Path(repo_root)
    cols = [
        "obs_id",
        "lat",
        "lon",
        "admin_unit",
        "season_year",
        "yield_t_ha",
        "include_primary",
        "weather_grid_id",
        "weather_grid_lon",
        "weather_grid_lat",
    ]
    fields = pd.read_parquet(
        root / WEATHER / "harmonized_labels_weather.parquet", columns=cols
    )
    country_ll, country, cities = _basemap(root)
    mapped = _field_grid(fields, country_ll)
    with mpl.rc_context(
        {
            "font.family": "DejaVu Sans",
            "axes.unicode_minus": True,
            "figure.facecolor": "white",
        }
    ):
        measured, counts, details = _observed_map(root, fields, mapped, country, cities)
        weather, coverage = _weather_map(root, fields, country, cities)
        predicted, matched = _prediction_map(root, fields, country_ll, country, cities, details[1])
    figures = {
        "yield_map": measured,
        "weather_map": weather,
        "prediction_map": predicted,
    }
    if output_dir is not None:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        for name, fig in figures.items():
            fig.savefig(
                folder / f"{name}.png",
                dpi=170,
                bbox_inches="tight",
                pad_inches=0.13,
                facecolor="white",
            )
        summary = {
            "cartography": "Lambert azimuthal equal-area, centered at 19° S, 29.5° E, WGS84",
            "yield_spatial_support": "Recorded GPS locations inside the national outline. Only exactly coincident coordinates share a dot, showing the mean of their records.",
            "detail_window_selection": "Candidate centers are median positions in occupied 25 km cells. Each side of 19 degrees south contributes its most populated 60 km by 30 km window.",
            "observed_yield": counts,
            "yield_detail_windows": details,
            "weather": coverage,
            "predictions": matched,
        }
        (folder / "map_data_summary.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    return figures


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    figures = build_maps(root, root / "results/visual_atlas")
    for figure in figures.values():
        plt.close(figure)
