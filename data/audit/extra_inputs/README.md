# Zimbabwe extra-input audit summaries

These small files summarize the optional Zimbabwe extra-input extraction. They contain coverage and quality metrics,
not the downloaded rasters or model-ready field-level feature tables.

| File | Contents |
|---|---|
| `combined_inputs_summary.json` | Overall row counts, completeness and Earth Engine integration status. |
| `feature_quality_summary.json` | Cross-source range, agreement and quality checks. |
| `monthly_source_coverage.csv` | Monthly Sentinel-1, ERA5-Land and SRTM coverage. |
| `s1_observation_coverage.csv` | Selected Sentinel-1 orbit and valid-month count by `obs_id`. |

The corresponding workflow is documented in
[`../../../docs/EXTRA_INPUTS.md`](../../../docs/EXTRA_INPUTS.md) and reproduced by
[`../../../notebooks/06_build_extra_inputs.ipynb`](../../../notebooks/06_build_extra_inputs.ipynb).
