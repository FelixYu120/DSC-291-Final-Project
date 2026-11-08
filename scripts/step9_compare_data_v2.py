"""Data v2: the scores written down before anyone looked (docs/DATA_V2_PLAN.md, section 6).

    python scripts/step9_compare_data_v2.py      # -> results/v2/data_v2_comparison.csv and .md

1. More photos per month: for each v1 cohort, A1 on v2 minus A1 on v1, on the same fields (the v1 model
   rows), the same frozen s1_cc2km folds, folds 1-4 scored. Fields that reach 4 clear months only in v2
   are counted apart and never enter this test. A win: the rank-inside-clusters interval lies above 0
   and the RMSE interval does not lie entirely above 0.
2. Malawi 2022 alone (R0, R1, A1 on folds 1-4) is in results/v2/baseline_table.md (step 8 --version 2).
3. temporal_rank Malawi 2022 <-> 2023: A1 trained on one season ranks the fields of the other. Spearman
   only, because the crop cuts differ. R1 (coordinates) is shown, so place can be told apart from the sensor.
   Test fields in fold 0 of their own s1_cc2km split are not scored (kept back).
It reads both databases (each checked against configs/team_database_v{1,2}.json) and writes only results/v2/.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step8_run_baseline import (ALPHAS, COHORTS, COHORTS_V2, FAMILY, K, MIN_CLUSTER_FIELDS, RESULTS, ROOT, SEED,
                                check_database, check_frozen, cohort_rows, git_commit, out_of_fold)
from cropyield.baselines import coordinates_knn, ridge_cv
from cropyield.data.labels import sha256
from cropyield.data.xy import load_xy
from cropyield.eval.scores import (BOOTSTRAP_DRAWS, centred, group_draws, in_large_clusters, paired_difference_ci,
                                   rank_inside_clusters, rmse, spearman)

V1, V2 = ROOT / "data", ROOT / "data" / "v2"
SKIP = ("0",)                               # fold 0 is kept back; its fields still train
TEMPORAL = "malawi_2022_2023__temporal_rank.csv"
TRANSFER_ROWS = {"0": (184, 204), "1": (253, 150)}   # repeat: (train, scored test) rows at the v2 freeze


def paired_scores(y: np.ndarray, old: np.ndarray, new: np.ndarray, fields: pd.DataFrame) -> list[dict]:
    """new minus old on the same fields: RMSE (below 0 is better) and rank inside clusters (above 0 is better)."""
    groups = fields["group_id"].to_numpy()
    cluster_years = (fields["group_id"] + "|" + fields["season_year"].astype(str)).to_numpy()
    keep = in_large_clusters(cluster_years, MIN_CLUSTER_FIELDS)
    y_in, old_in, new_in = (centred(values[keep], cluster_years[keep]) for values in (y, old, new))
    rank_low, rank_high = paired_difference_ci(y_in, new_in, old_in, groups[keep], spearman, seed=SEED)
    rmse_low, rmse_high = paired_difference_ci(y, new, old, groups, rmse, seed=SEED)
    win = rank_low > 0 and not rmse_low > 0
    return [{"metric": "rank_inside_clusters_v1", "value": rank_inside_clusters(y, old, cluster_years, MIN_CLUSTER_FIELDS)},
            {"metric": "rank_inside_clusters_v2", "value": rank_inside_clusters(y, new, cluster_years, MIN_CLUSTER_FIELDS)},
            {"metric": "rank_v2_minus_v1", "value": spearman(y_in, new_in) - spearman(y_in, old_in),
             "ci_low": rank_low, "ci_high": rank_high},
            {"metric": "rmse_v1", "value": rmse(y, old)}, {"metric": "rmse_v2", "value": rmse(y, new)},
            {"metric": "rmse_v2_minus_v1", "value": rmse(y, new) - rmse(y, old), "ci_low": rmse_low, "ci_high": rmse_high},
            {"metric": "v2_wins", "value": float(win)}]


def more_photos(cohort: str, labels1: pd.DataFrame, labels2: pd.DataFrame) -> list[dict]:
    """Test 1 for one cohort: the same fields, folds and models; only the season values differ."""
    X1, y1, fields = cohort_rows(cohort, V1, labels1, COHORTS[cohort])
    X2, y2, fields2 = cohort_rows(cohort, V2, labels2, COHORTS_V2[cohort], "labels_v2")
    if len(y1.index.difference(y2.index)):
        sys.exit(f"{cohort}: a v1 model row is not a v2 model row; stopping.")
    only_v2 = y2.index.difference(y1.index)             # reach 4 clear months in v2 only: never in the paired test
    X2, y2, fields2 = X2.loc[y1.index], y2.loc[y1.index], fields2.loc[y1.index]
    if not (y1.equals(y2) and fields["fold"].equals(fields2["fold"]) and fields["group_id"].equals(fields2["group_id"])):
        sys.exit(f"{cohort}: y or folds differ between v1 and v2 on the same fields; stopping.")
    old, new = out_of_fold(X1, y1, fields, SKIP)["A1"], out_of_fold(X2, y1, fields, SKIP)["A1"]
    tested = ~fields["fold"].isin(SKIP).to_numpy()
    changed = int((X1.to_numpy() != X2.to_numpy()).any(axis=1)[tested].sum())
    base = {"test": "more_photos", "cohort": cohort, "n_rows": int(tested.sum()),
            "n_clusters": fields["group_id"][tested].nunique(), "fields_changed": changed, "fields_only_v2": len(only_v2)}
    return [{**base, **row} for row in paired_scores(y1.to_numpy()[tested], old[tested], new[tested], fields[tested])]


def season_transfer(labels2: pd.DataFrame) -> list[dict]:
    """Test 3: train on one Malawi season, rank the fields of the other (repeat 0: 2022 -> 2023, repeat 1: back)."""
    split = pd.read_csv(V2 / "splits" / TEMPORAL, dtype=str, keep_default_na=False)
    X, y = (pd.concat(parts) for parts in zip(load_xy("malawi_2022", V2), load_xy("malawi_2023", V2)))
    if (y - labels2.loc[y.index, "yield_kg_ha"] / 1000).abs().max() > 1e-9:
        sys.exit("Malawi: y of the v2 database differs from labels_v2; stopping.")
    kept_back = set()                                   # fold 0 of each cohort's own s1_cc2km split is never scored
    for cohort in ("malawi_2022", "malawi_2023"):
        folds = pd.read_csv(V2 / "splits" / f"{cohort}__{FAMILY}.csv", dtype=str, keep_default_na=False)
        kept_back |= set(folds.loc[folds["fold"].isin(SKIP), "obs_id"])
    rows = []
    for repeat, table in split.groupby("repeat"):
        table = table.set_index("obs_id").loc[lambda t: t.index.isin(y.index)]   # model rows only (>= 4 clear months)
        train = table.index[table["fold"] == "train"]
        test = table.index[(table["fold"] == "test") & ~table.index.isin(kept_back)]
        if (len(train), len(test)) != TRANSFER_ROWS[repeat]:
            sys.exit(f"temporal_rank repeat {repeat}: {len(train)} train and {len(test)} test rows, "
                     f"expected {TRANSFER_ROWS[repeat]}; stopping.")
        groups = table.loc[test, "group_id"].to_numpy()
        a1 = ridge_cv(X.loc[train].to_numpy(), y.loc[train].to_numpy(), table.loc[train, "group_id"].to_numpy(),
                      X.loc[test].to_numpy(), ALPHAS)[0]
        r1 = coordinates_knn(labels2.loc[train, ["lat", "lon"]].to_numpy(), y.loc[train].to_numpy(),
                             labels2.loc[test, ["lat", "lon"]].to_numpy(), K)
        truth = y.loc[test].to_numpy()
        base = {"test": "season_transfer", "cohort": f"{table.loc[train, 'cohort'].iloc[0]} -> {table.loc[test, 'cohort'].iloc[0]}",
                "n_rows": len(test), "n_clusters": len(set(groups)), "n_train": len(train)}
        for arm, predicted in (("A1", a1), ("R1", r1)):
            draws = [spearman(truth[i], predicted[i]) for i in group_draws(groups, BOOTSTRAP_DRAWS, SEED)]
            low, high = np.nanquantile(draws, [0.025, 0.975])
            rows.append({**base, "metric": f"spearman_{arm}", "value": spearman(truth, predicted), "ci_low": low, "ci_high": high})
        low, high = paired_difference_ci(truth, a1, r1, groups, spearman, seed=SEED)
        rows.append({**base, "metric": "spearman_A1_minus_R1", "value": spearman(truth, a1) - spearman(truth, r1),
                     "ci_low": low, "ci_high": high})
    return rows


def table_text(scores: pd.DataFrame, run: dict) -> str:
    first = lambda rows, metric: rows[rows["metric"] == metric].iloc[0]  # noqa: E731
    span = lambda row: f"{row['value']:+.3f} ({row['ci_low']:+.3f} to {row['ci_high']:+.3f})"  # noqa: E731
    lines = ["# Data v2: the pre-registered scores", "",
             f"Split `{FAMILY}`, folds 1-4 scored (fold 0 trains only). Seed {run['seed']}. Commit `{run['commit']}`.", "",
             "## 1. More photos per month: A1 on v2 minus A1 on v1, same fields", "",
             "| Cohort | Fields | Changed | New in v2 (apart) | Rank v1 | Rank v2 | Rank v2 - v1 | RMSE v1 | RMSE v2 | RMSE v2 - v1 | v2 wins |",
             "|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|"]
    for cohort, rows in scores[scores["test"] == "more_photos"].groupby("cohort", sort=False):
        f = lambda metric: first(rows, metric)  # noqa: E731
        worse = f("rank_v2_minus_v1")["ci_high"] < 0 or f("rmse_v2_minus_v1")["ci_low"] > 0
        lines.append(f"| {cohort} | {int(rows['n_rows'].iloc[0]):,} | {int(rows['fields_changed'].iloc[0]):,} | "
                     f"{int(rows['fields_only_v2'].iloc[0])} | {f('rank_inside_clusters_v1')['value']:.3f} | "
                     f"{f('rank_inside_clusters_v2')['value']:.3f} | {span(f('rank_v2_minus_v1'))} | {f('rmse_v1')['value']:.3f} | "
                     f"{f('rmse_v2')['value']:.3f} | {span(f('rmse_v2_minus_v1'))} | "
                     f"{'yes' if f('v2_wins')['value'] else 'no, worse' if worse else 'no'} |")
    lines += ["", "A win: the rank interval lies above 0 and the RMSE interval does not lie entirely above 0.",
              "\"no, worse\": an interval excludes 0 on the worse side. \"Changed\": scored fields whose season values differ in v2.", "",
              "## 3. Malawi season transfer (Spearman only: the crop cuts differ)", "",
              "| Train -> test | Train fields | Test fields | Clusters | A1 | R1 (coordinates) | A1 - R1 |", "|---|---:|---:|---:|---|---|---|"]
    for cohort, rows in scores[scores["test"] == "season_transfer"].groupby("cohort", sort=False):
        f = lambda metric: first(rows, metric)  # noqa: E731
        lines.append(f"| {cohort} | {int(rows['n_train'].iloc[0])} | {int(rows['n_rows'].iloc[0])} | {int(rows['n_clusters'].iloc[0])} | "
                     f"{span(f('spearman_A1'))} | {span(f('spearman_R1'))} | {span(f('spearman_A1_minus_R1'))} |")
    lines += ["",
              "- Test fields in fold 0 of their own `s1_cc2km` split are not scored. Every field of the training season trains.",
              "- This is a new season, not a new place: the 2 km groups span both seasons, and about 13 % of the 2023 test "
              "fields lie within 2 km of a 2022 training field. R1 shows what place alone gives.",
              "- The season means cover different months: October and November are clear for every Malawi 2022 field and "
              "for no Malawi 2023 field (a catalogue gap of the newer collection). In the audit of 7 Nov, A1 on the five "
              "season maxima alone ranked the test season as well or better.",
              "", "Malawi 2022 alone (R0, R1, A1, folds 1-4): `results/v2/baseline_table.md`."]
    return "\n".join(lines) + "\n"


def main() -> int:
    check_database(V1, ROOT / "configs" / "team_database_v1.json")
    check_database(V2, ROOT / "configs" / "team_database_v2.json")
    check_frozen(V1, "labels_v1.parquet", COHORTS)
    check_frozen(V2, "labels_v2.parquet", COHORTS_V2)
    manifest = json.loads((V2 / "splits" / "manifest.json").read_text(encoding="utf-8"))
    if sha256(V2 / "splits" / TEMPORAL) != manifest["files"][TEMPORAL]["sha256"]:
        sys.exit(f"{TEMPORAL} differs from data/v2/splits/manifest.json; stopping.")
    columns = ["obs_id", "yield_kg_ha", "lat", "lon"]
    labels1 = pd.read_parquet(V1 / "processed" / "labels_v1.parquet", columns=columns).set_index("obs_id")
    labels2 = pd.read_parquet(V2 / "processed" / "labels_v2.parquet", columns=columns).set_index("obs_id")
    run = {"commit": git_commit(), "seed": SEED, "labels_v1_sha256": sha256(V1 / "processed" / "labels_v1.parquet"),
           "labels_v2_sha256": sha256(V2 / "processed" / "labels_v2.parquet")}
    rows = []
    for cohort in COHORTS:
        rows += more_photos(cohort, labels1, labels2)
        print(f"{cohort}: paired test done", flush=True)
    rows += season_transfer(labels2)
    columns = ["test", "cohort", "metric", "value", "ci_low", "ci_high", "n_rows", "n_clusters", "fields_changed",
               "fields_only_v2", "n_train", "commit", "seed", "labels_v1_sha256", "labels_v2_sha256"]
    scores = pd.DataFrame([{**row, **run} for row in rows]).reindex(columns=columns).round({"value": 6, "ci_low": 6, "ci_high": 6})
    out = RESULTS / "v2"
    out.mkdir(parents=True, exist_ok=True)
    scores.to_csv(out / "data_v2_comparison.csv", index=False, lineterminator="\n")
    text = table_text(scores, run)
    (out / "data_v2_comparison.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
