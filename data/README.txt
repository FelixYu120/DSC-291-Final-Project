MAIZE YIELD DATA DOWNLOAD AND AUDIT
Snapshot checked: 20 October 2026

Start with audit/report.html or audit/summary.csv.

CONTENTS
raw/       Original provider files, unchanged.
metadata/  Provider catalogue/API responses and a download manifest containing
           exact source URLs, byte sizes, and SHA-256 checksums.
audit/     Counts, all maize records with audit flags, screened candidate CSVs,
           and Malawi candidate field boundaries converted to WGS84 GeoJSON.

SOURCES AND ATTRIBUTION
One Acre Fund full monitoring and evaluation workbook:
https://data.harvestportal.org/dataset/oaf_mel
Catalogue licence: Creative Commons Attribution.

One Acre Fund curated maize release (2016-2022):
https://doi.org/10.5281/zenodo.11122388
Licence: CC BY 4.0. This overlaps the full workbook; counts are not additive.

Zimbabwe Lacuna crop/yield observations:
https://doi.org/10.5281/zenodo.10060610
Licence: CC BY 4.0.

FAO / NASA Harvest Malawi crop-cut yield datasets:
https://data.harvestportal.org/dataset/fao-bha-nasa-harvest-public-yield-datasets
The accompanying 2022 and 2023 metadata CSVs explicitly specify CC BY.
Field dictionaries and methodology documents are included. Retain provider
citations and attribution when using or redistributing these data.

INTERPRETING THE OUTPUTS
*_maize_audit.csv retains every maize observation, including unusable and
flagged rows. source_row and source_id identify the original observation.
Excel/CSV source_row includes the header; GeoJSON/shapefile source_row is a
one-based feature index. Curated OAF row identifiers are synthetic.

passes_basic_checks requires a finite nonnegative yield, valid point or polygon,
plausible coordinates within a broad country envelope, and no exact duplicate
source row. Country envelopes are heuristics, not authoritative borders.

*_screened_candidates.csv also excludes yield consistency review flags and
OAF Uganda 2020 records explicitly documented as using site coordinates.
These are CANDIDATES, not a fully validated training set. In particular:
- The curated OAF file mixes field, town and district locations without an
  explicit row-level location-source flag. Its candidate count does not verify
  how many observations are accurately located at field level.
- Other full-workbook OAF points may have been recorded at a homestead or near
  a field. Satellite imagery has not been checked against these coordinates.
- Zimbabwe's ambiguous yield column is provisionally interpreted as tonnes/ha.
  The three rows inconsistent with the documented 40 m2 crop-cut conversion
  are excluded from the screened file without changing their original values.
- Seven Malawi 2023 polygons are self-intersecting. They remain in the raw file
  and audit CSV but are excluded from the candidate boundary file. They may be
  recoverable after geometry repair and review.
- Malawi 2022's actual .prj is EPSG:20936, despite metadata listing EPSG:4326.
  Derived boundaries were transformed from the actual .prj; the originals
  remain unchanged. Transformation details are recorded in summary.json.
  The selected datum operation reports 27 m accuracy (not measured GPS error),
  so check imagery alignment before using these boundaries with 10 m pixels.
- Zero yields are retained because they may represent crop failure. Separate
  zero-yield counts and row flags are provided.
- Repeated coordinates are flagged but not automatically discarded: they may
  represent repeat measurements, distinct nearby fields, or imprecise locations.
- Counts are observations, not independently verified unique fields. Group
  repeated fields/locations into the same split when assessing transfer.

yield_kg_ha is the common derived unit. source_yield, source_yield_units and
yield_field preserve how it was obtained. Malawi 2023 nested crop cuts are
alternate measurements on the same field, not additional independent records.

REPRODUCING
From the project directory, using a Python 3.10+ environment:

  python -m pip install -r scripts/requirements-audit.txt
  python scripts/download_datasets.py
  python scripts/audit_datasets.py

The downloader uses cached catalogue responses when present and verifies
existing downloads. It records errors in metadata/download_manifest.json.
The audit reads the local files and does not require network access.
Provider code is preserved as documentation; it is not run by these scripts.
