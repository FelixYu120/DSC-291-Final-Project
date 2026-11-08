# Data foundation

Checked on 29 October 2026 against the raw provider files, the audit CSVs and `data/cropyield.duckdb`.
Every model reads one table, `labels_v1`, built and frozen before the first fit. This file is its contract.

## Short answers to the proposal feedback

- **Do the cohorts measure yield the same way?** No. Cut size, number of cuts and moisture basis differ
  (table below), and six of seven cohort-years do not state a moisture basis at all.
- **Do they all have exact field boundaries?** No. Only Malawi has walked polygons. Every other cohort is a
  GPS point, and no provider states its accuracy; OAF says points are "occasionally" at the homestead.
- **So:** we do not pool. One model per cohort, metrics within cohort. Shared code, separate fits. Pooled
  training is a stretch only (per-cohort standardised target, cohort indicator, still scored within
  cohort); a pooled R² is never reported, because differences between cohort means inflate it.

- **Can we harmonize them anyway?** Not in physical units: the moisture basis is missing in most cohorts, and
  no file lets us convert one cut size to another. Harmonization of the satellite side works without extra
  steps: a model trained in one cohort ranks fields in another (X1, Spearman up to 0.40), with no rescaling and
  no target label. The t/ha level does not carry over reliably. So we compare cohorts by rank, never by t/ha
  ([`ROADMAP.md`](ROADMAP.md#2-the-absolute-minimum-baseline-b0)).

## How each cohort measures yield

| Cohort | Yield definition | Location | Dates | Fields used | Groups for spatial splits | Median / zeros |
|---|---|---|---|---|---|---|
| **Kenya OAF 2019** | mean of 2 boxes of 6×6 m, "grain yield"; moisture not stated; the label is the provider's `yield_kg_ph`, which equals `yield_kg_pa` × 2.47105 | field GPS point, sometimes homestead | planting and harvest date per row (long rains) | 1,768 pure stand | `district` 39, `site` 473 (raw workbook) | 2.73 t/ha / 3.3 % |
| **Kenya OAF 2020** | mean of 2 boxes; the provider does not state the 2020 box size, so the 6×6 m of `labels_v1` is an assumption; moisture not stated; the label is `yield_kg_ph` | same as 2019 | same as 2019; 434 harvests after 30 Sep | 2,209 pure stand | `district` 50, `site` 684 | 3.04 t/ha / 0.7 % |
| **Malawi 2023** | one 10×10 m cut (`cc_ey_t`), shelled, 13 % moisture; nested 5×5 m cut `subc_ey_t` reads a median +17 % higher | walked polygon, median 0.59 ha | cut 17–26 May 2023; no planting date | 260 | none in the file: 2 km clusters (53) | 2.44 t/ha / 0 % |
| Lacuna 2023 (second) | one 8×5 m cut (40 m²), "dry weight", t/ha = dry kg × 0.25; moisture and grain-vs-cob not stated; unit provisional | point | planting and harvest date per row | 2,097; 1,880 pure stand rainfed | `Admin1` 20 (mixes districts, towns, one province) | 3.02 t/ha / 1.3 % |
| Zimbabwe 2024 (parked) | mean of 2 boxes of 40 m², threshed and dried; moisture not stated | point; pilot points on bare soil | no dates; photo-filename date only | 2,458 positive of 4,332 | none (the paper's 87 zones are not released) | 0.09 t/ha / 43 % |
| Malawi 2022 (v1 dropped; **data v2: in**, role second) | mean of 2 cuts of 5×5 m; `AVG_YLD` equals mean(2·kernwt·(100 − mc)/87) of the two cuts for 529 of 529 fields, so t/ha at 13 % moisture (inferred, not provider-confirmed); a different cut from Malawi 2023, so never pool the two | polygon, EPSG:20936; v1 positions use EPSG:1117 (27 m stated accuracy), v2 uses EPSG:1113 (44 m), about 24 m W and 24 m N of v1, chosen by a label-free within-field NDVI test | cut 30 Apr – 19 May 2022 | 529 | 3 districts by latitude; v2 `s1_cc2km` 97 clusters | 2.42 t/ha / 0.6 % |
| Lacuna 2022 (dropped) | as Lacuna 2023 | point | as Lacuna 2023 | 156 | `Admin1` 6 | 1.46 t/ha / 0 % |

Sources: Malawi metadata sheets and the 2023 sampling-frame methodology in `data/raw/malawi*/`; OAF
workbook sheets *Variables* and *Description*; Lacuna GeoJSON properties and technical manual
(`data/raw/zimbabwe/`); vision-guided `metadata.csv`.

Why Zimbabwe 2024 is parked: all 1,874 zeros have zero wet *and* zero dry weight, and the zero share
follows the visit month (13 % March, 30 % April, 66 % May, 92 % June, 100 % July). Most zeros are likely
"already harvested or not measured", not crop failure. 2023/24 was also a declared drought year.

## Imagery status

- Sentinel-2 L2A from Earth Search `sentinel-2-c1-l2a`, monthly, one clear scene per month (SCL mask).
- **All cohorts done on 30 October:** 11,364 of 11,364 records `complete`, which means no scene failed, not that
  every month is clear. Model rows with at least 4 clear months: Malawi 2023 251, Kenya 3,977, Lacuna 1,880,
  Zimbabwe 2024 2,458. Seasonal indices exist for every one of them. MOSAIKS and Presto exist only in the team database (`configs/team_database_v1.json`); a database you build yourself does not hold them.
- The download moves about 60 MB per field to keep about 2 MB, because reads fetch whole internal image blocks.
  32 slices fill a 40 MB/s line and give 40–45 fields per minute.
- **2022 gap.** Collection 1 holds almost no scenes for January–November 2022 over our tiles (ESA
  reprocessing backlog). This drops Malawi 2022 and Lacuna 2022 and removes October–November 2022 from Malawi
  2023 and Lacuna 2023; those months are before or at planting, so the core is not hurt. Filling 2022 needs
  the older `sentinel-2-l2a` collection (−1000 offset per item) or GEE `COPERNICUS/S2_SR_HARMONIZED`.
  **Data v2 fills Malawi 2022 from the older collection** (offset 0 only for the 4 measured processing-baseline
  cases; any other case is rejected unread): 529 of 529 fields have at least 4 clear months, March is clear for 89 %.
  Lacuna 2022 and October–November 2022 of Malawi 2023 and Lacuna 2023 stay empty. So the Malawi 2022 season
  means include October–November and the Malawi 2023 ones do not: compare the two seasons by rank only.
- **Data v2 top-up.** Up to 24 photos tried per cloudy month, every v1 scene kept: 624 new clear
  scenes, 522 model field-months cloudy → clear (Lacuna 205, Kenya 176, Zimbabwe 2024 90, Malawi 2023 51). The
  6,048 `no_scene` field-months (Kenya February 2019, October–November 2022) are catalogue gaps that more tries cannot fill.
- **Labels next to the pixels.** Each chip folder's `record.json` stores the yield and the audit row, and the view
  `monthly` has a `yield_kg_ha` column. Never use these as model inputs; take X from `load_xy` or the index columns.
- **Early 2019 gap.** The same holds for Kenya 2019: our first scene is 23 March 2019. At a test point Collection
  1 has 0 scenes in January and February 2019, the older collection has 6 each. So Kenya 2019 has at most 7
  months, Kenya 2020 has 8. This is a catalogue gap, not a download fault, and it makes `*_season_mean` less
  comparable between the two years.
- **Download outside OneDrive.** 17 broken `.part` files in the pilot download came from OneDrive locks.
- Points use one 10 m pixel (`aoi_type = point_pixel`); polygons use the pixels whose centres fall inside.
  A 3×3-pixel median for points is a stage-3 ablation.

## The labels table: `labels_v1`

One row per field-season, written to `data/processed/labels_v1.parquet`. The `labels` table of the database
keeps the audit columns and takes `include_primary` and `exclusion_reason` from it; every other column here is
in the parquet only, and `obs_id` joins the two. No standardised target column: models standardise inside the
training fold.

| Group | Columns |
|---|---|
| Keys | `obs_id` (= `dataset:source_id`, primary key), `cohort`, `dataset`, `source_id`, `source_row`, `source_sha256` |
| Season | `country_iso3`, `season_year`, `season_start`, `season_end` (fixed per cohort, `cohorts.py`) |
| Target | `yield_kg_ha` (stored in kg/ha, reported in t/ha) |
| Measurement | `yield_definition` (one value per cohort), `cut_area_m2`, `n_cuts`, `moisture_basis_pct` (null if not stated), `unit_provisional`, `cut1_kg_ha`, `cut2_kg_ha` (Malawi 2023 main and nested cut; Zimbabwe 2024 boxes) |
| Location | `geometry_type`, `lat`, `lon` (WGS84), `geometry_wkt`, `field_area_ha`, `location_source` (`walked_polygon`, `field_gps`, `field_gps_maybe_homestead`), `source_crs` |
| Dates | `plant_date`, `harvest_date`, `obs_date`, `obs_date_source` |
| Management | `intercropped`, `irrigated` (null where the provider does not report them) |
| Groups | `admin_unit` (OAF `district` normalised, Lacuna `Admin1`), `site_unit` (OAF `site`), `cluster_2km`, `site_distance_km` (OAF field point to site point) |
| Flags | `is_zero`, `near_dup_10m`, `polygon_overlap_dup`, `date_outside_window`, `impossible_date`, `source_flags` |
| Inclusion | `include_primary`, `exclusion_reason` |

**Inclusion rules for `include_primary`.**

- Kenya: `intercropping == "0"` (cohort filter of `cohorts.py`). **Lacuna: `intercropping == "no"` and no
  irrigated rows.** This rule lives in `include_primary` (`src/cropyield/data/labels.py`), not in `cohorts.py`,
  so the download still covers all 2,266 Lacuna rows; 225 intercropped and 5 irrigated rows are excluded
  (`exclusion_reason` counts 212 intercropped, because the 13 intercropped 2022 rows carry the 2022 reason first).
- Finite yield, 0 ≤ yield ≤ 15,000 kg/ha; valid geometry inside the country.
- Malawi 2023: target is `cc_ey_t` only; the nested cut is never a second row.
- Zimbabwe 2024: zeros excluded.
- Zeros elsewhere are kept; a without-zeros row is a robustness check.
- Duplicates and near-duplicates are **kept but grouped**: rows within 10 m share a cluster, so they always
  fall in the same fold.
- `date_outside_window`, `impossible_date` and large `site_distance_km` are flags for robustness rows, not
  exclusions.

**Checks (each one is a test that must pass before the table is frozen).**

1. `obs_id` is unique and non-null.
2. Row counts per cohort equal frozen constants (Kenya 2019 = 1,768, Kenya 2020 = 2,209, Malawi 2023 = 260,
   Lacuna 2023 = 1,880, Zimbabwe 2024 = 2,458).
3. Every row re-derives from its raw `source_row`: yield within 1e-6, coordinates within 1e-7°.
4. Included rows have a finite yield in [0, 15,000] kg/ha and a valid geometry inside the country.
5. Malawi polygon area (UTM) is within 2 % of `field_area_ha`.
6. Each cohort has exactly one `yield_definition`, one `cut_area_m2` and one unit.
7. Unit identities hold: Kenya kg/ha = kg/acre / 0.40468564224 (1 %); Lacuna t/ha = dry kg × 0.25;
   Zimbabwe 2024 yield = mean of the two boxes.
8. Included Lacuna rows are pure stand and rainfed; included Zimbabwe 2024 rows are positive.
9. `obs_date` lies in [`season_start`, `season_end`], or the row carries `date_outside_window`.
10. Rows within 10 m of each other share `cluster_2km`.
11. Input SHA-256 values match `data/metadata/download_manifest.json`.

Build with `python scripts/step3_build_labels.py`. Frozen on 30 October:
`data/processed/labels_v1.parquet`, SHA-256 `49aae383c4489aa98e9e7fe8c31cda6bf1cd752adc8e9540cffdc147a5e0ef92`
(`DECISIONS.md`). The split manifest pins this hash, so a rebuild means new splits. The experiment runner, which
stopped on a mismatch, is parked. One Kenya `unique_id` was stored by Excel as a date; the check compares its ISO text.

## Red flags found on 29 October

- **The audit drops the grouping columns.** OAF `district`, `site`, `site_latitude/longitude`,
  `plot_acres` and Lacuna `Admin1`, `Field_Irri` are in the raw files but not in the screened CSVs. Without
  them every "region" split is a grid split.
- **Kenya.** The fixed 1 Feb – 30 Sep window ends before 20–24 % of recorded harvests (850 rows; peak
  greenness is still inside). 13 rows carry `impossible_date`: 12 have a harvest on or before planting, and 5 have a planting
  year out of range (one in 2100); 4 rows are in both groups. District spelling changes between years (`kakamega(south)` vs `kakamegasouth`): normalise.
  Field points sit a median 1.75 km from the site point; 141 fields in 2019 are more than 10 km away
  (max 110 km). 108 coordinates are exact duplicates (likely homestead GPS). Only the mean of the two boxes
  is released, so Kenya has no noise ceiling.
- **Malawi.** 7 polygon pairs overlap more than 50 % in 2023 (for example `6625e538` and `04b466d6`,
  99 %, yields 2.36 and 2.35 t/ha); this may explain 267 public rows vs 261 documented fields. Villages were
  chosen by Sentinel-2 NDVI strata: scores describe this sample, not district-wide accuracy.
- **Lacuna.** `Admin1` mixes levels; 20 of the 169 points of 2022 are within 50 m of a 2023 point.
- **Zimbabwe 2024.** `Box used` holds strings such as "used box 1 and N" with an increasing N on 4,290 rows
  (export fault); 4,332 rows with yield vs 4,173 fields in the paper.
- **Audit script.** The curated-vs-full OAF overlap check reports 0 overlaps although the provider says the
  releases overlap; the repeated-coordinate flag uses exact float equality (149 Kenya 2019 rows lie within
  1 m of another); the only outlier rule (> 30 t/ha) never fires.

## What the imagery check found on 30 October

From `python scripts/step7_check_data.py`. None of these changes `labels_v1`: rows are never picked by a feature after
the freeze. Each one is a robustness row or a later arm.

- **Clouds hide the Malawi peak.** 78 % of fields peak in February or March, but only 51 % have a clear March
  (December 45 %, January 69 %, February 81 %, April 88 %, May and June 100 %). Fields without a clear March
  read `ndvi_season_max` 0.63 against 0.73 with one, and their yield is about the same (2.67 and 2.75 t/ha). So
  `*_season_max` partly says which month was clear. Filling the month (more scenes per month, or interpolation)
  is a stage-3 ablation.
- **Kenya points are sometimes not on the crop.** 285 fields (7 %) never pass NDVI 0.5 in the season, yet they
  report normal yields; among them the signal is negative (Spearman of `ndvi705_season_max` with yield −0.11,
  +0.23 in the other fields). In 2019, 66 % of the fields below NDVI 0.4 lie more than 5 km from their site
  point, against 12 % of all fields. The signal falls with that distance: 0.29 within 2 km, 0.17 beyond 2 km,
  0.07 beyond 5 km. Kenya 2020 has no site points, so only 2019 can show this.
- **The Kenya window holds more than this crop.** In 2020, 21 % of fields peak in February to April, and March
  reads NDVI 0.55 in 2020 against 0.36 in 2019. Season features also see green that is not this maize, and the
  level moves between years (`ndvi_season_mean` 0.52 in 2019, 0.59 in 2020).
- **Peak timing carries yield.** Kenya 2019 mean yield rises with the peak month: May 2.48, June 2.70, July 3.24,
  August 3.97 t/ha. The 10 season features cannot see timing; a series model (A4) can.
- **Cloud count is not the signal.** `months_with_data` has Spearman −0.01 to −0.08 with yield, and R2 scores
  like R0.
- **Index tails.** Kenya monthly MTCI runs from −2,828 to 11,341 (median 3.3), hence the clip in the B0 pipeline. The other
  indices stay in normal ranges. Haze is low: 0.8–2.3 % of clear months have a field-median blue above 0.15.
- **Lacuna is the cleanest point cohort.** All 1,880 fields have at least 4 clear months (median 7; December 95 %,
  January 80 %, February 74 %, March 90 % clear). `ndvi705_season_max` has Spearman 0.45 with yield, against 0.17–0.21
  in Kenya and 0.24 in Malawi. Points alone therefore do not explain the weak Kenya signal.
- **Zimbabwe 2024 (parked).** The chips are fine (median 9 months), and among the positive rows
  `ndvi705_season_max` has Spearman 0.45 with yield. The open question is its zeros, not its imagery.

## Where the label files come from

`data/raw/` holds the provider files unchanged; `data/metadata/` the provider records, URLs and SHA-256
checksums; `data/audit/` the audit outputs (`*_maize_audit.csv` all maize rows with flags,
`*_screened_candidates.csv` rows passing the yield and location checks, `summary.json`, `report.html`).
Screened rows are candidates, not validated labels. Rebuild with `python scripts/step2_audit_labels.py`
(offline). Licences and attribution: `data/README.txt`. Other sources we looked at and parked: see
`_parked/MANIFEST.csv`.
