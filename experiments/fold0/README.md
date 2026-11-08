# Fold 0 scoring (Lacuna 2023)

Owner ruling of 8 Nov 2026: fold 0 of `s1_cc2km` is not a one-time test. It is scored again when an experiment
needs it, for a small fixed set of arms, and every look is logged. Development scores stay on folds 1–4.

```bash
python experiments/fold0/score_fold0.py --reason "why this look is needed"
```

Run it with the global Python that has `torch` (X1 reads the Presto input arrays), from the repository root. It needs
the pinned v2 database (`data/v2/cropyield.duckdb`) and the Presto P0 embeddings in
`experiments/presto_finetune/runs/zimbabwe_lacuna_2022_2023/p0_embeddings.npz`. A blank `--reason` is refused.

```bash
python -m pytest -q experiments/fold0/test_fold0.py
```

## What one run does

- Every arm trains on folds 1–4 (1,504 fields) and predicts fold 0 (376 fields). No fold-0 label enters any fit.
  `test_fold0.py` checks this for the Ridge arms (`fold0_predict`: V0–V3, L1, M1, M2, M2-pre, P0) and for R0, R1
  and A1; the run also stops if A1 differs from the Ridge head. X1 fits only on the folds 1–4 rows by
  construction (`x1_predict`); it needs `torch` and the database, so no unit test covers it.
- Same features and the same Ridge head as the development runs (`experiments/stepup/stepup.py`,
  `experiments/time_features/time_features.py`, `experiments/presto_finetune/posthoc_controls.py`).
- Scores: RMSE, MAE, bias (prediction minus yield), R² (1 − SSE/SST over the 376 fields) and the rank inside clusters.
  Each arm against A1 with the paired cluster bootstrap (2,000 draws, seed 20261029). `p Holm` corrects the rank
  p-value over every arm except R0, R1 and A1.
- It stops if the database differs from `configs/team_database_v2.json` or a labels or split file changed.
- It writes `runs/<UTC time>/` (`scores.csv`, `predictions.csv`, `run.json`, `RESULT.md`) and never overwrites
  an earlier run. It adds one line to `looks.csv` with the time, the commit, the reason and the arms.

## Arms

| Key | Arm | Source |
|---|---|---|
| R0 | training mean | `scripts/baselines/baseline_table.py` |
| R1 | coordinates only, 10 nearest fields | `scripts/baselines/baseline_table.py` |
| A1 | Ridge on the 10 season indices (max + mean of 5 indices) | `scripts/baselines/baseline_table.py` |
| V0, V1, V2, V3 | season mean, pre-harvest mean, max, mean + median + max | `time_features.py` |
| L1 | GCVI peak only (Li et al. 2022) | `time_features.py` |
| M1, M2, M2-pre | monthly index curve, monthly band curve, band curve of the pre-harvest months | `time_features.py` |
| P0 | frozen Presto embedding (128) | `p0_embeddings.npz` of `experiments/presto_finetune/` (the input of `stepup.py` step S10) |
| X1 | raw monthly inputs (10 bands + NDVI x 9 months, mean fill + missing flags) | `posthoc_controls.py` |

To add an arm, add it to `NAMES` and to `VARIANTS` (or the code that builds it) in `score_fold0.py`, then run with a
reason. Keep the set small: each look at fold 0 makes it less of a test.

## How to read the scores

- Fold 0 is a confirmation set, not an untouched test. R0, R1 and A1 were scored on it in the v1 baseline table
  (all five folds, from 30 Oct), the other chat's `experiments/fold0_final/` scored R0, R1, A1 and X1 on 8 Nov, and
  the development runs train on fold-0 fields.
- `p Holm` corrects inside one run. It does not correct across runs: read `looks.csv` to see how often fold 0 was used.
- 376 fields in fewer than 60 clusters: intervals are wide. A difference that is not clear on folds 1–4 should not be
  called a result because it looks clear on fold 0.
