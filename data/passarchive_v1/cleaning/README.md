# Allen's pass-archive cleaning handoff

`allen_model_ready.parquet` is a small, versioned input for Zida's basic model comparison. It was produced from the checksum-verified `passarchive_v1.duckdb` release (`7a02a6fe7b0147dad9ba1ac7380a29224ecf6261847173182c11ece64990e4bf`). The original 2.68 GB database is local at `data/passarchive_v1/release/passarchive_v1.duckdb` and ignored by Git.

## Method and columns

Read [Allen's executed notebook](../../../notebooks/allen_median3_cleaning.ipynb). The quality screen uses the raw Level-2A passes from the previous and current archive years. It removes incomplete bands and locally obstructed observations; polygon cloud checks use native field footprint pixels. Allen's variant keeps one product per independent overflight, then up to three clear overflights per field-month. `median3` takes each band median; `best1` uses the single highest-ranked overflight from the same pool. The two rows per field-season form a matched comparison. Yield is joined **after** all scene choices.

Each row has `field_season_id`, `cleaning_arm`, country, source dataset, harvest year, `window_rule`, `months_in_window`, `months_observed`, `scene_count`, ten `b*_mean` reflectances, `ndvi_max`, `ndvi_mean`, field location flags, `label_status`, `yield_kg_ha`, and `yield_t_ha`. The band means are reflectances in `[0,1]`, not raw digital numbers. `window_rule=recorded_dates` uses coherent planting/harvest dates. `harvest_calendar_year` is a flagged fallback for missing or inconsistent dates; it does not establish the true crop season. `months_observed=0` means no usable optical feature. Missing bands are NULL, not zero.

For modeling, compare `median3` and `best1` on exactly the same field-seasons and frozen spatial splits. Exclude non-measured labels and decide how to handle recorded zeros according to the study cohort; do not silently treat `not_answered` or `not_measured` as zero. Preserve `fold0_reserved`. Impute and scale predictors inside each training fold. For strict field-level interpretation, use `usable_at_field_scale`; many point locations still lack verified field boundaries.

## Regenerate

From the repository root, with the release database in the location above:

```powershell
python scripts/quality/select_passarchive_imagery.py --database data/passarchive_v1/release/passarchive_v1.duckdb --output data/features/allen_screen_both_maize --window-kind both --crop maize
python scripts/quality/allen_median3.py --database data/passarchive_v1/release/passarchive_v1.duckdb --decisions data/features/allen_screen_both_maize/scene_decisions.parquet --output data/features/allen_median3
```

Then run `notebooks/allen_median3_cleaning.ipynb`; its last code cell checks the matched arms and copies the compact model table here. The large scene-level and monthly audit tables stay in ignored `data/features/`.

The cleaning rule is a proposed input policy, not a claim that the model scores improve. The notebook records the observed coverage and feature differences; Zida's identical-fold baseline comparison determines predictive value.
