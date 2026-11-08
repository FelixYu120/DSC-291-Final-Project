# Presto fine-tune

Does Presto, frozen or fine-tuned, beat Ridge on the season indices (A1)? The rules were fixed in `PLAN.md` before
the first score. This page gives the result.

## Result in short

- **Lacuna: Presto passes the win rule.** Frozen Presto + Ridge (P0) and fine-tuned Presto (P1) beat A1:
  R2 0.30 against 0.19, rank inside clusters +0.05 to +0.06 (interval just above 0), RMSE -0.13 t/ha.
- **But the gain is not Presto.** A post-hoc control (not in PLAN.md, run after the scores were seen): plain Ridge
  on the 99 raw monthly numbers (X1) is not clearly worse than any Presto arm in any cohort, and in Malawi 2022 it
  ranks clearly better. A Presto with random weights,
  frozen (X2), is as good as P0 in Lacuna. So the gain comes from the monthly detail that the 10 season indices
  throw away, not from pre-training.
- **Malawi 2022 and Malawi 2023: no win.** Malawi 2022: better RMSE than A1, but no better rank. Malawi 2023: P1
  ties A1, P0 is worse.
- **Fine-tuning adds nothing over the frozen embedding** (P1 minus P0 is about 0 in all three cohorts).
- **Pre-training matters only when the transformer is trained:** P2 (random start, trained the same way) is much
  worse than P1 everywhere.
- **Place:** with latitude and longitude set to 0, Lacuna RMSE does not change; rank drops by 0.01-0.02. In Malawi
  2022 the location token is worth 0.04-0.06 t/ha of RMSE.

My advice: do not build on Presto. Pre-register X1 (Ridge on the raw monthly bands) as a new arm and test it on
fold 0 or on a new split family. It was found post hoc, so these numbers do not count as its test.

## Lacuna (`zimbabwe_lacuna_2022_2023`), folds 1-4, 1,504 fields, 232 clusters

Intervals: paired cluster bootstrap, 95 %, 2,000 draws, seed 20261029. A negative RMSE difference and a positive
rank difference favour the first arm.

| Arm | RMSE, t/ha | R2 | Rank inside clusters | RMSE minus A1 | Rank minus A1 | RMSE minus R1 | Rank minus R1 | Wins vs A1 |
|---|---:|---:|---:|---|---|---|---|---|
| R0 | 1.992 | -0.008 |  |  |  |  |  |  |
| R1 | 1.854 | 0.127 | -0.054 |  |  |  |  |  |
| A1 | 1.785 | 0.191 | 0.299 |  |  |  |  |  |
| P0 | 1.657 | 0.302 | 0.358 | -0.128 (-0.200 to -0.057) | +0.059 (+0.014 to +0.105) | -0.197 (-0.318 to -0.075) | +0.412 (+0.319 to +0.496) | yes |
| P0, no lat/lon | 1.654 | 0.305 | 0.335 | -0.132 (-0.199 to -0.067) | +0.036 (-0.005 to +0.077) | -0.200 (-0.330 to -0.073) | +0.389 (+0.295 to +0.470) | no |
| P1 | 1.652 | 0.307 | 0.353 | -0.133 (-0.206 to -0.061) | +0.054 (+0.006 to +0.100) | -0.202 (-0.332 to -0.067) | +0.407 (+0.306 to +0.493) | yes |
| P1, no lat/lon | 1.652 | 0.307 | 0.339 | -0.133 (-0.202 to -0.067) | +0.041 (-0.004 to +0.083) | -0.202 (-0.324 to -0.077) | +0.393 (+0.299 to +0.473) | no |
| P2 | 1.756 | 0.217 | 0.314 | -0.029 (-0.074 to +0.014) | +0.015 (-0.035 to +0.063) | -0.098 (-0.237 to +0.048) | +0.368 (+0.280 to +0.441) | no |
| X1, post hoc | 1.626 | 0.328 | 0.350 | -0.159 (-0.244 to -0.084) | +0.051 (-0.004 to +0.108) |  |  |  |
| X2, post hoc | 1.665 | 0.296 | 0.341 | -0.120 (-0.186 to -0.053) | +0.042 (-0.008 to +0.093) |  |  |  |

| Pair | Question | RMSE, a minus b | Rank, a minus b |
|---|---|---|---|
| P1 minus P2 | what pre-training adds | -0.104 (-0.170 to -0.037) | +0.039 (-0.000 to +0.081) |
| P1 minus P1, no lat/lon | place, fine-tuned | -0.000 (-0.028 to +0.031) | +0.014 (-0.001 to +0.029) |
| P0 minus P0, no lat/lon | place, frozen | +0.004 (-0.024 to +0.034) | +0.023 (+0.007 to +0.040) |
| P1 minus P0 | fine-tuning vs frozen | -0.005 (-0.040 to +0.031) | -0.005 (-0.025 to +0.015) |
| P0 minus X1 | Presto vs raw bands (post hoc) | +0.031 (-0.016 to +0.078) | +0.008 (-0.029 to +0.043) |
| P0 minus X2 | pre-trained vs random, frozen (post hoc) | -0.008 (-0.055 to +0.041) | +0.017 (-0.014 to +0.047) |

The two wins are narrow: the rank intervals start at +0.014 and +0.006, and 5 Presto arms were tested. Without the
location token the rank intervals touch 0. P1 chose the lowest learning rate (3e-5) in all 4 folds; best epochs 3-34.

## Malawi, folds 1-4 (each cohort alone; never compare t/ha across cohorts)

| Cohort | Arm | RMSE, t/ha | R2 | Rank inside clusters | RMSE minus A1 | Rank minus A1 | RMSE minus R1 | Rank minus R1 | Wins vs A1 |
|---|---|---:|---:|---:|---|---|---|---|---|
| malawi_2022 (423 fields, 78 clusters) | R1 | 1.624 | 0.335 | -0.072 |  |  |  |  |  |
|  | A1 | 1.551 | 0.393 | 0.299 |  |  |  |  |  |
|  | P0 | 1.462 | 0.461 | 0.260 | -0.090 (-0.166 to -0.014) | -0.040 (-0.119 to +0.033) | -0.162 (-0.293 to -0.036) | +0.332 (+0.183 to +0.495) | no |
|  | P0, no lat/lon | 1.523 | 0.415 | 0.244 | -0.029 (-0.108 to +0.063) | -0.056 (-0.137 to +0.026) | -0.101 (-0.257 to +0.046) | +0.316 (+0.169 to +0.481) | no |
|  | P1 | 1.449 | 0.470 | 0.276 | -0.102 (-0.175 to -0.027) | -0.024 (-0.119 to +0.065) | -0.175 (-0.310 to -0.044) | +0.348 (+0.189 to +0.526) | no |
|  | P1, no lat/lon | 1.486 | 0.443 | 0.244 | -0.066 (-0.149 to +0.021) | -0.055 (-0.153 to +0.035) | -0.138 (-0.286 to +0.002) | +0.316 (+0.155 to +0.500) | no |
|  | P2 | 1.741 | 0.236 | 0.022 | +0.189 (+0.067 to +0.316) | -0.277 (-0.423 to -0.134) | +0.117 (-0.018 to +0.252) | +0.095 (-0.076 to +0.288) | no |
|  | X1, post hoc | 1.406 | 0.502 | 0.400 | -0.146 (-0.250 to -0.046) | +0.100 (-0.005 to +0.194) |  |  |  |
|  | X2, post hoc | 1.714 | 0.259 | 0.065 | +0.163 (+0.003 to +0.350) | -0.234 (-0.356 to -0.124) |  |  |  |
| malawi_2023 (204 fields, 44 clusters) | R1 | 1.634 | -0.142 | 0.048 |  |  |  |  |  |
|  | A1 | 1.406 | 0.154 | 0.425 |  |  |  |  |  |
|  | P0 | 1.459 | 0.090 | 0.299 | +0.052 (-0.038 to +0.130) | -0.126 (-0.226 to -0.010) | -0.175 (-0.385 to +0.017) | +0.251 (+0.039 to +0.478) | no |
|  | P0, no lat/lon | 1.458 | 0.090 | 0.321 | +0.052 (-0.031 to +0.125) | -0.103 (-0.204 to +0.007) | -0.176 (-0.382 to +0.016) | +0.274 (+0.069 to +0.489) | no |
|  | P1 | 1.405 | 0.156 | 0.390 | -0.001 (-0.092 to +0.080) | -0.034 (-0.150 to +0.103) | -0.229 (-0.431 to -0.049) | +0.342 (+0.142 to +0.555) | no |
|  | P1, no lat/lon | 1.420 | 0.137 | 0.379 | +0.014 (-0.073 to +0.089) | -0.045 (-0.163 to +0.088) | -0.214 (-0.405 to -0.046) | +0.332 (+0.131 to +0.541) | no |
|  | P2 | 1.546 | -0.022 | -0.175 | +0.140 (+0.037 to +0.251) | -0.600 (-0.797 to -0.390) | -0.088 (-0.282 to +0.082) | -0.223 (-0.390 to -0.018) | no |
|  | X1, post hoc | 1.460 | 0.088 | 0.389 | +0.054 (-0.068 to +0.171) | -0.036 (-0.183 to +0.133) |  |  |  |
|  | X2, post hoc | 1.561 | -0.042 | -0.026 | +0.155 (+0.047 to +0.265) | -0.451 (-0.632 to -0.249) |  |  |  |

R0 rows, the pair tables and the learning-rate choices are in `runs/<cohort>/table.md`. Malawi 2022, pre-training
(P1 minus P2): RMSE -0.292, rank +0.253; Malawi 2023: RMSE -0.141, rank +0.566. P1 minus P0 includes 0 on RMSE
in both. Malawi 2022, Presto minus X1 on rank: P0 -0.140, P1 -0.124 (both intervals below 0).

## What worked, what did not

Worked:
- The input path is exact: on v1 it gives back the stored v1 Presto embeddings (difference 0.0).
- More monthly detail helps: P0, P1 and X1 all cut RMSE against A1 in Lacuna and Malawi 2022.
- Pre-trained weights make the trained transformer usable on small cohorts (P1 much better than P2).

Did not work:
- Fine-tuning gave nothing over the frozen embedding.
- Presto did not beat plain Ridge on the same monthly bands (X1) in any cohort.
- Training the transformer from random weights (P2) was poor; in Malawi 2023 its rank is negative.

## Limits

- End-of-season estimates, not forecasts: 32 % of Lacuna clear months fall after the cut. A model that sees all
  monthly bands may use post-harvest months more than A1 does.
- X1 and X2 are post hoc. They explain the result but do not count as a pre-registered test.
- One split family (`s1_cc2km`), one seed per inner model, 5 inner models averaged. Several arms per cohort, so
  a single narrow win is weak evidence.
- Presto was pre-trained on Level-1C top-of-atmosphere data; ours is Level-2A (docs/DECISIONS.md, 2026-10-26).
  Sentinel-1, ERA5 and SRTM are masked, so Presto sees only part of what it was trained on.
- The first Lacuna run used the code before 4 small robustness edits (PLAN.md, clarifications). They do not
  change numbers in a run without a non-finite loss; both Malawi runs used the final code.

## What was done

- Inputs: the view `monthly` of `data/v2/cropyield.duckdb` (read-only), clear months only, over the fixed cohort
  window (Lacuna: 2022-10 to 2023-06, first month October). The parked `presto_inputs` builds the tensors, so the
  reflectance enters unchanged (no second -0.1 offset), and Sentinel-1, ERA5 and SRTM are zero and masked.
- Model: the parked `presto_single_file.py` and the pinned weights (upstream commit `11e207a6`, SHA-256 checked).
  Presto gets latitude and longitude as one extra token, so place can enter the model.
- Input check: on the v1 database, the same path gives back the stored v1 `presto_embeddings` exactly
  (largest difference 0.0 one by one, 1.4e-6 in batches; `check_inputs.py`).
- P0: frozen 128-number embedding + the step 8 Ridge. P1: encoder + linear head, fine-tuned end to end.
  P2: the same with random weights. `_noloc`: latitude and longitude set to 0 in training and test.
- P1 and P2: for each test fold, 5 inner models (GroupKFold on `group_id` inside the training folds), early
  stopping on the inner validation fold, learning rate from 3e-5 / 1e-4 / 3e-4 / 1e-3 by the mean inner MSE. The
  test prediction is the mean of the 5 inner models. Fold 0 trains and is never scored.
- R0, R1 and A1 come from the step 8 functions and equal `results/v2/baseline_scores.csv` (the run stops if not).

## Run it

The shared `.venv` has no torch. Use a Python with `torch>=2.5` and `einops>=0.8` and the repo's other packages.
On the owner's machine the global Python 3.12 has them (torch 2.14.1 CPU), so nothing was installed. A teammate
can make a separate venv, for example `python -m venv --system-site-packages .venv-presto`, then
`.venv-presto\Scripts\python -m pip install torch einops` (do not install into the shared `.venv`).

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
$py = "C:\Users\flori\AppData\Local\Programs\Python\Python312\python.exe"
& $py experiments\presto_finetune\check_inputs.py
& $py -m pytest experiments\presto_finetune\test_presto_finetune.py -q -p no:cacheprovider
& $py experiments\presto_finetune\run_cohort.py --cohort zimbabwe_lacuna_2022_2023 --workers 14
& $py experiments\presto_finetune\run_cohort.py --cohort malawi_2022 --workers 14
& $py experiments\presto_finetune\run_cohort.py --cohort malawi_2023 --workers 14
& $py experiments\presto_finetune\posthoc_controls.py --cohort zimbabwe_lacuna_2022_2023
```

CPU only. Lacuna took 30 min on 14 processes (240 small training runs), Malawi 2022 about 13 min, Malawi 2023
about 13 min on 5 processes. The 14 tests take about 30 s on an idle machine.

## Files

| File | What it holds |
|---|---|
| `PLAN.md` | The rules and the win rule, written before the first score. |
| `presto_lib.py` | Inputs, batching, training of one inner model. Loads the parked Presto files in place. |
| `run_cohort.py` | All arms of one cohort, the scores and the table. |
| `check_inputs.py` | The v1 embedding check. |
| `posthoc_controls.py` | X1 and X2, written after the scores were seen. |
| `test_presto_finetune.py` | Focused tests: masks, offset, token counts, inner splits, no use of test labels. |
| `runs/<cohort>/` | `table.md`, `scores.csv`, `predictions.csv` (folds 1-4 only), `choices.csv`, `inner_curves.csv`, `p0_embeddings.npz`, `run.json`, `posthoc_controls.md` and `.csv`; Malawi also `all_predictions.npz` (all rows; fold 0 is NaN for every arm). |
