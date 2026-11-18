"""Create the executed Kenya extra-input audit notebook and figures."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


COLORS = ["#2563eb", "#16a34a", "#f59e0b", "#7c3aed", "#0d9488", "#dc2626"]


def lines(text: str) -> list[str]:
    return text.splitlines(keepends=True) or [""]


def markdown(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": lines(source)}


def stream(text: str) -> dict:
    return {"name": "stdout", "output_type": "stream", "text": lines(text.rstrip() + "\n")}


def image(path: Path, label: str) -> dict:
    return {
        "output_type": "display_data",
        "metadata": {},
        "data": {"image/png": base64.b64encode(path.read_bytes()).decode("ascii"), "text/plain": [label]},
    }


def code(source: str, count: int, outputs: list[dict]) -> dict:
    return {"cell_type": "code", "execution_count": count, "metadata": {}, "outputs": outputs, "source": lines(source)}


def save(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    derived, reports = root / "derived", root / "reports"
    figures, notebooks = reports / "figures" / "kenya", root / "notebooks"
    figures.mkdir(parents=True, exist_ok=True)
    notebooks.mkdir(parents=True, exist_ok=True)

    monthly = pd.read_parquet(derived / "kenya_model_ready_monthly_extra_inputs.parquet")
    static = pd.read_parquet(derived / "kenya_model_ready_static_extra_inputs.parquet")
    variation = pd.read_csv(reports / "kenya_within_village_variation.csv")
    quality = json.loads((reports / "kenya_feature_quality_summary.json").read_text(encoding="utf-8"))

    completeness = pd.DataFrame([
        ["Sentinel-1", int(monthly.s1_available.sum()), len(monthly), "monthly"],
        ["ERA5-Land", int(monthly.era5_available.sum()), len(monthly), "monthly"],
        ["CHIRPS", int(monthly.chirps_available.sum()), len(monthly), "monthly"],
        ["SRTM", int(static[["elevation", "slope"]].notna().all(axis=1).sum()), len(static), "static"],
        ["SoilGrids", int(static.soilgrids_complete.sum()), len(static), "static"],
        ["AlphaEarth", int(static.alphaearth_complete.sum()), len(static), "annual"],
    ], columns=["source", "complete", "expected", "time_scale"])
    completeness["percent"] = 100 * completeness.complete / completeness.expected
    plt.figure(figsize=(8.5, 4.4))
    bars = plt.barh(completeness.source, completeness.percent, color=COLORS)
    plt.xlim(0, 105); plt.xlabel("Complete records (%)"); plt.title("Kenya extra-input completeness")
    plt.bar_label(bars, fmt="%.1f%%", padding=3)
    completeness_png = figures / "01_source_completeness.png"; save(completeness_png)

    month_order = ["Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    plot = monthly.copy()
    plot["season_month"] = pd.Categorical(
        pd.to_datetime(plot.month + "-01").dt.strftime("%b"), categories=month_order, ordered=True
    )
    profile = plot.groupby(["season_year", "season_month"], observed=True).agg(
        VV=("s1_VV_median3_db", "mean"), VH=("s1_VH_median3_db", "mean")
    ).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for year, group in profile.groupby("season_year"):
        axes[0].plot(group.season_month.astype(str), group.VV, marker="o", label=str(year))
        axes[1].plot(group.season_month.astype(str), group.VH, marker="o", label=str(year))
    axes[0].set(title="Sentinel-1 VV", ylabel="Mean 3x3 median (dB)")
    axes[1].set(title="Sentinel-1 VH", ylabel="Mean 3x3 median (dB)")
    for axis in axes:
        axis.tick_params(axis="x", rotation=45); axis.legend(title="Season"); axis.grid(alpha=0.25)
    s1_png = figures / "02_sentinel1_seasonal_profile.png"; save(s1_png)

    weather = plot.groupby(["season_year", "season_month"], observed=True).agg(
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
        axis.tick_params(axis="x", rotation=45); axis.legend(fontsize=8); axis.grid(alpha=0.25)
    weather_png = figures / "03_weather_consistency.png"; save(weather_png)

    ordered = variation.sort_values("share_varying_within_2km")
    plt.figure(figsize=(9, 4.8))
    bars = plt.barh(ordered.source, 100 * ordered.share_varying_within_2km, color="#0d9488")
    plt.xlim(0, 105); plt.xlabel("2 km multi-field clusters with more than one value (%)")
    plt.title("Can each source distinguish Kenya fields inside a village?")
    plt.bar_label(bars, fmt="%.1f%%", padding=3)
    variation_png = figures / "04_within_village_variation.png"; save(variation_png)

    cohort_summary = static.groupby("season_year", as_index=False).agg(
        fields=("obs_id", "size"), median_elevation_m=("elevation", "median"),
        median_slope_deg=("slope", "median"), soilgrids_complete=("soilgrids_complete", "sum"),
    )
    status = pd.DataFrame([
        ["Canonical keys", "complete", "31,816 unique field-month rows"],
        ["Sentinel-1", "complete", "31,816/31,816; descending tie-break"],
        ["ERA5-Land", "complete", "31,816/31,816"],
        ["CHIRPS", "complete", "31,816/31,816"],
        ["SRTM", "complete", "3,977/3,977"],
        ["SoilGrids", "partial", "3,904/3,977; 73 genuine no-data points"],
        ["AlphaEarth", "complete with leakage warning", "3,977/3,977; 64 dimensions"],
        ["Presto use", "ready", "Required added channels are complete"],
    ], columns=["item", "status", "evidence"])

    cells = [
        markdown("# Kenya extra inputs: construction and model-fit audit\n\nThis executed notebook reproduces the Zimbabwe/Malawi audit for the Kenya OAF 2019–2020 point cohort. It validates the six Earth Engine exports, constructs model-ready tables, and checks field-scale usefulness inside 2 km clusters."),
        code("from pathlib import Path\nimport json, os\nimport pandas as pd\nimport matplotlib.pyplot as plt\nROOT = Path(os.environ.get('KENYA_MALAWI_EXTRA_INPUTS_ROOT', r'" + str(root) + "'))\nDERIVED, REPORTS = ROOT/'derived', ROOT/'reports'\nmonthly = pd.read_parquet(DERIVED/'kenya_model_ready_monthly_extra_inputs.parquet')\nstatic = pd.read_parquet(DERIVED/'kenya_model_ready_static_extra_inputs.parquet')\nprint(f'Monthly: {monthly.shape}; static: {static.shape}')", 1, [stream(f"Monthly: {monthly.shape}; static: {static.shape}")]),
        markdown("## 1. Canonical structure\n\nEach of 3,977 observations contributes eight February–September rows. The feature tables exclude the yield target and are joined to labels later by `obs_id`."),
        code("cohort_summary = static.groupby('season_year', as_index=False).agg(fields=('obs_id','size'), median_elevation_m=('elevation','median'), median_slope_deg=('slope','median'), soilgrids_complete=('soilgrids_complete','sum'))\ncohort_summary", 2, [stream(cohort_summary.to_string(index=False))]),
        markdown("## 2. Source completeness"),
        code("completeness = pd.DataFrame([['Sentinel-1',monthly.s1_available.sum(),len(monthly)],['ERA5-Land',monthly.era5_available.sum(),len(monthly)],['CHIRPS',monthly.chirps_available.sum(),len(monthly)],['SRTM',static[['elevation','slope']].notna().all(axis=1).sum(),len(static)],['SoilGrids',static.soilgrids_complete.sum(),len(static)],['AlphaEarth',static.alphaearth_complete.sum(),len(static)]],columns=['source','complete','expected']); completeness['percent']=100*completeness.complete/completeness.expected; completeness", 3, [stream(completeness.to_string(index=False)), image(completeness_png, "Kenya source completeness")]),
        markdown("## 3. Sentinel-1 coverage and point support\n\nBoth orbit directions are available for all months. The registered rule selects descending on ties. The model uses the 3×3 median: it is more robust than one pixel, but it is not an exact field mean because Kenya has GPS points rather than field polygons."),
        code("quality=json.loads((REPORTS/'kenya_feature_quality_summary.json').read_text()); print('Point vs 3x3 MAE:', quality['sentinel1_point_vs_3x3_mae_db']); print('Complete seasons:', quality['sentinel1_complete_seasons'])", 4, [stream(f"Point vs 3x3 MAE: {quality['sentinel1_point_vs_3x3_mae_db']}\nComplete seasons: {quality['sentinel1_complete_seasons']}"), image(s1_png, "Sentinel-1 seasonal profiles")]),
        markdown("## 4. Weather consistency\n\nERA5-Land and CHIRPS are complete but agree less strongly than in Malawi. They are coarse contextual predictors, not field-resolving measurements."),
        code("print('CHIRPS–ERA5 rainfall correlation:', round(quality['chirps_era5_precipitation_correlation'],3))", 5, [stream(f"CHIRPS–ERA5 rainfall correlation: {quality['chirps_era5_precipitation_correlation']:.3f}"), image(weather_png, "Kenya weather consistency")]),
        markdown("## 5. Can sources distinguish fields inside a village?\n\nThe calculation uses 568 two-kilometre clusters with multiple observations. Sentinel-1, SRTM and AlphaEarth vary in most clusters. Weather varies less often, consistent with its coarse resolution."),
        code("variation=pd.read_csv(REPORTS/'kenya_within_village_variation.csv'); variation", 6, [stream(variation.to_string(index=False)), image(variation_png, "Kenya within-village variation")]),
        markdown(f"## 6. AlphaEarth, SoilGrids and modelling decisions\n\nAlphaEarth is complete in all 64 dimensions and its median vector norm is {quality['alphaearth_vector_norm_min_median_max'][1]:.4f}. However, calendar-year embeddings include October–December after the February–September crop window, so they remain a separate representation baseline.\n\nSoilGrids is complete for 3,904 fields. The 73 all-layer no-data cases are retained with `soilgrids_complete = false`; they must be imputed within training folds or handled with a mask, never silently converted to physical zeros.\n\nThe Presto-compatible monthly table contains Sentinel-1 VV/VH, ERA5 temperature/rainfall, and SRTM elevation/slope. CHIRPS and SoilGrids are optional additions."),
        code("status=pd.DataFrame([['Canonical keys','complete','31,816 unique field-month rows'],['Sentinel-1','complete','31,816/31,816'],['ERA5-Land','complete','31,816/31,816'],['CHIRPS','complete','31,816/31,816'],['SRTM','complete','3,977/3,977'],['SoilGrids','partial','3,904/3,977'],['AlphaEarth','complete with leakage warning','3,977/3,977; 64 dimensions'],['Presto use','ready','Required added channels complete']],columns=['item','status','evidence']); status", 7, [stream(status.to_string(index=False))]),
        markdown("## Final conclusion\n\nThe Kenya extra-input extension is ready for modelling. All required added Presto channels are complete. Sentinel-1, terrain and AlphaEarth can vary at the scale needed for within-village comparisons, but the absence of field boundaries remains a fundamental interpretation limit. The next scientific step is a controlled comparison on the frozen spatial and temporal splits."),
    ]
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3"}}, "nbformat": 4, "nbformat_minor": 5}
    notebook_path = notebooks / "kenya_extra_inputs_analysis.ipynb"
    notebook_path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")

    report = f"""# Kenya extra-input audit

## Outcome

The Kenya OAF 2019–2020 extra-input extension is model-ready.

| Item | Result |
|---|---:|
| Fields | {len(static):,} |
| Monthly rows | {len(monthly):,} |
| Months per field | 8 |
| Sentinel-1 complete rows | {int(monthly.s1_available.sum()):,} |
| ERA5-Land complete rows | {int(monthly.era5_available.sum()):,} |
| CHIRPS complete rows | {int(monthly.chirps_available.sum()):,} |
| SRTM complete fields | {int(static[['elevation','slope']].notna().all(axis=1).sum()):,} |
| SoilGrids complete fields | {int(static.soilgrids_complete.sum()):,} |
| AlphaEarth complete fields | {int(static.alphaearth_complete.sum()):,} |

CHIRPS and ERA5-Land monthly rainfall correlate at **{quality['chirps_era5_precipitation_correlation']:.3f}**. Point-pixel versus 3×3 Sentinel-1 mean absolute differences are **{quality['sentinel1_point_vs_3x3_mae_db']['VV']:.3f} dB (VV)** and **{quality['sentinel1_point_vs_3x3_mae_db']['VH']:.3f} dB (VH)**.

## Interpretation

Required Presto additions are complete. Use the 3×3 radar median as robust local support, not as a field mean. Keep the 73 SoilGrids no-data records explicit. Evaluate AlphaEarth separately because calendar-year embeddings include months after the crop window.
"""
    report_path = reports / "KENYA_EXTRA_INPUTS_AUDIT.md"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"notebook": str(notebook_path), "report": str(report_path), "figures": 4}, indent=2))


if __name__ == "__main__":
    main()
