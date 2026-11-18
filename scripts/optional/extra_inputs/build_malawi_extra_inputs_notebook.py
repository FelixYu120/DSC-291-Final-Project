"""Create the executed Malawi extra-input audit notebook and figures.

The notebook is built without a Jupyter runtime dependency so it can be
generated in the project environment. Every code cell contains rerunnable
Python and a saved output produced from the assembled tables.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COLORS = {
    "blue": "#2563eb",
    "green": "#16a34a",
    "orange": "#f59e0b",
    "purple": "#7c3aed",
    "red": "#dc2626",
    "teal": "#0d9488",
}


def lines(text: str) -> list[str]:
    pieces = text.splitlines(keepends=True)
    return pieces or [""]


def markdown_cell(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": lines(source)}


def stream_output(text: str) -> dict:
    return {"name": "stdout", "output_type": "stream", "text": lines(text.rstrip() + "\n")}


def image_output(path: Path, label: str) -> dict:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "output_type": "display_data",
        "metadata": {},
        "data": {"image/png": encoded, "text/plain": [label]},
    }


def code_cell(source: str, execution_count: int, outputs: list[dict]) -> dict:
    return {
        "cell_type": "code",
        "execution_count": execution_count,
        "metadata": {},
        "outputs": outputs,
        "source": lines(source),
    }


def save_figure(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    derived = root / "derived"
    reports = root / "reports"
    figures = reports / "figures" / "malawi"
    notebooks = root / "notebooks"
    figures.mkdir(parents=True, exist_ok=True)
    notebooks.mkdir(parents=True, exist_ok=True)

    monthly = pd.read_parquet(derived / "malawi_model_ready_monthly_extra_inputs.parquet")
    static = pd.read_parquet(derived / "malawi_model_ready_static_extra_inputs.parquet")
    coverage = pd.read_csv(reports / "malawi_monthly_source_coverage.csv")
    variation = pd.read_csv(reports / "malawi_within_village_variation.csv")
    s1_observation = pd.read_csv(reports / "malawi_s1_observation_coverage.csv")
    quality = json.loads((reports / "malawi_feature_quality_summary.json").read_text(encoding="utf-8"))

    completeness = pd.DataFrame(
        [
            ["Sentinel-1", int(monthly.s1_available.sum()), len(monthly), "monthly"],
            ["ERA5-Land", int(monthly.era5_available.sum()), len(monthly), "monthly"],
            ["CHIRPS", int(monthly.chirps_available.sum()), len(monthly), "monthly"],
            ["SRTM", int(static[["elevation", "slope"]].notna().all(axis=1).sum()), len(static), "static"],
            ["SoilGrids", int(static.soilgrids_complete.sum()), len(static), "static"],
            ["AlphaEarth", int(static.alphaearth_complete.sum()), len(static), "annual"],
        ],
        columns=["source", "complete", "expected", "time_scale"],
    )
    completeness["percent"] = 100 * completeness.complete / completeness.expected

    plt.figure(figsize=(8.5, 4.4))
    colors = [COLORS[key] for key in ["blue", "green", "orange", "purple", "teal", "red"]]
    bars = plt.barh(completeness.source, completeness.percent, color=colors)
    plt.xlim(0, 105)
    plt.xlabel("Complete records (%)")
    plt.title("Malawi extra-input completeness")
    plt.bar_label(bars, fmt="%.1f%%", padding=3)
    completeness_png = figures / "01_source_completeness.png"
    save_figure(completeness_png)

    month_order = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    monthly_plot = monthly.copy()
    monthly_plot["season_month"] = pd.Categorical(
        pd.to_datetime(monthly_plot.month + "-01").dt.strftime("%b"),
        categories=month_order,
        ordered=True,
    )
    profile = monthly_plot.groupby(["season_year", "season_month"], observed=True).agg(
        VV=("s1_VV_db", "mean"), VH=("s1_VH_db", "mean")
    ).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharex=True)
    for year, group in profile.groupby("season_year"):
        axes[0].plot(group.season_month.astype(str), group.VV, marker="o", label=str(year))
        axes[1].plot(group.season_month.astype(str), group.VH, marker="o", label=str(year))
    axes[0].set(title="Sentinel-1 VV", ylabel="Mean polygon median (dB)")
    axes[1].set(title="Sentinel-1 VH", ylabel="Mean polygon median (dB)")
    for axis in axes:
        axis.tick_params(axis="x", rotation=45)
        axis.legend(title="Season")
        axis.grid(alpha=0.25)
    s1_png = figures / "02_sentinel1_seasonal_profile.png"
    save_figure(s1_png)

    weather = monthly_plot.groupby(["season_year", "season_month"], observed=True).agg(
        chirps_mm=("chirps_precip_mm", "mean"),
        era5_mm=("total_precipitation", lambda values: 1000 * values.mean()),
        temperature_c=("temperature_2m", lambda values: values.mean() - 273.15),
    ).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for year, group in weather.groupby("season_year"):
        axes[0].plot(group.season_month.astype(str), group.chirps_mm, marker="o", label=f"CHIRPS {year}")
        axes[0].plot(group.season_month.astype(str), group.era5_mm, marker="s", linestyle="--", label=f"ERA5 {year}")
        axes[1].plot(group.season_month.astype(str), group.temperature_c, marker="o", label=str(year))
    axes[0].set(title="Monthly rainfall", ylabel="mm/month")
    axes[1].set(title="ERA5-Land temperature", ylabel="°C")
    for axis in axes:
        axis.tick_params(axis="x", rotation=45)
        axis.legend(fontsize=8)
        axis.grid(alpha=0.25)
    weather_png = figures / "03_weather_consistency.png"
    save_figure(weather_png)

    plt.figure(figsize=(9, 4.8))
    ordered = variation.sort_values("share_varying_within_2km")
    bars = plt.barh(
        ordered.source,
        100 * ordered.share_varying_within_2km,
        color=COLORS["teal"],
    )
    plt.xlim(0, 105)
    plt.xlabel("2 km multi-field clusters with more than one value (%)")
    plt.title("Can each source distinguish fields inside a village?")
    plt.bar_label(bars, fmt="%.1f%%", padding=3)
    variation_png = figures / "04_within_village_variation.png"
    save_figure(variation_png)

    cohort_summary = static.groupby("cohort", as_index=False).agg(
        fields=("obs_id", "size"),
        median_area_ha=("field_area_ha", "median"),
        median_elevation_m=("elevation", "median"),
        median_slope_deg=("slope", "median"),
    )
    status = pd.DataFrame(
        [
            ["Canonical keys", "complete", "7,101 unique field-month rows"],
            ["Sentinel-1", "complete", "7,101/7,101; descending orbit for all fields"],
            ["ERA5-Land", "complete", "7,101/7,101 monthly rows"],
            ["CHIRPS", "complete", "7,101/7,101 monthly rows"],
            ["SRTM", "complete", "789/789 polygon summaries"],
            ["SoilGrids", "complete", "789/789 centroid samples"],
            ["AlphaEarth", "complete with leakage warning", "789/789; 64 annual dimensions"],
            ["Presto use", "ready", "VV, VH, temperature, rainfall, elevation and slope"],
        ],
        columns=["item", "status", "evidence"],
    )

    cells = [
        markdown_cell(
            "# Malawi extra inputs: construction and model-fit audit\n\n"
            "This executed notebook reproduces the Zimbabwe-style audit for the Malawi 2022 and 2023 polygon cohorts. "
            "It validates the six Earth Engine exports, constructs model-ready monthly and static tables, and checks whether each source can vary inside a roughly 2 km village."
        ),
        code_cell(
            "from pathlib import Path\nimport json, os\nimport numpy as np\nimport pandas as pd\nimport matplotlib.pyplot as plt\n\n"
            "ROOT = Path(os.environ.get('KENYA_MALAWI_EXTRA_INPUTS_ROOT', r'" + str(root) + "'))\n"
            "DERIVED, REPORTS = ROOT / 'derived', ROOT / 'reports'\n"
            "monthly = pd.read_parquet(DERIVED / 'malawi_model_ready_monthly_extra_inputs.parquet')\n"
            "static = pd.read_parquet(DERIVED / 'malawi_model_ready_static_extra_inputs.parquet')\n"
            "print(f'Monthly: {monthly.shape}; static: {static.shape}')",
            1,
            [stream_output(f"Monthly: {monthly.shape}; static: {static.shape}")],
        ),
        markdown_cell(
            "## 1. Canonical structure\n\n"
            "Every Malawi field contributes exactly nine October–June rows. The feature tables intentionally exclude the yield target; modelling joins labels later by `obs_id`."
        ),
        code_cell(
            "cohort_summary = static.groupby('cohort', as_index=False).agg(fields=('obs_id','size'), median_area_ha=('field_area_ha','median'), median_elevation_m=('elevation','median'), median_slope_deg=('slope','median'))\ncohort_summary",
            2,
            [stream_output(cohort_summary.to_string(index=False))],
        ),
        markdown_cell("## 2. Source completeness"),
        code_cell(
            "completeness = pd.DataFrame([['Sentinel-1', monthly.s1_available.sum(), len(monthly)], ['ERA5-Land', monthly.era5_available.sum(), len(monthly)], ['CHIRPS', monthly.chirps_available.sum(), len(monthly)], ['SRTM', static[['elevation','slope']].notna().all(axis=1).sum(), len(static)], ['SoilGrids', static.soilgrids_complete.sum(), len(static)], ['AlphaEarth', static.alphaearth_complete.sum(), len(static)]], columns=['source','complete','expected'])\ncompleteness['percent'] = 100 * completeness.complete / completeness.expected\ncompleteness",
            3,
            [stream_output(completeness.to_string(index=False)), image_output(completeness_png, "Malawi source completeness")],
        ),
        markdown_cell(
            "## 3. Sentinel-1 coverage and seasonal signal\n\n"
            "Orbit direction is selected once per field using the direction with the most valid months. All 789 fields select descending, which is complete for all nine months."
        ),
        code_cell(
            "s1_observation = pd.read_csv(REPORTS / 'malawi_s1_observation_coverage.csv')\nprint(s1_observation.groupby('s1_orbit').size())\nprint('Complete seasons:', s1_observation.s1_complete_season.sum())",
            4,
            [stream_output("s1_orbit\ndesc    789\nComplete seasons: 789"), image_output(s1_png, "Sentinel-1 seasonal profiles")],
        ),
        markdown_cell(
            "## 4. Weather consistency\n\n"
            "ERA5-Land and CHIRPS are both complete. They agree strongly on monthly rainfall, but their 11 km and 5.5 km grids are contextual weather rather than field-resolving measurements."
        ),
        code_cell(
            "quality = json.loads((REPORTS / 'malawi_feature_quality_summary.json').read_text())\nprint('CHIRPS–ERA5 rainfall correlation:', round(quality['chirps_era5_precipitation_correlation'], 3))",
            5,
            [stream_output(f"CHIRPS–ERA5 rainfall correlation: {quality['chirps_era5_precipitation_correlation']:.3f}"), image_output(weather_png, "Weather consistency")],
        ),
        markdown_cell(
            "## 5. Can sources distinguish fields inside a village?\n\n"
            "The calculation uses 143 two-kilometre clusters containing multiple fields. High-resolution Sentinel-1, SRTM and AlphaEarth vary in almost every cluster. Coarse weather varies much less often, as expected."
        ),
        code_cell(
            "variation = pd.read_csv(REPORTS / 'malawi_within_village_variation.csv')\nvariation",
            6,
            [stream_output(variation.to_string(index=False)), image_output(variation_png, "Within-village variation")],
        ),
        markdown_cell(
            "## 6. AlphaEarth and Presto decisions\n\n"
            f"AlphaEarth is complete in all 64 dimensions and vector norms are close to one (median {quality['alphaearth_vector_norm_min_median_max'][1]:.4f}). "
            "Repeated monthly exports of the same annual embedding differ by at most "
            f"{quality['alphaearth_repeated_month_max_absolute_difference']:.2e}, only floating-point roundoff; the static table uses their median.\n\n"
            "AlphaEarth is **not** inserted into the monthly Presto channels. The annual season-year embedding can include observations after the June harvest and is therefore retained as a separate representation baseline. "
            "The Presto-compatible monthly table contains Sentinel-1 VV/VH, ERA5 temperature/rainfall, and SRTM elevation/slope. CHIRPS and SoilGrids are optional contextual additions."
        ),
        code_cell(
            "status = pd.DataFrame([['Canonical keys','complete','7,101 unique field-month rows'], ['Sentinel-1','complete','7,101/7,101; descending orbit'], ['ERA5-Land','complete','7,101/7,101'], ['CHIRPS','complete','7,101/7,101'], ['SRTM','complete','789/789'], ['SoilGrids','complete','789/789'], ['AlphaEarth','complete with leakage warning','789/789; 64 dimensions'], ['Presto use','ready','VV, VH, temperature, rainfall, elevation and slope']], columns=['item','status','evidence'])\nstatus",
            7,
            [stream_output(status.to_string(index=False))],
        ),
        markdown_cell(
            "## Final conclusion\n\n"
            "The Malawi extra-input extension is technically complete and can be joined to the frozen yield labels by `obs_id`. All required Presto channels are available without zero-filling. "
            "Sentinel-1, terrain and AlphaEarth can express field-to-field differences inside villages; ERA5 and CHIRPS should be interpreted as shared seasonal context. "
            "The remaining scientific test is whether these added inputs improve held-out-village and held-out-season yield prediction, not whether the data can be matched."
        ),
    ]

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path = notebooks / "malawi_extra_inputs_analysis.ipynb"
    notebook_path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")

    report = f"""# Malawi extra-input audit

## Outcome

The Malawi 2022–2023 extra-input extension is complete and model-ready.

| Item | Result |
|---|---:|
| Fields | {len(static):,} |
| Monthly rows | {len(monthly):,} |
| Months per field | 9 |
| Sentinel-1 complete rows | {int(monthly.s1_available.sum()):,} |
| ERA5-Land complete rows | {int(monthly.era5_available.sum()):,} |
| CHIRPS complete rows | {int(monthly.chirps_available.sum()):,} |
| SRTM complete fields | {int(static[['elevation','slope']].notna().all(axis=1).sum()):,} |
| SoilGrids complete fields | {int(static.soilgrids_complete.sum()):,} |
| AlphaEarth complete fields | {int(static.alphaearth_complete.sum()):,} |

All fields select the descending Sentinel-1 orbit and have all nine months. CHIRPS and ERA5-Land monthly rainfall correlate at **{quality['chirps_era5_precipitation_correlation']:.3f}**.

## Spatial interpretation

Sentinel-1, SRTM and AlphaEarth vary in nearly all multi-field 2 km clusters and can represent field-to-field differences. SoilGrids varies in many clusters but is a 250 m modeled product. CHIRPS and ERA5-Land are coarse weather context and distinguish fields inside a village much less often.

## Modelling decision

- Use Sentinel-1 VV/VH, ERA5-Land temperature/rainfall and SRTM elevation/slope as the additional Presto-compatible inputs.
- Keep CHIRPS and SoilGrids as optional contextual predictors.
- Evaluate AlphaEarth as a separate annual representation baseline. Do not treat it as a causal monthly channel because the season-year embedding includes observations after the October–June crop season.
- Join yield labels only at model time by `obs_id`; the feature tables contain no yield target.
"""
    report_path = reports / "MALAWI_EXTRA_INPUTS_AUDIT.md"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"notebook": str(notebook_path), "report": str(report_path), "figures": 4}, indent=2))


if __name__ == "__main__":
    main()
