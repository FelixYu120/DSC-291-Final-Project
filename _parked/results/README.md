# Results

`metrics.csv`: append-only; every figure and table in the report is generated from this file. One row per
run, cohort, split family, arm, fold and metric:

`run_id, timestamp, git_commit, config, cohort, split_family, split_sha256, arm, repeat, subset, fold, seed,
n_train, n_test, metric, value, ci_low, ci_high`

`fold` is an integer for per-fold rows and `pooled` for the pooled out-of-fold score; `ci_low` and `ci_high`
are the cluster-bootstrap interval (empty on per-fold rows). `repeat` is the split repeat. `subset` names a
part of the test rows: `seen_region` or `new_region` for the Kenya temporal split, `<source>><target>|<scaling>`
for the transfer rows of `scripts/run_transfer.py` (`split_family = transfer`). Metric names and the bootstrap
are defined in `docs/EVALUATION.md`; the noise ceiling is a row with `arm = noise_ceiling`.
