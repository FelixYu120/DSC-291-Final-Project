# Data-quality audit, 3 November 2026

The shared database passes all **108 implemented integrity checks**. All **27 protected input files**
are unchanged. This is evidence of internal consistency and correct source conversions; GPS accuracy,
measurement protocols and imagery relevance still require review. No observations were removed and no
models were trained or scored.

| Cohort | Eligible records reviewed | Records with at least four clear months |
|---|---:|---:|
| Kenya OAF 2019–2020 | 3,977 | 3,977 |
| Malawi 2023 | 260 | 251 |
| Zimbabwe Lacuna 2023 | 1,880 | 1,880 |
| Total | 6,117 | 6,108 |

Important review findings: 13 inconsistent Kenya dates, 89 missing Kenya observation dates,
203 Kenya observations with repeated exact coordinates, 850 Kenya harvests after the imagery window,
and 128 of 260 Malawi fields without clear March imagery. These overlapping flags are not a count of
bad fields. Malawi crop-cut area and Lacuna product/moisture conventions need provider clarification.

Monthly MOSAIKS availability differs from scene availability: one chip vector and 519 field vectors
are NULL across all retained cohorts. The extractor allows this when no complete convolution window
contributes; all present vectors pass dimension/finiteness checks. All seasonal vectors are present.

[summary.json](summary.json) records aggregate findings, definitions, code/input fingerprints,
package versions and validation. The run used commit `434cd3e` on `felix-branch` with a clean working
tree. Detailed local outputs are under `data/runs/data_quality/2026-11-03-final/`, including
`report.html` and country/cohort `record_review.csv` files.

Reproduce from the repository root:

```bash
python scripts/audit_data_quality.py
```

The command creates a new timestamped report and runs no models. See
[the quality guide](../../docs/quality/DATA_QUALITY.md) for meanings and remaining questions.

Validation: **200 data-pipeline tests passed, two Windows-only tests skipped**. The 35 dedicated
quality tests also passed after the final report wording/coverage changes. Ruff passed; country
review counts, unknown-value denominators, coverage totals and HTML links were verified.
