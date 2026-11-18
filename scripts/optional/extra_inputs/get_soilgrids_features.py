"""Download and sample selected SoilGrids 2.0 layers for a field table.

The input can be either a unique-field CSV or a field-month CSV. Duplicate
``obs_id`` rows are collapsed after checking that their coordinates agree.
SoilGrids is 250 m, so Malawi polygon observations use their representative
centroid; this does not discard meaningful within-field detail at that source
resolution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from pyproj import Transformer


WCS = "https://maps.isric.org/mapserv"
DEPTHS = ("0-5cm", "5-15cm")
PROPERTIES = {
    "bdod": (100.0, "kg/dm3"),
    "cec": (10.0, "cmol(c)/kg"),
    "clay": (10.0, "percent"),
    "sand": (10.0, "percent"),
    "nitrogen": (100.0, "g/kg"),
    "phh2o": (10.0, "pH"),
    "soc": (10.0, "g/kg"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_wcs(prop: str, depth: str, bbox: tuple[float, float, float, float], output: Path) -> str:
    params = {
        "map": f"/map/{prop}.map",
        "SERVICE": "WCS",
        "VERSION": "1.0.0",
        "REQUEST": "GetCoverage",
        "COVERAGE": f"{prop}_{depth}_mean",
        "CRS": "urn:ogc:def:crs:EPSG::152160",
        "BBOX": ",".join(str(value) for value in bbox),
        "RESX": "250",
        "RESY": "250",
        "FORMAT": "GEOTIFF_INT16",
    }
    response = requests.get(WCS, params=params, timeout=300)
    response.raise_for_status()
    if "tiff" not in response.headers.get("content-type", "").lower():
        raise RuntimeError(f"Unexpected WCS response: {response.headers.get('content-type')}")
    partial = output.with_suffix(output.suffix + ".part")
    partial.write_bytes(response.content)
    partial.replace(output)
    return response.url


def load_fields(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"obs_id": "string"})
    rename = {}
    if "latitude" in frame and "lat" not in frame:
        rename["latitude"] = "lat"
    if "longitude" in frame and "lon" not in frame:
        rename["longitude"] = "lon"
    frame = frame.rename(columns=rename)
    required = {"obs_id", "lat", "lon"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Field table lacks columns: {sorted(missing)}")
    coordinate_counts = frame.groupby("obs_id")[["lat", "lon"]].nunique(dropna=False)
    if coordinate_counts.gt(1).any(axis=None):
        raise ValueError("At least one obs_id has inconsistent coordinates")
    fields = frame[["obs_id", "lat", "lon"]].drop_duplicates("obs_id").sort_values("obs_id")
    if fields[["lat", "lon"]].isna().any().any():
        raise ValueError("Missing coordinates")
    return fields.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fields", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--tag", required=True, help="Short output name such as kenya or malawi")
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args()

    root = args.output_root.resolve()
    raw_folder = root / "raw" / "soilgrids" / args.tag
    derived = root / "derived"
    reports = root / "reports"
    for folder in (raw_folder, derived, reports):
        folder.mkdir(parents=True, exist_ok=True)

    fields = load_fields(args.fields)
    if args.expected_count is not None and len(fields) != args.expected_count:
        raise RuntimeError(
            f"Expected {args.expected_count:,} unique fields; received {len(fields):,}"
        )

    result = fields[["obs_id"]].copy()
    sources: list[dict[str, object]] = []
    igh = Transformer.from_crs(
        "EPSG:4326", "+proj=igh +datum=WGS84 +units=m +no_defs", always_xy=True
    )
    xy = [igh.transform(lon, lat) for lon, lat in zip(fields.lon, fields.lat)]
    margin = 500.0
    bbox = (
        min(x for x, _ in xy) - margin,
        min(y for _, y in xy) - margin,
        max(x for x, _ in xy) + margin,
        max(y for _, y in xy) + margin,
    )

    for prop, (divisor, unit) in PROPERTIES.items():
        for depth in DEPTHS:
            raster_path = raw_folder / f"{prop}_{depth}_mean.tif"
            if not raster_path.exists():
                url = download_wcs(prop, depth, bbox, raster_path)
            else:
                url = f"{WCS} (cached WCS coverage {prop}_{depth}_mean)"
            with rasterio.open(raster_path) as dataset:
                transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                coordinates = [
                    transformer.transform(lon, lat) for lon, lat in zip(fields.lon, fields.lat)
                ]
                rows_cols = [dataset.index(x, y) for x, y in coordinates]
                raw = np.asarray(
                    [value[0] for value in dataset.sample(coordinates)], dtype="float64"
                )
                if dataset.nodata is not None:
                    raw[raw == dataset.nodata] = np.nan
                column = f"soilgrids_{prop}_{depth.replace('-', '_')}_mean"
                result[column] = raw / divisor
                result[f"{column}_cell"] = [f"{row}:{column_}" for row, column_ in rows_cols]
                sources.append(
                    {
                        "property": prop,
                        "depth": depth,
                        "url": url,
                        "file": str(raster_path.relative_to(root)),
                        "bytes": raster_path.stat().st_size,
                        "sha256": sha256(raster_path),
                        "mapped_divisor": divisor,
                        "output_unit": unit,
                        "crs": str(dataset.crs),
                        "pixel_width_m": abs(dataset.transform.a),
                        "pixel_height_m": abs(dataset.transform.e),
                        "complete": int(np.isfinite(raw).sum()),
                        "unique_cells": int(len(set(rows_cols))),
                    }
                )

    value_columns = [
        column for column in result if column != "obs_id" and not column.endswith("_cell")
    ]
    result["soilgrids_complete"] = result[value_columns].notna().all(axis=1)
    output_path = derived / f"soilgrids_{args.tag}_features.csv"
    result.to_csv(output_path, index=False)
    summary = {
        "tag": args.tag,
        "fields_source": str(args.fields.resolve()),
        "observations": int(len(result)),
        "properties": list(PROPERTIES),
        "depths": list(DEPTHS),
        "feature_columns": value_columns,
        "layers": sources,
        "complete_observations": int(result["soilgrids_complete"].sum()),
        "missing_observations": result.loc[
            ~result["soilgrids_complete"], "obs_id"
        ].tolist(),
        "note": "Mean modeled predictions, not field soil samples. Polygon cohorts use the representative centroid because the source pixels are 250 m.",
    }
    (reports / f"soilgrids_{args.tag}_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "tag": args.tag,
                "observations": len(result),
                "layers": len(sources),
                "complete": int(result["soilgrids_complete"].sum()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
