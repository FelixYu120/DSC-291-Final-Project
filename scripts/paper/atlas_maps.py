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
from matplotlib.collections import PatchCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import ConnectionPatch, Patch
from matplotlib.patches import Polygon as MplPolygon
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform

if __package__:
    from .atlas_basemap import BASEMAP_CREDIT, draw_basemap
else:  # Supports direct execution from the repository root.
    from atlas_basemap import BASEMAP_CREDIT, draw_basemap

YEARS = (2022, 2023, 2024)
CELL_METRES = 25_000
MIN_RECORDS = 5
SPARSE = "#e2e1d5"
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
    selected["gx"] = np.floor(x / CELL_METRES).astype(int)
    selected["gy"] = np.floor(y / CELL_METRES).astype(int)
    return selected


def _cell_means(frame, values):
    groups = frame.groupby(["gx", "gy"], sort=True)
    return groups[values].mean().join(groups.size().rename("n")).reset_index()


def _yield_cells(cells, country):
    polygons = []
    for row in cells.itertuples():
        x, y = row.gx * CELL_METRES, row.gy * CELL_METRES
        polygons.append(
            box(x, y, x + CELL_METRES, y + CELL_METRES).intersection(country)
        )
    return polygons


def _polygons(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [MplPolygon(np.asarray(geom.exterior.coords), closed=True)]
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [patch for part in geom.geoms for patch in _polygons(part)]
    return []


def _draw_cells(ax, geoms, values, cmap, norm, *, opacity=1.0):
    patches, colors, edges, widths = [], [], [], []
    palette = mpl.colormaps[cmap] if isinstance(cmap, str) else cmap
    for geom, value in zip(geoms, values, strict=True):
        parts = _polygons(geom)
        patches.extend(parts)
        measured = np.isfinite(value)
        face = (*palette(norm(value))[:3], opacity) if measured else (0, 0, 0, 0)
        colors.extend([face] * len(parts))
        edges.extend([("#ffffff70" if measured else SPARSE)] * len(parts))
        widths.extend([0.22 if measured else 0.55] * len(parts))
    ax.add_collection(
        PatchCollection(
            patches, facecolors=colors, edgecolors=edges, linewidths=widths, zorder=2
        )
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


def _heading(fig, title, subtitle):
    fig.text(
        0.045,
        0.957,
        title,
        ha="left",
        va="top",
        family="DejaVu Serif",
        fontsize=21,
        weight="bold",
        color=INK,
    )
    fig.text(0.046, 0.862, subtitle, ha="left", va="top", fontsize=10.4, color=MUTED)


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


def _visibility_key(fig, rect):
    handles = [
        Patch(
            facecolor="#737c7c", edgecolor=SPARSE, label="Outlined cell  ·  1–4 fields"
        ),
        Patch(
            facecolor="#596265",
            edgecolor="#959f9f",
            label="Basemap alone  ·  no cell mean",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="center left",
        bbox_to_anchor=rect,
        ncols=1,
        frameon=False,
        fontsize=8.2,
        labelcolor=INK,
        handlelength=1.35,
        borderaxespad=0,
    )


def _panel_title(ax, title, detail):
    ax.set_title(title, fontsize=11.2, loc="left", weight="bold", color=INK, pad=13)
    ax.text(
        0, 1.007, detail, transform=ax.transAxes, fontsize=7.8, color=MUTED, va="bottom"
    )


def _support(source_count, frame, cells):
    eligible = cells.n >= MIN_RECORDS
    return {
        "screened_or_scored_records": int(source_count),
        "inside_outline": len(frame),
        "outside_outline": int(source_count - len(frame)),
        "colored_cells": int(eligible.sum()),
        "records_in_colored_cells": int(cells.loc[eligible, "n"].sum()),
        "sparse_cells": int((~eligible).sum()),
        "records_in_sparse_cells": int(cells.loc[~eligible, "n"].sum()),
    }


def _select_detail_windows(frame):
    """Find the most-populated 60 × 30 km window on each side of latitude 19°S.

    Candidate centers are the coordinate-wise medians in occupied 25 km cells.
    Stable grid order breaks ties, so the choice depends only on survey locations.
    """
    width, height = 60000, 30000
    centers = frame.groupby(["gx", "gy"], sort=True)[["x", "y"]].median()
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
    yearly_cells = {
        year: _cell_means(frame, ["yield_t_ha"]) for year, frame in yearly.items()
    }
    summary = {
        str(year): _support(
            fields.season_year.eq(year).sum(), yearly[year], yearly_cells[year]
        )
        for year in YEARS
    }

    def draw_grid(ax, year, locator=False):
        cells = yearly_cells[year]
        _base(ax, country, cities, root=root, locator=locator)
        _draw_cells(
            ax,
            _yield_cells(cells, country),
            cells.yield_t_ha.where(cells.n >= MIN_RECORDS),
            YIELD_CMAP,
            norm,
            opacity=0.96,
        )

    overview = fig.add_axes([0.045, 0.452, 0.459, 0.433])
    draw_grid(overview, 2023, locator=True)
    _panel_title(
        overview,
        "A   Lacuna 2023",
        "National view  ·  mean measured yield in 25 km cells",
    )
    zoom_summary = []
    windows = _select_detail_windows(yearly[2023])
    for letter, (bounds, records), bottom in zip(
        ("B", "C"), windows, (0.687, 0.449), strict=True
    ):
        left, low, right, high = bounds
        # A legend color always represents a recorded location or a measured-cell mean.
        zoom = fig.add_axes([0.561, bottom, 0.393, 0.190])
        _base(zoom, country, cities, root=root, bounds=bounds)
        points = records.groupby(
            ["x", "y"], as_index=False, sort=True
        ).yield_t_ha.mean()
        zoom.scatter(
            points.x,
            points.y,
            c=points.yield_t_ha,
            cmap=YIELD_CMAP,
            norm=norm,
            s=27,
            edgecolors="#fff9e3",
            linewidths=0.42,
            alpha=0.98,
            zorder=4,
        )
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
        "Regional dots show yield at the recorded field location.",
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
        draw_grid(ax, year)
        provider = "Lacuna" if year < 2024 else "Vision-Guided"
        _panel_title(
            ax,
            f"{year}   {provider}",
            f"{len(yearly[year]):,} records inside outline  ·  {summary[str(year)]['colored_cells']} colored cells",
        )
    fig.text(
        0.046,
        0.054,
        "Colored squares average at least five crop cuts. Outlined squares contain one to four. "
        "Exposed satellite imagery shows where the survey has no mapped mean.",
        fontsize=8.7,
        color=INK,
    )
    fig.text(
        0.046,
        0.034,
        f"The 2024 catalog includes {fields.loc[fields.season_year.eq(2024), 'yield_t_ha'].eq(0).sum():,} recorded zeros. "
        f"Its national map excludes {summary['2024']['outside_outline']} locations outside the generalized boundary.",
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


def _weather_map(root, fields, country, cities):
    weather = _weather_values(root, fields)
    cells = weather.drop_duplicates("weather_grid_id")
    geometries = {}
    for row in cells.itertuples():
        lon, lat = row.weather_grid_lon, row.weather_grid_lat
        rect = box(lon - 0.3125, lat - 0.25, lon + 0.3125, lat + 0.25)
        projected = transform(PROJECT.transform, rect.segmentize(0.05))
        geometries[row.weather_grid_id] = projected.intersection(country)
    visible = sum(not g.is_empty for g in geometries.values())
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
    uncovered = country.difference(shapely.union_all(list(geometries.values())))
    for col, year in enumerate(YEARS):
        d = weather.loc[weather.season_year.eq(year)]
        outlines = [geometries[key] for key in d.weather_grid_id]
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
            ax.add_collection(
                PatchCollection(
                    _polygons(uncovered),
                    facecolors="none",
                    edgecolors="#606e6d88",
                    linewidths=0,
                    hatch="///",
                    zorder=1,
                )
            )
            _draw_cells(ax, outlines, d[name], cmap, norm, opacity=0.77)
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
        "Top row shows seasonal rainfall. Bottom row shows day-weighted temperature departures. Hatching marks land outside the archived weather footprint.",
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


def _prediction_map(root, fields, country_ll, country, cities):
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
    cells = _cell_means(mapped, ["yield_t_ha", "A1"])
    cells["error"] = cells.A1 - cells.yield_t_ha
    eligible = cells.n >= MIN_RECORDS
    yield_limit = YIELD_LIMIT
    error_limit = max(1, np.ceil(cells.loc[eligible, "error"].abs().max()))
    y_norm, error_norm = Normalize(0, yield_limit), Normalize(-error_limit, error_limit)
    fig = plt.figure(figsize=(12.4, 5.9), facecolor="white")
    grid = fig.add_gridspec(
        1, 3, left=0.045, right=0.97, top=0.735, bottom=0.245, wspace=0.07
    )
    _heading(
        fig,
        "Measured and predicted maize yield on the same fields",
        f"Lacuna 2023  ·  {len(p):,} spatially held-out field predictions  ·  seasonal vegetation-index Ridge (A1)",
    )
    geo = _yield_cells(cells, country)
    for i, (title, detail, key, cmap, norm) in enumerate(
        [
            ("Measured", "Mean crop-cut yield", "yield_t_ha", YIELD_CMAP, y_norm),
            ("Predicted", "Mean out-of-fold estimate", "A1", YIELD_CMAP, y_norm),
            (
                "Prediction error",
                "Predicted minus measured",
                "error",
                "RdBu_r",
                error_norm,
            ),
        ]
    ):
        ax = fig.add_subplot(grid[0, i])
        _base(ax, country, cities, root=root, locator=i == 0)
        _draw_cells(ax, geo, cells[key].where(eligible), cmap, norm, opacity=0.95)
        _panel_title(ax, title, detail)
    _colorbar(
        fig,
        [0.048, 0.165, 0.34, 0.024],
        YIELD_CMAP,
        y_norm,
        "Mean yield (t/ha)",
        np.arange(0, yield_limit + 1, 2),
    )
    _colorbar(
        fig,
        [0.465, 0.165, 0.25, 0.024],
        "RdBu_r",
        error_norm,
        "Mean error (t/ha)",
        [-error_limit, 0, error_limit],
    )
    _visibility_key(fig, (0.745, 0.18))
    s = _support(len(p), mapped, cells)
    fig.text(
        0.046,
        0.065,
        f"Color covers {s['records_in_colored_cells']:,} fields in the same {s['colored_cells']} sampled cells. Red errors indicate overprediction and blue errors indicate underprediction.",
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
        predicted, matched = _prediction_map(root, fields, country_ll, country, cities)
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
            "yield_grid_metres": CELL_METRES,
            "minimum_records_for_cell_mean": MIN_RECORDS,
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
