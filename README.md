# DSC-291 Final Project: Smallholder Maize Yield Estimation

This project investigates whether fine-tuning an open-weight geospatial model improves field-level maize yield estimation when labelled data are limited and predictions are made for previously unseen locations. The planned evaluation compares the adapted model with simpler statistical and machine-learning baselines using spatially separated training and evaluation data.

The repository currently contains public yield datasets, their documentation, and scripts for downloading and auditing them. Satellite imagery extraction and model training are subsequent steps.

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

[`audit_datasets.py`](scripts/audit_datasets.py) reads local files without network access and regenerates `data/audit/`. It uses `openpyxl`, `pyshp`, `shapely`, and `pyproj`, installed by the requirements command above. Originals in `data/raw/` are preserved, and downloaded provider Python code is not executed.

| Output | Purpose |
|---|---|
| [`data/audit/summary.csv`](data/audit/summary.csv) / [`summary.json`](data/audit/summary.json) | Counts, flags, screening definitions, and transformation details. |
| [`data/audit/report.html`](data/audit/report.html) | Human-readable report; open locally in a browser. |
| `data/audit/*_maize_audit.csv` | All maize observations, including excluded rows and their quality flags. |
| `data/audit/*_screened_candidates.csv` | Rows where `passes_yield_and_known_location_checks` is true. Location and unit caveats above still apply. |
| `data/audit/malawi_*_candidates_wgs84.geojson` | Valid candidate field boundaries in WGS84. Invalid source polygons remain in the originals. |

The common derived yield column is **`yield_kg_ha`**. `source_yield`, `source_yield_units`, and `yield_field` document its origin; `source_id` and `source_row` link back to the input. Spreadsheet/CSV row numbers include the header, while GeoJSON/shapefile row numbers are one-based feature indices. Curated OAF identifiers are synthetic row identifiers.

## Repository layout

```text
data/
  raw/          Original datasets and supporting documents
  metadata/     Provider records, download URLs, and checksums
  audit/        Row-level audits, candidate CSVs, boundaries, and reports
  README.txt    Additional data-use and reproduction notes
scripts/
  download_datasets.py
  audit_datasets.py
  requirements-audit.txt
Notes/          Project notes
```
