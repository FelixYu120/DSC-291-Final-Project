# Pass archive v1 (`passarchive_v1.duckdb`)

What the surveys reported and what Sentinel-2 observed, for Kenya, Malawi and Zimbabwe. No cloud mask, no
monthly rule and no split is applied: each person chooses these later. Built 2026-11-19T14:46:35+00:00 (UTC).

- File: `passarchive_v1.duckdb`, 2678 MB. SHA-256: `7a02a6fe7b0147dad9ba1ac7380a29224ecf6261847173182c11ece64990e4bf` (also in `SHA256SUMS`).
- The file is not in Git (too large). Get it from the team and put it in this folder,
  `data/passarchive_v1/release/`; see `docs/DATA_SETUP.md`.
- It opens with DuckDB alone: no other file, no Internet, no account.
- Columns: `DICTIONARY.md`. Build record: `manifest.json`.

## What is inside

| | rows |
|---|---|
| original survey rows (`source_records`) | 42,379 |
| field-seasons (`fields`) | 35,510 |
| usable locations (`locations`) | 32,939 |
| Sentinel-2 product versions listed (`scenes`) | 66,085 |
| field-season passes listed (`passes`) | 8,248,916 |

Every pass that the catalogue lists for the harvest year (`current`) and the year before (`previous`) is in
`passes`, cloudy or not. Band values are in `pass_samples` for the passes that were read:

| `passes.sample_status` | passes | share |
|---|---|---|
| `not_sampled_no_public_file` | 81,561 | 1.0 % |
| `outside_swath_per_catalogue` | 2,483,065 | 30.1 % |
| `sampled_10m_bands` | 421 | 0.0 % |
| `sampled_all_bands` | 5,611,314 | 68.0 % |
| `sampled_nodata` | 72,555 | 0.9 % |

`sampled_all_bands` = all Level-2A bands and quality layers read from the public file at the native pixel.
`sampled_10m_bands` = B02, B03, B04, B08 taken from the old chips (exact native pixel; only the scenes the old
pipeline kept, which were clear at the field). `sampled_nodata` = read, and the pixel holds no data.
`outside_swath_per_catalogue` = the tile holds the field but the catalogue footprint says the sensor did not
see it on that pass (not read). `not_sampled_yet` = listed, values not downloaded yet.
`not_sampled_no_public_file` = listed, but no copy exists that can be read without an account.
All times are UTC (`sensing_time_utc`); `year` and `month` are UTC too.

Download progress by country-year, in read order (image blocks read / planned):

| step | country-year | read | planned | complete |
|---|---|---|---|---|
| 1 | Zimbabwe 2023 (Lacuna) | 53,585 | 53,585 | yes |
| 2 | Kenya 2020 | 61,400 | 61,400 | yes |
| 3 | Kenya 2019 | 20,717 | 20,717 | yes |
| 4 | Malawi 2023 | 10,405 | 10,405 | yes |
| 5 | Malawi 2022 | 12,192 | 12,192 | yes |
| 6 | Zimbabwe 2024, measured yield | 112,483 | 112,483 | yes |
| 7 | Zimbabwe 2022 (Lacuna) | 14,302 | 14,302 | yes |
| 8 | Kenya 2018 | 15,668 | 15,668 | yes |
| 9 | Kenya 2017 | 8,555 | 8,555 | yes |
| 10 | Kenya 2016 | 1,558 | 1,558 | yes |
| 11 | Malawi 2020 | 13,596 | 13,596 | yes |
| 12 | Zimbabwe 2024, recorded zero | 66,046 | 66,046 | yes |
| 13 | Zimbabwe 2024, no yield in the source | 22,588 | 22,588 | yes |


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

- One Acre Fund MEL data, all countries (workbook, sheet Data) (CC BY 4.0); `raw/one_acre_fund_full/one_acre_fund_mel_data_all_countries.xlsx`, 26,268 rows in scope.
- One Acre Fund MEL maize survey data 2016-2022, curated (Zenodo 11122388) (CC BY 4.0); `raw/one_acre_fund_curated/One_Acre_Fund_MEL_maize_survey_data_2016-2022.csv`, 7,258 rows in scope.
- Lacuna Fund / PULA Advisors Zimbabwe crop cuts (Zenodo 10060610) (CC BY 4.0); `raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson`, 3,002 rows in scope.
- Scalable Vision-Guided Crop Yield Estimation Dataset (Zenodo 17626117) (CC BY 4.0); `raw/vision_guided_yield_estimation/metadata.csv`, 5,055 rows in scope.
- FAO / NASA Harvest Malawi crop-cut campaign 2022 (CC BY); `raw/malawi/mwi_mwi_lc_fo_202205_averageyield_v1.zip`, 529 rows in scope.
- FAO / NASA Harvest Malawi crop-cut campaign 2023 (CC BY); `raw/malawi/mwi_kas_lc_fo_202305_cc_yield.zip`, 267 rows in scope.
- Contains modified Copernicus Sentinel data (European Space Agency). Catalogue: Copernicus Data Space
  Ecosystem. Pixel files: Earth Search by Element 84 (AWS open data).

Keep the provider attribution and the CC BY notices when you share or publish this file.
