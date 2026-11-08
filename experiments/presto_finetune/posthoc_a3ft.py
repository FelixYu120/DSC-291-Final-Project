"""Post-hoc arm P3: the A3-FT fine-tuning recipe of the 5 Nov team report (section 9.3). NOT part of PLAN.md:
written on 7 Nov 2026 after the first scores were seen, at the request of the session that started this work.

    python experiments/presto_finetune/posthoc_a3ft.py --cohort zimbabwe_lacuna_2022_2023 --workers 14

Recipe, as the report states it:
- Loss Huber (delta 1) on targets z-scored with the training rows' mean and SD.
- Stage 1: 10-epoch linear probe, encoder frozen, head lr 1e-3. Stage 2: unfreeze, at most 50 epochs, AdamW,
  lr encoder 1e-5 / head 1e-4, weight decay 1e-2 encoder / 1e-4 head, 3-epoch warm-up then cosine, grad clip 1.
- Three deterministic inner folds by group_id (GroupKFold(3)); the epoch count is the median best epoch; then a
  refit on all outer-training rows from the pretrained checkpoint, with a fresh head.
- Seeds 20261103, 20261104, 20261105; the arm is the mean of the three refits.
- Coordinates masked (set to 0) in training, validation and test.

Choices the report leaves open, fixed here before this arm was scored: batch 32 with same-kept-token batches; the
inner best epoch is the one with the lowest inner-validation MSE in t/ha, counted over stage 2 (0 = probe only);
the refit runs the same 50-epoch schedule and stops after the chosen epoch.

Writes runs/<cohort>/posthoc_a3ft.md, posthoc_a3ft.csv and posthoc_a3ft_choices.csv. Needs predictions.csv and
the X1 column of posthoc_controls.py (rerun here, cheap).
"""
from __future__ import annotations

import argparse
import copy
import math
import multiprocessing
import sys
import time

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupKFold

import posthoc_controls
import presto_lib as lib
import run_cohort

SEEDS = (20261103, 20261104, 20261105)
PROBE_EPOCHS, MAX_EPOCHS, WARMUP = 10, 50, 3
PROBE_LR, ENCODER_LR, HEAD_LR = 1e-3, 1e-5, 1e-4
ENCODER_WD, HEAD_WD = 1e-2, 1e-4
INNER_FOLDS = 3
_STATE: dict = {}


def init(payload: dict, y: np.ndarray) -> None:
    torch.set_num_threads(1)
    _STATE["arrays"], _STATE["y"] = lib.Arrays.from_numpy(payload), y


def schedule(epoch: int) -> float:
    """Stage-2 learning-rate factor for 1-based ``epoch``: linear warm-up, then cosine to 0 at MAX_EPOCHS."""
    if epoch <= WARMUP:
        return epoch / WARMUP
    return 0.5 * (1 + math.cos(math.pi * (epoch - WARMUP) / (MAX_EPOCHS - WARMUP)))


def fit(job: dict) -> dict:
    """Probe, then fine-tune. Inner job: record the validation MSE after each stage-2 epoch (0 = after the probe).
    Refit job: stop after ``epochs`` stage-2 epochs and predict the test fold."""
    arrays, y = _STATE["arrays"], _STATE["y"]
    train, val, test = job["train"], job.get("val"), job.get("test")
    mean, sd = float(y[train].mean()), float(y[train].std())
    target = torch.from_numpy(((y - mean) / sd).astype("float32"))
    model = lib.new_model("P1", job["seed"])  # pretrained checkpoint, fresh head (bias 0)
    rng = np.random.default_rng(job["seed"])
    huber = torch.nn.HuberLoss(delta=1.0)

    def one_epoch(optimiser):
        model.train()
        for block in arrays.batches(train, lib.BATCH_SIZE, rng):
            optimiser.zero_grad()
            loss = huber(model(**arrays.batch(block, no_location=True))[:, 0], target[block])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), lib.GRAD_CLIP)
            optimiser.step()

    def val_mse():
        return float(np.mean((lib.predict(model, arrays, val, True) * sd + mean - y[val]) ** 2))

    encoder = [p for name, p in model.named_parameters() if p.requires_grad and not name.startswith("head.")]
    head = list(model.head.parameters())
    for p in encoder:
        p.requires_grad_(False)
    probe = torch.optim.AdamW(head, lr=PROBE_LR, weight_decay=HEAD_WD)
    for _ in range(PROBE_EPOCHS):
        one_epoch(probe)
    for p in encoder:
        p.requires_grad_(True)
    optimiser = torch.optim.AdamW([{"params": encoder, "lr": ENCODER_LR, "weight_decay": ENCODER_WD},
                                   {"params": head, "lr": HEAD_LR, "weight_decay": HEAD_WD}])
    base = [group["lr"] for group in optimiser.param_groups]
    stop = MAX_EPOCHS if val is not None else job["epochs"]
    curve = [val_mse()] if val is not None else []
    for epoch in range(1, stop + 1):
        for group, lr in zip(optimiser.param_groups, base):
            group["lr"] = lr * schedule(epoch)
        one_epoch(optimiser)
        if val is not None:
            curve.append(val_mse())
    out = {key: job[key] for key in ("kind", "fold", "seed") if key in job} | {"inner": job.get("inner")}
    if val is not None:
        return out | {"curve": curve, "best_epoch": int(np.argmin(curve))}
    return out | {"epochs": job["epochs"], "test_pred": lib.predict(model, arrays, test, True) * sd + mean}


def run(pool, jobs):
    started, results = time.time(), []
    for k, result in enumerate(pool.imap_unordered(fit, jobs), 1):
        results.append(result)
    print(f"  {len(jobs)} jobs, {time.time() - started:.0f} s", flush=True)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cohort", default="zimbabwe_lacuna_2022_2023", choices=sorted(lib.WINDOWS))
    parser.add_argument("--workers", type=int, default=14)
    args = parser.parse_args(argv)
    out = lib.RUNS / args.cohort
    X, y_series, fields = lib.cohort_rows(args.cohort)
    y = y_series.to_numpy()
    arrays = lib.build_arrays(args.cohort, fields)
    groups, folds = fields["group_id"].to_numpy(), fields["fold"].to_numpy()
    outer = {fold: (np.flatnonzero(folds != fold), np.flatnonzero(folds == fold)) for fold in lib.SCORED_FOLDS}
    inner_jobs = []
    for fold, (train, test) in outer.items():
        for inner, (a, b) in enumerate(GroupKFold(n_splits=INNER_FOLDS).split(train, groups=groups[train])):
            if set(groups[train[a]]) & set(groups[train[b]]) or set(train[b]) & set(test):
                raise RuntimeError("inner split leaks")
            inner_jobs += [{"kind": "inner", "fold": fold, "inner": inner, "seed": seed, "train": train[a],
                            "val": train[b]} for seed in SEEDS]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(args.workers, init, (arrays.to_numpy(), y)) as pool:
        print(f"{args.cohort}: {len(inner_jobs)} inner jobs", flush=True)
        inner = run(pool, inner_jobs)
        chosen = {fold: int(np.median([r["best_epoch"] for r in inner if r["fold"] == fold]))
                  for fold in lib.SCORED_FOLDS}  # the test fold plays no part
        refit_jobs = [{"kind": "refit", "fold": fold, "seed": seed, "train": outer[fold][0], "test": outer[fold][1],
                       "epochs": chosen[fold]} for fold in lib.SCORED_FOLDS for seed in SEEDS]
        print(f"refit with epochs {chosen}", flush=True)
        refits = run(pool, refit_jobs)
    p3 = np.full(len(y), np.nan)
    for fold in lib.SCORED_FOLDS:
        p3[outer[fold][1]] = np.mean([r["test_pred"] for r in sorted(refits, key=lambda r: r["seed"])
                                      if r["fold"] == fold], axis=0)
    pd.DataFrame([{"fold": f, "epochs": chosen[f],
                   "inner_best_epochs": " ".join(str(r["best_epoch"]) for r in sorted(
                       [r for r in inner if r["fold"] == f], key=lambda r: (r["inner"], r["seed"])))}
                  for f in lib.SCORED_FOLDS]).to_csv(out / "posthoc_a3ft_choices.csv", index=False, lineterminator="\n")

    tested = fields["fold"].isin(lib.SCORED_FOLDS).to_numpy()
    saved = pd.read_csv(out / "predictions.csv", dtype={"fold": str, "group_id": str}).set_index("obs_id")
    rows = fields.index[tested]
    if not np.allclose(saved.loc[rows, "y_t_ha"].to_numpy(), y[tested]):
        raise RuntimeError("predictions.csv is not on the same fields")
    raw = posthoc_controls.raw_features(arrays)
    x1 = np.full(len(y), np.nan)
    for fold, (train, test) in outer.items():
        x1[test] = posthoc_controls.ridge_impute_cv(raw[train], y[train], groups[train], raw[test])
    scored = {arm: saved.loc[rows, arm].to_numpy() for arm in ("A1", "R1", "P0", "P0_noloc", "P1", "P1_noloc")}
    scored |= {"X1": x1[tested], "P3": p3[tested]}
    sub = fields[tested]
    arms = run_cohort.arm_scores(y[tested], scored, sub)
    cluster_years = run_cohort.cluster_years_of(sub)
    pairs = pd.DataFrame([{"a": "P3", "b": b} | run_cohort.pair(y[tested], scored["P3"], scored[b],
                                                                sub["group_id"].to_numpy(), cluster_years)
                          for b in ("A1", "R1", "P0_noloc", "P1_noloc", "P0", "X1")])
    pd.concat([arms.assign(kind="arm"), pairs.assign(kind="pair")]).to_csv(out / "posthoc_a3ft.csv", index=False,
                                                                           lineterminator="\n")
    lines = [f"# Post-hoc arm P3 (A3-FT recipe): {args.cohort}", "",
             "Not in PLAN.md. Written after the first scores were seen, so read it as exploration. "
             "Coordinates masked. Recipe: posthoc_a3ft.py docstring.", "",
             f"Chosen stage-2 epochs per test fold (median inner best epoch): {chosen}.", "",
             "| Arm | RMSE, t/ha | R2 | Rank inside clusters |", "|---|---:|---:|---:|"]
    lines += [f"| {r.arm} | {r.rmse:.3f} | {r.r2:.3f} | {r.rank_inside_clusters:.3f} |" for r in arms.itertuples()]
    lines += ["", "| Pair | RMSE, a minus b | Rank, a minus b |", "|---|---|---|"]
    lines += [f"| {r.a} minus {r.b} | {run_cohort.interval(r.rmse_diff, r.rmse_low, r.rmse_high)} | "
              f"{run_cohort.interval(r.rank_diff, r.rank_low, r.rank_high)} |" for r in pairs.itertuples()]
    text = "\n".join(lines) + "\n"
    (out / "posthoc_a3ft.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
