# Harmonized maize candidates by country

Run `python scripts/labels/audit_datasets.py` to regenerate this folder. ISO 3166-1
alpha-3 subfolders contain a merged `screened_maize_yield_candidates.csv`
from each eligible source release. The CSV retains `dataset`, `source_id`,
`source_row`, original yield fields, dates, location, quality flags, and the
common `yield_kg_ha` field so each row can be traced to its provider file.
Source releases can overlap: in particular, the curated One Acre Fund release
overlaps its full release. Do not interpret a sum across datasets as a count
of unique fields.

These are audit-screened candidates, not verified field labels or an
imagery-matched training split. Read the dataset-specific notes in
`data/audit/report.html` and check `manifest.json` for per-country counts and
source coverage. Malawi folders also contain valid screened field polygons
transformed to WGS84. Original source files remain under `data/raw/`, and the
full audits remain under `data/audit/`.

The U.S. Quick Stats data belong under `data/raw/USA/USDA_NASS/` and are
county-level aggregates, so they are intentionally not emitted into these
field-candidate files.
