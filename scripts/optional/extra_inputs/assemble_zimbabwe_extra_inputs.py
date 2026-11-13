"""Assemble and audit all Zimbabwe extra inputs.

The script is intentionally rerunnable. Before the browser export arrives it
creates a valid partial table with explicit availability flags. After the GEE
CSV is placed in ``incoming/``, the same command validates it, chooses one
Sentinel-1 orbit direction per observation, and fills the missing Presto bands.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


GEE_STEM = "zimbabwe_presto_s1_era5_srtm_2022_2023"
KEYS = ["obs_id", "season_year", "month"]


def add_gee(monthly: pd.DataFrame, paths: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    gee = pd.concat(
        [pd.read_csv(path, dtype={"obs_id": "string", "month": "string"}) for path in paths],
        ignore_index=True,
    )
    missing_keys = set(KEYS).difference(gee.columns)
    if missing_keys:
        raise ValueError(f"GEE CSV lacks key columns: {sorted(missing_keys)}")
    if gee.duplicated(KEYS).any():
        raise ValueError("GEE CSV has duplicate observation-month keys")
    if len(gee) != len(monthly):
        raise ValueError(f"GEE row count {len(gee)} != expected {len(monthly)}")

    value_columns = [c for c in gee.columns if c not in KEYS + ["latitude", "longitude", ".geo"]]
    for column in value_columns:
        gee[column] = pd.to_numeric(gee[column], errors="coerce").replace(-9999, np.nan)
    # Consolidate the many AlphaEarth columns before adding audit/normalization
    # fields; this avoids pandas DataFrame fragmentation warnings.
    gee = gee.copy()

    for direction in ("asc", "desc"):
        count = gee[f"s1_{direction}_count"].fillna(0)
        gee[f"valid_{direction}"] = (
            count.gt(0)
            & gee[f"VV_{direction}_median3"].notna()
            & gee[f"VH_{direction}_median3"].notna()
        )
    coverage = gee.groupby("obs_id")[["valid_asc", "valid_desc"]].sum()
    # Descending is the deterministic tie-breaker. The chosen direction is
    # constant across all nine months for an observation.
    coverage["s1_orbit"] = np.where(
        coverage["valid_asc"] > coverage["valid_desc"], "asc", "desc"
    )
    gee = gee.merge(coverage[["s1_orbit"]], on="obs_id", validate="many_to_one")

    for statistic in ("point", "median3"):
        for band in ("VV", "VH"):
            gee[f"s1_{band}_{statistic}_db"] = np.where(
                gee["s1_orbit"].eq("asc"),
                gee[f"{band}_asc_{statistic}"],
                gee[f"{band}_desc_{statistic}"],
            )
    gee["s1_scene_count"] = np.where(
        gee["s1_orbit"].eq("asc"), gee["s1_asc_count"], gee["s1_desc_count"]
    )
    gee["s1_available"] = (
        gee["s1_scene_count"].fillna(0).gt(0)
        & gee["s1_VV_median3_db"].notna()
        & gee["s1_VH_median3_db"].notna()
    )
    gee["presto_VV"] = (gee["s1_VV_median3_db"] + 25.0) / 25.0
    gee["presto_VH"] = (gee["s1_VH_median3_db"] + 25.0) / 25.0
    gee["presto_temperature_2m"] = (gee["temperature_2m"] - 272.15) / 35.0
    gee["presto_total_precipitation"] = gee["total_precipitation"] / 0.03
    gee["presto_elevation"] = gee["elevation"] / 2000.0
    gee["presto_slope"] = gee["slope"] / 50.0
    gee["era5_available"] = gee[["temperature_2m", "total_precipitation"]].notna().all(axis=1)
    gee["srtm_gee_available"] = gee[["elevation", "slope"]].notna().all(axis=1)

    alpha_columns = sorted(c for c in gee.columns if c.startswith("A") and c[1:].isdigit())
    keep = KEYS + [
        "s1_orbit", "s1_scene_count", "s1_available",
        "s1_VV_point_db", "s1_VH_point_db", "s1_VV_median3_db", "s1_VH_median3_db",
        "temperature_2m", "total_precipitation", "era5_available",
        "elevation", "slope", "srtm_gee_available",
        "presto_VV", "presto_VH", "presto_temperature_2m",
        "presto_total_precipitation", "presto_elevation", "presto_slope",
    ] + alpha_columns
    result = monthly.merge(gee[keep], on=KEYS, how="left", validate="one_to_one")
    alpha = gee[["obs_id", "season_year"] + alpha_columns].drop_duplicates("obs_id")
    if alpha_columns:
        alpha["alphaearth_complete"] = alpha[alpha_columns].notna().all(axis=1)
    audit = {
        # Keep committed audit reports portable and avoid exposing a contributor's
        # local filesystem path.
        "gee_csv_files": [path.name for path in paths],
        "rows": int(len(gee)),
        "s1_complete_rows": int(gee["s1_available"].sum()),
        "s1_complete_observations_all_9_months": int(
            gee.groupby("obs_id")["s1_available"].sum().eq(9).sum()
        ),
        "era5_complete_rows": int(gee["era5_available"].sum()),
        "srtm_complete_rows": int(gee["srtm_gee_available"].sum()),
        "chosen_orbits": coverage["s1_orbit"].value_counts().to_dict(),
        "alphaearth_dimensions": len(alpha_columns),
        "alphaearth_complete_observations": int(
            alpha.get("alphaearth_complete", pd.Series(dtype=bool)).sum()
        ),
    }
    return result, alpha, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    derived, reports, incoming = root / "derived", root / "reports", root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    fields = pd.read_csv(derived / "zimbabwe_fields_2022_2023.csv")
    monthly = pd.read_csv(derived / "zimbabwe_field_months_2022_2023.csv")
    chirps = pd.read_csv(derived / "chirps_monthly.csv")
    srtm = pd.read_csv(derived / "srtm_features.csv")
    soil = pd.read_csv(derived / "soilgrids_features.csv")

    monthly = monthly.merge(
        chirps[KEYS + ["chirps_precip_mm", "chirps_available"]],
        on=KEYS,
        validate="one_to_one",
    ).merge(
        srtm.drop(columns=["srtm_tile"]), on="obs_id", validate="many_to_one"
    )
    combined_gee_path = incoming / f"{GEE_STEM}.csv"
    part_paths = sorted(incoming.glob(f"{GEE_STEM}_part*.csv"))
    gee_paths = [combined_gee_path] if combined_gee_path.exists() else part_paths
    if gee_paths:
        monthly, alpha_from_gee, gee_audit = add_gee(monthly, gee_paths)
        gee_status = "integrated"
    else:
        gee_audit = {
            "expected_combined_path": str(combined_gee_path),
            "or_expected_part_pattern": f"{GEE_STEM}_part*.csv",
            "rows": 0,
        }
        gee_status = "awaiting_browser_export"

    static = fields.merge(srtm, on="obs_id", validate="one_to_one").merge(
        soil, on="obs_id", validate="one_to_one"
    )
    alpha_path = derived / "alphaearth_embeddings.csv"
    if alpha_path.exists():
        alpha = pd.read_csv(alpha_path)
        static = static.merge(alpha, on="obs_id", validate="one_to_one")
        alpha_status = "integrated"
    elif gee_paths and len(alpha_from_gee.columns) > 2:
        static = static.merge(alpha_from_gee, on=["obs_id", "season_year"], validate="one_to_one")
        alpha_status = "integrated_from_gee"
    else:
        alpha_status = "extraction_in_progress_or_not_run"

    monthly.to_csv(derived / "model_ready_monthly_extra_inputs.csv", index=False)
    static.to_csv(derived / "model_ready_static_extra_inputs.csv", index=False)

    if gee_status == "integrated":
        monthly_coverage = monthly.groupby("month", as_index=False).agg(
            expected_rows=("obs_id", "size"),
            s1_complete_rows=("s1_available", "sum"),
            era5_complete_rows=("era5_available", "sum"),
            srtm_complete_rows=("srtm_gee_available", "sum"),
        )
        for source in ("s1", "era5", "srtm"):
            monthly_coverage[f"{source}_complete_pct"] = (
                100 * monthly_coverage[f"{source}_complete_rows"]
                / monthly_coverage["expected_rows"]
            )
        monthly_coverage.to_csv(reports / "monthly_source_coverage.csv", index=False)

        s1_observation = monthly.groupby("obs_id", as_index=False).agg(
            season_year=("season_year", "first"),
            s1_orbit=("s1_orbit", "first"),
            s1_valid_months=("s1_available", "sum"),
        )
        s1_observation["s1_complete_9_months"] = s1_observation["s1_valid_months"].eq(9)
        s1_observation.to_csv(reports / "s1_observation_coverage.csv", index=False)

        alpha_columns = sorted(
            c for c in static.columns if c.startswith("A") and c[1:].isdigit()
        )
        alpha_norm = np.sqrt(static[alpha_columns].pow(2).sum(axis=1))
        quality = {
            "era5_temperature_kelvin_range": [
                float(monthly["temperature_2m"].min()),
                float(monthly["temperature_2m"].max()),
            ],
            "era5_monthly_precipitation_m_range": [
                float(monthly["total_precipitation"].min()),
                float(monthly["total_precipitation"].max()),
            ],
            "chirps_era5_precipitation_correlation": float(
                monthly[["chirps_precip_mm", "total_precipitation"]].corr().iloc[0, 1]
            ),
            "alphaearth_dimensions": len(alpha_columns),
            "alphaearth_vector_norm_min_median_max": [
                float(alpha_norm.min()), float(alpha_norm.median()), float(alpha_norm.max())
            ],
            "srtm_gee_vs_local_elevation_mean_absolute_difference_m": float(
                (monthly["elevation"] - monthly["srtm_elevation_m_point"]).abs().mean()
            ),
            "srtm_gee_vs_local_slope_mean_absolute_difference_deg": float(
                (monthly["slope"] - monthly["srtm_slope_deg_point"]).abs().mean()
            ),
            "sentinel1_complete_rows": int(monthly["s1_available"].sum()),
            "sentinel1_complete_rows_pct": float(100 * monthly["s1_available"].mean()),
            "sentinel1_observations_with_all_9_months": int(
                s1_observation["s1_complete_9_months"].sum()
            ),
        }
        (reports / "feature_quality_summary.json").write_text(
            json.dumps(quality, indent=2), encoding="utf-8"
        )
    summary = {
        "observations": int(fields["obs_id"].nunique()),
        "observation_month_rows": int(len(monthly)),
        "months_per_observation": sorted(monthly.groupby("obs_id").size().unique().tolist()),
        "srtm_local_complete_observations": int(
            srtm[["srtm_elevation_m_point", "srtm_slope_deg_point"]].notna().all(axis=1).sum()
        ),
        "chirps_complete_rows": int(monthly["chirps_available"].sum()),
        "soilgrids_complete_observations": int(soil["soilgrids_complete"].sum()),
        "alphaearth_status": alpha_status,
        "gee_status": gee_status,
        "gee_audit": gee_audit,
        "important_geometry_limit": "The source has points, not field polygons; values are point pixels or 3x3 summaries, not exact field means.",
    }
    (reports / "combined_inputs_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
