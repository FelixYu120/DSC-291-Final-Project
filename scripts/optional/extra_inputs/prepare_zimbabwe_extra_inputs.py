"""Prepare Zimbabwe field/month keys and download/sample public SRTM.

This script never modifies the team DuckDB.  It reads the frozen labels table,
writes the 2022--2023 Zimbabwe point list, builds one row per observation-month,
and samples the public SRTMGL1 30 m tiles for elevation and derived slope.

The output directory is intentionally outside the repository by default because
the raw HGT tiles are large and should not be committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.request
import zipfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import rasterio


DEFAULT_DB = Path("../cropyield.duckdb")
DEFAULT_OUTPUT = Path("../presto_extra_inputs_2026-11-09")
SRTM_BASE = "https://step.esa.int/auxdata/dem/SRTMGL1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def month_sequence(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    return [str(x) for x in pd.period_range(start, end, freq="M")]


def tile_name(latitude: float, longitude: float) -> str:
    south = math.floor(latitude)
    west = math.floor(longitude)
    ns = "N" if south >= 0 else "S"
    ew = "E" if west >= 0 else "W"
    return f"{ns}{abs(south):02d}{ew}{abs(west):03d}"


def download(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "DSC-291-student-project/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as handle:
        while block := response.read(1024 * 1024):
            handle.write(block)
    partial.replace(destination)


def horn_slope(elevation: np.ndarray, latitude: float) -> np.ndarray:
    """Horn slope in degrees for the interior pixels of an elevation window."""
    z = elevation.astype("float64")
    dx = 111_320.0 * math.cos(math.radians(latitude)) / 3600.0
    dy = 110_574.0 / 3600.0
    dzdx = (
        z[:-2, 2:] + 2 * z[1:-1, 2:] + z[2:, 2:]
        - z[:-2, :-2] - 2 * z[1:-1, :-2] - z[2:, :-2]
    ) / (8 * dx)
    dzdy = (
        z[2:, :-2] + 2 * z[2:, 1:-1] + z[2:, 2:]
        - z[:-2, :-2] - 2 * z[:-2, 1:-1] - z[:-2, 2:]
    ) / (8 * dy)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def safe_window(dataset: rasterio.io.DatasetReader, row: int, col: int, radius: int) -> np.ndarray:
    row = min(max(row, radius), dataset.height - radius - 1)
    col = min(max(col, radius), dataset.width - radius - 1)
    return dataset.read(1, window=((row - radius, row + radius + 1), (col - radius, col + radius + 1)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = args.output.resolve()
    raw_srtm = output / "raw" / "srtm"
    derived = output / "derived"
    reports = output / "reports"
    for folder in (raw_srtm, derived, reports):
        folder.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(args.database), read_only=True)
    fields = connection.execute(
        """
        SELECT obs_id, cohort, dataset, source_id, year AS season_year,
               latitude, longitude, geometry_type, season_start, season_end,
               label_date, include_primary, exclusion_reason
        FROM labels
        WHERE country = 'zimbabwe' AND year IN (2022, 2023)
        ORDER BY obs_id
        """
    ).fetchdf()
    connection.close()

    if len(fields) != 2266 or not fields["obs_id"].is_unique:
        raise RuntimeError(f"Expected 2,266 unique Zimbabwe observations; received {len(fields):,}")
    if not fields["geometry_type"].str.lower().eq("point").all():
        raise RuntimeError("This extraction rule is only registered for point observations")
    fields.to_csv(derived / "zimbabwe_fields_2022_2023.csv", index=False)

    month_rows: list[dict[str, object]] = []
    for row in fields.itertuples(index=False):
        for month in month_sequence(pd.Timestamp(row.season_start), pd.Timestamp(row.season_end)):
            month_rows.append(
                {
                    "obs_id": row.obs_id,
                    "season_year": row.season_year,
                    "month": month,
                    "latitude": row.latitude,
                    "longitude": row.longitude,
                }
            )
    field_months = pd.DataFrame(month_rows)
    if field_months.duplicated(["obs_id", "month"]).any():
        raise RuntimeError("Duplicate obs_id-month keys")
    field_months.to_csv(derived / "zimbabwe_field_months_2022_2023.csv", index=False)

    fields["srtm_tile"] = [tile_name(a, b) for a, b in zip(fields.latitude, fields.longitude)]
    manifest: list[dict[str, object]] = []
    hgt_paths: dict[str, Path] = {}
    for tile in sorted(fields["srtm_tile"].unique()):
        archive = raw_srtm / f"{tile}.SRTMGL1.hgt.zip"
        url = f"{SRTM_BASE}/{archive.name}"
        download(url, archive)
        with zipfile.ZipFile(archive) as bundle:
            members = [name for name in bundle.namelist() if name.lower().endswith(".hgt")]
            if len(members) != 1:
                raise RuntimeError(f"{archive.name}: expected one HGT member, found {members}")
            hgt = raw_srtm / Path(members[0]).name
            if not hgt.exists():
                bundle.extract(members[0], raw_srtm)
            hgt_paths[tile] = hgt
        manifest.append(
            {
                "tile": tile,
                "url": url,
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": sha256(archive),
                "hgt_bytes": hgt_paths[tile].stat().st_size,
            }
        )

    srtm_rows: list[dict[str, object]] = []
    for tile, group in fields.groupby("srtm_tile", sort=True):
        with rasterio.open(hgt_paths[tile]) as dataset:
            for row in group.itertuples(index=False):
                pixel_row, pixel_col = dataset.index(row.longitude, row.latitude)
                window5 = safe_window(dataset, pixel_row, pixel_col, radius=2).astype("float64")
                nodata = dataset.nodata
                if nodata is not None:
                    window5[window5 == nodata] = np.nan
                elevation3 = window5[1:4, 1:4]
                slopes3 = horn_slope(window5, row.latitude)
                srtm_rows.append(
                    {
                        "obs_id": row.obs_id,
                        "srtm_tile": tile,
                        "srtm_elevation_m_point": float(elevation3[1, 1]),
                        "srtm_elevation_m_3x3_median": float(np.nanmedian(elevation3)),
                        "srtm_slope_deg_point": float(slopes3[1, 1]),
                        "srtm_slope_deg_3x3_median": float(np.nanmedian(slopes3)),
                        "srtm_source_resolution_m": 30,
                    }
                )
    srtm = pd.DataFrame(srtm_rows).sort_values("obs_id")
    if len(srtm) != len(fields) or srtm.iloc[:, 2:6].isna().any().any():
        raise RuntimeError("SRTM extraction is incomplete")
    srtm.to_csv(derived / "srtm_features.csv", index=False)
    pd.DataFrame(manifest).to_csv(reports / "srtm_download_manifest.csv", index=False)

    summary = {
        "database": str(args.database.resolve()),
        "observations": int(len(fields)),
        "primary_observations": int(fields["include_primary"].sum()),
        "season_counts": {str(k): int(v) for k, v in fields.groupby("season_year").size().items()},
        "obs_month_rows": int(len(field_months)),
        "srtm_tiles": int(fields["srtm_tile"].nunique()),
        "srtm_complete": int(len(srtm)),
        "geometry_types": fields["geometry_type"].value_counts().to_dict(),
    }
    (reports / "preparation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
