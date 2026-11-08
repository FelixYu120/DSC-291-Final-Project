"""Source-backed Kenya review sidecars; never rewrite labels, coordinates or imagery.

An unusable date is quarantined only in proposed date columns. This is not a claim to
have recovered the true date. All field-season observations and original values remain.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from sklearn.neighbors import BallTree

from cropyield import ROOT
from cropyield.data.labels import LABELS_PATH, OAF_WORKBOOK, sha256
from cropyield.eval.splits import connected_clusters

COHORT = "kenya_oaf_2019_2020"
AUDIT = ROOT / "data/audit/one_acre_fund_full_screened_candidates.csv"
SPLIT = ROOT / "data/splits/kenya_oaf_2019_2020__s1_cc2km.csv"
DATABASE = ROOT / "data/cropyield.duckdb"
BANDS = ("b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12")


def source_text(value) -> str:
    if value is None:
        return ""
    return value.isoformat() if isinstance(value, (datetime, date)) else str(value)


def unambiguous_date(value) -> tuple[pd.Timestamp, str]:
    """Accept typed Excel dates or ISO dates; do not guess numeric serials or locale."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return pd.NaT, "source_missing"
    if isinstance(value, (date, datetime)):
        return pd.Timestamp(value.date() if isinstance(value, datetime) else value), "typed_excel_date"
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", value.strip()):
        try:
            parsed = datetime.fromisoformat(value.strip()).date()
            return pd.Timestamp(parsed), "iso_date"
        except ValueError:
            pass
    return pd.NaT, "unresolved_source_format"


def date_proposal(plant, harvest, year: int) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    """Keep valid components; quarantine an ambiguous reversed pair, without guessing."""
    plant, harvest = pd.Timestamp(plant), pd.Timestamp(harvest)
    reasons = []
    if pd.notna(plant) and not year - 1 <= plant.year <= year:
        plant = pd.NaT
        reasons.append("quarantine_plant_year_outside_season_range")
    if pd.notna(harvest) and not year <= harvest.year <= year + 1:
        harvest = pd.NaT
        reasons.append("quarantine_harvest_year_outside_season_range")
    if pd.notna(plant) and pd.notna(harvest) and harvest <= plant:
        plant, harvest = pd.NaT, pd.NaT
        reasons.append("quarantine_both_ambiguous_date_order")
    return plant, harvest, ";".join(reasons) or "retain_source_dates"


def raw_rows(workbook: Path, wanted: set[int]) -> pd.DataFrame:
    """Read selected Excel row numbers once, retaining typed date and linkage evidence."""
    names = ("unique_id", "country", "year", "crop", "intercrop", "district", "site", "plot_acres",
             "yield_kg_ph", "field_latitude", "field_longitude", "plant_date", "harvest_date")
    book = load_workbook(workbook, read_only=True, data_only=True)
    try:
        stream = book["Data"].iter_rows(values_only=True)
        header = list(next(stream))
        positions = {name: header.index(name) for name in names}
        result = []
        for number, values in enumerate(stream, 2):
            if number > max(wanted):
                break
            if number not in wanted:
                continue
            row = {"source_row": number, **{"raw_" + name: values[i] for name, i in positions.items()}}
            row["raw_row_sha256"] = hashlib.sha256(json.dumps(
                [source_text(v) for v in values], ensure_ascii=False).encode()).hexdigest()
            row["raw_payload_sha256_excluding_unique_id"] = hashlib.sha256(json.dumps(
                [source_text(v) for i, v in enumerate(values) if header[i] != "unique_id"],
                ensure_ascii=False).encode()).hexdigest()
            for name in ("plant_date", "harvest_date"):
                parsed, evidence = unambiguous_date(row["raw_" + name])
                row["raw_" + name + "_type"] = type(row["raw_" + name]).__name__
                row["raw_" + name + "_text"] = source_text(row["raw_" + name])
                row["raw_" + name + "_parsed"] = parsed
                row["raw_" + name + "_parse_evidence"] = evidence
                del row["raw_" + name]
            row["raw_unique_id"] = source_text(row["raw_unique_id"])
            result.append(row)
    finally:
        book.close()
    if len(result) != len(wanted):
        raise ValueError("Some Kenya source rows were not found in the workbook")
    return pd.DataFrame(result)


def review_dates(rows: pd.DataFrame) -> pd.DataFrame:
    result = rows.copy()
    decisions, recovered, proposals = [], [], []
    for row in rows.itertuples(index=False):
        dates = []
        recovery = []
        for name in ("plant_date", "harvest_date"):
            original = getattr(row, name)
            raw = getattr(row, "raw_" + name + "_parsed")
            if pd.notna(original) and (pd.isna(raw) or original != raw):
                raise ValueError(f"{row.obs_id}: {name} differs from the source or cannot be parsed safely")
            if pd.isna(original) and pd.notna(raw):
                recovery.append(name)
            dates.append(raw if pd.notna(raw) else original)
        proposed_plant, proposed_harvest, decision = date_proposal(*dates, int(row.season_year))
        proposals.append((proposed_plant, proposed_harvest))
        recovered.append(";".join(recovery))
        decisions.append(decision)
    result[["proposed_plant_date", "proposed_harvest_date"]] = pd.DataFrame(proposals, index=result.index)
    result["date_decision"] = decisions
    result["date_recovered_from_source"] = recovered
    result["original_missing_plant"] = result.plant_date.isna()
    result["original_missing_harvest"] = result.harvest_date.isna()
    result["proposed_obs_date"] = result.proposed_harvest_date
    result["date_quarantined"] = result.date_decision.str.startswith("quarantine_")
    result["retained_harvest_outside_window"] = ((result.proposed_harvest_date < result.season_start)
                                               | (result.proposed_harvest_date > result.season_end))
    result["timing_review_needed"] = (result.date_quarantined | result.original_missing_harvest
                                      | result.original_missing_plant | result.retained_harvest_outside_window)
    return result


def stable_group(prefix: str, ids) -> str:
    digest = hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()[:16]
    return f"{prefix}_{digest}"


def coordinate_review(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exact and <=10 m neighbors; no implication that a repeated GPS point is a duplicate field."""
    result = rows.copy().reset_index(drop=True)
    result["exact_coordinate_group_id"] = ""
    result["coordinate_group_id"] = ""
    result["exact_coordinate_group_size"] = 1
    for _, group in result.groupby(["lat", "lon"], sort=True):
        if len(group) > 1:
            result.loc[group.index, "exact_coordinate_group_id"] = stable_group("ken_exact", group.obs_id)
            result.loc[group.index, "exact_coordinate_group_size"] = len(group)
    clusters = connected_clusters(result.lat.to_numpy(), result.lon.to_numpy(), 0.01)
    for cluster in np.unique(clusters):
        group = result.loc[clusters == cluster]
        if len(group) > 1:
            result.loc[group.index, "coordinate_group_id"] = stable_group("ken_near10m", group.obs_id)
    radians = np.radians(result[["lat", "lon"]].to_numpy(dtype=float))
    neighbors, distances = BallTree(radians, metric="haversine").query_radius(
        radians, r=0.01 / 6371.0088, return_distance=True, sort_results=True)
    pairs = []
    for i, (others, gaps) in enumerate(zip(neighbors, distances)):
        for j, gap in zip(others, gaps):
            if j <= i:
                continue
            left, right = result.iloc[i], result.iloc[j]
            exact = left.lat == right.lat and left.lon == right.lon
            pairs.append({"left_obs_id": left.obs_id, "right_obs_id": right.obs_id,
                          "distance_m": float(gap * 6371008.8), "exact_coordinates": exact,
                          "same_year": bool(left.season_year == right.season_year),
                          "same_source_id": bool(left.source_id == right.source_id),
                          "same_district": bool(left.raw_district == right.raw_district),
                          "same_site": bool(left.raw_site == right.raw_site),
                          "same_reported_area": bool(left.raw_plot_acres == right.raw_plot_acres),
                          "same_yield": bool(left.yield_kg_ha == right.yield_kg_ha),
                          "identical_full_source_row": left.raw_row_sha256 == right.raw_row_sha256,
                          "identical_payload_except_id": (left.raw_payload_sha256_excluding_unique_id
                                                          == right.raw_payload_sha256_excluding_unique_id),
                          "same_spatial_group": bool(left.group_id == right.group_id),
                          "same_spatial_fold": bool(left.fold == right.fold),
                          "coordinate_group_id": left.coordinate_group_id,
                          "decision": "retain_and_group;provider_location_review",
                          "pixel_interpretation": ("same_point_same_season;check_scene_and_band_evidence"
                                                   if exact and left.season_year == right.season_year
                                                   else "distance_alone_does_not_establish_same_pixel")})
    return result, pd.DataFrame(pairs)


def add_imagery_evidence(pairs: pd.DataFrame, database: Path) -> pd.DataFrame:
    result = pairs.copy()
    with duckdb.connect(str(database), read_only=True) as con:
        scenes = con.execute("SELECT s.obs_id,s.month,s.item_id FROM scenes s JOIN labels l USING(obs_id) "
                             "WHERE l.cohort=?", [COHORT]).df()
        monthly = con.execute("SELECT b.* FROM monthly_bands b JOIN labels l USING(obs_id) WHERE l.cohort=?",
                              [COHORT]).df()
    scene_sets = {key: dict(zip(group.month, group.item_id)) for key, group in scenes.groupby("obs_id")}
    band_sets = {key: group.sort_values("month").set_index("month")[list(BANDS)]
                 for key, group in monthly.groupby("obs_id")}
    evidence = []
    for row in pairs.itertuples(index=False):
        left, right = scene_sets.get(row.left_obs_id, {}), scene_sets.get(row.right_obs_id, {})
        common = set(left) & set(right)
        a, b = band_sets.get(row.left_obs_id), band_sets.get(row.right_obs_id)
        same_bands = (a is not None and b is not None and a.index.equals(b.index)
                      and np.array_equal(a.to_numpy(), b.to_numpy(), equal_nan=True))
        evidence.append({"common_scene_months": len(common),
                         "matching_scene_months": sum(left[month] == right[month] for month in common),
                         "same_complete_scene_series": bool(left and left == right),
                         "same_complete_monthly_bands": same_bands})
    return pd.concat([result, pd.DataFrame(evidence, index=result.index)], axis=1)


def run_review(output_root: Path) -> Path:
    """Write derived records, pair evidence and provenance under a fresh KEN folder."""
    protected = [LABELS_PATH, OAF_WORKBOOK, AUDIT, SPLIT, DATABASE, ROOT / "data/splits/manifest.json",
                 ROOT / "configs/sentinel2_scenes_v1.parquet"]
    before = {str(path.relative_to(ROOT)): sha256(path) for path in protected}
    labels = pd.read_parquet(LABELS_PATH)
    kenya = labels.loc[labels.cohort == COHORT].copy()
    raw = raw_rows(OAF_WORKBOOK, set(kenya.source_row.astype(int)))
    rows = kenya.merge(raw, on="source_row", how="left", validate="one_to_one")
    if not (rows.source_id == rows.raw_unique_id).all():
        raise ValueError("Kenya workbook row identifiers do not match labels")
    for column, source in (("lat", "raw_field_latitude"), ("lon", "raw_field_longitude"),
                           ("yield_kg_ha", "raw_yield_kg_ph")):
        if not np.allclose(rows[column], pd.to_numeric(rows[source]), rtol=0, atol=1e-7):
            raise ValueError(f"Kenya {column} differs from provider source")
    audit = pd.read_csv(AUDIT, dtype=str, keep_default_na=False)
    audit["source_row"] = audit.source_row.astype(int)
    audit = audit[["source_row", "source_id", "planting_date", "harvest_date", "quality_flags"]].rename(
        columns={"planting_date": "audit_plant_date_text", "harvest_date": "audit_harvest_date_text",
                 "quality_flags": "audit_quality_flags"})
    rows = rows.merge(audit, on=["source_row", "source_id"], how="left", validate="one_to_one")
    if rows.audit_quality_flags.isna().any():
        raise ValueError("A Kenya source row is missing from the frozen audit")
    for name in ("plant_date", "harvest_date"):
        parsed = pd.to_datetime(rows["audit_" + name + "_text"], errors="coerce", format="mixed").dt.normalize()
        rows["audit_" + name + "_agrees_with_raw"] = ((parsed == rows["raw_" + name + "_parsed"])
                                                     | (parsed.isna() & rows["raw_" + name + "_parsed"].isna()))
    splits = pd.read_csv(SPLIT, dtype={"obs_id": str, "group_id": str, "fold": str})
    rows = rows.merge(splits[["obs_id", "group_id", "fold"]], on="obs_id", how="left", validate="one_to_one")
    if rows.group_id.isna().any():
        raise ValueError("A Kenya record is missing its frozen spatial group")
    rows, pairs = coordinate_review(review_dates(rows))
    pairs = add_imagery_evidence(pairs, DATABASE)
    if not (pairs.same_spatial_group & pairs.same_spatial_fold).all():
        raise ValueError("Near-coincident Kenya records cross frozen spatial groups or folds")
    rows["record_decision"] = "retain_observation;no_yield_or_coordinate_change"
    rows["proposed_lat"] = rows.lat
    rows["proposed_lon"] = rows.lon
    rows["proposed_yield_kg_ha"] = rows.yield_kg_ha
    rows["location_scope"] = "field_or_homestead_or_nearby_per_provider"
    rows["area_scope"] = "crop_and_field_type_land_not_verified_individual_field"
    summary = {
        "observations_retained": len(rows), "observations_removed": 0,
        "yield_changes": 0, "coordinate_changes": 0,
        "date_decisions": rows.date_decision.value_counts().to_dict(),
        "dates_recovered_from_source": int(rows.date_recovered_from_source.ne("").sum()),
        "original_missing_plant_dates": int(rows.original_missing_plant.sum()),
        "original_missing_harvest_dates": int(rows.original_missing_harvest.sum()),
        "raw_harvest_date_types_for_original_missing": rows.loc[rows.original_missing_harvest,
                                                               "raw_harvest_date_type"].value_counts().to_dict(),
        "exact_coordinate_observations": int(rows.exact_coordinate_group_id.ne("").sum()),
        "exact_coordinate_groups": int(rows.loc[rows.exact_coordinate_group_id.ne(""), "exact_coordinate_group_id"].nunique()),
        "near_10m_observations": int(rows.coordinate_group_id.ne("").sum()),
        "near_10m_groups": int(rows.loc[rows.coordinate_group_id.ne(""), "coordinate_group_id"].nunique()),
        "near_10m_pairs": len(pairs), "exact_pairs": int(pairs.exact_coordinates.sum()),
        "exact_pairs_cross_year": int((pairs.exact_coordinates & ~pairs.same_year).sum()),
        "near_pairs_cross_year": int((~pairs.same_year).sum()),
        "pairs_identical_full_source_row": int(pairs.identical_full_source_row.sum()),
        "pairs_identical_payload_except_id": int(pairs.identical_payload_except_id.sum()),
        "pairs_same_source_id": int(pairs.same_source_id.sum()),
        "exact_pairs_same_yield": int((pairs.exact_coordinates & pairs.same_yield).sum()),
        "exact_pairs_same_monthly_bands": int((pairs.exact_coordinates & pairs.same_complete_monthly_bands).sum()),
        "near_pairs_grouped_in_frozen_spatial_split": bool((pairs.same_spatial_group & pairs.same_spatial_fold).all()),
        "interpretation": "Quarantined dates are unknown, not corrected true dates. Repeated coordinates are not proof of duplicate fields.",
        "location_scope": "field_or_homestead_or_nearby_per_provider",
        "area_scope": "crop_and_field_type_land_not_verified_individual_field",
        "provider_metadata_evidence": {"location": "Workbook Variables!C40:C41",
                                       "area": "Workbook Variables!C75:C76 and Description row 2"},
        "audit_dates_agree_with_raw": bool(rows.audit_plant_date_agrees_with_raw.all()
                                           and rows.audit_harvest_date_agrees_with_raw.all()),
    }
    after = {str(path.relative_to(ROOT)): sha256(path) for path in protected}
    if before != after:
        raise RuntimeError("Protected inputs changed during Kenya review")
    run_id = datetime.now(UTC).strftime("kenya-review-%Y%m%dT%H%M%S%fZ")
    destination = output_root / run_id / "KEN"
    destination.mkdir(parents=True, exist_ok=False)
    rows.to_parquet(destination / "record_review.parquet", index=False)
    rows.loc[rows.timing_review_needed].to_csv(destination / "date_review.csv", index=False)
    pairs.to_csv(destination / "coordinate_pairs.csv", index=False)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    provenance = {"protected_sha256_before": before, "protected_sha256_after": after,
                  "inputs_unchanged": True, "module_sha256": sha256(Path(__file__)),
                  "derived_output_sha256": {name: sha256(destination / name) for name in
                                            ("record_review.parquet", "date_review.csv", "coordinate_pairs.csv", "summary.json")},
                  "source_workbook_sheet": "Data", "source_row_convention": "Excel row number including header",
                  "no_training": True, "no_automatic_label_or_coordinate_edits": True}
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return destination
