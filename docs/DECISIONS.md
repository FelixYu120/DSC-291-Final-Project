# Decision log

One line per decision: date, what, why. Newest on top.

- 2026-10-26 Presto pilot sample: the first 10 `malawi_2023` rows in audit-file order (all walked polygons, tile 36LWL). Their fixed cohort window, 1 Oct 2022 – 30 Jun 2023, is passed to `download_sentinel2.py` as `--date-overrides` (`configs/sentinel2_windows_malawi_2023_pilot.csv`); the downloader's own 180-days-before-crop-cut window is not used because windows are fixed per zone (2026-10-25).
- 2026-10-26 Reflectance scale: `reflectance.tif` is unitless BOA reflectance = DN × 0.0001 − 0.1, the STAC scale and offset applied once by the downloader (Collection 1, baseline ≥ 05, carries the −1000 DN offset). Presto divides Sentinel-2 DN by 10 000 and was pretrained on 2020–21 data without that offset, so the value Presto sees is our reflectance unchanged; the offset is never applied a second time (`cropyield.features.presto_inputs`).
- 2026-10-26 Presto band order: 17 NORMED_BANDS = VV, VH, B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12, temperature_2m, total_precipitation, elevation, slope, NDVI. Our B02…B12 fill B2…B12; B1, B9 and B10 are not used by Presto; NDVI is computed from the normalised B8 and B4 exactly as Presto does.
- 2026-10-26 Masks: we have Sentinel-2 only. Sentinel-1, ERA5 and SRTM slots are 0 and masked at every timestep; Dynamic World is 9 (unknown) so Presto ignores it. A month with no accepted scene or no valid field pixel is masked for every band, so Presto drops that month's tokens. Cloudy pixels never enter: a month's value is the median over AOI ∩ valid (SCL 4/5/6, all bands finite) pixels of the one accepted scene per month.
- 2026-10-26 Point vs polygon: polygon records use the downloader's rasterised field mask and the per-month median over its valid pixels; point records use the single 10 m pixel the downloader marks. A 3×3 neighbourhood for points is a later decision (ROADMAP).
- 2026-10-26 Presto code and weights pinned at nasaharvest/presto commit 11e207a668a34336ced1d8e492a1bd5849b96c4a: `single_file_presto.py` vendored byte-identical as `src/cropyield/models/presto_single_file.py` (MIT, SHA-256 fb487a3a…), `data/default_model.pt` (SHA-256 559c9d76…, 3,321,716 bytes) fetched by `scripts/get_presto.py` into git-ignored `data/models/presto/` and verified on every load. Byte-identical to the earlier research-notes checkpoint.
- 2026-10-26 Records are encoded one at a time: Presto's encoder requires the same number of masked tokens for every item in a batch, and missing months differ per record. Batching by identical mask pattern is a later optimisation.
- 2026-10-26 Open: Earth Search `sentinel-2-c1-l2a` has no scenes for Jan–Nov 2022 in the Malawi tiles (2022 is only partly reprocessed into Collection 1), so Malawi 2022 (Oct 2021 – Jun 2022) and the Oct–Nov 2022 start of Malawi 2023 cannot be filled from it. Candidate fix: also search `sentinel-2-pre-c1-l2a` for 2022. Not decided.
- 2026-10-26 Project structure added (package folders, configs, tests, results, splits); data layer unchanged.
- 2026-10-26 Kenya pure-stand filter is `intercropping == "0"` in the audit CSV (3,977 rows); `1` is intercropped, empty is unknown.
- 2026-10-25 Four cohorts: Zimbabwe 2024, OAF Kenya 2019–2020, Zimbabwe Lacuna 2022–23, Malawi 2022/2023. Parked: curated OAF, GROW-Africa, Nigeria 2022, Zindi/CGIAR, TAMASA, LSMS, USDA.
- 2026-10-25 Season windows fixed per agro-zone (Kenya Feb–Sep; Malawi and Zimbabwe Oct–Jun), never anchored on crop-cut dates.
- 2026-10-25 Splits are spatially blocked and frozen before training; random field splits only as a labelled diagnostic.
- 2026-10-25 RMSE in t/ha is the primary metric, reported within cohort; targeting metrics and the two-cut noise ceiling are added.
- 2026-10-24 Imagery is Sentinel-2 L2A only. The UCSD Planet licence expired and the free tier charges 100 km² per clip (Amy Work, UCSD Library).
- 2026-10-21 Data snapshot and audit committed (Felix). Screened candidates are not imagery-validated labels.
