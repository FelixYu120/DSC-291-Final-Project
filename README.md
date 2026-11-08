# Zimbabwe maize-yield data and experiments

DSC 291, UC San Diego, Fall 2026 — Felix Yu, Florian Saewert, Liuan Lu, Pamely Zantou and Zida Jin.

The current midterm work cleans Zimbabwe crop-cut data, compares Lacuna-only training with adding Zimbabwe 2024,
and tests whether rainfall and temperature improve prediction. Earlier Malawi/Kenya work remains available as background.

## Start here

| I want to… | Open |
|---|---|
| Read the one-page basic-feature Ridge summary | [Zimbabwe summary](docs/zimbabwe/SUMMARY.md) |
| Find everything added for Zimbabwe, in step order | [Zimbabwe project guide](docs/zimbabwe/README.md) |
| Walk through the data, methods and results | [Data Guide 2: Zimbabwe](notebooks/data_guide_2_zimbabwe.ipynb) |
| Find the cleaned or merged data | [Data directory](data/README.md) |
| Find `RESULTS.md`, scores and predictions | [Results directory](results/README.md) |
| Reproduce an existing experiment | [Reproduction guide](docs/zimbabwe/REPRODUCING.md) |
| Check how the V0–V3 R² values were calculated | [R² audit and Claude review packet](docs/zimbabwe/R2_AUDIT.md) |
| Read the whole dataset: structure, cleaning, quality register, splits | [Dataset guide](docs/DATASET.md) |
| See the R0/R1/A1 baseline table (folds 1–4) | [Baseline table](results/baseline_table.md), [data v2](results/v2/baseline_table.md) |

The basic merge experiment uses **10 vegetation-index features with Ridge**, not MOSAIKS. Naive pooling hurts;
source-aware adjustment removes most of that penalty, but adding 2024 has not established a reliable accuracy gain.
The later weather and richer-feature experiments are reported separately. The [seasonal aggregation comparison](docs/zimbabwe/AGGREGATION_RESULTS.md) tests mean, crop-date preharvest mean, maximum, median and a modal estimate. The [expanded-training comparison](docs/zimbabwe/MULTIYEAR_RESULTS.md) audits 2022–2024 coverage and tests all eligible Lacuna training rows with and without 2024 on the same 2023 evaluation fields.

## Read or run the notebooks

The notebooks include saved outputs that can be read on GitHub. For local execution, use Python 3.12 or newer:

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Select that environment as the notebook kernel. The Zimbabwe guide runs from committed artifacts without a database,
downloads or model fitting by default. The [notebook index](notebooks/README.md) explains all three notebooks.

For database audits or full experiment replay, obtain the shared team database from the team chat and place it at
`data/cropyield.duckdb`. Its fingerprint is recorded in `configs/team_database_v1.json`. Do not rebuild that file:
the original build step would remove its Presto embeddings. See [scripts](scripts/README.md) for the appropriate command.

## Data v2 and the Lacuna experiments

Data v2 sits next to v1 and changes nothing in it. It adds Malawi 2022 (529 walked polygons, photos from the older
`sentinel-2-l2a` collection) and tries up to 24 photos for each cloudy month (522 more clear field-months). Its labels,
audit and splits come with the clone in `data/v2/`. Get the v2 database from the same team link and put it at
`data/v2/cropyield.duckdb` (22,818,816 bytes; the SHA-256 is in `configs/team_database_v2.json`). Keep the v1 file too.

- The v2 database has **no Presto and no MOSAIKS rows**. Never join v1 Presto or MOSAIKS rows to v2 rows: they were made
  from other photos (Malawi 2022 most of all).
- Leave `CROPYIELD_DATA_DIR` unset and use the `--version 2` switch. Steps 8 and 9 stop if a database differs from its pin.

```bash
python scripts/step8_run_baseline.py --version 2   # results/v2/baseline_table.md (folds 1-4 scored)
python scripts/step9_compare_data_v2.py            # results/v2/data_v2_comparison.md: v2 against v1, and the Malawi season transfer
python scripts/step7_check_data.py --version 2     # what the v2 database holds, per cohort
```

The rules written before any v2 score: [`docs/DATA_V2_PLAN.md`](docs/DATA_V2_PLAN.md). The results: `docs/DECISIONS.md`
(7 Nov 2026). The whole dataset, its cleaning, its known problems and its splits: [`docs/DATASET.md`](docs/DATASET.md).

Experiments on folds 1–4 of `s1_cc2km` (fold 0 never scored), each with its README:
[`experiments/stepup/`](experiments/stepup/README.md) (step-up ladder, between/within-village R², audits),
[`experiments/time_features/`](experiments/time_features/README.md) (GCVI peak and pre-harvest windows),
[`experiments/presto_finetune/`](experiments/presto_finetune/README.md) (Presto frozen and fine-tuned).

## Repository map

| Folder | Contents |
|---|---|
| [docs/](docs/README.md) | Zimbabwe reports, quality guides, reference contracts and history |
| [data/](data/README.md) | Source snapshots, cleaned exports, frozen splits and experiment releases; `data/v2/` holds data v2 |
| [results/](results/README.md) | Index of all results plus aggregate quality/baseline evidence |
| [notebooks/](notebooks/README.md) | Executed explanations and checks |
| [scripts/](scripts/README.md) | Commands for steps 1–15, audits and reproduction |
| [configs/](configs/README.md) | Dataset fingerprints and experiment settings |
| [experiments/](experiments/) | Lacuna step-up ladder, time features and Presto runs (one README each) |
| [src/cropyield/](src/cropyield/) | Data preparation, features, baselines and experiment implementation |
| [sql/](sql/README.md) | Database schema and views |
| [tests/](tests/) | Automated checks; run `python -m pytest -q` |
| [_parked/](_parked/LANDING.md) | Archived earlier code and results; excluded from the current workflow |

Data licences and original-provider attribution are in [data/README.txt](data/README.txt).
Weather attribution and exact retrieval methods are in [the methods report](docs/zimbabwe/METHODS.md#sources-and-provenance).
