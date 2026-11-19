"""Step 1 of the pass archive: every survey observation for Kenya, Malawi and Zimbabwe, all crops, all years.

Reads the original provider files under ``data/raw`` and writes Parquet tables to ``staging/survey``:
``source_files``, ``source_records``, ``fields``, ``locations``, ``field_source_crosswalk``, ``labels``,
``label_measurements``, ``splits``, ``split_specs``. Nothing is filtered: a record without a yield or without
a usable location stays, with a status that says why.

Run: ``python -m cropyield.archive.survey``
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import shapefile
from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import transform as shapely_transform

from cropyield.archive import ids, paths

ACRE_HA = 0.40468564224                     # hectares in one acre
CURATED_FACTOR = 2.41705                    # the curated release multiplied kg/acre by this, not by 1/ACRE_HA
ENVELOPE = {"KEN": (33.8, -4.9, 42.1, 5.2), "MWI": (32.5, -17.2, 36.0, -9.2), "ZWE": (25.1, -22.5, 33.1, -15.5)}
ISO = {"kenya": "KEN", "malawi": "MWI", "zimbabwe": "ZWE"}
CROP = {"maize/corn": "maize", "maize": "maize", "wheat": "wheat", "sorghum": "sorghum", "soybeans": "soybean"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clean(value):
    """A JSON-safe copy of one cell; missing values become None."""
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)) or hasattr(value, "isoformat"):
        return pd.Timestamp(value).isoformat() if not hasattr(value, "isoformat") else value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def payload(row: dict) -> str:
    """The original columns of one source row as JSON, without the empty cells."""
    return json.dumps({key: clean(value) for key, value in row.items() if clean(value) is not None},
                      ensure_ascii=False, default=str)


def as_date(value):
    stamp = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(stamp) else stamp.date()


def location_fields(iso: str, lat, lon, quality_if_good: str) -> dict:
    """Location quality of a point. Only a finite point inside the country envelope is usable."""
    if lat is None or lon is None or not (np.isfinite(lat) and np.isfinite(lon)):
        return {"latitude": None, "longitude": None, "location_quality": "missing", "usable_at_field_scale": False,
                "unusable_reason": "no coordinates in the source"}
    west, south, east, north = ENVELOPE[iso]
    if not (west <= lon <= east and south <= lat <= north):
        return {"latitude": float(lat), "longitude": float(lon), "location_quality": "outside_country",
                "usable_at_field_scale": False, "unusable_reason": "coordinates outside the country"}
    usable = quality_if_good in ("field_point", "field_polygon")
    return {"latitude": float(lat), "longitude": float(lon), "location_quality": quality_if_good,
            "usable_at_field_scale": usable,
            "unusable_reason": None if usable else "provider rounded and shifted the point by about 160 m"}


def label_status(value, zero_is_failure: bool = False, not_measured: bool = False) -> str:
    if not_measured:
        return "not_measured"
    if value is None or not np.isfinite(value):
        return "not_answered"
    if value == 0:
        return "verified_crop_failure" if zero_is_failure else "recorded_zero"
    return "measured_positive"


# ------------------------------------------------------------------------------------------------ readers
def read_oaf_full(path: Path, file_id: str) -> tuple[list[dict], list[dict], pd.DataFrame]:
    frame = pd.read_excel(path, sheet_name="Data")
    frame["xlsx_row"] = np.arange(len(frame)) + 2
    # pandas turns a whole-number float cell into an int; the legacy obs_id used the cell as openpyxl gives it
    # (Excel damaged some ids into numbers such as 1.3621e+55), so read the id column once more, untouched.
    from openpyxl import load_workbook
    sheet = load_workbook(path, read_only=True, data_only=True)["Data"]
    stored = [row[0] for row in sheet.iter_rows(min_row=2, max_col=1, values_only=True)][:len(frame)]
    assert len(stored) == len(frame), "id column and data rows differ in length"
    frame["unique_id"] = pd.Series(stored, dtype=object).to_numpy()
    out_of_scope = int((~frame["country"].isin(["Kenya", "Malawi"])).sum())
    frame = frame[frame["country"].isin(["Kenya", "Malawi"])].copy()
    records, measures = [], []
    for row in frame.to_dict("records"):
        raw_id = row["unique_id"]
        provider_id = raw_id.isoformat() if hasattr(raw_id, "isoformat") else str(raw_id)
        iso = ISO[row["country"].lower()]
        obs = ids.source_observation_id("one_acre_fund_full", provider_id)
        per_ha, per_acre = clean(row["yield_kg_ph"]), clean(row["yield_kg_pa"])
        year = int(row["year"])
        box = {2016: 40.0, 2017: 40.0, 2018: 36.0, 2019: 36.0}.get(year) if iso == "KEN" else None
        record = {
            "source_observation_id": obs, "dataset": "one_acre_fund_full", "source_file_id": file_id,
            "provider_record_id": provider_id, "provider_id_damaged_by_excel": not isinstance(raw_id, str),
            "source_row_number": int(row["xlsx_row"]), "country_iso3": iso, "crop_raw": clean(row["crop"]),
            "crop": "maize", "season_raw": clean(row["season"]), "harvest_year": year,
            "year_basis": "season_year_column", "year_inferred": False,
            "planting_date": as_date(row["plant_date"]), "harvest_date": as_date(row["harvest_date"]),
            "survey_date": None, "survey_date_basis": None,
            "admin_unit": clean(row["district"]), "site_unit": clean(row["site"]),
            "intercropped": None if clean(row["intercrop"]) is None else bool(row["intercrop"]),
            "irrigated": None, "geometry_type": "point", "source_crs": "WGS84 (assumed, not stated)",
            "source_geometry_wkt": None,
            **location_fields(iso, clean(row["field_latitude"]), clean(row["field_longitude"]), "field_point"),
            "yield_raw": per_ha, "yield_raw_unit": "kg/ha", "yield_kg_ha": per_ha,
            "yield_conversion": "none (provider column yield_kg_ph = yield_kg_pa / 0.40468564224)",
            "moisture_basis": "not stated", "n_cuts": 2, "cut_area_m2": box,
            "protocol": "two randomly placed crop-cut boxes, weighed by One Acre Fund staff",
            "label_status": label_status(per_ha), "zero_evidence": None,
            "payload_json": payload({k: v for k, v in row.items() if k != "xlsx_row"}),
        }
        records.append(record)
        for name, value, unit in (("yield_kg_ph", per_ha, "kg/ha"), ("yield_kg_pa", per_acre, "kg/acre"),
                                  ("prev_season_yield", clean(row["prev_season_yield"]), "farmer report, unit unstated")):
            if value is not None:
                measures.append({"source_observation_id": obs, "measurement": name, "cut_number": None,
                                 "value": float(value), "unit": unit})
    return records, measures, pd.DataFrame({"out_of_scope_rows": [out_of_scope]})


def read_oaf_curated(path: Path, file_id: str) -> tuple[list[dict], list[dict], int]:
    frame = pd.read_csv(path, low_memory=False)
    frame["csv_line"] = np.arange(len(frame)) + 2
    out_of_scope = int((frame["iso"] != "KEN").sum())      # the curated release has no Malawi or Zimbabwe rows
    frame = frame[frame["iso"] == "KEN"].copy()
    records, measures = [], []
    for row in frame.to_dict("records"):
        obs = ids.source_observation_id("one_acre_fund_curated", f"row_{int(row['csv_line'])}")
        raw = clean(row["yield_kg_ha"])
        fixed = None if raw is None else float(raw) / CURATED_FACTOR / ACRE_HA
        records.append({
            "source_observation_id": obs, "dataset": "one_acre_fund_curated", "source_file_id": file_id,
            "provider_record_id": None, "provider_id_damaged_by_excel": False,
            "source_row_number": int(row["csv_line"]), "country_iso3": "KEN", "crop_raw": "maize", "crop": "maize",
            "season_raw": clean(row["season"]), "harvest_year": int(row["year"]),
            "year_basis": "season_year_column", "year_inferred": False,
            "planting_date": as_date(row["plant_date"]), "harvest_date": as_date(row["harvest_date"]),
            "survey_date": None, "survey_date_basis": None, "admin_unit": clean(row["strat"]), "site_unit": None,
            "intercropped": False, "irrigated": None, "geometry_type": "point",
            "source_crs": "WGS84 (assumed, not stated)", "source_geometry_wkt": None,
            **location_fields("KEN", clean(row["lat"]), clean(row["lon"]), "rounded_point"),
            "yield_raw": raw, "yield_raw_unit": "kg/ha as published (kg/acre x 2.41705)", "yield_kg_ha": fixed,
            "yield_conversion": "published value / 2.41705 / 0.40468564224 (the release used 2.41705 for 2.47105)",
            "moisture_basis": "not stated", "n_cuts": 2, "cut_area_m2": None,
            "protocol": "curated copy of the One Acre Fund crop cuts, pure stands only, outliers removed",
            "label_status": label_status(raw), "zero_evidence": None,
            "payload_json": payload({k: v for k, v in row.items() if k != "csv_line"}),
        })
        if raw is not None:
            measures.append({"source_observation_id": obs, "measurement": "yield_kg_ha_as_published",
                             "cut_number": None, "value": float(raw), "unit": "kg/ha as published"})
    return records, measures, out_of_scope


def read_lacuna(path: Path, file_id: str) -> tuple[list[dict], list[dict]]:
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    records, measures = [], []
    for number, feature in enumerate(features, start=1):
        props = feature["properties"]
        obs = ids.source_observation_id("zimbabwe", props["Case_ID"])
        lon, lat = feature["geometry"]["coordinates"][:2]
        tonnes = clean(props["Yield(Mt/H"])
        failed = props.get("Crop_Condi") == "no_crop_survived"
        records.append({
            "source_observation_id": obs, "dataset": "zimbabwe", "source_file_id": file_id,
            "provider_record_id": props["Case_ID"], "provider_id_damaged_by_excel": False,
            "source_row_number": number, "country_iso3": "ZWE", "crop_raw": props["Crop_Type"],
            "crop": CROP[props["Crop_Type"].lower()], "season_raw": None,
            "harvest_year": int(props["Harvesting"][:4]), "year_basis": "harvest_date", "year_inferred": False,
            "planting_date": as_date(props["Planting_D"]), "harvest_date": as_date(props["Harvesting"]),
            "survey_date": as_date(props["Harvesting"]), "survey_date_basis": "crop-cut day",
            "admin_unit": props.get("Admin1"), "site_unit": None,
            "intercropped": props.get("Intercropp") == "yes", "irrigated": props.get("Field_Irri") == "yes",
            "geometry_type": "point", "source_crs": "OGC:CRS84", "source_geometry_wkt": Point(lon, lat).wkt,
            **location_fields("ZWE", lat, lon, "field_point"),
            "yield_raw": tonnes, "yield_raw_unit": "t/ha", "yield_kg_ha": None if tonnes is None else tonnes * 1000,
            "yield_conversion": "t/ha x 1000 (provider: dry weight kg x 0.25)",
            "moisture_basis": "dry weight after drying, percent not stated", "n_cuts": 1, "cut_area_m2": 40.0,
            "protocol": "one 8 m x 5 m crop cut, weighed wet at harvest and again after drying",
            "label_status": label_status(tonnes, zero_is_failure=failed),
            "zero_evidence": f"Crop_Condi={props.get('Crop_Condi')}" if tonnes == 0 else None,
            "payload_json": payload(props),
        })
        for name, unit in (("Wet_Weight", "kg per cut"), ("Dry_weight", "kg per cut"), ("Yield(Mt/H", "t/ha")):
            if clean(props[name]) is not None:
                measures.append({"source_observation_id": obs, "measurement": name, "cut_number": 1,
                                 "value": float(props[name]), "unit": unit})
    return records, measures


def read_vision(path: Path, file_id: str) -> tuple[list[dict], list[dict], int]:
    frame = pd.read_csv(path, low_memory=False)
    frame["csv_line"] = np.arange(len(frame)) + 2
    out_of_scope = int((frame["country"] != "Zimbabwe").sum())
    frame = frame[frame["country"] == "Zimbabwe"].copy()
    photo_date = pd.to_datetime(frame["q_field_photo"].str.extract(r"(\d{4}-\d{2}-\d{2})-\d{2}-\d{2}-\d{2}")[0],
                                errors="coerce")
    weight_photos = ["q_box1_wet_weight_photo", "q_box2_wet_weight_photo", "q_box1_dry_weight_photo",
                     "q_box2_dry_weight_photo"]
    records, measures = [], []
    for row, taken in zip(frame.to_dict("records"), photo_date):
        obs = ids.source_observation_id("vision_guided_yield_estimation", row["cce_id"])
        tonnes = clean(row["Avg_yield_mt_ha"])
        comment = clean(row["Comments"])
        evidence = None
        if tonnes == 0:
            has_photo = any(clean(row[name]) is not None for name in weight_photos)
            evidence = "all box weights 0; " + ("a weight photo exists" if has_photo
                                               else "no weight photo: likely not measured")
        records.append({
            "source_observation_id": obs, "dataset": "vision_guided_yield_estimation", "source_file_id": file_id,
            "provider_record_id": row["cce_id"], "provider_id_damaged_by_excel": False,
            "source_row_number": int(row["csv_line"]), "country_iso3": "ZWE", "crop_raw": row["crop"],
            "crop": CROP[row["crop"].lower()], "season_raw": None,
            "harvest_year": int(row["data_collection_year"]), "year_basis": "season_year_column",
            "year_inferred": False, "planting_date": None, "harvest_date": None,
            "survey_date": None if pd.isna(taken) else taken.date(), "survey_date_basis": "field photo file name",
            "admin_unit": None, "site_unit": None, "intercropped": None, "irrigated": None,
            "geometry_type": "point", "source_crs": "WGS84", "source_geometry_wkt": None,
            **location_fields("ZWE", clean(row["latitude"]), clean(row["longitude"]), "field_point"),
            "yield_raw": tonnes, "yield_raw_unit": "t/ha", "yield_kg_ha": None if tonnes is None else tonnes * 1000,
            "yield_conversion": "t/ha x 1000 (provider: mean of boxes, dry kg / 4)",
            "moisture_basis": "dry weight after drying, percent not stated", "n_cuts": 2, "cut_area_m2": 40.0,
            "protocol": "two 40 m2 crop-cut boxes, weighed wet and dry, photos of the scale",
            "label_status": label_status(tonnes, not_measured=tonnes is None and comment is not None),
            "zero_evidence": evidence if tonnes == 0 else comment if tonnes is None else None,
            "payload_json": payload({k: v for k, v in row.items() if k != "csv_line"}),
        })
        for box in (1, 2):
            for name, unit in ((f"box{box}_wet_weight_confirmation", "kg per box"),
                               (f"box{box}_dry_weight_confirmation", "kg per box"), (f"box{box}_into_mt_ha", "t/ha")):
                if clean(row[name]) is not None:
                    measures.append({"source_observation_id": obs, "measurement": name, "cut_number": box,
                                     "value": float(row[name]), "unit": unit})
    return records, measures, out_of_scope


def read_malawi(path: Path, file_id: str, year: int, v2_geometry: dict[str, str]) -> tuple[list[dict], list[dict]]:
    archive = zipfile.ZipFile(path)
    base = next(name[:-4] for name in archive.namelist() if name.endswith(".shp"))
    reader = shapefile.Reader(shp=io.BytesIO(archive.read(base + ".shp")), dbf=io.BytesIO(archive.read(base + ".dbf")),
                              shx=io.BytesIO(archive.read(base + ".shx")))
    crs = CRS.from_wkt(archive.read(base + ".prj").decode())
    to_wgs84 = Transformer.from_crs(crs, 4326, always_xy=True).transform
    dataset = f"malawi_{year}"
    names = [field[0] for field in reader.fields[1:]]
    records, measures = [], []
    for number, item in enumerate(reader.iterShapeRecords(), start=1):
        props = dict(zip(names, item.record))
        obs = ids.source_observation_id(dataset, props["globalid"])
        native = shape(item.shape.__geo_interface__)
        if year == 2022:    # Arc 1950 polygons: reuse the reviewed data-v2 geometry (datum operation EPSG:1113)
            wgs84 = None
            if obs in v2_geometry:
                from shapely import wkt as _wkt
                wgs84 = _wkt.loads(v2_geometry[obs])
            how = "Arc 1950 / UTM 36S to WGS84 with datum operation EPSG:1113 (data v2 geometry)"
            if wgs84 is None:
                wgs84, how = shapely_transform(to_wgs84, native), "Arc 1950 / UTM 36S to WGS84, PROJ default"
        else:
            wgs84, how = native, "none (provider WGS84)"
        was_valid = wgs84.is_valid
        if not was_valid:
            wgs84 = make_valid(wgs84)
        point = wgs84.representative_point()
        taken = as_date(props["start_time"])
        if year == 2022:
            tonnes, cuts, area = clean(props["AVG_YLD"]), 2, 25.0
            protocol = "two 5 m x 5 m crop cuts per field, kernel moisture measured; AVG_YLD is their mean"
            measure_names = (("AVG_YLD", "t/ha"),)
        else:
            tonnes, cuts, area = clean(props["cc_ey_t"]), 1, 100.0
            protocol = "one 10 m x 10 m crop cut (cc_ey_t) with a nested 5 m x 5 m cut (subc_ey_t)"
            measure_names = (("cc_ey_t", "t/ha"), ("subc_ey_t", "t/ha"), ("ff_ey_t", "t/ha"))
        info = location_fields("MWI", point.y, point.x, "field_polygon")
        records.append({
            "source_observation_id": obs, "dataset": dataset, "source_file_id": file_id,
            "provider_record_id": props["globalid"], "provider_id_damaged_by_excel": False,
            "source_row_number": number, "country_iso3": "MWI", "crop_raw": props.get("CT_NAME") or "maize (campaign)",
            "crop": "maize", "season_raw": None, "harvest_year": year, "year_basis": "survey_date",
            "year_inferred": False, "planting_date": None, "harvest_date": None, "survey_date": taken,
            "survey_date_basis": "crop-cut visit (start_time)", "admin_unit": None, "site_unit": None,
            "intercropped": None, "irrigated": None, "geometry_type": "polygon",
            "source_crs": crs.name + (" (EPSG:20936)" if year == 2022 else " (EPSG:4326)"),
            "source_geometry_wkt": native.wkt, **info,
            "geometry_wkt_wgs84": wgs84.wkt, "geometry_transformation": how, "polygon_was_invalid": not was_valid,
            "yield_raw": tonnes, "yield_raw_unit": "t/ha", "yield_kg_ha": None if tonnes is None else tonnes * 1000,
            "yield_conversion": "t/ha x 1000", "moisture_basis": "13 percent kernel moisture",
            "n_cuts": cuts, "cut_area_m2": area, "protocol": protocol, "label_status": label_status(tonnes),
            "zero_evidence": None, "payload_json": payload(props),
        })
        for name, unit in measure_names:
            value = clean(props[name])
            if value is not None and not (name == "ff_ey_t" and value == 0):
                measures.append({"source_observation_id": obs, "measurement": name, "cut_number": None,
                                 "value": float(value), "unit": unit})
    return records, measures


# -------------------------------------------------------------------------------------------- identity links
def link_curated(records: pd.DataFrame) -> pd.DataFrame:
    """Match each curated Kenya row to full-workbook rows: same year, yield = kg/acre x 2.41705, point within
    0.00151 degrees on each axis, planting dates equal or one missing. Returns curated id, candidate full ids."""
    full = records[(records.dataset == "one_acre_fund_full") & (records.country_iso3 == "KEN")
                   & records.yield_raw.notna()].copy()
    full["as_curated"] = full.yield_raw * ACRE_HA * CURATED_FACTOR
    curated = records[records.dataset == "one_acre_fund_curated"]
    rows = []
    for year, part in curated.groupby("harvest_year"):
        pool = full[full.harvest_year == year].sort_values("as_curated")
        values = pool.as_curated.to_numpy()
        for row in part.itertuples():
            # 0.02 kg/ha: the workbook's kg/ha column differs from kg/acre / 0.40468564224 by up to 0.007 kg
            low, high = np.searchsorted(values, [row.yield_raw - 0.02, row.yield_raw + 0.02])
            near = pool.iloc[low:high]
            near = near[(near.latitude - row.latitude).abs().le(0.00151) & (near.longitude - row.longitude).abs().le(0.00151)]
            if not pd.isna(row.planting_date):
                near = near[near.planting_date.isna() | (near.planting_date == row.planting_date)]
            rows.append({"curated_id": row.source_observation_id, "candidates": list(near.source_observation_id)})
    return pd.DataFrame(rows)


def build() -> dict:
    raw, out = paths.raw_dir(), paths.staging_dir("survey")
    out.mkdir(parents=True, exist_ok=True)
    data = paths.data_dir()
    v2 = pd.read_parquet(data / "v2" / "processed" / "labels_v2.parquet")
    v2_geometry = dict(v2.loc[v2.dataset == "malawi_2022", ["obs_id", "geometry_wkt"]].dropna().values)

    sources = [
        ("one_acre_fund_full", raw / "one_acre_fund_full" / "one_acre_fund_mel_data_all_countries.xlsx",
         "One Acre Fund MEL data, all countries (workbook, sheet Data)", "CC BY 4.0"),
        ("one_acre_fund_curated", raw / "one_acre_fund_curated" / "One_Acre_Fund_MEL_maize_survey_data_2016-2022.csv",
         "One Acre Fund MEL maize survey data 2016-2022, curated (Zenodo 11122388)", "CC BY 4.0"),
        ("zimbabwe", raw / "zimbabwe" / "Lacuna_Yield_data_geojson-2023.geojson",
         "Lacuna Fund / PULA Advisors Zimbabwe crop cuts (Zenodo 10060610)", "CC BY 4.0"),
        ("vision_guided_yield_estimation", raw / "vision_guided_yield_estimation" / "metadata.csv",
         "Scalable Vision-Guided Crop Yield Estimation Dataset (Zenodo 17626117)", "CC BY 4.0"),
        ("malawi_2022", raw / "malawi" / "mwi_mwi_lc_fo_202205_averageyield_v1.zip",
         "FAO / NASA Harvest Malawi crop-cut campaign 2022", "CC BY"),
        ("malawi_2023", raw / "malawi" / "mwi_kas_lc_fo_202305_cc_yield.zip",
         "FAO / NASA Harvest Malawi crop-cut campaign 2023", "CC BY"),
    ]
    files, records, measures = [], [], []
    for dataset, path, title, licence in sources:
        file_id = sha256(path)
        skipped = 0
        if dataset == "one_acre_fund_full":
            new, extra, info = read_oaf_full(path, file_id)
            skipped = int(info.out_of_scope_rows[0])
        elif dataset == "one_acre_fund_curated":
            new, extra, skipped = read_oaf_curated(path, file_id)
        elif dataset == "zimbabwe":
            new, extra = read_lacuna(path, file_id)
        elif dataset == "vision_guided_yield_estimation":
            new, extra, skipped = read_vision(path, file_id)
        else:
            new, extra = read_malawi(path, file_id, int(dataset[-4:]), v2_geometry)
        records += new
        measures += extra
        files.append({"source_file_id": file_id, "dataset": dataset, "title": title, "licence": licence,
                      "path": path.relative_to(data).as_posix(), "bytes": path.stat().st_size,
                      "rows_in_scope": len(new), "rows_other_countries": skipped})
        print(f"{dataset}: {len(new)} rows in scope, {skipped} rows of other countries")

    frame = pd.DataFrame(records)
    for column in ("geometry_wkt_wgs84", "geometry_transformation"):
        if column not in frame:
            frame[column] = None
    points = frame.geometry_type.eq("point") & frame.latitude.notna()
    frame.loc[points, "geometry_wkt_wgs84"] = [f"POINT ({lon:.7f} {lat:.7f})" for lon, lat in
                                               zip(frame.longitude[points], frame.latitude[points])]
    frame.loc[points, "geometry_transformation"] = "none"
    frame["polygon_was_invalid"] = frame.get("polygon_was_invalid", False)
    frame["polygon_was_invalid"] = frame["polygon_was_invalid"].fillna(False).astype(bool)
    assert frame.source_observation_id.is_unique, "source_observation_id repeats"

    # --- field-seasons: one per source record, except a curated row that matches exactly one full-workbook row
    links = link_curated(frame)
    one = {row.curated_id: row.candidates[0] for row in links.itertuples() if len(row.candidates) == 1}
    many = {row.curated_id: row.candidates for row in links.itertuples() if len(row.candidates) > 1}
    primary_of = {obs: one.get(obs, obs) for obs in frame.source_observation_id}
    frame["field_season_id"] = [ids.field_season_id([primary_of[obs]]) for obs in frame.source_observation_id]
    crosswalk = pd.DataFrame({
        "field_season_id": frame.field_season_id, "source_observation_id": frame.source_observation_id,
        "link_role": ["same_record_other_release" if obs in one else "primary" for obs in frame.source_observation_id],
        "match_method": ["year + yield x 2.41705 + point within 0.00151 deg + planting date" if obs in one or obs in many
                         else None for obs in frame.source_observation_id],
        "n_candidates": [1 if obs in one else len(many.get(obs, [])) for obs in frame.source_observation_id],
    })
    overlap = {}
    for group, (curated_id, candidates) in enumerate(sorted(many.items()), start=1):
        for obs in [curated_id, *candidates]:
            overlap[obs] = f"overlap_{group:04d}"
    linked = set(one.values())

    primary = frame[frame.source_observation_id.map(primary_of) == frame.source_observation_id].copy()
    primary["identity_status"] = ["ambiguous_overlap" if obs in overlap else "linked_confident" if obs in linked
                                  else "single_source" for obs in primary.source_observation_id]
    primary["overlap_group_id"] = primary.source_observation_id.map(overlap)
    primary["n_source_records"] = primary.field_season_id.map(crosswalk.field_season_id.value_counts())
    primary["window_status"] = np.where(primary.harvest_year.notna(), "dated", "undated")
    primary["location_id"] = [ids.location_id(wkt) if usable and wkt else None for wkt, usable in
                              zip(primary.geometry_wkt_wgs84, primary.usable_at_field_scale)]

    legacy = v2.set_index("obs_id")[["cohort", "include_primary", "exclusion_reason"]]
    primary["legacy_cohort"] = primary.source_observation_id.map(legacy.cohort)
    primary["legacy_include_primary"] = primary.source_observation_id.map(legacy.include_primary)
    primary["legacy_exclusion_reason"] = primary.source_observation_id.map(legacy.exclusion_reason)
    missing = set(legacy.index) - set(primary.source_observation_id)
    assert not missing, f"{len(missing)} legacy obs_id have no source record, for example {sorted(missing)[:3]}"

    field_columns = ["field_season_id", "source_observation_id", "dataset", "country_iso3", "crop", "harvest_year",
                     "year_basis", "year_inferred", "window_status", "season_raw", "planting_date", "harvest_date",
                     "survey_date", "survey_date_basis", "admin_unit", "site_unit", "intercropped", "irrigated",
                     "geometry_type", "latitude", "longitude", "geometry_wkt_wgs84", "geometry_transformation",
                     "source_crs", "source_geometry_wkt", "polygon_was_invalid", "location_quality",
                     "usable_at_field_scale", "unusable_reason", "location_id", "identity_status", "overlap_group_id",
                     "n_source_records", "legacy_cohort", "legacy_include_primary", "legacy_exclusion_reason"]
    fields = primary[field_columns].rename(columns={"source_observation_id": "primary_source_observation_id"})
    assert fields.field_season_id.is_unique

    label_columns = ["field_season_id", "source_observation_id", "crop", "label_status", "yield_raw", "yield_raw_unit",
                     "yield_kg_ha", "yield_conversion", "moisture_basis", "n_cuts", "cut_area_m2", "protocol",
                     "zero_evidence"]
    labels = primary[label_columns]
    by_obs = frame.set_index("source_observation_id").field_season_id
    measurements = pd.DataFrame(measures)
    measurements.insert(0, "field_season_id", measurements.source_observation_id.map(by_obs))

    usable = fields[fields.location_id.notna()]
    locations = (usable.groupby("location_id", sort=True)
                 .agg(geometry_type=("geometry_type", "first"), geometry_wkt_wgs84=("geometry_wkt_wgs84", "first"),
                      latitude=("latitude", "first"), longitude=("longitude", "first"),
                      country_iso3=("country_iso3", "first"), n_field_seasons=("field_season_id", "size"))
                 .reset_index())

    # --- frozen splits, imported as they are, each under its own name
    spec_rows, split_rows = [], []
    for version, folder in (("v1", data / "splits"), ("v2", data / "v2" / "splits")):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for path in sorted(folder.glob("*.csv")):
            cohort, family = path.stem.split("__")
            table = pd.read_csv(path)
            name = f"frozen/{version}/{cohort}/{family}"
            table["field_season_id"] = table.obs_id.map(by_obs)
            assert table.field_season_id.notna().all(), f"{path.name}: obs_id without a source record"
            for column in ("season_year", "cluster_id", "group_id", "fold", "repeat"):
                if column not in table:
                    table[column] = None
            table["split_name"] = name
            for column in ("cluster_id", "group_id"):       # numbers in one family, names in another
                table[column] = table[column].map(lambda value: None if pd.isna(value) else str(value))
            for column in ("season_year", "fold", "repeat"):
                table[column] = pd.to_numeric(table[column], errors="coerce").astype("Int64")
            split_rows.append(table[["split_name", "field_season_id", "obs_id", "season_year", "cluster_id",
                                     "group_id", "fold", "repeat"]])
            spec_rows.append({"split_name": name, "frozen": True, "version": version, "cohort": cohort,
                              "family": family, "source_file": path.relative_to(data).as_posix(),
                              "sha256": sha256(path), "rows": len(table), "seed": manifest.get("seed"),
                              "generator_commit": manifest.get("generator_commit")})
    splits = pd.concat(split_rows, ignore_index=True)
    held = splits[splits.split_name.str.endswith("/s1_cc2km") & (splits.fold == 0)].field_season_id.unique()
    fields = fields.assign(fold0_reserved=fields.field_season_id.isin(held))

    record_columns = ["source_observation_id", "field_season_id", "dataset", "source_file_id", "provider_record_id",
                      "provider_id_damaged_by_excel", "source_row_number", "country_iso3", "crop_raw", "crop",
                      "harvest_year", "label_status", "location_quality", "usable_at_field_scale", "payload_json"]
    tables = {"source_files": pd.DataFrame(files), "source_records": frame[record_columns], "fields": fields,
              "locations": locations, "field_source_crosswalk": crosswalk, "labels": labels,
              "label_measurements": measurements, "splits": splits, "split_specs": pd.DataFrame(spec_rows)}
    for name, table in tables.items():
        table.to_parquet(out / f"{name}.parquet", index=False)
    summary = {name: len(table) for name, table in tables.items()}
    summary["curated_linked_to_one_full_row"] = len(one)
    summary["curated_ambiguous"] = len(many)
    summary["fold0_reserved_field_seasons"] = int(fields.fold0_reserved.sum())
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
