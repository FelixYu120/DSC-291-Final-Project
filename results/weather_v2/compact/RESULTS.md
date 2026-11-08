# Compact weather results

Same 1,504 evaluation fields; exploratory. Lower RMSE is better.

Training rows follow `labels_v1.include_primary` (config `training_rows`); rows and source permissions come from `data/runs/zimbabwe_merge_v2`.

| Method | RMSE t/ha | MAE t/ha | R² |
|---|---:|---:|---:|
| monthly_target | 1.692594 | 1.322254 | 0.272339 |
| monthly_adaptive | 1.686930 | 1.317029 | 0.277201 |
| monthly_tree_target | 1.659352 | 1.289692 | 0.300640 |
| monthly_tree_transfer | 1.676956 | 1.303770 | 0.285723 |
| weather_target | 1.744311 | 1.364891 | 0.227192 |
| weather_adaptive | 1.738593 | 1.359489 | 0.232251 |
| weather_shared | 1.755083 | 1.371015 | 0.217618 |
| weather_tree_target | 1.695751 | 1.311391 | 0.269622 |
| weather_tree_transfer | 1.716384 | 1.336362 | 0.251740 |
| compact2_target | 1.699398 | 1.330826 | 0.266477 |
| compact2_adaptive | 1.695877 | 1.327306 | 0.269514 |
| compact2_shared | 1.675774 | 1.301876 | 0.286730 |
| compact2_tree_target | 1.680642 | 1.311757 | 0.282579 |
| compact2_tree_transfer | 1.660726 | 1.298501 | 0.299482 |
| compact4_target | 1.728332 | 1.355323 | 0.241287 |
| compact4_adaptive | 1.723129 | 1.350252 | 0.245847 |
| compact4_shared | 1.642762 | 1.276286 | 0.314555 |
| compact4_tree_target | 1.672713 | 1.296116 | 0.289333 |
| compact4_tree_transfer | 1.690386 | 1.312152 | 0.274237 |

Primary compact4 merging difference +0.017673; 95% group interval [-0.009484, +0.046680].

See paired_differences.csv for all contrasts and the weather-cell bootstrap sensitivity, and training_outer_diagnostics.csv for fit gaps.

![Compact weather comparison](compact_weather_comparison.png)
