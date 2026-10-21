# DSC-291 Final Project: Smallholder Maize Yield Estimation

This project investigates whether fine-tuning an open-weight geospatial model improves field-level maize yield estimation when labelled data are limited and predictions are made for previously unseen locations. The planned evaluation compares the adapted model with simpler statistical and machine-learning baselines using spatially separated training and evaluation data.

The repository currently contains public yield datasets, their documentation, and scripts for downloading and auditing them. Satellite imagery extraction and model training are subsequent steps.

The research plan is in [`docs/RESEARCH_PLAN.md`](docs/RESEARCH_PLAN.md). It distinguishes AlphaEarth's released annual embeddings from Presto's fine-tunable pretrained model, defines spatial and low-label evaluation, and keeps the optional U.S. county-yield benchmark separate from field-level African labels.

## Proposed modeling approach

The target is harmonized maize yield in kg/ha. The main evaluation should ask how well models predict fields from locations excluded from training, and whether a pretrained representation is useful when only 10%, 25%, or 50% of available training labels are used. Report a random split only as a diagnostic; group fields, repeat observations, and nearby coordinates in the same spatial split.

- **AlphaEarth downstream regression:** extract the 64-dimensional, 10 m annual embedding vector for each eligible field from Google's Earth Engine collection [`GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL), then fit downstream Ridge and tree-based regressors. AlphaEarth is supplied here as an embedding dataset; it is not the encoder being fine-tuned. Same-year annual embeddings are suitable for retrospective completed-season estimation, not a causal pre-harvest forecast because they summarize the annual observation period. For a pre-harvest task, use prior-year embeddings only.
- **Presto transfer and fine-tuning:** load the [pretrained Presto model](https://github.com/nasaharvest/presto), represent each field as a dated and masked remote-sensing time series, and attach the official one-output regression head (`construct_finetuning_model(num_outputs=1, regression=True)`). Compare a frozen encoder with a Ridge/tree head, head-only training, and full or partial encoder fine-tuning. The released Presto architecture defaults and a proposed student-project hyperparameter search are documented in the [research plan](docs/RESEARCH_PLAN.md); the learning rate and regularization values are search candidates, not guaranteed best settings.
- **Baselines:** training-fold mean/median, Ridge on seasonal band/index summaries, Random Forest, and HistGradientBoosting, all using the same eligible fields, date window, and spatial folds as far as each input allows.
- **Optional United States comparison:** USDA NASS Quick Stats supplies county-level corn-yield estimates, not individual farm yields or field locations. Use it only as a separate county-scale benchmark, joined to county boundaries with FIPS and compared to county-aggregated predictions. The optional downloader is [`scripts/download_usda_nass.py`](scripts/download_usda_nass.py); instructions are in [`data/raw/USA/USDA_NASS/README.md`](data/raw/USA/USDA_NASS/README.md).

The central citation is Burke and Lobell (2017), “Satellite-based assessment of yield variation and its determinants in smallholder African systems” ([PNAS](https://doi.org/10.1073/pnas.1616919114)). The project also builds on Tseng et al.'s [Presto paper](https://arxiv.org/abs/2304.14065) and Brown et al.'s [AlphaEarth Foundations paper](https://arxiv.org/abs/2507.22291). Full references, hypotheses, model settings, data checks, and evaluation design are in the research plan.

## How many usable maize records do we have?

The **20 October 2026 data snapshot contains 33,529 screened candidate observations**, including **18,939 from 2019 onward**, across the full One Acre Fund release, Zimbabwe, and Malawi. These are observations that pass the implemented yield and location checks; field alignment with satellite imagery still needs validation. They are not a verified count of unique fields.

| Dataset | Maize records before screening | Screened candidates | Candidates from 2019 onward |
|---|---:|---:|---:|
| One Acre Fund — full release | 45,569 | 30,474 | 15,884 |
| Zimbabwe — Lacuna | 2,269 | 2,266 | 2,266 |
| Malawi — 2022 | 529 | 529 | 529 |
| Malawi — 2023 | 267 | 260 | 260 |
| **Total, excluding curated OAF** | **48,634** | **33,529** | **18,939** |
| One Acre Fund — curated release, excluded from total | 14,773 | 14,773* | 8,055* |

*The curated OAF release overlaps the full release and mixes field, town, and district coordinates without an explicit location-source flag for each row. Its screening count does not establish how many records have accurate field locations. Do not add these records to the total without resolving overlap and location provenance.*

The counts come from [`data/audit/summary.json`](data/audit/summary.json), specifically `maize_records`, `screened_candidates`, and `screened_candidates_since_2019`. A compact [summary CSV](data/audit/summary.csv) and a detailed [HTML report](data/audit/report.html) are also included. Open the HTML file locally in a browser to view the formatted report.

### What “screened” means

Each candidate must have a maize label, a finite nonnegative yield, and a valid point or nonempty valid polygon with plausible coordinates inside a broad envelope of its reported country. The audit excludes exact duplicate source rows after the first and flags repeated coordinates. Country envelopes detect gross errors; they do not verify field boundaries or national borders.

Additional screening excludes documented site coordinates and yield consistency flags: values above 30 tonnes/ha, disagreement between per-acre and per-hectare yields beyond the implemented tolerance, Zimbabwe crop-cut conversion discrepancies, and dry weights exceeding wet weights. The 30 tonnes/ha threshold is a review heuristic. These rules are implemented in [`scripts/audit_datasets.py`](scripts/audit_datasets.py).

Zero yields are retained because they may represent crop failure. The total includes **375 zero-yield observations**; restricting it to positive yields would leave **33,154**. Repeated coordinates are not automatically removed because they can represent repeated observations or distinct fields. Keep observations from the same field or spatial cluster in the same evaluation split.

## Datasets and limitations

| Dataset and source | Coverage and measurements | Licence reported by the provider |
|---|---|---|
| [One Acre Fund full release](https://data.harvestportal.org/dataset/oaf_mel) | Multi-country monitoring and evaluation workbook covering 2015–2020; 81,411 records across crops. Screened maize observations cover 2016–2020. Includes crop-cut yields, field coordinate columns, and management variables. | CC BY |
| [One Acre Fund curated release](https://doi.org/10.5281/zenodo.11122388) | Maize in pure stands across seven African countries, 2016–2022. Includes yield and management/environmental variables with mixed location precision. | CC BY 4.0 |
| [Zimbabwe Lacuna](https://doi.org/10.5281/zenodo.10060610) | 3,002 observations across four crops; 2,269 are maize. Maize harvest dates span 2022–2023. Includes point locations, crop-cut weights, and reported yields. | CC BY 4.0 |
| [FAO / NASA Harvest Malawi](https://data.harvestportal.org/dataset/fao-bha-nasa-harvest-public-yield-datasets) | Field polygons and maize crop-cut yields: 2022 in Mzimba North, Kasungu, and Balaka; 2023 in Kasungu. Dictionaries and methodology documents are included. | CC BY, explicitly stated in the downloaded metadata |

Important checks remain before using the candidates for satellite-based modelling:

- **OAF full:** The audit excludes 246 Uganda 2020 records documented as using site coordinates. Other coordinates may have been collected at a homestead or near the field. Some records include intercropping.
- **OAF curated:** The provider describes approximately 70% field locations, 21% nearby-town locations, and 9% district locations. The public CSV does not identify these categories per row.
- **Zimbabwe:** The source yield column, `Yield(Mt/H`, is provisionally interpreted as tonnes/ha. Three records disagree with the documented 40 m² crop-cut conversion and are excluded from the screened file. Confirm the units and measurement protocol before pooling yields across datasets.
- **Malawi 2022:** The shapefile's actual coordinate system is **EPSG:20936**, despite generic metadata listing EPSG:4326. The audit transforms it to WGS84 using its `.prj`. The selected datum operation reports **27 m accuracy**; this is not a measurement of GPS error, but it warrants an alignment check before extracting 10 m satellite pixels.
- **Malawi 2023:** Seven polygons are self-intersecting and are excluded without automatic repair. The primary yield is from a 10 × 10 m crop cut; the nested 5 × 5 m cut is an alternate measurement on the same field, not an independent record.
- **Malawi sample counts:** The public files contain 529 and 267 rows, whereas campaign narratives report 523 and 261 fields. The audit retains the file counts and flags the discrepancy rather than removing unexplained rows.

Retain the original provider citations and attribution when using or redistributing the data. Exact download URLs and checksums are in the [download manifest](data/metadata/download_manifest.json); cached provider records are in [`data/metadata/`](data/metadata/).

## Run the download and audit

Use **Python 3.10 or newer**. From a new checkout on macOS or Linux:

```bash
git clone https://github.com/FelixYu120/DSC-291-Final-Project.git
cd DSC-291-Final-Project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r scripts/requirements-audit.txt
python scripts/download_datasets.py
python scripts/audit_datasets.py
```

If you already have the repository, start with the environment setup from its root directory. On Windows PowerShell, create the environment with `py -3 -m venv .venv` and activate it with `.\.venv\Scripts\Activate.ps1`; the remaining `python` commands are the same.

### Download behaviour

[`download_datasets.py`](scripts/download_datasets.py) uses Python's standard library. It downloads missing files into `data/raw/`, caches provider catalogue responses in `data/metadata/`, checks available provider sizes and Zenodo MD5 checksums, and records SHA-256 hashes in `download_manifest.json`.

The repository already includes the data snapshot, so a normal rerun reuses existing files and cached metadata. Network access is needed for missing downloads or metadata. The script does not automatically refresh the snapshot to newer provider releases.

Check that the final download summary reports **13 files** and **`"errors": []`** for this snapshot. Individual failures are recorded in the manifest; the script currently catches them rather than exiting with a failure status. Its recorded snapshot date is fixed, not the date of each rerun.

### Audit behaviour and outputs

[`audit_datasets.py`](scripts/audit_datasets.py) reads local files without network access and regenerates `data/audit/` plus the country-partitioned outputs in `data/processed/by_country/`. It uses `openpyxl`, `pyshp`, `shapely`, and `pyproj`, installed by the requirements command above. Originals in `data/raw/` are preserved, and downloaded provider Python code is not executed. To rebuild the country partitions alone from existing audit CSVs, run `python scripts/organize_country_data.py`.

| Output | Purpose |
|---|---|
| [`data/audit/summary.csv`](data/audit/summary.csv) / [`summary.json`](data/audit/summary.json) | Counts, flags, screening definitions, and transformation details. |
| [`data/audit/report.html`](data/audit/report.html) | Human-readable report; open locally in a browser. |
| `data/audit/*_maize_audit.csv` | All maize observations, including excluded rows and their quality flags. |
| `data/audit/*_screened_candidates.csv` | Rows where `passes_yield_and_known_location_checks` is true. Location and unit caveats above still apply. |
| `data/audit/malawi_*_candidates_wgs84.geojson` | Valid candidate field boundaries in WGS84. Invalid source polygons remain in the originals. |
| `data/processed/by_country/<ISO3>/` | Harmonized candidate CSVs partitioned by country, created by the audit run. |

The common derived yield column is **`yield_kg_ha`**. `source_yield`, `source_yield_units`, and `yield_field` document its origin; `source_id` and `source_row` link back to the input. Spreadsheet/CSV row numbers include the header, while GeoJSON/shapefile row numbers are one-based feature indices. Curated OAF identifiers are synthetic row identifiers.

### Country-organized analysis files

Running the audit also writes harmonized candidates to [`data/processed/by_country/`](data/processed/by_country/), grouped by ISO3 country code (for example, `MWI`, `ZWE`, and `KEN`). Each folder contains a `screened_maize_yield_candidates.csv`; Malawi also has valid field polygons in WGS84. The `manifest.json` lists counts and contributing source releases. These outputs are still screening candidates, not confirmed training examples. Original files remain organized by provider release under `data/raw/`, since some releases (especially One Acre Fund) span multiple countries. The U.S. Quick Stats data are organized separately under `data/raw/USA/USDA_NASS/` because they have county-level labels.

## Sentinel-2 imagery

[`scripts/download_sentinel2.py`](scripts/download_sentinel2.py) searches the free Sentinel-2 Level-2A Cloud-Optimized GeoTIFF archive through the [Earth Search STAC API](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a). The [AWS Open Data Registry](https://registry.opendata.aws/sentinel-2-l2a-cogs/) documents public, no-account-required access and the archive’s open data terms. Earth Search is a public, best-effort catalogue without a guaranteed service level. Credit ESA/Copernicus and cite the AWS Sentinel-2 COG archive as described by its registry page in research outputs.

The default selection uses the same **18,939 screened OAF, Zimbabwe, and Malawi records from 2019 onward** counted above. The overlapping OAF curated release is excluded because its field, town, or district location is not identified per row. The script uses recorded planting-to-harvest dates when available. For missing or inconsistent dates, its default policy infers a 180-day window before harvest or crop-cut observation, then records that the timing needs review. Use `--date-policy observed-only` to skip records without a valid observed date window, or pass a CSV of reviewed date overrides.

For each selected record, the downloader searches for Sentinel-2 scenes intersecting its location during the observation window. It considers months spread across the window, tries scenes in order of catalogue cloud cover, and accepts at most one scene per selected month. It then checks the scene classification over the field or location and requires at least 80% clear, valid pixels there by default. It reads the selected small chip from public cloud-optimized rasters instead of saving full satellite scenes. Imagery is atmospheric-corrected Level-2A bottom-of-atmosphere reflectance. The default output contains 10 spectral bands, an SCL scene-classification raster, a valid-pixel mask, an AOI mask, and JSON provenance per accepted scene. The bands originally measured at 20 m are resampled onto the default 10 m output grid; this resampling does not add spatial detail to those bands. OAF and Zimbabwe observations have point coordinates, so the mask marks their location pixel rather than asserting a known field boundary. Malawi records use the available field polygons; check the Malawi 2022 datum-offset caveat above.

Install the imagery dependencies and make a small offline plan first:

```bash
python -m pip install -r scripts/requirements-sentinel2.txt
python scripts/download_sentinel2.py plan --limit 5
```

`plan` estimates timing and output size without contacting the imagery catalogue or confirming that scenes exist. Try a small download batch next:

```bash
python scripts/download_sentinel2.py download --limit 5
```

For later batches, change `--offset` and `--limit`, for example `--offset 5 --limit 5`. The downloader caches STAC searches, writes progress files, and verifies existing scene files by SHA-256 when rerun. Common options include `--datasets`, `--date-policy observed-only`, `--max-cloud-cover`, `--min-clear-fraction`, `--bands`, and `--date-overrides`; use `python scripts/download_sentinel2.py --help` for the complete list.

A complete default run can generate **about 40 GB of uncompressed chips** at the maximum of 12 scenes per record. Actual output is usually smaller because only clear scenes that pass the field-pixel check are retained and the GeoTIFFs are compressed. Review the plan and run in batches. Imagery outputs are stored under `data/imagery/sentinel2/`, which is ignored by Git; the repository contains the script and instructions, not the generated image files.

Per-record JSON files record the crop observation, date-window basis, search results, and whether the AOI fits inside the chip. Each accepted scene's `scene.json` stores the full source item metadata, acquisition date, tile cloud cover, clear-pixel fraction, processing settings, and chip checksums. A point passing the pixel check does not prove that its coordinates identify the crop field. Imagery and time-window checks also do not validate each provider’s yield units. Review those issues and the 2022 Malawi position uncertainty before using chips as model labels.

## Optional U.S. county-yield data

USDA NASS Quick Stats is free to query after requesting an API key. The project script checks the API's count endpoint before downloading and never saves the key:

```bash
export USDA_NASS_API_KEY="your-key"
python scripts/download_usda_nass.py
```

This requests county-level annual corn yield rows for 2019–2024 and writes the CSV plus query provenance under `data/raw/USA/USDA_NASS/county_yield/`. The raw output may contain multiple published yield definitions or unavailable/suppressed values. Inspect its `short_desc`, `unit_desc`, and `Value` columns, retain NASS disclosure statuses, and select the corn-grain definition before analysis. These are county estimates; they do not increase the field-level maize candidate count above and should not be pooled with African field rows. See the [U.S. data notes](data/raw/USA/USDA_NASS/README.md).

## Repository layout

```text
data/
  raw/          Original datasets, kept by provider release
    USA/USDA_NASS/ Optional U.S. county-yield data and notes
  processed/
    by_country/  Harmonized audit candidates partitioned by ISO3 country
  metadata/     Provider records, download URLs, and checksums
  audit/        Row-level audits, candidate CSVs, boundaries, and reports
  imagery/      Local Sentinel-2 search caches and image chips (Git-ignored)
  README.txt    Additional data-use and reproduction notes
docs/           Research plan and model/evaluation protocol
scripts/
  download_datasets.py
  audit_datasets.py
  requirements-audit.txt
  download_sentinel2.py
  requirements-sentinel2.txt
  organize_country_data.py
  download_usda_nass.py
Notes/          Project notes
```
