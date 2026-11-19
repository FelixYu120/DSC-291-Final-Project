# Dictionary of passarchive_v1.duckdb

Tables and views, with every column and its type.

## acquisitions (table)

One row per physical overflight (datatake) of a satellite.

| column | type |
|---|---|
| `acquisition_id` | VARCHAR |
| `platform` | VARCHAR |
| `relative_orbit` | BIGINT |
| `first_sensing_time_utc` | TIMESTAMP |
| `n_granules_listed` | BIGINT |

## build_info (table)

When and from which commit the file was built, and its sample coverage.

| column | type |
|---|---|
| `release` | VARCHAR |
| `built_at_utc` | VARCHAR |
| `git_commit` | VARCHAR |
| `details_json` | VARCHAR |

## catalog_queries (table)

The catalogue requests that were made: provider, tile, year, items, time, status.

| column | type |
|---|---|
| `provider` | VARCHAR |
| `mgrs_tile` | VARCHAR |
| `year` | BIGINT |
| `status` | VARCHAR |
| `items` | BIGINT |
| `pages` | BIGINT |
| `fetched_at` | VARCHAR |

## coverage_months (table)

One row per field-season, window and calendar month (24 per dated field-season), with pass counts and month_status. A month without a pass is a row, not a gap.

| column | type |
|---|---|
| `fs_key` | INTEGER |
| `window_kind` | VARCHAR |
| `year` | INTEGER |
| `month` | BIGINT |
| `n_passes` | BIGINT |
| `n_overflights` | BIGINT |
| `n_outside_swath_per_catalogue` | BIGINT |
| `n_sampled_all_bands` | BIGINT |
| `n_sampled_10m_bands` | BIGINT |
| `n_sampled_nodata` | BIGINT |
| `n_not_sampled` | BIGINT |
| `month_status` | VARCHAR |

## field_source_crosswalk (table)

Which source rows belong to which field-season. A curated One Acre Fund row that matches exactly one full-workbook row shares its field-season.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `source_observation_id` | VARCHAR |
| `link_role` | VARCHAR |
| `match_method` | VARCHAR |
| `n_candidates` | BIGINT |

## field_xy (table)

X and y with one row per field-season: the field, its yield, and passes = the list of all its passes in time order, each with all band values (empty where not read yet). Open the list with unnest(passes, recursive := true).

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `dataset` | VARCHAR |
| `source_observation_id` | VARCHAR |
| `country_iso3` | VARCHAR |
| `crop` | VARCHAR |
| `harvest_year` | BIGINT |
| `latitude` | DOUBLE |
| `longitude` | DOUBLE |
| `geometry_type` | VARCHAR |
| `location_quality` | VARCHAR |
| `usable_at_field_scale` | BOOLEAN |
| `legacy_cohort` | VARCHAR |
| `fold0_reserved` | BOOLEAN |
| `label_status` | VARCHAR |
| `yield_raw` | DOUBLE |
| `yield_raw_unit` | VARCHAR |
| `yield_kg_ha` | DOUBLE |
| `n_passes` | INTEGER |
| `n_passes_all_bands` | INTEGER |
| `passes` | STRUCT(sensing_time_utc TIMESTAMP, window_kind VARCHAR, "year" INTEGER, "month" INTEGER, mgrs_tile VARCHAR, acquisition_id VARCHAR, sample_status VARCHAR, scene_cloud_cover_percent FLOAT, dn_add_offset FLOAT, b01 FLOAT, b02 FLOAT, b03 FLOAT, b04 FLOAT, b05 FLOAT, b06 FLOAT, b07 FLOAT, b08 FLOAT, b8a FLOAT, b09 FLOAT, b11 FLOAT, b12 FLOAT, scl FLOAT, cld FLOAT, snw FLOAT, aot FLOAT, wvp FLOAT)[] |

## fields (table)

One row per field-season (one crop on one field in one season). Key: field_season_id (text) and fs_key (integer). Location, location quality, harvest year, old-pipeline flags, fold0_reserved.

| column | type |
|---|---|
| `fs_key` | INTEGER |
| `field_season_id` | VARCHAR |
| `primary_source_observation_id` | VARCHAR |
| `dataset` | VARCHAR |
| `country_iso3` | VARCHAR |
| `crop` | VARCHAR |
| `harvest_year` | BIGINT |
| `year_basis` | VARCHAR |
| `year_inferred` | BOOLEAN |
| `window_status` | VARCHAR |
| `season_raw` | VARCHAR |
| `planting_date` | DATE |
| `harvest_date` | DATE |
| `survey_date` | DATE |
| `survey_date_basis` | VARCHAR |
| `admin_unit` | VARCHAR |
| `site_unit` | VARCHAR |
| `intercropped` | BOOLEAN |
| `irrigated` | BOOLEAN |
| `geometry_type` | VARCHAR |
| `latitude` | DOUBLE |
| `longitude` | DOUBLE |
| `geometry_wkt_wgs84` | VARCHAR |
| `geometry_transformation` | VARCHAR |
| `source_crs` | VARCHAR |
| `source_geometry_wkt` | VARCHAR |
| `polygon_was_invalid` | BOOLEAN |
| `location_quality` | VARCHAR |
| `usable_at_field_scale` | BOOLEAN |
| `unusable_reason` | VARCHAR |
| `location_id` | VARCHAR |
| `identity_status` | VARCHAR |
| `overlap_group_id` | VARCHAR |
| `n_source_records` | BIGINT |
| `legacy_cohort` | VARCHAR |
| `legacy_include_primary` | BOOLEAN |
| `legacy_exclusion_reason` | VARCHAR |
| `fold0_reserved` | BOOLEAN |
| `loc_key` | INTEGER |

## footprint_pixels (table)

The native pixels of each location in each tile grid. Polygons: every pixel near the outline with center_inside and area_fraction, so the edge rule can be changed.

| column | type |
|---|---|
| `loc_key` | INTEGER |
| `mgrs_tile` | VARCHAR |
| `res_m` | BIGINT |
| `px_row` | BIGINT |
| `px_col` | BIGINT |
| `center_inside` | BOOLEAN |
| `area_fraction` | DOUBLE |
| `is_point_pixel` | BOOLEAN |
| `in_default_summary` | BOOLEAN |

## granules (table)

One row per overflight and tile. Key: granule_id / granule_key. Sensing time in UTC.

| column | type |
|---|---|
| `granule_key` | INTEGER |
| `granule_id` | VARCHAR |
| `mgrs_tile` | VARCHAR |
| `acquisition_id` | VARCHAR |
| `platform` | VARCHAR |
| `relative_orbit` | BIGINT |
| `year` | INTEGER |
| `month` | INTEGER |
| `footprint_wkt` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |

## label_measurements (table)

Every single measurement a source gives: per-box weights, wet and dry weights, the yield in each unit, nested cuts.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `source_observation_id` | VARCHAR |
| `measurement` | VARCHAR |
| `cut_number` | DOUBLE |
| `value` | DOUBLE |
| `unit` | VARCHAR |

## labels (table)

One row per field-season: raw yield, raw unit, kg/ha, conversion, protocol and label_status (measured_positive, recorded_zero, verified_crop_failure, not_answered, not_measured).

| column | type |
|---|---|
| `fs_key` | INTEGER |
| `field_season_id` | VARCHAR |
| `source_observation_id` | VARCHAR |
| `crop` | VARCHAR |
| `label_status` | VARCHAR |
| `yield_raw` | DOUBLE |
| `yield_raw_unit` | VARCHAR |
| `yield_kg_ha` | DOUBLE |
| `yield_conversion` | VARCHAR |
| `moisture_basis` | VARCHAR |
| `n_cuts` | BIGINT |
| `cut_area_m2` | DOUBLE |
| `protocol` | VARCHAR |
| `zero_evidence` | VARCHAR |

## location_tiles (table)

Every tile whose square holds a location, with the native pixel row/column at 10, 20, 60 m.

| column | type |
|---|---|
| `loc_key` | INTEGER |
| `location_id` | VARCHAR |
| `mgrs_tile` | VARCHAR |
| `x` | DOUBLE |
| `y` | DOUBLE |
| `row10` | INTEGER |
| `col10` | INTEGER |
| `row20` | INTEGER |
| `col20` | INTEGER |
| `row60` | INTEGER |
| `col60` | INTEGER |

## locations (table)

One row per distinct usable sampling geometry (point or polygon). Key: location_id / loc_key.

| column | type |
|---|---|
| `loc_key` | INTEGER |
| `location_id` | VARCHAR |
| `geometry_type` | VARCHAR |
| `geometry_wkt_wgs84` | VARCHAR |
| `latitude` | DOUBLE |
| `longitude` | DOUBLE |
| `country_iso3` | VARCHAR |
| `n_field_seasons` | BIGINT |

## master (view)

Everything in one table: one row per field-season and pass, with the survey facts, the yield, the pass and all band values (empty where not read yet), and the original survey row as JSON. A field-season without a usable location is one row with empty pass columns.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `dataset` | VARCHAR |
| `source_observation_id` | VARCHAR |
| `country_iso3` | VARCHAR |
| `crop` | VARCHAR |
| `harvest_year` | BIGINT |
| `planting_date` | DATE |
| `harvest_date` | DATE |
| `survey_date` | DATE |
| `admin_unit` | VARCHAR |
| `site_unit` | VARCHAR |
| `intercropped` | BOOLEAN |
| `irrigated` | BOOLEAN |
| `geometry_type` | VARCHAR |
| `latitude` | DOUBLE |
| `longitude` | DOUBLE |
| `location_quality` | VARCHAR |
| `usable_at_field_scale` | BOOLEAN |
| `legacy_cohort` | VARCHAR |
| `fold0_reserved` | BOOLEAN |
| `label_status` | VARCHAR |
| `yield_raw` | DOUBLE |
| `yield_raw_unit` | VARCHAR |
| `yield_kg_ha` | DOUBLE |
| `zero_evidence` | VARCHAR |
| `window_kind` | VARCHAR |
| `year` | INTEGER |
| `month` | INTEGER |
| `sensing_time_utc` | TIMESTAMP |
| `mgrs_tile` | VARCHAR |
| `acquisition_id` | VARCHAR |
| `granule_id` | VARCHAR |
| `in_catalogue_footprint` | BOOLEAN |
| `n_l2a_products` | BIGINT |
| `n_l1c_products` | BIGINT |
| `sample_status` | VARCHAR |
| `scene_id` | VARCHAR |
| `processing_baseline` | VARCHAR |
| `scene_cloud_cover_percent` | DOUBLE |
| `read_route` | VARCHAR |
| `item_id` | VARCHAR |
| `dn_add_offset` | DOUBLE |
| `n_pixels` | INTEGER |
| `b01` | DOUBLE |
| `b02` | DOUBLE |
| `b03` | DOUBLE |
| `b04` | DOUBLE |
| `b05` | DOUBLE |
| `b06` | DOUBLE |
| `b07` | DOUBLE |
| `b08` | DOUBLE |
| `b8a` | DOUBLE |
| `b09` | DOUBLE |
| `b11` | DOUBLE |
| `b12` | DOUBLE |
| `scl` | DOUBLE |
| `cld` | DOUBLE |
| `snw` | DOUBLE |
| `aot` | DOUBLE |
| `wvp` | DOUBLE |
| `source_row_json` | VARCHAR |

## pass_bands_long (view)

The same, one row per band.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `fs_key` | INTEGER |
| `window_kind` | VARCHAR |
| `granule_id` | VARCHAR |
| `acquisition_id` | VARCHAR |
| `scene_id` | VARCHAR |
| `level` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |
| `year` | INTEGER |
| `month` | INTEGER |
| `read_route` | VARCHAR |
| `dn_add_offset` | DOUBLE |
| `band` | VARCHAR |
| `dn` | DOUBLE |
| `kind` | VARCHAR |

## pass_bands_wide (view)

One row per field-season and measured scene, bands side by side (digital numbers).

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `fs_key` | INTEGER |
| `window_kind` | VARCHAR |
| `granule_id` | VARCHAR |
| `acquisition_id` | VARCHAR |
| `scene_id` | VARCHAR |
| `level` | VARCHAR |
| `processing_baseline` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |
| `year` | INTEGER |
| `month` | INTEGER |
| `mgrs_tile` | VARCHAR |
| `scene_cloud_cover_percent` | DOUBLE |
| `sample_status` | VARCHAR |
| `read_route` | VARCHAR |
| `item_id` | VARCHAR |
| `dn_add_offset` | DOUBLE |
| `n_pixels` | INTEGER |
| `b01` | DOUBLE |
| `b02` | DOUBLE |
| `b03` | DOUBLE |
| `b04` | DOUBLE |
| `b05` | DOUBLE |
| `b06` | DOUBLE |
| `b07` | DOUBLE |
| `b08` | DOUBLE |
| `b8a` | DOUBLE |
| `b09` | DOUBLE |
| `b11` | DOUBLE |
| `b12` | DOUBLE |
| `scl` | DOUBLE |
| `cld` | DOUBLE |
| `snw` | DOUBLE |
| `aot` | DOUBLE |
| `wvp` | DOUBLE |

## pass_samples (table)

The measured values, once per location and scene: one column per band (digital numbers as published) and per quality layer. Point: the native pixel. Polygon: the default summary.

| column | type |
|---|---|
| `loc_key` | INTEGER |
| `scene_key` | INTEGER |
| `granule_key` | INTEGER |
| `item_id` | VARCHAR |
| `read_route` | VARCHAR |
| `n_pixels` | INTEGER |
| `b01` | DOUBLE |
| `b02` | DOUBLE |
| `b03` | DOUBLE |
| `b04` | DOUBLE |
| `b05` | DOUBLE |
| `b06` | DOUBLE |
| `b07` | DOUBLE |
| `b08` | DOUBLE |
| `b8a` | DOUBLE |
| `b09` | DOUBLE |
| `b11` | DOUBLE |
| `b12` | DOUBLE |
| `scl` | DOUBLE |
| `cld` | DOUBLE |
| `snw` | DOUBLE |
| `aot` | DOUBLE |
| `wvp` | DOUBLE |

## passes (table)

One row per field-season and granule in its two windows (harvest year = current, year before = previous). Every catalogued pass is here, cloudy or not, sampled or not (sample_status).

| column | type |
|---|---|
| `fs_key` | INTEGER |
| `loc_key` | INTEGER |
| `granule_key` | INTEGER |
| `acquisition_id` | VARCHAR |
| `mgrs_tile` | VARCHAR |
| `window_kind` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |
| `year` | INTEGER |
| `month` | INTEGER |
| `in_catalogue_footprint` | BOOLEAN |
| `n_l2a_products` | BIGINT |
| `n_l1c_products` | BIGINT |
| `cloud_cover_percent` | DOUBLE |
| `read_route` | VARCHAR |
| `sample_status` | VARCHAR |

## pixel_samples (table)

Polygons only: every native pixel that was read (long form), for your own mask and mean.

| column | type |
|---|---|
| `loc_key` | INTEGER |
| `scene_key` | INTEGER |
| `res_m` | SMALLINT |
| `px_row` | INTEGER |
| `px_col` | INTEGER |
| `band` | VARCHAR |
| `dn` | INTEGER |

## scene_items (table)

The public cloud copies of a scene that can be read without an account (Earth Search), with the asset links and dn_add_offset.

| column | type |
|---|---|
| `scene_key` | INTEGER |
| `scene_id` | VARCHAR |
| `provider` | VARCHAR |
| `collection` | VARCHAR |
| `item_id` | VARCHAR |
| `processing_baseline` | VARCHAR |
| `boa_offset_applied` | BOOLEAN |
| `dn_add_offset` | DOUBLE |
| `cloud_cover_percent` | DOUBLE |
| `nodata_percent` | DOUBLE |
| `sun_elevation` | DOUBLE |
| `sun_azimuth` | DOUBLE |
| `assets_json` | VARCHAR |

## scenes (table)

One row per processed product version (level, baseline) of a granule. Key: scene_id (the ESA product name) / scene_key. in_cdse says the Copernicus catalogue lists it.

| column | type |
|---|---|
| `scene_key` | INTEGER |
| `granule_key` | INTEGER |
| `scene_id` | VARCHAR |
| `level` | VARCHAR |
| `platform` | VARCHAR |
| `mgrs_tile` | VARCHAR |
| `acquisition_id` | VARCHAR |
| `granule_id` | VARCHAR |
| `relative_orbit` | BIGINT |
| `processing_baseline` | VARCHAR |
| `cloud_cover_percent` | DOUBLE |
| `absolute_orbit` | BIGINT |
| `footprint_wkt` | VARCHAR |
| `in_cdse` | BOOLEAN |
| `cdse_id` | VARCHAR |
| `year` | BIGINT |
| `month` | BIGINT |
| `sensing_time_utc` | TIMESTAMP |

## source_files (table)

One row per original provider file: path, SHA-256, licence, rows in scope.

| column | type |
|---|---|
| `source_file_id` | VARCHAR |
| `dataset` | VARCHAR |
| `title` | VARCHAR |
| `licence` | VARCHAR |
| `path` | VARCHAR |
| `bytes` | BIGINT |
| `rows_in_scope` | BIGINT |
| `rows_other_countries` | BIGINT |

## source_reconciliation (table)

Source rows, field-seasons, usable locations and labels by dataset, country, crop and year, beside the old pipeline's label count.

| column | type |
|---|---|
| `dataset` | VARCHAR |
| `country_iso3` | VARCHAR |
| `crop` | VARCHAR |
| `harvest_year` | BIGINT |
| `source_rows` | BIGINT |
| `field_seasons_with_this_primary_source` | BIGINT |
| `usable_locations` | BIGINT |
| `measured_positive` | BIGINT |
| `recorded_zero` | BIGINT |
| `verified_crop_failure` | BIGINT |
| `no_yield` | BIGINT |
| `in_old_labels` | BIGINT |

## source_records (table)

One row per original survey row of Kenya, Malawi and Zimbabwe (all crops, all years). payload_json holds every original column. Key: source_observation_id.

| column | type |
|---|---|
| `source_observation_id` | VARCHAR |
| `field_season_id` | VARCHAR |
| `dataset` | VARCHAR |
| `source_file_id` | VARCHAR |
| `provider_record_id` | VARCHAR |
| `provider_id_damaged_by_excel` | BOOLEAN |
| `source_row_number` | BIGINT |
| `country_iso3` | VARCHAR |
| `crop_raw` | VARCHAR |
| `crop` | VARCHAR |
| `harvest_year` | BIGINT |
| `label_status` | VARCHAR |
| `location_quality` | VARCHAR |
| `usable_at_field_scale` | BOOLEAN |
| `payload_json` | VARCHAR |

## split_membership_full (view)

Every field-season beside every named split; assigned = false where it has no fold.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `fs_key` | INTEGER |
| `split_name` | VARCHAR |
| `fold` | BIGINT |
| `repeat` | BIGINT |
| `assigned` | BOOLEAN |

## split_specs (table)

One row per named split: version, source file, SHA-256, frozen or not.

| column | type |
|---|---|
| `split_name` | VARCHAR |
| `frozen` | BOOLEAN |
| `version` | VARCHAR |
| `cohort` | VARCHAR |
| `family` | VARCHAR |
| `source_file` | VARCHAR |
| `sha256` | VARCHAR |
| `rows` | BIGINT |
| `seed` | BIGINT |
| `generator_commit` | VARCHAR |

## splits (table)

One row per field-season and named split, with fold. Frozen splits are imported unchanged.

| column | type |
|---|---|
| `fs_key` | INTEGER |
| `split_name` | VARCHAR |
| `field_season_id` | VARCHAR |
| `obs_id` | VARCHAR |
| `season_year` | BIGINT |
| `cluster_id` | VARCHAR |
| `group_id` | VARCHAR |
| `fold` | BIGINT |
| `repeat` | BIGINT |

## tiles (table)

The fixed pixel grid of every Sentinel-2 tile that holds a location.

| column | type |
|---|---|
| `mgrs_tile` | VARCHAR |
| `epsg` | BIGINT |
| `ulx` | DOUBLE |
| `uly` | DOUBLE |
| `size_m` | BIGINT |

## v_gcvi_v1 (view)

Green chlorophyll index version 1 = B08 / B03 - 1 from v_reflectance; NULL when B03 is not above 0.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `fs_key` | INTEGER |
| `window_kind` | VARCHAR |
| `scene_id` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |
| `year` | INTEGER |
| `month` | INTEGER |
| `scl` | DOUBLE |
| `cld` | DOUBLE |
| `gcvi` | DOUBLE |

## v_ndvi_v1 (view)

NDVI version 1 = (B08 - B04) / (B08 + B04) from v_reflectance; NULL when the sum is not above 0.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `fs_key` | INTEGER |
| `window_kind` | VARCHAR |
| `scene_id` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |
| `year` | INTEGER |
| `month` | INTEGER |
| `scl` | DOUBLE |
| `cld` | DOUBLE |
| `ndvi` | DOUBLE |

## v_overflights (view)

One row per field-season and physical overflight. Use it to count passes: two tiles or two product levels of one overflight count once.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `fs_key` | INTEGER |
| `window_kind` | VARCHAR |
| `year` | INTEGER |
| `month` | INTEGER |
| `acquisition_id` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |
| `n_tiles` | BIGINT |
| `n_l2a_products` | BIGINT |
| `n_l1c_products` | BIGINT |

## v_reflectance (view)

Reflectance = (DN + dn_add_offset) / 10000 for the spectral bands; DN 0 (no data) gives NULL.

| column | type |
|---|---|
| `field_season_id` | VARCHAR |
| `fs_key` | INTEGER |
| `window_kind` | VARCHAR |
| `granule_id` | VARCHAR |
| `acquisition_id` | VARCHAR |
| `scene_id` | VARCHAR |
| `sensing_time_utc` | TIMESTAMP |
| `year` | INTEGER |
| `month` | INTEGER |
| `read_route` | VARCHAR |
| `scene_cloud_cover_percent` | DOUBLE |
| `scl` | DOUBLE |
| `cld` | DOUBLE |
| `snw` | DOUBLE |
| `b01` | DOUBLE |
| `b02` | DOUBLE |
| `b03` | DOUBLE |
| `b04` | DOUBLE |
| `b05` | DOUBLE |
| `b06` | DOUBLE |
| `b07` | DOUBLE |
| `b08` | DOUBLE |
| `b8a` | DOUBLE |
| `b09` | DOUBLE |
| `b11` | DOUBLE |
| `b12` | DOUBLE |
