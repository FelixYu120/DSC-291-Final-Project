# Notebook reading order

For data files and reports, use the [Zimbabwe project guide](../docs/zimbabwe/README.md).

1. [Data Guide 1](data_guide.ipynb): the original multi-country foundation, provider measurements,
   satellite extraction, harmonization, database structure and X/y inputs.
2. [Data Guide 2: Zimbabwe](data_guide_2_zimbabwe.ipynb): the complete Zimbabwe midterm and follow-up work,
   from raw crop-cut audits through merging, weather enrichment, model comparisons and uncertainty.
3. [Data quality review](data_quality_review.ipynb): the Kenya source checks, cloud-screening variant,
   plot-to-pixel diagrams, field-boundary limitations and tabular-foundation-model preparation plan.

Guide 2 contains saved tables and figures and can be read directly on GitHub. To run it, select the Python environment
installed from `requirements.txt` and run all cells in order. The default path reads the tracked releases and
recomputes checks and summaries without downloads, a DuckDB connection or model fitting. A clearly marked optional
cell replays one selected Ridge fit. Full model-training and verification commands are documented at the end.
Use the [recorded-code runner](../docs/zimbabwe/REPRODUCING.md) to reproduce historical Zimbabwe releases after
merging the stronger data-validation modules into main.

The second guide uses Zimbabwe, not Malawi: Lacuna 2023 is the target population and Zimbabwe 2024 is the auxiliary
training source. Both guides retain the distinction between historical data policies and later authorized experiments.
