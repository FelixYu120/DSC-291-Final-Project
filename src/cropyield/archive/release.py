"""Step 4 of the pass archive: put the staged tables into one portable DuckDB file.

The file holds its own data: no Parquet beside it, no absolute path, no credentials, no network. It is written
next to the old databases and never changes them.

Build:            python -m cropyield.archive.release build
Add a split:      python -m cropyield.archive.release register-split --name team/<you>/<label> --csv my_split.csv
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from cropyield import ROOT
from cropyield.archive import RELEASE, paths

BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12"]
QUALITY = ["SCL", "CLD", "SNW", "AOT", "WVP"]
ALL = BANDS + QUALITY

TABLES = {
    "source_files": "One row per original provider file: path, SHA-256, licence, rows in scope.",
    "source_records": "One row per original survey row of Kenya, Malawi and Zimbabwe (all crops, all years). "
                      "payload_json holds every original column. Key: source_observation_id.",
    "fields": "One row per field-season (one crop on one field in one season). Key: field_season_id (text) and "
              "fs_key (integer). Location, location quality, harvest year, old-pipeline flags, fold0_reserved.",
    "field_source_crosswalk": "Which source rows belong to which field-season. A curated One Acre Fund row that "
                              "matches exactly one full-workbook row shares its field-season.",
    "locations": "One row per distinct usable sampling geometry (point or polygon). Key: location_id / loc_key.",
    "labels": "One row per field-season: raw yield, raw unit, kg/ha, conversion, protocol and label_status "
              "(measured_positive, recorded_zero, verified_crop_failure, not_answered, not_measured).",
    "label_measurements": "Every single measurement a source gives: per-box weights, wet and dry weights, the "
                          "yield in each unit, nested cuts.",
    "splits": "One row per field-season and named split, with fold. Frozen splits are imported unchanged.",
    "split_specs": "One row per named split: version, source file, SHA-256, frozen or not.",
    "tiles": "The fixed pixel grid of every Sentinel-2 tile that holds a location.",
    "location_tiles": "Every tile whose square holds a location, with the native pixel row/column at 10, 20, 60 m.",
    "footprint_pixels": "The native pixels of each location in each tile grid. Polygons: every pixel near the "
                        "outline with center_inside and area_fraction, so the edge rule can be changed.",
    "acquisitions": "One row per physical overflight (datatake) of a satellite.",
    "granules": "One row per overflight and tile. Key: granule_id / granule_key. Sensing time in UTC.",
    "scenes": "One row per processed product version (level, baseline) of a granule. Key: scene_id (the ESA "
              "product name) / scene_key. in_cdse says the Copernicus catalogue lists it.",
    "scene_items": "The public cloud copies of a scene that can be read without an account (Earth Search), with "
                   "the asset links and dn_add_offset.",
    "catalog_queries": "The catalogue requests that were made: provider, tile, year, items, time, status.",
    "passes": "One row per field-season and granule in its two windows (harvest year = current, year before = "
              "previous). Every catalogued pass is here, cloudy or not, sampled or not (sample_status).",
    "pass_samples": "The measured values, once per location and scene: one column per band (digital numbers as "
                    "published) and per quality layer. Point: the native pixel. Polygon: the default summary.",
    "pixel_samples": "Polygons only: every native pixel that was read (long form), for your own mask and mean.",
    "coverage_months": "One row per field-season, window and calendar month (24 per dated field-season), with "
                       "pass counts and month_status. A month without a pass is a row, not a gap.",
    "source_reconciliation": "Source rows, field-seasons, usable locations and labels by dataset, country, crop "
                             "and year, beside the old pipeline's label count.",
    "field_xy": "X and y with one row per field-season: the field, its yield, and passes = the list of all its "
                "passes in time order, each with all band values (empty where not read yet). Open the list with "
                "unnest(passes, recursive := true).",
    "build_info": "When and from which commit the file was built, and its sample coverage.",
}


def q(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def build() -> Path:
    survey, catalog, samples = (paths.staging_dir(part) for part in ("survey", "catalog", "samples"))
    target = paths.team_database()
    target.parent.mkdir(parents=True, exist_ok=True)
    work = target.with_suffix(".building")
    for leftover in (work, Path(str(work) + ".wal")):
        if leftover.exists():
            leftover.unlink()
    con = duckdb.connect(str(work))
    con.execute("set memory_limit = '6GB'")
    con.execute("set threads = 6")
    run = con.execute

    def staged(folder: Path, name: str) -> str:
        """The staged table; with its ``_pc`` twin (the second public image source) when that file exists."""
        files = [folder / f"{name}.parquet", folder / f"{name}_pc.parquet"]
        listed = ", ".join(f"'{q(file)}'" for file in files if file.exists())
        return f"read_parquet([{listed}], union_by_name = true)"

    # ------------------------------------------------------------------------------------------ survey side
    run(f"create table source_files as select * from {staged(survey, 'source_files')}")
    run(f"create table locations as select cast(row_number() over (order by location_id) as integer) loc_key, * "
        f"from {staged(survey, 'locations')}")
    run(f"""create table fields as
            select cast(row_number() over (order by f.field_season_id) as integer) fs_key, f.*, l.loc_key
            from {staged(survey, 'fields')} f left join locations l using (location_id)""")
    run(f"create table source_records as select * from {staged(survey, 'source_records')}")
    run(f"create table field_source_crosswalk as select * from {staged(survey, 'field_source_crosswalk')}")
    run(f"create table labels as select f.fs_key, l.* from {staged(survey, 'labels')} l join fields f using (field_season_id)")
    run(f"create table label_measurements as select * from {staged(survey, 'label_measurements')}")
    run(f"create table splits as select f.fs_key, s.* from {staged(survey, 'splits')} s join fields f using (field_season_id)")
    run(f"create table split_specs as select * from {staged(survey, 'split_specs')}")

    # --------------------------------------------------------------------------------------- satellite side
    run(f"create table tiles as select * from {staged(catalog, 'tiles')}")
    run(f"create table location_tiles as select l.loc_key, t.* from {staged(catalog, 'location_tiles')} t "
        f"join locations l using (location_id)")
    run(f"create table granules as select cast(row_number() over (order by granule_id) as integer) granule_key, "
        f"* exclude (sensing_time), cast(sensing_time at time zone 'UTC' as timestamp) as sensing_time_utc "
        f"from {staged(catalog, 'granules')}")
    run("""create table acquisitions as
           select acquisition_id, any_value(platform) platform, any_value(relative_orbit) relative_orbit,
                  min(sensing_time_utc) first_sensing_time_utc, count(*) n_granules_listed
           from granules group by acquisition_id""")
    run(f"""create table scenes as
            select cast(row_number() over (order by s.scene_id) as integer) scene_key, g.granule_key,
                   s.* exclude (sensing_time), cast(s.sensing_time at time zone 'UTC' as timestamp) as sensing_time_utc
            from {staged(catalog, 'scenes')} s join granules g using (granule_id)""")
    run(f"create table scene_items as select s.scene_key, i.* from {staged(catalog, 'scene_items')} i "
        f"join scenes s using (scene_id)")
    run(f"create table catalog_queries as select * from {staged(catalog, 'catalog_queries')}")

    pixel_file = samples / "footprint_pixels.parquet"
    if pixel_file.exists():
        run(f"""create table footprint_pixels as
                with p as (select l.loc_key, x.* exclude (location_id) from read_parquet('{q(pixel_file)}') x
                           join locations l using (location_id)),
                best as (select loc_key, mgrs_tile, res_m, bool_or(center_inside) any_inside, max(area_fraction) top
                         from p group by all)
                select p.*, (p.is_point_pixel or p.center_inside or (not b.any_inside and p.area_fraction = b.top))
                            as in_default_summary
                from p join best b using (loc_key, mgrs_tile, res_m)""")
    else:
        run("""create table footprint_pixels (loc_key integer, mgrs_tile varchar, res_m bigint, px_row bigint,
               px_col bigint, center_inside boolean, area_fraction double, is_point_pixel boolean,
               in_default_summary boolean)""")

    # ------------------------------------------------------------------------------------------- samples
    value_columns = ", ".join(f"{name.lower()} double" for name in ALL)
    run(f"""create table pass_samples (loc_key integer, scene_key integer, granule_key integer, item_id varchar,
            read_route varchar, n_pixels integer, {value_columns})""")
    run("""create table pixel_samples (loc_key integer, scene_key integer, res_m smallint, px_row integer,
           px_col integer, band varchar, dn integer)""")
    shards = samples / "shards"
    picks = ", ".join(
        (f"avg(r.dn) filter (where r.band = '{name}' and f.in_default_summary) as {name.lower()}" if name != "SCL"
         else "mode(r.dn) filter (where r.band = 'SCL' and f.in_default_summary) as scl") for name in ALL)
    # one image block at a time: the rows of all blocks together do not fit in memory at full size
    for folder in (sorted(path for path in shards.glob("*/*") if path.is_dir()) if shards.exists() else []):
        if not any(folder.glob("*.parquet")):
            continue
        run(f"""create temp table raw as
                select l.loc_key, l.geometry_type, s.scene_key, s.granule_key, s.mgrs_tile, p.item_id,
                       cast(p.res_m as smallint) res_m, cast(p.px_row as integer) px_row,
                       cast(p.px_col as integer) px_col, p.band, cast(p.dn as integer) dn
                from read_parquet('{q(folder)}/*.parquet') p
                join locations l using (location_id) join scenes s using (scene_id)""")
        run(f"""insert into pass_samples
                select r.loc_key, r.scene_key, r.granule_key, r.item_id, 'direct_cog_all_bands',
                       cast(count(*) filter (where r.band = 'B04' and f.in_default_summary) as integer), {picks}
                from raw r join footprint_pixels f using (loc_key, mgrs_tile, res_m, px_row, px_col)
                group by r.loc_key, r.scene_key, r.granule_key, r.item_id""")
        run("""insert into pixel_samples select loc_key, scene_key, res_m, px_row, px_col, band, dn from raw
               where geometry_type = 'polygon'""")
        run("drop table raw")

    # Band values the old pipeline already holds, where they are the exact native pixel: point fields, the four
    # 10 m bands, a Collection 1 scene in the UTM zone of the chip. DN = reflectance x 10000 + 1000.
    old = paths.data_dir() / "v2" / "cropyield.duckdb"
    reused = 0
    if old.exists():
        run(f"attach '{q(old)}' as old (read_only)")
        run("""insert into pass_samples (loc_key, scene_key, granule_key, item_id, read_route, n_pixels, b02, b03, b04, b08)
               select f.loc_key, s.scene_key, s.granule_key, o.item_id, 'reused_v2_chip_10m_bands', 1,
                      any_value(round(m.b02 * 10000) + 1000), any_value(round(m.b03 * 10000) + 1000),
                      any_value(round(m.b04 * 10000) + 1000), any_value(round(m.b08 * 10000) + 1000)
               from old.scenes o
               join old.monthly_bands m using (obs_id, month)
               join old.downloads d using (obs_id)
               join fields f on f.primary_source_observation_id = o.obs_id
               join scene_items i on i.item_id = o.item_id and i.collection = 'sentinel-2-c1-l2a'
               join scenes s on s.scene_key = i.scene_key
               where d.aoi_type = 'point_pixel' and not m.missing and f.loc_key is not null
                 and substr(o.item_id, 6, 2) = right(d.crs, 2)
                 and not exists (select 1 from pass_samples p where p.loc_key = f.loc_key and p.scene_key = s.scene_key)
               group by f.loc_key, s.scene_key, s.granule_key, o.item_id""")
        reused = con.execute("select count(*) from pass_samples where read_route like 'reused%'").fetchone()[0]
        run("detach old")

    # --------------------------------------------------------------------------------------------- passes
    run(f"""create table passes as
            with listed as (
                select f.fs_key, f.loc_key, g.granule_key, g.acquisition_id, g.mgrs_tile,
                       case when g.year = f.harvest_year then 'current' else 'previous' end window_kind,
                       g.sensing_time_utc, g.year, g.month, e.in_catalogue_footprint
                from fields f
                join {staged(catalog, 'location_granules')} e on e.location_id = f.location_id
                join granules g using (granule_id)
                where g.year in (f.harvest_year, f.harvest_year - 1)),
            products as (
                select granule_key, count(*) filter (where level = 'L2A') n_l2a_products,
                       count(*) filter (where level = 'L1C') n_l1c_products,
                       coalesce(avg(cloud_cover_percent) filter (where level = 'L2A' and in_cdse),
                                avg(cloud_cover_percent) filter (where level = 'L2A')) cloud_cover_percent,
                       bool_or(scene_key in (select scene_key from scene_items where assets_json <> '{{}}')) has_public_cog
                from scenes group by granule_key),
            measured as (
                select loc_key, granule_key, min(read_route) read_route,
                       bool_and(coalesce(b02, 0) = 0 and coalesce(b04, 0) = 0 and coalesce(b08, 0) = 0) all_nodata
                from pass_samples group by loc_key, granule_key)
            select l.*, p.n_l2a_products, p.n_l1c_products, p.cloud_cover_percent, m.read_route,
                   case when m.read_route is not null and m.all_nodata then 'sampled_nodata'
                        when m.read_route = 'direct_cog_all_bands' then 'sampled_all_bands'
                        when m.read_route is not null then 'sampled_10m_bands'
                        when l.in_catalogue_footprint = false then 'outside_swath_per_catalogue'
                        when not p.has_public_cog then 'not_sampled_no_public_file'
                        else 'not_sampled_yet' end as sample_status
            from listed l join products p using (granule_key) left join measured m using (loc_key, granule_key)""")

    run("""create table coverage_months as
           with cells as (
               select f.fs_key, f.loc_key, w.window_kind, cast(f.harvest_year + w.shift as integer) as year, m.month
               from fields f, (values ('current', 0), ('previous', -1)) w(window_kind, shift), range(1, 13) m(month)
               where f.harvest_year is not null),
           failed as (
               select distinct t.loc_key, c.year from catalog_queries c join location_tiles t using (mgrs_tile)
               where c.provider = 'cdse' and c.status <> 'ok'),
           counted as (
               select fs_key, window_kind, year, month, count(*) n_passes,
                      count(distinct acquisition_id) n_overflights,
                      count(*) filter (where sample_status = 'outside_swath_per_catalogue') n_outside_swath_per_catalogue,
                      count(*) filter (where sample_status = 'sampled_all_bands') n_sampled_all_bands,
                      count(*) filter (where sample_status = 'sampled_10m_bands') n_sampled_10m_bands,
                      count(*) filter (where sample_status = 'sampled_nodata') n_sampled_nodata,
                      count(*) filter (where sample_status like 'not_sampled%') n_not_sampled
               from passes group by all)
           select c.fs_key, c.window_kind, c.year, c.month,
                  coalesce(n.n_passes, 0) n_passes, coalesce(n.n_overflights, 0) n_overflights,
                  coalesce(n.n_outside_swath_per_catalogue, 0) n_outside_swath_per_catalogue,
                  coalesce(n.n_sampled_all_bands, 0) n_sampled_all_bands,
                  coalesce(n.n_sampled_10m_bands, 0) n_sampled_10m_bands,
                  coalesce(n.n_sampled_nodata, 0) n_sampled_nodata, coalesce(n.n_not_sampled, 0) n_not_sampled,
                  case when c.loc_key is null then 'unusable_location'
                       when make_date(c.year, c.month, 1) + interval 1 month <= date '2015-06-27' then 'pre_mission'
                       when x.loc_key is not null then 'catalogue_error'
                       when coalesce(n.n_passes, 0) = 0 then 'catalogue_zero'
                       when n.n_not_sampled = 0 then 'complete'
                       when n.n_sampled_all_bands + n.n_sampled_10m_bands + n.n_sampled_nodata > 0 then 'partly_sampled'
                       else 'listed_not_sampled' end as month_status
           from cells c left join counted n using (fs_key, window_kind, year, month)
           left join failed x on x.loc_key = c.loc_key and x.year = c.year""")

    run("""create table source_reconciliation as
            with r as (select dataset, country_iso3, crop, harvest_year, count(*) source_rows
                       from source_records group by all),
            f as (select f.dataset, f.country_iso3, f.crop, f.harvest_year, count(*) field_seasons,
                         count(*) filter (where f.usable_at_field_scale) usable_locations,
                         count(*) filter (where l.label_status = 'measured_positive') measured_positive,
                         count(*) filter (where l.label_status = 'recorded_zero') recorded_zero,
                         count(*) filter (where l.label_status = 'verified_crop_failure') verified_crop_failure,
                         count(*) filter (where l.label_status in ('not_answered', 'not_measured')) no_yield,
                         count(*) filter (where f.legacy_cohort is not null) in_old_labels
                  from fields f join labels l using (fs_key) group by all)
            select r.*, coalesce(f.field_seasons, 0) field_seasons_with_this_primary_source,
                   f.usable_locations, f.measured_positive, f.recorded_zero, f.verified_crop_failure, f.no_yield,
                   f.in_old_labels
            from r left join f using (dataset, country_iso3, crop, harvest_year)
            order by 1, 2, 3, 4""")

    # ---------------------------------------------------------------------------------------------- views
    wide = ", ".join(f"x.{name.lower()}" for name in ALL)
    run(f"""create view pass_bands_wide as
            select f.field_season_id, p.fs_key, p.window_kind, g.granule_id, p.acquisition_id, s.scene_id, s.level,
                   s.processing_baseline, p.sensing_time_utc, p.year, p.month, p.mgrs_tile, s.cloud_cover_percent
                   as scene_cloud_cover_percent, p.sample_status, x.read_route, x.item_id, i.dn_add_offset,
                   x.n_pixels, {wide}
            from passes p join fields f using (fs_key) join granules g using (granule_key)
            join pass_samples x on x.loc_key = p.loc_key and x.granule_key = p.granule_key
            join scenes s on s.scene_key = x.scene_key
            left join (select item_id, any_value(dn_add_offset) dn_add_offset from scene_items group by item_id) i
                   on i.item_id = x.item_id""")
    run(f"""create view pass_bands_long as
            select field_season_id, fs_key, window_kind, granule_id, acquisition_id, scene_id, level, sensing_time_utc,
                   year, month, read_route, dn_add_offset, upper(band) as band, value as dn,
                   case when upper(band) in ({", ".join(repr(name) for name in BANDS)}) then 'spectral DN'
                        else 'quality layer' end as kind
            from pass_bands_wide unpivot (value for band in ({", ".join(name.lower() for name in ALL)}))""")
    reflect = ", ".join(f"case when {name.lower()} > 0 then ({name.lower()} + dn_add_offset) / 10000.0 end as {name.lower()}"
                        for name in BANDS)
    run(f"""create view v_reflectance as
            select field_season_id, fs_key, window_kind, granule_id, acquisition_id, scene_id, sensing_time_utc, year,
                   month, read_route, scene_cloud_cover_percent, scl, cld, snw, {reflect}
            from pass_bands_wide""")
    run("""create view v_ndvi_v1 as
           select field_season_id, fs_key, window_kind, scene_id, sensing_time_utc, year, month, scl, cld,
                  case when b08 + b04 > 0 then (b08 - b04) / (b08 + b04) end as ndvi
           from v_reflectance where b08 is not null and b04 is not null""")
    run("""create view v_gcvi_v1 as
           select field_season_id, fs_key, window_kind, scene_id, sensing_time_utc, year, month, scl, cld,
                  case when b03 > 0 then b08 / b03 - 1 end as gcvi
           from v_reflectance where b08 is not null and b03 is not null""")
    run("""create view v_overflights as
           select f.field_season_id, p.fs_key, p.window_kind, p.year, p.month, p.acquisition_id,
                  min(p.sensing_time_utc) sensing_time_utc, count(*) n_tiles, max(p.n_l2a_products) n_l2a_products,
                  max(p.n_l1c_products) n_l1c_products
           from passes p join fields f using (fs_key) group by all""")
    run("""create view split_membership_full as
           select f.field_season_id, f.fs_key, c.split_name, s.fold, s.repeat, s.fold is not null as assigned
           from fields f cross join split_specs c left join splits s on s.fs_key = f.fs_key and s.split_name = c.split_name""")
    # Everything in one table: one row per field-season and pass. A pass without values has empty band columns; a
    # field-season without any pass (no usable location) is one row with empty pass columns. Nothing is left out.
    run(f"""create view master as
            with best as (select * from pass_samples
                          qualify row_number() over (partition by loc_key, granule_key order by read_route, scene_key) = 1)
            select f.field_season_id, f.dataset, f.primary_source_observation_id as source_observation_id,
                   f.country_iso3, f.crop, f.harvest_year, f.planting_date, f.harvest_date, f.survey_date, f.admin_unit,
                   f.site_unit, f.intercropped, f.irrigated, f.geometry_type, f.latitude, f.longitude,
                   f.location_quality, f.usable_at_field_scale, f.legacy_cohort, f.fold0_reserved,
                   l.label_status, l.yield_raw, l.yield_raw_unit, l.yield_kg_ha, l.zero_evidence,
                   p.window_kind, p.year, p.month, p.sensing_time_utc, p.mgrs_tile, p.acquisition_id, g.granule_id,
                   p.in_catalogue_footprint, p.n_l2a_products, p.n_l1c_products, p.sample_status,
                   s.scene_id, s.processing_baseline,
                   coalesce(s.cloud_cover_percent, p.cloud_cover_percent) as scene_cloud_cover_percent,
                   x.read_route, x.item_id, i.dn_add_offset, x.n_pixels, {wide},
                   r.payload_json as source_row_json
            from fields f join labels l using (fs_key)
            left join passes p using (fs_key)
            left join granules g on g.granule_key = p.granule_key
            left join best x on x.loc_key = p.loc_key and x.granule_key = p.granule_key
            left join scenes s on s.scene_key = x.scene_key
            left join (select item_id, any_value(dn_add_offset) dn_add_offset from scene_items group by item_id) i
                   on i.item_id = x.item_id
            left join source_records r on r.source_observation_id = f.primary_source_observation_id""")
    # X and y with one row per field-season: the yield, and the list of all its passes with all bands, in time
    # order. Stored as a table (the lists are built once here, not at every query).
    struct = ", ".join([
        "'sensing_time_utc': p.sensing_time_utc", "'window_kind': p.window_kind", "'year': p.year", "'month': p.month",
        "'mgrs_tile': p.mgrs_tile", "'acquisition_id': p.acquisition_id", "'sample_status': p.sample_status",
        "'scene_cloud_cover_percent': cast(coalesce(s.cloud_cover_percent, p.cloud_cover_percent) as float)",
        "'dn_add_offset': cast(i.dn_add_offset as float)", *(f"'{band.lower()}': cast(x.{band.lower()} as float)" for band in ALL)])
    run("""create temp table best as select * from pass_samples
           qualify row_number() over (partition by loc_key, granule_key order by read_route, scene_key) = 1""")
    run("create temp table offsets as select item_id, any_value(dn_add_offset) dn_add_offset from scene_items group by item_id")
    chunk = f"""select f.field_season_id, f.dataset, f.primary_source_observation_id as source_observation_id,
                       f.country_iso3, f.crop, f.harvest_year, f.latitude, f.longitude, f.geometry_type,
                       f.location_quality, f.usable_at_field_scale, f.legacy_cohort, f.fold0_reserved, l.label_status,
                       l.yield_raw, l.yield_raw_unit, l.yield_kg_ha, cast(coalesce(k.n_passes, 0) as integer) as n_passes,
                       cast(coalesce(k.n_passes_all_bands, 0) as integer) as n_passes_all_bands, k.passes
                from fields f join labels l using (fs_key)
                left join (
                    select p.fs_key, count(*) as n_passes,
                           count(*) filter (where p.sample_status = 'sampled_all_bands') as n_passes_all_bands,
                           list({{{struct}}} order by p.sensing_time_utc) as passes
                    from passes p
                    left join best x on x.loc_key = p.loc_key and x.granule_key = p.granule_key
                    left join scenes s on s.scene_key = x.scene_key
                    left join offsets i on i.item_id = x.item_id
                    where p.fs_key >= ? and p.fs_key < ?
                    group by p.fs_key) k using (fs_key)
                where f.fs_key >= ? and f.fs_key < ?
                order by f.fs_key"""
    # in pieces of 1,000 field-seasons: the lists of all 8 million passes at once do not fit in memory.
    # fs_key follows field_season_id, so the table is in field_season_id order.
    last = con.execute("select coalesce(max(fs_key), 0) from fields").fetchone()[0]
    for number, first in enumerate(range(1, last + 1, 1000)):
        bounds = [first, first + 1000, first, first + 1000]
        run(("create table field_xy as " if number == 0 else "insert into field_xy ") + chunk, bounds)
    run("drop table best")
    run("drop table offsets")

    # ----------------------------------------------------------------------------------------- build info
    counts = {name: con.execute(f'select count(*) from "{name}"').fetchone()[0] for name in TABLES if name != "build_info"}
    status = dict(con.execute("select sample_status, count(*) from passes group by 1").fetchall())
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    info = {"release": RELEASE, "built_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "git_commit": commit, "duckdb_version": duckdb.__version__, "row_counts": counts,
            "passes_by_sample_status": status, "reused_10m_samples": reused}
    run("create table build_info as select ? as release, ? as built_at_utc, ? as git_commit, ? as details_json",
        [RELEASE, info["built_at_utc"], commit, json.dumps(info)])
    for name, text in TABLES.items():
        run(f"comment on table \"{name}\" is '{text.replace(chr(39), chr(39) * 2)}'")
    run("checkpoint")
    con.close()
    if target.exists():
        target.unlink()
    work.replace(target)
    write_documents(target, info)
    return target


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def write_documents(database: Path, info: dict) -> None:
    """README, dictionary, manifest and checksum beside the database."""
    con = duckdb.connect(str(database), read_only=True)
    columns = con.execute("""select table_name, column_name, data_type from information_schema.columns
                             where table_schema = 'main' order by table_name, ordinal_position""").fetchall()
    views = [row[0] for row in con.execute("select view_name from duckdb_views() where not internal order by 1").fetchall()]
    files = con.execute("select dataset, title, licence, path, sha256_or_id, rows_in_scope from "
                        "(select dataset, title, licence, path, source_file_id as sha256_or_id, rows_in_scope from source_files)").fetchall()
    con.close()
    folder = database.parent
    lines = [f"# Dictionary of {database.name}", "", "Tables and views, with every column and its type.", ""]
    for name in sorted({row[0] for row in columns}):
        kind = "view" if name in views else "table"
        lines += [f"## {name} ({kind})", "", TABLES.get(name, VIEW_NOTES.get(name, "")), "", "| column | type |", "|---|---|"]
        lines += [f"| `{column}` | {dtype} |" for table, column, dtype in columns if table == name]
        lines.append("")
    (folder / "DICTIONARY.md").write_text("\n".join(lines), encoding="utf-8")

    digest = sha256(database)
    info = dict(info, file=database.name, bytes=database.stat().st_size, sha256=digest,
                source_files=[dict(zip(("dataset", "title", "licence", "path", "sha256", "rows_in_scope"), row)) for row in files])
    (folder / "manifest.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    (folder / "SHA256SUMS").write_text(f"{digest}  {database.name}\n", encoding="utf-8")
    status = info["passes_by_sample_status"]
    total = sum(status.values()) or 1
    rows = "\n".join(f"| `{key}` | {value:,} | {100 * value / total:.1f} % |" for key, value in sorted(status.items()))
    sources = "\n".join(f"- {title} ({licence}); `{path}`, {rows_in:,} rows in scope." for _, title, licence, path, _, rows_in in files)
    (folder / "README.md").write_text(README.format(
        name=database.name, built=info["built_at_utc"], size=database.stat().st_size / 1e6, sha=digest,
        source_rows=info["row_counts"]["source_records"], fields=info["row_counts"]["fields"],
        locations=info["row_counts"]["locations"], passes=info["row_counts"]["passes"],
        scenes=info["row_counts"]["scenes"], status_rows=rows, sources=sources,
        progress=download_progress()), encoding="utf-8")


def download_progress() -> str:
    """A README table: image blocks read and planned for each country-year step of the download."""
    from cropyield.archive import (
        sampling,  # imported here: the builder itself needs no raster library
    )
    if not (paths.staging_dir("samples") / "plan.parquet").exists():
        return ""
    lines = ["", "Download progress by country-year, in read order (image blocks read / planned):", "",
             "| step | country-year | read | planned | complete |", "|---|---|---|---|---|"]
    lines += [f"| {row['step']} | {row['name']} | {row['read']:,} | {row['units']:,} | {'yes' if row['complete'] else 'no'} |"
              for row in sampling.progress_by_step()]
    return chr(10).join(lines) + chr(10)


VIEW_NOTES = {
    "pass_bands_wide": "One row per field-season and measured scene, bands side by side (digital numbers).",
    "pass_bands_long": "The same, one row per band.",
    "v_reflectance": "Reflectance = (DN + dn_add_offset) / 10000 for the spectral bands; DN 0 (no data) gives NULL.",
    "v_ndvi_v1": "NDVI version 1 = (B08 - B04) / (B08 + B04) from v_reflectance; NULL when the sum is not above 0.",
    "v_gcvi_v1": "Green chlorophyll index version 1 = B08 / B03 - 1 from v_reflectance; NULL when B03 is not above 0.",
    "v_overflights": "One row per field-season and physical overflight. Use it to count passes: two tiles or two "
                     "product levels of one overflight count once.",
    "split_membership_full": "Every field-season beside every named split; assigned = false where it has no fold.",
    "master": "Everything in one table: one row per field-season and pass, with the survey facts, the yield, the "
              "pass and all band values (empty where not read yet), and the original survey row as JSON. A "
              "field-season without a usable location is one row with empty pass columns.",
}

README = """# Pass archive v1 (`{name}`)

What the surveys reported and what Sentinel-2 observed, for Kenya, Malawi and Zimbabwe. No cloud mask, no
monthly rule and no split is applied: each person chooses these later. Built {built} (UTC).

- File: `{name}`, {size:.0f} MB. SHA-256: `{sha}` (also in `SHA256SUMS`).
- The file is not in Git (too large). Get it from the team and put it in this folder,
  `data/passarchive_v1/release/`; see `docs/DATA_SETUP.md`.
- It opens with DuckDB alone: no other file, no Internet, no account.
- Columns: `DICTIONARY.md`. Build record: `manifest.json`.

## What is inside

| | rows |
|---|---|
| original survey rows (`source_records`) | {source_rows:,} |
| field-seasons (`fields`) | {fields:,} |
| usable locations (`locations`) | {locations:,} |
| Sentinel-2 product versions listed (`scenes`) | {scenes:,} |
| field-season passes listed (`passes`) | {passes:,} |

Every pass that the catalogue lists for the harvest year (`current`) and the year before (`previous`) is in
`passes`, cloudy or not. Band values are in `pass_samples` for the passes that were read:

| `passes.sample_status` | passes | share |
|---|---|---|
{status_rows}

`sampled_all_bands` = all Level-2A bands and quality layers read from the public file at the native pixel.
`sampled_10m_bands` = B02, B03, B04, B08 taken from the old chips (exact native pixel; only the scenes the old
pipeline kept, which were clear at the field). `sampled_nodata` = read, and the pixel holds no data.
`outside_swath_per_catalogue` = the tile holds the field but the catalogue footprint says the sensor did not
see it on that pass (not read). `not_sampled_yet` = listed, values not downloaded yet.
`not_sampled_no_public_file` = listed, but no copy exists that can be read without an account.
All times are UTC (`sensing_time_utc`); `year` and `month` are UTC too.
{progress}

## Start here

```sql
-- everything in one table: one row per field-season and pass (survey facts, yield, pass, all bands)
select * from master where field_season_id = '<id>' order by sensing_time_utc;
-- X and y, one row per field: the yield, and the list of all passes with all bands
select field_season_id, yield_kg_ha, n_passes, passes from field_xy where legacy_cohort = 'malawi_2023';
-- every pass of one field in one month, with the bands that were read
select * from passes join fields using (fs_key) where field_season_id = '<id>' and year = 2023 and month = 3;
select * from pass_bands_wide where field_season_id = '<id>' and year = 2023 and month = 3;
-- all 24 months, also the empty ones
select * from coverage_months join fields using (fs_key) where field_season_id = '<id>' order by year, month;
-- labels with a named split
select f.field_season_id, l.yield_kg_ha, s.fold from fields f join labels l using (fs_key)
join splits s using (fs_key) where s.split_name = 'frozen/v2/zimbabwe_lacuna_2022_2023/s1_cc2km';
```

Units: band columns are digital numbers as published. Use `v_reflectance` (it applies `dn_add_offset` once),
or `v_ndvi_v1` / `v_gcvi_v1`. To use another formula or another cloud rule, write your own view on
`pass_bands_wide`; `scl` is the scene classification (4 vegetation, 5 bare, 8-10 cloud, 3 shadow).

## Things to know

- Level-1C products are listed in `scenes` but their pixels are not read in this release.
- For 2015 and 2016 Earth Search has no file. Those passes are read from Planetary Computer where it has one
  (`scene_items.provider`); its aerosol and water-vapour layers are the 10 m ones. The rest are listed only.
- The download reads one country-year after the other (table above), each completely before the next; inside
  a country-year the main growing season comes first (`sampling.plan`).
- `fields.fold0_reserved` marks the field-seasons in fold 0 of a frozen `s1_cc2km` split. The project rule keeps
  fold 0 out of development. Their labels are in this file, as in the older team databases: do not train on them.
- One Acre Fund has two releases. A curated row that matches exactly one full-workbook row shares its
  field-season (`field_source_crosswalk`). The curated yields were published 2.2 % too low (factor 2.41705
  instead of 2.47105); `labels.yield_kg_ha` is corrected and `yield_raw` is the published number.
- A zero yield is not always a real zero: read `labels.label_status` and `labels.zero_evidence`.
- Curated One Acre Fund points are rounded and shifted by the provider (about 160 m): not usable at field scale.
- Malawi 2022 polygons were converted from Arc 1950 with datum operation EPSG:1113 (as in data v2).
- New split: `python -m cropyield.archive.release register-split --name team/<you>/<label> --csv file.csv`
  (columns `field_season_id`, `fold`). Frozen splits cannot be overwritten.
- To use the data you need only the `.duckdb` file. To build it again from the public sources (many hours of
  download), run the four steps named in `src/cropyield/archive/__init__.py`; finished blocks are skipped.

## Sources and attribution

{sources}
- Contains modified Copernicus Sentinel data (European Space Agency). Catalogue: Copernicus Data Space
  Ecosystem. Pixel files: Earth Search by Element 84 (AWS open data).

Keep the provider attribution and the CC BY notices when you share or publish this file.
"""


def register_split(database: Path, name: str, csv: Path) -> int:
    """Add a named split from a CSV (field_season_id, fold[, repeat]). An existing name is never replaced."""
    table = pd.read_csv(csv)
    if not {"field_season_id", "fold"} <= set(table.columns):
        raise SystemExit("the CSV needs the columns field_season_id and fold")
    con = duckdb.connect(str(database))
    if con.execute("select count(*) from split_specs where split_name = ?", [name]).fetchone()[0]:
        raise SystemExit(f"split '{name}' exists already; choose another name")
    if name.startswith("frozen/"):
        raise SystemExit("names that start with frozen/ are reserved")
    known = set(con.execute("select field_season_id from fields").df().field_season_id)
    unknown = set(table.field_season_id) - known
    if unknown or table.field_season_id.duplicated().any():
        raise SystemExit(f"{len(unknown)} unknown and {int(table.field_season_id.duplicated().sum())} repeated field_season_id")
    table["repeat"] = table.get("repeat", 0)
    con.register("incoming", table)
    con.execute("""insert into splits (fs_key, split_name, field_season_id, fold, repeat)
                   select f.fs_key, ?, i.field_season_id, i.fold, i.repeat from incoming i join fields f using (field_season_id)""",
                [name])
    con.execute("""insert into split_specs (split_name, frozen, version, source_file, sha256, rows)
                   values (?, false, 'user', ?, ?, ?)""", [name, csv.name, sha256(csv), len(table)])
    con.close()
    return len(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build")
    add = commands.add_parser("register-split")
    add.add_argument("--name", required=True)
    add.add_argument("--csv", required=True, type=Path)
    add.add_argument("--db", type=Path, default=None)
    arguments = parser.parse_args()
    if arguments.command == "build":
        built = build()
        print(built, f"{built.stat().st_size / 1e6:.0f} MB")
    else:
        print(register_split(arguments.db or paths.team_database(), arguments.name, arguments.csv), "rows added")
