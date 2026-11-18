"""Prepare Kenya and Malawi field assets for the extra-input pipeline.

The script reads the frozen ``labels_v1.parquet`` table and writes:

* one unique-field upload file per country;
* one canonical ``obs_id`` x month key table per country; and
* a machine-readable preparation summary.

Kenya is exported as a CSV of point observations. Malawi is exported as
GeoJSON so that its walked field polygons are retained for polygon reduction
in Earth Engine. Data v2 is the default because it restores Malawi 2022 to the
primary modelling cohort after the older-collection imagery recovery.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from shapely import wkt
from shapely.geometry import mapping


DEFAULT_LABELS = Path("data/v2/processed/labels_v2.parquet")
DEFAULT_OUTPUT = Path("../kenya_malawi_extra_inputs_2026-11-18")

EXPECTED_FIELDS = {
    ("kenya_oaf_2019_2020", 2019): 1768,
    ("kenya_oaf_2019_2020", 2020): 2209,
    ("malawi_2022", 2022): 529,
    ("malawi_2023", 2023): 260,
}


def month_sequence(start: object, end: object) -> list[str]:
    return [str(period) for period in pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M")]


def serialise_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def build_month_keys(fields: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in fields.itertuples(index=False):
        for month in month_sequence(row.season_start, row.season_end):
            rows.append(
                {
                    "obs_id": row.obs_id,
                    "cohort": row.cohort,
                    "season_year": int(row.season_year),
                    "month": month,
                    "lat": float(row.lat),
                    "lon": float(row.lon),
                    "include_primary": bool(row.include_primary),
                }
            )
    result = pd.DataFrame(rows)
    if result.duplicated(["obs_id", "month"]).any():
        raise RuntimeError("Duplicate obs_id-month keys were generated")
    return result.sort_values(["season_year", "obs_id", "month"]).reset_index(drop=True)


def write_geojson(fields: pd.DataFrame, destination: Path) -> None:
    property_columns = [
        "obs_id",
        "cohort",
        "season_year",
        "lat",
        "lon",
        "season_start",
        "season_end",
        "include_primary",
        "exclusion_reason",
        "geometry_type",
    ]
    features: list[dict[str, object]] = []
    for row in fields.itertuples(index=False):
        properties = {
            column: serialise_value(getattr(row, column))
            for column in property_columns
        }
        features.append(
            {
                "type": "Feature",
                "id": row.obs_id,
                "properties": properties,
                "geometry": mapping(wkt.loads(row.geometry_wkt)),
            }
        )
    collection = {
        "type": "FeatureCollection",
        "name": destination.stem,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    destination.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")


def validate(fields: pd.DataFrame) -> None:
    if not fields["obs_id"].is_unique:
        raise RuntimeError("obs_id is not unique")
    if fields[["lat", "lon", "season_start", "season_end"]].isna().any().any():
        raise RuntimeError("Required spatial or season fields contain missing values")

    counts = fields.groupby(["cohort", "season_year"]).size().to_dict()
    for (cohort, season_year), expected in EXPECTED_FIELDS.items():
        actual = int(counts.get((cohort, season_year), 0))
        if actual != expected:
            raise RuntimeError(
                f"{cohort} {season_year}: expected {expected:,} fields, received {actual:,}"
            )

    kenya_types = set(fields.loc[fields.country_iso3.eq("KEN"), "geometry_type"])
    malawi_types = set(fields.loc[fields.country_iso3.eq("MWI"), "geometry_type"])
    if kenya_types != {"Point"}:
        raise RuntimeError(f"Unexpected Kenya geometry types: {sorted(kenya_types)}")
    if not malawi_types.issubset({"Polygon", "MultiPolygon"}):
        raise RuntimeError(f"Unexpected Malawi geometry types: {sorted(malawi_types)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    labels_path = args.labels.resolve()
    output = args.output.resolve()
    upload = output / "upload"
    derived = output / "derived"
    reports = output / "reports"
    incoming_kenya = output / "incoming" / "kenya"
    incoming_malawi = output / "incoming" / "malawi"
    for folder in (upload, derived, reports, incoming_kenya, incoming_malawi):
        folder.mkdir(parents=True, exist_ok=True)

    columns = [
        "obs_id",
        "cohort",
        "country_iso3",
        "season_year",
        "season_start",
        "season_end",
        "geometry_type",
        "lat",
        "lon",
        "geometry_wkt",
        "include_primary",
        "exclusion_reason",
    ]
    fields = pd.read_parquet(labels_path, columns=columns)
    fields = fields[
        fields["cohort"].isin(
            ["kenya_oaf_2019_2020", "malawi_2022", "malawi_2023"]
        )
    ].copy()
    fields = fields.sort_values(["country_iso3", "season_year", "obs_id"]).reset_index(drop=True)
    validate(fields)

    kenya = fields[fields.country_iso3.eq("KEN")].copy()
    malawi = fields[fields.country_iso3.eq("MWI")].copy()

    kenya_upload_columns = [
        "obs_id",
        "cohort",
        "season_year",
        "lat",
        "lon",
        "season_start",
        "season_end",
        "include_primary",
        "exclusion_reason",
    ]
    kenya[kenya_upload_columns].to_csv(upload / "kenya_fields_2019_2020.csv", index=False)
    write_geojson(malawi, upload / "malawi_fields_2022_2023.geojson")

    kenya_months = build_month_keys(kenya)
    malawi_months = build_month_keys(malawi)
    kenya_months.to_csv(derived / "kenya_field_months_2019_2020.csv", index=False)
    malawi_months.to_csv(derived / "malawi_field_months_2022_2023.csv", index=False)

    summary = {
        "labels": str(labels_path),
        "output": str(output),
        "earth_engine_uploads": {
            "kenya": "upload/kenya_fields_2019_2020.csv",
            "malawi": "upload/malawi_fields_2022_2023.geojson",
        },
        "field_counts": {
            str(name): int(value)
            for name, value in fields.groupby("cohort", sort=True).size().items()
        },
        "primary_field_counts": {
            str(name): int(value)
            for name, value in fields.groupby("cohort", sort=True)["include_primary"].sum().items()
        },
        "field_month_rows": {
            "kenya": int(len(kenya_months)),
            "malawi": int(len(malawi_months)),
        },
        "expected_field_month_rows": {"kenya": 31816, "malawi": 7101},
        "geometry_counts": {
            f"{country}_{geometry}": int(value)
            for (country, geometry), value in fields.groupby(
                ["country_iso3", "geometry_type"], sort=True
            ).size().items()
        },
        "notes": [
            "Kenya contains only include_primary pure-stand observations.",
            "Data v2 marks Malawi 2022 as primary after recovery from the older Sentinel-2 collection.",
            "Malawi polygons are preserved; do not replace them with centroid-only point geometry in Earth Engine.",
        ],
    }
    if len(kenya_months) != 31816 or len(malawi_months) != 7101:
        raise RuntimeError(f"Unexpected month-row counts: {summary['field_month_rows']}")
    (reports / "asset_preparation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
