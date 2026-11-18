"""Extraction-support candidates and geometric validation, never inferred field boundaries."""
from __future__ import annotations

import math
from functools import lru_cache

import pandas as pd
from pyproj import Transformer
from shapely import from_wkt
from shapely.geometry import Point, mapping
from shapely.ops import transform

from cropyield.data.quality import CORE

RADII_M = (10, 20, 30)
OFFSETS_M = (0, 10, 20, 30)


@lru_cache(maxsize=120)
def _transformers(epsg: int):
    return (Transformer.from_crs(4326, epsg, always_xy=True).transform,
            Transformer.from_crs(epsg, 4326, always_xy=True).transform)


def metric_transforms(longitude: float, latitude: float):
    """Local UTM for area/distance calculations; always preserve lon/lat axis order."""
    if not (-180 <= longitude <= 180 and -80 <= latitude <= 84):
        raise ValueError("A finite coordinate in the UTM latitude range is required")
    zone = min(60, int((longitude + 180) // 6) + 1)
    epsg = (32600 if latitude >= 0 else 32700) + zone
    forward, reverse = _transformers(epsg)
    return forward, reverse, epsg


def support_circle(lon: float, lat: float, radius_m: float):
    """A circular sensitivity AOI around the supplied coordinate, not a field polygon."""
    if not math.isfinite(radius_m) or radius_m <= 0:
        raise ValueError("Radius must be finite and positive")
    forward, reverse, _ = metric_transforms(lon, lat)
    centre = transform(forward, Point(lon, lat))
    return transform(reverse, centre.buffer(radius_m, quad_segs=8))


def candidate_features(labels: pd.DataFrame):
    """Yield country/cohort GeoJSON features for active eligible point observations."""
    rows = labels.loc[labels.cohort.isin(CORE) & labels.include_primary & labels.geometry_type.eq("Point")]
    for row in rows.itertuples():
        for radius in RADII_M:
            yield row.country_iso3, row.cohort, {
                "type": "Feature", "geometry": mapping(support_circle(row.lon, row.lat, radius)),
                "properties": {
                    "obs_id": row.obs_id, "season_year": int(row.season_year),
                    "aoi_id": f"{row.obs_id}:proxy_radius_{radius}m",
                    "method": "fixed_radius_sensitivity_support", "radius_m": radius,
                    "status": "unvalidated_proxy_not_field_boundary", "original_longitude": row.lon,
                    "original_latitude": row.lat, "gps_accuracy_m": None,
                    "reported_area_used": False, "source": "frozen label point; radius is an analysis assumption",
                    "location_caveat": ("Provider permits homestead/near-field GPS; acreage may aggregate fields."
                                        if row.cohort == "kenya_oaf_2019_2020" else "GPS accuracy not documented."),
                },
            }


def overlap_metrics(support, field) -> dict:
    """Both geometries must use the same metric CRS; fractions are geometric, not spectral."""
    if support.is_empty or field.is_empty or not support.is_valid or not field.is_valid:
        raise ValueError("Valid nonempty geometries required")
    # Suppress only floating-point area roundoff at exact containment boundaries.
    shared = max(0.0, min(support.intersection(field).area, support.area, field.area))
    union = support.area + field.area - shared
    return {"support_area_m2": support.area, "field_area_m2": field.area,
            "fraction_support_inside_field": shared / support.area,
            "fraction_field_covered": shared / field.area, "intersection_over_union": shared / union}


def validate_proxies(labels: pd.DataFrame) -> pd.DataFrame:
    """Use Malawi polygons to measure buffer contamination under declared synthetic offsets.

    The point is the polygon representative point already stored in labels, not an independent
    GPS survey measurement. Thus zero-offset results are optimistic for Kenya homestead GPS.
    Offsets test sensitivity; they are not estimates of actual positioning error.
    """
    rows = labels.loc[labels.cohort.eq("malawi_2023") & labels.include_primary]
    result = []
    for row in rows.itertuples():
        forward, _, epsg = metric_transforms(row.lon, row.lat)
        field = transform(forward, from_wkt(row.geometry_wkt))
        point = transform(forward, Point(row.lon, row.lat))
        for distance in OFFSETS_M:
            for bearing in ((0,) if distance == 0 else (0, 90, 180, 270)):
                radians = math.radians(bearing)
                shifted = Point(point.x + distance * math.sin(radians), point.y + distance * math.cos(radians))
                for radius in RADII_M:
                    support = shifted.buffer(radius, quad_segs=8)
                    result.append({"obs_id": row.obs_id, "radius_m": radius, "synthetic_offset_m": distance,
                                   "bearing_degrees": bearing, "metric_epsg": epsg,
                                   "shifted_point_inside_field": bool(field.covers(shifted)),
                                   **overlap_metrics(support, field)})
    return pd.DataFrame(result)


def summarize_validation(metrics: pd.DataFrame) -> list[dict]:
    """Equal field weighting within each radius/offset; average four directions first."""
    columns = ["fraction_support_inside_field", "fraction_field_covered", "intersection_over_union",
               "shifted_point_inside_field"]
    per_field = metrics.groupby(["obs_id", "radius_m", "synthetic_offset_m"])[columns].mean().reset_index()
    result = []
    for (radius, distance), rows in per_field.groupby(["radius_m", "synthetic_offset_m"]):
        result.append({"radius_m": int(radius), "synthetic_offset_m": int(distance), "fields": len(rows),
                       **{f"median_{col}": float(rows[col].median()) for col in columns[:3]},
                       "mean_share_directions_point_inside": float(rows.shifted_point_inside_field.mean())})
    return result
