# Extra-input scripts

These scripts reproduce the optional Zimbabwe input extension without modifying the frozen labels or splits.
Run commands from the repository root and keep the output directory outside Git.

| Script | Purpose |
|---|---|
| `prepare_zimbabwe_extra_inputs.py` | Build observation/month keys and download and sample SRTM. |
| `align_existing_chirps.py` | Align an existing CHIRPS monthly table to the canonical keys. |
| `get_zimbabwe_soilgrids.py` | Download and sample selected SoilGrids layers. |
| `get_soilgrids_features.py` | Download and sample the same SoilGrids layers for any canonical point or centroid table. |
| `gee_export_zimbabwe_presto_inputs.js` | Export Sentinel-1, ERA5-Land, SRTM and AlphaEarth from Earth Engine. |
| `gee_check_zimbabwe_nicfi.js` | Check optional NICFI mosaic coverage. |
| `assemble_zimbabwe_extra_inputs.py` | Validate and combine all sources into monthly and static tables. |
| `assemble_malawi_extra_inputs.py` | Validate and combine Malawi polygon-level Earth Engine and SoilGrids inputs. |
| `assemble_kenya_extra_inputs.py` | Validate and combine Kenya point-level Earth Engine and SoilGrids inputs. |
| `build_malawi_extra_inputs_notebook.py` | Build the executed Malawi audit notebook, figures and English summary. |
| `build_kenya_extra_inputs_notebook.py` | Build the executed Kenya audit notebook, figures and English summary. |
| `build_three_country_extra_inputs_duckdb.py` | Package raw and processed Zimbabwe, Kenya and Malawi extra inputs into one DuckDB file. |
| `prepare_kenya_malawi_assets.py` | Build data-v2 Kenya point and Malawi polygon upload assets plus canonical month keys. |
| `gee_export_kenya_presto_inputs.js` | Export Kenya Sentinel-1, ERA5-Land, CHIRPS, SRTM and AlphaEarth values. |
| `gee_export_malawi_presto_inputs.js` | Export polygon-median Malawi Sentinel-1, ERA5-Land, CHIRPS, SRTM and AlphaEarth values. |

The Python scripts accept explicit input or output paths; use `--help` for their arguments. The Earth Engine steps
are documented in [`../../../docs/GEE_EXTRA_INPUTS_GUIDE.md`](../../../docs/GEE_EXTRA_INPUTS_GUIDE.md). Coverage,
licences and modelling recommendations are in
[`../../../docs/EXTRA_INPUTS.md`](../../../docs/EXTRA_INPUTS.md).

Large rasters, Earth Engine exports and model-ready field tables are intentionally excluded from Git. Only the
small audit summaries in `data/audit/extra_inputs/` are committed.
