"""Sample selected SoilGrids 2.0 mean layers at the Zimbabwe point labels."""
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


DEFAULT_ROOT = Path("../presto_extra_inputs_2026-11-09")
BASE = "https://files.isric.org/soilgrids/latest/data"
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    fields_path = root / "derived" / "zimbabwe_fields_2022_2023.csv"
    output_path = root / "derived" / "soilgrids_features.csv"
    report_path = root / "reports" / "soilgrids_summary.json"
    raw_folder = root / "raw" / "soilgrids"
    raw_folder.mkdir(parents=True, exist_ok=True)

    fields = pd.read_csv(fields_path)
    result = fields[["obs_id"]].copy()
    sources: list[dict[str, object]] = []
    igh = Transformer.from_crs(
        "EPSG:4326", "+proj=igh +datum=WGS84 +units=m +no_defs", always_xy=True
    )
    xy = [igh.transform(lon, lat) for lon, lat in zip(fields.longitude, fields.latitude)]
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
                    transformer.transform(lon, lat)
                    for lon, lat in zip(fields["longitude"], fields["latitude"])
                ]
                rows_cols = [dataset.index(x, y) for x, y in coordinates]
                raw = np.asarray([value[0] for value in dataset.sample(coordinates)], dtype="float64")
                if dataset.nodata is not None:
                    raw[raw == dataset.nodata] = np.nan
                column = f"soilgrids_{prop}_{depth.replace('-', '_')}_mean"
                result[column] = raw / divisor
                result[f"{column}_cell"] = [f"{r}:{c}" for r, c in rows_cols]
                sources.append(
                    {
                        "property": prop,
                        "depth": depth,
                        "url": url,
                        "file": raster_path.name,
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

    value_columns = [column for column in result if not column.endswith("_cell") and column != "obs_id"]
    if len(result) != 2266:
        raise RuntimeError(f"Expected 2,266 output rows; received {len(result)}")
    result["soilgrids_complete"] = result[value_columns].notna().all(axis=1)
    missing = result.loc[~result["soilgrids_complete"], "obs_id"].tolist()
    result.to_csv(output_path, index=False)
    summary = {
        "observations": int(len(result)),
        "properties": list(PROPERTIES),
        "depths": list(DEPTHS),
        "feature_columns": value_columns,
        "layers": sources,
        "complete_observations": int(result["soilgrids_complete"].sum()),
        "missing_observations": missing,
        "note": "Mean modeled predictions, not field soil samples. Values converted using ISRIC divisors.",
    }
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"observations": len(result), "layers": len(sources)}, indent=2))


if __name__ == "__main__":
    main()
