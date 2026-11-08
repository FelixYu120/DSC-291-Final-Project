# Dataset: structure, cleaning, quality, splits and pipeline

Florian Saewert, 7 November 2026. The data deliverable of the project: a cleaned and documented dataset with
reproducible preprocessing steps and clearly defined data splits. It covers data v1 (frozen on 30 Oct) and data v2
(5–7 Nov; additive, v1 unchanged byte for byte). Every number was checked on 7 Nov against the code and the data,
read-only, by one writer and one independent checker per section. Decisions with dates: `docs/DECISIONS.md`.

| Task | Section | In one line |
|---|---|---|
| Investigate and document the data structure | [1](#1-data-structure) | 5 cohorts, 11,364 field-seasons, one key `obs_id`; the files, tables, views and columns, with row counts in v1 and v2 |
| Clean and harmonize the Zimbabwe dataset | [2](#2-zimbabwe-cleaning-and-harmonization) | Lacuna 3,002 raw features → 1,880 model fields; Zimbabwe 2024 6,932 raw rows → 2,458; each step counted, each column mapped, fresh checks, 11 open issues |
| Identify data quality issues and weaknesses | [3](#3-data-quality-issues-inconsistencies-and-methodological-weaknesses) | a register of 31 items, ranked by impact: 7 open, 7 handled, 17 accepted |
| Establish training, validation and test splits | [4](#4-training-validation-and-test-splits) | test = `s1_cc2km` fold 0 (kept back); development = folds 1–4; validation = inner `GroupKFold` on `group_id`; counts per fold; code to use them |
| Document the codebase and the pipeline | [5](#5-codebase-and-pipeline) | one row per script, the package modules, how to rebuild v1 and v2, the hash pins, 175 tests |

**Read this first**

- One model per cohort. Never pool cohorts, and never compare t/ha or R² across them. Malawi 2022 and 2023 are never pooled in t/ha.
- Join on `obs_id`. Group on the `group_id` of the split file, never on `cluster_2km`. Read split columns as text.
- `s1_cc2km` fold 0 is the kept-back test set: no new arm is scored on it, in any split family.
- Take X from `load_xy` only. Each chip `record.json` and the `monthly` view also hold the yield.
- v1 and v2 share `obs_id`, not features: never join v1 Presto or MOSAIKS rows to v2 rows.
- No leakage was found (audit of 7 Nov): every `s1_cc2km` fold is at least 2 km from the other folds, no group sits in
  two folds, the inner CV groups on `group_id`, and random test yields change no prediction.
- Scores today: `results/baseline_table.md` (v1), `results/v2/baseline_table.md` and `results/v2/data_v2_comparison.md` (v2).
  More photos per month gave no win; A1 trained on one Malawi season ranks the other at 0.315 and 0.413 (coordinates alone 0.102 and 0.155).

## 1. Data structure

Checked on 7 November 2026 on branch `baseline/mvp` (HEAD `a95c12c`, plus uncommitted work): the files on disk, the code, and both databases opened with `read_only=True`. v1 and data v2 sit side by side. Where they differ, this section gives both.

### 1.1 Files on disk

| Path | What it holds | In git | Bytes |
|---|---|---|---:|
| `data/raw/` | The provider files, unchanged: the OAF workbook and the curated OAF CSV, the Lacuna GeoJSON and its manual, the Malawi 2022 and 2023 shapefile zips, the field dictionaries and metadata sheets, and the Zimbabwe 2024 `metadata.csv`. Also a `README.md` that the team wrote for the Zimbabwe 2024 folder. | committed, 15 files | 47,313,403 |
| `data/raw/vision_guided_yield_estimation/q_field_photo.zip` | The Zimbabwe 2024 photo archive (4,904,281,772 bytes in its manifest). It is not on disk, and no step needs it. | git-ignored | – |
| `data/metadata/` | The provider catalogue records and two download manifests (URL, bytes, SHA-256): `download_manifest.json` (13 files, 41,270,663 bytes) and `vision_guided_yield_download_manifest.json`. | committed, 9 files | 51,594 |
| `data/audit/` | Step 2 output for 6 datasets. `<dataset>_maize_audit.csv` has every maize row with its flags. `<dataset>_screened_candidates.csv` has the rows that pass. `malawi_*_candidates_wgs84.geojson` has the polygons in WGS84. Also `summary.json`, `summary.csv` and `report.html`. | committed, 17 files | 34,072,706 |
| `data/processed/labels_v1.parquet` | The v1 labels table: 11,364 rows, 44 columns. Frozen. | committed | 2,128,518 |
| `data/splits/` | 13 split CSVs, `manifest.json` and `README.md`. Frozen. | committed | 3,044,528 |
| `data/cropyield.duckdb` | The v1 team database. | git-ignored | 872,689,664 |
| `data/v2/audit/` | Malawi 2022 audited again with the datum operation EPSG:1113: the screened CSV, the audit CSV, the GeoJSON and `summary.json`. The four files have a time stamp of 7 Nov 2026, 19:32. The CSV (`733fb603…`) and the GeoJSON (`b7014e54…`) still have the SHA-256 that `labels_v2` and the step 5 plans record. | not committed yet | 2,313,957 |
| `data/v2/processed/labels_v2.parquet` | The v2 labels table: 11,364 rows, 44 columns. | not committed yet | 1,926,986 |
| `data/v2/splits/` | 17 split CSVs (13 byte-equal to v1, 4 new) and `manifest.json`. | not committed yet | 3,265,102 |
| `data/v2/cropyield.duckdb` | The v2 team database. | git-ignored, by the line `data/v2/*.duckdb`, which is an uncommitted change of `.gitignore` | 22,818,816 |
| `data/imagery/sentinel2/` | The v1 chips. One run folder, `run-517bfcf0a69c6cac`, with 11,364 record folders and 103 plan files. Also `catalog_cache/` (921 cached STAC searches) and `windows/` (3 window CSVs and one left-over `.part` file). | git-ignored | not measured |
| `data/imagery/sentinel2.zip` | A zip of `sentinel2/` (460,251 entries). | git-ignored | 19,947,568,402 |
| `data/imagery/sentinel2_v2/` | The v2 chips. `run-2f26e410d1eb4434` has the 529 Malawi 2022 records from the older collection. `run-7cfb6b81a83e1bf9` has the 10,835 top-up records. `catalog_cache/` has 969 searches: hard links to all 921 v1 searches, plus 48 searches of the older collection. Also `windows/` (the two v2 window CSVs) and `logs/` (32 top-up slices, 32 + 16 Malawi 2022 slices, and `step6_v2.log`). | git-ignored | not measured |
| `data/imagery/malawi_2022_recovered/` | The Malawi 2022 recovery work of 3 Nov (chips and its own scripts). No script reads it. Its `imagery/catalog_cache/` holds the 48 older-collection searches that are hard-linked into `data/imagery/sentinel2_v2/catalog_cache/`. | git-ignored | 1,560,700,267 |
| `data/features/mosaiks/` | The v1 MOSAIKS features: `monthly.parquet`, `season.parquet`, `params.json` and `filters.npz`. Parked code made them. Step 6 v1 reads them. There is no `mosaiks_v2/`. | git-ignored | 642,824,720 |
| `data/models/presto/` | The Presto weights (`default_model.pt`, `default_model.json`). No step reads them. | git-ignored | 3,322,174 |
| `data/runs/` | 61 download logs, 48 PNG cards of the pilot records (`pilot48/cards/`), two B0 prediction files of 30 Oct, and `v2_pins/`: 3 snapshots of the v1 files (bytes and SHA-256 of 85 files, plus file lists of the v1 chip folders), taken before stage 1, after stage 1 and after stage 3 of data v2 (81,617,960 bytes each), and a fourth after the v2 scores of 7 Nov. The first three are byte-equal; the fourth differs only by the 4 new files in `results/v2/`. | git-ignored | 249,451,395 |
| `configs/` | Committed: `sentinel2_windows_pilot48.csv` (48 records), `sentinel2_scenes_v1.parquet` (84,967 rows) and `team_database_v1.json`. Not committed yet: `sentinel2_scenes_v2.parquet` (88,305 rows) and `team_database_v2.json`. | mixed | 772,974 |
| `results/` | `baseline_table.md` and `baseline_scores.csv` (40 rows). `v2/baseline_table.md` and `v2/baseline_scores.csv` (53 rows). `v2/data_v2_comparison.md` and `v2/data_v2_comparison.csv` (27 rows). | not committed yet | 39,215 |

`data/v2/` holds 30,324,861 bytes in total, including its database. Two folder trees are empty and unused: `data/raw/USA/USDA_NASS/` and the 9 country folders under `data/processed/by_country/`. "Not committed yet" means that the file is untracked in the working tree today.

**Audit rows per dataset** (`data/audit/summary.json`):

| Audit dataset | Maize rows | Pass basic checks | Screened | Cohort that uses it |
|---|---:|---:|---:|---|
| `one_acre_fund_full` | 45,569 | 30,720 | 30,474 | `kenya_oaf_2019_2020` (Kenya 2019–2020, `intercropping == "0"`) |
| `one_acre_fund_curated` | 14,773 | 14,773 | 14,773 | none (it overlaps the full workbook) |
| `zimbabwe` | 2,269 | 2,269 | 2,266 | `zimbabwe_lacuna_2022_2023` |
| `malawi_2022` | 529 | 529 | 529 | `malawi_2022` (v2 audit: the same 529) |
| `malawi_2023` | 267 | 260 | 260 | `malawi_2023` |
| `vision_guided_yield_estimation` | 5,729 | 4,712 | 4,712 | `zimbabwe_2024` (country `zimbabwe`, year 2024: 4,332 rows) |

### 1.2 The key, and how tables join

- `obs_id = "<dataset>:<source_id>"` (`cropyield.data.cohorts.obs_id`). `dataset` is the audit dataset, not the cohort. Examples: `one_acre_fund_full:ee151220` (Kenya), `zimbabwe:6e287d1e-…` (Lacuna), `vision_guided_yield_estimation:0012b17c-…` (Zimbabwe 2024), `malawi_2023:506ae8b2-…`, `malawi_2022:3ee4d3a6-…`.
- One `obs_id` is one field in one season. It is unique in `labels_v1`, in `labels_v2` and in the `labels` table of both databases: 11,364 rows each.
- Every database table except `build_info` has `obs_id`. The monthly tables (`coverage`, `monthly_bands`, `vegetation_indices`, `mosaiks_monthly`) join on `(obs_id, month)`, where `month` is `'YYYY-MM'`.
- The split CSVs join on `obs_id`. Always join by key, never by row position. Step 8 does `split.set_index("obs_id").loc[y.index]`.
- The parquet and the database `labels` table hold the same 11,364 `obs_id`. They agree on the shared fields: 0 rows differ in `yield_kg_ha`, `include_primary`, `exclusion_reason`, coordinates, year or cohort, in v1 and in v2.
- v1 and v2 use the same `obs_id`, so never join features across the two databases. v1 holds Presto and MOSAIKS rows for all 529 Malawi 2022 fields. These come from v1 imagery with 2 to 4 clear months (2 months: 4 fields, 3 months: 517, 4 months: 8). In v2, the same fields have 5 to 9 clear months, and v2 has no Presto or MOSAIKS rows.

### 1.3 Database tables and views

Both files hold the same 10 tables and 3 views (`sql/schema.sql`, `sql/views.sql`).

| Name | One row is | Columns | Rows v1 | Rows v2 |
|---|---|---:|---:|---:|
| `labels` | one field-season of any cohort, with or without imagery | 22 | 11,364 | 11,364 |
| `downloads` | one field-season with a chip folder | 12 | 11,364 | 11,364 |
| `scenes` | one accepted Sentinel-2 scene (at most one per field and month) | 9 | 84,967 | 88,305 |
| `coverage` | one field-season × month of its season window | 4 | 98,299 | 98,299 |
| `monthly_bands` | one field-season × month: median field reflectance | 14 | 98,299 | 98,299 |
| `vegetation_indices` | one field-season × month: five indices | 7 | 98,299 | 98,299 |
| `presto_embeddings` | one field-season with an embedding | 2 | 11,364 | 0 |
| `mosaiks_monthly` | one field-season × clear month | 4 | 84,967 | 0 |
| `mosaiks_season` | one field-season: the season mean of the MOSAIKS vectors | 4 | 11,364 | 0 |
| `build_info` | the build | 11 | 1 | 1 |
| `season_indices` (view) | one field-season with data: the season max and mean of each index | 11 | 11,364 | 11,364 |
| `master` (view) | one field-season of any cohort: `labels` plus status plus every feature | 39 | 11,364 | 11,364 |
| `monthly` (view) | one downloaded field-season × month, for sequence models | 22 | 98,299 | 98,299 |

Columns:

- `labels`: `obs_id, cohort, dataset, source_id, source_row, country, year, yield_kg_ha, source_yield, source_yield_units, yield_field, latitude, longitude, geometry_type, field_area_ha, label_date, season_start, season_end, intercropping, field_polygon, include_primary, exclusion_reason`.
- `downloads`: `obs_id, record_dir, status, aoi_type, aoi_pixels, field_pixels, aoi_inside_chip, catalog_scenes, accepted_months, crs, search_start, search_end`.
- `scenes`: `obs_id, item_id, acquired, month, satellite, tile, tile_cloud_cover, clear_fraction_aoi, field_valid_pixels`.
- `coverage`: `obs_id, month, state, item_id`. `state` is `clear`, `cloudy`, `no_scene` or `download_error`.
- `monthly_bands`: `obs_id, month, b02, b03, b04, b05, b06, b07, b08, b8a, b11, b12, field_pixels, missing`.
- `vegetation_indices`: `obs_id, month, ndvi, gcvi, mtci, ndvi705, ndvi740`.
- `presto_embeddings`: `obs_id, embedding FLOAT[128]`. `mosaiks_monthly`: `obs_id, month, chip FLOAT[], field FLOAT[]`. `mosaiks_season`: `obs_id, months_used, chip FLOAT[], field FLOAT[]`.
- `master`: every `labels` column, then `has_imagery, download_status, months_with_data`, then the 10 season features `{ndvi, gcvi, mtci, ndvi705, ndvi740}_season_{max, mean}`, then `presto_embedding, mosaiks_chip, mosaiks_field, mosaiks_months_used`.
- `monthly`: `obs_id, cohort, month, coverage_state`, the 10 bands, the 5 indices, `mosaiks_chip, mosaiks_field, yield_kg_ha`.

**What the two databases hold.**

| | v1 (`data/cropyield.duckdb`) | v2 (`data/v2/cropyield.duckdb`) |
|---|---|---|
| Built (`build_info.built_at`, UTC) | 2026-10-30 21:53:55 | 2026-11-05 21:22:16 |
| `build_info.git_commit` | `96e2e81` | `a95c12c` |
| Chips read (`imagery_dir`) | `data/imagery/sentinel2` | `data/imagery/sentinel2_v2` |
| Presto | built, 11,364 rows | empty |
| MOSAIKS | K = 1,024 (`params.json`: seed 291, 483 fit scenes) | empty |
| Download status | 11,364 `complete` | 11,364 `complete` |
| Coverage: clear / cloudy / no_scene | 84,967 / 2,922 / 10,410 | 88,305 / 2,649 / 7,345 |

No month is `download_error` in either file. Each field has 8 window months in Kenya (Feb–Sep) and 9 in the other cohorts (Oct–Jun).

**Model rows** (`include_primary AND months_with_data >= 4`, the rule of `load_xy`):

| Cohort | `include_primary` v1 | Model rows v1 | `include_primary` v2 | Model rows v2 |
|---|---:|---:|---:|---:|
| `kenya_oaf_2019_2020` | 3,977 | 3,977 | 3,977 | 3,977 |
| `malawi_2023` | 260 | 251 | 260 | 253 |
| `zimbabwe_lacuna_2022_2023` | 1,880 | 1,880 | 1,880 | 1,880 |
| `zimbabwe_2024` (parked) | 2,458 | 2,458 | 2,458 | 2,458 |
| `malawi_2022` | 0 | 0 | 529 | 529 |

On the v2 model rows outside Malawi 2022, v2 moved 522 field-months from `cloudy` to `clear`: Kenya 176, Malawi 2023 51, Lacuna 205 and Zimbabwe 2024 90. Outside Malawi 2022, all 83,376 `clear` months of v1 keep the same scene in v2. In Malawi 2022, 2,631 field-months moved from `no_scene` to `clear`, 83 from `cloudy` to `clear` and 434 from `no_scene` to `cloudy`. Its 1,591 `clear` months of v1 are all `clear` in v2, but each with another scene (`item_id`), from the older collection. No `clear` month of v1 is lost in v2.

**The database `labels` table and the parquet are not the same table.** The database table keeps the audit columns as text or numbers (`country`, `year`, `source_yield`, `source_yield_units`, `yield_field`, `latitude`, `longitude`, `label_date`, `intercropping` as text, `field_polygon` as GeoJSON). Some names differ from the parquet: `year` is `season_year`, `latitude` and `longitude` are `lat` and `lon`, and `country` (a lower-case name) is `country_iso3`. It takes only `include_primary` and `exclusion_reason` from the parquet (`labels_v1` in v1, `labels_v2` in v2). Groups, flags and measurement columns are in the parquet only, so join the parquet on `obs_id` for them. `field_area_ha` has the same name but a different content: the database has it for Malawi only (789 rows), and the parquet adds Kenya (3,977 rows, the self-reported `plot_acres` × 0.40468564224).

| Cohort | `source_yield_units` | `yield_field` | `aoi_type` | Field pixels (median) |
|---|---|---|---|---:|
| `kenya_oaf_2019_2020` | kg/ha | `yield_kg_ph` | `point_pixel` | 1 |
| `malawi_2022` | t/ha | `AVG_YLD` | `field_polygon` | 37 (v1 and v2 chips) |
| `malawi_2023` | t/ha | `cc_ey_t` | `field_polygon` | 59 |
| `zimbabwe_2024` | t/ha | `Avg_yield_mt_ha` | `point_pixel` | 1 |
| `zimbabwe_lacuna_2022_2023` | t/ha | `Yield(Mt/H` | `point_pixel` | 1 |

The chips lie in 5 UTM grids, with the same counts in v1 and v2: EPSG:32636 (2,337), 32637 (14), 32735 (1,902), 32736 (7,010) and 32737 (101).

### 1.4 The labels table: `labels_v1` (and `labels_v2`)

Built by `src/cropyield/data/labels.py`. One row is one field-season of every cohort. Nothing is deleted: a row that is not used has `include_primary = False` and an `exclusion_reason`. Both files have the same 44 columns and the same types.

| Column | Type | Meaning |
|---|---|---|
| `obs_id` | string | the key, `dataset:source_id` |
| `cohort` | string | one of the 5 cohorts of `cohorts.py` |
| `role` | string | `core`, `second`, `parked` or `dropped`. Malawi 2022 is `dropped` in v1 and `second` in v2 |
| `dataset` | string | audit dataset |
| `source_id` | string | the provider's id of the row |
| `source_row` | int64 | row number in the provider file |
| `source_sha256` | string | SHA-256 of the screened audit CSV that the row came from |
| `country_iso3` | string | `KEN`, `MWI` or `ZWE` |
| `season_year` | int64 | harvest year |
| `season_start`, `season_end` | timestamp[us] | the fixed season window of the cohort and year |
| `yield_kg_ha` | double | the target, in kg/ha |
| `yield_definition` | string | one value per cohort: `mean_2_boxes_6x6m`, `cut_10x10m_13pct`, `mean_2_cuts_5x5m`, `cut_8x5m_dry_weight`, `mean_2_boxes_40m2` |
| `cut_area_m2` | double | 36 (Kenya), 100 (Malawi 2023), 25 (Malawi 2022), 40 (Lacuna, Zimbabwe 2024) |
| `n_cuts` | int64 | cuts behind one yield: 1 or 2 |
| `moisture_basis_pct` | double | 13 for Malawi 2023; null where the provider states no basis |
| `unit_provisional` | bool | True for Lacuna |
| `cut1_kg_ha`, `cut2_kg_ha` | double | Malawi 2023: the main cut and the nested 5×5 m cut. Zimbabwe 2024: box 1 and box 2. Null elsewhere |
| `geometry_type` | string | `Point`, `Polygon` or `MultiPolygon` |
| `lat`, `lon` | double | WGS84 degrees. For a polygon, a point inside it, from the audit |
| `geometry_wkt` | string | polygon WKT, Malawi only (789 rows in v1 and in v2) |
| `field_area_ha` | double | Malawi: the provider area. Kenya: `plot_acres` × 0.40468564224 |
| `location_source` | string | `walked_polygon`, `field_gps` or `field_gps_maybe_homestead` |
| `source_crs` | string | `EPSG:4326`, `OGC:CRS84` or `EPSG:20936`. In v2, Malawi 2022 has `EPSG:20936 via EPSG:1113` |
| `plant_date`, `harvest_date` | timestamp[us] | provider dates, where given |
| `obs_date` | timestamp[us] | the harvest date, else the crop-cut or photo date |
| `obs_date_source` | string | `harvest_date`, `crop_cut_time`, `photo_filename` or `none` |
| `intercropped` | bool, nullable | Kenya and Lacuna; null elsewhere |
| `irrigated` | bool, nullable | Lacuna only |
| `admin_unit` | string | Kenya: the district, normalised. Lacuna: `Admin1` in lower case |
| `site_unit` | string | Kenya: `district\|site` |
| `cluster_2km` | int32 | a 2 km connected cluster over all rows of the cohort, including excluded rows |
| `site_distance_km` | double | Kenya: the distance from the field point to the site point (1,706 of 3,977 rows have it) |
| `is_zero` | bool | yield is 0 |
| `near_dup_10m` | bool | another row of the cohort lies within 10 m |
| `polygon_overlap_dup` | bool | Malawi: overlaps another polygon by more than half of the smaller one |
| `date_outside_window` | bool | `obs_date` lies outside the season window |
| `impossible_date` | bool | the planting year is out of range, or the harvest is on or before planting, or the harvest year is out of range |
| `source_flags` | string | the audit's `quality_flags`, for example `yield_unit_interpretation_provisional`, `zero_yield_review`, `coordinates_reused_across_records` |
| `include_primary` | bool | True on the rows that models use |
| `exclusion_reason` | string | `""` on a model row, else the first reason that applies |

**Rows per cohort and year:**

| Cohort | Role (v1 / v2) | Year | Rows | `include_primary` v1 | `include_primary` v2 | Season window |
|---|---|---:|---:|---:|---:|---|
| `kenya_oaf_2019_2020` | core | 2019 | 1,768 | 1,768 | 1,768 | 1 Feb – 30 Sep 2019 |
| `kenya_oaf_2019_2020` | core | 2020 | 2,209 | 2,209 | 2,209 | 1 Feb – 30 Sep 2020 |
| `malawi_2023` | core | 2023 | 260 | 260 | 260 | 1 Oct 2022 – 30 Jun 2023 |
| `zimbabwe_lacuna_2022_2023` | second | 2022 | 169 | 0 | 0 | 1 Oct 2021 – 30 Jun 2022 |
| `zimbabwe_lacuna_2022_2023` | second | 2023 | 2,097 | 1,880 | 1,880 | 1 Oct 2022 – 30 Jun 2023 |
| `zimbabwe_2024` | parked | 2024 | 4,332 | 2,458 | 2,458 | 1 Oct 2023 – 30 Jun 2024 |
| `malawi_2022` | dropped / second | 2022 | 529 | 0 | 529 | 1 Oct 2021 – 30 Jun 2022 |
| **Total** | | | **11,364** | **8,575** | **9,104** | |

**Exclusion reasons** (one per row; the first rule that applies wins):

| `exclusion_reason` | v1 | v2 |
|---|---:|---:|
| `zimbabwe_2024_zero_likely_not_measured` | 1,874 | 1,874 |
| `dropped_cohort_2022_imagery_gap` | 529 | 0 |
| `lacuna_intercropped` | 212 | 212 |
| `dropped_year_2022_imagery_gap` | 169 | 169 |
| `lacuna_irrigated` | 5 | 5 |
| `yield_above_15_t_ha` | 0 | 0 |

There are 225 intercropped Lacuna rows in total. 13 of them are 2022 rows, which carry the year reason.

**v2 against v1.** The two files hold the same 11,364 rows in the same order. Outside Malawi 2022, all 44 columns are equal. In Malawi 2022, 9 columns change: `role`, `source_sha256`, `lat`, `lon`, `geometry_wkt`, `source_crs`, `cluster_2km`, `include_primary` and `exclusion_reason`. All 529 Malawi 2022 positions move, because the polygons come from the EPSG:1113 audit. `cluster_2km` changes on 88 of the 529 rows; the other 8 columns change on all 529.

### 1.5 Split files

One CSV per cohort and family: `<cohort>__<family>.csv`. The one exception is `malawi_2022_2023__temporal_rank.csv`, which holds two cohorts. The columns are `obs_id, cohort, season_year, cluster_id, group_id, fold, repeat, family`. `temporal` adds `test_subset`. The rows are the `include_primary` rows of the cohort, also the rows with fewer than 4 clear months (Malawi 2023: 260 split rows, but 251 model rows in v1 and 253 in v2). `temporal_rank` is different: it holds every Malawi 2023 row, and only the Malawi 2022 rows within 20 km of a Malawi 2023 field. `fold` is `0`–`4`, or `train`/`test` in the season families.

| Cohort | `s1_cc2km` groups | `s2_region` groups | Rows per repeat | Other families |
|---|---:|---:|---:|---|
| `kenya_oaf_2019_2020` | 849 | 50 (district) | 3,977 | `temporal` (2 repeats, 7,954 rows), `random_diag` |
| `malawi_2023` | 53 | 21 (5 km clusters) | 260 | `random_diag` |
| `zimbabwe_lacuna_2022_2023` | 289 | 20 (`Admin1`) | 1,880 | `random_diag` |
| `zimbabwe_2024` | 996 | 20 (k-means) | 2,458 | `random_diag` |
| `malawi_2022` (v2 only) | 97 | 20 (k-means) | 529 | `random_diag` |
| `malawi_2022_2023` (v2 only) | – | – | 444 (184 Malawi 2022 + 260 Malawi 2023) | `temporal_rank` (2 repeats, 888 rows, 79 groups; 10 groups hold fields of both seasons) |

`data/splits/` has 13 files. `data/v2/splits/` has 17: the same 13, byte for byte, plus `malawi_2022__s1_cc2km.csv`, `malawi_2022__s2_region.csv`, `malawi_2022__random_diag.csv` and `malawi_2022_2023__temporal_rank.csv`. Group by the `group_id` of the split file. Do not group by `cluster_id`: in every split file it is the labels column `cluster_2km`. `cluster_2km` covers all rows of a cohort, so it differs in Lacuna (272 values on the primary rows against 289 groups) and in Zimbabwe 2024 (956 against 996). In `s1_cc2km`, 12 Lacuna and 27 Zimbabwe 2024 `cluster_id` values lie in more than one fold.

## 2. Zimbabwe: cleaning and harmonization

Checked on 7 November 2026 against the raw files in `data/raw/`, the audit files in `data/audit/`, `data/processed/labels_v1.parquet` (SHA-256 `49aae383…`), `data/v2/processed/labels_v2.parquet` (`2b157317…`), `data/cropyield.duckdb` and `data/v2/cropyield.duckdb`. All reads were read-only.

Two cohorts come from Zimbabwe. They use different protocols and are never pooled, with each other or with any other cohort.

| | `zimbabwe_lacuna_2022_2023` | `zimbabwe_2024` |
|---|---|---|
| Audit dataset | `zimbabwe` | `vision_guided_yield_estimation` |
| Provider | PULA Advisors, Lacuna Fund grant. Zenodo record 10060610, CC BY 4.0, published 1 Nov 2023 | Irgau, Li, Lobell, Janmohamed, Rieckmann (data from Pula). Zenodo record 17626117, CC BY 4.0, published 17 Nov 2025. Paper: Li et al. 2026, AAAI |
| Download | `scripts/step1_download_labels.py` | `scripts/step1b_download_zimbabwe2024_labels.py` (`--metadata-only` skips the 4.9 GB photo archive) |
| Raw files | `data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson` (1,481,197 B) and the technical manual (`.py`, `.slides.html`, `_2.pdf`) | `data/raw/vision_guided_yield_estimation/metadata.csv` (6,040,484 B) and `README.md`. `q_field_photo.zip` is in the manifest but not on disk in this working copy |
| Checksums | `data/metadata/download_manifest.json` (GeoJSON `0dc43015…`, matches today) | `data/metadata/vision_guided_yield_download_manifest.json` (CSV `bbd14515…`, matches today) |
| One row | one GeoJSON feature: one field, one crop cut, one season | one CSV row: one field (`cce_id`), up to two crop-cut boxes |
| Location | GPS point, `OGC:CRS84` (lon, lat) | GPS point, `latitude`/`longitude`. No CRS is stated; `labels_v1` records `EPSG:4326` |
| Protocol | one cut of 8 × 5 m (40 m²). Wet weight at harvest, dry weight after drying. t/ha = dry kg × 0.25. Moisture basis and grain-vs-cob are not stated | two random crop-cut boxes per field at harvest. The label is their mean (`Avg_yield_mt_ha`). Each box is 40 m², which the data confirm (t/ha = dry kg × 0.25 on every box with a dry weight above 0: 2,431 box-1 and 2,428 box-2 values). Moisture is not stated |
| Unit | `Yield(Mt/H`. The catalogue says "Megatonnes per Hectare"; the team reads it as metric t/ha, **provisional** (`unit_provisional = True`) | `Avg_yield_mt_ha`, metric t/ha (`unit_provisional = False`) |
| Dates | `Planting_D`, `Harvesting` per row | no planting or harvest date. `obs_date` is the date in the `q_field_photo` filename |
| Role in `labels_v1` | `second` | `parked` |

Sources for the protocol rows: the Zenodo record text in `data/metadata/zimbabwe.json`, the `NOTES` in `scripts/step2_audit_labels.py`, `MEASUREMENTS` in `src/cropyield/data/labels.py`, and Li et al. 2026, section 2 ("two random crop cuts … average … mt ha-1").

### 2.1 Cleaning funnel: Lacuna (`zimbabwe_lacuna_2022_2023`)

Steps 2 and 3 never change a source value. Step 2 writes all 2,269 maize rows with their flags to `data/audit/zimbabwe_maize_audit.csv`. Outside the raw GeoJSON, this file is the only place that keeps the 3 maize rows step 2 drops; the 733 non-maize features are in the raw file only. Step 3 keeps every row that `load_cohort` returns and sets `include_primary` and `exclusion_reason`. If a row has more than one reason, the first one wins.

| Step | Rule (code) | Rows left | Removed |
|---|---|---:|---:|
| Raw features | GeoJSON, all crops | 3,002 | – |
| Maize | `Crop_Type == "Maize/Corn"` (`zimbabwe()` in step 2; `Type` 1) | 2,269 | 733 (wheat 304, sorghum 217, soybeans 212) |
| Numeric yield ≥ 0 | `base()` | 2,269 | 0 |
| Valid coordinates | `base()` | 2,269 | 0 |
| Inside country envelope (25.1–33.1° E, 22.5–15.5° S) | `base()` | 2,269 | 0 |
| Exact duplicate source row | `finish()` | 2,269 | 0 |
| = basic candidates | `passes_basic_checks` | 2,269 (169 harvested 2022, 2,100 harvested 2023; 28 zeros) | |
| Yield ≠ dry kg × 0.25 (relative and absolute tolerance 0.001) | flag `yield_disagrees_with_documented_40m2_crop_cut` set in `zimbabwe()`; `finish()` drops flagged rows | 2,266 | 3 (all 2023; the yield is dry kg × 0.5 in all three) |
| Dry weight > wet weight; yield > 30 t/ha | flags set in `zimbabwe()` and `base()`; `finish()` drops flagged rows | 2,266 | 0 |
| = screened candidates | `data/audit/zimbabwe_screened_candidates.csv` | 2,266 (2022: 169, 2023: 2,097) | |
| Cohort load: years 2022–2023, Zimbabwe, maize, passes checks | `load_cohort` in `src/cropyield/data/cohorts.py` | 2,266 | 0 |
| `dropped_year_2022_imagery_gap` | `exclusion_reasons` in `labels.py` | 2,097 | 169 |
| `lacuna_intercropped` (`Intercropp == "yes"`) | same | 1,885 | 212 |
| `lacuna_irrigated` (`Field_Irri == "yes"`) | same | 1,880 | 5 |
| `yield_above_15_t_ha` | same | 1,880 | 0 |
| = `include_primary` | `labels_v1`, `labels_v2` | **1,880** | |
| ≥ 4 clear months (`MIN_CLEAR_MONTHS` in `src/cropyield/data/xy.py`) | v1 and v2 database | **1,880** (median 7 clear months, min 4) | 0 |

- In the raw maize rows, 225 are intercropped (13 of them in 2022, 212 in 2023) and 5 are irrigated (all 2023). No row is both. The 13 intercropped 2022 rows carry the year reason, so `exclusion_reason` counts 212 and 5.
- Zeros are kept. All 28 zeros are in the 1,880 model rows.
- Lacuna 2022 has 169 rows: 156 pure stand and rainfed, 6 `Admin1` units, median 1.46 t/ha over all 169 rows (1.63 t/ha over the 156). They were planted November 2021 – February 2022 and harvested March – July 2022. Of the 169 points, 20 are within 50 m of a Lacuna 2023 point and 5 within 10 m.

### 2.2 Cleaning funnel: Zimbabwe 2024 (`zimbabwe_2024`)

Step 2 audits Nigeria and Zimbabwe maize together. The country is split off at the cohort load.

| Step | Rule (code) | Rows left | Removed |
|---|---|---:|---:|
| Raw CSV rows | `metadata.csv` | 6,932 | – |
| Maize | `"maize"` or `"corn"` in `crop` (`vision_guided_yield_estimation()` in step 2) | 5,729 (Zimbabwe 2024: 5,055; Nigeria 2022: 674) | 1,203 rice (Nigeria 2022) |
| Numeric yield ≥ 0 (Zimbabwe) | `base()` | 4,332 | 723 blank `Avg_yield_mt_ha`: comment "only have farm photos" 590, "did wet but no dry" 133 |
| Valid coordinates, inside envelope, no exact duplicate | `base()`, `finish()` | 4,332 | 0 |
| Additional yield checks | `finish()` (only the 30 t/ha rule applies here) | 4,332 | 0 |
| = screened candidates | `data/audit/vision_guided_yield_estimation_screened_candidates.csv` (4,712 rows = 4,332 Zimbabwe + 380 Nigeria) | 4,332 | |
| Cohort load: year 2024, Zimbabwe | `load_cohort` | 4,332 | 380 Nigeria rows not used |
| `zimbabwe_2024_zero_likely_not_measured` | `exclusion_reasons` | 2,458 | 1,874 |
| `yield_above_15_t_ha` | same | 2,458 | 0 |
| = `include_primary` | `labels_v1`, `labels_v2` | **2,458** | |
| ≥ 4 clear months | v1 and v2 database | **2,458** (median 9 clear months, min 5) | 0 |

**v1 and data v2.** Both Zimbabwe cohorts have the same rows and values in `labels_v1` and `labels_v2`; `v2_differences` in `scripts/step3_build_labels.py` stops the v2 build if any non-Malawi-2022 row differs. The six Zimbabwe split files have the same SHA-256 in `data/splits/manifest.json` and `data/v2/splits/manifest.json`. In the v2 database, the change for Zimbabwe is in the imagery: with up to 24 photo tries per cloudy month, 195 Lacuna model rows gain 205 clear months and 90 Zimbabwe 2024 model rows gain 90. No row loses a month. The v2 database also holds no Presto or MOSAIKS rows (0 rows in `presto_embeddings`, `mosaiks_monthly` and `mosaiks_season`). The model row counts stay 1,880 and 2,458. Lacuna 2022 stays excluded in v2.

**Splits (summary).** Lacuna `s1_cc2km` has 289 groups in 5 folds of 376 fields. `s2_region` holds out the 20 `Admin1` units in 5 folds (372–378 fields). Zimbabwe 2024 `s1_cc2km` has 996 groups in folds of 491–492. Its `s2_region` uses 20 k-means blocks (`kmeans20` in `scripts/step4_build_splits.py`), because the paper's 87 zones are not released (`metadata.csv` has no zone column). Fold 0 of `s1_cc2km` is kept back for the end of the project; new scores use folds 1–4. Group on the split's `group_id`, not on `labels.cluster_2km`: `cluster_2km` is built over all cohort rows, so 12 Lacuna and 27 Zimbabwe 2024 `cluster_2km` values hold fields of two `s1_cc2km` folds.

### 2.3 Harmonization: raw columns to `labels_v1`

Harmonization here means the same column names, units and keys in every cohort. It does not mean the same measurement. The t/ha values of the two cohorts are not comparable (2.4, 2.6).

| `labels_v1` column | Lacuna source | Zimbabwe 2024 source | Provisional? |
|---|---|---|---|
| `obs_id` | `"zimbabwe:" + Case_ID` | `"vision_guided_yield_estimation:" + cce_id` | no |
| `source_row` | feature number in the GeoJSON (from 1) | CSV line number (header = 1) | no |
| `season_year` | first 4 characters of `Harvesting` (harvest year) | `data_collection_year` (`2024.0` → 2024) | Lacuna: yes, the year comes from the harvest date |
| `season_start`, `season_end` | fixed: 1 Oct of year − 1 to 30 Jun of year (`COHORTS` in `cohorts.py`) | same window: 1 Oct 2023 – 30 Jun 2024 | yes, one window per agro-zone, not per field |
| `yield_kg_ha` | `Yield(Mt/H` × 1000 | `Avg_yield_mt_ha` × 1000 | Lacuna: yes (unit) |
| `source_yield`, `source_yield_units`, `yield_field` (database `labels` table) | the `Yield(Mt/H` value, `t/ha`, `Yield(Mt/H` | the `Avg_yield_mt_ha` value, `t/ha`, `Avg_yield_mt_ha` | |
| `yield_definition`, `cut_area_m2`, `n_cuts` | `cut_8x5m_dry_weight`, 40, 1 | `mean_2_boxes_40m2`, 40, 2 | declared from the provider documents, one value per cohort |
| `moisture_basis_pct` | null (not stated) | null (not stated) | |
| `unit_provisional` | `True` | `False` | |
| `cut1_kg_ha`, `cut2_kg_ha` | null | `box1_into_mt_ha` × 1000, `box2_into_mt_ha` × 1000 (both present on 2,416 model rows) | |
| `lat`, `lon` | GeoJSON `coordinates[1]`, `[0]`, unchanged | `latitude`, `longitude`, unchanged | |
| `geometry_type`, `geometry_wkt` | `Point`, null | `Point`, null | |
| `location_source`, `source_crs` | `field_gps`, `OGC:CRS84` | `field_gps`, `EPSG:4326` | 2024 CRS is an assumption |
| `plant_date`, `harvest_date` | `Planting_D`, `Harvesting` | null, null | |
| `obs_date`, `obs_date_source` | `harvest_date`, `harvest_date` | photo filename date, `photo_filename` | 2024: yes, a proxy for the visit |
| `intercropped` | `Intercropp`: `yes` → True, `no` → False | null (not reported) | |
| `irrigated` | `Field_Irri` from the raw file (the audit drops it; `lacuna_groups()`) | null | |
| `admin_unit` | `Admin1`, trimmed and lower case | null | `Admin1` is not one admin level (one 2022 value is `mashonaland central`); see 2.4 and 2.6 issue 4 |
| `include_primary`, `exclusion_reason` | rules in 2.1 | rules in 2.2 | the 2024 zero rule is a team judgment |

`check_against_raw` (`src/cropyield/data/labels.py`) re-derives Lacuna rows from the GeoJSON: yield within 1e-6 kg/ha, t/ha = dry kg × 0.25 within 1e-3, latitude within 1e-7° (longitude is not checked). For Zimbabwe 2024 it checks only that the yield is the mean of the label's own `cut1_kg_ha` and `cut2_kg_ha` within 1 kg/ha, on rows with both boxes; it does not read `metadata.csv`. `check_labels` checks the table alone. Both return no problems on `labels_v1` today. A separate join of the 4,332 Zimbabwe 2024 rows to `metadata.csv` on `cce_id` today gives the same yield, `lat`, `lon` and `cut1_kg_ha` with zero difference, and `source_row` equals the CSV line number on every row.

### 2.4 Fresh quality checks on the model rows

These are new checks on the 1,880 Lacuna and 2,458 Zimbabwe 2024 model rows (`include_primary` and ≥ 4 clear months). They use their own haversine distances (brute force and scikit-learn `BallTree`), not the project's KD-tree. Scripts and outputs are listed in the sources.

**Duplicates and near-duplicates**

| | Lacuna (1,880) | Zimbabwe 2024 (2,458) |
|---|---:|---:|
| Repeated `source_id` | 0 | 0 |
| Exactly the same coordinates | 14 rows (7 pairs), all with different yields | 0 |
| Pairs within 10 m | 8 (16 rows; includes the 7 same-coordinate pairs); median yield gap 0.52 t/ha; 3 pairs on the same date | 1 (0.081 and 0.038 t/ha, different dates) |
| Pairs within 50 m / 100 m | 26 / 103 | 25 / 91 |
| All 10 m pairs in the same `cluster_2km` and the same `s1_cc2km` group | yes | yes |
| `near_dup_10m = True` in `labels_v1` | 22 | 2 |

`near_dup_10m` is computed over all cohort rows (2,266 for Lacuna). So 6 included Lacuna rows carry it only because an excluded row lies within 10 m. The pairs at the same coordinates with different yields look like one GPS fix used for two fields. They are kept and grouped, which is correct for the splits.

**Location**

- All model points are inside the step 2 envelope. Lacuna spans 27.21–31.88° E and 20.96–16.41° S. Zimbabwe 2024 spans 27.11–33.04° E and 21.84–16.21° S.
- The envelope is a box, not the border, and the repository has no boundary file. 34 Zimbabwe 2024 model rows lie east of 32.95° E (32.96–33.04° E, 17.39–18.43° S), near the eastern edge of the box (33.1° E). They need a point-in-polygon test.
- Isolated points: the median distance to the nearest other model row is 0.39 km (Lacuna) and 1.14 km (2024). The maximum is 33.1 km and 49.7 km.
- `Admin1` spread (Lacuna): 148 model rows lie more than 50 km from the median point of their own `admin_unit`, and 24 lie more than 100 km from it. All 24 are `mazowe` rows near 18.22° S, 31.41° E, in one `cluster_2km`. They are about 110 km from the median point of the 72 `mazowe` rows and at least 113 km from any other `mazowe` row. `mazowe` spans 142.8 km (5 clusters) and `chivi` spans 131.9 km.

**Yield distribution (t/ha)**

| | n | mean | median | p10 | p90 | p99 | max | zeros | > 10 | > 15 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lacuna model rows | 1,880 | 3.35 | 3.02 | 0.97 | 6.14 | 8.52 | 12.43 | 28 | 2 | 0 |
| Zimbabwe 2024 model rows | 2,458 | 0.86 | 0.53 | 0.08 | 2.03 | 4.84 | 9.11 | 0 (excluded) | 0 | 0 |

- Lacuna: no row is above Q3 + 3 × IQR (13.34). 8 rows are above Q3 + 1.5 × IQR (9.02). The two highest values (12.43 and 12.34 t/ha, both `Zvimba`) are 49.7 and 49.3 kg dry from 40 m².
- Lacuna `Crop_Condi` orders yield as expected: median `very_good` 4.88, `good` 3.42, `average` 2.12, `below_average` 0.97, `no_crop_survived` 0.00 t/ha. Of the 28 zeros, 12 are `no_crop_survived`, 15 `below_average` and 1 `average`. All 28 have wet = dry = 0.
- Zimbabwe 2024: 311 model rows are below 0.1 t/ha (a mean box dry weight under 0.4 kg per 40 m²) and 136 below 0.05 t/ha. 51 are above Q3 + 3 × IQR (3.94).

**Dry-weight unit check**

| | Rows checked | Deviate from t/ha = dry kg × 0.25 (> 0.001) | Dry > wet | Median dry / wet |
|---|---:|---:|---:|---:|
| Lacuna, all maize rows | 2,269 | 3 (0.13 %); the audit drops them | 0 | – |
| Lacuna, model rows | 1,880 | 0 | 0 | 0.76 (7 rows below 0.3, min 0.16) |
| Zimbabwe 2024, all 5,055 maize rows, box 1 / box 2 (dry > 0) | 2,431 / 2,428 | 0 / 0 | 0 | 0.60 / 0.59 |

In Zimbabwe 2024, `Avg_yield_mt_ha` equals the mean of the two boxes on all 4,290 two-box rows. On the 42 one-box rows (`only box 1 used` 19, `only box 2 used` 23), it equals that one box.

**Dates and the season window**

- Lacuna model rows were planted October 2022 – March 2023 (October 63, November 1,212, December 500, January 70, February 34, March 1). They were harvested February – July 2023 (February 1, March 193, April 802, May 692, June 190, July 2). The season lasts 89–211 days, median 157.
- No model row is planted before the window start, and `impossible_date` is 0. Two rows harvested on 1 Jul 2023 are one day past the window end. They carry `date_outside_window` and are kept. Over all 2,266 rows, 22 carry the flag: 19 in 2022 (excluded by year), 2 included, 1 intercropped.
- Zimbabwe 2024 model photo dates run from 17 Feb to 18 Jun 2024 (February 1, March 13, April 2,043, May 384, June 17). All 86 rows outside the window are July zeros, and all are excluded.

**Why Zimbabwe 2024 yields are low (mean 0.86, median 0.53 t/ha on the positive rows)**

The low values do not come from the unit conversion:

1. Every box obeys t/ha = dry kg × 0.25 (a 40 m² box), and the label is exactly the box mean.
2. The weighed mass itself is small. The median dry weight per box on positive rows is 2.04 kg, against 12.08 kg per 40 m² cut in the 1,880 Lacuna model rows.
3. Location does not explain it. 488 positive 2024 rows lie within 5 km of a Lacuna model row. Their median is 0.61 t/ha; the nearest Lacuna rows have a median of 3.57 t/ha, a factor of about 5.9.
4. The basis of the 2024 "dry" weight is not stated. The file has threshing-photo columns (box 1: 1,766 of 5,055 rows, box 2: 1,768), which suggests threshed grain, but this is an inference. Dry / wet is 0.60 / 0.59 (2024) against 0.76 (Lacuna), and the Lacuna grain-vs-cob basis is not stated either. The files give no number for how much of the gap a different basis could explain.
5. Visit timing matters. Among numeric rows, the zero share is 13.3 % in March, 29.6 % in April, 65.8 % in May, 91.7 % in June and 100 % in July. The positive mean falls to 0.24 t/ha in June.
6. No file in the repository gives a source for a 2023/24 drought. This section does not use drought as a reason.

So this is a question of season, protocol and visit timing, not of units. The dataset authors keep small and zero values as data: Li et al. 2026 show a Zimbabwe 2024 field at 0.0061 t/ha (Fig. 1), and the Fig. 3 caption calls the values at 0 "exact zeros". The Zenodo record and the dataset `README.md` say nothing about zeros. Every zero row has all four box weights at zero or blank. The `Comments` column holds "have average yields" on all 4,332 numeric rows, so it does not separate zeros from positive rows.

### 2.5 Reproduce

```
python scripts/step1_download_labels.py                          # OAF, Lacuna (Zenodo 10060610) and Malawi; network; rewrites data/metadata/download_manifest.json
python scripts/step1b_download_zimbabwe2024_labels.py --metadata-only   # Zenodo 17626117, network
python scripts/step2_audit_labels.py                             # offline, rewrites data/audit/
python scripts/step3_build_labels.py                             # confirms labels_v1 bytes, else stops
python scripts/step3_build_labels.py --version 2                 # confirms labels_v2 bytes
```

`source_sha256` in `labels_v1` pins the screened CSV of each cohort. Both match the files on disk today (`b5760d3e…` Lacuna, `2c5a730c…` Zimbabwe 2024). A step 2 rerun today also changes `data/audit/summary.json` and `data/audit/report.html`: their stored notes name `scripts/download_vision_guided_yield_data.py`, which does not exist, while the current `NOTES` name `scripts/step1b_download_zimbabwe2024_labels.py`.

### 2.6 Open issues

None of these edits the frozen `labels_v1`. A change to a row would need a new labels version, new splits and a new line in `docs/DECISIONS.md`.

| # | Issue | Evidence | Recommended action |
|---|---|---|---|
| 1 | Lacuna unit and basis not confirmed | The column is `Yield(Mt/H` and the catalogue says "Megatonnes per Hectare". Moisture and grain-vs-cob are not stated. Dry / wet is 0.76 (Lacuna) vs 0.60 / 0.59 (2024). 3 raw rows use dry kg × 0.5 | Ask PULA for the protocol sheet. Keep `unit_provisional`. Report Lacuna by rank and R², never next to other cohorts in t/ha |
| 2 | The Zimbabwe 2024 zero rule is a team judgment | 1,874 zeros. The zero share rises with visit month (13 % → 100 %). All four box weights are zero or blank. Li et al. 2026 (the dataset authors) keep them as "exact zeros" (Fig. 3); the step 2 note calls them "possible crop failures" | Keep the cohort `parked`. Ask the authors what a zero means. If it is used, report with and without zeros as separate rows |
| 3 | The Zimbabwe 2024 t/ha level is not comparable with Lacuna | Same area within 5 km: 0.61 vs 3.57 t/ha median. The units check out | Use ranks only. Do not give drought as a reason without a source |
| 4 | Lacuna `Admin1` is not a clean region key | 24 `mazowe` rows are about 110 km from the median point of the `mazowe` rows and at least 113 km from any other `mazowe` row. `mazowe` spans 142.8 km and `chivi` 131.9 km. 148 rows are more than 50 km from their unit's median point | Check against an admin boundary file before `s2_region` becomes a headline. A fix is a new labels version or a documented group override in the splits |
| 5 | No true border test | Only a bounding box is checked. 34 Zimbabwe 2024 model rows lie east of 32.95° E | Add a point-in-polygon test with a national boundary file in a new audit version. Report the count |
| 6 | Same-coordinate Lacuna pairs | 7 pairs at the same point with different yields; 8 pairs within 10 m | They are already grouped. Add a robustness row without `near_dup_10m`, and note that the flag counts excluded neighbours too |
| 7 | Lacuna 2022 could now be recovered | v2 closed the 2022 imagery gap for Malawi with `sentinel-2-l2a`. Lacuna 2022 has 156 pure-stand rainfed rows in 6 units, 20 of them within 50 m of a 2023 point | If wanted, add it in a new labels version with v2 imagery, and score a Lacuna 2022 ↔ 2023 rank transfer like Malawi |
| 8 | Lacuna weight outliers | 7 rows with dry / wet below 0.3; 1 zero with condition `average`; 2 rows above 12 t/ha | A robustness row only. No edit |
| 9 | `Box used` export fault | 4,290 rows read "used box 1 and N", each with a different N (11 to 34,759). The label is not affected (it is the box mean on all of them) | None for the label. Tell the provider |
| 10 | The input checksum for Zimbabwe 2024 is not checked by step 3 | `check_against_raw` checks four raw files against `download_manifest.json`. `metadata.csv` is only in `vision_guided_yield_download_manifest.json` (it matches today) | Add `metadata.csv` to the step 3 check in the next labels version |
| 11 | The photo archive is not on disk | `data/raw/vision_guided_yield_estimation/` holds only `metadata.csv` and `README.md`; the manifest lists `q_field_photo.zip` | Run `python scripts/step1b_download_zimbabwe2024_labels.py` before any photo work |

## 3. Data quality issues, inconsistencies and methodological weaknesses

Checked on 7 November 2026, read-only, against `data/processed/labels_v1.parquet`, `data/v2/processed/labels_v2.parquet`,
both team databases (`data/cropyield.duckdb`, `data/v2/cropyield.duckdb`), the split files, the scripts and `results/`.
"Model rows" are the rows `load_xy` returns: `include_primary` and at least 4 clear months (v2: Malawi 2023 253, Kenya 3,977,
Lacuna 1,880, Malawi 2022 529, Zimbabwe 2024 2,458). Numbers are v2 unless a v1 value is given next to them.
Rows are ranked by how much the issue can move the current scores or how they are read.
Status: **open** = no fix yet; **handled** = a fix is in the code or data; **accepted** = known, kept on purpose, stated next to the results.

| ID | Area | Issue | Evidence | Impact on results | Mitigation in place | Status |
|---|---|---|---|---|---|---|
| Q-01 | evaluation | Place still predicts yield across the 2 km gap. The new-village split removes neighbours, not the region. | Yield correlation of field pairs, Lacuna: +0.37 at 0–2 km (7,819 pairs), +0.45 at 2–10 km (26,410), +0.25 at 10–50 km (145,556), −0.065 at 50–200 km. Kenya 2019: +0.71, +0.53, +0.17, −0.05. R1 (coordinates only) R² on `s1_cc2km`: Kenya 0.224 (v1) / 0.211, Lacuna 0.131 / 0.127, Malawi 2022 0.335. | Part of every R² is knowledge of the region. In Kenya R1 beats A1: A1 − R1 RMSE +0.159 (+0.077 to +0.256) in v1, +0.145 (+0.052 to +0.255) in v2. | Every arm is scored next to R1 on the same folds; rank inside clusters takes out the cluster-year mean; paired cluster bootstrap. | handled |
| Q-02 | labels | One small crop cut stands for the whole field. The noise ceiling is only an upper bound. | Malawi 2023 main 10 × 10 m cut vs nested 5 × 5 m cut: r = 0.904 on 260 fields; median ratio nested / main 1.169. The provider places the 5 × 5 m sub-plot in the south-west corner of the 10 × 10 m square and harvests it first, so the two cuts share no plants (`data/raw/malawi_metadata/mwi_cc_23.csv`). Zimbabwe 2024 box 1 vs box 2: r = 0.868 (2,416 rows). Kenya releases only the mean of two boxes; Lacuna and the public Malawi 2022 file give one value per field (`cut1_kg_ha`, `cut2_kg_ha` empty). | Label noise and input noise cannot be separated. An R² near 0.2 may be close to the real limit. | Ceiling table in `docs/EVALUATION.md`, read as an upper bound. | accepted |
| Q-03 | location | Point cohorts use one 10 m pixel, and the point accuracy is not known. | `downloads.aoi_type = point_pixel` with `field_pixels` = 1 for 8,315 of 9,097 model rows (Kenya, Lacuna, Zimbabwe 2024). The OAF workbook (`data/raw/one_acre_fund_full/one_acre_fund_mel_data_all_countries.xlsx`, sheet *Variables*) says that the field point "occassionally" (sic) "was taken from homestead or near the field", with no per-row flag. The 70 / 21 / 9 % split (field GPS / nearby town / district) is stated for the curated OAF release (Zenodo 11122388, parked on 25 Oct), not for our workbook. Kenya 2019 points lie a median 1.75 km from their site point, 141 more than 10 km (`site_distance_km`, on 1,706 of 1,768 rows; 2020 has no site points). Season NDVI max < 0.5: Kenya 285 (7.2 %), Lacuna 174 (9.3 %; v1 182), Zimbabwe 2024 918 (37.3 %). | Some labels sit on a pixel that is not the crop. In Kenya 2019 the signal falls with the distance to the site point (0.29 within 2 km, 0.07 beyond 5 km, `docs/DATA.md`). | `location_source` column; no row is dropped by a feature after the freeze; a 3 × 3 median for points is a planned stage-3 test. | open |
| Q-04 | labels | Cohorts, and the two Malawi seasons, use different crop-cut protocols. | `labels_v2`: Kenya mean of 2 boxes of 36 m²; Malawi 2023 1 cut of 100 m² at 13 % (stored as 100 m²; 75 or 100 m² is open, Q-24); Malawi 2022 mean of 2 cuts of 25 m²; Lacuna 1 cut of 40 m², "dry weight"; Zimbabwe 2024 mean of 2 boxes of 40 m². 4 of 5 cohorts store `moisture_basis_pct` as null. Malawi 2022 and 2023 medians: 2.418 and 2.440 t/ha. | t/ha and R² do not compare across cohorts or across the Malawi seasons. A pooled R² would be inflated by the cohort means. | One model per cohort; no pooled R²; Malawi season transfer scored by Spearman only. | handled |
| Q-05 | features | Season features include months after the harvest. | Used clear scenes dated after the label date (harvest date, else cut date; 89 Kenya rows have neither and are not counted): Kenya 19.5 %, Malawi 2023 19.0 %, Malawi 2022 20.6 %, Zimbabwe 2024 28.4 %, Lacuna 32.2 % (v1 32.8 %). Counted by whole month after the harvest month: Lacuna 23.6 % (v1 24.0 %), Kenya 13.3 %. The window is fixed per zone (`src/cropyield/data/cohorts.py`). | The 5 `*_season_mean` values also average these months, when the field may be cut or bare; they are half of the A1 inputs. Every score is an end-of-season estimate, not a forecast. | Fixed, label-free window by design. Both baseline tables print the scene shares as "Clear months after the cut", without the definition; the v1 table prints Kenya 19 %, but the measure gives 19.6 %. | open |
| Q-06 | evaluation | Malawi samples are small. | Malawi 2023: 251 (v1) / 253 model rows in 53 groups; 49–52 fields and 9–12 groups per fold; folds 1–4 score 204 fields in 44 clusters. Malawi 2022: 105–106 fields and 19–20 groups per fold; 423 scored in 78 clusters. Season transfer: 204 and 150 test fields. `docs/EVALUATION.md` asks for ≥ 100 test fields and ≥ 10 groups before a per-fold number. | Wide intervals: Malawi 2023 A1 − R1 rank +0.377 (+0.175 to +0.580). Two more fields in v2 change the scored set. | Pooled out-of-fold scores only; cluster bootstrap. | accepted |
| Q-07 | evaluation | Only the new-village split is scored. | `scripts/step8_run_baseline.py` and `scripts/step9_compare_data_v2.py` read only `*__s1_cc2km.csv` and `malawi_2022_2023__temporal_rank.csv`; no hit for `s2_region`, `random_diag` or `kenya_oaf_2019_2020__temporal`. | No new-region score and no Kenya new-season score yet. After Q-01, the new-village score is the optimistic one. | The other split files are frozen (`data/splits/manifest.json`), so they can be scored without change. | open |
| Q-08 | evaluation | Results carry a commit that does not hold the code that made them. | Every row of `results/baseline_scores.csv` (40), `results/v2/baseline_scores.csv` (53) and `results/v2/data_v2_comparison.csv` (27) has commit `a95c12c…-dirty`. `git ls-files` lists none of `scripts/step8_run_baseline.py`, `scripts/step9_compare_data_v2.py`, `src/cropyield/baselines.py`, `src/cropyield/eval/scores.py`, `results/`. `data/v2/splits/manifest.json` and the v2 `build_info` say `a95c12c` with no dirty flag; v1 `build_info` and `data/splits/manifest.json` say `96e2e81`. | No commit rebuilds any score. The frozen manifest and databases keep the stamp for good. | SHA-256 pins: labels and splits in the manifests; databases in `configs/team_database_v1.json` and `_v2.json`, checked by step 8 `--version 2` and step 9 (step 8 v1 does not check the v1 pin). | open |
| Q-09 | features | In the Malawi season transfer, the season means cover different months. | October and November are clear for 529 of 529 Malawi 2022 fields (older collection) and for 0 of 253 Malawi 2023 fields (`no_scene`). `ndvi_season_mean` median 0.339 (184 Malawi 2022 transfer fields) vs 0.464 (Malawi 2023); on December–June only 0.396 vs 0.464. 60.1 % of 2023 test fields lie above the training clip for `ndvi_season_mean` (audit of 7 Nov, first run). | Part of the shift between seasons is coverage, not crop, so A1 transfer is probably understated: on the 5 max features alone A1 ranks 0.335 / 0.467, against 0.316 / 0.451 for all 10 (first run, fold 0 included). | Rank-only scoring; R1 shown; the caveat is printed in `results/v2/data_v2_comparison.md`. | accepted |
| Q-10 | imagery | Clouds leave months empty, most in Malawi. | Cloudy field-months on model rows, v1 → v2: Kenya 566 → 390, Malawi 2023 396 → 353, Lacuna 1,150 → 945, Zimbabwe 2024 239 → 149; Malawi 2022 456. Malawi 2023 clear in March 52.6 % → 54.9 %, in December 46.2 % → 47.4 %. v1 tried 3 photos per month, v2 up to 24; tiles above 80 % cloud are never tried (`scripts/step5_download_imagery.py`). | `*_season_max` partly records which month was clear (Malawi 2023 without a clear March: NDVI max 0.63 vs 0.73, `docs/DATA.md`). More photos gave no win: A1 rank v2 − v1 Malawi 2023 −0.021 (−0.068 to +0.035), Kenya +0.001 (−0.003 to +0.004), Lacuna −0.006 (−0.012 to −0.001). | ≥ 4 clear months rule; the pre-registered v2 test of more photos. | handled |
| Q-11 | labels | The Lacuna unit is provisional. | `unit_provisional` is true only for Lacuna. t/ha = dry kg × 0.25 is checked against the GeoJSON (`check_against_raw`, `src/cropyield/data/labels.py`). Moisture basis and grain vs cob are not stated. | Lacuna RMSE in t/ha (A1 1.785) may be off by a constant factor. R² and ranks do not change with a constant factor. | Flag in the labels; note in both baseline tables. | accepted |
| Q-12 | labels | The Malawi 2022 unit is inferred, not stated by the provider. | The field dictionary (`data/raw/malawi_field_dictionary/mwi_cc_22_fieldnames.xlsx`) names the per-cut yields `yield_est_tons_p_ha`, but no provider file in the repo names `AVG_YLD` or its unit. All 529 values equal mean(2 × kernwt_i × (100 − mc_i) / 87) of the two 5 × 5 m cuts (max residual 0.0005), so t/ha at 13 % moisture; this used the advanced zip `mwi_mwi_lc_fo_202205_yield_v1.zip`, which is not in the repo, and the public file in the repo does not expose the individual cuts (`data/v2/audit/summary.json`). `labels_v2` stores `moisture_basis_pct` null and `unit_provisional` false. | Malawi 2022 RMSE (A1 1.551 t/ha) rests on the inference; ranks do not. | "inferred, not confirmed by the provider" in `results/v2/baseline_table.md`. | accepted |
| Q-13 | imagery | Catalogue gaps leave whole months with no photo (2022, early 2019). | `coverage.state = no_scene` on `include_primary` rows: 6,048 field-months in v1 and in v2 = Lacuna 3,760 (October–November 2022 × 1,880), Kenya 1,768 (February 2019), Malawi 2023 520 (October–November 2022 × 260); 6,030 (v1) / 6,034 on model rows. v1 Malawi 2022 had 2–4 clear months (517 of 529 had 3) and was dropped; v2 fills it from `sentinel-2-l2a` (5–9 clear months). | Lacuna and Malawi 2023 miss October–November, before or at planting (Lacuna: 1,212 of 1,880 planted in November 2022, 63 in October). Kenya 2019 has at most 7 months and 2020 has 8, so season means differ by year. | `no_scene` is kept apart from `cloudy`; Malawi 2022 filled in v2; the other gaps are left for a later go / no-go (`docs/DATA_V2_PLAN.md`). | accepted |
| Q-14 | location | Malawi 2022 datum: which Arc 1950 transformation. | Raw `.prj` is EPSG:20936. v1 used EPSG:1117 (27 m stated accuracy), v2 EPSG:1113 (44 m). v2 points sit a median 24 m west and 24 m north of v1 (median distance 34 m; range 23–48 m). Only 245 of 529 v2 points fall inside their v1 polygon (audit). The shift splits one cluster: 97 groups, not 96. | A 34 m shift is large next to a median field of 0.37 ha (about 60 m across), so features built on v1 positions read partly other pixels. | Label-free choice: within-field NDVI spread is lowest at −24 m E, +24 m N, which is EPSG:1113. The first hint came from a yield probe on 3 Nov; this is disclosed in `docs/DECISIONS.md`. v1 keeps Malawi 2022 out. | handled |
| Q-15 | splits | Fold 0 is kept back, but the first step 9 run scored fold-0 fields. | Owner ruling of 1 Nov. v1 (`results/baseline_table.md`) scores all 5 folds; R0, R1 and A1 were first seen on 30 Oct. v2 scores folds 1–4: Malawi 2023 204, Kenya 3,181, Lacuna 1,504, Malawi 2022 423 fields. The first step 9 run on 7 Nov also scored 83 fold-0 fields in the season transfer (49 Malawi 2023, 34 Malawi 2022; A1 0.316 / 0.451). | 34 Malawi 2022 fold-0 labels were seen once by A1 and R1. Without fold 0: A1 0.315 / 0.413, R1 0.102 / 0.155; A1 − R1 stays above 0 both ways. | `scripts/step9_compare_data_v2.py` drops fold-0 test fields and stops on other row counts (`TRANSFER_ROWS`); step 8 `--version 2` skips fold 0. | handled |
| Q-16 | imagery | Lacuna scenes from the next UTM zone are resampled in every band. | Scenes whose MGRS zone differs from the chip CRS, model rows: Lacuna 4,316 of 12,010 (35.9 %, v1) and 4,388 of 12,215 (35.9 %, v2); Zimbabwe 2024 12.2 % (v1) / 12.3 %; Kenya 0.7 %; Malawi 0. Bands are read through `WarpedVRT` (`scripts/step5_download_imagery.py`). | In about a third of Lacuna months the one point pixel mixes about 4 pixels: more noise, no bias (`notebooks/data_guide.ipynb`). | Counted in the guide; noted in both baseline tables. | accepted |
| Q-17 | features | Labels are stored next to the features. | Each chip `record.json` holds `record.yield_kg_ha` and the full `record.source_record`; `Chip.yield_kg_ha` loads it (`src/cropyield/satellite/chips.py`, line 116). View `monthly` repeats `labels.yield_kg_ha` on every field-month; `master` carries `labels.*` (`yield_kg_ha`, `source_yield`). | A sequence or chip model that reads these columns as X sees y. Sharing chips shares labels. | `load_xy` selects only the 10 named features; the audit found no change in any prediction when test y was scrambled. | open |
| Q-18 | splits | `labels.cluster_2km` is not the split group. | Lacuna `cluster_2km` is built over all 2,266 rows, the split `group_id` over the 1,880 primary rows: 272 vs 289 values, and 12 `cluster_2km` values span more than one fold. Zimbabwe 2024 (`cluster_2km` over all 4,332 rows): 956 vs 996, 27 span folds. Equal in Kenya (849), Malawi 2023 (53) and Malawi 2022 (97). `cluster_2km` is in neither database. | Grouping by `cluster_2km` gives a wrong fold map. No leak: each `group_id` lies inside one `cluster_2km`, and Lacuna fields in other folds are ≥ 2.0048 km apart (audit). | Steps 8 and 9 and `ridge_cv` group by `group_id`. | open |
| Q-19 | features | The v1 database holds Presto and MOSAIKS for Malawi 2022 from the old imagery; v2 holds none. | v1: 529 Malawi 2022 rows in `presto_embeddings` and `mosaiks_season`, built from 2–4 clear months. v2: 0 rows in `presto_embeddings`, `mosaiks_monthly` and `mosaiks_season`. `obs_id` is the same key in both files. | A join of v1 Presto or MOSAIKS onto v2 rows gives features of other imagery, with no error. Arms A2 and A3 cannot run on v2 yet. | None in code; `master` on v2 returns NULL in these columns. | open |
| Q-20 | splits | The Malawi season transfer is not a spatial holdout. | `malawi_2022_2023__temporal_rank.csv` builds 2 km groups over both seasons: 10 of 79 groups hold both seasons, and 28 of the 204 scored 2023 test fields (13.7 %) lie within 2 km of a 2022 training field (34 of all 260 split rows, 13.1 %). Only 184 of 529 Malawi 2022 fields (those within 20 km of a 2023 field) enter. | "New season" is partly "known place". R1 at 0.102 / 0.155 shows that place adds little here. | R1 on the same rows; without the test fields within 2 km, A1 − R1 stays above 0 (audit, first run). | accepted |
| Q-21 | labels | Kenya season window and dates. | The fixed window 1 Feb – 30 Sep ends before 850 recorded harvests (`date_outside_window`); 13 rows carry `impossible_date`; 89 rows have no harvest date. `ndvi_season_mean` 0.52 in 2019 vs 0.59 in 2020 (`docs/DATA.md`). | Season values differ between years for reasons other than yield. Kenya A1 R² inside each year: 0.077 (2019), 0.020 (2020). | Flags, not exclusions; rank inside clusters is centred per cluster and year. | accepted |
| Q-22 | location | Kenya has many repeated points. | 560 rows lie within 10 m of another row (`near_dup_10m`; 290 in 2019, 270 in 2020); 203 rows share 95 exact coordinates. Only 10 of 2,209 2020 fields lie within 10 m of a 2019 field, so most repeats are in the same season. | Different labels on what is probably the same pixel (likely homestead GPS, `docs/DATA.md`): noise in X. | Rows within 10 m share a cluster, so they always fall in the same fold. | accepted |
| Q-23 | labels | Zimbabwe Lacuna: what is cleaned out and what stays. | 2,266 maize rows → 1,880 primary: 169 rows of 2022 out (`dropped_year_2022_imagery_gap`; 156 pure stand), 212 intercropped and 5 irrigated rows of 2023 out. Kept and flagged: 28 zeros, 22 rows within 10 m of another, 2 harvests after the 30 Jun window end. `Admin1` has 20 units that mix districts, towns and one province. In v2 the 2022 reason is out of date: the older collection now covers 2022 (Malawi 2022 is in), and the reason that applies is the deferral in the next column. | The cohort name says 2022_2023, but only 2023 is modelled. A region split on `Admin1` mixes levels. | `exclusion_reason` on every row. Lacuna 2022 is deferred: 156 more fields would join clusters and change the 2023 folds (`docs/DATA_V2_PLAN.md`). | accepted |
| Q-24 | evaluation | Malawi 2023 sample frame and polygons. | Villages were chosen by Sentinel-2 NDVI strata (`docs/DATA.md`). 14 primary rows in 7 pairs of polygons overlap by more than 50 % (`polygon_overlap_dup`); 267 public rows vs 261 documented fields. The cut is "a nominal 10 x 10 m", and the data cannot settle 75 or 100 m² (`docs/DECISIONS.md`, 1 Nov). | Scores describe this sample, not the district. Overlapping pairs always share a fold. | Provider value `cc_ey_t` kept; note in both baseline tables. | accepted |
| Q-25 | labels | Zimbabwe 2024 zeros (parked cohort). | 1,874 of 4,332 rows are zero (43.3 %), with zero wet and dry weight; the zero share rises with the visit month, from 13 % in March to 100 % in July (`docs/DATA.md`). 918 of 2,458 positive model rows (37.3 %) never reach NDVI 0.5. 4,332 rows vs 4,173 fields in the paper. | Not used for scores. The positive rows are a biased sample of a drought year. | Zeros excluded; role `parked`. | accepted |
| Q-26 | imagery | One photo per month, and its date is not used. | Per month, photos are tried in tile-cloud order and the first one with SCL 4, 5 or 6 and all 10 bands valid on ≥ 80 % of the AOI pixels is kept; v1 tried ≤ 3, v2 ≤ 24. `scenes.acquired` is stored but is not a feature. | "February" can be early or late in the month; in a fast season this moves the value. | None. | accepted |
| Q-27 | features | Presto and MOSAIKS inputs (v1 database only). | Presto was pre-trained on Level-1C with radar, weather and elevation; we give it Level-2A with those inputs set to 0 and masked (`docs/DECISIONS.md`, 26 Oct). The MOSAIKS `chip` value averages the whole 640 m chip, so for a point it mostly sees the neighbours. | A frozen-Presto score may understate the model. A MOSAIKS chip score can carry place, like R1. | Neither is in the baseline tables; compare any such arm with R1. | accepted |
| Q-28 | imagery | Some Malawi 2022 polygons are very small. | `field_pixels` median 37, minimum 2; 16 of 529 fields have fewer than 9 pixels, 66 fewer than 18. Malawi 2023: minimum 18, median 59. | The median of a small field is close to a point value and includes edge pixels. | None. | accepted |
| Q-29 | splits | The 2 km rule is measured between field points, not polygon edges. | 2 cross-fold pairs of Malawi 2022 polygons (4 fields) have edges 1,967.9 m and 1,979.4 m apart; Malawi 2023 minimum 2,108.2 m (audit). | None on scores: chips are 640 m wide and features use only each field's own pixels. | None needed. | accepted |
| Q-30 | imagery | The older collection has a reflectance offset that changes between products. | 309 scenes (6 items, baseline 04.00, no `boa_offset_applied` flag) of the recovered Malawi 2022 chips from before v2 were stored 0.1 too low (`docs/DECISIONS.md`, 5 Nov), which voids the 3 Nov Malawi 2022 probe. v2 sets offset 0 only for the 4 measured (baseline, flag) pairs (`OLDER_OFFSET_ZERO`, `scripts/step5_download_imagery.py`) and rejects the rest: 1 item, `S2B_36LWL_20220322_1_L2A`, in 23 record-months. | A wrong offset shifts every band by 0.1 and breaks the indices. | Rule in code; no accepted v2 scene has an unmeasured pair (audit). | handled |
| Q-31 | features | MTCI has extreme tails. | Monthly MTCI on primary rows: Kenya −2,828 to 11,341 (median 3.3), Lacuna −3,344 to 627, Zimbabwe 2024 −8,634 to 868; Malawi 0.15 to 6.9. | Without a clip, Ridge would follow a few rows. | `Winsorize` clips each feature at its training 1st and 99th percentile inside the fold (`src/cropyield/baselines.py`). | handled |

Count: 7 open, 7 handled, 17 accepted.

## 4. Training, validation and test splits

Checked on 7 November 2026 against the split CSVs, both manifests, both databases (opened read-only) and the code of steps 4, 8 and 9. Every split is a CSV file that is made once and never edited. The v1 files were made on 30 Oct, before the first model. The v2 files were made on 5 Nov, before the first v2 score. The key is `obs_id`. There is one file per cohort and family: `<cohort>__<family>.csv`. The `temporal_rank` file is named after the cohort pair (`malawi_2022_2023`).

- Data v1: 13 files in `data/splits/`.
- Data v2: 17 files in `data/v2/splits/`. The 13 v1 files are byte for byte the same. Data v2 adds three Malawi 2022 files and `malawi_2022_2023__temporal_rank.csv`.

### 4.1 Roles: test, development, validation

| Role | What it is | Code | Rule |
|---|---|---|---|
| **Test** | `s1_cc2km` fold 0 of each cohort | none yet | Owner ruling of 1 Nov 2026: "No new arm is scored on it, in any split family." `docs/EVALUATION.md` and the step 8 note add that fold 0 is kept back for the end of the project. Fold-0 fields still train. |
| **Development** | cross-validation over `s1_cc2km` folds 1–4 | `out_of_fold(..., skip=("0",))` in `scripts/step8_run_baseline.py` | Each of folds 1–4 is the test fold once. Its model trains on the other four folds, fold 0 included. Scores use the pooled out-of-fold predictions of folds 1–4. |
| **Validation** (tuning) | inner `GroupKFold` on `group_id`, inside the training folds | `ridge_cv` in `src/cropyield/baselines.py` | `GridSearchCV` over the 17 Ridge penalties `np.logspace(-3, 5, 17)` with `GroupKFold(n_splits=min(5, training groups))` (no shuffle, scikit-learn 1.9.1), scored by `neg_mean_squared_error`. Clipping (training 1st and 99th percentile) and scaling are fit inside each inner fold. |

- **No validation file.** A model that needs a fixed validation set, for example to stop a GRU early, takes it from the training folds and keeps `group_id` groups whole (one inner `GroupKFold` split, say). Never take it from the outer test fold. Never use fold 0 alone as the validation set: a choice made on fold 0 is a score on fold 0.
- **Inner folds keep the 2 km gap.** In `s1_cc2km`, two fields in different groups are always more than 2 km apart. So inner-validation fields are also more than 2 km from inner-training fields. The audit of 7 Nov measured a minimum of 2.0026 km. With v2 model rows, each development fold trains on 41–43 groups (Malawi 2023), 679 (Kenya), 231 (Lacuna) or 77–78 (Malawi 2022). The season transfer trains on 36 groups (Malawi 2022) or 53 (Malawi 2023). So the inner search always has 5 folds.
- **Fold 0 is fresh only for new arms.** R0, R1, R2 and A1 were scored on fold 0 on 30 Oct. `results/baseline_table.md` scores all five folds, and so does `python scripts/step8_run_baseline.py` without `--version 2`. The first step 9 run of 7 Nov also scored 83 fold-0 fields in the season transfer (49 Malawi 2023, 34 Malawi 2022). Step 9 now drops these fields. Malawi 2022 yields were also used in a probe on 3 Nov, before its split existed (`docs/DECISIONS.md`, 5 and 7 Nov).
- **The final test has no code and no written protocol.** Every development model trains on fold-0 fields. To keep fold 0 unseen, the final model must train and tune on folds 1–4 only (inner `GroupKFold` on their `group_id`), then predict fold 0 once. No document says this yet. The owner must confirm it.

### 4.2 Split families

| Family | Files, v1 → v2 | Held-out unit (`group_id`) | `fold` values | Used by |
|---|---|---|---|---|
| `s1_cc2km` (new village) | 4 → 5 | 2 km single-linkage clusters of the `include_primary` rows | `0`–`4` | step 8, step 9 |
| `s2_region` (new region) | 4 → 5 | Kenya: `admin_unit` (50 districts). Lacuna: `admin_unit` (20 `Admin1` units). Malawi 2023: 5 km clusters (21). Zimbabwe 2024 and Malawi 2022: 20 k-means blocks on lat/lon | `0`–`4` | frozen, no script scores it |
| `temporal` (new season, Kenya only) | 1 → 1 | `admin_unit` (50) | `train` / `test`. Repeat 0 trains on 2019 and tests on 2020. Repeat 1 is the reverse. Extra column `test_subset` | frozen, no script scores it |
| `random_diag` (diagnostic) | 4 → 5 | each field is its own group | `0`–`4` | frozen, never a headline |
| `temporal_rank` (data v2 only) | 0 → 1 (`malawi_2022_2023`) | 2 km clusters over both seasons | `train` / `test`. Repeat 0 trains on Malawi 2022 and tests on 2023. Repeat 1 is the reverse | step 9, Spearman only |

The region units are in `REGION_UNITS` and `REGION_UNITS_V2` of `scripts/step4_build_splits.py`. The manifests store them too.

### 4.3 File columns

| Column | Content |
|---|---|
| `obs_id` | `dataset:source_id`. One row per field per repeat |
| `cohort` | the cohort. In `temporal_rank`, `malawi_2022` or `malawi_2023` |
| `season_year` | season year of the field |
| `cluster_id` | a copy of `labels.cluster_2km`. **This is not the held-out unit** |
| `group_id` | the unit that is held out as a whole. Group on this column |
| `fold` | `0`–`4`, or `train` / `test` |
| `repeat` | `0`. For `temporal` and `temporal_rank`: `0` and `1` |
| `family` | the family name |
| `test_subset` | `temporal` only: `seen_region` or `new_region` for test rows, empty for training rows |

- **Rows.** Every `include_primary` row of the cohort is in the file, also rows without imagery (`data/splits/README.md` says "every labels_v1 row"; that frozen file is wrong on this point). So a split never changes when imagery coverage changes. The exception is `temporal_rank`, which keeps only the Malawi 2022 fields within 20 km of a 2023 field (see 4.4). Models use the subset that `load_xy` returns, called "model rows": `include_primary` and at least 4 clear months.
- **Read the columns as text.** Use `dtype={"group_id": str, "fold": str}` and `keep_default_na=False`. If not, the empty `test_subset` becomes NaN, and in the numbered families `fold` and `group_id` become integers, so `fold == "0"` matches no row.
- **`cluster_id` is not `group_id`.** `labels.cluster_2km` is built over all rows of a cohort, excluded rows too. The `s1_cc2km` `group_id` is built over the `include_primary` rows only. In `s1_cc2km` the two are equal for Kenya, Malawi 2023 and Malawi 2022. They differ in two cohorts:
  - Lacuna: 2,266 rows, 1,880 primary. 272 `cluster_id` values against 289 groups, and 12 values hold fields of two folds.
  - Zimbabwe 2024: 4,332 rows, 2,458 primary. 956 values against 996 groups, and 27 values hold fields of two folds.
  - In `temporal_rank`, each season numbers its clusters separately. So 20 of the 70 `cluster_id` values hold fields of more than one group.

### 4.4 Counts per fold

Each cell gives fields / groups / model rows, for repeat 0. Fields are the rows of the file. Model rows are the `load_xy` rows of the matching database: `data/cropyield.duckdb` for v1 and `data/v2/cropyield.duckdb` for v2.

**`s1_cc2km`.** Fold 0 is the test fold.

| Cohort | Data | Fold 0 (test) | Fold 1 | Fold 2 | Fold 3 | Fold 4 | All |
|---|---|---|---|---|---|---|---|
| `kenya_oaf_2019_2020` | v1 = v2 | 796 / 169 / 796 | 796 / 170 / 796 | 795 / 170 / 795 | 795 / 170 / 795 | 795 / 170 / 795 | 3,977 / 849 / 3,977 |
| `malawi_2023` | v1 | 52 / 9 / 49 | 52 / 10 / 51 | 52 / 10 / 51 | 52 / 12 / 48 | 52 / 12 / 52 | 260 / 53 / 251 |
| `malawi_2023` | v2 | 52 / 9 / 49 | 52 / 10 / 51 | 52 / 10 / 51 | 52 / 12 / 50 | 52 / 12 / 52 | 260 / 53 / 253 |
| `zimbabwe_lacuna_2022_2023` | v1 = v2 | 376 / 57 / 376 | 376 / 58 / 376 | 376 / 58 / 376 | 376 / 58 / 376 | 376 / 58 / 376 | 1,880 / 289 / 1,880 |
| `malawi_2022` | v2 only | 106 / 19 / 106 | 106 / 19 / 106 | 106 / 20 / 106 | 106 / 20 / 106 | 105 / 19 / 105 | 529 / 97 / 529 |
| `zimbabwe_2024` (parked) | v1 = v2 | 492 / 199 / 492 | 492 / 199 / 492 | 492 / 200 / 492 | 491 / 199 / 491 | 491 / 199 / 491 | 2,458 / 996 / 2,458 |

- **Development set in v2 (folds 1–4), model rows:** Malawi 2023 has 204 (of 208 fields) in 44 groups, Kenya 3,181 in 680, Lacuna 1,504 in 232 and Malawi 2022 423 in 78. These numbers equal the Fields and Clusters columns of `results/v2/baseline_table.md`.
- **v1:** `results/baseline_table.md` scores all five folds, with 251, 3,977 and 1,880 model rows.
- **Malawi 2023, v1 → v2:** 2 fields in fold 3 reach 4 clear months only in v2, so its model rows go from 251 to 253.

The distances below are between the fields of the file (all rows, not only model rows).

| Cohort | Smallest test-to-training distance per fold 0 / 1 / 2 / 3 / 4, km | Group size: median, largest |
|---|---|---|
| `kenya_oaf_2019_2020` | 2.0036 / 2.0047 / 2.0058 / 2.0026 / 2.0026 | 2, 168 |
| `malawi_2023` | 2.2401 / 2.2401 / 2.6471 / 2.2144 / 2.2144 | 4, 22 |
| `zimbabwe_lacuna_2022_2023` | 2.0108 / 2.0108 / 2.0048 / 2.0087 / 2.0048 | 2, 65 |
| `malawi_2022` | 2.2032 / 2.0333 / 2.0333 / 2.1160 / 2.0899 | 4, 23 |
| `zimbabwe_2024` | 2.0040 / 2.0040 / 2.0053 / 2.0053 / 2.0059 | 1, 30 |

**`s2_region`.** There is no distance buffer.

| Cohort | Unit (groups) | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 |
|---|---|---|---|---|---|---|
| `kenya_oaf_2019_2020` | `admin_unit` (50) | 800 / 10 / 800 | 798 / 10 / 798 | 797 / 10 / 797 | 794 / 10 / 794 | 788 / 10 / 788 |
| `malawi_2023` | 5 km clusters (21) | 62 / 1 / 54 (v2: 56) | 50 / 4 / 49 | 51 / 5 / 51 | 49 / 6 / 49 | 48 / 5 / 48 |
| `zimbabwe_lacuna_2022_2023` | `admin_unit` (20) | 378 / 2 / 378 | 375 / 3 / 375 | 377 / 5 / 377 | 372 / 5 / 372 | 378 / 5 / 378 |
| `malawi_2022` (v2) | `kmeans20` (20) | 106 / 4 / 106 | 107 / 4 / 107 | 106 / 4 / 106 | 109 / 4 / 109 | 101 / 4 / 101 |
| `zimbabwe_2024` | `kmeans20` (20) | 487 / 4 / 487 | 497 / 4 / 497 | 471 / 4 / 471 | 508 / 4 / 508 | 495 / 4 / 495 |

- **Fold-0 fields in these test folds.** Each `s2_region` test fold holds model rows of `s1_cc2km` fold 0 (v2), per fold 0 / 1 / 2 / 3 / 4. A new arm must not score these rows.
  - Kenya: 134 / 228 / 113 / 150 / 171
  - Malawi 2023: 23 / 1 / 8 / 15 / 2
  - Lacuna: 81 / 73 / 124 / 35 / 63
  - Malawi 2022: 22 / 14 / 27 / 29 / 14
  - Zimbabwe 2024: 142 / 104 / 89 / 80 / 77
- **Distance from each test field to the nearest training field** (all fields of the file, v2). Medians: Kenya 4.58 km, Malawi 2023 9.71, Lacuna 33.39, Malawi 2022 12.41, Zimbabwe 2024 38.62.
  - Share of test fields under 2 km: Kenya 20.3 %, Malawi 2023 0 %, Lacuna 0.2 %, Malawi 2022 1.1 %, Zimbabwe 2024 0.4 %.
  - Smallest distance: Kenya 0.003 km, Malawi 2023 5.095, Lacuna 1.668, Malawi 2022 0.893, Zimbabwe 2024 0.260.
- **Small groups per fold.** Folds hold 1–6 groups, except in Kenya (10). `docs/EVALUATION.md` asks for at least 100 test fields and at least 10 groups before per-fold numbers are reported. So only Kenya can report `s2_region` per fold. A cluster bootstrap on the pooled predictions draws from only 20–21 groups outside Kenya.

**`temporal`** (Kenya, v1 = v2). Model rows equal fields. Groups are districts.

| Repeat | Train | Test | Test `seen_region` | Test `new_region` | Test rows in `s1_cc2km` fold 0 | Test within 2 km of a training field |
|---|---|---|---|---|---|---|
| 0 | 2019: 1,768 / 39 | 2020: 2,209 / 50 | 1,849 / 39 | 360 / 11 | 430 | 37.7 % (median 2.79 km) |
| 1 | 2020: 2,209 / 50 | 2019: 1,768 / 39 | 1,768 / 39 | 0 | 366 | 52.3 % (median 1.92 km) |

This is a new season, not a new place. The smallest test-to-training distance is 0.001 km in both repeats.

**`random_diag`.** Each field is its own group. Fields per fold 0 / 1 / 2 / 3 / 4:
- Kenya 796 / 796 / 795 / 795 / 795
- Malawi 2023 52 each. Model rows: v1 50 / 50 / 52 / 50 / 49, v2 51 / 50 / 52 / 51 / 49
- Lacuna 376 each
- Malawi 2022 106 / 106 / 106 / 106 / 105
- Zimbabwe 2024 492 / 492 / 492 / 491 / 491

Model rows equal fields, except in Malawi 2023.

**`temporal_rank`** (v2, `malawi_2022_2023__temporal_rank.csv`). The file has 888 rows: 444 fields, twice. These are the 184 of the 529 Malawi 2022 fields that lie within 20 km of a 2023 field, and all 260 Malawi 2023 fields. The fields form 79 groups, and 10 groups hold fields of both seasons.

| Repeat | Train | Test | Test model rows in their own `s1_cc2km` fold 0 | Scored test rows | Test within 2 km of a training field (all test fields) |
|---|---|---|---|---|---|
| 0 | Malawi 2022: 184 / 36 / 184 | Malawi 2023: 260 / 53 / 253 | 49 (52 fields) | 204 fields, 44 groups | 13.1 % (34 of 260), median 5.85 km |
| 1 | Malawi 2023: 260 / 53 / 253 | Malawi 2022: 184 / 36 / 184 | 34 | 150 fields, 30 groups | 20.1 % (37 of 184), median 5.23 km |

- The scored counts equal `TRANSFER_ROWS` in `scripts/step9_compare_data_v2.py` and the counts in `results/v2/data_v2_comparison.md`.
- Some scored test fields share a group with a training field of the other season: 36 of the 204, and 43 of the 150. So this test is a new season at partly the same places. It is not a spatial holdout.

### 4.5 How the splits were made

- `python scripts/step4_build_splits.py` builds the v1 files from `labels_v1`. `python scripts/step4_build_splits.py --version 2` builds the v2 files from `labels_v2`. Both keep the `include_primary` rows and call `src/cropyield/eval/splits.py`. The seed is `20261029` and there are 5 folds.
- `connected_clusters` turns each lat/lon into a 3-D point on a sphere of radius 6,371.0088 km. A KD-tree finds every pair within the chord of 2 km. The connected parts of that graph are the groups. This works as a chain: if A–B and B–C are within 2 km, A, B and C are one group.
- `assign_folds` (greedy) works in four steps:
  1. Count the fields of each group.
  2. Shuffle the groups with `np.random.default_rng(20261029)`.
  3. Sort the groups by size, largest first. Ties keep their shuffled order.
  4. Put each group into the fold that has the fewest fields so far.
- `s2_region` uses the same `assign_folds` on its units. K-means is `KMeans(20, n_init=10, random_state=20261029)` on lat/lon degrees. Malawi 2023 uses connected clusters at 5 km.
- `random_diag` is `default_rng(20261029).permutation(n) % 5`.
- `temporal` sets `train` for the training year. `test_subset` is `seen_region` when the district also has fields in the training year.
- `temporal_rank` takes the Malawi 2022 fields within 20 km of any 2023 field, and every 2023 field. Then it makes 2 km clusters over both seasons.
- **Frozen.** Step 4 never changes an existing file or manifest, and it stops if a rebuild would differ. `--version 2` also checks that each of the 13 v1 files is byte for byte the same as in `data/splits/`. On a complete copy, step 4 ends with "unchanged" and writes nothing.
- **Reproduced on 7 Nov.** An in-memory rebuild with the step 4 code gave all 13 v1 files from `labels_v1` and all 17 v2 files from `labels_v2`, byte for byte. Nothing was written.
- **The v2 code is not committed yet.** `src/cropyield/eval/splits.py` at HEAD (`a95c12c`) has no `temporal_rank`, and `scripts/step4_build_splits.py` at HEAD has no `--version` option. So the v2 files can be rebuilt only from the uncommitted working tree.

### 4.6 Frozen hashes

| File | SHA-256 | What it pins |
|---|---|---|
| `data/splits/manifest.json` | `b8abf5e47c59d7e6c93620742de65ca5ba6a332d3a701eedc61a67d2533af53f` | `labels_v1` `49aae383c4489aa98e9e7fe8c31cda6bf1cd752adc8e9540cffdc147a5e0ef92`. Generator commit `96e2e81`. The git tag `splits-v1` (`32f4a42`, child of `96e2e81`) holds the same 13 split files and manifest |
| `data/v2/splits/manifest.json` | `172e6616ec2053383d4a146463c9a2a2f581a388efe1594d9436ce8a501513d2` | `labels_v2` `2b157317bd5af770e1347aaea82c8f6986bb5f92b13a4dacc0c81a3ba8669b1a`. Generator commit `a95c12c`: this is HEAD, without the uncommitted v2 code (step 4 records `git rev-parse HEAD`, with no dirty flag). `v1_manifest_sha256` = the v1 manifest above |

The per-file hashes below are the first 16 hex digits. The full values are in `manifest.json`. On 7 Nov all 30 files matched their manifests.

| File | SHA-256 (first 16) | Rows | In |
|---|---|---:|---|
| `kenya_oaf_2019_2020__s1_cc2km.csv` | `752e4ac95980eea5` | 3,977 | v1, v2 |
| `kenya_oaf_2019_2020__s2_region.csv` | `93a6102262294f18` | 3,977 | v1, v2 |
| `kenya_oaf_2019_2020__temporal.csv` | `dd0c3cc68f24ecf1` | 7,954 | v1, v2 |
| `kenya_oaf_2019_2020__random_diag.csv` | `db6247d269334bf6` | 3,977 | v1, v2 |
| `malawi_2023__s1_cc2km.csv` | `d7536035db17f25e` | 260 | v1, v2 |
| `malawi_2023__s2_region.csv` | `a12cdbf1b55c9731` | 260 | v1, v2 |
| `malawi_2023__random_diag.csv` | `b65cab99d548bc5b` | 260 | v1, v2 |
| `zimbabwe_lacuna_2022_2023__s1_cc2km.csv` | `253f437d30a37427` | 1,880 | v1, v2 |
| `zimbabwe_lacuna_2022_2023__s2_region.csv` | `da357af13e1fa78d` | 1,880 | v1, v2 |
| `zimbabwe_lacuna_2022_2023__random_diag.csv` | `d6dc5bc2e16ad5fb` | 1,880 | v1, v2 |
| `zimbabwe_2024__s1_cc2km.csv` | `f96a188ad708c2fe` | 2,458 | v1, v2 |
| `zimbabwe_2024__s2_region.csv` | `5fb70cec3dc6cf79` | 2,458 | v1, v2 |
| `zimbabwe_2024__random_diag.csv` | `3a16126c2bedb7b8` | 2,458 | v1, v2 |
| `malawi_2022__s1_cc2km.csv` | `b8a877cde664503e` | 529 | v2 |
| `malawi_2022__s2_region.csv` | `d393be5c46da47ac` | 529 | v2 |
| `malawi_2022__random_diag.csv` | `97a47d89a42bee3e` | 529 | v2 |
| `malawi_2022_2023__temporal_rank.csv` | `2b03602604f08e1a` | 888 | v2 |

### 4.7 Checks

| Check | Where | Result on 7 Nov |
|---|---|---|
| Each `obs_id` once per repeat, and exactly the `include_primary` rows (for `temporal_rank`, step 4 passes the file's own rows, so only "once per repeat" is tested) | `check_split` in `src/cropyield/eval/splits.py` | no problem in all 13 v1 and 17 v2 files |
| No `group_id` in two folds (skipped for `temporal` and `temporal_rank`, where groups span train and test by design) | `check_split` | 0 groups in two folds |
| `s1_cc2km`: every test field at least 2 km from every training field | `check_split`, with `nearest_km` | smallest distance 2.0026 km |
| Hashes equal the manifest | step 4 (rebuild). `tests/test_splits.py` (v1 files only). Step 8 `check_frozen` (`s1_cc2km` files). Step 9 (`s1_cc2km` files of v1 and v2, and `temporal_rank`) | all equal |
| No test label reaches a prediction | audit of 7 Nov: test y replaced by random values, step 8 folds 1–4, 4 cohorts | R0, R1 and A1 predictions change by 0.0 |

The 2 km rule is measured point to point, on the labels `lat`/`lon`. For Malawi this point lies inside the polygon (529 of 529 in 2022, 260 of 260 in 2023). Edge to edge, two pairs of Malawi 2022 fields in different folds (4 fields) are 1,967.9 m and 1,979.4 m apart (UTM 36S). In Malawi 2023 the smallest edge-to-edge gap is 2,108.2 m. Each chip is 64 × 64 pixels of 10 m (640 m wide), centred on the labels point. Two chips can overlap only when their points are less than 1 km apart, so the chips of fields in different folds share no pixel.

### 4.8 How to use them

Run this from the repository root. It reproduces the Malawi 2022 A1 row of `results/v2/baseline_table.md`: 423 fields, 78 groups, RMSE 1.551.

```python
from pathlib import Path
import numpy as np
import pandas as pd
from cropyield.baselines import ridge_cv
from cropyield.data.xy import load_xy

DATA = Path("data/v2")                         # data v2; Path("data") for v1
cohort = "malawi_2022"

X, y = load_xy(cohort, DATA)                   # model rows: include_primary and >= 4 clear months
split = pd.read_csv(DATA / "splits" / f"{cohort}__s1_cc2km.csv",
                    dtype={"group_id": str, "fold": str}, keep_default_na=False)
fields = split.set_index("obs_id").loc[y.index]   # join on obs_id, never by row position
assert fields.index.equals(y.index)

predicted = pd.Series(np.nan, index=y.index)
for fold in ["1", "2", "3", "4"]:              # development folds; fold 0 is the kept-back test
    test = (fields["fold"] == fold).to_numpy()
    train = ~test                               # fold-0 fields train
    predicted[test], alpha = ridge_cv(X[train].to_numpy(), y[train].to_numpy(),
                                      fields["group_id"].to_numpy()[train],   # inner GroupKFold groups
                                      X[test].to_numpy(), np.logspace(-3, 5, 17))

# Any other family: drop s1_cc2km fold-0 fields from the scored test rows.
s1 = pd.read_csv(DATA / "splits" / f"{cohort}__s1_cc2km.csv", dtype=str, keep_default_na=False)
kept_back = set(s1.loc[s1["fold"] == "0", "obs_id"])
```

**Rules**

- **One model per cohort.** Never pool cohorts. Never compare t/ha or R² across cohorts.
- **Malawi 2022 and Malawi 2023 are never pooled in t/ha.** Their crop cuts differ. Score `temporal_rank` by Spearman only.
- **`random_diag` is never in a headline.** Report it only as a labelled diagnostic.
- **Group by the `group_id` of the split file.** Never by row position. Never by `labels.cluster_2km` or the `cluster_id` column of the split file: in Lacuna 12 of those values, and in Zimbabwe 2024 27, hold fields of two folds, and in `temporal_rank` 20 values hold fields of more than one group.
- **Fold 0:**
  - Do not score a new arm on `s1_cc2km` fold 0.
  - Drop its fields from the test rows of `s2_region`, `temporal`, `random_diag` and `temporal_rank` too.
  - Do not add a new arm to the v1 path of step 8, because that path scores all five folds.
- **Do not mix the versions.** Use v1 split files with `data/` and v2 split files with `data/v2/`. The `obs_id` values are the same in both, but the database features are not.
- **Compare arms on the same rows.** Use the rows that all compared arms can predict. Use paired intervals over whole groups.
- **Report per fold only when a fold has at least 100 test fields and at least 10 groups.** Otherwise report the pooled scores only. Malawi 2023 is always pooled-only.
- **Name the place signal.** `s2_region`, `temporal` and `temporal_rank` have no distance buffer (see 4.4). Show R1 (coordinates alone) next to every model on the same split.

## 5. Codebase and pipeline


### 5.1 One row per script

Run every command from the repository root. "Frozen" means that the script refuses to change an existing output. Every data v2 switch in the last column (`--version 2`, `--only`, `--out-dir`, `--datum-operation`, `--collection`, `--base-run`, `--catalog-dir`) is in uncommitted changes: HEAD `a95c12c` has none of them.

| Script | What it does | Inputs | Outputs | Frozen | Data v2 switch |
|---|---|---|---|---|---|
| `scripts/step1_download_labels.py` | Downloads OAF full (Harvest Portal `oaf_mel`), OAF curated (Zenodo 11122388), Lacuna (Zenodo 10060610) and Malawi (3 Harvest Portal packages). Standard library only. A file already on disk is not downloaded again: its size (and the MD5, for Zenodo files) is checked, and a mismatch goes into the `errors` list of the manifest. It rewrites `download_manifest.json` on every run. | network | `data/raw/`, `data/metadata/*.json`, `data/metadata/download_manifest.json` | no; the outputs are committed | none |
| `scripts/step1b_download_zimbabwe2024_labels.py` | Downloads Zenodo 17626117: `metadata.csv`, and the 4.9 GB photo zip unless `--metadata-only`. It checks the licence and the MD5. | network | `data/raw/vision_guided_yield_estimation/`, `data/metadata/vision_guided_yield_download_manifest.json`, `zenodo_17626117_record.json` | no; the outputs are committed | none |
| `scripts/step2_audit_labels.py` | Screens the maize rows: a finite yield of 0 or more, valid coordinates or a valid polygon, inside a country envelope, exact duplicates removed. Extra checks: yield above 30 t/ha, per-acre against per-ha above 1 %, the Lacuna 40 m² conversion, dry weight above wet weight. Drops the OAF Uganda 2020 site coordinates. Moves the Malawi polygons to WGS84. Offline. | `data/raw/` | `data/audit/` (17 files) | no; it overwrites `data/audit/` | `--only malawi_2022 --out-dir data/v2/audit --datum-operation EPSG:1113` → `data/v2/audit/` (4 files). It refuses `--only` or `--datum-operation` into `data/audit/` |
| `scripts/step3_build_labels.py` | Builds the labels table from the screened CSVs and the raw files (OAF district, site and `plot_acres`; Lacuna `Admin1` and `Field_Irri`). It runs the checks and prints the SHA-256. The OAF workbook takes about a minute. | `data/audit/`, `data/raw/`, `data/metadata/download_manifest.json` | `data/processed/labels_v1.parquet` | yes: if the file exists, it only confirms the same bytes, else it stops | `--version 2` → `data/v2/processed/labels_v2.parquet`, with Malawi 2022 from `data/v2/audit/`. It also checks that v2 equals v1 outside Malawi 2022, and that only 11 allowed columns change inside it |
| `scripts/step4_build_splits.py` | Writes `s1_cc2km`, `s2_region` and `random_diag` for each cohort, and `temporal` for Kenya. Seed 20261029, 5 folds. It runs `check_split` on each file. | the labels parquet | `data/splits/*.csv`, `data/splits/manifest.json` | yes: it stops if a file or the manifest would change | `--version 2` → `data/v2/splits/`. It rebuilds the v1 files and requires them to be byte-equal. It adds the Malawi 2022 files and `temporal_rank`, and the manifest records the SHA of the v1 manifest |
| `scripts/step5_download_imagery.py` | `plan` (offline) or `download`. Searches Earth Search STAC and writes 64 × 64 chips at 10 m with 10 bands. Defaults: at most 12 scenes and one accepted scene per month, 3 candidates per month, tile cloud ≤ 80 %, clear share over the field ≥ 0.8, collection `sentinel-2-c1-l2a`. | `data/audit/`, a window CSV, network | `<output-dir>/run-<config hash>/records/<dataset>__<source_id>__<hash>/` (`record.json`, `aoi_mask.tif`, and one folder per scene with `scene.json`, `reflectance.tif`, `scl.tif`, `valid_mask.tif`), `plan-*.json`, `catalog_cache/` | no; the chips are git-ignored. `configs/sentinel2_scenes_v1.parquet` and `_v2.parquet` record the accepted scenes, but only the v1 list is compared by code | no `--version`. `--collection sentinel-2-l2a` (offset 0 only for 4 measured (processing baseline, offset flag) pairs), `--base-run <run folder>` (top-up: hard-link the accepted scenes, try only the untried candidates), `--catalog-dir`, `--candidates-per-month 24` |
| `scripts/get_all_data.py` | Wraps step 5 in 4 steps: it checks the audit files, writes the window file (fixed cohort windows), calls step 5 `download --only-listed`, and prints a summary. Options: `--scope pilot\|cohorts\|all`, `--batch i/n`, `--plan`, `--status`. The default is the 48-record pilot. | `data/audit/` | `configs/sentinel2_windows_pilot48.csv` (pilot) or `data/imagery/sentinel2/windows/`, and the chips | no | none: v1 only |
| `scripts/step6_build_database.py` | Rebuilds the database from scratch. It reads the labels (audit CSVs, plus the include flags from the parquet) and the chips (a folder counts only if its window equals the season window; the newest `record.json` wins). It reads MOSAIKS if the parquet files exist. It leaves Presto empty. It refuses a target file that holds Presto rows. `--workers` sets the processes. | `data/audit/`, the labels parquet, `data/imagery/sentinel2/`, `data/features/mosaiks/`, `sql/` | `data/cropyield.duckdb` | no; the team copy is pinned instead | `--version 2` → `data/v2/cropyield.duckdb` from `data/v2/audit/` (Malawi 2022), `data/imagery/sentinel2_v2` and `data/features/mosaiks_v2`. It refuses every v1 path. It overwrites the v2 team copy without a warning, because that file holds no Presto rows. The v2 build took 4,980.3 s (`data/imagery/sentinel2_v2/logs/step6_v2.log`) |
| `scripts/step7_check_data.py` | Read-only report on the model rows: coverage, the clear share per month, feature ranges, haze, the greenest month, and the Spearman with yield per cohort-year. | the database, the labels parquet | stdout | – | `--version 2` (the `labels_v2` rows on the v2 database) |
| `src/cropyield/data/xy.py` `load_xy` | X (the 10 season features) and y (t/ha) of one cohort: `include_primary` and at least 4 clear months, sorted by `obs_id`. | `<data_dir>/cropyield.duckdb` (argument, else `CROPYIELD_DATA_DIR`, else `data/`) | `(X, y)` | – | `load_xy(cohort, Path("data/v2"))` |
| `scripts/step8_run_baseline.py` | R0 (training mean), R1 (10 nearest fields by coordinates) and A1 (Ridge; winsorize and scale inside the fold; alpha from 17 values 1e-3 to 1e5, chosen by `GroupKFold` on `group_id` inside the training folds) on `s1_cc2km`, for Malawi 2023, Kenya and Lacuna. Zimbabwe 2024 is not scored. Cluster bootstrap with 2,000 draws. It stops on a changed labels or split hash, a wrong row count (v1: 251 / 3,977 / 1,880), or a y that differs from the parquet. It does not check the v1 database pin. | the database, the labels parquet, `data/splits/` | `results/baseline_table.md`, `results/baseline_scores.csv` (all 5 folds scored) | – | `--version 2`: adds Malawi 2022, also checks the v2 database pin, expects 253 / 3,977 / 1,880 / 529 rows, scores folds 1–4 only (fold 0 trains), and writes `results/v2/` |
| `scripts/step9_compare_data_v2.py` | Data v2 only. (1) A1 on v2 minus A1 on v1, on the same fields, folds 1–4. (3) Malawi season transfer 2022 ↔ 2023, Spearman only, with fold-0 test fields not scored (train/test 184/204 and 253/150). It checks both database pins, the labels and split hashes, the `temporal_rank` hash and the row counts. | both databases, both label files, both split folders | `results/v2/data_v2_comparison.md`, `.csv` | – | – |

### 5.2 The package `src/cropyield/`

| Module | What it provides |
|---|---|
| `__init__.py` | `ROOT`, the repository root |
| `longpath.py` | `filesystem_path`, `path_exists`, `replace_file`: Windows paths of 248 characters or more, and renames retried while OneDrive locks a file |
| `data/cohorts.py` | `Cohort`, `COHORTS` (5 cohorts with audit dataset, years, country, fixed window, Kenya intercrop filter), `season_window`, `obs_id`, `load_cohort` (screened CSV → cohort rows), `date_overrides` |
| `data/labels.py` | `MEASUREMENTS` and `MEASUREMENTS_V2` (one yield definition per cohort), `EXPECTED_ROWS`, `build_labels`, `exclusion_reasons`, `check_labels`, `check_against_raw`, `LABELS_PATH`, `LABELS_V2_PATH`, `audit_dir` (v2 Malawi 2022 must come from an EPSG:1113 audit) |
| `data/database.py` | `connect` (read-only, always the v1 file `data/cropyield.duckdb`), `run_query` (runs `sql/queries/<name>.sql`), `scene_differences` (local scenes against `configs/sentinel2_scenes_v1.parquet` by default), `wide` (array column → numbered columns) |
| `data/xy.py` | `load_xy`, `FEATURES` (10), `MIN_CLEAR_MONTHS = 4` |
| `satellite/records.py` | `match_downloads` (chip folder ↔ labelled row, exact window, newest wins), `RecordScan`, `field_mask` |
| `satellite/chips.py` | `read_chip`: one record folder → `Chip` with scenes, the all-touched mask and the pixel-centre mask |
| `satellite/monthly.py` | `monthly_series`: the median field reflectance per band and month; NaN where no clear field pixel |
| `features/indices.py` | `vegetation_indices`: NDVI, GCVI, MTCI, NDVI705, NDVI740 (Lobell et al. 2020, Table 2) |
| `eval/splits.py` | `SEED = 20261029`, `FOLDS = 5`, `connected_clusters`, `assign_folds`, `new_village`, `new_region`, `new_season`, `random_diagnostic`, `temporal_rank`, `check_split` |
| `eval/scores.py` | `rmse`, `r2`, `spearman`, `rank_inside_clusters`, `group_draws`, `paired_difference_ci` (2,000 cluster-bootstrap draws) |
| `baselines.py` | `Winsorize` (1st and 99th training percentile), `train_mean` (R0), `coordinates_knn` (R1), `ridge_cv` (A1) |

Other code: `sql/schema.sql` (the 10 tables, every column commented), `sql/views.sql` (the 3 views), and `sql/queries/` with 4 saved queries: `coverage_by_cohort`, `modelling_table`, `monthly_series`, `table_overview`. The notebooks: `notebooks/data_guide.ipynb` (committed, 118 cells, checks the v1 pin in Step 2). Not committed yet: `duckdb_v1_tour.ipynb` (32 cells), `step3_labels_walkthrough.ipynb` (24), `step4_splits_walkthrough.ipynb` (22) and `zimbabwe_master.ipynb` (5). The code that made the Presto and MOSAIKS rows of the v1 team database is in `_parked/` (`_parked/MANIFEST.csv`).

### 5.3 Reproduce from scratch

v1. Network steps are marked. Build into a new database path if the team copy is already at `data/cropyield.duckdb`: step 6 refuses a file that holds Presto rows.

```bash
python scripts/step1_download_labels.py                              # network; checks the files on disk, rewrites data/metadata/download_manifest.json
python scripts/step1b_download_zimbabwe2024_labels.py --metadata-only  # network
python scripts/step2_audit_labels.py                                 # offline; rewrites data/audit/, then check git status
python scripts/step3_build_labels.py                                 # confirms labels_v1 byte for byte, or stops
python scripts/step4_build_splits.py                                 # confirms data/splits/ byte for byte, or stops
python scripts/get_all_data.py --scope all --batch 1/32              # network; run slices 1/32 ... 32/32 in parallel
python scripts/step6_build_database.py --workers 8                   # data/cropyield.duckdb (or --db <other path>)
python scripts/step7_check_data.py
python scripts/step8_run_baseline.py                                 # results/
```

Data v2 (it needs the v1 chips for the top-up):

```bash
python scripts/step2_audit_labels.py --only malawi_2022 --out-dir data/v2/audit --datum-operation EPSG:1113
python scripts/step3_build_labels.py --version 2
python scripts/step4_build_splits.py --version 2
# before the downloads: the two window files and the v2 catalogue cache (see the note below the block)
# top-up of the cloudy months: all v1 records except Malawi 2022 (10,835), with OPENBLAS_NUM_THREADS=1, in 32 parallel slices (--offset 0, 339, 678, ... --limit 339)
python scripts/step5_download_imagery.py download --date-overrides data/imagery/sentinel2_v2/windows/sentinel2_windows_v2_topup.csv --only-listed --datasets one_acre_fund_full zimbabwe malawi_2023 vision_guided_yield_estimation --output-dir data/imagery/sentinel2_v2 --catalog-dir data/imagery/sentinel2_v2/catalog_cache --base-run data/imagery/sentinel2/run-517bfcf0a69c6cac --candidates-per-month 24 --offset 0 --limit 339
# Malawi 2022 from the older collection, on the EPSG:1113 polygons (529 records), in 32 slices (--limit 17), then the same command again in 16 slices (--limit 34)
python scripts/step5_download_imagery.py download --datasets malawi_2022 --audit-dir data/v2/audit --date-overrides data/imagery/sentinel2_v2/windows/sentinel2_windows_v2_malawi_2022.csv --only-listed --collection sentinel-2-l2a --candidates-per-month 24 --output-dir data/imagery/sentinel2_v2 --catalog-dir data/imagery/sentinel2_v2/catalog_cache --offset 0 --limit 17
python scripts/step6_build_database.py --version 2 --workers 8      # overwrites data/v2/cropyield.duckdb; pass --db <other path> to keep the team copy. scripts/README.md says to set OPENBLAS_NUM_THREADS=1
python scripts/step7_check_data.py --version 2
python scripts/step8_run_baseline.py --version 2                    # results/v2/; runs only on the pinned team copy
python scripts/step9_compare_data_v2.py                             # results/v2/data_v2_comparison.*; runs only on both pinned team copies
```

These are the exact commands of 5 Nov; a helper outside the repository started the slices. Before them: (1) the top-up window file is `data/imagery/sentinel2/windows/sentinel2_windows_all.csv` without its 529 Malawi 2022 rows, and the Malawi 2022 window file is those 529 rows without the `cohort` column (both git-ignored); (2) `data/imagery/sentinel2_v2/catalog_cache/` holds hard links to the 921 v1 searches and to the 48 older-collection searches of `data/imagery/malawi_2022_recovered/imagery/catalog_cache/`, so no new catalogue search is made. Never pass `--max-cloud-cover` or `--refresh-catalog`: either gives another run folder (`docs/DATA_V2_PLAN.md`). In the Malawi 2022 run, 200 records first failed on a DNS outage ("could not resolve host"); the second pass retried only those, and all 529 ended `complete`. Step 6 v2 crashed with `--workers 16` (a broken process pool) and ran with `--workers 8` and `OPENBLAS_NUM_THREADS=1` in 4,980 s.

A rebuilt database never has the SHA-256 of the pin, because `build_info.built_at` changes on every build. So `step8 --version 2` and step 9 stop on a rebuilt database: they run only on the team copies. Check a rebuild by its scenes instead: `scene_differences` compares them with `configs/sentinel2_scenes_v1.parquet`. For v2, pass `configs/sentinel2_scenes_v2.parquet` as its `scene_list`; no code does this today. Today's step 6 never fills Presto, and it fills MOSAIKS only from the files in `data/features/mosaiks/`, which parked code made (`_parked/scripts/features/mosaiks_features.py`). Get the team copy for those rows.

### 5.4 Use the team copy instead (README "Get started")

```bash
python -m venv .venv
.venv\Scripts\activate                       # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt    # exact versions (duckdb 1.5.5, pandas 3.0.6, scikit-learn 1.9.1, ...) and the package
python -m pytest -q
```

1. Clone outside OneDrive. Labels, audit and splits come with the clone (v2 only after it is committed).
2. Get the two databases from the team link (README). Put them at `data/cropyield.duckdb` (872,689,664 bytes) and `data/v2/cropyield.duckdb` (22,818,816 bytes). Do not rebuild them.
3. Check a file by hand with `certutil -hashfile data\cropyield.duckdb SHA256` (Windows) or `shasum -a 256 data/cropyield.duckdb`, and compare the result with `configs/team_database_v1.json` (v2: `configs/team_database_v2.json`). Step 2 of `notebooks/data_guide.ipynb` checks the v1 file. `step8 --version 2` and step 9 check the v2 file.
4. Read data with `X, y = load_xy("malawi_2023")`, or `load_xy("malawi_2022", Path("data/v2"))` for v2. Leave `CROPYIELD_DATA_DIR` unset, and use `--version 2` for the scripts.

### 5.5 Hashes and pins

All values below match the files on disk today.

| Pin | What it guards | Value | Checked by |
|---|---|---|---|
| `configs/team_database_v1.json` | `data/cropyield.duckdb` | 872,689,664 bytes, `e192b9d6…cdcd60` | `data_guide.ipynb` Step 2; step 9 |
| `configs/team_database_v2.json` | `data/v2/cropyield.duckdb` | 22,818,816 bytes, `5f36d91b…1e44` | `step8 --version 2`; step 9 |
| `data/splits/manifest.json` | `labels_v1` (`49aae383…e0ef92`) and the 13 v1 split files (SHA and rows), seed 20261029, 5 folds, region units, generator commit `96e2e81` | manifest SHA `b8abf5e4…af53f` | step 4 (refuses changes); step 8 v1 (labels and `s1_cc2km` files); step 9; `tests/test_splits.py` |
| `data/v2/splits/manifest.json` | `labels_v2` (`2b157317…69b1a`), the 17 v2 files (13 marked `same_as_v1`), the SHA of the v1 manifest, generator commit `a95c12c` (HEAD at build time; that commit does not hold the v2 code) | manifest SHA `172e6616…13d2` | `step4 --version 2`; `step8 --version 2`; step 9 |
| `data/metadata/download_manifest.json` | the 13 raw files of step 1 | 41,270,663 bytes in total | step 3 (`check_against_raw`, 4 files: OAF workbook, Lacuna GeoJSON, both Malawi zips; a file without a manifest entry is skipped without a message) |
| `data/metadata/vision_guided_yield_download_manifest.json` | `metadata.csv` (`bbd14515…e003`) and the photo zip | – | no step checks a file against it (step 1b only merges and rewrites it) |
| `configs/sentinel2_scenes_v1.parquet` | the 84,967 accepted `(obs_id, month, item_id)` of v1; equal to the v1 `scenes` table | `d48bff1d…60fa` | `get_all_data.py` (`scene_differences`, after a download from the notebook); `tests/test_build_database.py` (its SHA must be in `docs/DECISIONS.md`) |
| `configs/sentinel2_scenes_v2.parquet` | the 88,305 accepted scenes of v2; equal to the v2 `scenes` table | `cd069f68…273f` | no code reads it |
| `labels_*.parquet` column `source_sha256` | the screened audit CSV of each row (v2 Malawi 2022: `733fb603…dbd14`, equal to `data/v2/audit/malawi_2022_screened_candidates.csv`) | per row | step 3 writes it |
| step 5 `plan-*.json` `input_sha256` | the audit inputs of each download | per run | written by step 5 |

The v2 database `build_info.git_commit` is also `a95c12c`, with no "-dirty" mark, although the v2 code was uncommitted when it ran.

### 5.6 Tests

`python -m pytest -q` runs **175 tests** in 13 files; all 175 passed on 7 Nov 2026 (8 min).

| File | Tests | File | Tests |
|---|---:|---|---:|
| `tests/test_get_data.py` | 55 | `tests/test_cohorts.py` | 5 |
| `tests/test_build_database.py` | 25 | `tests/test_check_data.py` | 5 |
| `tests/test_data_v2.py` | 19 | `tests/test_longpath.py` | 5 |
| `tests/test_baseline.py` | 17 | `tests/test_monthly.py` | 5 |
| `tests/test_labels.py` | 11 | `tests/test_records.py` | 3 |
| `tests/test_xy.py` | 11 | `tests/test_splits.py` | 8 |
| `tests/test_download_selection.py` | 6 | | |

`tests/conftest.py` builds a synthetic 6 × 6 pixel chip, so no imagery is needed. `tests/test_baseline.py` and `tests/test_data_v2.py` are not committed yet.

## 6. Open items

Ordered by what blocks the team first. Each links to its evidence above.

| # | Item | Who | Evidence |
|---|---|---|---|
| 1 | Write the final-test protocol for fold 0: train and tune on folds 1–4 only (inner `GroupKFold` on their `group_id`), then predict fold 0 once, per cohort | owner | 4.1 |
| 2 | Commit data v2 as one set, tag `labels-v2` and `splits-v2`, then rerun `step8`, `step8 --version 2` and `step9` on the clean tree so the results carry a commit that holds their code | owner | 5.1, Q-08 |
| 3 | Upload `data/v2/cropyield.duckdb` (22,818,816 bytes) to the team link next to the v1 file | owner | README "Data v2" |
| 4 | Ask PULA for the Lacuna protocol (unit, moisture, grain or cob); keep `unit_provisional` until then | team | 2.6 issue 1, Q-11 |
| 5 | Ask the Zimbabwe 2024 authors what a zero means; keep the cohort parked | team | 2.6 issue 2, Q-25 |
| 6 | Test Lacuna `Admin1` against a boundary file before `s2_region` becomes a headline; add a point-in-polygon border test | next labels version | 2.6 issues 4–5 |
| 7 | Build Presto and MOSAIKS features from the v2 photos before any A2/A3 score on v2 | team | Q-19 |
| 8 | Score `s2_region` and the Kenya `temporal` split (frozen, not yet scored), with fold 0 removed from the test rows | team | Q-07, 4.8 |
| 9 | Later go / no-go: Lacuna 2022 (156 fields) and the October–November 2022 gap from the older collection | owner | 2.6 issue 7, Q-13 |
| 10 | Next labels version: check the Zimbabwe 2024 `metadata.csv` checksum in step 3 | next labels version | 2.6 issue 10 |
