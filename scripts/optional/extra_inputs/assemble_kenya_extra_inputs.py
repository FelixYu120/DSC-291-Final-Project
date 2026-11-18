"""Assemble and audit Kenya OAF 2019-2020 extra inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


STEM = "kenya_presto_s1_era5_srtm_2019_2020"
KEYS = ["obs_id", "season_year", "month"]
EXPECTED_ROWS = 31816
EXPECTED_OBSERVATIONS = 3977


def locate_exports(root: Path) -> list[Path]:
    for folder in (root, root / "incoming", root / "incoming" / "kenya"):
        paths = sorted(folder.glob(f"{STEM}_part*.csv"))
        if paths:
            return paths
    return []


def varying_share(frame: pd.DataFrame, column: str) -> tuple[int, int, float]:
    multi = frame.groupby(["cohort", "cluster_2km"], dropna=True).filter(lambda group: len(group) > 1)
    counts = multi.groupby(["cohort", "cluster_2km"])[column].nunique(dropna=True)
    total = int(len(counts))
    varying = int(counts.gt(1).sum())
    return total, varying, float(varying / total) if total else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=Path("data/v2/processed/labels_v2.parquet"))
    args = parser.parse_args()
    root = args.root.resolve()
    derived, reports = root / "derived", root / "reports"
    for folder in (derived, reports, reports / "figures" / "kenya"):
        folder.mkdir(parents=True, exist_ok=True)

    month_keys = pd.read_csv(
        derived / "kenya_field_months_2019_2020.csv",
        dtype={"obs_id": "string", "month": "string"},
    )
    if len(month_keys) != EXPECTED_ROWS or month_keys.duplicated(KEYS).any():
        raise RuntimeError("Canonical Kenya month keys are incomplete or duplicated")

    paths = locate_exports(root)
    if len(paths) != 6:
        raise RuntimeError(f"Expected six Kenya exports; found {len(paths)}")
    parts = []
    for path in paths:
        if path.stat().st_size <= 2:
            raise RuntimeError(f"Earth Engine export is empty: {path.name}")
        part = pd.read_csv(path, dtype={"obs_id": "string", "month": "string"})
        part["source_export"] = path.name
        parts.append(part)
    gee = pd.concat(parts, ignore_index=True)
    if len(gee) != EXPECTED_ROWS or gee.duplicated(KEYS).any():
        raise RuntimeError("Kenya Earth Engine rows are incomplete or duplicated")
    key_check = month_keys[KEYS].merge(gee[KEYS], on=KEYS, how="outer", indicator=True, validate="one_to_one")
    if not key_check["_merge"].eq("both").all():
        raise RuntimeError(f"Earth Engine keys do not match canonical keys: {key_check['_merge'].value_counts().to_dict()}")

    ignore = set(KEYS + ["system:index", "source_export", "cohort", "lat", "lon", ".geo"])
    for column in [name for name in gee.columns if name not in ignore]:
        gee[column] = pd.to_numeric(gee[column], errors="coerce").replace(-9999, np.nan)
    gee = gee.copy()

    for direction in ("asc", "desc"):
        gee[f"valid_{direction}"] = (
            gee[f"s1_{direction}_count"].fillna(0).gt(0)
            & gee[f"VV_{direction}_median3"].notna()
            & gee[f"VH_{direction}_median3"].notna()
        )
    orbit_coverage = gee.groupby("obs_id")[["valid_asc", "valid_desc"]].sum()
    orbit_coverage["s1_orbit"] = np.where(
        orbit_coverage.valid_asc > orbit_coverage.valid_desc, "asc", "desc"
    )
    gee = gee.merge(orbit_coverage[["s1_orbit"]], on="obs_id", validate="many_to_one")
    for band in ("VV", "VH"):
        for statistic in ("point", "median3"):
            gee[f"s1_{band}_{statistic}_db"] = np.where(
                gee.s1_orbit.eq("asc"),
                gee[f"{band}_asc_{statistic}"],
                gee[f"{band}_desc_{statistic}"],
            )
    gee["s1_scene_count"] = np.where(
        gee.s1_orbit.eq("asc"), gee.s1_asc_count, gee.s1_desc_count
    )
    gee["s1_available"] = (
        gee.s1_scene_count.fillna(0).gt(0)
        & gee[["s1_VV_median3_db", "s1_VH_median3_db"]].notna().all(axis=1)
    )

    gee["presto_VV_recomputed"] = (gee.s1_VV_median3_db + 25.0) / 25.0
    gee["presto_VH_recomputed"] = (gee.s1_VH_median3_db + 25.0) / 25.0
    gee["presto_VV"] = np.where(
        gee.s1_orbit.eq("asc"), gee.VV_asc_median3_presto, gee.VV_desc_median3_presto
    )
    gee["presto_VH"] = np.where(
        gee.s1_orbit.eq("asc"), gee.VH_asc_median3_presto, gee.VH_desc_median3_presto
    )
    gee["presto_temperature_2m"] = (gee.temperature_2m - 272.15) / 35.0
    gee["presto_total_precipitation"] = gee.total_precipitation / 0.03
    gee["presto_elevation"] = gee.elevation / 2000.0
    gee["presto_slope"] = gee.slope / 50.0
    gee["era5_available"] = gee[["temperature_2m", "total_precipitation"]].notna().all(axis=1)
    gee["chirps_available"] = gee.chirps_precip_mm.notna()
    gee["srtm_available"] = gee[["elevation", "slope"]].notna().all(axis=1)

    normalization_diffs = {
        "VV": float((gee.presto_VV_recomputed - gee.presto_VV).abs().max()),
        "VH": float((gee.presto_VH_recomputed - gee.presto_VH).abs().max()),
        "temperature": float((gee.presto_temperature_2m - gee.temperature_2m_presto).abs().max()),
        "precipitation": float((gee.presto_total_precipitation - gee.total_precipitation_presto).abs().max()),
        "elevation": float((gee.presto_elevation - gee.elevation_presto).abs().max()),
        "slope": float((gee.presto_slope - gee.slope_presto).abs().max()),
    }

    alpha_columns = [f"A{index:02d}" for index in range(64)]
    if set(alpha_columns).difference(gee.columns):
        raise RuntimeError("AlphaEarth dimensions are incomplete")
    alpha_ranges = gee.groupby("obs_id")[alpha_columns].agg(lambda values: values.max() - values.min())
    alpha_repeat_max_difference = float(alpha_ranges.max(axis=None))
    if alpha_repeat_max_difference > 1e-10:
        raise RuntimeError(f"AlphaEarth changes materially within a field-year: {alpha_repeat_max_difference}")

    monthly_columns = KEYS + [
        "s1_orbit", "s1_scene_count", "s1_available",
        "s1_VV_point_db", "s1_VH_point_db", "s1_VV_median3_db", "s1_VH_median3_db",
        "temperature_2m", "total_precipitation", "era5_available",
        "chirps_precip_mm", "chirps_available", "elevation", "slope", "srtm_available",
        "presto_VV", "presto_VH", "presto_temperature_2m", "presto_total_precipitation",
        "presto_elevation", "presto_slope",
    ]
    monthly = month_keys.merge(gee[monthly_columns], on=KEYS, how="left", validate="one_to_one")

    label_columns = [
        "obs_id", "cohort", "season_year", "geometry_type", "lat", "lon",
        "cluster_2km", "admin_unit", "site_unit", "site_distance_km", "include_primary",
    ]
    labels = pd.read_parquet(args.labels.resolve(), columns=label_columns)
    labels = labels[labels.cohort.eq("kenya_oaf_2019_2020")].copy()
    if len(labels) != EXPECTED_OBSERVATIONS or not labels.obs_id.is_unique:
        raise RuntimeError("Data-v2 Kenya metadata do not match expected observations")
    soil = pd.read_csv(derived / "soilgrids_kenya_features.csv", dtype={"obs_id": "string"})
    alpha = gee.groupby(["obs_id", "season_year"], as_index=False)[alpha_columns].median()
    alpha["alphaearth_complete"] = alpha[alpha_columns].notna().all(axis=1)
    alpha["alphaearth_vector_norm"] = np.sqrt(alpha[alpha_columns].pow(2).sum(axis=1))
    srtm = gee[["obs_id", "elevation", "slope"]].drop_duplicates("obs_id")
    static = labels.merge(srtm, on="obs_id", validate="one_to_one").merge(
        soil, on="obs_id", validate="one_to_one"
    ).merge(alpha, on=["obs_id", "season_year"], validate="one_to_one")

    monthly_csv = derived / "kenya_model_ready_monthly_extra_inputs.csv"
    monthly_parquet = derived / "kenya_model_ready_monthly_extra_inputs.parquet"
    static_csv = derived / "kenya_model_ready_static_extra_inputs.csv"
    static_parquet = derived / "kenya_model_ready_static_extra_inputs.parquet"
    monthly.to_csv(monthly_csv, index=False)
    monthly.to_parquet(monthly_parquet, index=False)
    static.to_csv(static_csv, index=False)
    static.to_parquet(static_parquet, index=False)

    coverage = monthly.groupby(["season_year", "month"], as_index=False).agg(
        expected_rows=("obs_id", "size"), s1_complete_rows=("s1_available", "sum"),
        era5_complete_rows=("era5_available", "sum"), chirps_complete_rows=("chirps_available", "sum"),
        srtm_complete_rows=("srtm_available", "sum"),
    )
    for source in ("s1", "era5", "chirps", "srtm"):
        coverage[f"{source}_complete_pct"] = 100 * coverage[f"{source}_complete_rows"] / coverage.expected_rows
    coverage.to_csv(reports / "kenya_monthly_source_coverage.csv", index=False)

    s1_observation = monthly.groupby("obs_id", as_index=False).agg(
        season_year=("season_year", "first"), s1_orbit=("s1_orbit", "first"),
        expected_months=("month", "size"), s1_valid_months=("s1_available", "sum"),
    )
    s1_observation["s1_complete_season"] = s1_observation.s1_valid_months.eq(s1_observation.expected_months)
    s1_observation.to_csv(reports / "kenya_s1_observation_coverage.csv", index=False)

    seasonal = monthly.groupby("obs_id", as_index=False).agg(
        s1_VV_season_mean=("s1_VV_median3_db", "mean"),
        chirps_season_total_mm=("chirps_precip_mm", "sum"),
        era5_season_total_m=("total_precipitation", "sum"),
    )
    village = static.merge(seasonal, on="obs_id", validate="one_to_one")
    variables = [
        ("Sentinel-1 VV seasonal mean", "s1_VV_season_mean", "10 m 3x3 median", 6),
        ("CHIRPS seasonal rainfall", "chirps_season_total_mm", "~5.5 km", 6),
        ("ERA5-Land seasonal rainfall", "era5_season_total_m", "~11 km", 8),
        ("SRTM elevation", "elevation", "30 m", 3),
        ("SoilGrids pH 0-5 cm", "soilgrids_phh2o_0_5cm_mean", "250 m", 3),
        ("SoilGrids SOC 0-5 cm", "soilgrids_soc_0_5cm_mean", "250 m", 3),
        ("AlphaEarth A00", "A00", "10 m point pixel", 8),
    ]
    rows = []
    for source, column, resolution, decimals in variables:
        rounded = f"__{column}"
        village[rounded] = village[column].round(decimals)
        total, varying, share = varying_share(village, rounded)
        rows.append({"source": source, "resolution": resolution, "multi_field_2km_clusters": total,
                     "clusters_with_more_than_one_value": varying, "share_varying_within_2km": share})
    variation = pd.DataFrame(rows)
    variation.to_csv(reports / "kenya_within_village_variation.csv", index=False)

    quality = {
        "observations": EXPECTED_OBSERVATIONS,
        "monthly_rows": EXPECTED_ROWS,
        "source_complete": {
            "sentinel1_rows": int(monthly.s1_available.sum()),
            "era5_rows": int(monthly.era5_available.sum()),
            "chirps_rows": int(monthly.chirps_available.sum()),
            "srtm_observations": int(static[["elevation", "slope"]].notna().all(axis=1).sum()),
            "soilgrids_observations": int(static.soilgrids_complete.sum()),
            "alphaearth_observations": int(static.alphaearth_complete.sum()),
        },
        "sentinel1_orbits": orbit_coverage.s1_orbit.value_counts().to_dict(),
        "sentinel1_complete_seasons": int(s1_observation.s1_complete_season.sum()),
        "sentinel1_point_vs_3x3_mae_db": {
            "VV": float((monthly.s1_VV_point_db - monthly.s1_VV_median3_db).abs().mean()),
            "VH": float((monthly.s1_VH_point_db - monthly.s1_VH_median3_db).abs().mean()),
        },
        "chirps_era5_precipitation_correlation": float(
            monthly[["chirps_precip_mm", "total_precipitation"]].corr().iloc[0, 1]
        ),
        "alphaearth_dimensions": 64,
        "alphaearth_repeated_month_max_absolute_difference": alpha_repeat_max_difference,
        "alphaearth_vector_norm_min_median_max": [
            float(static.alphaearth_vector_norm.min()), float(static.alphaearth_vector_norm.median()),
            float(static.alphaearth_vector_norm.max()),
        ],
        "presto_normalization_max_absolute_difference": normalization_diffs,
        "soilgrids_missing_observations": int((~static.soilgrids_complete).sum()),
        "alphaearth_leakage_warning": "Calendar-year embeddings include October-December after the February-September crop window; use as a separate annual baseline.",
        "kenya_geometry_limit": "Provider locations are GPS points and may be homesteads; the 3x3 radar median is a robust local support, not a field mean.",
    }
    (reports / "kenya_feature_quality_summary.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")

    dictionary = pd.DataFrame([
        ["s1_VV_median3_db", "monthly", "Sentinel-1", "dB", "10 m 3x3 median", "Presto radar input; not a field mean"],
        ["s1_VH_median3_db", "monthly", "Sentinel-1", "dB", "10 m 3x3 median", "Presto radar input; not a field mean"],
        ["temperature_2m", "monthly", "ERA5-Land", "K", "~11 km", "Contextual weather"],
        ["total_precipitation", "monthly", "ERA5-Land", "m/month", "~11 km", "Contextual weather"],
        ["chirps_precip_mm", "monthly", "CHIRPS v2", "mm/month", "~5.5 km", "Independent rainfall"],
        ["elevation / slope", "static", "SRTM", "m / degrees", "30 m point", "Terrain channels"],
        ["soilgrids_*", "static", "SoilGrids 2.0", "property-specific", "250 m point", "Optional; 73 no-data points"],
        ["A00-A63", "annual", "AlphaEarth", "dimensionless", "10 m point", "Separate baseline; leakage warning"],
    ], columns=["variable", "time_scale", "source", "unit", "spatial_support", "recommended_use"])
    dictionary.to_csv(reports / "kenya_extra_inputs_data_dictionary.csv", index=False)

    summary = {
        "status": "complete", "observations": EXPECTED_OBSERVATIONS, "monthly_rows": EXPECTED_ROWS,
        "months_per_observation": sorted(monthly.groupby("obs_id").size().unique().tolist()),
        "season_counts": static.groupby("season_year").size().to_dict(),
        "outputs": {"monthly_csv": str(monthly_csv.relative_to(root)), "monthly_parquet": str(monthly_parquet.relative_to(root)),
                    "static_csv": str(static_csv.relative_to(root)), "static_parquet": str(static_parquet.relative_to(root))},
        "quality_report": str((reports / "kenya_feature_quality_summary.json").relative_to(root)),
        "village_variation_report": str((reports / "kenya_within_village_variation.csv").relative_to(root)),
    }
    (reports / "kenya_combined_inputs_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
