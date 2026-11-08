"""Traceable Presto sanity fits and regularization on retrospective monthly data."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "presto_finetune"))
import presto_lib as lib  # noqa: E402

STAGES = {
    "one": (1, 0.0, 0.0), "two": (2, 0.0, 0.0),
    "none": (128, 0.0, 0.0),
    "light": (128, 0.001, 0.05), "medium": (128, 0.05, 0.20),
    "strong": (128, 0.2, 0.50),
}
COHORT = "zimbabwe_lacuna_2022_2023"


class YieldModel(nn.Module):
    """Batch-normalize the new 128-dimensional head; do not alter Presto's LayerNorm."""
    def __init__(self, encoder, dropout=0.0):
        super().__init__()
        self.encoder = encoder
        self.bn = nn.BatchNorm1d(encoder.embedding_size)
        self.dropout = nn.Dropout(dropout)
        self.linear = nn.Linear(encoder.embedding_size, 1)

    def forward(self, arrays, indices):
        indices = np.asarray(indices, dtype=int)
        # Presto requires equal token counts within each encoder call. Build the
        # logical batch from token-compatible blocks before applying batch norm.
        chunks, positions = [], []
        for block in arrays.batches(indices, len(indices)):
            chunks.append(self.encoder(**arrays.batch(block), eval_task=True))
            positions.extend(block.tolist())
        lookup = {value: i for i, value in enumerate(positions)}
        encoded = torch.cat(chunks)[[lookup[int(i)] for i in indices]]
        if self.bn.training and len(indices) == 1:
            raise ValueError("training batch normalization needs at least two samples")
        return self.linear(self.dropout(self.bn(encoded))).squeeze(-1)


def logical_batches(index, batch_size, rng):
    """No singleton tail: combine it into the previous batch."""
    shuffled = rng.permutation(index)
    if len(shuffled) == 1:
        return [shuffled]
    blocks = [shuffled[i:i + batch_size] for i in range(0, len(shuffled), batch_size)]
    if len(blocks[-1]) == 1:
        tail = blocks.pop()
        blocks[-1] = np.concatenate([blocks[-1], tail])
    return blocks


def choose_rows(fields, n, sanity):
    folds = fields["fold"].astype(str).to_numpy()
    eligible = np.flatnonzero(np.isin(folds, ["2", "3", "4"]))
    validation = np.flatnonzero(folds == "1")[:64] if not sanity else np.array([], dtype=int)
    train = eligible[:n]
    if len(train) != n or (not sanity and not len(validation)):
        raise ValueError("not enough eligible training/validation rows")
    if set(fields.iloc[train].group_id) & set(fields.iloc[validation].group_id):
        raise ValueError("training and validation groups overlap")
    return train, validation


def target_normalization(y, train):
    """Fit the target transform only on training labels; reject a constant target."""
    target = np.asarray(y)[np.asarray(train, dtype=int)]
    mean, scale = float(target.mean()), float(target.std())
    if not np.isfinite(mean) or not np.isfinite(scale) or scale < 1e-8:
        raise ValueError("training target is non-finite or has zero variance")
    return mean, scale


def inverse_predictions(values, mean, scale):
    return np.asarray(values) * scale + mean


def metrics(model, arrays, y, indices, target_mean=0.0, target_scale=1.0):
    if not len(indices):
        return float("nan"), float("nan"), np.array([])
    model.eval()
    values = []
    with torch.no_grad():
        for i in range(0, len(indices), 32):
            values.extend(model(arrays, indices[i:i + 32]).cpu().numpy().tolist())
    values = inverse_predictions(values, target_mean, target_scale)
    target = y[indices]
    mse = float(np.mean((values - target) ** 2))
    denom = float(np.sum((target - target.mean()) ** 2))
    r2 = float(1 - np.sum((values - target) ** 2) / denom) if len(target) > 1 and denom > 0 else float("nan")
    return mse, r2, values


def fit_mode_mse(model, arrays, y, indices):
    """For sanity checks, measure batch-stat fit without changing BN running buffers."""
    if len(indices) < 2:
        return metrics(model, arrays, y, indices)[0]
    model.train()
    old_mean, old_var = model.bn.running_mean.clone(), model.bn.running_var.clone()
    old_count = model.bn.num_batches_tracked.clone()
    try:
        with torch.no_grad():
            pred = model(arrays, indices).cpu().numpy()
        return float(np.mean((pred - y[indices]) ** 2))
    finally:
        model.bn.running_mean.copy_(old_mean)
        model.bn.running_var.copy_(old_var)
        model.bn.num_batches_tracked.copy_(old_count)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory; never overwrites a prior run")
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261108)
    parser.add_argument("--tensorboard-deps", type=Path, help="Optional dependency directory to append to sys.path")
    args = parser.parse_args(argv)
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    if args.tensorboard_deps:
        sys.path.append(str(args.tensorboard_deps.resolve()))
    from torch.utils.tensorboard import SummaryWriter

    torch.set_num_threads(1)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    n, decay, dropout = STAGES[args.stage]
    sanity = n <= 2
    _, all_y, all_fields = lib.cohort_rows(COHORT)
    train_source, val_source = choose_rows(all_fields, n, sanity)
    chosen = np.concatenate([train_source, val_source])
    fields = all_fields.iloc[chosen].copy()
    y = all_y.iloc[chosen].to_numpy(dtype="float32")  # cohort_rows already returns t/ha
    arrays = lib.build_arrays(COHORT, fields)
    train = np.arange(n)
    val = np.arange(n, len(fields))
    # Keep tiny-set sanity checks on raw labels; fit the transform strictly on
    # train rows for all larger experiments, never the held-out validation.
    target_mean, target_scale = (0.0, 1.0) if sanity else target_normalization(y, train)
    if arrays.obs_ids != list(fields.index):
        raise RuntimeError("field order mismatch")
    model = YieldModel(lib.load_presto().encoder, dropout)
    opt = torch.optim.AdamW([
        {"params": model.encoder.parameters(), "lr": 3e-4 if sanity else 3e-5},
        {"params": list(model.bn.parameters()) + list(model.linear.parameters()), "lr": 3e-3 if sanity else 3e-4},
    ], weight_decay=decay)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    config = {"stage": args.stage, "seed": args.seed, "epochs": args.epochs,
              "weight_decay": decay, "dropout": dropout, "cohort": COHORT,
              "train_ids": fields.index[:n].tolist(), "validation_ids": fields.index[n:].tolist(),
              "train_folds": ["2", "3", "4"], "validation_fold": "1" if len(val) else None,
              "fold0_used": False, "target_units": "tonnes per hectare",
              "mse_units": "(tonnes per hectare)^2",
              "target_mean_train": target_mean, "target_scale_train": target_scale,
              "target_transform": "identity" if sanity else "training-only standardization",
              "setting": "retrospective full season; not a forecast",
              "singleton_bn": "fixed initial running stats, affine parameters trainable" if n == 1 else None,
              "database_sha256": lib.sha256(lib.DATABASE), "weights_sha256": lib.PRESTO_WEIGHTS_SHA256,
              "script_sha256": lib.sha256(Path(__file__)),
              "labels_sha256": lib.sha256(lib.DATA / "processed" / lib.LABELS_FILE),
              "split_sha256": lib.sha256(lib.DATA / "splits" / f"{COHORT}__s1_cc2km.csv"),
              "torch_version": str(torch.__version__),
              "threshold_mse": 0.01 if sanity else None}
    (out / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    writer = SummaryWriter(str(out / "tensorboard"))
    rng = np.random.default_rng(args.seed)
    loss_fn = nn.MSELoss()
    initial = copy.deepcopy(model.state_dict())
    initial_loss, _, _ = metrics(model, arrays, y, train, target_mean, target_scale)
    if sanity and initial_loss < 1e-8:
        raise RuntimeError("initial residual too small to prove that learning occurred")
    initial_val_mse, initial_val_r2, _ = metrics(model, arrays, y, val, target_mean, target_scale)
    history = [{"epoch": 0, "train_mse": initial_loss, "val_mse": initial_val_mse,
                "val_r2": initial_val_r2, "fit_mode_mse": fit_mode_mse(model, arrays, y, train) if sanity else float("nan"),
                "grad_norm": float("nan"), "encoder_grad_norm": float("nan"),
                "head_grad_norm": float("nan"), "lr": opt.param_groups[0]["lr"]}]
    for key, value in history[0].items():
        if key != "epoch" and np.isfinite(value):
            writer.add_scalar(key, value, 0)
    for epoch in range(1, args.epochs + 1):
        model.train()
        if n == 1:
            model.bn.eval()  # retain initial running mean=0, var=1; gradients remain enabled
        gradient, encoder_gradient, head_gradient = 0.0, 0.0, 0.0
        for batch in logical_batches(train, 16, rng):
            opt.zero_grad(set_to_none=True)
            normalized_y = (y[batch] - target_mean) / target_scale
            loss = loss_fn(model(arrays, batch), torch.from_numpy(normalized_y.astype("float32")))
            loss.backward()
            encoder_gradient = float(torch.sqrt(sum((p.grad.detach() ** 2).sum() for p in model.encoder.parameters() if p.grad is not None)))
            head_gradient = float(torch.sqrt(sum((p.grad.detach() ** 2).sum() for p in model.linear.parameters() if p.grad is not None)))
            gradient = float(torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0))
            opt.step()
        train_mse, _, train_pred = metrics(model, arrays, y, train, target_mean, target_scale)
        val_mse, val_r2, val_pred = metrics(model, arrays, y, val, target_mean, target_scale)
        fit_mse = fit_mode_mse(model, arrays, y, train) if sanity else float("nan")
        row = {"epoch": epoch, "train_mse": train_mse, "val_mse": val_mse, "val_r2": val_r2,
               "fit_mode_mse": fit_mse, "grad_norm": gradient, "encoder_grad_norm": encoder_gradient,
               "head_grad_norm": head_gradient, "lr": opt.param_groups[0]["lr"]}
        history.append(row)
        for key, value in row.items():
            if key != "epoch" and np.isfinite(value):
                writer.add_scalar(key, value, epoch)
        writer.add_scalar("sample_count/train", len(train), epoch)
        writer.add_scalar("sample_count/validation", len(val), epoch)
        if epoch == 1 or epoch % 25 == 0 or (sanity and train_mse <= 0.01):
            print(f"{args.stage} epoch={epoch} train_mse={train_mse:.6f} val_mse={val_mse:.6f}", flush=True)
        if sanity and train_mse <= 0.01:
            break
    writer.close()
    with (out / "history.csv").open("w", newline="", encoding="utf-8") as handle:
        csv_writer = csv.DictWriter(handle, fieldnames=list(history[0]))
        csv_writer.writeheader()
        csv_writer.writerows(history)
    _, _, train_pred = metrics(model, arrays, y, train, target_mean, target_scale)
    _, _, val_pred = metrics(model, arrays, y, val, target_mean, target_scale)
    with (out / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        csv_writer = csv.writer(handle)
        csv_writer.writerow(["split", "observed", "predicted", "obs_id"])
        for name, idx, pred in (("train", train, train_pred), ("validation", val, val_pred)):
            csv_writer.writerows((name, float(y[i]), float(p), str(fields.index[i])) for i, p in zip(idx, pred))
    torch.save(model.state_dict(), out / "checkpoint.pt")
    changed_encoder = any(not torch.equal(v, model.state_dict()[k]) for k, v in initial.items() if k.startswith("encoder."))
    changed_head = any(not torch.equal(v, model.state_dict()[k]) for k, v in initial.items() if k.startswith("linear."))
    summary = {"initial_train_mse": initial_loss, "final_train_mse": history[-1]["train_mse"],
               "final_val_mse": history[-1]["val_mse"] if len(val) else None,
               "epochs_run": len(history) - 1, "threshold_met": bool(history[-1]["train_mse"] <= 0.01) if sanity else None,
               "encoder_changed": changed_encoder, "head_changed": changed_head}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if not sanity or (summary["threshold_met"] and changed_encoder and changed_head) else 2


if __name__ == "__main__":
    raise SystemExit(main())
