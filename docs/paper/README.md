# Paper material for Felix and Florian

This folder contains the data sources and preparation section, a one-page results handoff, and the complete evidence behind the summary. The manuscript uses collective research prose and numbered citations; the bibliography is also supplied in BibTeX. The analysis snapshot is repository revision `a8f31fb`. Writing this material did not alter labels, features, splits, predictions or reported model results.

| Use | Editable document | Repository text or data |
|---|---|---|
| Paste the data sources and preparation section into the paper | [Manuscript DOCX](data_sources_and_preparation.docx) | [Manuscript text](DATA_SOURCES_AND_PREPARATION.md) |
| Share a one-page overview with teammates | [One-page summary DOCX](results_summary_one_page.docx) | [Copyable summary](RESULTS_SUMMARY.md) |
| Find every reported score and its exact model name | — | [Complete results appendix](RESULTS_APPENDIX.md), [full-precision ledger](RESULTS_LEDGER.csv) |
| Import citations into the paper's bibliography | — | [REFERENCES.bib](REFERENCES.bib) |
| Check document and numeric verification | — | [Verification receipt](validation.json) |

The summary selects ten representative rows; the appendix retains all **149 target-arm rows** across six releases and **six separate source-diagnostic rows**. All target rows evaluate the same 1,504 Lacuna 2023 observations. Reused controls and numerically equivalent predictions are identified explicitly, so they cannot be mistaken for independent replications. Source-diagnostic scores concern a different 3,764-field population and must not be ranked against the target scores.

## Integration with the team paper

Use the manuscript as the data and preprocessing section. It includes the dataset population, measurement checks, satellite support and feature definitions, weather extraction, partitioning, preprocessing and data provenance. The modeling section can refer back to those definitions and describe the individual learner grids and architectures. The results section should use the exact method and training-population labels in the ledger. Renumber references when integrating the section with the rest of the paper; BibTeX keys remain stable.

The original and expanded training populations are different. Original target models use the 1,880-field primary Lacuna 2023 pool. Expanded models add 217 screened 2023 candidates before spatial buffering. All 2022 records remain catalog-only because they fail the common-window imagery criterion. Neither version evaluates 2024 outcomes as part of the target RMSE/R².

The lowest observed RMSE, four-weather-feature shared Ridge at 1.6554 t/ha, is a candidate for independent validation. Its post-hoc comparison against imagery-only merged trees does not establish superiority. Shared Ridge and adaptive Ridge have different source calibration; retain their distinct names when writing the model comparison.

## Details resolved during the manuscript audit

| Claim requiring precision | Audited statement | Project evidence |
|---|---|---|
| Catalog size | 2,266 screened Lacuna + 4,332 screened 2024 = 6,598 | [Lacuna audit](../../data/processed/zimbabwe_midterm_v1/audit_summary.json), [2024 audit](../../data/runs/zimbabwe_merge_v1/source_2024_audit.csv) |
| Yield thresholds | Raw Lacuna 0–30 t/ha; original primary Lacuna also ≤15; 2024 0–15 | [handoff.py](../../src/cropyield/data/handoff.py), [zimbabwe_merge.py](../../src/cropyield/experiments/zimbabwe_merge.py) |
| Conversion tolerance | Lacuna uses max(0.001 t/ha, 0.1% relative magnitude); 2024 uses absolute 10⁻⁶ t/ha | Same audit implementations |
| 2024 cut area | Reported cut yields are numerically consistent with 40 m²; the raw CSV and associated paper do not independently specify physical area | [raw metadata](../../data/raw/vision_guided_yield_estimation/metadata.csv), [associated paper](https://arxiv.org/html/2511.12999v1) |
| Spatial satellite support | All catalog geometries are points; accepted Zimbabwe observations contain one valid 10 m grid cell | [observations](../../data/runs/zimbabwe_multiyear_v1/observations.csv), [monthly observations](../../data/runs/zimbabwe_multiyear_v1/monthly_observations.parquet), [extractor](../../scripts/step5_download_imagery.py) |
| Scene masking | Frozen inputs accept SCL classes 4, 5 and 6; the separate stricter buffered mask was not used | [extractor](../../scripts/step5_download_imagery.py), [separate quality variant](../quality/QUALITY_REMEDIATION.md) |
| Archived `mtci` | Uses B08 in the numerator; ESA SNAP's Sentinel-2 MTCI uses B06 | [actual formula](../../src/cropyield/features/indices.py), [ESA specification](https://step.esa.int/main/wp-content/help/versions/11.0.0/snap-toolboxes/eu.esa.opt.opttbx.radiometric.indices.ui/mtci/MtciAlgorithmSpecification.html) |
| Missing imagery | Earlier monthly models impute within training folds; latest aggregation models reject nonfinite aggregate predictors | [monthly transform](../../src/cropyield/experiments/zimbabwe_diagnosis.py), [aggregate eligibility](../../src/cropyield/experiments/zimbabwe_multiyear.py) |
| Actual years used | All 169 Lacuna 2022 fields fail ≥4 observed December–June months | [coverage](../../data/runs/zimbabwe_multiyear_v1/coverage_summary.csv), [window audit](../../data/runs/zimbabwe_multiyear_v1/window_audit.csv) |
| Historical fold 0 | Excluded from the current comparisons; not an untouched blind test across all repository history | [evaluation policy](../EVALUATION.md), [current memberships](../../data/runs/zimbabwe_multiyear_v1/target_memberships.csv) |
| Weather independence | 1,447/1,504 outer evaluation fields share a weather cell with that fit's target-training set | [weather-cell overlap](../../data/runs/zimbabwe_weather_v1/weather_cell_overlap.csv) |
| Source hash | Legacy row-level `source_sha256` hashes a screened audit table; original provider-file hashes are separately in manifests | [label construction](../../src/cropyield/data/labels.py), [release manifest](../../data/runs/zimbabwe_multiyear_v1/manifest.json) |

The archived MTCI-style feature is described by its actual formula. Changing it to standard Sentinel-2 MTCI would require a new feature release and model comparison. Neither unknown moisture nor uncertain physical cut area can be resolved by relabeling columns. The manuscript keeps these limitations explicit.

## Document production and verification

[build_paper_documents.py](../../scripts/paper/build_paper_documents.py) builds both DOCX files from the reviewed Markdown using `python-docx`. Word-native fraction objects keep the equations editable. The final documents were rendered and every page inspected; the team summary occupies exactly one page. The validation receipt records source/document hashes and render page counts. Rendered PDF/PNG intermediates are retained only for local layout checks.

The score ledger was independently checked against saved predictions for sample count, uniqueness, RMSE, MAE and R². The manuscript was separately reviewed against processing code and primary sources. Frozen experiments were not rerun or rewritten for this writing task.

8 Nov 2026 (merge into `data-v2-experiments`): `build_paper_documents.py` moved to `scripts/paper/` (its `ROOT` line changed, and it now reads the Markdown as UTF-8), so `validation.json` records the 7 Nov builder. The numbers here are the v1 runs of 7 Nov; the rule-compliant v2 values are in `notebooks/lacuna_results_consensus.ipynb`, section 6.1.
