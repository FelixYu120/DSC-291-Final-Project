# Saved model comparisons in TensorBoard

`export.py` reads **existing aggregated result tables** and writes new TensorBoard event files. It does not train models, change source files, or record field-level observations. Each model has a run directory; its complete method and protocol are in the TensorBoard **Text** tab and in the export manifest. Directory names are shortened with a hash to avoid Windows path limits.

In **Time Series**, select `overall/rmse_t_ha` or `overall/r2` to compare published summary metrics. Select `by_fold/rmse_t_ha` or `by_fold/r2` for per-fold metrics. **The horizontal step in those charts is the fold number, not a training epoch**. Overall metrics are a single point at step zero; they are not training curves. RMSE and MAE are in tonnes per hectare. `spearman_overall` and `rank_centered_clusters` are distinct metrics.

`fresh_merge`, `fresh_diagnosis`, and the `saved_weather`, `saved_compact`, `saved_temporal`, and `saved_multiyear` runs use the pinned original team database and the Zimbabwe experiment v2 protocol excluding fold 0. `saved_footprint`, `saved_presto`, and `saved_controls` use the separate data-v2 database and our protocol, in which fold-0 fields train (still in use; the team has not chosen between the two). The two protocols score the same 1,504 Lacuna fields but differ in training rows (1,504 against 1,128 per fold), database (v2 against v1) and tuning (5 inner folds and 17 alphas against 3 and 6), so do not compare them as one leaderboard (`notebooks/lacuna_results_consensus.ipynb`, section 6). The charts show arm scores only; the paired differences and their intervals are in each release's `paired_differences.csv`, and most primary gaps are not significant. `fresh_` only means "read from `--root`": it marks a replay only when `--root` points at a separate replay copy. With `--root .` every `fresh_` series is the saved release itself. Footprint and Presto rows are also separated by cohort. All these saved models use retrospective full-season inputs; they do not establish pre-harvest forecasting accuracy. Presto's own per-epoch curves remain under the separate `one`, `two`, `none`, `light`, `medium`, and `strong` runs.

To refresh after newly generated stages finish, specify a **new** log directory; the command refuses an existing one. For example, from this repository root, with a Python environment containing PyTorch and TensorBoard:

```powershell
python experiments/tensorboard_comparison/export.py --root <isolated replay copy> --archive-root . --logdir path/to/tensorboard_logs/comparison/run2
```

`--root` is the location of fresh `data/runs/zimbabwe_*_v2` artifacts; `--archive-root` points to the repo containing `results/` and the historical Presto and footprint tables. They may differ when using an isolated replay. The manifest records each source path, SHA-256, status and number of exported scalars. Missing stages are printed and recorded; they are not invented. Re-run to a new directory once those stages exist.

Run the tests with `python -m pytest -q experiments/tensorboard_comparison/test_export.py` (needs `torch` and `tensorboard`). The event files themselves stay out of git; rebuild them with the command above.
