# Experiment configs

One YAML file per experiment (cohorts, rows, split families, arms, metrics, seed). A run records the config
file and its git commit next to its results, so a config that has been run is copied to a new name rather
than edited.

| File | What |
|---|---|
| `b0_seasonal_indices_ridge.yaml` | B0, the first baseline: seasonal indices + Ridge next to R0, R1, R2 (`docs/ROADMAP.md`, section 2) |
| `x1_cross_cohort_transfer.yaml` | X1: every ordered pair of cohorts, seasonal indices, at three harmonization levels (`scripts/run_transfer.py`) |
| `sentinel2_windows_pilot48.csv`, `sentinel2_windows_malawi_2023_pilot.csv` | fixed season windows of the pilot downloads (`--date-overrides`) |

Run one with `python scripts/run_experiment.py configs/<file>.yaml`; `--cohorts` limits it to some cohorts and
`--no-save` writes nothing. Only an X1 config goes through `scripts/run_transfer.py`.
