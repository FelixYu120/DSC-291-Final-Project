# Splits

Frozen train/test assignments, created from `labels_v1` before any model is trained and never edited
afterwards. Full rules: `docs/EVALUATION.md`, section 4.

- One CSV per cohort and family: `<cohort>__<family>.csv`, family one of `s1_cc2km` (new village),
  `s2_region` (new district), `temporal` (Kenya 2019 to 2020 and back), `random_diag` (diagnostic).
- Columns: `obs_id`, `cohort`, `season_year`, `cluster_id`, `group_id`, `fold`, `repeat`, `family`.
- Every `labels_v1` row of the cohort, also rows without imagery.
- Seed `20261029`; `manifest.json` records the generator commit, the input and output SHA-256 and the row
  counts. Tagged `splits-v1` in git.
