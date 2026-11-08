"""Run the Presto arms of PLAN.md on one cohort and score them against R0, R1 and A1 on folds 1-4.

    python experiments/presto_finetune/run_cohort.py --cohort zimbabwe_lacuna_2022_2023 --workers 14

Writes experiments/presto_finetune/runs/<cohort>/: predictions.csv, choices.csv, inner_curves.csv, scores.csv,
table.md, p0_embeddings.npz, run.json. Reads data/v2 read-only; writes nothing else. CPU only.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import platform
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import sklearn
import torch

import presto_lib as lib
from cropyield.eval.scores import (centred, in_large_clusters, paired_difference_ci, r2, rank_inside_clusters,
                                   rmse, spearman)

step8 = lib.step8
ARMS = ("R0", "R1", "A1", "P0", "P0_noloc", "P1", "P1_noloc", "P2")
PRESTO_ARMS = ("P0", "P0_noloc", "P1", "P1_noloc", "P2")
EXTRA_PAIRS = (("P1", "P2", "what pre-training adds"), ("P1", "P1_noloc", "place, fine-tuned"),
               ("P0", "P0_noloc", "place, frozen"), ("P1", "P0", "fine-tuning vs frozen"))
MIN_CLUSTER_FIELDS = step8.MIN_CLUSTER_FIELDS


def frozen_arms(arrays: lib.Arrays, y: np.ndarray, fields: pd.DataFrame, out) -> dict[str, np.ndarray]:
    """P0 and P0_noloc: frozen pretrained embeddings + the step 8 Ridge, fold by fold (fold 0 trains only)."""
    encoder = lib.load_presto().encoder
    everything = np.arange(len(y))
    embeddings = {"P0": lib.embed(encoder, arrays, everything),
                  "P0_noloc": lib.embed(encoder, arrays, everything, no_location=True)}
    np.savez_compressed(out / "p0_embeddings.npz", obs_id=np.array(arrays.obs_ids), **embeddings)
    groups, folds = fields["group_id"].to_numpy(), fields["fold"].to_numpy()
    predicted, alphas = {arm: np.full(len(y), np.nan) for arm in embeddings}, []
    for fold in lib.SCORED_FOLDS:
        test, train = folds == fold, folds != fold
        for arm, values in embeddings.items():
            predicted[arm][test], alpha = step8.ridge_cv(values[train], y[train], groups[train], values[test],
                                                         step8.ALPHAS)
            alphas.append({"arm": arm, "fold": fold, "alpha": alpha})
    return predicted, alphas


def network_arms(arrays: lib.Arrays, y: np.ndarray, fields: pd.DataFrame, workers: int, arms=lib.NN_ARMS):
    """P1, P1_noloc and P2: every (arm, test fold, learning rate, inner fold) job, then the inner choice."""
    groups, folds = fields["group_id"].to_numpy(), fields["fold"].to_numpy()
    jobs = []
    for fold in lib.SCORED_FOLDS:
        test, train = np.flatnonzero(folds == fold), np.flatnonzero(folds != fold)
        for inner, (inner_train, inner_val) in enumerate(lib.inner_splits(train, groups)):
            if set(groups[inner_train]) & set(groups[inner_val]) or set(inner_val) & set(test):
                raise RuntimeError("inner split leaks groups or test rows")
            for lr_index, lr in enumerate(lib.LEARNING_RATES):
                for arm in arms:
                    jobs.append({"arm": arm, "fold": fold, "lr": lr, "inner": inner,
                                 "seed": lib.job_seed(fold, lr_index, inner),
                                 "train": inner_train, "val": inner_val, "test": test})
    print(f"{len(jobs)} training jobs on {workers} processes", flush=True)
    results, started = [], time.time()
    with multiprocessing.get_context("spawn").Pool(workers, lib.init_worker, (arrays.to_numpy(), y)) as pool:
        for k, result in enumerate(pool.imap_unordered(lib.run_job, jobs), 1):
            results.append(result)
            if k % 20 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)} jobs, {time.time() - started:.0f} s", flush=True)
    curves = pd.DataFrame([{key: r[key] for key in ("arm", "fold", "lr", "inner")} | {"epoch": e + 1, "val_mse": v}
                           for r in results for e, v in enumerate(r["curve"])])
    runs = pd.DataFrame([{key: r[key] for key in ("arm", "fold", "lr", "inner", "best_val_mse", "best_epoch",
                                                  "epochs_run")} for r in results])
    predicted, choices = {arm: np.full(len(y), np.nan) for arm in arms}, []
    for (arm, fold), block in runs.groupby(["arm", "fold"]):
        by_lr = block.groupby("lr")["best_val_mse"].mean()
        chosen = float(by_lr.idxmin())  # the inner choice: the test fold plays no part
        test = np.flatnonzero(folds == fold)
        members = [r["test_pred"] for r in sorted(results, key=lambda r: r["inner"])
                   if (r["arm"], r["fold"], r["lr"]) == (arm, fold, chosen)]
        if len(members) != lib.INNER_FOLDS:
            raise RuntimeError(f"{arm} fold {fold}: {len(members)} inner models")
        predicted[arm][test] = np.mean(members, axis=0)
        picked = block[block["lr"] == chosen]
        choices.append({"arm": arm, "fold": fold, "chosen_lr": chosen, "inner_val_rmse": float(np.sqrt(by_lr.min())),
                        **{f"inner_val_rmse_lr_{lr:g}": float(np.sqrt(v)) for lr, v in by_lr.items()},
                        "best_epochs": " ".join(str(e) for e in picked.sort_values("inner")["best_epoch"])})
    return predicted, pd.DataFrame(choices), curves


def pair(y, a, b, groups, cluster_years) -> dict:
    """a minus b: RMSE and rank inside clusters, each with its paired cluster-bootstrap interval (as step 8)."""
    rmse_low, rmse_high = paired_difference_ci(y, a, b, groups, rmse, seed=lib.SEED)
    keep = in_large_clusters(cluster_years, MIN_CLUSTER_FIELDS)
    y_in, a_in, b_in = (centred(values[keep], cluster_years[keep]) for values in (y, a, b))
    rank_low, rank_high = paired_difference_ci(y_in, a_in, b_in, groups[keep], spearman, seed=lib.SEED)
    return {"rmse_diff": rmse(y, a) - rmse(y, b), "rmse_low": rmse_low, "rmse_high": rmse_high,
            "rank_diff": spearman(y_in, a_in) - spearman(y_in, b_in), "rank_low": rank_low, "rank_high": rank_high}


def cluster_years_of(fields: pd.DataFrame) -> np.ndarray:
    return (fields["group_id"] + "|" + fields["season_year"].astype(str)).to_numpy()


def arm_scores(y: np.ndarray, predicted: dict, fields: pd.DataFrame) -> pd.DataFrame:
    cluster_years = cluster_years_of(fields)
    return pd.DataFrame([{"arm": arm, "rmse": rmse(y, p), "r2": r2(y, p),
                          "rank_inside_clusters": rank_inside_clusters(y, p, cluster_years, MIN_CLUSTER_FIELDS)}
                         for arm, p in predicted.items()])


def score(y: np.ndarray, predicted: dict, fields: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    groups, cluster_years = fields["group_id"].to_numpy(), cluster_years_of(fields)
    arms = arm_scores(y, predicted, fields)
    pairs = [{"a": a, "b": b, "what": f"vs {b}"} | pair(y, predicted[a], predicted[b], groups, cluster_years)
             for a in PRESTO_ARMS if a in predicted for b in ("A1", "R1")]
    pairs += [{"a": a, "b": b, "what": what} | pair(y, predicted[a], predicted[b], groups, cluster_years)
              for a, b, what in EXTRA_PAIRS if a in predicted and b in predicted]
    pairs = pd.DataFrame(pairs)
    vs_a1 = pairs["b"] == "A1"
    pairs.loc[vs_a1, "wins_vs_A1"] = (pairs.loc[vs_a1, "rank_low"] > 0) & (pairs.loc[vs_a1, "rmse_low"] <= 0)
    return arms, pairs


def check_baselines(cohort: str, arms: pd.DataFrame) -> None:
    """R0, R1 and A1 must equal results/v2/baseline_scores.csv (read only)."""
    saved = pd.read_csv(lib.ROOT / "results" / "v2" / "baseline_scores.csv")
    saved = saved[saved["cohort"] == cohort].set_index(["arm", "metric"])["value"]
    mine = arms.set_index("arm")
    for arm in ("R0", "R1", "A1"):
        for column, metric in (("rmse", "rmse_t_ha"), ("r2", "r2"), ("rank_inside_clusters", "rank_inside_clusters")):
            a, b = mine.loc[arm, column], saved.get((arm, metric), np.nan)
            if not (np.isnan(a) and np.isnan(b)) and not abs(a - b) < 1e-5:
                sys.exit(f"{arm} {metric}: {a:.6f} here, {b:.6f} in results/v2/baseline_scores.csv; stopping.")


def interval(value: float, low: float, high: float) -> str:
    return f"{value:+.3f} ({low:+.3f} to {high:+.3f})"


def table_text(cohort: str, n: int, clusters: int, arms: pd.DataFrame, pairs: pd.DataFrame,
               choices: pd.DataFrame) -> str:
    by = pairs.set_index(["a", "b"])
    lines = [f"# Presto fine-tune: {cohort}", "",
             f"Folds 1-4 of `s1_cc2km` ({n:,} fields, {clusters} clusters). Fold 0 trains but is never scored. "
             f"Paired cluster-bootstrap 95 % intervals, 2,000 draws, seed {lib.SEED}. Rules: PLAN.md.", "",
             "| Arm | RMSE, t/ha | R2 | Rank inside clusters | RMSE minus A1 | Rank minus A1 | RMSE minus R1 | "
             "Rank minus R1 | Wins vs A1 |", "|---|---:|---:|---:|---|---|---|---|---|"]
    for row in arms.itertuples():
        rank = "" if np.isnan(row.rank_inside_clusters) else f"{row.rank_inside_clusters:.3f}"
        cells = [row.arm, f"{row.rmse:.3f}", f"{row.r2:.3f}", rank]
        if row.arm in PRESTO_ARMS:
            a1, r1 = by.loc[(row.arm, "A1")], by.loc[(row.arm, "R1")]
            cells += [interval(a1.rmse_diff, a1.rmse_low, a1.rmse_high),
                      interval(a1.rank_diff, a1.rank_low, a1.rank_high),
                      interval(r1.rmse_diff, r1.rmse_low, r1.rmse_high),
                      interval(r1.rank_diff, r1.rank_low, r1.rank_high), "yes" if a1.wins_vs_A1 else "no"]
        else:
            cells += [""] * 5
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "| Pair | Question | RMSE, a minus b | Rank, a minus b |", "|---|---|---|---|"]
    for row in pairs[~pairs["what"].str.startswith("vs ")].itertuples():
        lines.append(f"| {row.a} minus {row.b} | {row.what} | {interval(row.rmse_diff, row.rmse_low, row.rmse_high)} "
                     f"| {interval(row.rank_diff, row.rank_low, row.rank_high)} |")
    if len(choices):
        lines += ["", "Inner choices (the test fold plays no part):", "",
                  "| Arm | Fold | Learning rate | Inner RMSE | Best epochs of the 5 inner models |", "|---|---|---:|---:|---|"]
        for row in choices.sort_values(["arm", "fold"]).itertuples():
            lines.append(f"| {row.arm} | {row.fold} | {row.chosen_lr:g} | {row.inner_val_rmse:.3f} | {row.best_epochs} |")
    lines += ["", "Lower RMSE is better: a negative RMSE difference favours the Presto arm. A higher rank is better.",
              "Win vs A1 = rank interval above 0 and RMSE interval not entirely above 0 (PLAN.md)."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cohort", default="zimbabwe_lacuna_2022_2023", choices=sorted(lib.WINDOWS))
    parser.add_argument("--workers", type=int, default=14)
    args = parser.parse_args(argv)
    started = datetime.now(timezone.utc)
    out = lib.RUNS / args.cohort
    out.mkdir(parents=True, exist_ok=True)
    X, y_series, fields = lib.cohort_rows(args.cohort)
    y = y_series.to_numpy()
    arrays = lib.build_arrays(args.cohort, fields)
    if arrays.obs_ids != list(fields.index):
        raise RuntimeError("Presto inputs are not in the order of the fields")
    print(f"{args.cohort}: {len(y):,} fields, kept-token counts {sorted(set(arrays.kept.tolist()))}", flush=True)

    tested = fields["fold"].isin(lib.SCORED_FOLDS).to_numpy()  # fold 0 is never scored
    predicted = step8.out_of_fold(X, y_series, fields, skip=("0",))
    check_baselines(args.cohort, arm_scores(y[tested], {arm: predicted[arm][tested] for arm in step8.ARMS},
                                            fields[tested]))  # before training, so a mismatch costs nothing
    frozen, alphas = frozen_arms(arrays, y, fields, out)
    predicted |= frozen
    print("P0 done", flush=True)
    networks, choices, curves = network_arms(arrays, y, fields, args.workers)
    predicted |= networks
    np.savez_compressed(out / "all_predictions.npz", obs_id=np.array(arrays.obs_ids), fold=fields["fold"].to_numpy(),
                        **predicted)  # saved at once, so a later failure keeps the training

    scored = {arm: predicted[arm][tested] for arm in ARMS}
    if any(np.isnan(p).any() for p in scored.values()):
        raise RuntimeError("a scored field has no prediction")
    arms, pairs = score(y[tested], scored, fields[tested])

    predictions = fields[tested][["fold", "group_id", "season_year"]].assign(y_t_ha=y[tested], **scored)
    predictions.to_csv(out / "predictions.csv", index_label="obs_id", lineterminator="\n")
    choices.to_csv(out / "choices.csv", index=False, lineterminator="\n")
    curves.to_csv(out / "inner_curves.csv", index=False, lineterminator="\n")
    pd.concat([arms.assign(kind="arm"), pairs.assign(kind="pair")]).to_csv(out / "scores.csv", index=False,
                                                                           lineterminator="\n")
    text = table_text(args.cohort, int(tested.sum()), fields[tested]["group_id"].nunique(), arms, pairs, choices)
    (out / "table.md").write_text(text, encoding="utf-8", newline="\n")
    run = {"cohort": args.cohort, "started": started.isoformat(), "finished": datetime.now(timezone.utc).isoformat(),
           "window": lib.WINDOWS[args.cohort], "fields_total": len(y), "fields_scored": int(tested.sum()),
           "python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__,
           "pandas": pd.__version__, "sklearn": sklearn.__version__, "presto_commit": lib.PRESTO_COMMIT,
           "presto_weights_sha256": lib.PRESTO_WEIGHTS_SHA256, "parked_sha256": lib.check_parked(),
           "database_pin": json.loads(lib.DATABASE_PIN.read_text(encoding="utf-8")).get("sha256"),
           "split_sha256": lib.sha256(lib.DATA / "splits" / f"{args.cohort}__{step8.FAMILY}.csv"),
           "settings": {k: getattr(lib, k) for k in ("LEARNING_RATES", "HEAD_LR_FACTOR", "WEIGHT_DECAY", "BATCH_SIZE",
                                                     "GRAD_CLIP", "MAX_EPOCHS", "PATIENCE", "INNER_FOLDS", "SEED")},
           "p0_ridge_alphas": alphas, "workers": args.workers}
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
