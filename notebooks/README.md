# Notebooks

For data files and reports, use the [Zimbabwe project guide](../docs/zimbabwe/README.md).

## Start here for the results

[lacuna_results_consensus.ipynb](lacuna_results_consensus.ipynb): every current Lacuna number in one place, rebuilt
from the two DuckDB files with the code that made it: our baselines, time features, step-up ladder, Presto controls
and fold-0 scores, Felix's v1 and v2 runs, why the two teams' numbers differ, and one consensus. Each recomputed
number with a committed counterpart is checked against it, and so is every number in its answer
section. Needs both team databases; takes about three minutes.

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

## Walkthroughs and tours

These notebooks run the real code on the real data in small cells and write nothing. Open them from the
`notebooks/` folder; they find the repository folder from there.

| Notebook | What it shows | Needs |
|---|---|---|
| [step3_labels_walkthrough.ipynb](step3_labels_walkthrough.ipynb) | How `labels_v1` is built, one piece at a time | the clone |
| [step4_splits_walkthrough.ipynb](step4_splits_walkthrough.ipynb) | How the frozen split files are built, one piece at a time | the clone |
| [duckdb_v1_tour.ipynb](duckdb_v1_tour.ipynb) | The tables and views of the v1 database, with SQL only | `data/cropyield.duckdb` |
| [zimbabwe_master.ipynb](zimbabwe_master.ipynb) | The Zimbabwe master table (labels, season indices, Presto, MOSAIKS) | `data/cropyield.duckdb` |

## Experiment notebook

| Notebook | What it shows | Needs |
|---|---|---|
| [season_features_lacuna.ipynb](season_features_lacuna.ipynb) | Lacuna 2023 season features: whole-season mean, pre-harvest window, peak; folds 1–4 only | `data/v2/cropyield.duckdb` |

The scripted experiments, each with its own README, are in [experiments/](../experiments/).
