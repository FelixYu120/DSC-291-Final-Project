# Data directory

For the Zimbabwe work, start with the [dataset selector](../docs/zimbabwe/README.md#choose-the-dataset-you-need).
All linked releases below are tracked in Git. The shared database, chips and scratch experiments stay local.

## Current Zimbabwe exports

| Directory | Contents | Start with |
|---|---|---|
| [processed/zimbabwe_midterm_v1/](processed/zimbabwe_midterm_v1/) | Clean Lacuna labels, model/monthly tables, dictionary, audits and explicit splits | [README.md](processed/zimbabwe_midterm_v1/README.md) |
| [runs/zimbabwe_merge_v1/](runs/zimbabwe_merge_v1/) | Combined label catalog, ten-feature model table, source audit, splits and first comparison | [RESULTS.md](runs/zimbabwe_merge_v1/RESULTS.md) |
| [runs/zimbabwe_transfer_diagnosis_v1/](runs/zimbabwe_transfer_diagnosis_v1/) | Monthly/Presto predictors, quality diagnostics and transfer comparisons | [RESULTS.md](runs/zimbabwe_transfer_diagnosis_v1/RESULTS.md) |
| [processed/zimbabwe_weather_v1/](processed/zimbabwe_weather_v1/) | Weather-enriched labels, monthly weather, climate normals, grid joins and retrieval ledger | [README.md](processed/zimbabwe_weather_v1/README.md) |
| [runs/zimbabwe_weather_v1/](runs/zimbabwe_weather_v1/) | Imagery/weather model tables and full-weather comparisons | [RESULTS.md](runs/zimbabwe_weather_v1/RESULTS.md) |
| [runs/zimbabwe_weather_compact_v1/](runs/zimbabwe_weather_compact_v1/) | Compact weather and predictor tables, comparisons and overfitting diagnostics | [RESULTS.md](runs/zimbabwe_weather_compact_v1/RESULTS.md) |
| [runs/zimbabwe_multiyear_v1/](runs/zimbabwe_multiyear_v1/) | All-label imagery audit, eligible aggregation features, extra-Lacuna spatial permissions and expanded training comparisons | [RESULTS.md](runs/zimbabwe_multiyear_v1/RESULTS.md) |

The releases include both usable and reserved/ineligible observations, identified by flags and split tables.
Use `target_memberships.csv` and `source_spatial_permissions.csv` when reproducing the comparisons;
do not treat every row in a combined table as training data.

The [runs/zimbabwe_aggregation_v1/](runs/zimbabwe_aggregation_v1/) release holds the original same-field temporal aggregation comparison, including raw monthly values, crop-date audits, variant predictors and [RESULTS.md](runs/zimbabwe_aggregation_v1/RESULTS.md). Step 15 audits all 6,598 labels but excludes all 169 Lacuna 2022 fields and two 2024 fields for insufficient December–June imagery; no missing imagery is imputed.

## Sources and common inputs

| Path | Purpose |
|---|---|
| [raw/zimbabwe/](raw/zimbabwe/) | Original Lacuna observations and provider documentation |
| [raw/vision_guided_yield_estimation/](raw/vision_guided_yield_estimation/) | Original 2024 source metadata; the large photo archive is not tracked |
| [raw/nasa_power_zimbabwe_v1/](raw/nasa_power_zimbabwe_v1/) | Saved NASA POWER responses and request metadata |
| [metadata/](metadata/) | Provider records, source URLs, licences and download checksums |
| [audit/](audit/) | Original cross-country screening evidence and candidate records |
| [processed/labels_v1.parquet](processed/labels_v1.parquet) | Frozen multi-country labels used by the original database |
| [splits/](splits/README.md) | Frozen spatial/region/temporal split assignments |
| `cropyield.duckdb` | Local shared team database; obtain from the team chat and verify with `configs/team_database_v1.json` |

Derived Zimbabwe exports are separate from the shared DuckDB. Preserve the database: rebuilding it removes its
Presto embeddings. Raw/provider data, recorded releases and split files remain unchanged during repository cleanup.

## Local-only outputs

`imagery/`, `features/`, `models/` and most scratch `runs/` are ignored by Git. New reproductions go to
`runs/reproductions/`; quality-review record tables go to local `runs/data_quality/` or `runs/quality_variant/`.
Their shared aggregate evidence is indexed under [results](../results/README.md).

Licences and original label-provider attribution: [README.txt](README.txt), retained as the historical source inventory.
Weather source and attribution: [methods](../docs/zimbabwe/METHODS.md#sources-and-provenance).
