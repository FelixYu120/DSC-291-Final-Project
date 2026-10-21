"""Partition audited maize yield candidates into ISO3 country folders."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/audit"
OUTPUT = ROOT / "data/processed/by_country"
DATASETS = (
    "one_acre_fund_full", "one_acre_fund_curated", "zimbabwe",
    "malawi_2022", "malawi_2023", "vision_guided_yield_estimation",
)
COUNTRY_ISO3 = {
    "burundi": "BDI", "kenya": "KEN", "malawi": "MWI", "nigeria": "NGA", "rwanda": "RWA",
    "tanzania": "TZA", "uganda": "UGA", "zambia": "ZMB", "zimbabwe": "ZWE",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def organize() -> dict:
    by_country: dict[str, list[dict[str, str]]] = defaultdict(list)
    boundaries: dict[str, list[dict]] = defaultdict(list)
    for dataset in DATASETS:
        source = AUDIT / f"{dataset}_screened_candidates.csv"
        for row in read_rows(source):
            iso3 = COUNTRY_ISO3.get(row.get("country", "").strip().lower())
            if not iso3 or row.get("passes_yield_and_known_location_checks", "true").lower() != "true":
                continue
            by_country[iso3].append(row)

        if dataset.startswith("malawi_"):
            geojson_path = AUDIT / f"{dataset}_candidates_wgs84.geojson"
            if geojson_path.exists():
                collection = json.loads(geojson_path.read_text(encoding="utf-8"))
                for feature in collection.get("features", []):
                    properties = feature.get("properties", {})
                    if properties.get("passes_yield_and_known_location_checks", "false") is True or str(
                        properties.get("passes_yield_and_known_location_checks", "false")
                    ).lower() == "true":
                        boundaries["MWI"].append(feature)

    manifest = {
        "definition": "Rows passing the audit's yield and known-location screening; candidates are not imagery-validated field labels.",
        "country_directories": {},
    }
    for iso3, rows in sorted(by_country.items()):
        rows.sort(key=lambda row: (row.get("year", ""), row.get("dataset", ""), row.get("source_row", "")))
        directory = OUTPUT / iso3
        directory.mkdir(parents=True, exist_ok=True)
        write_rows(directory / "screened_maize_yield_candidates.csv", rows)
        features = boundaries.get(iso3, [])
        if features:
            (directory / "screened_field_boundaries_wgs84.geojson").write_text(
                json.dumps({"type": "FeatureCollection", "features": features}, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        years = [int(row["year"]) for row in rows if row.get("year", "").isdigit()]
        entry = {
            "country": rows[0]["country"],
            "records": len(rows),
            "records_since_2019": sum(year >= 2019 for year in years),
            "by_dataset": dict(sorted(Counter(row["dataset"] for row in rows).items())),
            "field_boundary_features": len(features),
            "candidate_csv": f"{iso3}/screened_maize_yield_candidates.csv",
        }
        if features:
            entry["boundary_geojson"] = f"{iso3}/screened_field_boundaries_wgs84.geojson"
        manifest["country_directories"][iso3] = entry

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    organize()
