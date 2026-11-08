# Check and understand data quality

The quality audit makes data problems and uncertainties visible without changing the research dataset.
It checks the shared database against the provider files and frozen labels, then creates a review table
for every eligible observation in the three active cohorts. It does not train or score a model.

## Run the audit

From the repository root, after installing `requirements.txt` and placing the shared file at
`data/cropyield.duckdb`:

```bash
python scripts/quality/audit_data_quality.py
```

Each run creates a new folder under `data/runs/data_quality/<UTC timestamp>/`. The command prints the
path to `report.html`. To choose a readable folder name instead:

```bash
python scripts/quality/audit_data_quality.py --output data/runs/data_quality/my-review
```

The destination must not exist. Repeating the default command creates another report, leaving earlier
reports available for comparison. The command opens DuckDB read-only and compares protected input
fingerprints before and after the audit. Do not run the database builder or regenerate frozen labels
and splits to resolve a finding.

| Output | Purpose |
|---|---|
| `report.html` | Human-readable findings, definitions, limitations and provider questions; open locally in a browser |
| `summary.json` | Integrity checks, aggregate flag counts, input/code fingerprints and package versions |
| `monthly_coverage.csv` | Expected eligible fields, observed/missing coverage rows, and clear/cloudy/unavailable/failed months by cohort and year |
| `KEN/kenya_oaf_2019_2020/record_review.csv` | Kenya observations with original values and review flags |
| `MWI/malawi_2023/record_review.csv` | Malawi observations, including the nine below the coverage requirement |
| `ZWE/zimbabwe_lacuna_2022_2023/record_review.csv` | Eligible Lacuna observations from 2023 |

Full reports and record-level tables stay in the local, Git-ignored `data/runs/` folder. The committed
[aggregate snapshot](../../results/data_quality/summary.json) records the audit findings without publishing
another copy of field coordinates or observation-level review files.

**Exit status 0 means the implemented integrity checks passed. It does not certify scientific quality.**
Exit status 1 means at least one check failed or an audit stage could not complete. Read the named check
and its explanation. If invalid keys make joins unsafe, detailed review tables are omitted rather than
silently deduplicating records. Missing input files or an existing output destination also require fixing
the setup before a complete report can be produced.

## Which observations are reviewed

An observation is one field in one season; `obs_id` links it across tables. The detailed review uses
`include_primary` in the existing labels and keeps each cohort separate.

| Cohort | Eligible observations reviewed | At least four clear months |
|---|---:|---:|
| Kenya OAF 2019–2020 | 3,977 | 3,977 |
| Malawi 2023 | 260 | 251 |
| Zimbabwe Lacuna 2023 | 1,880 | 1,880 |
| **Total** | **6,117** | **6,108** |

The database retains 11,364 labels, including excluded and parked cohorts. Integrity checks cover that
larger collection. The detailed review tables cover the active three-cohort selection above. The nine
Malawi observations with insufficient imagery remain valid label records; they do not become additional
usable model inputs merely because they appear in a review table.

## What an integrity check establishes

The checks verify source-file and frozen-data fingerprints; unique IDs and complete table links; yield
unit conversions; source coordinate agreement in both latitude and longitude; valid polygon geometry;
scene dates and seasonal grids; missing-band conventions; vegetation-index arithmetic; seasonal
aggregates; and feature-vector dimensions and finite values. These checks can find contradictions such
as an orphan observation, a changed coordinate, or an index that no longer matches its input bands.

Some stored values are intentionally missing. A month without usable imagery has NULL bands, not zeros.
Monthly MOSAIKS vectors can also be NULL when no fully valid convolution window contributes to the
field or chip. The shared copy has **519 unavailable monthly field vectors and one unavailable monthly
chip vector**. Those are reported as availability counts, not malformed vectors. Seasonal MOSAIKS means
skip missing vectors, and `months_used` counts available monthly **chip** vectors. A finite vector of the
right size still does not prove that it represents the correct field.

## How to interpret review flags

Review flags are separate from integrity failures. They identify records to investigate and are not a
quality score or an automatic deletion list. The CSV retains original values, the existing coverage
eligibility and a flag for each issue. Empty nullable flags mean a rule could not be assessed or does
not apply. Counts in the report use the assessed population; flags overlap and must not be added to
count “bad fields.”

Examples from the shared copy:

| Finding | Count and interpretation |
|---|---|
| Kenya inconsistent dates | 13 observations violate a date-order or year rule; no correction is inferred |
| Kenya missing observation dates | 89 observations cannot be assessed for observation-date timing comparisons |
| Kenya harvest after the fixed season window | 850 observations need timing review; this does not prove their yield is wrong |
| Repeated Kenya coordinates | 203 observations share 95 coordinate pairs; these may include repeated fields across years |
| Nearby Kenya coordinates | 560 observations carry the frozen within-10-m flag; proximity alone does not establish duplicates |
| Overlapping Malawi polygons | 14 polygons in seven pairs overlap by more than half the smaller polygon's area |
| Malawi March coverage | 128 of 260 eligible observations have no clear March scene |
| Low Kenya seasonal greenness | 285 observations have NDVI maximum below 0.5; this is a location/timing/vegetation review signal |
| Retained zero yields | 74 Kenya and 28 Lacuna observations remain in the primary cohort |

The exact-coordinate flag is computed within the reviewed cohort, potentially across years. The
near-coordinate and polygon-overlap flags come from frozen labels and were calculated on the original
cohort, which can include subsequently excluded observations. The report states those populations.

Other descriptive flags use fixed thresholds from the data guide: B02 above 0.15 can indicate haze or
bright ground, and absolute monthly MTCI above 100 indicates an unstable ratio to inspect. The project's
MTCI formula is `(B08 - B05) / (B05 - B04)`. Reflectance outside [0, 1] warrants
review, but small negative surface-reflectance values can arise from atmospheric processing and are
not automatically corruption. These flags do not change feature values or eligibility.

Accepted scenes after a field's harvest or crop-cut date are flagged separately. The current fixed
windows can include those scenes, so the data support retrospective estimation; they do not by
themselves establish a pre-harvest forecast. A missing date is unknown, not evidence that all scenes
preceded harvest.

## Decisions and questions requiring evidence

The [decision log](../DECISIONS.md) keeps core zero yields, the provider's Malawi yield and all frozen
labels/splits unchanged. The original audit's 30 t/ha review threshold and the later `labels_v1`
15 t/ha eligibility cap belong to different processing stages; neither is a newly fitted cutoff here.

| Cohort | Evidence still needed | Current treatment |
|---|---|---|
| Malawi 2023 | Was the main weight harvested from all 100 m², or 75 m² after the nested 5×5 m cut? Which overlapping polygons are distinct fields or repeated exports? | Keep the provider's yield and describe a nominal 10×10 m cut. The nested measurement is not an independent field or a proven noise floor. |
| Kenya | Which coordinates mark the field versus a home, which repetitions share a field identity, and can missing/inconsistent dates be corrected? Can the 2020 crop-cut protocol be explicitly confirmed? | Keep locations and dates unchanged. The team accepted the 2020 box-size interpretation from weight quantization; this is still an inference rather than an explicit provider statement. |
| Lacuna | What were the grain/cob basis, drying or moisture standard and precise yield-unit convention? What geographic level does each `Admin1` label represent? | Retain the provisional measurement interpretation and analyze this cohort separately. |

The audit cannot establish GPS accuracy, inspect cloud masks or pixels without imagery, resolve a
provider's measurement ambiguity, or independently validate country membership against administrative
boundaries. A promising review flag should lead to source-record or image inspection. Any later
correction needs documented evidence and a separately versioned proposal; the review tables are not a
cleaned replacement dataset.

Implementation: [`scripts/quality/audit_data_quality.py`](../../scripts/quality/audit_data_quality.py),
[`src/cropyield/data/quality.py`](../../src/cropyield/data/quality.py) and the source-label checks in
[`src/cropyield/data/labels.py`](../../src/cropyield/data/labels.py). The
[data guide notebook](../../notebooks/data_guide.ipynb) explains the original pipeline in detail.
