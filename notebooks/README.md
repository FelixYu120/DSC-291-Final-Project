# Notebooks

For data files and reports, use the [Zimbabwe project guide](../docs/zimbabwe/README.md).

The [Zimbabwe visual atlas](zimbabwe_visual_atlas.ipynb) opens with four described satellite-backed maps of measured yield, model error, greenness and weather, followed by four other Zimbabwe charts and a gallery of 106 visuals from the project, its archives and provider manuals. The notebook embeds the figures and their explanations. Yield, prediction error and greenness use recorded field coordinates with regional close-ups. Each gallery ID has a caption, source link and full-resolution view. [Download the new figures or browse the source index](../results/visual_atlas/README.md).

## Start here for the data

[pass_archive_overview.ipynb](pass_archive_overview.ipynb): what the pass archive holds, to skim in a few minutes.
Surveys by country, year and crop; coordinates and a label-free check of what the pixel shows; every Sentinel-2 pass
and where its values come from; coverage by month; one field with all its passes; how to get X and y (`field_xy`,
`master`, your own monthly rule with a frozen split); what to handle with care; checks. It needs only
`data/passarchive_v1/release/passarchive_v1.duckdb` (2.7 GB, not in Git; see
[where to put the data](../docs/DATA_SETUP.md)), opens it read-only and runs in about one minute. The saved outputs
show everything without a run. The country outlines on the map are optional.

[pass_archive_query.ipynb](pass_archive_query.ipynb): the same file, to query yourself. One cell opens it read-only
and lists its tables and views; one cell holds a query to change (`select * from master limit 10`). No plots.

[allen_top15_cleaning.ipynb](allen_top15_cleaning.ipynb): Executed, label-free image-cleaning notebook.
It uses the original image-quality screen and top-15 ranks, then compares the best single pass with the median of the selected passes per field-month, audits
coverage and feature differences, and produces a small matched model handoff for Zida under
`data/passarchive_v1/cleaning/`. The source database is the same pass archive; the large intermediate scene
tables are generated in ignored `data/features/`.

## Start here for the results

[lacuna_results_consensus.ipynb](lacuna_results_consensus.ipynb): every current Lacuna number in one place, rebuilt
from the two DuckDB files with the code that made it: our baselines, time features, step-up ladder, Presto controls
and fold-0 scores, Felix's v1 and v2 runs, why the two teams' numbers differ, and one consensus. Each recomputed
number with a committed counterpart is checked against it, and so is every number in its answer
section. Needs both team databases; takes about three minutes.

## Figures for the midterm report

[midterm_figures.ipynb](midterm_figures.ipynb): 39 figures in three parts (data and maps, architecture, results), each
with a short text and a caption draft, so that the team can pick a few for each part. It writes each figure to
`report/figures/midterm/` as PNG (300 dpi) and PDF, and one overview sheet for each part. It needs
`data/v2/cropyield.duckdb`, the data v2 image chips for six figures, and the public map files that
[midterm_get_basemap.py](midterm_get_basemap.py) fetches into `data/imagery/basemap/` (git-ignored, about 45 MB). It
opens the database read-only and takes about five minutes. The saved outputs show every figure without a run.

## Reading order

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
merging the stronger data-validation modules into main. Guide 2 is kept byte for byte as its validation receipt
(`data_guide_2_zimbabwe.validation.json`) records it, so its commands still name the old flat script paths; the current
paths are in [scripts/README.md](../scripts/README.md#moved-on-8-nov-2026).

The second guide uses Zimbabwe, not Malawi: Lacuna 2023 is the target population and Zimbabwe 2024 is the auxiliary
training source. Both guides retain the distinction between historical data policies and later authorized experiments.

## Archive: the first pipeline and the old databases

Moved to [archive/](archive/) on 19 Nov 2026, unchanged except for the folder they start from. They describe the
data v1 pipeline and database (one clear scene per month); for new work use the pass archive notebooks at the top.
Open them from `notebooks/archive/`.

| Notebook | What it shows | Needs |
|---|---|---|
| [step3_labels_walkthrough.ipynb](archive/step3_labels_walkthrough.ipynb) | How `labels_v1` is built, one piece at a time | the clone |
| [step4_splits_walkthrough.ipynb](archive/step4_splits_walkthrough.ipynb) | How the frozen split files are built, one piece at a time | the clone |
| [duckdb_v1_tour.ipynb](archive/duckdb_v1_tour.ipynb) | The tables and views of the v1 database, with SQL only | `data/cropyield.duckdb` |
| [zimbabwe_master.ipynb](archive/zimbabwe_master.ipynb) | The Zimbabwe master table (labels, season indices, Presto, MOSAIKS) | `data/cropyield.duckdb` |
| [season_features_lacuna.ipynb](archive/season_features_lacuna.ipynb) | Season features for the Lacuna fields from the v1 database | `data/cropyield.duckdb` |
| [first_baselines/](archive/first_baselines/) | The first baseline notebook, the first data overview and their saved figures and tables (was the top-level folder `notebook/`) | the clone |

## Extra-input audits

| Notebook | What it shows | Needs to rerun |
|---|---|---|
| [07_kenya_extra_inputs_analysis.ipynb](07_kenya_extra_inputs_analysis.ipynb) | Kenya coverage, seasonal radar/weather profiles, 2 km within-village variation, point-support limits and model-input decisions | external Kenya Earth Engine and SoilGrids tables; saved outputs are embedded |
| [08_malawi_extra_inputs_analysis.ipynb](08_malawi_extra_inputs_analysis.ipynb) | Malawi polygon-level coverage, seasonal profiles, 2 km within-village variation and model-input decisions | external Malawi Earth Engine and SoilGrids tables; saved outputs are embedded |

## Experiment notebook

| Notebook | What it shows | Needs |
|---|---|---|
| [season_features_lacuna.ipynb](season_features_lacuna.ipynb) | Lacuna 2023 season features: whole-season mean, pre-harvest window, peak; folds 1–4 only | `data/v2/cropyield.duckdb` |

The scripted experiments, each with its own README, are in [experiments/](../experiments/).
