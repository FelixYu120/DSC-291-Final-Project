# R0, R1 and A1: a runnable first comparison

The question is whether seasonal satellite measurements help estimate a field's maize yield beyond what
we can already predict from the average yield and the field's location. Each dataset has its own models
because measurement protocols differ.

| Arm | Information it uses | Prediction |
|---|---|---|
| R0 | Training yields | The same training-fold mean for every test field |
| R1 | Coordinates and training yields | Mean yield of the 10 nearest training fields, by great-circle distance |
| A1 | Seasonal vegetation indices and training yields | Ridge regression, with regularisation chosen by grouped validation |

A1 uses the mean and maximum of NDVI, GCVI, MTCI, NDVI705 and NDVI740: ten features. Ridge learns a
weighted combination of them and penalises large coefficients to reduce overfitting. The target is
tonnes per hectare (t/ha), converted once from the frozen labels' kg/ha.

## Run it

From the repository root, after the README setup and obtaining `data/cropyield.duckdb`:

```bash
python scripts/run_baselines.py
```

On macOS, the existing project environment can also be used without activation:

```bash
.venv/bin/python scripts/run_baselines.py
```

The default configuration is `configs/spatial_baselines_v1.yaml`. A saved experiment configuration
should stay unchanged; copy it to a new name for a deliberate follow-up. Optional arguments are
`--config PATH`, `--data-dir PATH` and `--output-dir NEW_DIRECTORY`. A data directory must contain the
verified shared database, frozen labels and split files. Existing output directories are never overwritten.

## Follow the code

1. **Load and verify — `src/cropyield/baselines/experiment.py`, `verify_inputs` and `load_rows`.**
   Check the database, labels and split hashes, then call `load_xy` for the ten features. Join the frozen
   labels, coordinates and split assignments by `obs_id`. All arms use exactly the same eligible rows:
   251 Malawi, 3,977 Kenya and 1,880 Lacuna. Preserve zeros; fail on missing/nonfinite features rather than
   silently excluding observations. Frozen label order preserves the historical KNN tie breaking.
2. **Hold out geographic groups — `out_of_fold`.**
   For each of five frozen `s1_cc2km` folds, train on the other four and predict the held-out fold.
   Every observation receives exactly one prediction per arm. A geographic `group_id` cannot cross folds;
   the existing split check verifies that test fields are at least 2 km from training fields.
3. **Fit the models — `src/cropyield/baselines/models.py`.**
   R0 averages training yields. R1 converts latitude/longitude to radians for haversine distance.
   A1 uses `Winsorize -> StandardScaler -> Ridge` inside `GridSearchCV`, with five-fold `GroupKFold`
   using the outer training rows' `group_id`. The search tries 17 alphas from 0.001 to 100,000. Both the
   1st/99th-percentile clipping limits and scaling statistics are fitted again within each inner
   training fold. The selected pipeline is refitted on all outer training rows, then predicts the test rows.
4. **Evaluate — `src/cropyield/baselines/scoring.py`.**
   Combine the held-out predictions within each dataset. Report RMSE, MAE, bias, R² and Spearman.
   Use 2,000 resamples of entire geographic groups for 95% confidence intervals. Compare each model's
   RMSE with R1 using the same sampled groups. The bootstrap describes uncertainty in these held-out
   predictions; it does not refit the model or resolve uncertainty in the yield measurements.

## Read the outputs

Each run has a new directory under `results/spatial_baselines/`:

- `summary.csv`: one row per dataset and arm, with pooled scores and RMSE intervals.
- `metrics.csv`: pooled scores and qualifying individual-fold scores, with run/commit/config/split identifiers.
- `fold_fits.csv`: training/test counts, group counts and the selected Ridge alpha for each fold.
- `config.yaml` and `run.json`: exact configuration, data and source hashes, package versions and Git state.

The per-field `predictions.parquet` stays in `data/runs/spatial_baselines/<run_id>/`, outside Git, and its
path/hash is in `run.json`. It includes IDs, groups, folds, observed yield and predictions for each arm.
To compare models, use matching IDs on the same folds; never treat monthly rows as independent labels.

Lower RMSE/MAE is better. Positive bias means overprediction; negative bias means underprediction. Higher
R² and Spearman are better, but a negative R² is possible. `rmse_minus_R1` is the model's RMSE minus the
coordinates baseline: a negative interval entirely below zero supports an improvement over R1. An interval
crossing zero is inconclusive under this comparison. Malawi's small individual folds are not scored in the
metrics table; use its pooled results. A fold must have at least 100 test fields and 10 groups for its own scores.

## Scope of the result

These are reproductions on previously inspected research splits, not a fresh final holdout. The current
runner supports only the already evaluated R0/R1/A1 arms and `s1_cc2km`. Before evaluating a new model such
as MOSAIKS or Presto, specify the restricted fold-0 observation IDs across split families with the team.
The same fold number can refer to different fields in another split family.

Keep the frozen labels/splits and shared database intact. The 2 km separation tests new nearby locations;
it does not guarantee independence from broader regional conditions. District and Kenya temporal tests
are subsequent experiments. Kenya GPS/season-window issues, cloud gaps and differing yield protocols remain
documented limitations in `DATA.md`. Paired crop cuts are not used here to claim a universal error floor.
