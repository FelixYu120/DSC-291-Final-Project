"""Watch Presto train, live, in TensorBoard: training and validation error per epoch on one inner split.

    $env:OPENBLAS_NUM_THREADS = "1"
    $tb = "C:\\Users\\flori\\.venvs\\presto-tb\\Scripts\\python.exe"   # the global Python 3.12 + tensorboard
    & $tb experiments\\presto_finetune\\watch_training.py --cohort zimbabwe_lacuna_2022_2023 --fold 1 --inner 0
    & $tb -m tensorboard.main --logdir experiments\\presto_finetune\\tensorboard --port 6006

Diagnostics only, not a result. It uses one inner split (GroupKFold on group_id) inside the training folds of one
test fold. The test fold is never read, so this makes no score and does not change PLAN.md. The training step is
the same as presto_lib.train_one (same seed, batches, optimiser), but there is no early stopping: every run goes to
MAX_EPOCHS, so the whole U shape of the validation curve shows. ``early_stop/plan_stops_here`` marks the epoch at
which the PLAN rule (patience 6) stops; the saved model of the real run is the one at ``early_stop/best_epoch``.

Charts in TensorBoard (SCALARS tab):
    rmse            train (all inner training rows, after each epoch), val (inner validation rows), and
                    val_if_mean (predict the training mean: the "no skill" line). All in t/ha.
    loss/batch      MSE of each training batch, in standardised units (noisy: this is the "feel" of training).
    grad_norm       mean gradient norm per epoch, before clipping at 1.0.
Writes only under experiments/presto_finetune/tensorboard/ (a scratch folder; do not commit it).
"""
from __future__ import annotations

import argparse
import multiprocessing
import sys
from pathlib import Path

import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import presto_lib as lib  # noqa: E402

LOGDIR = lib.HERE / "tensorboard"


def watch(job: dict) -> dict:
    """One (arm, learning rate) run on the inner split, logged every epoch. Mirrors presto_lib.train_one."""
    torch.set_num_threads(1)
    arrays, y = lib._WORKER["arrays"], lib._WORKER["y"]
    train, val = job["train"], job["val"]
    no_location = job["arm"] == "P1_noloc"
    mean, sd = float(y[train].mean()), float(y[train].std())
    target = torch.from_numpy(((y - mean) / sd).astype("float32"))
    model = lib.new_model(job["arm"], job["seed"])
    head = list(model.head.parameters())
    body = [p for name, p in model.named_parameters() if p.requires_grad and not name.startswith("head.")]
    optimiser = torch.optim.AdamW([{"params": body, "lr": job["lr"]},
                                   {"params": head, "lr": job["lr"] * lib.HEAD_LR_FACTOR}],
                                  weight_decay=lib.WEIGHT_DECAY)
    rng = np.random.default_rng(job["seed"])
    writer = SummaryWriter(str(job["logdir"]), flush_secs=5)
    no_skill = float(np.sqrt(np.mean((mean - y[val]) ** 2)))

    def rmse_of(index):
        return float(np.sqrt(np.mean((lib.predict(model, arrays, index, no_location) * sd + mean - y[index]) ** 2)))

    writer.add_scalars("rmse", {"train": rmse_of(train), "val": rmse_of(val), "val_if_mean": no_skill}, 0)
    best, best_epoch, stopped, curve, step = np.inf, 0, None, [], 0
    for epoch in range(1, job["epochs"] + 1):
        model.train()
        norms = []
        for block in arrays.batches(train, lib.BATCH_SIZE, rng):
            optimiser.zero_grad()
            output = model(**arrays.batch(block, no_location))[:, 0]
            loss = torch.nn.functional.mse_loss(output, target[block])
            loss.backward()
            norms.append(float(torch.nn.utils.clip_grad_norm_(model.parameters(), lib.GRAD_CLIP)))
            optimiser.step()
            step += 1
            writer.add_scalar("loss/batch", loss.item(), step)
        val_rmse = rmse_of(val)
        curve.append(val_rmse ** 2)
        if val_rmse ** 2 < best:
            best, best_epoch = val_rmse ** 2, epoch
        elif stopped is None and epoch - best_epoch >= lib.PATIENCE:
            stopped = epoch
        writer.add_scalars("rmse", {"train": rmse_of(train), "val": val_rmse, "val_if_mean": no_skill}, epoch)
        writer.add_scalar("grad_norm", float(np.mean(norms)), epoch)
        writer.add_scalar("early_stop/best_epoch", best_epoch, epoch)
        writer.add_scalar("early_stop/plan_stops_here", 1.0 if stopped == epoch else 0.0, epoch)
    writer.close()
    return {"arm": job["arm"], "lr": job["lr"], "curve": curve, "best_epoch": best_epoch, "plan_stop": stopped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cohort", default="zimbabwe_lacuna_2022_2023", choices=sorted(lib.WINDOWS))
    parser.add_argument("--fold", default="1", choices=lib.SCORED_FOLDS, help="test fold to leave out (never read)")
    parser.add_argument("--inner", type=int, default=0, help="inner split 0-4")
    parser.add_argument("--arms", nargs="+", default=["P1", "P2"], choices=lib.NN_ARMS)
    parser.add_argument("--lrs", nargs="+", type=float, default=list(lib.LEARNING_RATES))
    parser.add_argument("--epochs", type=int, default=lib.MAX_EPOCHS)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    X, y, fields = lib.cohort_rows(args.cohort)
    arrays = lib.build_arrays(args.cohort, fields)
    groups, folds = fields["group_id"].to_numpy(), fields["fold"].to_numpy()
    outer_train = np.flatnonzero(folds != args.fold)
    inner_train, inner_val = lib.inner_splits(outer_train, groups)[args.inner]
    assert not set(inner_val) & set(np.flatnonzero(folds == args.fold))
    root = LOGDIR / f"{args.cohort}_fold{args.fold}_inner{args.inner}"
    jobs = [{"arm": arm, "lr": lr, "epochs": args.epochs, "train": inner_train, "val": inner_val,
             "seed": lib.job_seed(args.fold, list(lib.LEARNING_RATES).index(lr), args.inner)
             if lr in lib.LEARNING_RATES else lib.SEED, "logdir": root / f"{arm}_lr{lr:g}"}
            for arm in args.arms for lr in args.lrs]
    print(f"{len(jobs)} runs -> {root}", flush=True)
    with multiprocessing.get_context("spawn").Pool(min(args.workers, len(jobs)), lib.init_worker,
                                                   (arrays.to_numpy(), y.to_numpy())) as pool:
        for result in pool.imap_unordered(watch, jobs):
            print(f"  {result['arm']} lr {result['lr']:g}: best epoch {result['best_epoch']}, "
                  f"PLAN rule stops at {result['plan_stop']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
