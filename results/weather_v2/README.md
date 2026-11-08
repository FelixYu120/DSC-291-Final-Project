# Zimbabwe weather experiments, v2 (team training-row rule)

Small copies of the v2 step 12 and step 13 outputs and their independent verification receipts. The full releases are
in `data/runs/zimbabwe_weather_v2/` and `data/runs/zimbabwe_weather_compact_v2/` (git-ignored). The v2 weather data
release, `data/processed/zimbabwe_weather_v2/`, was built offline by step 11 from the committed NASA POWER cache.
Each folder holds the release `manifest.json`; every copied file is a listed release output with its SHA-256.

**Why v2 exists.** v1 trained on the v1 merge pool, which held 1,874 recorded 2024 zeros that
`labels_v1.include_primary` excludes. v2 reads only v2 upstream releases, and its code stops if a fit pool holds a row
outside `include_primary`. Splits, buffer, feature sets, grids, seeds and bootstrap units are unchanged.

| File or folder | Source | Command |
|---|---|---|
| `full/` | `data/runs/zimbabwe_weather_v2` | `python scripts/step11_add_zimbabwe_weather.py --config configs/zimbabwe_weather_v2.json`, then `python scripts/step12_compare_zimbabwe_weather.py --config configs/zimbabwe_weather_v2.json` |
| `compact/` | `data/runs/zimbabwe_weather_compact_v2` | `python scripts/step13_compare_compact_weather.py --config configs/zimbabwe_weather_compact_v2.json` |
| `weather_verification.json` | independent checker | `python scripts/verify_zimbabwe_weather.py --config configs/zimbabwe_weather_v2.json --report results/weather_v2/weather_verification.json` |
| `compact_verification.json`, `zimbabwe_weather_compact_support_v2.csv` | independent checker | `python scripts/verify_compact_weather.py --config configs/zimbabwe_weather_compact_v2.json --output results/weather_v2/compact_verification.json` |
| `compact_candidate.csv` | post-hoc benchmark, no refit | `python scripts/compare_compact_candidate.py --config configs/zimbabwe_weather_compact_v2.json --output results/weather_v2/compact_candidate.csv` |

The v1 versus v2 comparison is in `docs/zimbabwe/METHODS.md`. All results are exploratory and retrospective.
