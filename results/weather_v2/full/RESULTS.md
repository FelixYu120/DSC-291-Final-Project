# Zimbabwe weather experiment

Exploratory results; every arm predicts the same 1,504 Lacuna 2023 fields. Fold 0 remains reserved. RMSE/MAE/bias are t/ha. No-weather predictions are unchanged saved controls.

Training rows follow `labels_v1.include_primary` (config `training_rows`); rows, splits and source permissions come from `data/runs/zimbabwe_merge_v2`, so the 2024 pool holds no recorded zeros.

| Method | RMSE | MAE | Bias | R² |
|---|---:|---:|---:|---:|
| monthly_target | 1.692594 | 1.322254 | +0.004525 | 0.272339 |
| monthly_adaptive | 1.686930 | 1.317029 | +0.006234 | 0.277201 |
| monthly_tree_target | 1.659352 | 1.289692 | -0.005360 | 0.300640 |
| monthly_tree_transfer | 1.676956 | 1.303770 | -0.045808 | 0.285723 |
| weather_only_target | 1.905502 | 1.512309 | -0.056175 | 0.077764 |
| weather_target | 1.744311 | 1.364891 | -0.032396 | 0.227192 |
| weather_adaptive | 1.738593 | 1.359489 | -0.033761 | 0.232251 |
| weather_shared | 1.755083 | 1.371015 | -0.020456 | 0.217618 |
| interactions_target | 1.733092 | 1.351325 | -0.014426 | 0.237101 |
| interactions_adaptive | 1.726112 | 1.344651 | -0.017165 | 0.243234 |
| interactions_shared | 1.747439 | 1.359200 | -0.015548 | 0.224418 |
| weather_tree_target | 1.695751 | 1.311391 | -0.058559 | 0.269622 |
| weather_tree_transfer | 1.716384 | 1.336362 | -0.077111 | 0.251740 |

Primary: merged weather minus Lacuna-only weather RMSE = +0.020633; 95% spatial-group bootstrap interval [-0.004421, +0.044261].

Weather × merging interaction = +0.003029; 95% interval [-0.034625, +0.038984]. Negative means weather increased the merging benefit.

## Selected source contributions

| Method | Fold | Source/target weight ratio | Source rows used |
|---|---:|---:|---:|
| weather_only_target | 1 | 0 | 0 |
| weather_target | 1 | 0 | 0 |
| weather_adaptive | 1 | 0.3 | 2367 |
| weather_shared | 1 | 0.3 | 2367 |
| interactions_target | 1 | 0 | 0 |
| interactions_adaptive | 1 | 0.3 | 2367 |
| interactions_shared | 1 | 0.3 | 2367 |
| weather_tree_target | 1 | 0 | 0 |
| weather_tree_transfer | 1 | 0.1 | 2367 |
| weather_only_target | 2 | 0 | 0 |
| weather_target | 2 | 0 | 0 |
| weather_adaptive | 2 | 1 | 2335 |
| weather_shared | 2 | 0.3 | 2335 |
| interactions_target | 2 | 0 | 0 |
| interactions_adaptive | 2 | 1 | 2335 |
| interactions_shared | 2 | 1 | 2335 |
| weather_tree_target | 2 | 0 | 0 |
| weather_tree_transfer | 2 | 0.1 | 2335 |
| weather_only_target | 3 | 0 | 0 |
| weather_target | 3 | 0 | 0 |
| weather_adaptive | 3 | 1 | 2354 |
| weather_shared | 3 | 0 | 0 |
| interactions_target | 3 | 0 | 0 |
| interactions_adaptive | 3 | 1 | 2354 |
| interactions_shared | 3 | 0 | 0 |
| weather_tree_target | 3 | 0 | 0 |
| weather_tree_transfer | 3 | 1 | 2354 |
| weather_only_target | 4 | 0 | 0 |
| weather_target | 4 | 0 | 0 |
| weather_adaptive | 4 | 1 | 2357 |
| weather_shared | 4 | 0.3 | 2357 |
| interactions_target | 4 | 0 | 0 |
| interactions_adaptive | 4 | 1 | 2357 |
| interactions_shared | 4 | 0.3 | 2357 |
| weather_tree_target | 4 | 0 | 0 |
| weather_tree_transfer | 4 | 0 | 0 |

Weather-cell overlap: 1447/1504 evaluation fields share a weather cell with target-training fields. The required 2 km splits do not test entirely new weather cells.

## Weather contrast on the same 97 cells

| Harvest year | Jan–Mar rainfall % normal | Jan–Mar temperature anomaly °C |
|---|---:|---:|
| 2023 | 117.615 | -0.624 |
| 2024 | 63.703 | 1.350 |

The weather contrast is descriptive, not causal attribution of yield differences. Year, provider, management, and measurement protocol remain confounded. Monthly regional weather cannot establish field drought damage or dry-spell duration.

Run step11 with the cached NASA responses, then step12. PROTOCOL.md describes source matching, unit conversion, baseline construction, training-only preprocessing and all parameter grids. The full input/output hash chain is in manifest.json.

![Weather experiment](weather_comparison.png)
