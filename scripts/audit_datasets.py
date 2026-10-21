"""Screen maize yield labels and locations; preserve all original downloads.

Outputs are screening candidates, not satellite-validated field observations.
See data/audit/report.html for definitions, caveats and source-specific issues.
The harmonized screened files are also partitioned by country under
data/processed/by_country/.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date, datetime
import html
import io
import json
import math
from pathlib import Path
import statistics
import zipfile

import openpyxl
from pyproj import CRS, Transformer
import shapefile
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/audit"
ACRE_HA = 0.40468564224

# Deliberately generous envelopes, not authoritative national borders. These
# detect gross location/country mismatches, not small errors or border crossings.
# Bounds are longitude_min, latitude_min, longitude_max, latitude_max (degrees).
COUNTRY_ENVELOPES = {
    "kenya": (33.8, -4.9, 42.1, 5.2),
    "tanzania": (29.2, -11.8, 40.7, -0.8),
    "uganda": (29.4, -1.6, 35.1, 4.4),
    "rwanda": (28.8, -2.9, 31.0, -1.0),
    "burundi": (28.9, -4.6, 30.9, -2.2),
    "zambia": (21.8, -18.2, 33.8, -8.1),
    "malawi": (32.5, -17.2, 36.0, -9.2),
    "zimbabwe": (25.1, -22.5, 33.1, -15.5),
    "nigeria": (2.5, 4.0, 14.8, 14.0),
}

NOTES = {
    "one_acre_fund_full": [
        "The audit reads only field_latitude / field_longitude; it never fills missing coordinates from site columns. However, the Variables sheet explicitly says the Uganda 2020 LR values use site coordinates. These 246 records are flagged and excluded by the additional screening step.",
        "The workbook warns that some field coordinates were collected at homesteads or near the field. Passing checks does not establish that a point is inside the cultivated field.",
        "Yield uses yield_kg_ph (kg/ha). A missing per-hectare value can be filled from a nonnegative yield_kg_pa / 0.40468564224 (kg/acre to kg/ha), and is flagged. Negative per-hectare values are not overwritten.",
        "The year column is retained as the observation year. Crop cuts, generally two 6 x 6 m boxes, underpin the yield measurements. Some management and area measurements are self-reported.",
        "Planting/harvest dates are retained when present. Records may contain intercropping.",
    ],
    "one_acre_fund_curated": [
        "This is a separate curated release, not independent of the full OAF data. Do not add its count to the full-release count.",
        "Provider documentation states 70% had recorded field geolocation; 21% use a nearby town and 9% a district location. The CSV has no explicit location-source flag, so these cannot be reliably separated here.",
        "All rows are maize in pure stands. Yield is yield_kg_ha. Row numbers are audit identifiers, not original field IDs.",
    ],
    "zimbabwe": [
        "Filter Crop_Type == Maize/Corn. Geography is CRS84: longitude, latitude.",
        "The source column is literally named Yield(Mt/H. Its catalogue incorrectly says Megatonnes. Metric tonnes/ha is the provisional interpretation, consistent with dry kg / 40 square metres * 10 for most rows. Do not pool with other sources until the units/protocol are confirmed.",
        "For the stated 8 x 5 m crop cut, expected tonnes/ha = Dry_weight * 0.25. Deviations are flagged; source values are never corrected.",
        "The 2023 release contains harvest dates in both 2022 and 2023. Zero yields are retained and separately reported.",
    ],
    "malawi_2022": [
        "The maize identity is established by the campaign metadata; this public shapefile has no per-row crop column.",
        "The actual .prj is EPSG:20936, not EPSG:4326 as stated in the generic metadata CSV. The derived locations/GeoJSON are transformed using the actual .prj to EPSG:4326. The selected Arc 1950 to WGS84 datum operation reports 27 m accuracy; this is operation accuracy, not measured GPS error. Verify boundary alignment before extracting 10 m satellite pixels.",
        "AVG_YLD is used as the field-average crop-cut yield, interpreted in tonnes/ha based on the campaign dictionary/methodology. The public subset does not expose the individual cuts for recalculation.",
        "The public file has 529 rows, whereas the project narrative reports 523 sampled fields. No extra rows are arbitrarily removed to match the narrative.",
        "The downloaded metadata explicitly states Creative Commons By Attribution (CC BY), despite the catalogue page lacking a licence.",
    ],
    "malawi_2023": [
        "All public rows explicitly say Maize. The actual .prj is EPSG:4326.",
        "cc_ey_t is the primary yield (10 x 10 m crop cut, tonnes/ha). subc_ey_t is a nested 5 x 5 m cut, not a second independent field. ff_ey_t has only one nonmissing full-field value.",
        "The public file has 267 rows, whereas the methodology reports 261 sampled fields. The public subset lacks a training-survey flag to explain this difference, so no six rows are arbitrarily removed.",
        "The downloaded metadata explicitly states Creative Commons By Attribution (CC BY).",
    ],
}


def num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def serial(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return "" if value is None else str(value)


def base(dataset, source_row, source_id, country, year, season, yield_value,
         yield_field, units, lon=None, lat=None, geometry=None):
    y = num(yield_value)
    lon, lat = num(lon), num(lat)
    flags = []
    valid_geometry = False
    reason = ""
    geom_type = "Point" if geometry is None else geometry.geom_type
    if geometry is not None:
        valid_geometry = not geometry.is_empty and geometry.is_valid
        if not valid_geometry:
            reason = explain_validity(geometry)
        if not geometry.is_empty:
            p = geometry.representative_point()
            lon, lat = p.x, p.y
            bounds = geometry.bounds
            valid_geometry = valid_geometry and all(math.isfinite(x) for x in bounds)
            valid_geometry = valid_geometry and -180 <= bounds[0] <= bounds[2] <= 180 and -90 <= bounds[1] <= bounds[3] <= 90
    coord_ok = lon is not None and lat is not None and -180 <= lon <= 180 and -90 <= lat <= 90 and (lon, lat) != (0, 0)
    if geometry is None:
        valid_geometry = coord_ok
    location_ok = coord_ok and valid_geometry
    country = serial(country).strip().lower()
    env = COUNTRY_ENVELOPES.get(country)
    in_country_envelope = bool(coord_ok and env and env[0] <= lon <= env[2] and env[1] <= lat <= env[3])
    if not coord_ok:
        flags.append("missing_or_invalid_coordinates")
    if geometry is not None and not valid_geometry:
        flags.append("invalid_polygon_geometry")
    if coord_ok and not in_country_envelope:
        flags.append("outside_country_screening_envelope" if env else "country_envelope_unavailable")
    if y is None:
        flags.append("missing_or_nonnumeric_yield")
    elif y < 0:
        flags.append("negative_yield")
    elif y == 0:
        flags.append("zero_yield_review")
    ykg = y * (1000 if units == "t/ha" else 1) if y is not None else None
    if ykg is not None and ykg > 30000:
        flags.append("yield_above_30_t_ha_review")
    yr = num(year)
    return {
        "dataset": dataset, "source_row": source_row, "source_id": serial(source_id),
        "country": country, "year": int(yr) if yr is not None else "", "season": serial(season),
        "crop": "maize", "yield_field": yield_field, "source_yield": y,
        "source_yield_units": units, "yield_kg_ha": ykg,
        "longitude": lon, "latitude": lat, "geometry_type": geom_type,
        "valid_nonnegative_yield": y is not None and y >= 0,
        "valid_coordinates_and_geometry": location_ok,
        "within_country_screening_envelope": in_country_envelope,
        "planting_date": "", "harvest_date": "", "intercropping": "",
        "geometry_validation_detail": reason, "quality_flags": flags,
        "exact_duplicate_after_first": False,
        "_geometry": geometry, "_signature": None,
    }


def oaf_full():
    path = RAW / "one_acre_fund_full/one_acre_fund_mel_data_all_countries.xlsx"
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = book["Data"].iter_rows(values_only=True)
    headers = list(next(rows))
    result = []
    all_count = 0
    crop_counts = Counter()
    for row_num, raw in enumerate(rows, 2):
        if not any(x is not None for x in raw):
            continue
        all_count += 1
        d = dict(zip(headers, raw))
        crop = serial(d.get("crop")).strip().lower()
        crop_counts[crop] += 1
        if crop not in ("maize", "corn"):
            continue
        y, ya = num(d.get("yield_kg_ph")), num(d.get("yield_kg_pa"))
        converted = y is None and ya is not None and ya >= 0
        if converted:
            y = ya / ACRE_HA
        r = base("one_acre_fund_full", row_num, d.get("unique_id"), d.get("country"),
                 d.get("year"), d.get("season"), y,
                 "yield_kg_pa_converted" if converted else "yield_kg_ph", "kg/ha",
                 d.get("field_longitude"), d.get("field_latitude"))
        if converted:
            r["quality_flags"].append("yield_converted_from_kg_per_acre")
        if r["country"] == "uganda" and r["year"] == 2020:
            r["quality_flags"].append("documented_site_coordinates_not_field_coordinates")
        if y is not None and ya is not None and ya >= 0 and abs(y - ya / ACRE_HA) > max(1, abs(y) * 0.01):
            r["quality_flags"].append("per_acre_vs_per_hectare_yield_disagree_over_1_percent")
        for out, col in [("planting_date", "plant_date"), ("harvest_date", "harvest_date"), ("intercropping", "intercrop")]:
            r[out] = serial(d.get(col))
        r["_signature"] = tuple(serial(x) for x in raw)
        result.append(r)
    book.close()
    return result, {"all_source_rows": all_count, "all_crop_counts": dict(crop_counts)}


def oaf_curated():
    path = RAW / "one_acre_fund_curated/One_Acre_Fund_MEL_maize_survey_data_2016-2022.csv"
    result = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row_num, d in enumerate(csv.DictReader(file), 2):
            r = base("one_acre_fund_curated", row_num, f"row_{row_num}", d["country"],
                     d["year"], d["season"], d["yield_kg_ha"], "yield_kg_ha", "kg/ha", d["lon"], d["lat"])
            r.update(planting_date=d["plant_date"], harvest_date=d["harvest_date"], intercropping="no")
            r["quality_flags"].append("field_town_or_district_coordinate_provenance_unresolved")
            r["_signature"] = tuple(d.items())
            result.append(r)
    return result, {"all_source_rows": len(result)}


def zimbabwe():
    path = RAW / "zimbabwe/Lacuna_Yield_data_geojson-2023.geojson"
    data = json.loads(path.read_text())
    result = []
    crops = Counter()
    for row_num, f in enumerate(data["features"], 1):
        d = f["properties"]
        crops[d["Crop_Type"]] += 1
        if d["Crop_Type"] != "Maize/Corn":
            continue
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        harvest = serial(d.get("Harvesting"))
        r = base("zimbabwe", row_num, d.get("Case_ID"), d.get("Adm0"), harvest[:4], "",
                 d.get("Yield(Mt/H"), "Yield(Mt/H", "t/ha", coords[0], coords[1])
        r.update(planting_date=serial(d.get("Planting_D")), harvest_date=harvest,
                 intercropping=serial(d.get("Intercropp")))
        r["quality_flags"].append("yield_unit_interpretation_provisional")
        dry, wet, y = num(d.get("Dry_weight")), num(d.get("Wet_Weight")), num(d.get("Yield(Mt/H"))
        if dry is not None and y is not None and not math.isclose(y, dry * 0.25, rel_tol=0.001, abs_tol=0.001):
            r["quality_flags"].append("yield_disagrees_with_documented_40m2_crop_cut")
        if wet is not None and dry is not None and dry > wet:
            r["quality_flags"].append("dry_weight_exceeds_wet_weight")
        r["dry_weight_kg"] = dry
        r["wet_weight_kg"] = wet
        r["expected_t_ha_from_40m2_cut"] = dry * 0.25 if dry is not None else None
        r["crop_condition"] = serial(d.get("Crop_Condi"))
        r["_signature"] = json.dumps(f, sort_keys=True)
        result.append(r)
    return result, {"all_source_rows": len(data["features"]), "all_crop_counts": dict(crops), "source_crs": "OGC:CRS84"}


def malawi(year):
    filename = "mwi_mwi_lc_fo_202205_averageyield_v1.zip" if year == 2022 else "mwi_kas_lc_fo_202305_cc_yield.zip"
    result = []
    operations = Counter()
    with zipfile.ZipFile(RAW / "malawi" / filename) as z:
        stem = next(n[:-4] for n in z.namelist() if n.endswith(".shp"))
        crs = CRS.from_wkt(z.read(stem + ".prj").decode())
        trans = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        reader = shapefile.Reader(shp=io.BytesIO(z.read(stem + ".shp")),
                                 shx=io.BytesIO(z.read(stem + ".shx")),
                                 dbf=io.BytesIO(z.read(stem + ".dbf")))
        for row_num, feature in enumerate(reader.iterShapeRecords(), 1):
            d = feature.record.as_dict()
            if year == 2023 and serial(d.get("CT_NAME")).lower() != "maize":
                continue
            g = transform(trans.transform, shape(feature.shape.__geo_interface__))
            try:
                operation = trans.get_last_used_operation()
                operations[(operation.description, operation.accuracy)] += 1
            except Exception:
                operations[(trans.description, trans.accuracy)] += 1
            field = "AVG_YLD" if year == 2022 else "cc_ey_t"
            r = base(f"malawi_{year}", row_num, d["globalid"], "Malawi", year, "",
                     d[field], field, "t/ha", geometry=g)
            r["observation_time"] = serial(d["start_time"])
            r["field_area_ha"] = d["area_ha"] if year == 2022 else d["fld_area"]
            if year == 2023:
                r["nested_subcut_yield_t_ha"] = d["subc_ey_t"]
                r["full_field_yield_t_ha"] = d["ff_ey_t"]
            r["_signature"] = (json.dumps(d, sort_keys=True), g.wkb_hex)
            result.append(r)
        source_rows = len(reader)
    return result, {"all_source_rows": source_rows, "source_crs": crs.to_string(),
                    "derived_crs": "EPSG:4326", "coordinate_operations_used": [
                        {"description": description, "reported_accuracy_m": accuracy,
                         "feature_count": count}
                        for (description, accuracy), count in operations.items()]}


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row if not k.startswith("_")))
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ";".join(v) if isinstance(v, list) else v for k, v in row.items() if not k.startswith("_")})


def finish(name, rows, details):
    seen = set()
    id_counts = Counter(r["source_id"] for r in rows if r["source_id"])
    coordinate_counts = Counter((r["longitude"], r["latitude"]) for r in rows if r["valid_coordinates_and_geometry"])
    disqualifying_review_flags = {
        "yield_above_30_t_ha_review", "per_acre_vs_per_hectare_yield_disagree_over_1_percent",
        "yield_disagrees_with_documented_40m2_crop_cut", "dry_weight_exceeds_wet_weight",
    }
    for r in rows:
        signature = r.pop("_signature")
        r["exact_duplicate_after_first"] = signature in seen
        seen.add(signature)
        if r["exact_duplicate_after_first"]:
            r["quality_flags"].append("exact_duplicate_source_row_after_first")
        if id_counts[r["source_id"]] > 1:
            r["quality_flags"].append("source_id_repeated")
        if r["valid_coordinates_and_geometry"] and coordinate_counts[(r["longitude"], r["latitude"])] > 1:
            r["quality_flags"].append("coordinates_reused_across_records")
        r["passes_basic_checks"] = (r["valid_nonnegative_yield"] and r["valid_coordinates_and_geometry"]
                                    and r["within_country_screening_envelope"] and not r["exact_duplicate_after_first"])
        r["passes_basic_checks_positive_yield"] = r["passes_basic_checks"] and r["yield_kg_ha"] > 0
        r["passes_additional_yield_consistency_checks"] = r["passes_basic_checks"] and not disqualifying_review_flags.intersection(r["quality_flags"])
        r["passes_yield_and_known_location_checks"] = (r["passes_additional_yield_consistency_checks"]
            and "documented_site_coordinates_not_field_coordinates" not in r["quality_flags"])
    good = [r for r in rows if r["passes_basic_checks"]]
    screened = [r for r in rows if r["passes_yield_and_known_location_checks"]]
    summary = {
        "dataset": name, **details, "maize_records": len(rows),
        "nonnegative_numeric_yield": sum(r["valid_nonnegative_yield"] for r in rows),
        "valid_coordinates_and_geometry": sum(r["valid_coordinates_and_geometry"] for r in rows),
        "within_country_envelope": sum(r["within_country_screening_envelope"] for r in rows),
        "passes_basic_checks": len(good),
        "passes_basic_checks_since_2019": sum(r["year"] != "" and r["year"] >= 2019 for r in good),
        "passes_basic_checks_positive_yield": sum(r["passes_basic_checks_positive_yield"] for r in rows),
        "zero_yield_in_basic_candidates": sum(r["yield_kg_ha"] == 0 for r in good),
        "passes_additional_yield_consistency_checks": sum(r["passes_additional_yield_consistency_checks"] for r in rows),
        "screened_candidates": len(screened),
        "screened_candidates_since_2019": sum(r["year"] != "" and r["year"] >= 2019 for r in screened),
        "zero_yield_in_screened_candidates": sum(r["yield_kg_ha"] == 0 for r in screened),
        "distinct_locations_in_basic_candidates": len({(r["longitude"], r["latitude"]) for r in good}),
        "exact_duplicate_rows_after_first": sum(r["exact_duplicate_after_first"] for r in rows),
        "repeated_source_ids": sum(n > 1 for n in id_counts.values()),
        "flag_counts": dict(Counter(f for r in rows for f in r["quality_flags"])),
        "by_year": dict(sorted(Counter(str(r["year"]) for r in good).items())),
        "by_country": dict(sorted(Counter(r["country"] for r in good).items())),
        "candidate_yield_kg_ha_min_median_max": [min(r["yield_kg_ha"] for r in good), statistics.median(r["yield_kg_ha"] for r in good), max(r["yield_kg_ha"] for r in good)] if good else [],
        "notes": NOTES[name],
    }
    write_csv(OUT / f"{name}_maize_audit.csv", rows)
    write_csv(OUT / f"{name}_screened_candidates.csv", screened)
    # Full field boundaries are kept for Malawi. Point files remain in originals
    # and in the audit CSVs; no country-wide satellite data are downloaded.
    if name.startswith("malawi"):
        features = []
        for r in good:
            props = {k: v for k, v in r.items() if not k.startswith("_")}
            features.append({"type": "Feature", "properties": props, "geometry": mapping(r["_geometry"])})
        (OUT / f"{name}_candidates_wgs84.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, allow_nan=False))
    return summary


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summaries = []
    all_rows = {}
    for name, loader in [("one_acre_fund_full", oaf_full), ("one_acre_fund_curated", oaf_curated),
                         ("zimbabwe", zimbabwe), ("malawi_2022", lambda: malawi(2022)), ("malawi_2023", lambda: malawi(2023))]:
        print(f"Auditing {name}", flush=True)
        rows, details = loader()
        summary = finish(name, rows, details)
        summaries.append(summary)
        all_rows[name] = rows
        print(json.dumps({k: summary[k] for k in ["dataset", "maize_records", "passes_basic_checks", "passes_basic_checks_since_2019", "flag_counts"]}), flush=True)
    from organize_country_data import organize
    organize()
    def fingerprint(r):
        if not r["passes_basic_checks"]:
            return None
        return (r["country"], r["year"], round(r["latitude"], 6), round(r["longitude"], 6), round(r["yield_kg_ha"], 3))
    full_keys = {fingerprint(r) for r in all_rows["one_acre_fund_full"]} - {None}
    overlap = sum(fingerprint(r) in full_keys for r in all_rows["one_acre_fund_curated"] if fingerprint(r) is not None)
    report = {
        "audit_date": "2026-10-20", "screening_not_imagery_validation": True,
        "basic_checks": "Maize; finite yield >= 0; finite nonzero WGS84 point or valid nonempty polygon; representative location within a broad envelope of the reported country; exact duplicate source rows after first removed. Polygon topology is checked without automatic repair. Zero yields are retained and counted separately.",
        "additional_yield_checks": "Excludes review flags for yield above 30 tonnes/ha, per-acre/per-hectare disagreement above 1%, Zimbabwe 40m2 conversion disagreement, or dry weight greater than wet weight. The 30 t/ha threshold is a review heuristic, not an agronomic impossibility limit. These extra checks still do not prove field-level location or yield protocol validity.",
        "screened_candidates_definition": "Pass basic and additional yield checks and exclude OAF Uganda 2020 coordinates documented as site locations. All curated OAF rows remain flagged for unresolved field/town/district coordinate provenance; their candidate count is not a verified field-location count. Zimbabwe yield units remain provisionally interpreted as tonnes/ha. No screened file is a fully validated training set.",
        "country_screening_envelopes": COUNTRY_ENVELOPES,
        "oaf_curated_matching_full_release_fingerprints": overlap,
        "overlap_definition": "Same country/year, coordinates rounded to 6 decimals and kg/ha yield rounded to 3 decimals. This is a lower-bound overlap warning, not a definitive field-ID linkage. No pooled unique-field count is asserted.",
        "datasets": summaries,
    }
    (OUT / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    compact = [{k: v for k, v in s.items() if not isinstance(v, (list, dict))} for s in summaries]
    write_csv(OUT / "summary.csv", compact)
    rows_html = "".join("<tr>" + "".join(f"<td>{html.escape(str(s[k]))}</td>" for k in ["dataset", "maize_records", "passes_basic_checks", "screened_candidates", "screened_candidates_since_2019", "zero_yield_in_screened_candidates"]) + "</tr>" for s in summaries)
    details_html = ""
    for s in summaries:
        name = s["dataset"]
        details_html += f'<h2>{html.escape(name)}</h2><p><a href="{name}_maize_audit.csv">All maize rows and audit flags</a> · <a href="{name}_screened_candidates.csv">Screened candidates CSV</a></p><ul>' + "".join(f"<li>{html.escape(n)}</li>" for n in s["notes"]) + "</ul>"
        details_html += "<p>Flag counts (overlapping):</p><pre>" + html.escape(json.dumps(s["flag_counts"], indent=2)) + "</pre>"
        details_html += "<p>Basic candidates by year:</p><pre>" + html.escape(json.dumps(s["by_year"], indent=2)) + "</pre>"
        if name.startswith("malawi"):
            details_html += f'<p><a href="{name}_candidates_wgs84.geojson">Candidate field boundaries in WGS84</a></p>'
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Maize dataset audit</title>
<style>body{max-width:1120px;margin:40px auto;padding:0 24px;font:16px/1.55 system-ui;color:#202a27}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;text-align:left;border-bottom:1px solid #ccd5ce}th{background:#e9f1eb}h1,h2{color:#264b37}pre{white-space:pre-wrap;background:#f4f6f4;padding:16px}a{color:#176046}li{margin:8px 0}.note{border-left:4px solid #b78023;padding:12px 16px;background:#fff9ed}</style>
<h1>Maize yield and location audit</h1><p>Checked 20 October 2026. Original files are preserved under <a href="../raw/">data/raw</a>.</p>
<p class="note"><strong>These are screening candidates, not imagery-validated field observations.</strong> Numeric GPS values do not establish that a point lies inside its maize field. The OAF releases overlap and must not be added together.</p>
<table><tr><th>Dataset</th><th>Maize rows</th><th>Basic candidates</th><th>After extra checks</th><th>2019+ after extra checks</th><th>Zero yields included after extra checks</th></tr>''' + rows_html + "</table>"
    page += "<h2>Checks and interpretation</h2><p>" + html.escape(report["basic_checks"]) + "</p><p>" + html.escape(report["additional_yield_checks"]) + "</p>"
    page += "<p>" + html.escape(report["screened_candidates_definition"]) + "</p>"
    page += f"<p>{overlap:,} curated OAF rows match full-release fingerprints. " + html.escape(report["overlap_definition"]) + "</p>"
    page += '<p><a href="summary.json">Full machine-readable summary and thresholds</a> · <a href="summary.csv">Summary CSV</a> · <a href="../metadata/download_manifest.json">Download sources and SHA-256 checksums</a></p>'
    page += details_html + "<h2>Next validation needed</h2><p>Check locations against imagery; investigate repeated coordinates and yield flags; verify Zimbabwe yield units and exceptional crop-cut areas; reconcile Malawi campaign counts with the provider. For model evaluation, keep all observations from a field or spatial cluster in the same split.</p></html>"
    (OUT / "report.html").write_text(page)
    print(f"Report: {OUT / 'report.html'}", flush=True)


if __name__ == "__main__":
    main()
