"""Field footprint: does a bigger window around the point add signal? Data v2, Zimbabwe point cohorts, folds 1-4.

    python experiments/footprint/windows.py      # first: window stats from the chips -> windows.parquet (label-free)
    python experiments/footprint/footprint.py    # -> results.csv, pairs.csv, checks.json, run.json, results.md

The rules are in PLAN.md, written before any score. Arms: R1 (coordinates), A1-w (season max and mean of 5 indices)
and X1-w (10 bands per month, gap-filled), at w = 1, 3, 5, 7 pixels, and with the within-window std (`+sd`) for w > 1.
The head is the step 8 Ridge. Fold-0 fields train and are never scored. Before any window arm is scored, the 1-pixel
arms and R1 must give back today's numbers; else the script stops.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
V2 = REPO / "data" / "v2"
spec = importlib.util.spec_from_file_location("step8", REPO / "scripts" / "baselines" / "baseline_table.py")
step8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(step8)                                  # also puts src/ on sys.path
sys.path.insert(0, str(HERE))
import windows as W

from cropyield.baselines.models import coordinates_knn, ridge_cv
from cropyield.data.labels import sha256
from cropyield.data.xy import FEATURES
from cropyield.eval.scores import (
    BOOTSTRAP_DRAWS,
    centred,
    group_draws,
    in_large_clusters,
    r2,
    rank_inside_clusters,
    rmse,
    spearman,
)
from cropyield.features.indices import INDICES

COHORTS = {"zimbabwe_lacuna_2022_2023": (1880, "main"),
           "zimbabwe_2024": (2458, "robustness (parked: positive rows only)")}
LABELS_FILE = "labels_v2.parquet"
SKIP, SCORED = ("0",), ("1", "2", "3", "4")
SEED = step8.SEED                    # 20261029
SIZES = W.SIZES
BANDS = list(W.BAND_COLUMNS)
MIN_CLUSTER_FIELDS = step8.MIN_CLUSTER_FIELDS
PLAN = HERE / "PLAN.md"
TOLERANCE = 1e-6


# ---------- features -------------------------------------------------------------------------------------------------

def with_k(frame: pd.DataFrame, season_start: pd.Series) -> pd.DataFrame:
    """Add k = month of the season (0 = the window's first month), as experiments/time_features does."""
    start = pd.DatetimeIndex(pd.to_datetime(season_start.loc[frame.obs_id].to_numpy()))
    month = pd.DatetimeIndex(pd.to_datetime(frame.month + "-01"))
    return frame.assign(k=(month.year * 12 + month.month) - (start.year * 12 + start.month))


def season(frame: pd.DataFrame, columns: list[str], prefix: str = "") -> pd.DataFrame:
    """Season max and mean of each column over the clear months (NaN months skipped, like the SQL view)."""
    g = frame.groupby("obs_id")
    out = {}
    for c in columns:
        out[f"{prefix}{c}_season_max"] = g[c].max()
        out[f"{prefix}{c}_season_mean"] = g[c].mean()
    return pd.DataFrame(out)


def curve(frame: pd.DataFrame, columns: list[str], index: pd.Index, ks: list[int]) -> pd.DataFrame:
    """One column per variable and month k: gaps filled linearly between clear months, edges with the nearest clear
    month, then the field's own mean (the M2 curve of experiments/time_features)."""
    parts = []
    for v in columns:
        cube = frame.pivot(index="obs_id", columns="k", values=v).reindex(index=index, columns=ks)
        own = cube.mean(axis=1)
        part = cube.interpolate(axis=1, limit_direction="both")
        parts.append(part.apply(lambda col, own=own: col.fillna(own)).add_prefix(f"{v}_m"))
    return pd.concat(parts, axis=1)


def arms_for(win: pd.DataFrame, index: pd.Index) -> dict[str, pd.DataFrame]:
    """Every A1 and X1 arm of one cohort, on `index` (the load_xy rows), from the window table."""
    clear = {w: win[win.w == w] for w in SIZES}
    # X1 keeps the months where all 5 indices are finite (the time_features rule); the month set must not move with w
    x_frames = {w: f[f[list(INDICES)].notna().all(axis=1)] for w, f in clear.items()}
    ks = sorted(x_frames[1].k.unique())
    for w, f in x_frames.items():
        if sorted(f.k.unique()) != ks or len(f) != len(x_frames[1]):
            raise ValueError(f"window {w}: the clear months differ from the 1-pixel months")
    arms: dict[str, pd.DataFrame] = {}
    for w in SIZES:
        a1 = season(clear[w], list(INDICES)).reindex(index)[FEATURES]
        x1 = curve(x_frames[w], BANDS, index, ks)
        arms[f"A1-{w}"], arms[f"X1-{w}"] = a1, x1
        if w > 1:
            arms[f"A1-{w}+sd"] = pd.concat([a1, season(clear[w], [f"sd_{i}" for i in INDICES]).reindex(index)], axis=1)
            arms[f"X1-{w}+sd"] = pd.concat([x1, curve(x_frames[w], [f"sd_{b}" for b in BANDS], index, ks)], axis=1)
    for name, X in arms.items():
        if not (X.index.equals(index) and np.isfinite(X.to_numpy()).all()):
            raise ValueError(f"{name}: missing or non-finite features")
    return arms


ARM_ORDER = (["A1-1", "A1-3", "A1-5", "A1-7", "A1-3+sd", "A1-5+sd", "A1-7+sd",
              "X1-1", "X1-3", "X1-5", "X1-7", "X1-3+sd", "X1-5+sd", "X1-7+sd"])


# ---------- models and scores ----------------------------------------------------------------------------------------

def out_of_fold(X: np.ndarray, y: np.ndarray, fields: pd.DataFrame) -> np.ndarray:
    """Step 8 Ridge per scored fold; fold-0 fields train and stay NaN."""
    groups, folds = fields["group_id"].to_numpy(), fields["fold"].to_numpy()
    predicted = np.full(len(y), np.nan)
    for fold in SCORED:
        test = folds == fold
        predicted[test] = ridge_cv(X[~test], y[~test], groups[~test], X[test], step8.ALPHAS)[0]
    return predicted


def r1_out_of_fold(y: np.ndarray, fields: pd.DataFrame) -> np.ndarray:
    latlon, folds = fields[["lat", "lon"]].to_numpy(), fields["fold"].to_numpy()
    predicted = np.full(len(y), np.nan)
    for fold in SCORED:
        test = folds == fold
        predicted[test] = coordinates_knn(latlon[~test], y[~test], latlon[test], step8.K)
    return predicted


def cluster_years_of(fields: pd.DataFrame) -> np.ndarray:
    return (fields["group_id"] + "|" + fields["season_year"].astype(str)).to_numpy()


def arm_score(y: np.ndarray, p: np.ndarray, cluster_years: np.ndarray) -> dict:
    return {"rmse": rmse(y, p), "r2": r2(y, p),
            "rank_inside_clusters": rank_inside_clusters(y, p, cluster_years, MIN_CLUSTER_FIELDS)}


class Draws:
    """The step 8 cluster bootstrap: the same 2,000 draws of groups for every pair of one cohort."""

    def __init__(self, y: np.ndarray, fields: pd.DataFrame):
        self.y, self.groups = y, fields["group_id"].to_numpy()
        self.cluster_years = cluster_years_of(fields)
        self.keep = in_large_clusters(self.cluster_years, MIN_CLUSTER_FIELDS)
        self.y_in = centred(y[self.keep], self.cluster_years[self.keep])
        self.full = list(group_draws(self.groups, BOOTSTRAP_DRAWS, SEED))
        self.rank = list(group_draws(self.groups[self.keep], BOOTSTRAP_DRAWS, SEED))

    def pair(self, a: np.ndarray, b: np.ndarray) -> list[dict]:
        """a minus b on RMSE, R2 and rank inside clusters, with the 95 % interval and a two-sided bootstrap p."""
        y, cy, keep = self.y, self.cluster_years, self.keep
        a_in, b_in = centred(a[keep], cy[keep]), centred(b[keep], cy[keep])
        rows = []
        for metric, point, draws in (
                ("rmse", rmse(y, a) - rmse(y, b), [rmse(y[i], a[i]) - rmse(y[i], b[i]) for i in self.full]),
                ("r2", r2(y, a) - r2(y, b), [r2(y[i], a[i]) - r2(y[i], b[i]) for i in self.full]),
                ("rank", spearman(self.y_in, a_in) - spearman(self.y_in, b_in),
                 [spearman(self.y_in[i], a_in[i]) - spearman(self.y_in[i], b_in[i]) for i in self.rank])):
            d = np.asarray(draws, dtype=float)
            d = d[np.isfinite(d)]
            p = min(1.0, 2 * min(float(np.mean(d <= 0)), float(np.mean(d >= 0))))
            rows.append({"metric": metric, "diff": point, "lo": float(np.quantile(d, 0.025)),
                         "hi": float(np.quantile(d, 0.975)), "p": p})
        return rows


def holm(p: pd.Series) -> pd.Series:
    order = p.sort_values().index
    m = len(p)
    adjusted = pd.Series([min(1.0, (m - i) * p[k]) for i, k in enumerate(order)], index=order).cummax()
    return adjusted.reindex(p.index)


def pairs_of() -> list[tuple[str, str, str]]:
    """(a, b, kind): every window minus its 1-pixel arm, every +sd minus the same window, every arm minus R1."""
    out = []
    for family in ("A1", "X1"):
        for w in SIZES[1:]:
            out += [(f"{family}-{w}", f"{family}-1", "window_vs_1px"), (f"{family}-{w}+sd", f"{family}-1", "window_vs_1px")]
        out += [(f"{family}-{w}+sd", f"{family}-{w}", "sd_vs_window") for w in SIZES[1:]]
    out += [(arm, "R1", "vs_R1") for arm in ARM_ORDER]
    return out


# ---------- references: today's numbers ------------------------------------------------------------------------------

def references(cohort: str) -> dict[str, dict]:
    """Today's scores of R1, A1-1 and X1-1: results/v2/baseline_scores.csv (Lacuna) and the time-features table."""
    ref: dict[str, dict] = {}
    tf = pd.read_csv(REPO / "experiments" / "time_features" / "results.csv")
    tf = tf[tf.cohort == cohort].drop_duplicates("variant").set_index("variant")
    for arm, variant in (("A1-1", "A1 max + mean"), ("X1-1", "M2 monthly band curve")):
        row = tf.loc[variant]
        ref[arm] = {"rmse": row.rmse, "r2": row.r2, "rank_inside_clusters": row.rank_inside_clusters,
                    "source": "experiments/time_features/results.csv"}
    base = pd.read_csv(REPO / "results" / "v2" / "baseline_scores.csv")
    base = base[base.cohort == cohort]
    if len(base):
        value = base.set_index(["arm", "metric"])["value"]
        for arm, name in (("A1-1", "A1"), ("R1", "R1")):
            ref[arm] = {"rmse": value[name, "rmse_t_ha"], "r2": value[name, "r2"],
                        "rank_inside_clusters": value[name, "rank_inside_clusters"],
                        "source": "results/v2/baseline_scores.csv"}
    else:  # Zimbabwe 2024 has no step 8 row; the step-up ladder scored R1 with the step 8 code
        ladder = pd.read_csv(REPO / "experiments" / "stepup" / "results.csv")
        row = ladder[(ladder.cohort == cohort) & ladder.step.str.startswith("S1 R1")].iloc[0]
        ref["R1"] = {"rmse": row.rmse, "r2": row.r2, "rank_inside_clusters": row.rank_inside_clusters,
                     "source": "experiments/stepup/results.csv"}
    return ref


def check_reference(cohort: str, arm: str, score: dict, ref: dict) -> dict:
    """Stop when a 1-pixel arm or R1 does not give back today's number."""
    out = {"arm": arm, "source": ref["source"]}
    for metric in ("rmse", "r2", "rank_inside_clusters"):
        gap = abs(score[metric] - ref[metric])
        out[metric] = {"now": score[metric], "before": float(ref[metric]), "gap": gap}
        if not gap < TOLERANCE:
            sys.exit(f"{cohort} {arm} {metric}: {score[metric]:.6f} here, {ref[metric]:.6f} in {ref['source']}; stopping.")
    return out


# ---------- label-free data checks -----------------------------------------------------------------------------------

def data_checks(win: pd.DataFrame, arms: dict[str, pd.DataFrame]) -> dict:
    one = win[win.w == 1].set_index(["obs_id", "month"])
    out = {"fields": int(win.obs_id.nunique()), "clear_field_months": len(one),
           "features": {name: int(X.shape[1]) for name, X in arms.items()}}
    for w in SIZES:
        f = win[win.w == w].set_index(["obs_id", "month"]).loc[one.index]
        gap = (f.ndvi - one.ndvi).abs()
        out[f"w{w}"] = {
            "clear_pixel_share": round(float((f.n_valid / f.n_window).mean()), 4),
            "months_with_every_pixel_clear": round(float((f.n_valid == f.n_window).mean()), 4),
            "median_abs_ndvi_gap_to_1px": round(float(gap.median()), 4),
            "p90_abs_ndvi_gap_to_1px": round(float(gap.quantile(0.9)), 4),
            "mean_ndvi_sd_in_window": round(float(f.sd_ndvi.mean()), 4),
            "corr_ndvi_season_max_with_1px": round(float(np.corrcoef(arms[f"A1-{w}"].ndvi_season_max,
                                                                     arms["A1-1"].ndvi_season_max)[0, 1]), 4),
            "never_green_fields_ndvi_max_below_0_5": int((arms[f"A1-{w}"].ndvi_season_max < 0.5).sum()),
        }
    return out


# ---------- run ------------------------------------------------------------------------------------------------------

def git_commit() -> str:
    run = subprocess.run(["git", "describe", "--always", "--dirty", "--abbrev=40"], cwd=REPO, capture_output=True,
                         text=True, check=False)
    return run.stdout.strip() or "unknown"


def load(cohort: str, expected: int, labels: pd.DataFrame, table: pd.DataFrame):
    """The step 8 rows, folds and A1 of one cohort, after the hash checks, and its window rows with k."""
    step8.check_frozen(V2, LABELS_FILE, {cohort: expected})
    X_a1, y, fields = step8.cohort_rows(cohort, V2, labels, expected, LABELS_FILE.removesuffix(".parquet"))
    win = table[table.cohort == cohort]
    if set(win.obs_id) != set(y.index):
        raise ValueError(f"{cohort}: windows.parquet does not hold the load_xy rows; run windows.py again")
    return X_a1, y, fields, with_k(win, labels["season_start"])


def run_cohort(cohort: str, expected: int, role: str, labels: pd.DataFrame, table: pd.DataFrame):
    X_a1, y_series, fields, win = load(cohort, expected, labels, table)
    arms = arms_for(win, y_series.index)
    gap = float(np.abs(arms["A1-1"].to_numpy() - X_a1.to_numpy()).max())
    if not gap < 1e-9:
        sys.exit(f"{cohort}: A1-1 differs from load_xy by {gap:.2e}; stopping.")
    y = y_series.to_numpy()
    tested = fields["fold"].isin(SCORED).to_numpy()
    sub = fields[tested]
    cy = cluster_years_of(sub)
    predicted, scores = {}, {}

    def score(name: str, p: np.ndarray) -> None:
        predicted[name] = p[tested]
        scores[name] = arm_score(y[tested], predicted[name], cy)

    # 1. Today's numbers first: R1, A1-1, X1-1. Stop if one differs.
    score("R1", r1_out_of_fold(y, fields))
    for name in ("A1-1", "X1-1"):
        score(name, out_of_fold(arms[name].to_numpy(), y, fields))
    ref = references(cohort)
    reproduced = [check_reference(cohort, arm, scores[arm], ref[arm]) for arm in ("R1", "A1-1", "X1-1") if arm in ref]
    print(f"{cohort}: today's numbers reproduced for {', '.join(r['arm'] for r in reproduced)}", flush=True)
    # 2. The window arms.
    for name in ARM_ORDER:
        if name not in predicted:
            score(name, out_of_fold(arms[name].to_numpy(), y, fields))
    draws = Draws(y[tested], sub)
    pair_rows = [{"cohort": cohort, "a": a, "b": b, "kind": kind, **row}
                 for a, b, kind in pairs_of() for row in draws.pair(predicted[a], predicted[b])]
    pairs = pd.DataFrame(pair_rows)
    pairs["p_holm"] = np.nan
    for metric in ("rmse", "r2", "rank"):
        mask = (pairs.kind == "window_vs_1px") & (pairs.metric == metric)
        pairs.loc[mask, "p_holm"] = holm(pairs.loc[mask, "p"]).to_numpy()
    results = pd.DataFrame([{"cohort": cohort, "role": role, "arm": name,
                             "n_features": 2 if name == "R1" else arms[name].shape[1],
                             **scores[name], "n_rows": int(tested.sum()), "n_clusters": int(sub.group_id.nunique())}
                            for name in ["R1", *ARM_ORDER]])
    oof = pd.DataFrame(predicted, index=sub.index).assign(y_t_ha=y[tested], fold=sub.fold, group_id=sub.group_id)
    checks = {"role": role, "a1_1_max_gap_to_load_xy": gap, "reproduced": reproduced, **data_checks(win, arms)}
    return results, pairs, checks, oof


def interval(r) -> str:
    return f"{r['diff']:+.3f} ({r['lo']:+.3f} to {r['hi']:+.3f})"


def report(results: pd.DataFrame, pairs: pd.DataFrame, run: dict) -> str:
    lines = ["# Footprint results (generated by footprint.py)", "",
             (f"Data v2, split `s1_cc2km`, folds 1-4 scored (fold 0 trains, never scored). Seed {SEED}, "
              f"{BOOTSTRAP_DRAWS:,} cluster-bootstrap draws. Commit `{run['commit']}`. "
              f"PLAN.md SHA-256 `{run['plan_sha256'][:16]}`."), ""]
    for cohort, rows in results.groupby("cohort", sort=False):
        p = pairs[pairs.cohort == cohort]
        lines += [f"## {cohort} ({rows.role.iloc[0]})", "",
                  f"{rows.n_rows.iloc[0]:,} fields in {rows.n_clusters.iloc[0]:,} clusters.", "",
                  "| Arm | Features | RMSE, t/ha | R2 | Rank inside clusters |", "|---|---:|---:|---:|---:|"]
        lines += [f"| {r.arm} | {r.n_features} | {r.rmse:.3f} | {r.r2:.3f} | {r.rank_inside_clusters:.3f} |"
                  for r in rows.itertuples()]
        for kind, title in (("window_vs_1px", "Window minus 1 pixel"), ("sd_vs_window", "With std minus without"),
                            ("vs_R1", "Arm minus R1")):
            part = p[p.kind == kind]
            lines += ["", f"### {title}", "",
                      "| Pair | RMSE | R2 | Rank inside clusters | Holm p (RMSE / rank) |", "|---|---|---|---|---|"]
            for (a, b), g in part.groupby(["a", "b"], sort=False):
                m = g.set_index("metric")
                holm_text = (f"{m.loc['rmse', 'p_holm']:.3f} / {m.loc['rank', 'p_holm']:.3f}"
                             if kind == "window_vs_1px" else "")
                lines.append(f"| {a} minus {b} | {interval(m.loc['rmse'])} | {interval(m.loc['r2'])} | "
                             f"{interval(m.loc['rank'])} | {holm_text} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not PLAN.exists():
        sys.exit("PLAN.md is missing; no score before the plan. Stopping.")
    step8.check_database(V2, REPO / "configs" / "team_database_v2.json")
    labels = pd.read_parquet(V2 / "processed" / LABELS_FILE,
                             columns=["obs_id", "yield_kg_ha", "lat", "lon", "season_start"]).set_index("obs_id")
    table = pd.read_parquet(W.OUT)
    run = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "commit": git_commit(), "seed": SEED,
           "draws": BOOTSTRAP_DRAWS, "plan_sha256": sha256(PLAN), "windows_sha256": sha256(W.OUT),
           "labels_sha256": sha256(V2 / "processed" / LABELS_FILE),
           "database": json.loads((REPO / "configs" / "team_database_v2.json").read_text(encoding="utf-8")),
           "split_sha256": {c: sha256(V2 / "splits" / f"{c}__s1_cc2km.csv") for c in COHORTS}}
    all_results, all_pairs, all_checks, oofs = [], [], {}, []
    for cohort, (expected, role) in COHORTS.items():
        results, pairs, checks, oof = run_cohort(cohort, expected, role, labels, table)
        all_results.append(results)
        all_pairs.append(pairs)
        all_checks[cohort] = checks
        oofs.append(oof.assign(cohort=cohort))
        print(f"{cohort}: scored {len(results)} arms, {len(pairs)} pair rows", flush=True)
    results, pairs = pd.concat(all_results, ignore_index=True), pd.concat(all_pairs, ignore_index=True)
    results.to_csv(HERE / "results.csv", index=False, lineterminator="\n")
    pairs.to_csv(HERE / "pairs.csv", index=False, lineterminator="\n")
    pd.concat(oofs).to_csv(HERE / "predictions.csv", lineterminator="\n")
    (HERE / "checks.json").write_text(json.dumps(all_checks, indent=2) + "\n", encoding="utf-8", newline="\n")
    run["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (HERE / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")
    text = report(results, pairs, run)
    (HERE / "results.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
