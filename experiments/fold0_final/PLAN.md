# Fold 0 final test (written 8 Nov 2026, before any fold-0 score)

The owner asked for one test of X1 on fold 0. Fold 0 has not been scored before by any arm in the Lacuna cohort.

- Cohort: `zimbabwe_lacuna_2022_2023` only (the paper is Zimbabwe-only).
- Train on folds 1-4 (all their fields), predict fold 0. One run. No change to any model after the run.
- Arms (fixed now):
  - R0: training mean.
  - R1: coordinates kNN, k = 10 (step 8).
  - A1: Ridge on the 10 season indices (step 8 `ridge_cv`, same alpha grid).
  - X1: Ridge on the 99 raw monthly inputs (10 bands + NDVI x 9 months, mean-filled + missing flags), the same
    code as `experiments/presto_finetune/posthoc_controls.py`.
- Hyperparameters: alpha chosen by grouped inner CV on folds 1-4 only (the existing code).
- Scores: RMSE, R2, rank inside clusters; pairs X1-A1, X1-R1, A1-R1 with the paired cluster bootstrap
  (95 %, 2,000 draws, seed 20261029), the same functions as `run_cohort.py`.
- Claim rule: X1 beats A1 if the rank interval of X1 minus A1 is above 0 and the RMSE interval is not entirely
  above 0 (the Presto PLAN.md rule).
- Whatever the result, it is reported as it is. Fold 0 is used up for these four arms.
- 8 Nov 2026, correction after the run: the line "Fold 0 has not been scored before by any arm" is wrong for R0, R1 and A1. They were scored on fold 0 in the v1 baseline table (all five folds, first on 30 Oct); only X1 was fresh here. Since the owner ruling of 8 Nov, fold 0 is scored with `experiments/fold0/score_fold0.py`, which logs every look; its first run reproduced these four arms exactly.
