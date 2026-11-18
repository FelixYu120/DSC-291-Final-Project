"""Package raw and processed extra inputs for Zimbabwe, Kenya, and Malawi."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd


EXPECTED = {"raw_gee": 59311, "processed_monthly": 59311, "processed_static": 7032}


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def sql_paths(paths: list[Path]) -> str:
    return "[" + ",".join(f"'{sql_path(path)}'" for path in paths) + "]"


def country_from_name(name: str) -> str:
    lower = name.lower()
    if "zimbabwe" in lower:
        return "ZWE"
    if "kenya" in lower:
        return "KEN"
    if "malawi" in lower:
        return "MWI"
    return ""


def manifest_rows(paths: list[Path], project_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(set(p.resolve() for p in paths)):
        stat = path.stat()
        try:
            relative = str(path.relative_to(project_root))
        except ValueError:
            relative = str(path)
        rows.append(
            {
                "country_iso3": country_from_name(str(path)),
                "file_name": path.name,
                "relative_path": relative.replace("\\", "/"),
                "extension": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "storage_note": (
                    "loaded into raw_gee_observations"
                    if "_presto_" in path.name.lower() and path.suffix.lower() == ".csv"
                    else "original file retained on disk; catalogued here"
                ),
            }
        )
    return rows


def create_country_union(
    con: duckdb.DuckDBPyConnection,
    table: str,
    sources: list[tuple[str, Path, str]],
) -> None:
    selects = []
    for iso3, path, reader in sources:
        if reader == "csv":
            relation = (
                f"read_csv_auto('{sql_path(path)}', header=true, sample_size=-1, "
                "null_padding=true)"
            )
        else:
            relation = f"read_parquet('{sql_path(path)}')"
        selects.append(
            f"SELECT '{iso3}' AS country_iso3, '{path.name.replace("'", "''")}' "
            f"AS source_file, * FROM {relation}"
        )
    con.execute(
        f"CREATE TABLE {table} AS " + " UNION ALL BY NAME ".join(selects)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    google_earth = project_root / "Google Earth"
    km_root = google_earth / "Kenya Malawi"
    zim_root = project_root / "presto_extra_inputs_2026-11-09"
    output = (args.output or google_earth / "three_country_extra_inputs.duckdb").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    gee_files = sorted(
        path
        for path in google_earth.rglob("*.csv")
        if path.name.lower().startswith(("zimbabwe_presto_", "kenya_presto_", "malawi_presto_"))
        and "derived" not in {part.lower() for part in path.parts}
    )
    if len(gee_files) != 18:
        raise RuntimeError(f"Expected 18 original GEE CSV files, found {len(gee_files)}")

    monthly_sources = [
        ("ZWE", zim_root / "derived" / "model_ready_monthly_extra_inputs.csv", "csv"),
        ("KEN", km_root / "derived" / "kenya_model_ready_monthly_extra_inputs.parquet", "parquet"),
        ("MWI", km_root / "derived" / "malawi_model_ready_monthly_extra_inputs.parquet", "parquet"),
    ]
    static_sources = [
        ("ZWE", zim_root / "derived" / "model_ready_static_extra_inputs.csv", "csv"),
        ("KEN", km_root / "derived" / "kenya_model_ready_static_extra_inputs.parquet", "parquet"),
        ("MWI", km_root / "derived" / "malawi_model_ready_static_extra_inputs.parquet", "parquet"),
    ]
    source_specific = {
        "processed_zimbabwe_chirps_monthly": zim_root / "derived" / "chirps_monthly.csv",
        "processed_zimbabwe_soilgrids": zim_root / "derived" / "soilgrids_features.csv",
        "processed_zimbabwe_srtm": zim_root / "derived" / "srtm_features.csv",
        "processed_kenya_soilgrids": km_root / "derived" / "soilgrids_kenya_features.csv",
        "processed_malawi_soilgrids": km_root / "derived" / "soilgrids_malawi_features.csv",
    }
    required = [p for _, p, _ in monthly_sources + static_sources] + list(source_specific.values())
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))

    raw_roots = [km_root / "raw", zim_root / "raw"]
    raw_downloads = [p for root in raw_roots for p in root.rglob("*") if p.is_file()]
    manifest = pd.DataFrame(manifest_rows(gee_files + raw_downloads, project_root))

    temp_output = output.with_suffix(output.suffix + ".building")
    if temp_output.exists():
        temp_output.unlink()
    con = duckdb.connect(str(temp_output))
    try:
        gee_relation = (
            f"read_csv_auto({sql_paths(gee_files)}, header=true, union_by_name=true, "
            "filename=true, sample_size=-1, null_padding=true)"
        )
        con.execute(
            f"""
            CREATE TABLE raw_gee_observations AS
            SELECT
                CASE
                    WHEN lower(filename) LIKE '%zimbabwe_presto_%' THEN 'ZWE'
                    WHEN lower(filename) LIKE '%kenya_presto_%' THEN 'KEN'
                    WHEN lower(filename) LIKE '%malawi_presto_%' THEN 'MWI'
                END AS country_iso3,
                regexp_extract(replace(filename, '\\', '/'), '[^/]+$') AS source_file,
                * EXCLUDE (filename)
            FROM {gee_relation}
            """
        )
        create_country_union(con, "processed_monthly_inputs", monthly_sources)
        create_country_union(con, "processed_static_inputs", static_sources)

        for table, path in source_specific.items():
            con.execute(
                f"CREATE TABLE {table} AS SELECT * FROM "
                f"read_csv_auto('{sql_path(path)}', header=true, sample_size=-1, null_padding=true)"
            )

        alpha_index = zim_root / "raw" / "alphaearth" / "aef_index.parquet"
        if alpha_index.exists():
            con.execute(
                f"CREATE TABLE raw_zimbabwe_alphaearth_index AS "
                f"SELECT * FROM read_parquet('{sql_path(alpha_index)}')"
            )

        con.register("manifest_df", manifest)
        con.execute("CREATE TABLE raw_file_manifest AS SELECT * FROM manifest_df")
        con.unregister("manifest_df")

        about = pd.DataFrame(
            [
                {
                    "database": "Three-country extra inputs",
                    "countries": "Zimbabwe, Kenya, Malawi",
                    "raw_layer": "Original GEE CSV exports; no imputation, unit conversion, or reshaping",
                    "processed_layer": "Model-ready monthly/static tables and source-specific derived tables",
                    "raster_note": "Original GeoTIFF/HGT/ZIP downloads remain on disk and are listed in raw_file_manifest",
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                }
            ]
        )
        con.register("about_df", about)
        con.execute("CREATE TABLE about AS SELECT * FROM about_df")
        con.unregister("about_df")

        con.execute(
            """
            CREATE VIEW country_inventory AS
            SELECT
                country_iso3,
                count(*) AS raw_gee_rows,
                count(DISTINCT obs_id) AS observations,
                min(season_year) AS first_season,
                max(season_year) AS last_season,
                count(DISTINCT month) AS months
            FROM raw_gee_observations
            GROUP BY country_iso3
            ORDER BY country_iso3
            """
        )
        con.execute("CREATE INDEX raw_gee_obs_month ON raw_gee_observations(obs_id, season_year, month)")
        con.execute("CREATE INDEX processed_monthly_obs_month ON processed_monthly_inputs(obs_id, season_year, month)")
        con.execute("CREATE INDEX processed_static_obs ON processed_static_inputs(obs_id)")

        counts = {
            "raw_gee": con.execute("SELECT count(*) FROM raw_gee_observations").fetchone()[0],
            "processed_monthly": con.execute("SELECT count(*) FROM processed_monthly_inputs").fetchone()[0],
            "processed_static": con.execute("SELECT count(*) FROM processed_static_inputs").fetchone()[0],
        }
        if counts != EXPECTED:
            raise RuntimeError(f"Unexpected row counts: {counts}; expected {EXPECTED}")
        con.execute("CHECKPOINT")
    finally:
        con.close()

    if output.exists():
        output.unlink()
    temp_output.replace(output)
    summary = {
        "output": str(output),
        "size_bytes": output.stat().st_size,
        "counts": EXPECTED,
        "raw_gee_files": len(gee_files),
        "catalogued_raw_files": len(manifest),
    }
    summary_path = output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
