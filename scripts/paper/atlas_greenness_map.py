"""Map three months of observed Sentinel-2 GCVI on a fixed set of Lacuna fields."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle

from scripts.paper.atlas_basemap import BASEMAP_CREDIT
from scripts.paper.atlas_maps import (
    _base,
    _basemap,
    _draw_field_points,
    _field_grid,
    _point_means,
    _scale,
)

MONTHS = ["2023-01", "2023-02", "2023-03"]
MONTH_NAMES = ["January", "February", "March"]


def matched_greenness(root):
    """One row per primary field with a finite, observed GCVI in all three months."""
    source = root / "data/processed/zimbabwe_midterm_v2"
    labels = pd.read_csv(
        source / "cleaned_labels.csv",
        usecols=[
            "obs_id",
            "lat",
            "lon",
            "season_year",
            "include_primary",
            "yield_kg_ha",
        ],
    )
    labels = labels.loc[labels.include_primary & labels.season_year.eq(2023)].copy()
    labels["yield_t_ha"] = labels.yield_kg_ha / 1000
    monthly = pd.read_csv(
        source / "monthly_features.csv",
        usecols=["obs_id", "month", "gcvi", "coverage_state"],
    )
    selected = monthly.loc[
        monthly.month.isin(MONTHS)
        & monthly.coverage_state.eq("clear")
        & np.isfinite(monthly.gcvi)
    ]
    observed = selected.pivot(index="obs_id", columns="month", values="gcvi")[MONTHS]
    matched = labels.merge(observed.dropna(), on="obs_id", validate="one_to_one")
    return matched, len(labels)


def build_greenness_map(root, output_dir):
    """Render all three months at the same recorded sites, including a common local view."""
    root, folder = Path(root), Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    country_ll, country, cities = _basemap(root)
    fields, total = matched_greenness(root)
    mapped = _field_grid(fields, country_ll)
    sites = _point_means(mapped, MONTHS)
    if sites.empty or not np.isfinite(sites[MONTHS]).all().all():
        raise ValueError(
            "The map requires finite GCVI for all three months at each plotted site"
        )

    # Use the yield plate's geographic selection so the two close-ups are comparable.
    window_source = folder / "map_data_summary.json"
    if not window_source.is_file():
        window_source = root / "results/visual_atlas/map_data_summary.json"
    windows = json.loads(window_source.read_text())["yield_detail_windows"]
    window = next(w for w in windows if w["provider_area"] == "Shurugwi")
    bounds = window["bounds_laea_m"]
    left, bottom, right, top = bounds
    local = sites.loc[sites.x.between(left, right) & sites.y.between(bottom, top)]
    if local.empty:
        raise ValueError("No three-month sites in the Shurugwi window")

    norm = Normalize(0, 6, clip=True)
    cmap = LinearSegmentedColormap.from_list(
        "canopy", colormaps["viridis"](np.linspace(0.16, 0.99, 180))
    )
    fig = plt.figure(figsize=(13.4, 8.5), facecolor="white")
    fig.text(
        0.045,
        0.936,
        "Seasonal greenness at maize fields",
        fontsize=23,
        color="#18373b",
        weight="bold",
        family="DejaVu Serif",
    )
    fig.text(
        0.046,
        0.889,
        f"Lacuna 2023   ·   {len(fields):,} fields observed in all three months   ·   {len(sites):,} recorded locations",
        fontsize=11,
        color="#415b5d",
    )
    upper = fig.add_gridspec(
        1, 3, left=0.045, right=0.956, top=0.80, bottom=0.44, wspace=0.075
    )
    lower = fig.add_gridspec(
        1, 3, left=0.045, right=0.956, top=0.37, bottom=0.175, wspace=0.075
    )
    for i, (month, name) in enumerate(zip(MONTHS, MONTH_NAMES, strict=True)):
        ax = fig.add_subplot(upper[0, i])
        _base(ax, country, cities, root=root, locator=i == 0, tone="dark")
        _draw_field_points(ax, sites, month, cmap, norm, size=6)
        ax.add_patch(
            Rectangle(
                (left, bottom),
                right - left,
                top - bottom,
                fill=False,
                ec="#fff4bf",
                lw=0.95,
                zorder=7,
            )
        )
        ax.set_title(
            f"{name}    ·    median GCVI {sites[month].median():.2f}",
            loc="left",
            fontsize=10.4,
            weight="bold",
            color="#18373b",
            pad=7,
        )
        zoom = fig.add_subplot(lower[0, i])
        _base(zoom, country, cities, root=root, bounds=bounds, tone="dark")
        _draw_field_points(zoom, local, month, cmap, norm, size=17)
        if i == 0:
            _scale(zoom, bounds, 10000)
        zoom.set_title(
            f"Shurugwi   /   {name}",
            loc="left",
            fontsize=9,
            weight="bold",
            color="#18373b",
            pad=4,
        )
    bar = fig.colorbar(
        ScalarMappable(norm=norm, cmap=cmap),
        cax=fig.add_axes([0.047, 0.115, 0.39, 0.017]),
        orientation="horizontal",
        extend="max",
        ticks=np.arange(0, 7),
    )
    bar.outline.set_visible(False)
    bar.set_label(
        "Green chlorophyll vegetation index (GCVI)", fontsize=9, color="#29474b"
    )
    bar.ax.tick_params(labelsize=8, length=2)
    fig.text(
        0.49,
        0.121,
        f"Local view   ·   {local.n.sum():,} fields at {len(local):,} sites",
        fontsize=10,
        color="#23484a",
        weight="bold",
    )
    fig.text(
        0.49,
        0.087,
        "The boxes locate the same 60 × 30 km window in each month.",
        fontsize=8.9,
        color="#415b5d",
    )
    fig.text(
        0.046,
        0.036,
        "Each dot shows the monthly GCVI at a sampled location. Records sharing a coordinate are averaged. Higher values indicate greener observed vegetation.",
        color="#324a4d",
        fontsize=8.7,
    )
    fig.text(0.046, 0.010, BASEMAP_CREDIT, color="#52666a", fontsize=7.4)
    fig.savefig(
        folder / "greenness_map.png",
        dpi=170,
        bbox_inches="tight",
        pad_inches=0.14,
        facecolor="white",
    )
    plt.close(fig)
    return pd.DataFrame(
        {
            "month": MONTHS,
            "primary_fields": total,
            "matched_fields": len(fields),
            "mapped_fields": len(mapped),
            "mapped_locations": len(sites),
            "median_site_gcvi": sites[MONTHS].median().to_numpy(),
            "closeup_fields": int(local.n.sum()),
            "closeup_locations": len(local),
            "closeup_median_gcvi": local[MONTHS].median().to_numpy(),
        }
    )
