"""Assemble and audit Malawi 2022-2023 extra inputs.

This is the polygon-cohort counterpart of the Zimbabwe extra-input assembly.
It combines the six Earth Engine exports, canonical data-v2 keys, SoilGrids,
and frozen non-target field metadata. Outputs are written outside Git by
default and never modify the team labels, database, or split files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


STEM = "malawi_presto_s1_era5_srtm_2022_2023"
KEYS = ["obs_id", "season_year", "month"]
EXPECTED_ROWS = 7101
EXPECTED_OBSERVATIONS = 789


def locate_exports(root: Path) -> list[Path]:
    candidates = [root, root / "incoming", root / "incoming" / "malawi"]
    for folder in candidates:
        paths = sorted(folder.glob(f"{STEM}_part*.csv"))
        if paths:
            return paths
    return []


def load_exports(paths: list[Path]) -> pd.DataFrame:
    if len(paths) != 6:
        raise RuntimeError(f"Expected six Malawi exports; found {len(paths)}")
    parts = []
    for path in paths:
        if path.stat().st_size <= 2:
            raise RuntimeError(f"Earth Engine export is empty: {path.name}")
        part = pd.read_csv(path, dtype={"obs_id": "string", "month": "string"})
        part["source_export"] = path.name
        parts.append(part)
    gee = pd.concat(parts, ignore_index=True)
    missing = set(KEYS).difference(gee.columns)
    if missing:
        raise RuntimeError(f"Earth Engine export lacks key columns: {sorted(missing)}")
    if len(gee) != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS:,} rows; received {len(gee):,}")
    if gee.duplicated(KEYS).any():
        raise RuntimeError("Duplicate obs_id-season_year-month keys in Earth Engine exports")
    return gee


def choose_sentinel1_orbit(gee: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    for direction in ("asc", "desc"):
        gee[f"valid_{direction}"] = (
            gee[f"s1_{direction}_count"].fillna(0).gt(0)
            & gee[f"VV_{direction}"].notna()
            & gee[f"VH_{direction}"].notna()
        )
    coverage = gee.groupby("obs_id")[["valid_asc", "valid_desc"]].sum()
    coverage["s1_orbit"] = np.where(
        coverage["valid_asc"] > coverage["valid_desc"], "asc", "desc"
    )
    gee = gee.merge(coverage[["s1_orbit"]], on="obs_id", validate="many_to_one")
    for band in ("VV", "VH"):
        gee[f"s1_{band}_db"] = np.where(
            gee["s1_orbit"].eq("asc"), gee[f"{band}_asc"], gee[f"{band}_desc"]
        )
    gee["s1_scene_count"] = np.where(
        gee["s1_orbit"].eq("asc"), gee["s1_asc_count"], gee["s1_desc_count"]
    )
    gee["s1_available"] = (
        gee["s1_scene_count"].fillna(0).gt(0)
        & gee[["s1_VV_db", "s1_VH_db"]].notna().all(axis=1)
    )
    return gee, coverage


def varying_share(frame: pd.DataFrame, column: str) -> tuple[int, int, float]:
    groups = frame.groupby(["cohort", "cluster_2km"], dropna=True)
    multi = groups.filter(lambda group: len(group) > 1)
    counts = multi.groupby(["cohort", "cluster_2km"])[column].nunique(dropna=True)
    total = int(len(counts))
    varying = int(counts.gt(1).sum())
    return total, varying, float(varying / total) if total else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("data/v2/processed/labels_v2.parquet"),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    derived = root / "derived"
    reports = root / "reports"
    figures = reports / "figures" / "malawi"
    for folder in (derived, reports, figures):
        folder.mkdir(parents=True, exist_ok=True)

    month_keys = pd.read_csv(
        derived / "malawi_field_months_2022_2023.csv",
        dtype={"obs_id": "string", "month": "string"},
    )
    if len(month_keys) != EXPECTED_ROWS or month_keys.duplicated(KEYS).any():
        raise RuntimeError("Canonical Malawi month keys are incomplete or duplicated")

    paths = locate_exports(root)
    gee = load_exports(paths)
    key_check = month_keys[KEYS].merge(
        gee[KEYS], on=KEYS, how="outer", indicator=True, validate="one_to_one"
    )
    if not key_check["_merge"].eq("both").all():
        raise RuntimeError(f"Earth Engine keys do not match canonical keys: {key_check['_merge'].value_counts().to_dict()}")

    ignore = set(KEYS + [
        "system:index", "source_export", "cohort", "lat", "lon", "primary",
        "season_yr", "start", "end", ".geo",
    ])
    value_columns = [column for column in gee.columns if column not in ignore]
    for column in value_columns:
        gee[column] = pd.to_numeric(gee[column], errors="coerce").replace(-9999, np.nan)
    gee = gee.copy()
    gee, orbit_coverage = choose_sentinel1_orbit(gee)

    gee["presto_VV_recomputed"] = (gee["s1_VV_db"] + 25.0) / 25.0
    gee["presto_VH_recomputed"] = (gee["s1_VH_db"] + 25.0) / 25.0
    # Use the values normalized on the image before Earth Engine's polygon
    # reduction. The recomputed columns are retained only as an audit because
    # approximate polygon medians need not commute perfectly in practice.
    gee["presto_VV"] = np.where(
        gee["s1_orbit"].eq("asc"), gee["VV_asc_presto"], gee["VV_desc_presto"]
    )
    gee["presto_VH"] = np.where(
        gee["s1_orbit"].eq("asc"), gee["VH_asc_presto"], gee["VH_desc_presto"]
    )
    gee["presto_temperature_2m"] = (gee["temperature_2m"] - 272.15) / 35.0
    gee["presto_total_precipitation"] = gee["total_precipitation"] / 0.03
    gee["presto_elevation"] = gee["elevation"] / 2000.0
    gee["presto_slope"] = gee["slope"] / 50.0
    gee["era5_available"] = gee[["temperature_2m", "total_precipitation"]].notna().all(axis=1)
    gee["chirps_available"] = gee["chirps_precip_mm"].notna()
    gee["srtm_available"] = gee[["elevation", "slope"]].notna().all(axis=1)

    normalization_diffs = {
        "VV": float((gee["presto_VV_recomputed"] - gee["presto_VV"]).abs().max()),
        "VH": float((gee["presto_VH_recomputed"] - gee["presto_VH"]).abs().max()),
        "temperature": float((gee["presto_temperature_2m"] - gee["temperature_2m_presto"]).abs().max()),
        "precipitation": float((gee["presto_total_precipitation"] - gee["total_precipitation_presto"]).abs().max()),
        "elevation": float((gee["presto_elevation"] - gee["elevation_presto"]).abs().max()),
        "slope": float((gee["presto_slope"] - gee["slope_presto"]).abs().max()),
    }

    alpha_columns = [f"A{index:02d}" for index in range(64)]
    missing_alpha = set(alpha_columns).difference(gee.columns)
    if missing_alpha:
        raise RuntimeError(f"Missing AlphaEarth dimensions: {sorted(missing_alpha)}")
    alpha_ranges = gee.groupby("obs_id")[alpha_columns].agg(
        lambda values: values.max() - values.min()
    )
    alpha_repeat_max_difference = float(alpha_ranges.max(axis=None))
    if alpha_repeat_max_difference > 1e-10:
        raise RuntimeError(
            "AlphaEarth annual embeddings vary materially across months for the same field: "
            f"maximum difference {alpha_repeat_max_difference}"
        )

    monthly_columns = KEYS + [
        "s1_orbit", "s1_scene_count", "s1_available", "s1_VV_db", "s1_VH_db",
        "temperature_2m", "total_precipitation", "era5_available",
        "chirps_precip_mm", "chirps_available", "elevation", "slope", "srtm_available",
        "presto_VV", "presto_VH", "presto_temperature_2m",
        "presto_total_precipitation", "presto_elevation", "presto_slope",
    ]
    monthly = month_keys.merge(
        gee[monthly_columns], on=KEYS, how="left", validate="one_to_one"
    )

    labels_columns = [
        "obs_id", "cohort", "season_year", "geometry_type", "lat", "lon",
        "field_area_ha", "cluster_2km", "admin_unit", "include_primary",
    ]
    labels = pd.read_parquet(args.labels.resolve(), columns=labels_columns)
    labels = labels[labels["cohort"].isin(["malawi_2022", "malawi_2023"])].copy()
    if len(labels) != EXPECTED_OBSERVATIONS or not labels["obs_id"].is_unique:
        raise RuntimeError("Data-v2 Malawi field metadata do not match expected observations")

    soil = pd.read_csv(
        derived / "soilgrids_malawi_features.csv", dtype={"obs_id": "string"}
    )
    # Repeated annual reductions differ by at most floating-point roundoff.
    # Collapse them with a per-field median to make the static table stable.
    alpha = gee.groupby(["obs_id", "season_year"], as_index=False)[alpha_columns].median()
    alpha["alphaearth_complete"] = alpha[alpha_columns].notna().all(axis=1)
    alpha["alphaearth_vector_norm"] = np.sqrt(alpha[alpha_columns].pow(2).sum(axis=1))
    srtm = gee[["obs_id", "elevation", "slope"]].drop_duplicates("obs_id")
    static = labels.merge(srtm, on="obs_id", validate="one_to_one").merge(
        soil, on="obs_id", validate="one_to_one"
    ).merge(alpha, on=["obs_id", "season_year"], validate="one_to_one")

    monthly_csv = derived / "malawi_model_ready_monthly_extra_inputs.csv"
    monthly_parquet = derived / "malawi_model_ready_monthly_extra_inputs.parquet"
    static_csv = derived / "malawi_model_ready_static_extra_inputs.csv"
    static_parquet = derived / "malawi_model_ready_static_extra_inputs.parquet"
    monthly.to_csv(monthly_csv, index=False)
    monthly.to_parquet(monthly_parquet, index=False)
    static.to_csv(static_csv, index=False)
    static.to_parquet(static_parquet, index=False)

    coverage = monthly.groupby(["season_year", "month"], as_index=False).agg(
        expected_rows=("obs_id", "size"),
        s1_complete_rows=("s1_available", "sum"),
        era5_complete_rows=("era5_available", "sum"),
        chirps_complete_rows=("chirps_available", "sum"),
        srtm_complete_rows=("srtm_available", "sum"),
    )
    for source in ("s1", "era5", "chirps", "srtm"):
        coverage[f"{source}_complete_pct"] = (
            100 * coverage[f"{source}_complete_rows"] / coverage["expected_rows"]
        )
    coverage.to_csv(reports / "malawi_monthly_source_coverage.csv", index=False)

    s1_observation = monthly.groupby("obs_id", as_index=False).agg(
        cohort=("cohort", "first"),
        season_year=("season_year", "first"),
        s1_orbit=("s1_orbit", "first"),
        expected_months=("month", "size"),
        s1_valid_months=("s1_available", "sum"),
    )
    s1_observation["s1_complete_season"] = s1_observation["s1_valid_months"].eq(
        s1_observation["expected_months"]
    )
    s1_observation.to_csv(reports / "malawi_s1_observation_coverage.csv", index=False)

    seasonal = monthly.groupby("obs_id", as_index=False).agg(
        s1_VV_season_mean=("s1_VV_db", "mean"),
        s1_VH_season_mean=("s1_VH_db", "mean"),
        chirps_season_total_mm=("chirps_precip_mm", "sum"),
        era5_season_total_m=("total_precipitation", "sum"),
    )
    village = static.merge(seasonal, on="obs_id", validate="one_to_one")
    variables = [
        ("Sentinel-1 VV seasonal mean", "s1_VV_season_mean", "10 m polygon median", 6),
        ("CHIRPS seasonal rainfall", "chirps_season_total_mm", "~5.5 km", 6),
        ("ERA5-Land seasonal rainfall", "era5_season_total_m", "~11 km", 8),
        ("SRTM elevation", "elevation", "30 m", 3),
        ("SoilGrids pH 0-5 cm", "soilgrids_phh2o_0_5cm_mean", "250 m", 3),
        ("SoilGrids SOC 0-5 cm", "soilgrids_soc_0_5cm_mean", "250 m", 3),
        ("AlphaEarth A00", "A00", "10 m polygon median", 8),
    ]
    variation_rows = []
    for source, column, resolution, decimals in variables:
        rounded = f"__{column}"
        village[rounded] = village[column].round(decimals)
        total, varying, share = varying_share(village, rounded)
        variation_rows.append(
            {
                "source": source,
                "resolution": resolution,
                "multi_field_2km_clusters": total,
                "clusters_with_more_than_one_value": varying,
                "share_varying_within_2km": share,
            }
        )
    variation = pd.DataFrame(variation_rows)
    variation.to_csv(reports / "malawi_within_village_variation.csv", index=False)

    alpha_norm = static["alphaearth_vector_norm"]
    quality = {
        "observations": EXPECTED_OBSERVATIONS,
        "monthly_rows": EXPECTED_ROWS,
        "export_files": [path.name for path in paths],
        "source_complete": {
            "sentinel1_rows": int(monthly["s1_available"].sum()),
            "era5_rows": int(monthly["era5_available"].sum()),
            "chirps_rows": int(monthly["chirps_available"].sum()),
            "srtm_observations": int(static[["elevation", "slope"]].notna().all(axis=1).sum()),
            "soilgrids_observations": int(static["soilgrids_complete"].sum()),
            "alphaearth_observations": int(static["alphaearth_complete"].sum()),
        },
        "sentinel1_orbits": orbit_coverage["s1_orbit"].value_counts().to_dict(),
        "sentinel1_complete_seasons": int(s1_observation["s1_complete_season"].sum()),
        "era5_temperature_kelvin_range": [
            float(monthly["temperature_2m"].min()),
            float(monthly["temperature_2m"].max()),
        ],
        "era5_precipitation_m_range": [
            float(monthly["total_precipitation"].min()),
            float(monthly["total_precipitation"].max()),
        ],
        "chirps_precipitation_mm_range": [
            float(monthly["chirps_precip_mm"].min()),
            float(monthly["chirps_precip_mm"].max()),
        ],
        "chirps_era5_precipitation_correlation": float(
            monthly[["chirps_precip_mm", "total_precipitation"]].corr().iloc[0, 1]
        ),
        "alphaearth_dimensions": len(alpha_columns),
        "alphaearth_repeated_month_max_absolute_difference": alpha_repeat_max_difference,
        "alphaearth_vector_norm_min_median_max": [
            float(alpha_norm.min()), float(alpha_norm.median()), float(alpha_norm.max())
        ],
        "presto_normalization_max_absolute_difference": normalization_diffs,
        "alphaearth_leakage_warning": "Annual embeddings for season_year include observations after the October-June harvest window; keep AlphaEarth as a separate annual baseline, not a causal monthly Presto channel.",
        "malawi_geometry_rule": "Sentinel-1, SRTM and AlphaEarth are polygon medians over walked field boundaries; ERA5 and CHIRPS remain coarse contextual weather.",
    }
    (reports / "malawi_feature_quality_summary.json").write_text(
        json.dumps(quality, indent=2), encoding="utf-8"
    )

    dictionary_rows = [
        ["s1_VV_db", "monthly", "Sentinel-1", "dB", "10 m polygon median", "Chosen orbit; dynamic Presto radar input"],
        ["s1_VH_db", "monthly", "Sentinel-1", "dB", "10 m polygon median", "Chosen orbit; dynamic Presto radar input"],
        ["temperature_2m", "monthly", "ERA5-Land", "K", "~11 km", "Contextual weather; not field resolving"],
        ["total_precipitation", "monthly", "ERA5-Land", "m/month", "~11 km", "Contextual weather; not field resolving"],
        ["chirps_precip_mm", "monthly", "CHIRPS v2", "mm/month", "~5.5 km", "Independent rainfall product"],
        ["elevation", "static", "SRTM", "m", "30 m polygon median", "Terrain channel"],
        ["slope", "static", "SRTM", "degrees", "30 m polygon median", "Terrain channel"],
        ["soilgrids_*", "static", "SoilGrids 2.0", "property-specific", "250 m centroid sample", "Modeled soil context, not field samples"],
        ["A00-A63", "annual", "AlphaEarth", "dimensionless", "10 m polygon median", "Separate annual baseline; leakage warning"],
    ]
    dictionary = pd.DataFrame(
        dictionary_rows,
        columns=["variable", "time_scale", "source", "unit", "spatial_support", "recommended_use"],
    )
    dictionary.to_csv(reports / "malawi_extra_inputs_data_dictionary.csv", index=False)

    summary = {
        "status": "complete",
        "observations": EXPECTED_OBSERVATIONS,
        "monthly_rows": EXPECTED_ROWS,
        "months_per_observation": sorted(monthly.groupby("obs_id").size().unique().tolist()),
        "cohort_counts": static.groupby("cohort").size().to_dict(),
        "outputs": {
            "monthly_csv": str(monthly_csv.relative_to(root)),
            "monthly_parquet": str(monthly_parquet.relative_to(root)),
            "static_csv": str(static_csv.relative_to(root)),
            "static_parquet": str(static_parquet.relative_to(root)),
        },
        "quality_report": str((reports / "malawi_feature_quality_summary.json").relative_to(root)),
        "village_variation_report": str((reports / "malawi_within_village_variation.csv").relative_to(root)),
    }
    (reports / "malawi_combined_inputs_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
