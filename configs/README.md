# Configurations

Saved configurations describe the recorded experiments. Copy to a new filename for a changed experiment;
do not edit a published configuration to make an old manifest pass. Every file here is read by its exact path, and
most are recorded with their SHA-256 in the run manifests, so none of them moves. Keep the line endings of the
checkout as they are: several recorded hashes are of the Windows (CRLF) bytes.

## Zimbabwe experiments (steps 8–15)

Use the v2 file for new work (8 Nov 2026; the team rules on `include_primary`, label-free windows and folds 1–4).
The v1 file stays for the recorded v1 releases.

| v1 | v2 | Purpose |
|---|---|---|
| [zimbabwe_midterm_v1.json](zimbabwe_midterm_v1.json) | [zimbabwe_midterm_v2.json](zimbabwe_midterm_v2.json) | Step 8 Lacuna cleaning, predictors and explicit handoff splits |
| [zimbabwe_merge_v1.json](zimbabwe_merge_v1.json) | [zimbabwe_merge_v2.json](zimbabwe_merge_v2.json) | Step 9 common-window merge, source weighting and model grids |
| [zimbabwe_transfer_diagnosis_v1.json](zimbabwe_transfer_diagnosis_v1.json) | [zimbabwe_transfer_diagnosis_v2.json](zimbabwe_transfer_diagnosis_v2.json) | Step 10 source-quality and representation diagnostics |
| [zimbabwe_weather_v1.json](zimbabwe_weather_v1.json) | [zimbabwe_weather_v2.json](zimbabwe_weather_v2.json) | Steps 11–12 NASA POWER extraction and model comparison |
| [zimbabwe_weather_compact_v1.json](zimbabwe_weather_compact_v1.json) | [zimbabwe_weather_compact_v2.json](zimbabwe_weather_compact_v2.json) | Step 13 compact weather comparison |
| [zimbabwe_aggregation_v1.json](zimbabwe_aggregation_v1.json) | [zimbabwe_aggregation_v2.json](zimbabwe_aggregation_v2.json) | Step 14 temporal mean, preharvest window, max, median and modal estimate (v2: calendar window, not crop dates) |
| [zimbabwe_multiyear_v1.json](zimbabwe_multiyear_v1.json) | [zimbabwe_multiyear_v2.json](zimbabwe_multiyear_v2.json) | Step 15 imagery eligibility and expanded Lacuna/2024 training, same 2023 evaluation fields |

## Data pins and inventories

| v1 | v2 | Purpose |
|---|---|---|
| [team_database_v1.json](team_database_v1.json) | [team_database_v2.json](team_database_v2.json) | Size and SHA-256 of the team database (`data/cropyield.duckdb`, `data/v2/cropyield.duckdb`) and its label fingerprint |
| [sentinel2_scenes_v1.parquet](sentinel2_scenes_v1.parquet) | [sentinel2_scenes_v2.parquet](sentinel2_scenes_v2.parquet) | Frozen scene of each record and month (84,967 and 88,305 rows) |

## Other settings

| File | Purpose |
|---|---|
| [spatial_baselines_v1.yaml](spatial_baselines_v1.yaml) | Earlier within-cohort R0/R1/A1 baselines (`scripts/baselines/spatial_baselines.py`) |
| [sentinel2_windows_pilot48.csv](sentinel2_windows_pilot48.csv) | Original pilot cohort/season imagery windows |

Start with the [Zimbabwe guide](../docs/zimbabwe/README.md) for data and report locations.
