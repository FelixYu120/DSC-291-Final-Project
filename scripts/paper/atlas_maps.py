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
from matplotlib.colors import Normalize
from matplotlib.patches import Patch
from matplotlib.patches import Polygon as MplPolygon
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform

YEARS = (2022, 2023, 2024)
CELL_METRES = 25_000
MIN_RECORDS = 5
LAND = "#eef0ed"
SPARSE = "#adb9bd"
INK = "#213b42"
MUTED = "#52666a"
YIELD_CMAP = "viridis"
PROJECT = Transformer.from_crs(
    "EPSG:4326", "+proj=laea +lat_0=-19 +lon_0=29.5 +datum=WGS84 +units=m", always_xy=True
)
WEATHER = Path("data/processed/zimbabwe_weather_v2")
PREDICTIONS = Path("experiments/presto_finetune/runs/zimbabwe_lacuna_2022_2023/predictions.csv")


def _basemap(root):
    path = root / "results/visual_atlas/sources/zimbabwe_natural_earth.geojson"
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    country = next(shape(f["geometry"]) for f in features if f["properties"]["role"] == "country")
    cities = {
        f["properties"]["name"]: PROJECT.transform(*f["geometry"]["coordinates"])
        for f in features
        if f["properties"]["role"] == "city"
    }
    return country, transform(PROJECT.transform, country), cities


def _field_grid(fields, country):
    if not fields.obs_id.is_unique or not np.isfinite(fields[["lat", "lon", "yield_t_ha"]]).all().all():
        raise ValueError("Expected one finite location and yield per field observation")
    inside = shapely.covers(country, shapely.points(fields.lon, fields.lat))
    selected = fields.loc[inside].copy()
    x, y = PROJECT.transform(selected.lon, selected.lat)
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
        polygons.append(box(x, y, x + CELL_METRES, y + CELL_METRES).intersection(country))
    return polygons


def _polygons(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [MplPolygon(np.asarray(geom.exterior.coords), closed=True)]
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [patch for part in geom.geoms for patch in _polygons(part)]
    return []


def _draw_cells(ax, geoms, values, cmap, norm):
    patches, colors = [], []
    palette = mpl.colormaps[cmap]
    for geom, value in zip(geoms, values, strict=True):
        parts = _polygons(geom)
        patches.extend(parts)
        colors.extend([palette(norm(value)) if np.isfinite(value) else SPARSE] * len(parts))
    ax.add_collection(
        PatchCollection(patches, facecolors=colors, edgecolors="white", linewidths=0.28, zorder=2)
    )


def _base(ax, country, cities, *, locator=False, hatch_unmapped=False):
    x, y = country.exterior.xy
    ax.fill(
        x,
        y,
        facecolor=LAND,
        edgecolor="#c9d0cd" if hatch_unmapped else "none",
        hatch="///" if hatch_unmapped else None,
        linewidth=0,
        zorder=0,
    )
    ax.plot(x, y, color=INK, lw=0.8, zorder=3)
    for name, (cx, cy) in cities.items():
        ax.scatter(cx, cy, s=10, color=INK, edgecolors="white", linewidths=0.5, zorder=4)
        label = ax.annotate(
            name, (cx, cy), xytext=(3, 3), textcoords="offset points", fontsize=7.2, color=INK, zorder=5
        )
        label.set_path_effects([pe.withStroke(linewidth=1.8, foreground="white")])
    xmin, ymin, xmax, ymax = country.bounds
    ax.set(xlim=(xmin - 12000, xmax + 14000), ylim=(ymin - 26000, ymax + 22000), aspect="equal")
    ax.set_axis_off()
    if locator:
        sx, sy = xmin + 16000, ymin + 6000
        ax.plot([sx, sx + 100000], [sy, sy], color=INK, lw=1.7, solid_capstyle="butt", zorder=6)
        ax.text(sx + 50000, sy + 12000, "100 km", ha="center", fontsize=7.1, color=INK)
        ax.annotate(
            "",
            xy=(0.075, 0.9),
            xytext=(0.075, 0.81),
            xycoords="axes fraction",
            arrowprops={"arrowstyle": "-|>", "lw": 0.85, "color": INK},
        )
        ax.text(
            0.075, 0.905, "N", transform=ax.transAxes, ha="center", va="bottom", fontsize=7.6, color=INK
        )


def _heading(fig, title, subtitle):
    fig.text(0.045, 0.958, title, ha="left", va="top", fontsize=19, weight="bold", color=INK)
    fig.text(0.046, 0.885, subtitle, ha="left", va="top", fontsize=10.4, color=MUTED)


def _colorbar(fig, rect, cmap, norm, label, ticks):
    bar = fig.colorbar(
        mpl.cm.ScalarMappable(norm=norm, cmap=cmap),
        cax=fig.add_axes(rect),
        orientation="horizontal",
        ticks=ticks,
    )
    bar.outline.set_visible(False)
    bar.ax.tick_params(length=2.5, labelsize=8, color=MUTED, labelcolor=INK, pad=1.5)
    bar.set_label(label, fontsize=9, color=INK, labelpad=3.5)
    return bar


def _yield_legend(fig, x=0.55, y=0.18):
    handles = [
        Patch(facecolor=SPARSE, label="1–4 records"),
        Patch(facecolor=LAND, edgecolor="#a2b1b2", linewidth=0.6, label="No mapped records"),
    ]
    fig.legend(
        handles=handles,
        loc="center left",
        bbox_to_anchor=(x, y),
        ncols=2,
        frameon=False,
        fontsize=8.5,
        labelcolor=INK,
        handlelength=1.2,
        columnspacing=1.5,
    )


def _panel_title(ax, title, detail):
    ax.text(0.02, 1.095, title, transform=ax.transAxes, fontsize=11.5, weight="bold", color=INK)
    ax.text(0.02, 1.024, detail, transform=ax.transAxes, fontsize=8.6, color=MUTED)


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


def _observed_map(fields, mapped, country, cities):
    fig = plt.figure(figsize=(12.4, 5.9), facecolor="white")
    grid = fig.add_gridspec(1, 3, left=0.045, right=0.97, top=0.735, bottom=0.245, wspace=0.07)
    _heading(
        fig,
        "Where crop cuts recorded maize yield",
        "Mean observed yield within 25 km × 25 km equal-area cells with at least five field records",
    )
    summary = {}
    norm = Normalize(0, 6)
    for column, year in enumerate(YEARS):
        frame = mapped.loc[mapped.season_year.eq(year)]
        cells = _cell_means(frame, ["yield_t_ha"])
        s = _support(fields.season_year.eq(year).sum(), frame, cells)
        summary[str(year)] = s
        ax = fig.add_subplot(grid[0, column])
        _base(ax, country, cities, locator=column == 0)
        _draw_cells(
            ax,
            _yield_cells(cells, country),
            cells.yield_t_ha.where(cells.n >= MIN_RECORDS),
            YIELD_CMAP,
            norm,
        )
        provider = "Lacuna" if year < 2024 else "Vision-Guided"
        _panel_title(
            ax,
            f"{provider}  ·  {year}",
            f"{len(frame):,} records inside outline  ·  {s['colored_cells']} colored cells",
        )
    _colorbar(
        fig,
        [0.048, 0.165, 0.39, 0.024],
        YIELD_CMAP,
        norm,
        "Mean measured yield (t/ha)",
        [0, 1, 2, 3, 4, 5, 6],
    )
    _yield_legend(fig)
    records_2024 = fields.loc[fields.season_year.eq(2024), "yield_t_ha"]
    fig.text(
        0.046,
        0.065,
        f"Screened catalog includes {records_2024.eq(0).sum():,} recorded 2024 zeros. "
        f"The generalized national outline excludes {summary['2024']['outside_outline']} of "
        f"{len(records_2024):,} screened 2024 locations.",
        fontsize=8.3,
        color=MUTED,
    )
    fig.text(
        0.046,
        0.032,
        "Sources: PULA/Lacuna and Scalable Vision-Guided Crop Yield Estimation Dataset. Boundary and cities: Natural Earth, 1:50m.",
        fontsize=8,
        color=MUTED,
    )
    return fig, summary


def _weather_values(root, locations):
    monthly = pd.read_parquet(root / WEATHER / "weather_cell_months.parquet")
    m = monthly.loc[monthly.calendar_month.between(1, 3) & monthly.season_year.isin(YEARS)].copy()
    keys = ["season_year", "weather_grid_id"]
    if m.duplicated([*keys, "calendar_month"]).any() or not m.groupby(keys).size().eq(3).all():
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
        raise ValueError("Positive expected rainfall is required for the percent-of-normal map")
    sums["rain_pct"] = 100 * sums.rain_total_mm / sums.rain_expected_current_days_mm
    sums["temp_anomaly"] = sums.weighted_temperature_anomaly / sums.days_in_month
    coords = locations[["weather_grid_id", "weather_grid_lon", "weather_grid_lat"]].drop_duplicates()
    table = sums.reset_index().merge(coords, on="weather_grid_id", how="left", validate="many_to_one")
    expected = set(coords.weather_grid_id)
    if table.isna().any().any() or any(
        set(t.weather_grid_id) != expected for _, t in table.groupby("season_year")
    ):
        raise ValueError("Every season must use the same archived weather cells with finite values")
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
        "January–March weather across Zimbabwe’s sampled areas",
        fontsize=18.5,
        weight="bold",
        color=INK,
    )
    fig.text(
        0.046,
        0.927,
        f"Each column shows one harvest year. All years use the same {len(cells)} archived NASA POWER grid cells.",
        fontsize=10,
        color=MUTED,
    )
    grid = fig.add_gridspec(
        2, 3, left=0.045, right=0.974, top=0.84, bottom=0.20, wspace=0.07, hspace=0.10
    )
    rain_norm, temp_norm = Normalize(0, 200), Normalize(-2.5, 2.5)
    rain_cmap, temp_cmap = "BrBG", "RdBu_r"
    for col, year in enumerate(YEARS):
        d = weather.loc[weather.season_year.eq(year)]
        outlines = [geometries[key] for key in d.weather_grid_id]
        for level, (name, cmap, norm) in enumerate(
            [("rain_pct", rain_cmap, rain_norm), ("temp_anomaly", temp_cmap, temp_norm)]
        ):
            ax = fig.add_subplot(grid[level, col])
            _base(ax, country, cities, locator=level == 0 and col == 0, hatch_unmapped=True)
            _draw_cells(ax, outlines, d[name], cmap, norm)
            if level == 0:
                ax.set_title(str(year), fontsize=12, weight="bold", loc="center", color=INK, pad=9)
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
    fig.text(
        0.046,
        0.068,
        "Reference: 1991–2020 in each grid cell. Rainfall uses seasonal totals. Temperature uses monthly departures weighted by calendar days.",
        fontsize=8.4,
        color=MUTED,
    )
    fig.text(
        0.046,
        0.043,
        "Hatching marks land outside the archived grid footprint. Boundaries and cities: Natural Earth. Weather: NASA Langley POWER / MERRA-2.",
        fontsize=8.2,
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
    p = pd.read_csv(root / PREDICTIONS, usecols=["obs_id", "fold", "season_year", "y_t_ha", "A1"])
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
    yield_limit = max(6, np.ceil(cells.loc[eligible, ["yield_t_ha", "A1"]].max().max()))
    error_limit = max(1, np.ceil(cells.loc[eligible, "error"].abs().max()))
    y_norm, error_norm = Normalize(0, yield_limit), Normalize(-error_limit, error_limit)
    fig = plt.figure(figsize=(12.4, 5.9), facecolor="white")
    grid = fig.add_gridspec(1, 3, left=0.045, right=0.97, top=0.735, bottom=0.245, wspace=0.07)
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
            ("Prediction error", "Predicted minus measured", "error", "RdBu_r", error_norm),
        ]
    ):
        ax = fig.add_subplot(grid[0, i])
        _base(ax, country, cities, locator=i == 0)
        _draw_cells(ax, geo, cells[key].where(eligible), cmap, norm)
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
    handles = [
        Patch(facecolor=SPARSE, label="1–4 fields"),
        Patch(facecolor=LAND, edgecolor="#a2b1b2", linewidth=0.6, label="No mapped fields"),
    ]
    fig.legend(
        handles=handles,
        loc="center left",
        bbox_to_anchor=(0.76, 0.178),
        frameon=False,
        fontsize=8.4,
        labelcolor=INK,
    )
    s = _support(len(p), mapped, cells)
    fig.text(
        0.046,
        0.065,
        f"Color shows the same {s['colored_cells']} cells (25 km × 25 km, ≥5 fields) in all panels. Positive error means overprediction. Gray marks sparse or unsampled cells.",
        fontsize=8.3,
        color=MUTED,
    )
    fig.text(
        0.046,
        0.032,
        "Sources: PULA/Lacuna crop cuts and archived Presto experiment A1 predictions (folds 1–4). Boundary and cities: Natural Earth.",
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
                1 - ((p.A1 - p.y_t_ha) ** 2).sum() / ((p.y_t_ha - p.y_t_ha.mean()) ** 2).sum()
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
        "season_year",
        "yield_t_ha",
        "include_primary",
        "weather_grid_id",
        "weather_grid_lon",
        "weather_grid_lat",
    ]
    fields = pd.read_parquet(root / WEATHER / "harmonized_labels_weather.parquet", columns=cols)
    country_ll, country, cities = _basemap(root)
    mapped = _field_grid(fields, country_ll)
    with mpl.rc_context(
        {"font.family": "DejaVu Sans", "axes.unicode_minus": True, "figure.facecolor": "white"}
    ):
        measured, counts = _observed_map(fields, mapped, country, cities)
        weather, coverage = _weather_map(root, fields, country, cities)
        predicted, matched = _prediction_map(root, fields, country_ll, country, cities)
    figures = {"yield_map": measured, "weather_map": weather, "prediction_map": predicted}
    if output_dir is not None:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        for name, fig in figures.items():
            fig.savefig(
                folder / f"{name}.png", dpi=170, bbox_inches="tight", pad_inches=0.13, facecolor="white"
            )
        summary = {
            "cartography": "Lambert azimuthal equal-area, centered at 19° S, 29.5° E, WGS84",
            "yield_grid_metres": CELL_METRES,
            "minimum_records_for_cell_mean": MIN_RECORDS,
            "observed_yield": counts,
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
