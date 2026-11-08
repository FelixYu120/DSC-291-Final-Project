# Presto: overfit checks and regularization

This experiment fine-tunes Presto on the v2 monthly Sentinel-2 series and records each run to TensorBoard. Start with [Presto_debug.ipynb](Presto_debug.ipynb) for an explanation, loss curves and predictions. `train.py` is the reproducible command-line entry point; [the tests](test_train.py) cover the training helpers.

**Scope:** inputs cover the full season, so results are retrospective yield estimates, not pre-harvest forecasts. Fold 0 is not used. One- and two-field runs are training diagnostics, not measures of generalization. They deliberately use no dropout or weight decay. The final sanity test must meet the configured MSE threshold in evaluation mode; reaching the epoch limit without doing so is a failed diagnostic, not a successful fit.

## What is being trained

The input adapter preserves monthly order and masks missing inputs. The pretrained Presto encoder is fine-tuned along with a new linear yield head. Presto keeps its own pretrained LayerNorm; `BatchNorm1d` is in the new head. The one-field stage keeps that BatchNorm in evaluation mode with its initial running mean and variance, because training-mode batch statistics need more than one observation. Its affine parameters and encoder remain trainable. From two observations onward the head uses training-mode batch statistics. Model evaluation uses the running statistics, so fit-mode and evaluation-mode errors can differ.

For three or more training fields, targets are standardized using only the training subset mean and standard deviation; the model predictions are converted back to tonnes per hectare (t/ha) before metrics and predictions are saved. One- and two-field diagnostics use unscaled yield, without fitting a target mean to a single example. MSE is in (t/ha)². The regularization stages use train folds 2–4 and grouped validation fold 1, with the same selection and seed for each setting. A model cannot use the held-out fold 0 in this experiment.

## Environment and run

Use Python with `torch`, `einops`, `duckdb`, `numpy`, `pandas`, `scikit-learn` and `tensorboard`; the notebook additionally uses `matplotlib` and IPython. Install the **complete TensorBoard distribution and its dependencies** in the chosen environment, for example `python -m pip install --upgrade tensorboard`. A partial environment can write TensorBoard events yet fail to start the viewer (for example, if `markdown` is missing). The owner has an existing environment at `C:\Users\flori\.venvs\presto-tb\Scripts\python.exe`, but its viewer dependencies must be checked or installed; choose an appropriate Python environment on another computer. Keep the v2 database at `data/v2/cropyield.duckdb` and the verified pretrained checkpoint in the location expected by the existing Presto adapter. The trainer checks frozen data and weights.

From the repository root, replace `python` below with the chosen interpreter if necessary. Each output directory **must not already exist**. To rerun, use a fresh parent directory. `--epochs` bounds the run; the tiny checks may stop earlier when the target is met.

```powershell
python experiments/presto_debug/train.py --stage one --output experiments/presto_debug/runs/example/one --epochs 500
python experiments/presto_debug/train.py --stage two --output experiments/presto_debug/runs/example/two --epochs 500
python experiments/presto_debug/train.py --stage none --output experiments/presto_debug/runs/example/none --epochs 50
python experiments/presto_debug/train.py --stage light --output experiments/presto_debug/runs/example/light --epochs 50
python experiments/presto_debug/train.py --stage medium --output experiments/presto_debug/runs/example/medium --epochs 50
python experiments/presto_debug/train.py --stage strong --output experiments/presto_debug/runs/example/strong --epochs 50
```

Check the one- and two-field diagnostics before proceeding to the regularized stages. If a tiny sanity check reaches its epoch limit without meeting the threshold, the program exits with a nonzero status and leaves its logs for inspection. The `none` stage uses the same 128 training fields and validation fields with zero dropout and zero weight decay. Increasing regularization is a controlled comparison between `none`, `light`, `medium` and `strong`, not between those stages and the one- or two-field sanity tests, which use different training samples.

**What the shipped runs show (`runs/latest`, checked 8 Nov).** The tiny stages memorize: one field 8.9128 -> 0.0036 in 13 epochs, two fields 12.1267 -> 0.0067 in 100 epochs, both first crossings of an oscillating curve (a linear head on a frozen embedding could also fit one or two points, so this shows that gradients reach the encoder, not that the encoder is needed). The four regularization stages ran **50 epochs**, not the 500 of the commands above, and they differ in practice only by head dropout (0, 0.05, 0.2, 0.5): weight decay shrinks the encoder by at most 0.24 % over 400 steps, and there is no freezing, augmentation or early stopping. All four overfit after epochs 6–14. Their best validation MSE is the same (2.49–2.53, RMSE about 1.58, R² about 0.22), and that best epoch was picked on the same 64 validation fields; at epoch 50, `none`, `light` and `medium` are worse than predicting the training mean (MSE 3.27). So dropout delays overfitting but does not lower the best error, and 64 fields cannot rank models. Do not set these numbers next to the development table (`experiments/presto_finetune/`), which trains on about 1,500 fields per fold.

The first exploratory regularization runs used 25 epochs and showed underfitting; they are kept outside the repository (`rerun_20261108/presto_final_runs` in the course folder). The revised protocol adds the zero-regularization baseline, standardizes targets using training-only statistics and extends the training budget. Treat those follow-up comparisons as exploratory, not preregistered confirmation.

## TensorBoard and files

```powershell
python -m tensorboard.main --logdir experiments/presto_debug/runs/example
```

First check `python -c "import tensorboard.main"` in the same environment; if it fails, install the complete TensorBoard dependencies as above. Then open the local URL printed by TensorBoard, usually `http://localhost:6006/`. TensorBoard finds the event files in each `<stage>/tensorboard` directory. Each stage also saves:

- `config.json`: stage, seed, split IDs, batch-normalization rule, data/weight hashes and hyperparameters.
- `history.csv`: evaluation-mode training MSE (`train_mse`), validation MSE and R², fit-mode MSE for the tiny checks, learning rate, and encoder/head gradient norms.
- `predictions.csv`: observed and predicted values by split and field ID.
- `summary.json`: initial/final loss, sanity threshold result and whether encoder/head parameters changed.
- `checkpoint.pt`: trained model weights (local only; checkpoints and TensorBoard events stay out of git).

`fit_mode_mse` uses batch-statistics behavior for tiny runs, without updating the stored running statistics; `train_mse` uses evaluation mode. For the singleton both use the fixed BatchNorm statistics. Validation MSE is only available for the larger regularization stages, and validation R² is undefined for a constant or one-observation target.

Open [the notebook](Presto_debug.ipynb): it displays the shipped `runs/latest` results automatically when present. Set `RUN_ROOT` to a different parent to inspect other stage directories, or explicitly turn on `RUN_TRAINING` to launch fresh stages in a new timestamped directory. The notebook does not train by default. Do not treat the best validation result as a final unbiased test or extrapolate these full-season results to a pre-harvest forecast.

## Focused checks

```powershell
python -m pytest -q experiments/presto_debug/test_train.py
```
