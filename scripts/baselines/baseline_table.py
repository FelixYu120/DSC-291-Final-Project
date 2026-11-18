"""Rebuild the baseline table: Ridge on the season indices against the training mean and coordinates alone.

    python scripts/baselines/baseline_table.py               # v1: data/, all five folds -> results/
    python scripts/baselines/baseline_table.py --version 2   # v2: data/v2/, folds 1-4 only -> results/v2/

One model per cohort, on the frozen s1_cc2km folds. Each field gets one prediction from a model that
never saw its 2 km cluster. Writes baseline_scores.csv and baseline_table.md.
It needs the database (data/cropyield.duckdb or data/v2/cropyield.duckdb), and no network and no GPU.
Version 2 scores folds 1-4 only: fold 0 is kept back (owner ruling, 1 Nov 2026); its fields still train.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.baselines.models import coordinates_knn, ridge_cv, train_mean  # noqa: E402
from cropyield.data.labels import sha256  # noqa: E402
from cropyield.data.xy import load_xy  # noqa: E402
from cropyield.eval.scores import (bias, centred, in_large_clusters, mae, paired_difference_ci, r2,  # noqa: E402
                                   rank_inside_clusters, rmse, spearman)

COHORTS = {"malawi_2023": 251, "kenya_oaf_2019_2020": 3977, "zimbabwe_lacuna_2022_2023": 1880}  # with the expected rows
# v2: the rows with >= 4 clear months, counted when data v2 was frozen (configs/team_database_v2.json).
COHORTS_V2 = {"malawi_2023": 253, "kenya_oaf_2019_2020": 3977, "zimbabwe_lacuna_2022_2023": 1880, "malawi_2022": 529}
FAMILY = "s1_cc2km"
ARMS = ("R0", "R1", "A1")
K = 10                                # R1: neighbours
ALPHAS = np.logspace(-3, 5, 17)       # A1: the Ridge penalties to try
SEED = 20261029
MIN_CLUSTER_FIELDS = 3
RESULTS = ROOT / "results"
HOW_TO_READ = """## How to read this

- Each cohort stands alone. Yield definitions differ, so never compare t/ha or R2 across cohorts.
- A win needs a paired interval that excludes 0. The primary comparison is A1 minus R1 on RMSE, per cohort.
- MAE is the mean absolute error. Bias is the mean of prediction minus yield: above 0 means the arm predicts too high.
- A cluster is a chain of fields with gaps under 2 km. It is not a surveyed village. The widest Kenya cluster spans about 30 km.
- Kenya yield keeps spatial structure to about 50 km, so coordinates still know the neighbourhood in a new cluster.
- R1 is coordinates with 10 neighbours. It is one measure of place, not the best one.
- Rank inside clusters takes out the mean of each cluster and year, on clusters of at least 3 fields. This removes most of place, not all: in Kenya about a third of these fields sit in clusters that cross a district line. It does not show what a sensor can or cannot see.
- Each result is an end-of-season estimate. It is not a forecast. Clear months after the cut: Kenya 19 %, Malawi 20 %, Lacuna 33 %.
- These scores were first seen on 30 Oct 2026. This table is a rebuild, not a fresh test.
- Malawi: villages were chosen by NDVI strata, so the score describes this sample, not a district.
- Lacuna: the unit is provisional, and 36 % of its scenes are warped from the next UTM zone.
"""
HOW_TO_READ_V2 = """## How to read this

- Each cohort stands alone. Yield definitions differ, so never compare t/ha or R2 across cohorts. Malawi 2022 and Malawi 2023 come from different crop cuts: never pool them or compare their t/ha.
- A win needs a paired interval that excludes 0. The primary comparison is A1 minus R1 on RMSE, per cohort.
- MAE is the mean absolute error. Bias is the mean of prediction minus yield: above 0 means the arm predicts too high.
- A cluster is a chain of fields with gaps under 2 km, measured point to point. It is not a surveyed village.
- R1 is coordinates with 10 neighbours. It is one measure of place, not the best one.
- Rank inside clusters takes out the mean of each cluster and year, on clusters of at least 3 fields. This removes most of place, not all.
- Each result is an end-of-season estimate. It is not a forecast. Clear months after the cut: Kenya 19.5 %, Malawi 2023 19.0 %, Malawi 2022 20.6 %, Lacuna 32.2 %.
- First run on 7 Nov 2026. Malawi 2022 is a new test. The other rows differ from results/baseline_table.md by the folds scored and by the cloudy months that v2 filled; results/v2/data_v2_comparison.md compares v2 with v1 on the same fields.
- Malawi 2023: villages were chosen by NDVI strata, so the score describes this sample, not a district. Malawi 2022: AVG_YLD in t/ha is inferred (it equals the mean of its two 5 x 5 m cuts at 13 % moisture), not confirmed by the provider.
- Lacuna: the unit is provisional, and about 36 % of its v1 scenes are warped from the next UTM zone.
"""


def check_frozen(data: Path, labels_file: str = "labels_v1.parquet", cohorts: dict = COHORTS) -> None:
    """Stop if the labels or a split file used here differs from <data>/splits/manifest.json."""
    manifest = json.loads((data / "splits" / "manifest.json").read_text(encoding="utf-8"))
    if sha256(data / "processed" / labels_file) != manifest["labels_sha256"]:
        sys.exit(f"{labels_file} differs from {data / 'splits' / 'manifest.json'}; stopping.")
    for cohort in cohorts:
        name = f"{cohort}__{FAMILY}.csv"
        if sha256(data / "splits" / name) != manifest["files"][name]["sha256"]:
            sys.exit(f"{name} differs from {data / 'splits' / 'manifest.json'}; stopping.")


def check_database(data: Path, pin: Path) -> None:
    """Stop if <data>/cropyield.duckdb differs from its pin (configs/team_database_v1.json or _v2.json)."""
    expected = json.loads(pin.read_text(encoding="utf-8"))
    database = data / "cropyield.duckdb"
    if database.stat().st_size != expected["bytes"] or sha256(database) != expected["sha256"]:
        sys.exit(f"{database} differs from {pin.name}; get the team copy again. Stopping.")


def split_on_rows(split: pd.DataFrame, rows: pd.Index) -> pd.DataFrame:
    """The split rows of these fields, in their order. The join is on obs_id, never by position."""
    return split.set_index("obs_id").loc[rows]


def cohort_rows(cohort: str, data: Path, labels: pd.DataFrame, expected: int | None = None,
                labels_name: str = "labels_v1") -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """X, y and one table with fold, group, year, lat and lon, all on the same fields."""
    expected = COHORTS[cohort] if expected is None else expected
    X, y = load_xy(cohort, data)
    if len(y) != expected:
        sys.exit(f"{cohort}: {len(y)} rows, expected {expected}; stopping.")
    if (y - labels.loc[y.index, "yield_kg_ha"] / 1000).abs().max() > 1e-9:
        sys.exit(f"{cohort}: y of the database differs from {labels_name}; stopping.")
    split = pd.read_csv(data / "splits" / f"{cohort}__{FAMILY}.csv", dtype={"group_id": str, "fold": str}, keep_default_na=False)
    fields = split_on_rows(split, y.index)[["fold", "group_id", "season_year"]].join(labels[["lat", "lon"]])
    return X, y, fields


def out_of_fold(X: pd.DataFrame, y: pd.Series, fields: pd.DataFrame, skip: tuple = ()) -> dict[str, np.ndarray]:
    """One prediction per field and arm, each from a model that never saw the fold of that field.

    Folds in `skip` are never tested (their fields still train); their predictions stay NaN.
    """
    features, target, groups = X.to_numpy(), y.to_numpy(), fields["group_id"].to_numpy()
    latlon = fields[["lat", "lon"]].to_numpy()
    predicted = {arm: np.full(len(y), np.nan) for arm in ARMS}
    for fold in sorted(set(fields["fold"].unique()) - set(skip)):
        test = (fields["fold"] == fold).to_numpy()
        train = ~test
        predicted["R0"][test] = train_mean(target[train], int(test.sum()))
        predicted["R1"][test] = coordinates_knn(latlon[train], target[train], latlon[test], K)
        predicted["A1"][test] = ridge_cv(features[train], target[train], groups[train], features[test], ALPHAS)[0]
    return predicted


def cohort_scores(y: np.ndarray, predicted: dict[str, np.ndarray], fields: pd.DataFrame) -> list[dict]:
    """The scores of one cohort, as one row per number."""
    groups, years, a1 = fields["group_id"].to_numpy(), fields["season_year"].to_numpy(), predicted["A1"]
    cluster_years = (fields["group_id"] + "|" + fields["season_year"].astype(str)).to_numpy()
    scores = []
    for arm in ARMS:
        scores += [{"arm": arm, "metric": "rmse_t_ha", "value": rmse(y, predicted[arm])},
                   {"arm": arm, "metric": "mae_t_ha", "value": mae(y, predicted[arm])},
                   {"arm": arm, "metric": "bias_t_ha", "value": bias(y, predicted[arm])},
                   {"arm": arm, "metric": "r2", "value": r2(y, predicted[arm])},
                   {"arm": arm, "metric": "rank_inside_clusters",
                    "value": rank_inside_clusters(y, predicted[arm], cluster_years, MIN_CLUSTER_FIELDS)}]
    for other in ("R0", "R1"):  # A1 minus each rival on RMSE: below 0 means that A1 is better
        low, high = paired_difference_ci(y, a1, predicted[other], groups, rmse, seed=SEED)
        scores.append({"arm": "A1", "metric": f"rmse_minus_{other}", "value": rmse(y, a1) - rmse(y, predicted[other]),
                       "ci_low": low, "ci_high": high})
    keep = in_large_clusters(cluster_years, MIN_CLUSTER_FIELDS)  # A1 minus R1 on rank: above 0 means that A1 is better
    y_in, a1_in, r1_in = (centred(values[keep], cluster_years[keep]) for values in (y, a1, predicted["R1"]))
    low, high = paired_difference_ci(y_in, a1_in, r1_in, groups[keep], spearman, seed=SEED)
    scores.append({"arm": "A1", "metric": "rank_minus_R1", "value": spearman(y_in, a1_in) - spearman(y_in, r1_in),
                   "ci_low": low, "ci_high": high})
    for year in np.unique(years):
        scores.append({"arm": "A1", "metric": f"r2_in_{year}", "value": r2(y[years == year], a1[years == year])})
    return scores


def git_commit() -> str:
    """HEAD, with "-dirty" when tracked files differ from it."""
    run = subprocess.run(["git", "describe", "--always", "--dirty", "--abbrev=40"], cwd=ROOT, capture_output=True, text=True, check=False)
    return run.stdout.strip() or "unknown"


def with_interval(row: pd.Series) -> str:
    return f"{row['value']:+.3f} ({row['ci_low']:+.3f} to {row['ci_high']:+.3f})"


def winner(row: pd.Series) -> str:
    return "A1 wins" if row["ci_high"] < 0 else "R1 wins" if row["ci_low"] > 0 else "no clear winner"


def table_text(scores: pd.DataFrame, note: str = "", how_to_read: str = HOW_TO_READ, folds: str = "five folds") -> str:
    """The Markdown page: nine rows, one comparison row per cohort, and how to read them."""
    first = scores.iloc[0]
    lines = ["# Baseline result", "",
             "Ridge on the 10 season indices (A1) against the training mean (R0) and coordinates alone (R1). Each cohort has its own model.",
             f"Split `{FAMILY}`: {folds}, whole 2 km clusters held out. Seed {first['seed']}. Commit `{first['commit']}`.", "",
             *([note, ""] if note else []),
             "| Cohort | Fields | Clusters | Arm | RMSE, t/ha | MAE, t/ha | Bias, t/ha | R2 inside the cohort | Rank inside clusters |", "|---|---:|---:|---|---:|---:|---:|---:|---:|"]
    compare = ["| Cohort | A1 minus R0, RMSE | A1 minus R1, RMSE | A1 minus R1, rank | Against coordinates |", "|---|---|---|---|---|"]
    for cohort, rows in scores.groupby("cohort", sort=False):
        value = rows.set_index(["arm", "metric"])["value"]
        for arm in ARMS:
            rank = value[arm, "rank_inside_clusters"]
            lines.append(f"| {cohort} | {rows['n_rows'].iloc[0]:,} | {rows['n_clusters'].iloc[0]:,} | {arm} | {value[arm, 'rmse_t_ha']:.3f} | {value[arm, 'mae_t_ha']:.3f} | {value[arm, 'bias_t_ha']:+.3f} | {value[arm, 'r2']:.3f} | {'' if pd.isna(rank) else f'{rank:.3f}'} |")
        by_metric = rows[rows["arm"] == "A1"].set_index("metric")
        compare.append(f"| {cohort} | {with_interval(by_metric.loc['rmse_minus_R0'])} | {with_interval(by_metric.loc['rmse_minus_R1'])} | {with_interval(by_metric.loc['rank_minus_R1'])} | {winner(by_metric.loc['rmse_minus_R1'])} |")
    years = scores[scores["metric"].str.startswith("r2_in_") & (scores["cohort"] == "kenya_oaf_2019_2020")]
    in_years = ", ".join(f"{row.metric.removeprefix('r2_in_')}: {row.value:.3f}" for row in years.itertuples())
    return "\n".join(lines + ["", *compare, "", f"Kenya A1, R2 inside each year: {in_years}.", "", how_to_read])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    v2 = args.version == 2
    data = Path(os.environ.get("CROPYIELD_DATA_DIR") or (ROOT / "data" / "v2" if v2 else ROOT / "data"))
    labels_file, cohorts, skip, results = (("labels_v2.parquet", COHORTS_V2, ("0",), RESULTS / "v2") if v2
                                           else ("labels_v1.parquet", COHORTS, (), RESULTS))
    unfrozen = [cohort for cohort, expected in cohorts.items() if expected is None]
    if unfrozen:
        sys.exit(f"Row counts of {unfrozen} are not frozen yet: set COHORTS_V2 when data v2 is frozen; stopping.")
    if v2:
        check_database(data, ROOT / "configs" / "team_database_v2.json")
    check_frozen(data, labels_file, cohorts)
    labels = pd.read_parquet(data / "processed" / labels_file, columns=["obs_id", "yield_kg_ha", "lat", "lon"]).set_index("obs_id")
    run = {"family": FAMILY, "commit": git_commit(), "seed": SEED, "labels_sha256": sha256(data / "processed" / labels_file)}
    rows = []
    for cohort, expected in cohorts.items():
        X, y, fields = cohort_rows(cohort, data, labels, expected, labels_file.removesuffix(".parquet"))
        predicted = out_of_fold(X, y, fields, skip)
        tested = ~fields["fold"].isin(skip).to_numpy()          # v2: fold 0 trains but is never scored
        y, fields = y[tested], fields[tested]
        predicted = {arm: values[tested] for arm, values in predicted.items()}
        base = {"cohort": cohort, **run, "split_sha256": sha256(data / "splits" / f"{cohort}__{FAMILY}.csv"),
                "n_rows": len(y), "n_clusters": fields["group_id"].nunique()}
        rows += [{**base, **score} for score in cohort_scores(y.to_numpy(), predicted, fields)]
        print(f"{cohort}: {len(y):,} fields done", flush=True)
    columns = ["cohort", "family", "arm", "metric", "value", "ci_low", "ci_high", "n_rows", "n_clusters", "commit", "seed", "labels_sha256", "split_sha256"]
    scores = pd.DataFrame(rows).reindex(columns=columns).round({"value": 6, "ci_low": 6, "ci_high": 6})
    results.mkdir(parents=True, exist_ok=True)
    scores.to_csv(results / "baseline_scores.csv", index=False, lineterminator="\n")
    note = "Data v2: folds 1-4 only. Fold 0 is kept back for the end of the project; its fields still train." if v2 else ""
    text = (table_text(scores, note, HOW_TO_READ_V2, "five folds, folds 1-4 scored") if v2 else table_text(scores))
    (results / "baseline_table.md").write_text(text, encoding="utf-8", newline="\n")
    print(text.split("## How to read this")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
