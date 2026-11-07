# DSC-291 Final Project: field-level maize yield from Sentinel-2 in sub-Saharan Africa

Felix Yu, Florian Saewert, Liuan Lu, Pamely Zantou, Zida Jin. UCSD DSC 291, Fall 2026.

**Start with the data guide: [`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb).** It teaches the data from
zero: which files make it, where it comes from, how it is matched and split, and what X and Y look like.

**Continue with [Data Guide 2: Zimbabwe](notebooks/data_guide_2_zimbabwe.ipynb).** It walks through cleaning,
yield conversion, merging the two Zimbabwe seasons, spatial evaluation, weather provenance, model results and
the compact-weather overfitting check. Its default run uses tracked artifacts offline, without the database or model retraining.
See the [notebook index](notebooks/README.md) for the reading order.

**Zimbabwe midterm handoff (November 7):** [`docs/ZIMBABWE_DATA_HANDOFF.md`](docs/ZIMBABWE_DATA_HANDOFF.md)
documents the November 4 Zimbabwe focus, source checks, cleaned exports and explicit train/validation/historical-test
roles. Reproduce the package with `python scripts/step8_build_zimbabwe_handoff.py`; it reads the team database without
rebuilding it. The older cross-country plan below remains background, not the current midterm scope.

**Zimbabwe merge experiment:** [`docs/ZIMBABWE_MERGE_PROTOCOL.md`](docs/ZIMBABWE_MERGE_PROTOCOL.md) records the
compatibility fixes and Lacuna-only versus Lacuna + 2024 comparison. Run
`python scripts/step9_compare_zimbabwe_merge.py` for the complete harmonized label catalog, audited features,
nested spatial validation, predictions and report under `data/runs/zimbabwe_merge_v1/`. Fold 0 stays reserved.
The [results and teammate explanation](docs/ZIMBABWE_MERGE_RESULTS.md) report all nine arms: naive pooling hurts;
adapted pooling approximately matches Lacuna-only, with no established accuracy gain.

**Why transfer helps little:** the [follow-up findings](docs/ZIMBABWE_TRANSFER_FINDINGS.md) separate source quality,
population shift and model limitations. Step 10 tests 30 target arms plus source learnability: richer monthly models
improve performance substantially, while the additional contribution from 2024 remains small and uncertain.
Reproduce with `python scripts/step10_diagnose_zimbabwe_transfer.py`.

**Zimbabwe weather and complete methods:** the [consolidated methods](docs/ZIMBABWE_COMPLETE_METHODS.md) explain
both sources, cleaning, units, seasons, every merge method and the weather comparison. Step 11 adds 46 NASA POWER
rainfall/temperature predictors to all 6,598 labels, with raw API snapshots and provenance. Step 12 compares
Lacuna-only and merged models on the exact existing splits. The [weather protocol](docs/ZIMBABWE_WEATHER_PROTOCOL.md)
was fixed before scoring; results and enriched comparison data are in `data/runs/zimbabwe_weather_v1/`.
The weather experiment did not improve accuracy: monthly-tree RMSE changes from 1.6594 / 1.6578 (Lacuna / merged)
to 1.6958 / 1.7221 with weather. Read the [methods Page](https://chatgpt.com/space/page_61fc048f13d081918467a88b670e9da4)
for all arms, paired uncertainty, provenance and limitations.

**Compact weather follow-up:** step 13 tests two/four fixed seasonal weather summaries using the same splits.
Two-feature merged trees recover some of the 46-feature loss (RMSE 1.6740 versus 1.7221), but remain behind
imagery-only merged trees (1.6578). Four-feature shared Ridge reaches 1.6554; its 0.0023 advantage over the best
imagery-only result is uncertain. The [short report](docs/ZIMBABWE_COMPLETE_METHODS.md) puts the conclusion first
and methods/provenance in an appendix. Results: `data/runs/zimbabwe_weather_compact_v1/`;
reproduce with `python scripts/step13_compare_compact_weather.py` and check with
`python scripts/verify_compact_weather.py`. The [compact protocol](docs/ZIMBABWE_COMPACT_WEATHER_PROTOCOL.md)
defines the primary comparison; the observed best-arm benchmark checks are explicitly post-hoc.

**Question.** Within one smallholder cohort, which Sentinel-2 representation predicts field-level maize yield best,
and how much of that skill survives in new villages, new districts and a new season? The plan is
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Get started

Clone **outside OneDrive** (for example `C:\Dev\`). Use Python 3.12 or newer. Run these commands once, from the
repository root:

```bash
python -m venv .venv
.venv\Scripts\activate                   # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt   # the exact package versions, and this repository
python -m pytest -q                      # small checks, no imagery needed
```

Labels and splits come with the clone. Then get the team database: download the file from the link in the team chat,
and put it at `data/cropyield.duckdb`. Do not rebuild it. Open
[`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb) with the `.venv` kernel, for example in VS Code, and press
Run All. Step 2 of the guide checks that your file is the team copy.

You need the chips only to draw pixels or to build new image features. In Step 2 of the guide, set `DOWNLOAD = True` in
the pilot cell and press its Run arrow, then do the same for all the data. Each cell then asks for a typed `yes`, shows
a loading bar, continues after a stop, and builds a database of your own.

Without the notebook, the same steps are:

```bash
python scripts/get_all_data.py           # labels check and Sentinel-2 chips (48-record pilot, one process)
python scripts/step6_build_database.py   # data/cropyield.duckdb
python scripts/step7_check_data.py       # what the database holds, per cohort
```

## Where things are

| Path | What it holds |
|---|---|
| [`notebooks/data_guide.ipynb`](notebooks/data_guide.ipynb) | the one guide to the data |
| [`scripts/`](scripts/README.md) | the data path, one script per step |
| [`sql/`](sql/README.md) | the database schema, views and example queries |
| `src/cropyield/` | the package that the scripts and the notebook import |
| `data/` | labels and splits are frozen and committed; the database is one shared file; chips stay local |
| `docs/` | plan, data notes, evaluation, related work, decisions and structure |
| `_parked/` | everything that is not on the data path, safe and listed in `_parked/MANIFEST.csv` |

Licences and attribution: `data/README.txt`. Keep the provider citations when you use or share the data.
