"""labels_v1: the one table every model reads. Contract and checks: docs/DATA.md.

One row per field-season of every cohort. It starts from ``load_cohort`` (the audited rows) and
adds what the audit leaves out: the grouping columns of the raw files, each cohort's yield
definition, flags, and the inclusion decision. Nothing is deleted: a row that is not used has
``include_primary`` False and an ``exclusion_reason``. There is deliberately no standardised
target; models standardise inside the training fold.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import shape
from shapely.ops import transform

from cropyield import ROOT
from cropyield.data.cohorts import AUDIT_DIR, COHORTS, load_cohort
from cropyield.eval.splits import connected_clusters, has_neighbour

RAW_DIR = ROOT / "data" / "raw"
LABELS_PATH = ROOT / "data" / "processed" / "labels_v1.parquet"
# Data v2 (docs/DECISIONS.md, 5 Nov 2026): v1 plus Malawi 2022, whose polygons come from a second audit with
# the datum operation EPSG:1113. Every other row is the v1 row unchanged.
V2_DIR = ROOT / "data" / "v2"
LABELS_V2_PATH = V2_DIR / "processed" / "labels_v2.parquet"
AUDIT_V2_DIR = V2_DIR / "audit"
MANIFEST_PATH = ROOT / "data" / "metadata" / "download_manifest.json"
MAX_YIELD_KG_HA = 15_000
ACRE_HA = 0.40468564224
OAF_WORKBOOK = RAW_DIR / "one_acre_fund_full" / "one_acre_fund_mel_data_all_countries.xlsx"
LACUNA_GEOJSON = RAW_DIR / "zimbabwe" / "Lacuna_Yield_data_geojson-2023.geojson"
MALAWI_2023_ZIP = RAW_DIR / "malawi" / "mwi_kas_lc_fo_202305_cc_yield.zip"
MALAWI_2022_ZIP = RAW_DIR / "malawi" / "mwi_mwi_lc_fo_202205_averageyield_v1.zip"


@dataclass(frozen=True)
class Measurement:
    """How one cohort measures yield and locates a field (docs/DATA.md, first table).

    Cut area, number of cuts and moisture are declared from the provider documents: one constant
    per cohort, not a measurement of the row.
    """
    role: str                     # core, second, parked or dropped
    iso3: str
    definition: str
    cut_area_m2: float
    n_cuts: int
    moisture_pct: float | None    # None: the provider does not state a moisture basis
    unit_provisional: bool
    location_source: str
    source_crs: str


MEASUREMENTS = {
    "malawi_2022": Measurement("dropped", "MWI", "mean_2_cuts_5x5m", 25, 2, None, False, "walked_polygon", "EPSG:20936"),
    "malawi_2023": Measurement("core", "MWI", "cut_10x10m_13pct", 100, 1, 13.0, False, "walked_polygon", "EPSG:4326"),
    "kenya_oaf_2019_2020": Measurement("core", "KEN", "mean_2_boxes_6x6m", 36, 2, None, False,
                                       "field_gps_maybe_homestead", "EPSG:4326"),
    "zimbabwe_lacuna_2022_2023": Measurement("second", "ZWE", "cut_8x5m_dry_weight", 40, 1, None, True, "field_gps", "OGC:CRS84"),
    "zimbabwe_2024": Measurement("parked", "ZWE", "mean_2_boxes_40m2", 40, 2, None, False, "field_gps", "EPSG:4326"),
}
MEASUREMENTS_V2 = {**MEASUREMENTS, "malawi_2022": replace(MEASUREMENTS["malawi_2022"], role="second",
                                                          source_crs="EPSG:20936 via EPSG:1113")}


def audit_dir(name: str, version: int) -> Path:
    """Where a cohort's audited rows are: data/v2/audit for Malawi 2022 in v2, data/audit for everything else.

    The v2 audit must have been written with EPSG:1113, as MEASUREMENTS_V2 records; anything else stops here.
    """
    if version == 2 and name == "malawi_2022":
        summary = AUDIT_V2_DIR / "summary.json"
        if not summary.exists() or json.loads(summary.read_text())["datum_operation"] != "EPSG:1113":
            raise ValueError(f"{summary} is missing or was not written with --datum-operation EPSG:1113")
        return AUDIT_V2_DIR
    return AUDIT_DIR

# Audited rows per cohort and harvest year; a change here means the audit changed.
EXPECTED_ROWS = {("malawi_2022", 2022): 529, ("malawi_2023", 2023): 260, ("kenya_oaf_2019_2020", 2019): 1768,
                 ("kenya_oaf_2019_2020", 2020): 2209, ("zimbabwe_lacuna_2022_2023", 2022): 169,
                 ("zimbabwe_lacuna_2022_2023", 2023): 2097, ("zimbabwe_2024", 2024): 4332}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_column(frame: pd.DataFrame, column: str) -> pd.Series:
    """A source column, or empty text where this cohort does not have it."""
    return frame[column] if column in frame else pd.Series("", index=frame.index)


def number_column(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(text_column(frame, column), errors="coerce")


def dates(text: pd.Series) -> pd.Series:
    """Calendar dates from the mixed source formats; NaT where blank or unreadable."""
    return pd.to_datetime(text.replace("", None), errors="coerce", format="mixed").dt.normalize()


def normal_district(text: pd.Series) -> pd.Series:
    """OAF spells districts differently per year: kakamega(south), kakamegasouth, kakamegab(north)."""
    return (text.str.lower().str.replace(r"[^a-z]", "", regex=True)
            .str.replace("kakamegab", "kakamega", regex=False))


def oaf_groups() -> pd.DataFrame:
    """Raw workbook columns of the audited rows the audit drops, by ``source_row`` (slow: about a minute)."""
    from openpyxl import load_workbook
    book = load_workbook(OAF_WORKBOOK, read_only=True, data_only=True)
    rows = book["Data"].iter_rows(values_only=True)
    header = list(next(rows))
    wanted = ("unique_id", "district", "site", "site_latitude", "site_longitude", "plot_acres",
              "yield_kg_ph", "yield_kg_pa", "field_latitude", "field_longitude")
    position = {name: header.index(name) for name in wanted}
    records = []
    for number, raw in enumerate(rows, 2):
        if str(raw[header.index("country")] or "").strip().lower() == "kenya":
            records.append({"source_row": number, **{name: raw[i] for name, i in position.items()}})
    book.close()
    return pd.DataFrame(records)


def lacuna_groups() -> pd.DataFrame:
    """Raw GeoJSON properties of the Lacuna maize rows, by ``Case_ID``."""
    features = json.loads(LACUNA_GEOJSON.read_text())["features"]
    rows = []
    for feature in features:
        properties = feature["properties"]
        if properties["Crop_Type"] == "Maize/Corn":
            rows.append({"source_id": str(properties["Case_ID"]), "Admin1": properties["Admin1"],
                         "Field_Irri": properties["Field_Irri"], "raw_yield_t_ha": properties["Yield(Mt/H"],
                         "raw_dry_kg": properties["Dry_weight"],
                         "raw_lon": feature["geometry"]["coordinates"][0], "raw_lat": feature["geometry"]["coordinates"][1]})
    return pd.DataFrame(rows)


def malawi_2023_raw() -> pd.DataFrame:
    """Main and nested cut of Malawi 2023 from the shapefile itself, by ``source_id``."""
    import shapefile
    with zipfile.ZipFile(MALAWI_2023_ZIP) as archive:
        stem = next(name[:-4] for name in archive.namelist() if name.endswith(".shp"))
        reader = shapefile.Reader(dbf=io.BytesIO(archive.read(stem + ".dbf")))
        return pd.DataFrame([{"source_id": r["globalid"], "cc_ey_t": r["cc_ey_t"], "subc_ey_t": r["subc_ey_t"]}
                             for r in reader.records()])


def malawi_2022_raw() -> pd.DataFrame:
    """AVG_YLD of Malawi 2022 from the shapefile itself, by ``source_id``."""
    import shapefile
    with zipfile.ZipFile(MALAWI_2022_ZIP) as archive:
        stem = next(name[:-4] for name in archive.namelist() if name.endswith(".shp"))
        reader = shapefile.Reader(dbf=io.BytesIO(archive.read(stem + ".dbf")))
        return pd.DataFrame([{"source_id": r["globalid"], "AVG_YLD": r["AVG_YLD"]} for r in reader.records()])


def field_polygons(dataset: str, directory: Path = AUDIT_DIR) -> dict[str, str]:
    """source_id -> polygon WKT from the audited WGS84 boundary file."""
    path = directory / f"{dataset}_candidates_wgs84.geojson"
    features = json.loads(path.read_text())["features"]
    return {str(f["properties"]["source_id"]): shape(f["geometry"]).wkt for f in features}


def overlapping_polygons(wkt: pd.Series) -> pd.Series:
    """True where a polygon overlaps another one by more than half of the smaller polygon's area."""
    from shapely import wkt as wkt_io
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32736", always_xy=True).transform
    polygons = [transform(to_utm, wkt_io.loads(text)) for text in wkt]
    tree, flagged = STRtree(polygons), np.zeros(len(polygons), dtype=bool)
    for left, right in zip(*tree.query(polygons, predicate="intersects")):
        if left < right:
            shared = polygons[left].intersection(polygons[right]).area
            if shared > 0.5 * min(polygons[left].area, polygons[right].area):
                flagged[[left, right]] = True
    return pd.Series(flagged, index=wkt.index)


def geodesic_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km; NaN where a coordinate is missing."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(h))


def cohort_frame(name: str, oaf: pd.DataFrame, lacuna: pd.DataFrame, version: int = 1) -> pd.DataFrame:
    """labels rows of one cohort, before the flags that need all rows of the cohort."""
    directory = audit_dir(name, version)
    rows, m = load_cohort(name, directory), (MEASUREMENTS_V2 if version == 2 else MEASUREMENTS)[name]
    frame = pd.DataFrame({
        "obs_id": rows["obs_id"], "cohort": name, "role": m.role, "dataset": rows["dataset"],
        "source_id": rows["source_id"], "source_row": rows["source_row"],
        "source_sha256": sha256(directory / f"{COHORTS[name].dataset}_screened_candidates.csv"),
        "country_iso3": m.iso3, "season_year": rows["year"],
        "season_start": pd.to_datetime(rows["season_start"]), "season_end": pd.to_datetime(rows["season_end"]),
        "yield_kg_ha": rows["yield_kg_ha"],
        "yield_definition": m.definition, "cut_area_m2": float(m.cut_area_m2), "n_cuts": m.n_cuts,
        "moisture_basis_pct": m.moisture_pct, "unit_provisional": m.unit_provisional,
        "cut1_kg_ha": np.nan, "cut2_kg_ha": np.nan,
        "geometry_type": rows["geometry_type"], "lat": rows["latitude"], "lon": rows["longitude"],
        "field_area_ha": number_column(rows, "field_area_ha"), "location_source": m.location_source, "source_crs": m.source_crs,
        "plant_date": dates(text_column(rows, "planting_date")), "harvest_date": dates(text_column(rows, "harvest_date")),
        "intercropped": text_column(rows, "intercropping").map({"0": False, "no": False, "1": True, "yes": True}),
        "irrigated": pd.NA, "admin_unit": None, "site_unit": None, "site_distance_km": np.nan,
        "source_flags": rows["quality_flags"],
    })
    frame["intercropped"] = frame["intercropped"].astype("boolean")
    frame["irrigated"] = frame["irrigated"].astype("boolean")
    observed = dates(text_column(rows, "observation_time"))
    # obs_date: the harvest date, else the crop-cut or photo date, else NaT.
    frame["obs_date"] = frame["harvest_date"].fillna(observed)
    frame["obs_date_source"] = np.where(frame["harvest_date"].notna(), "harvest_date", np.where(
        observed.notna(), "photo_filename" if name == "zimbabwe_2024" else "crop_cut_time", "none"))
    frame["geometry_wkt"] = None
    if name.startswith("malawi"):
        polygons = field_polygons(COHORTS[name].dataset, directory)
        frame["geometry_wkt"] = frame["source_id"].map(polygons)
    if name == "malawi_2023":
        frame["cut1_kg_ha"] = rows["yield_kg_ha"]
        frame["cut2_kg_ha"] = number_column(rows, "nested_subcut_yield_t_ha") * 1000
    if name == "zimbabwe_2024":
        frame["cut1_kg_ha"] = number_column(rows, "box1_yield_t_ha") * 1000
        frame["cut2_kg_ha"] = number_column(rows, "box2_yield_t_ha") * 1000
    if name == "kenya_oaf_2019_2020":
        raw = rows[["source_row"]].merge(oaf, on="source_row", how="left", validate="one_to_one")
        frame["admin_unit"] = normal_district(raw["district"].fillna("").astype(str)).to_numpy()
        site = raw["site"].fillna("").astype(str).str.lower().str.strip()
        frame["site_unit"] = (frame["admin_unit"] + "|" + site.to_numpy()).to_numpy()
        site_lat = pd.to_numeric(raw["site_latitude"], errors="coerce").to_numpy()
        site_lon = pd.to_numeric(raw["site_longitude"], errors="coerce").to_numpy()
        frame["site_distance_km"] = geodesic_km(frame["lat"].to_numpy(), frame["lon"].to_numpy(), site_lat, site_lon)
        frame["field_area_ha"] = (pd.to_numeric(raw["plot_acres"], errors="coerce") * ACRE_HA).to_numpy()
    if name == "zimbabwe_lacuna_2022_2023":
        raw = rows[["source_id"]].merge(lacuna, on="source_id", how="left", validate="one_to_one")
        frame["admin_unit"] = raw["Admin1"].str.strip().str.lower().to_numpy()
        frame["irrigated"] = raw["Field_Irri"].map({"no": False, "yes": True}).astype("boolean").to_numpy()
    return frame


def add_cohort_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Flags that compare rows: 2 km clusters, near-duplicates, overlapping polygons, dates."""
    lat, lon = frame["lat"].to_numpy(), frame["lon"].to_numpy()
    frame["cluster_2km"] = connected_clusters(lat, lon, 2.0)
    frame["near_dup_10m"] = has_neighbour(lat, lon, 0.01)
    frame["polygon_overlap_dup"] = False
    if frame["geometry_wkt"].notna().all():
        frame["polygon_overlap_dup"] = overlapping_polygons(frame["geometry_wkt"])
    frame["is_zero"] = frame["yield_kg_ha"] == 0
    frame["date_outside_window"] = (frame["obs_date"] < frame["season_start"]) | (frame["obs_date"] > frame["season_end"])
    year = frame["season_year"]
    plant, harvest = frame["plant_date"], frame["harvest_date"]
    frame["impossible_date"] = ((plant.notna() & ((plant.dt.year < year - 1) | (plant.dt.year > year)))
                                | (harvest.notna() & plant.notna() & (harvest <= plant))
                                | (harvest.notna() & ((harvest.dt.year < year) | (harvest.dt.year > year + 1))))
    return frame


def exclusion_reasons(frame: pd.DataFrame, version: int = 1) -> pd.Series:
    """Why a row is out of the primary analysis; '' for rows that are in. First reason wins.

    In v2 the Malawi 2022 imagery gap is closed (older collection), so that rule is gone; all else is v1.
    """
    # An NA in intercropped or irrigated counts as pure stand and rainfed. No Lacuna row is NA.
    conditions = [
        ((frame["cohort"] == "malawi_2022") & (version == 1), "dropped_cohort_2022_imagery_gap"),
        ((frame["cohort"] == "zimbabwe_lacuna_2022_2023") & (frame["season_year"] == 2022), "dropped_year_2022_imagery_gap"),
        ((frame["cohort"] == "zimbabwe_lacuna_2022_2023") & frame["intercropped"].fillna(False).astype(bool), "lacuna_intercropped"),
        ((frame["cohort"] == "zimbabwe_lacuna_2022_2023") & frame["irrigated"].fillna(False).astype(bool), "lacuna_irrigated"),
        ((frame["cohort"] == "zimbabwe_2024") & frame["is_zero"], "zimbabwe_2024_zero_likely_not_measured"),
        (frame["yield_kg_ha"] > MAX_YIELD_KG_HA, "yield_above_15_t_ha"),
    ]
    reasons = pd.Series("", index=frame.index, dtype=object)
    for condition, reason in reversed(conditions):
        reasons[condition] = reason
    return reasons


COLUMNS = ["obs_id", "cohort", "role", "dataset", "source_id", "source_row", "source_sha256",
           "country_iso3", "season_year", "season_start", "season_end", "yield_kg_ha",
           "yield_definition", "cut_area_m2", "n_cuts", "moisture_basis_pct", "unit_provisional", "cut1_kg_ha", "cut2_kg_ha",
           "geometry_type", "lat", "lon", "geometry_wkt", "field_area_ha", "location_source", "source_crs",
           "plant_date", "harvest_date", "obs_date", "obs_date_source", "intercropped", "irrigated",
           "admin_unit", "site_unit", "cluster_2km", "site_distance_km",
           "is_zero", "near_dup_10m", "polygon_overlap_dup", "date_outside_window", "impossible_date", "source_flags",
           "include_primary", "exclusion_reason"]


def build_labels(oaf: pd.DataFrame, lacuna: pd.DataFrame, version: int = 1) -> pd.DataFrame:
    """All cohorts, in COHORTS order, with every labels column; version 1 is labels_v1, version 2 adds Malawi 2022."""
    frames = [add_cohort_flags(cohort_frame(name, oaf, lacuna, version)) for name in COHORTS]
    labels = pd.concat(frames, ignore_index=True)
    labels["exclusion_reason"] = exclusion_reasons(labels, version)
    labels["include_primary"] = labels["exclusion_reason"] == ""
    return labels[COLUMNS]


def check_labels(labels: pd.DataFrame) -> list[str]:
    """Checks 1, 2, 4, 6, 8 and 10 of docs/DATA.md, on the table alone. Empty list: all pass."""
    problems = []
    if labels["obs_id"].isna().any() or labels["obs_id"].duplicated().any():
        problems.append("obs_id is not unique and non-null")
    counts = labels.groupby(["cohort", "season_year"]).size().to_dict()
    if counts != EXPECTED_ROWS:
        problems.append(f"row counts changed: {counts}")
    primary = labels[labels["include_primary"]]
    if not primary["yield_kg_ha"].between(0, MAX_YIELD_KG_HA).all():
        problems.append("an included row has a yield outside [0, 15000] kg/ha")
    if primary[["lat", "lon"]].isna().any(axis=None):
        problems.append("an included row has no coordinates")
    for column in ("yield_definition", "cut_area_m2", "n_cuts"):
        if (labels.groupby("cohort")[column].nunique() != 1).any():
            problems.append(f"a cohort has more than one {column}")
    lacuna = primary[primary["cohort"] == "zimbabwe_lacuna_2022_2023"]
    if lacuna["intercropped"].any() or lacuna["irrigated"].any():
        problems.append("an included Lacuna row is intercropped or irrigated")
    if primary.loc[primary["cohort"] == "zimbabwe_2024", "is_zero"].any():
        problems.append("an included Zimbabwe 2024 row has zero yield")
    for cohort, rows in labels.groupby("cohort"):
        close = connected_clusters(rows["lat"].to_numpy(), rows["lon"].to_numpy(), 0.01)
        if (pd.Series(rows["cluster_2km"].to_numpy()).groupby(close).nunique() > 1).any():
            problems.append(f"{cohort}: rows within 10 m are in different clusters")
    return problems


def check_against_raw(labels: pd.DataFrame, oaf: pd.DataFrame, lacuna: pd.DataFrame) -> list[str]:
    """Rows re-derive from the provider files (parts of checks 3, 7 and 11 of docs/DATA.md).

    Kenya: source id, yield, kg/ha against kg/acre, latitude, district. Lacuna: yield, t/ha = dry kg x 0.25,
    latitude. Malawi 2022 and 2023: yield and the nested cut. Zimbabwe 2024: the yield is the mean of its two
    boxes. The SHA-256 of 4 raw files (OAF workbook, Lacuna GeoJSON, both Malawi zips) against
    data/metadata/download_manifest.json, where it lists them. Not checked here: longitudes, the Malawi polygon
    area (check 5) and the Zimbabwe 2024 metadata.csv checksum.
    """
    problems = []
    kenya = labels[labels["cohort"] == "kenya_oaf_2019_2020"].merge(oaf, on="source_row", validate="one_to_one")
    # Excel stored one id as a date; the audit wrote it with isoformat().
    raw_id = kenya["unique_id"].map(lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value))
    if (kenya["source_id"] != raw_id).any():
        problems.append("Kenya: source_row points at another unique_id")
    per_ha = pd.to_numeric(kenya["yield_kg_ph"], errors="coerce")
    per_acre = pd.to_numeric(kenya["yield_kg_pa"], errors="coerce") / ACRE_HA
    expected = per_ha.fillna(per_acre)
    if (np.abs(kenya["yield_kg_ha"] - expected) > 1e-6).any():
        problems.append("Kenya: yield_kg_ha differs from the workbook")
    if ((np.abs(per_ha - per_acre) > np.maximum(1, per_ha.abs() * 0.01)) & per_ha.notna() & per_acre.notna()).any():
        problems.append("Kenya: kg/ha and kg/acre disagree by more than 1 %")
    if (np.abs(kenya["lat"] - pd.to_numeric(kenya["field_latitude"])) > 1e-7).any():
        problems.append("Kenya: latitude differs from the workbook")
    if (kenya["admin_unit"] == "").any():
        problems.append("Kenya: a row has no district")

    zimbabwe = labels[labels["cohort"] == "zimbabwe_lacuna_2022_2023"].merge(lacuna, on="source_id", validate="one_to_one")
    if (np.abs(zimbabwe["yield_kg_ha"] - zimbabwe["raw_yield_t_ha"].astype(float) * 1000) > 1e-6).any():
        problems.append("Lacuna: yield_kg_ha differs from the GeoJSON")
    if (np.abs(zimbabwe["raw_yield_t_ha"].astype(float) - zimbabwe["raw_dry_kg"].astype(float) * 0.25) > 1e-3).any():
        problems.append("Lacuna: t/ha is not dry kg x 0.25")
    if (np.abs(zimbabwe["lat"] - zimbabwe["raw_lat"].astype(float)) > 1e-7).any():
        problems.append("Lacuna: latitude differs from the GeoJSON")

    malawi = labels[labels["cohort"] == "malawi_2023"].merge(malawi_2023_raw(), on="source_id", validate="one_to_one")
    if (np.abs(malawi["yield_kg_ha"] - malawi["cc_ey_t"].astype(float) * 1000) > 1e-6).any():
        problems.append("Malawi 2023: yield_kg_ha differs from cc_ey_t")
    if (np.abs(malawi["cut2_kg_ha"] - malawi["subc_ey_t"].astype(float) * 1000) > 1e-6).any():
        problems.append("Malawi 2023: nested cut differs from subc_ey_t")

    malawi_2022 = labels[labels["cohort"] == "malawi_2022"].merge(malawi_2022_raw(), on="source_id", validate="one_to_one")
    if (np.abs(malawi_2022["yield_kg_ha"] - malawi_2022["AVG_YLD"].astype(float) * 1000) > 1e-6).any():
        problems.append("Malawi 2022: yield_kg_ha differs from AVG_YLD")

    boxes = labels[(labels["cohort"] == "zimbabwe_2024") & labels["cut1_kg_ha"].notna() & labels["cut2_kg_ha"].notna()]
    if (np.abs(boxes["yield_kg_ha"] - (boxes["cut1_kg_ha"] + boxes["cut2_kg_ha"]) / 2) > 1).any():
        problems.append("Zimbabwe 2024: yield is not the mean of the two boxes")

    recorded = {entry["path"].replace("\\", "/"): entry["sha256"] for entry in manifest_entries()}
    for path in (OAF_WORKBOOK, LACUNA_GEOJSON, MALAWI_2023_ZIP, MALAWI_2022_ZIP):
        key = path.relative_to(RAW_DIR).as_posix()
        found = [value for name, value in recorded.items() if name.endswith(key)]
        if found and found[0] != sha256(path):
            problems.append(f"{key}: SHA-256 differs from the download manifest")
    return problems


def manifest_entries() -> list[dict]:
    """Every {path, sha256} entry of the download manifest, wherever it is nested."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            digest = value.get("sha256")
            path = value.get("path") or value.get("relative_path") or value.get("local_path") or value.get("file")
            if digest and path:
                found.append({"path": str(path), "sha256": digest})
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(json.loads(MANIFEST_PATH.read_text()))
    return found
