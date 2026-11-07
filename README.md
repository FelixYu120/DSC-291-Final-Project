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

The basic merge experiment uses **10 vegetation-index features with Ridge**, not MOSAIKS. Naive pooling hurts;
source-aware adjustment removes most of that penalty, but adding 2024 has not established a reliable accuracy gain.
The later weather and richer-feature experiments are reported separately.

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

## Repository map

| Folder | Contents |
|---|---|
| [docs/](docs/README.md) | Zimbabwe reports, quality guides, reference contracts and history |
| [data/](data/README.md) | Source snapshots, cleaned exports, frozen splits and experiment releases |
| [results/](results/README.md) | Index of all results plus aggregate quality/baseline evidence |
| [notebooks/](notebooks/README.md) | Executed explanations and checks |
| [scripts/](scripts/README.md) | Commands for steps 1–13, audits and reproduction |
| [configs/](configs/README.md) | Dataset fingerprints and experiment settings |
| [src/cropyield/](src/cropyield/) | Data preparation, features, baselines and experiment implementation |
| [sql/](sql/README.md) | Database schema and views |
| [tests/](tests/) | Automated checks; run `python -m pytest -q` |
| [_parked/](_parked/LANDING.md) | Archived earlier code and results; excluded from the current workflow |

Data licences and original-provider attribution are in [data/README.txt](data/README.txt).
Weather attribution and exact retrieval methods are in [the methods report](docs/zimbabwe/METHODS.md#sources-and-provenance).
