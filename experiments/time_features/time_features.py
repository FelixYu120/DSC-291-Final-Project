"""P1 time features: which summary of the monthly series ranks fields best? Data v2, every cohort, folds 1-4 vs A1.

    python experiments/time_features/time_features.py      # -> experiments/time_features/{results.csv, checks.json,
                                                           #    features.parquet, README.md}

Every feature is label-free: it uses only the field's own clear months inside the fixed cohort window. The harvest or
cut date (`obs_date`) is read only for a data check (how many clear months fall after it), never as an input.
Exploratory: many variants on the same folds, so p-values are Holm-corrected within each cohort, and fold 0 stays
untouched for a final confirmation.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
V2 = REPO / "data" / "v2"
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("step8", REPO / "scripts" / "step8_run_baseline.py")
step8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(step8)                      # also puts src/ on sys.path
from cropyield.baselines import ridge_cv  # noqa: E402
from cropyield.eval.scores import centred, group_draws, in_large_clusters, r2, rank_inside_clusters, rmse, spearman  # noqa: E402

INDICES = ["ndvi", "gcvi", "mtci", "ndvi705", "ndvi740"]
BANDS = ["b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12"]
PEAK_INDICES = ["gcvi", "ndvi705", "mtci"]
SOUTH, KENYA_LONG_RAINS = {11, 12, 1, 2, 3, 4}, {3, 4, 5, 6, 7, 8}   # pre-harvest calendar months (crop calendars)
COHORTS = {  # name: (model rows, pre-harvest months, role)
    "zimbabwe_lacuna_2022_2023": (1880, SOUTH, "main"),
    "malawi_2023": (253, SOUTH, "main"),
    "malawi_2022": (529, SOUTH, "main"),
    "kenya_oaf_2019_2020": (3977, KENYA_LONG_RAINS, "main"),
    "zimbabwe_2024": (2458, SOUTH, "robustness (parked: positive rows only)"),
}
BASE, SKIP = "A1 max + mean", ("0",)
RANK_ONLY = "W1 within-village Ridge on A1 features"   # predicts deviations from the village mean, not t/ha


def load(cohort: str, expected: int, labels: pd.DataFrame):
    """Model rows (step 8 rules), their folds, and every clear field-month with its month-of-season k."""
    X_a1, y, fields = step8.cohort_rows(cohort, V2, labels, expected, "labels_v2")
    columns = ", ".join(["m.obs_id", "m.month", *[f"m.{c}" for c in INDICES + BANDS], "s.acquired"])
    with duckdb.connect(str(V2 / "cropyield.duckdb"), read_only=True) as con:
        monthly = con.execute(f"""SELECT {columns} FROM monthly m
                                  LEFT JOIN scenes s ON s.obs_id = m.obs_id AND s.month = m.month
                                  WHERE m.cohort = ? AND m.coverage_state = 'clear'""", [cohort]).df()
    monthly = monthly[monthly.obs_id.isin(y.index) & monthly[INDICES].notna().all(axis=1)].copy()
    start = pd.to_datetime(labels.loc[monthly.obs_id, "season_start"]).to_numpy()
    month = pd.to_datetime(monthly.month + "-01")
    monthly["k"] = (month.dt.year * 12 + month.dt.month).to_numpy() - (pd.DatetimeIndex(start).year * 12 + pd.DatetimeIndex(start).month).to_numpy()
    return X_a1, y, fields, monthly


def cubes(monthly: pd.DataFrame, index: pd.Index) -> dict[str, pd.DataFrame]:
    """Field x month-of-season table per variable; NaN where the month is not clear. Months with no data dropped."""
    ks = sorted(monthly.k.unique())
    return {v: monthly.pivot(index="obs_id", columns="k", values=v).reindex(index=index, columns=ks) for v in INDICES + BANDS}


def peak_features(cube: pd.DataFrame) -> pd.DataFrame:
    """Per field: peak value, peak month, area under the gap-filled curve from the first clear month to the peak,
    and the mean of the clear months within one month of the peak."""
    rows = []
    for _, series in cube.iterrows():
        clear = series.dropna()
        x, v = clear.index.to_numpy(dtype=float), clear.to_numpy()
        peak = int(np.argmax(v))
        grid = np.arange(x[0], x[peak] + 1)
        curve = np.interp(grid, x, v)
        near = v[np.abs(x - x[peak]) <= 1]
        rows.append((v[peak], x[peak], float(((curve[:-1] + curve[1:]) / 2).sum()), near.mean()))
    return pd.DataFrame(rows, index=cube.index, columns=["peak", "peak_month", "area_before_peak", "peak_window_mean"])


def build(cohort: str, X_a1: pd.DataFrame, y: pd.Series, monthly: pd.DataFrame, pre_months: set) -> tuple[dict, dict]:
    c = cubes(monthly, y.index)
    ks = list(c["ndvi"].columns)
    start_month = 10 if pre_months is SOUTH else 2
    calendar = {k: (start_month - 1 + k) % 12 + 1 for k in ks}
    pre_ks = [k for k in ks if calendar[k] in pre_months]
    mean = pd.DataFrame({f"{i}_mean": c[i].mean(axis=1) for i in INDICES})
    pre = pd.DataFrame({f"{i}_mean_pre": c[i][pre_ks].mean(axis=1) for i in INDICES})
    fallback = int(pre.isna().any(axis=1).sum())
    pre = pre.fillna(mean.set_axis(pre.columns, axis=1))
    mx = pd.DataFrame({f"{i}_max": c[i].max(axis=1) for i in INDICES})
    med = pd.DataFrame({f"{i}_median": c[i].median(axis=1) for i in INDICES})
    pk = {i: peak_features(c[i]) for i in INDICES}
    peaks = pd.concat([pk[i][["peak", "peak_month", "area_before_peak"]].add_prefix(f"{i}_") for i in PEAK_INDICES], axis=1)
    window = pd.DataFrame({f"{i}_peak_window_mean": pk[i]["peak_window_mean"] for i in INDICES})
    def curve(names, keep):
        """One column per variable and month: gaps filled linearly between clear months, edges with the nearest clear
        month; a field with no clear month in `keep` gets its own whole-window mean."""
        parts = []
        for v in names:
            part = c[v][keep].interpolate(axis=1, limit_direction="both")
            parts.append(part.apply(lambda col, own=c[v].mean(axis=1): col.fillna(own)).add_prefix(f"{v}_m"))
        return pd.concat(parts, axis=1)
    variants = {
        BASE: X_a1,
        "V0 mean, whole window": mean,
        "V1 mean, pre-harvest months": pre,
        "V2 max (peak value)": mx,
        "V2+ peak, peak month, area before peak": peaks,
        "V3 mean + median + max": pd.concat([mean, med, mx], axis=1),
        "L1 GCVI peak only (Li et al. 2022)": mx[["gcvi_max"]],
        "C1 mean within 1 month of the peak": window,
        "M1 monthly index curve": curve(INDICES, ks),
        "M1-pre monthly index curve, pre-harvest": curve(INDICES, pre_ks),
        "M2 monthly band curve": curve(BANDS, ks),
        "M2-pre monthly band curve, pre-harvest": curve(BANDS, pre_ks),
    }
    # Self-checks: the max and mean built here are the database's season features, and no feature is missing
    assert np.allclose(mx.to_numpy(), X_a1[[f"{i}_season_max" for i in INDICES]].to_numpy()), cohort
    assert np.allclose(mean.to_numpy(), X_a1[[f"{i}_season_mean" for i in INDICES]].to_numpy()), cohort
    for name, X in variants.items():
        assert X.index.equals(y.index) and np.isfinite(X.to_numpy()).all(), (cohort, name)
    info = {"months_of_season": [f"{k}:{calendar[k]}" for k in ks], "pre_harvest_months": [calendar[k] for k in pre_ks],
            "pre_harvest_fallback_fields": fallback}
    table = pd.concat([mean, pre, mx, med, peaks, window], axis=1).assign(cohort=cohort)
    return variants, {"info": info, "table": table}


def within_village(X: pd.DataFrame, y: pd.Series, fields: pd.DataFrame) -> np.ndarray:
    """Ridge on features and yield minus their 2 km cluster mean; at test, features minus the test cluster mean.
    Predicts 'better or worse than the village', so only the rank inside clusters is meaningful."""
    groups = fields["group_id"].to_numpy()
    Xd = (X - X.groupby(groups).transform("mean")).to_numpy()
    yd = (y - y.groupby(groups).transform("mean")).to_numpy()
    out = np.full(len(y), np.nan)
    for fold in sorted(set(fields["fold"]) - set(SKIP)):
        test = (fields["fold"] == fold).to_numpy()
        out[test] = ridge_cv(Xd[~test], yd[~test], groups[~test], Xd[test], step8.ALPHAS)[0]
    return out


def compare(yt, p, base, groups, cy, keep, rank_only=False) -> dict:
    """Paired cluster bootstrap against A1 (same draws and seed as step 8): differences, 95 % intervals, p-values."""
    y_in, p_in, b_in = (centred(v[keep], cy[keep]) for v in (yt, p, base))
    rank = [spearman(y_in[i], p_in[i]) - spearman(y_in[i], b_in[i]) for i in group_draws(groups[keep], 2000, step8.SEED)]
    row = {"rank_vs_A1": spearman(y_in, p_in) - spearman(y_in, b_in), "rank_lo": np.nanquantile(rank, .025),
           "rank_hi": np.nanquantile(rank, .975),
           "p_rank": min(1.0, 2 * min(np.nanmean(np.array(rank) <= 0), np.nanmean(np.array(rank) >= 0)))}
    if not rank_only:
        diff =[rmse(yt[i], p[i]) - rmse(yt[i], base[i]) for i in group_draws(groups, 2000, step8.SEED)]
        row |= {"rmse_vs_A1": rmse(yt, p) - rmse(yt, base), "rmse_lo": np.quantile(diff, .025), "rmse_hi": np.quantile(diff, .975)}
    return row


def holm(p: pd.Series) -> pd.Series:
    order = p.sort_values().index
    adjusted = np.minimum(1, np.maximum.accumulate([(len(p) - r) * p[i] for r, i in enumerate(order)]))
    return pd.Series(adjusted, index=order).reindex(p.index)


def data_checks(cohort, y, fields, monthly, labels) -> dict:
    tested = fields["fold"] != "0"
    when = pd.to_datetime(labels.loc[monthly.obs_id, "obs_date"]).to_numpy()
    shot = pd.to_datetime(monthly.acquired).to_numpy()
    month_after = (pd.to_datetime(monthly.month + "-01") > pd.to_datetime(pd.Series(when).dt.to_period("M").astype(str) + "-01", errors="coerce").to_numpy())
    has_date = ~pd.isna(when)
    day = pd.to_datetime(monthly.acquired).dt.day
    return {
        "fields": len(y), "scored_folds_1_4": int(tested.sum()), "clusters_scored": int(fields[tested]["group_id"].nunique()),
        "fold_sizes": {k: int(v) for k, v in fields["fold"].value_counts().sort_index().items()},
        "groups_in_two_folds": int((fields.groupby("group_id")["fold"].nunique() > 1).sum()),
        "clear_months_per_field": round(float(monthly.groupby("obs_id").size().mean()), 2),
        "clear_share_by_month_of_season": {int(k): float(v) for k, v in monthly.groupby("k").obs_id.nunique().div(len(y)).round(2).items()},
        "share_clear_months_after_cut_month": round(float(month_after[has_date].mean()), 3),
        "share_clear_photos_after_cut_day": round(float((shot > when)[has_date].mean()), 3),
        "photo_day_of_month_sd": round(float(day.std()), 1),
        "mtci_outside_0_50": int(((monthly.mtci < 0) | (monthly.mtci > 50)).sum()),
        "yield_t_ha_median": round(float(y.median()), 2),
    }


def main() -> int:
    labels = pd.read_parquet(V2 / "processed" / "labels_v2.parquet").set_index("obs_id")
    results, checks, tables = [], {}, []
    for cohort, (expected, pre_months, role) in COHORTS.items():
        X_a1, y, fields, monthly = load(cohort, expected, labels)
        variants, extra = build(cohort, X_a1, y, monthly, pre_months)
        checks[cohort] = {"role": role, **data_checks(cohort, y, fields, monthly, labels), **extra["info"]}
        tables.append(extra["table"])
        tested = (fields["fold"] != "0").to_numpy()
        yt, ft = y.to_numpy()[tested], fields[tested]
        groups = ft["group_id"].to_numpy()
        cy = (ft["group_id"] + "|" + ft["season_year"].astype(str)).to_numpy()
        keep = in_large_clusters(cy, step8.MIN_CLUSTER_FIELDS)
        preds = {}
        for name, X in variants.items():
            out = step8.out_of_fold(X, y, fields, SKIP)
            preds[name] = out["A1"][tested]
        preds["R1 coordinates only"] = out["R1"][tested]
        preds[RANK_ONLY] = within_village(X_a1, y, fields)[tested]
        rows = []
        for name, p in preds.items():
            level = name != RANK_ONLY
            row = {"cohort": cohort, "role": role, "variant": name,
                   "n_features": variants[name].shape[1] if name in variants else (2 if name.startswith("R1") else 10),
                   "rmse": rmse(yt, p) if level else np.nan, "r2": r2(yt, p) if level else np.nan,
                   "rank_inside_clusters": rank_inside_clusters(yt, p, cy, step8.MIN_CLUSTER_FIELDS)}
            if name != BASE:
                row |= compare(yt, p, preds[BASE], groups, cy, keep, rank_only=not level)
            rows.append(row)
        frame = pd.DataFrame(rows)
        tests = frame["variant"].ne(BASE) & frame["variant"].ne("R1 coordinates only")
        frame.loc[tests, "p_rank_holm"] = holm(frame.loc[tests, "p_rank"])
        frame["wins"] = (frame["rank_lo"] > 0) & ~(frame["rmse_lo"] > 0) & (frame["p_rank_holm"] < 0.05)
        results.append(frame)
        print(f"{cohort}: done ({len(y)} fields)", flush=True)
    res = pd.concat(results, ignore_index=True)
    res.to_csv(OUT / "results.csv", index=False, lineterminator="\n")
    pd.concat(tables).to_parquet(OUT / "features.parquet")
    (OUT / "checks.json").write_text(json.dumps(checks, indent=1, default=str) + "\n", encoding="utf-8")
    fmt = lambda v, lo, hi: "" if pd.isna(v) else f"{v:+.3f} ({lo:+.3f} to {hi:+.3f})"  # noqa: E731
    lines = ["# P1 time features, data v2, folds 1-4", "",
             "Generated by `time_features.py`. Paired cluster bootstrap vs A1 (2,000 draws, seed 20261029); `p Holm` is "
             "the rank p-value corrected for the 12 variants of the cohort. A win needs the rank interval above 0, the "
             "RMSE interval not entirely worse, and p Holm < 0.05. W1 predicts within-village deviations, so only its rank counts.", ""]
    for cohort, rows in res.groupby("cohort", sort=False):
        ck = checks[cohort]
        lines += [f"## {cohort} ({ck['role']})", "",
                  f"{ck['scored_folds_1_4']} scored fields, {ck['clusters_scored']} clusters; clear photos after the cut day: "
                  f"{ck['share_clear_photos_after_cut_day']:.0%} (after the cut month: {ck['share_clear_months_after_cut_month']:.0%}).", "",
                  "| Variant | Features | RMSE | R² | Rank inside clusters | Rank vs A1 | RMSE vs A1 | p Holm | Win |",
                  "|---|---:|---:|---:|---:|---|---|---:|---|"]
        for r in rows.itertuples():
            lines.append(f"| {r.variant} | {r.n_features} | {'' if pd.isna(r.rmse) else f'{r.rmse:.3f}'} | "
                         f"{'' if pd.isna(r.r2) else f'{r.r2:.3f}'} | {r.rank_inside_clusters:.3f} | "
                         f"{fmt(getattr(r, 'rank_vs_A1'), r.rank_lo, r.rank_hi)} | {fmt(getattr(r, 'rmse_vs_A1'), r.rmse_lo, r.rmse_hi)} | "
                         f"{'' if pd.isna(r.p_rank_holm) else f'{r.p_rank_holm:.3f}'} | {'yes' if r.wins else ''} |")
        lines.append("")
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
