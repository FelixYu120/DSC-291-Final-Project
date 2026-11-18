# Presto fine-tune: plan and win rule

Written on 7 Nov 2026, before any Presto score was computed. The rules below do not change after the first score.
If a rule must change, the change gets a dated line at the end of this file, and the README says so.

## Question

Does Presto (Tseng et al. 2023, arXiv 2304.14065), frozen or fine-tuned, rank fields inside a village better than
Ridge on the 10 season indices (A1), without a clearly worse RMSE? And how much does pre-training add, and how much
of the score is place (latitude and longitude)?

Expectation: a modest gain at best. On CY-Bench, frozen Presto + RF did worse than RF (Nedungadi et al. 2025).

## Data

- First cohort: `zimbabwe_lacuna_2022_2023`. Then, if time is left, `malawi_2022` and `malawi_2023`, with the same rules.
- Rows: the rows of `load_xy(cohort, data/v2)` (`include_primary`, at least 4 clear months). Lacuna: 1,880.
- Checks before any model: the v2 database matches `configs/team_database_v2.json`, and the labels and the split
  file match `data/v2/splits/manifest.json` (the functions of `scripts/step8_run_baseline.py`).
- Folds: `data/v2/splits/<cohort>__s1_cc2km.csv`, joined on `obs_id` only.
- Every DuckDB file opens with `read_only=True`. All new files go under `experiments/presto_finetune/`.

## Inputs

- The view `monthly` of `data/v2/cropyield.duckdb`: 10 Sentinel-2 bands per field and month.
- Only `clear` months carry values. `cloudy` and `no_scene` months are masked (Presto drops their tokens).
- Window: the fixed cohort window, the same for every field and the same as A1 uses. Lacuna and Malawi 2023:
  2022-10 to 2023-06. Malawi 2022: 2021-10 to 2022-06. Nine months, first month October (Presto `month` = 9).
  No shorter window is run. No field is cut at its own survey date.
- Presto tensors come from the parked code `_parked/src/cropyield/features/presto_inputs.py`, loaded from the parked
  file (its SHA-256 must match `_parked/MANIFEST.csv`). Reflectance enters unchanged: no second -0.1 offset.
  Sentinel-1, ERA5 and SRTM are zero and masked. Dynamic World is 9 (unknown).
- Latitude and longitude: `lat`, `lon` of `labels_v2`, the same as R1.
- Model code and weights: the parked `presto_single_file.py` (upstream commit `11e207a6`) and
  `data/models/presto/default_model.pt` (SHA-256 checked by the parked `presto_weights.py`).
- Input check: the same code on the v1 database must give back the v1 `presto_embeddings` for v1 Lacuna fields
  (largest absolute difference below 1e-4). If it does not, stop and find out why.

## Arms

| Arm | What it is |
|---|---|
| R0 | Training mean (step 8). |
| R1 | Coordinates only, 10 nearest neighbours (step 8). |
| A1 | Ridge on the 10 season indices (step 8). |
| P0 | Frozen pretrained Presto embedding (128 numbers, `eval_task=True`) + the step 8 Ridge (`ridge_cv`). |
| P0-noloc | P0 with latitude and longitude set to 0 for every field. |
| P1 | Pretrained Presto encoder + linear head (upstream `construct_finetuning_model`), fine-tuned end to end. |
| P1-noloc | P1 with latitude and longitude set to 0 for every field, in training and test. |
| P2 | P1 with random weights (no pre-training), trained the same way. |

## Training rules for P1, P1-noloc and P2

- Outer loop: test folds 1, 2, 3, 4. Fold 0 is never a test fold and is never scored; its fields train.
- The training set of a test fold is every other field (fold 0 included).
- Inner split: GroupKFold(5) on `group_id` inside the training set. The test fold is never used for any choice.
- Target: yield in t/ha, standardised with the mean and SD of the inner training rows.
- Loss MSE. AdamW, weight decay 0.01. Batch 32. Gradient clip 1.0. Head learning rate = 10 x encoder learning rate.
  Upstream frozen parts stay frozen (positional and month tables).
- Batches hold fields with the same number of kept tokens (Presto needs this); batch order is shuffled each epoch.
- Encoder learning rate grid: 3e-5, 1e-4, 3e-4, 1e-3. The same grid for all three arms.
- Each inner model trains at most 40 epochs and stops after 6 epochs without a better inner-validation MSE. It keeps
  the weights of its best epoch.
- Learning rate choice: the lowest mean inner-validation MSE over the 5 inner models.
- Test prediction: the mean of the 5 inner models of the chosen learning rate.
- Seeds: fixed per arm, test fold and inner fold, from base seed 20261029. CPU only, 1 torch thread per process.

P0 and P0-noloc use the step 8 `ridge_cv`: clip at the 1st and 99th training percentile, standardise, choose alpha
from `np.logspace(-3, 5, 17)` by GroupKFold on `group_id` inside the training folds.

## Scores

All on the pooled out-of-fold predictions of folds 1-4, with `src/cropyield/eval/scores.py`:

- RMSE (t/ha), R2 inside the cohort, rank inside clusters (Spearman after the cluster mean is taken out; clusters of
  at least 3 fields; cluster = `group_id` + season year, as in step 8).
- Paired cluster-bootstrap 95 % intervals (2,000 draws, seed 20261029, resample `group_id`) of each Presto arm minus
  A1 and minus R1, on RMSE and on rank inside clusters. Rank intervals use the centred values of the large clusters,
  as in step 8.
- Also reported, with the same intervals: P1 minus P2 (what pre-training adds) and P1 minus P1-noloc (place).
- R0, R1 and A1 are recomputed with the step 8 functions. They must equal `results/v2/baseline_table.md`
  (A1 R2 0.191, rank 0.299; R1 R2 0.127), else stop.

## Win rule

An arm wins against A1 when both hold:

1. The paired interval of rank inside clusters (arm minus A1) is above 0 (lower end > 0).
2. The paired RMSE interval (arm minus A1) is not entirely worse (lower end <= 0).

P1 is the primary test. P0 and P2 get the same rule, but they are secondary. With several arms, a single narrow win
is weak evidence; the README says so. Against R1 the same two numbers are reported, with no extra rule.

A null result is a valid result. It is reported as it is.

## Outputs

- `experiments/presto_finetune/runs/<cohort>/`: `predictions.csv` (one row per scored field and arm),
  `choices.csv` (learning rate and best epochs per arm and fold), `inner_curves.csv`, `scores.csv`, `table.md`,
  `p0_embeddings.npz`, `run.json` (versions, hashes, times).
- `experiments/presto_finetune/README.md`: the result table, what worked, what did not, and run commands.

## Changes after the first score

None.

Clarifications on 7 Nov 2026, while the first Lacuna run was training and before any Presto score was seen
(from an independent code review). They make the text match the code; no rule changes:

- Seeds: the seed depends on the test fold, the learning rate and the inner fold, and is the same for every arm.
  So P1, P1-noloc and P2 see the same batch order and the same head start weights (paired arms).
- `predictions.csv` holds one row per scored field and one column per arm.
- The input check is a separate script (`check_inputs.py`), run by hand before the scores. It printed OK.
- Robustness only: R0/R1/A1 are checked before training, the raw predictions are saved right after training,
  and an inner model whose validation MSE is never finite falls back to its start weights. The 5 inner models
  are averaged in inner-fold order. The first Lacuna run used the code before these edits; for a run without a
  non-finite loss the numbers are the same.

## Notes received after all scores (7 Nov 2026, from the session that started this work)

The rules above stay as they are. These notes change how to read the result, and add one post-hoc arm.

- **A team recipe existed.** The 5 Nov team report (section 9.3, "A3-FT") already set a fine-tuning recipe. This
  plan was written without it. Differences: one stage here, probe-then-unfreeze there; MSE here, Huber (delta 1)
  there; learning-rate grid 3e-5 to 1e-3 (head x10) here, fixed 1e-5 / 1e-4 there; 5 inner folds with early
  stopping and a 5-model mean here, 3 inner folds with the median best epoch, a refit and 3 seeds there; P1 keeps
  coordinates here (P1-noloc masks them), A3-FT masks them always. P1 is not changed after the fact. A3-FT runs as
  a post-hoc arm P3 (`posthoc_a3ft.py`, its open choices written in its docstring before it was scored). Reason
  to look: P1 chose the lowest learning rate of the grid (3e-5) in all 4 Lacuna folds.
- **Input shift.** Presto was pre-trained on Sentinel-2 Level-1C; our chips are Level-2A. Fine-tuning can adapt
  to that; the frozen embedding (P0) cannot.
- **Coordinates.** The team rule masks coordinates in every region and transfer test. Under that rule the
  `noloc` arms (and P3) are the arms to read. This split holds out 2 km clusters inside one cohort, not regions,
  so both are reported.
- **Fold 4 was seen before.** On 3 Nov an exploratory run on Lacuna fold 4 found frozen Presto beside the indices
  lifted rank inside clusters from 0.30 to 0.36; no result there survived the 21-test correction. Fold 4 is one of
  the 4 folds scored here, so the Lacuna Presto result is not a fully fresh test of that hypothesis.
- **Environment.** No package was installed. The shared `.venv` has no torch; the runs used the global Python
  3.12, which already had torch 2.14.1 (CPU) and the same versions of the other packages.
- **8 Nov 2026, repository clean-up.** `scripts/step8_run_baseline.py` is now `scripts/baselines/baseline_table.py` (same code, one `ROOT` line changed). `presto_lib.py` imports it from there under the same name `step8`.
  The rules above are unchanged.
