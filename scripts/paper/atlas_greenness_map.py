"""Map three months of observed Sentinel-2 GCVI on a fixed set of Lacuna fields."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Patch

from scripts.paper.atlas_basemap import BASEMAP_CREDIT
from scripts.paper.atlas_maps import (
    MIN_RECORDS,
    _base,
    _basemap,
    _cell_means,
    _draw_cells,
    _field_grid,
    _yield_cells,
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
    """Write a three-panel figure and return the support and values shown in each panel."""
    root, folder = Path(root), Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    country_ll, country, cities = _basemap(root)
    fields, total = matched_greenness(root)
    mapped = _field_grid(fields, country_ll)
    cells = _cell_means(mapped, MONTHS)
    supported = cells.n.ge(MIN_RECORDS)
    means = cells.loc[supported, MONTHS]
    if means.empty or not np.isfinite(means).all().all():
        raise ValueError(
            "All displayed cells must contain matched, finite three-month observations"
        )
    polygons = _yield_cells(cells, country)
    # A common range encompasses every cell mean, in index units.
    norm = Normalize(np.floor(means.min().min()), np.ceil(means.max().max()))
    cmap = LinearSegmentedColormap.from_list(
        "canopy", colormaps["viridis"](np.linspace(0.17, 0.97, 128))
    )
    fig = plt.figure(figsize=(13.3, 7.0), facecolor="white")
    fig.text(
        0.045,
        0.935,
        "Seasonal greenness across the same maize fields",
        fontsize=20,
        color="#18373b",
        weight="bold",
        family="DejaVu Serif",
    )
    fig.text(
        0.046,
        0.878,
        f"Lacuna · 2023 harvest   /   {len(fields):,} fields with clear Sentinel-2 observations in all three months",
        fontsize=10.6,
        color="#415b5d",
    )
    grid = fig.add_gridspec(
        1, 3, left=0.045, right=0.957, top=0.76, bottom=0.27, wspace=0.072
    )
    for i, (month, name) in enumerate(zip(MONTHS, MONTH_NAMES, strict=True)):
        ax = fig.add_subplot(grid[0, i])
        _base(ax, country, cities, root=root, locator=i == 0, tone="dark")
        _draw_cells(
            ax, polygons, cells[month].where(supported), cmap, norm, opacity=0.96
        )
        ax.set_title(
            f"{name}    ·    median GCVI {means[month].median():.2f}",
            loc="left",
            fontsize=10.5,
            weight="bold",
            color="#18373b",
            pad=7,
        )
    bar = fig.colorbar(
        ScalarMappable(norm=norm, cmap=cmap),
        cax=fig.add_axes([0.047, 0.195, 0.40, 0.019]),
        orientation="horizontal",
        ticks=np.arange(norm.vmin, norm.vmax + 1),
    )
    bar.outline.set_visible(False)
    bar.set_label(
        "Mean green chlorophyll vegetation index (GCVI)", fontsize=9, color="#29474b"
    )
    bar.ax.tick_params(labelsize=8, length=2)
    fig.legend(
        [Patch(facecolor="none", edgecolor="#7c898b")],
        ["1–4 matched fields"],
        loc="center left",
        bbox_to_anchor=(0.53, 0.205),
        frameon=False,
        fontsize=9,
    )
    fig.text(
        0.046,
        0.100,
        f"Colored 25 km cells average at least five fields. The same {int(supported.sum())} colored cells and "
        f"{cells.loc[supported, 'n'].sum():,} fields contribute each month. Higher GCVI indicates greener vegetation.",
        color="#324a4d",
        fontsize=9,
    )
    fig.text(0.046, 0.057, BASEMAP_CREDIT, color="#52666a", fontsize=7.6)
    path = folder / "greenness_map.png"
    fig.savefig(path, dpi=170, bbox_inches="tight", pad_inches=0.14, facecolor="white")
    plt.close(fig)
    return pd.DataFrame(
        {
            "month": MONTHS,
            "primary_fields": total,
            "fields_with_all_three_months": len(fields),
            "inside_outline": len(mapped),
            "colored_cells": int(supported.sum()),
            "fields_in_colored_cells": int(cells.loc[supported, "n"].sum()),
            "median_of_cell_means_gcvi": means.median().to_numpy(),
        }
    )
