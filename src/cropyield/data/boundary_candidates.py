"""Review FTW model-predicted boundaries without moving points or replacing truth."""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
from pyproj import Transformer
from shapely import wkb, wkt
from shapely.geometry import Point
from shapely.ops import transform

from cropyield.data.labels import LABELS_PATH, sha256

SOURCE_TEMPLATE = "https://data.source.coop/ftw/global-data-2e/vector/{year}/zone={zone}/utm{zone}.parquet"
ATTRIBUTION = "Fields of The World global-data-2e, global annual predicted field boundaries, CC BY 4.0"
SOURCE_PAGE = "https://source.coop/ftw/global-data-2e"
COHORTS = ("malawi_2023", "kenya_oaf_2019_2020")


def reference_rows(labels: pd.DataFrame, per_cohort_limit: int | None) -> pd.DataFrame:
    malawi = labels.loc[(labels.cohort == "malawi_2023") & labels.include_primary].copy()
    kenya = labels.loc[labels.cohort == "kenya_oaf_2019_2020"].copy()
    kenya = kenya.loc[kenya.duplicated(["lat", "lon"], keep=False)]
    rows = pd.concat([malawi, kenya]).sort_values(["cohort", "season_year", "obs_id"])
    if per_cohort_limit is not None:
        # Include each country/year, rather than letting Kenya 2019 consume the pilot.
        rows = rows.groupby(["cohort", "season_year"], sort=False).head(per_cohort_limit)
    rows = rows.copy().reset_index(drop=True)
    rows["zone"] = ((rows.lon + 180) // 6 + 1).astype(int)
    rows["tile_x"] = (rows.lon * 10).apply(math.floor)
    rows["tile_y"] = (rows.lat * 10).apply(math.floor)
    return rows


def projected_reference(row):
    source = wkt.loads(row.geometry_wkt) if isinstance(row.geometry_wkt, str) else Point(row.lon, row.lat)
    epsg = (32600 if row.lat >= 0 else 32700) + int(row.zone)
    forward = Transformer.from_crs(4326, epsg, always_xy=True).transform
    inverse = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    return source, transform(forward, source), forward, inverse


def candidate_evidence(row, candidates: pd.DataFrame, radius_m: float = 30) -> list[dict]:
    """Rank only by geometric distance, then identifier; scores/yields never choose a field."""
    _, reference, forward, _ = projected_reference(row)
    point = transform(forward, Point(row.lon, row.lat))
    evidence = []
    for candidate in candidates.itertuples(index=False):
        geometry = wkb.loads(bytes(candidate.geometry))
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        projected = transform(forward, geometry)
        distance = reference.distance(projected)
        if distance > radius_m:
            continue
        iou = None
        if reference.geom_type in ("Polygon", "MultiPolygon"):
            union_area = reference.union(projected).area
            iou = reference.intersection(projected).area / union_area if union_area else None
        evidence.append({"obs_id": row.obs_id, "candidate_id": str(candidate.id),
                         "distance_m": distance, "contains_reference_point": bool(projected.covers(point)),
                         "malawi_polygon_iou": iou, "score": candidate.score,
                         "score_interpretation": "model_score_not_calibrated_boundary_accuracy",
                         "collection": candidate.collection, "year": int(row.season_year),
                         "zone": int(row.zone), "source_url": SOURCE_TEMPLATE.format(year=row.season_year, zone=row.zone)})
    evidence.sort(key=lambda item: (item["distance_m"], item["candidate_id"]))
    for rank, item in enumerate(evidence, 1):
        item["distance_rank"] = rank
    return evidence


def describe_candidates(evidence: list[dict]) -> dict:
    containing = sum(item["contains_reference_point"] for item in evidence)
    status = ("no_candidate_unknown" if not evidence else "ambiguous_multiple_candidates" if len(evidence) > 1
              else "one_predicted_candidate_requires_review")
    ious = [item["malawi_polygon_iou"] for item in evidence if item["malawi_polygon_iou"] is not None]
    return {"candidate_count": len(evidence), "containing_count": containing, "status": status,
            "best_malawi_iou": max(ious) if ious else None,
            "mean_malawi_iou": sum(ious) / len(ious) if ious else None,
            "decision": "review_only;no_coordinate_or_boundary_replacement"}


def fetch_candidates(connection, group, remaining: float, row_limit: int = 20_000) -> pd.DataFrame:
    boxes = []
    for row in group.itertuples(index=False):
        _, reference, _, inverse = projected_reference(row)
        boxes.append(transform(inverse, reference.buffer(30)).bounds)
    xmin, ymin = min(b[0] for b in boxes), min(b[1] for b in boxes)
    xmax, ymax = max(b[2] for b in boxes), max(b[3] for b in boxes)
    url = SOURCE_TEMPLATE.format(year=int(group.season_year.iloc[0]), zone=int(group.zone.iloc[0]))
    # The source is spatially sorted. This tile-sized bbox predicate enables row-group pruning.
    query = """SELECT id,collection,geometry,score,"metrics:area" AS reported_area_m2
               FROM read_parquet(?) WHERE bbox.xmin <= ? AND bbox.xmax >= ?
               AND bbox.ymin <= ? AND bbox.ymax >= ? LIMIT ?"""
    timer = threading.Timer(max(0.01, remaining), connection.interrupt)
    timer.daemon = True
    timer.start()
    try:
        frame = connection.execute(query, [url, xmax, xmin, ymax, ymin, row_limit + 1]).df()
    finally:
        timer.cancel()
    if len(frame) > row_limit:
        raise RuntimeError("Candidate query exceeded its row cap; subdivide the tile rather than silently truncating")
    return frame


def run_boundary_review(output_root: Path, per_cohort_limit: int | None = 2, max_seconds: float = 180) -> Path:
    started = time.monotonic()
    before = sha256(LABELS_PATH)
    rows = reference_rows(pd.read_parquet(LABELS_PATH), per_cohort_limit)
    run = output_root / datetime.now(UTC).strftime("ftw-review-%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True, exist_ok=False)
    extension_dir = output_root / "duckdb_extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET extension_directory = ?", [str(extension_dir.resolve())])
    setup_error = None
    try:
        con.execute("LOAD httpfs")
        con.execute("SET http_timeout=30")
    except duckdb.Error:
        try:
            con.execute("INSTALL httpfs FROM 'https://extensions.duckdb.org'")
            con.execute("LOAD httpfs")
            con.execute("SET http_timeout=30")
        except duckdb.Error as error:
            setup_error = str(error)
    record_results, pair_results, saved_candidates, query_log = [], [], [], []
    for _, group in rows.groupby(["country_iso3", "season_year", "zone", "tile_x", "tile_y"], sort=True):
        remaining = max_seconds - (time.monotonic() - started)
        error = setup_error or ("Time budget exhausted before this tile" if remaining <= 0 else None)
        candidates = None
        if error is None:
            try:
                candidates = fetch_candidates(con, group, remaining)
            except (duckdb.Error, RuntimeError) as failure:
                error = str(failure)
        query_log.append({"country": group.country_iso3.iloc[0], "year": int(group.season_year.iloc[0]),
                          "zone": int(group.zone.iloc[0]), "observations": len(group),
                          "candidates_fetched": None if candidates is None else len(candidates), "error": error})
        if candidates is not None:
            candidates = candidates.copy()
            candidates["year"] = int(group.season_year.iloc[0])
            candidates["zone"] = int(group.zone.iloc[0])
            candidates["country_iso3"] = group.country_iso3.iloc[0]
            saved_candidates.append(candidates)
        for row in group.itertuples(index=False):
            evidence = candidate_evidence(row, candidates) if candidates is not None else []
            pair_results.extend(evidence)
            detail = describe_candidates(evidence)
            if error:
                detail.update(status="not_evaluated_query_error_or_budget", candidate_count=None, containing_count=None)
            record_results.append({"obs_id": row.obs_id, "country_iso3": row.country_iso3,
                                   "season_year": int(row.season_year), "original_lat": row.lat,
                                   "original_lon": row.lon, **detail, "query_error": error})
    con.close()
    after = sha256(LABELS_PATH)
    if before != after:
        raise RuntimeError("Protected labels changed during boundary review")
    records = pd.DataFrame(record_results)
    for country, selected in records.groupby("country_iso3"):
        destination = run / country
        destination.mkdir()
        selected.to_csv(destination / "observation_review.csv", index=False)
        pairs = pd.DataFrame([p for p in pair_results if p["obs_id"] in set(selected.obs_id)])
        pairs.to_csv(destination / "candidate_matches.csv", index=False)
        local = [c for c in saved_candidates if not c.empty and c.country_iso3.iloc[0] == country]
        if local:
            geometries = pd.concat(local).drop_duplicates(["year", "zone", "id"])
            geometries["geometry"] = geometries.geometry.map(bytes)
            geometries.to_parquet(destination / "predicted_boundaries.parquet", index=False)
    summary = {"source": ATTRIBUTION, "source_page": SOURCE_PAGE, "source_version": "global-data-2e",
               "radius_m": 30, "pilot_limit_per_country_year": per_cohort_limit,
               "records": len(records), "status_counts": records.status.value_counts().to_dict(),
               "queries": query_log, "labels_sha256_before": before, "labels_sha256_after": after,
               "inputs_unchanged": True, "module_sha256": sha256(Path(__file__)),
               "score_scale": "0 to 100; uncalibrated model score",
               "source_limitations": "Predictions filter fields below 900 square meters; sparse 2017–2019 imagery; "
               "annual imagery can include postharvest observations.",
               "interpretation": "FTW boundaries are model predictions, not surveyed field truth. No matches means unknown. "
               "Malawi overlap is validation evidence only; no yield-based selection or coordinate changes are performed."}
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return run
