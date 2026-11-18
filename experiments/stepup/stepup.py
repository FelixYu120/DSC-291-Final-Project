"""Step-up ladder: from the simplest baseline to monthly bands, Presto and MOSAIKS, with Ridge and Bayesian heads.

    python experiments/stepup/stepup.py     # -> experiments/stepup/{results.csv, importance.csv, gcvi_months.csv, README.md}

Every row uses the same fields and the same s1_cc2km folds as step 8: fold-0 fields train, folds 1-4 are scored.
Features are label-free (the field's own clear months in the fixed cohort window; time_features.py builds them).
Heads: Ridge (the step 8 head), Bayesian ridge, ARD (sparse Bayesian; shows which inputs matter), a Gaussian process
(Bayesian, non-linear; small cohorts only), and a Bayesian pairwise ranking model (Bradley-Terry with features and a
Gaussian prior, trained on pairs of fields inside the same 2 km cluster; it predicts order, not t/ha).
Exploratory: many rows on the same folds, so p-values are Holm-corrected within each cohort.
"""
from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.linear_model import ARDRegression, BayesianRidge, LogisticRegression, Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
V1, V2 = REPO / "data", REPO / "data" / "v2"


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


tf = module("time_features", REPO / "experiments" / "time_features" / "time_features.py")   # loads step 8 too
step8 = tf.step8
from cropyield.baselines.models import Winsorize  # noqa: E402
from cropyield.eval.scores import (bias, centred, group_draws, in_large_clusters, mae, r2, rank_inside_clusters,  # noqa: E402
                                   rmse, spearman)

warnings.filterwarnings("ignore", category=ConvergenceWarning)
SEED, SKIP = step8.SEED, ("0",)
PRESTO = REPO / "experiments" / "presto_finetune" / "runs"
GP_COHORTS = {"zimbabwe_lacuna_2022_2023", "malawi_2022", "malawi_2023"}   # a GP on 3,000+ fields is too slow here
MOSAIKS_OK = {"zimbabwe_lacuna_2022_2023", "malawi_2023", "kenya_oaf_2019_2020", "zimbabwe_2024"}  # v1 Malawi 2022 chips were wrong


# ---------- heads ---------------------------------------------------------------------------------------------------

def fit_predict(head: str, X_train, y_train, g_train, X_test):
    """Fit one head on the training rows only; return test and training predictions."""
    if head == "Ridge":                                               # identical to cropyield.baselines.ridge_cv
        model = GridSearchCV(make_pipeline(Winsorize(), StandardScaler(), Ridge()), {"ridge__alpha": step8.ALPHAS},
                             cv=GroupKFold(n_splits=min(5, len(np.unique(g_train)))), scoring="neg_mean_squared_error")
        model.fit(X_train, y_train, groups=g_train)
    elif head == "Bayesian ridge":
        model = make_pipeline(Winsorize(), StandardScaler(), BayesianRidge()).fit(X_train, y_train)
    elif head == "ARD":
        model = make_pipeline(Winsorize(), StandardScaler(), ARDRegression(max_iter=300)).fit(X_train, y_train)
    elif head == "Gaussian process":
        kernel = ConstantKernel(1.0) * RBF(length_scale=np.sqrt(X_train.shape[1])) + WhiteKernel(1.0)
        model = make_pipeline(Winsorize(), StandardScaler(),
                              GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=0)).fit(X_train, y_train)
    else:
        raise ValueError(head)
    return model.predict(X_test), model.predict(X_train), model


def bradley_terry(X_train, y_train, clusters_train, X_test, max_pairs=200, seed=SEED):
    """Pairs of fields inside one cluster-year: P(i beats j) = sigmoid(w . (x_i - x_j)), w ~ N(0, 1) (L2 penalty, C = 1).
    Returns the score w . x for the test fields (an order, not t/ha)."""
    prep = make_pipeline(Winsorize(), StandardScaler()).fit(X_train)
    Z = prep.transform(X_train)
    rng, left, right = np.random.default_rng(seed), [], []
    for members in pd.Series(np.arange(len(y_train))).groupby(clusters_train).agg(list):
        pairs = [(i, j) for a, i in enumerate(members) for j in members[a + 1:] if y_train[i] != y_train[j]]
        if len(pairs) > max_pairs:
            pairs = [pairs[k] for k in rng.choice(len(pairs), max_pairs, replace=False)]
        left += [p[0] for p in pairs]
        right += [p[1] for p in pairs]
    left, right = np.array(left), np.array(right)
    diff = np.vstack([Z[left] - Z[right], Z[right] - Z[left]])
    wins = np.concatenate([y_train[left] > y_train[right], y_train[right] > y_train[left]]).astype(int)
    w = LogisticRegression(C=1.0, fit_intercept=False, max_iter=2000).fit(diff, wins).coef_[0]
    return prep.transform(X_test) @ w, len(left)


def out_of_fold(head: str, X: pd.DataFrame, y: pd.Series, fields: pd.DataFrame):
    """Predictions for folds 1-4 (fold 0 only trains) and the mean training R2 (overfitting check)."""
    Xv, yv = X.to_numpy(dtype=float), y.to_numpy()
    groups = fields["group_id"].to_numpy()
    clusters = (fields["group_id"] + "|" + fields["season_year"].astype(str)).to_numpy()
    pred, train_r2, pairs = np.full(len(y), np.nan), [], []
    for fold in sorted(set(fields["fold"]) - set(SKIP)):
        test = (fields["fold"] == fold).to_numpy()
        if head == "Bayesian pairwise rank":
            pred[test], n = bradley_terry(Xv[~test], yv[~test], clusters[~test], Xv[test])
            pairs.append(n)
        else:
            pred[test], fitted, _ = fit_predict(head, Xv[~test], yv[~test], groups[~test], Xv[test])
            train_r2.append(r2(yv[~test], fitted))
    return pred, (float(np.mean(train_r2)) if train_r2 else np.nan), (int(np.mean(pairs)) if pairs else None)


# ---------- features ------------------------------------------------------------------------------------------------

def gap_filled(cube: pd.DataFrame, prefix: str) -> pd.DataFrame:
    part = cube.interpolate(axis=1, limit_direction="both")
    return part.apply(lambda col, own=cube.mean(axis=1): col.fillna(own)).add_prefix(prefix)


def ladder(cohort: str, X_a1, y, monthly, labels, pre_months) -> dict[str, pd.DataFrame]:
    variants, _ = tf.build(cohort, X_a1, y, monthly, pre_months)
    c = tf.cubes(monthly, y.index)
    g = tf.peak_features(c["gcvi"])
    xy = labels.loc[y.index, ["lat", "lon"]].astype(float)
    coords = xy.assign(lat2=xy.lat ** 2, lon2=xy.lon ** 2, latlon=xy.lat * xy.lon)
    steps = {
        "S2 GCVI peak": variants["L1 GCVI peak only (Li et al. 2022)"],
        "S3 GCVI season shape (peak, mean, peak month, area before peak)":
            pd.DataFrame({"gcvi_peak": g["peak"], "gcvi_mean": c["gcvi"].mean(axis=1), "gcvi_peak_month": g["peak_month"],
                          "gcvi_area_before_peak": g["area_before_peak"]}),
        "S4 GCVI monthly curve": gap_filled(c["gcvi"], "gcvi_m"),
        "S5 A1: 5 indices, max + mean": X_a1,
        "S6 5 indices, monthly curve": variants["M1 monthly index curve"],
        "S7 10 bands, monthly curve": variants["M2 monthly band curve"],
        "S8 10 bands, monthly, pre-harvest months only": variants["M2-pre monthly band curve, pre-harvest"],
        "S9 10 bands monthly + coordinates": pd.concat([variants["M2 monthly band curve"], coords], axis=1),
    }
    presto = PRESTO / cohort / "p0_embeddings.npz"
    if presto.exists():
        saved = np.load(presto, allow_pickle=True)
        p0 = pd.DataFrame(saved["P0"], index=saved["obs_id"].astype(str)).add_prefix("presto_").reindex(y.index)
        if p0.notna().all().all():
            steps["S10 Presto frozen embedding (128)"] = p0
            steps["S11 10 bands monthly + Presto"] = pd.concat([variants["M2 monthly band curve"], p0], axis=1)
    if cohort in MOSAIKS_OK:
        with duckdb.connect(str(V1 / "cropyield.duckdb"), read_only=True) as con:
            mos = con.execute("SELECT obs_id, field, chip FROM mosaiks_season WHERE obs_id IN (SELECT unnest(?))",
                              [list(y.index)]).df().set_index("obs_id").reindex(y.index)
        if mos.notna().all().all():
            steps["S12 MOSAIKS field + chip (v1, 2,048)"] = pd.DataFrame(
                np.hstack([np.vstack(mos["field"]), np.vstack(mos["chip"])]), index=y.index).add_prefix("mosaiks_")
    return steps


def heads_for(cohort: str, step: str, n_features: int) -> list[str]:
    heads = ["Ridge", "Bayesian ridge"]
    if n_features <= 130:
        heads.append("ARD")
    if cohort in GP_COHORTS and step[:3] in ("S3 ", "S5 ", "S7 "):
        heads.append("Gaussian process")
    if step[:3] in ("S3 ", "S5 ", "S7 ", "S8 "):
        heads.append("Bayesian pairwise rank")
    return heads


# ---------- scores --------------------------------------------------------------------------------------------------

def decompose(y, p, clusters) -> tuple[float, float, float]:
    """R2 between clusters (cluster means), R2 within clusters (deviations from the cluster mean), share of variance between."""
    frame = pd.DataFrame({"y": y, "p": p, "c": clusters})
    means = frame.groupby("c")[["y", "p"]].transform("mean")
    between = 1 - ((means.y - means.p) ** 2).sum() / ((means.y - y.mean()) ** 2).sum()
    within = 1 - (((y - means.y) - (p - means.p)) ** 2).sum() / ((y - means.y) ** 2).sum()
    share = ((means.y - y.mean()) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return float(between), float(within), float(share)


def versus(yt, p, base, groups, cy, keep, rank_only) -> dict:
    y_in, p_in, b_in = (centred(v[keep], cy[keep]) for v in (yt, p, base))
    draws = [spearman(y_in[i], p_in[i]) - spearman(y_in[i], b_in[i]) for i in group_draws(groups[keep], 2000, SEED)]
    out = {"rank_vs_A1": spearman(y_in, p_in) - spearman(y_in, b_in), "rank_lo": np.nanquantile(draws, .025),
           "rank_hi": np.nanquantile(draws, .975),
           "p_rank": min(1.0, 2 * min(np.nanmean(np.array(draws) <= 0), np.nanmean(np.array(draws) >= 0)))}
    if not rank_only:
        diff = [rmse(yt[i], p[i]) - rmse(yt[i], base[i]) for i in group_draws(groups, 2000, SEED)]
        out |= {"rmse_vs_A1": rmse(yt, p) - rmse(yt, base), "rmse_lo": np.quantile(diff, .025), "rmse_hi": np.quantile(diff, .975)}
    return out


def holm_family(frame: pd.DataFrame) -> pd.Series:
    return frame["p_rank"].notna() & ~frame["step"].str.startswith("S1 ")


def importance(X: pd.DataFrame, y: pd.Series, fields: pd.DataFrame, repeats: int = 5) -> pd.DataFrame:
    """Ridge on the monthly band curve: how much R2 and rank drop when one band (all months) or one month (all bands)
    is shuffled across the test fields of a fold. Model fixed per fold; shuffles use a fixed seed."""
    Xv, yv = X.to_numpy(dtype=float), y.to_numpy()
    groups = fields["group_id"].to_numpy()
    cy = (fields["group_id"] + "|" + fields["season_year"].astype(str)).to_numpy()
    blocks = {f"band {b}": [i for i, c in enumerate(X.columns) if c.startswith(f"{b}_m")] for b in tf.BANDS}
    months = sorted({c.split("_m")[1] for c in X.columns}, key=int)
    blocks |= {f"month {m}": [i for i, c in enumerate(X.columns) if c.endswith(f"_m{m}")] for m in months}
    base, shuffled = np.full(len(yv), np.nan), {k: np.full((repeats, len(yv)), np.nan) for k in blocks}
    rng = np.random.default_rng(SEED)
    for fold in sorted(set(fields["fold"]) - set(SKIP)):
        test = (fields["fold"] == fold).to_numpy()
        base[test], _, model = fit_predict("Ridge", Xv[~test], yv[~test], groups[~test], Xv[test])
        for name, cols in blocks.items():
            for r in range(repeats):
                Xs = Xv[test].copy()
                Xs[:, cols] = Xs[rng.permutation(len(Xs))][:, cols]
                shuffled[name][r, test] = model.predict(Xs)
    tested = (fields["fold"] != "0").to_numpy()
    yt, ct = yv[tested], cy[tested]
    r2_0, rank_0 = r2(yt, base[tested]), rank_inside_clusters(yt, base[tested], ct, step8.MIN_CLUSTER_FIELDS)
    rows = [{"block": k, "r2_drop": r2_0 - np.mean([r2(yt, s[tested]) for s in v]),
             "rank_drop": rank_0 - np.mean([rank_inside_clusters(yt, s[tested], ct, step8.MIN_CLUSTER_FIELDS) for s in v])}
            for k, v in shuffled.items()]
    return pd.DataFrame(rows)


def gcvi_by_month(monthly: pd.DataFrame, y: pd.Series, fields: pd.DataFrame) -> pd.DataFrame:
    """Folds 1-4 only: Spearman of each month's clear GCVI with yield, all fields, between clusters, inside clusters."""
    scored = fields[fields["fold"] != "0"]
    m = monthly[monthly.obs_id.isin(scored.index)][["obs_id", "k", "month", "gcvi"]].copy()
    m["y"] = y.loc[m.obs_id].to_numpy()
    m["c"] = (scored.loc[m.obs_id, "group_id"] + "|" + scored.loc[m.obs_id, "season_year"].astype(str)).to_numpy()
    rows = []
    for k, d in m.groupby("k"):
        size = d.groupby("c").c.transform("size")
        inside = d[size >= 3]
        means = d.groupby("c")[["gcvi", "y"]].mean()
        rows.append({"k": int(k), "months": ",".join(sorted(d.month.str[5:].unique())), "fields": len(d),
                     "all": spearman(d.y.to_numpy(), d.gcvi.to_numpy()),
                     "between_clusters": spearman(means.y.to_numpy(), means.gcvi.to_numpy()),
                     "inside_clusters": spearman(centred(inside.y.to_numpy(), inside.c.to_numpy()),
                                                 centred(inside.gcvi.to_numpy(), inside.c.to_numpy())) if len(inside) > 20 else np.nan})
    return pd.DataFrame(rows)


def main() -> int:
    labels = pd.read_parquet(V2 / "processed" / "labels_v2.parquet").set_index("obs_id")
    results, imps, gcvis = [], [], []
    for cohort, (expected, pre_months, role) in tf.COHORTS.items():
        X_a1, y, fields, monthly = tf.load(cohort, expected, labels)
        steps = ladder(cohort, X_a1, y, monthly, labels, pre_months)
        tested = (fields["fold"] != "0").to_numpy()
        yt, ft = y.to_numpy()[tested], fields[tested]
        groups = ft["group_id"].to_numpy()
        cy = (ft["group_id"] + "|" + ft["season_year"].astype(str)).to_numpy()
        keep = in_large_clusters(cy, step8.MIN_CLUSTER_FIELDS)
        reference = step8.out_of_fold(X_a1, y, fields, SKIP)
        rows = [{"step": "S0 R0 training mean", "head": "-", "p": reference["R0"][tested], "n_features": 0},
                {"step": "S1 R1 coordinates only (10 nearest fields)", "head": "kNN", "p": reference["R1"][tested], "n_features": 2}]
        for step, X in steps.items():
            for head in heads_for(cohort, step, X.shape[1]):
                pred, train_r2, pairs = out_of_fold(head, X, y, fields)
                rows.append({"step": step, "head": head, "p": pred[tested], "n_features": X.shape[1],
                             "train_r2": train_r2, "pairs": pairs})
            print(f"{cohort}: {step} done", flush=True)
        base = next(r["p"] for r in rows if r["step"].startswith("S5") and r["head"] == "Ridge")
        assert np.allclose(base, reference["A1"][tested]), "the Ridge head must equal the step 8 A1"
        for r in rows:
            rank_only = r["head"] == "Bayesian pairwise rank"
            p = r.pop("p")
            r |= {"cohort": cohort, "role": role, "rank_inside_clusters": rank_inside_clusters(yt, p, cy, step8.MIN_CLUSTER_FIELDS)}
            if not rank_only:
                b, w, share = decompose(yt, p, cy)
                r |= {"rmse": rmse(yt, p), "mae": mae(yt, p), "bias": bias(yt, p), "r2": r2(yt, p), "r2_between": b,
                      "r2_within": w, "share_between": share}
            if not (r["step"].startswith("S5") and r["head"] == "Ridge") and not r["step"].startswith("S0"):
                r |= versus(yt, p, base, groups, cy, keep, rank_only)
        frame = pd.DataFrame(rows)
        tests = holm_family(frame)
        frame.loc[tests, "p_rank_holm"] = tf.holm(frame.loc[tests, "p_rank"])
        results.append(frame)
        imps.append(importance(steps["S7 10 bands, monthly curve"], y, fields).assign(cohort=cohort))
        gcvis.append(gcvi_by_month(monthly, y, fields).assign(cohort=cohort))
        print(f"{cohort}: all done", flush=True)
    res = pd.concat(results, ignore_index=True)
    res.to_csv(HERE / "results.csv", index=False, lineterminator="\n")
    pd.concat(imps).to_csv(HERE / "importance.csv", index=False, lineterminator="\n")
    pd.concat(gcvis).to_csv(HERE / "gcvi_months.csv", index=False, lineterminator="\n")
    print(res[["cohort", "step", "head", "r2", "rank_inside_clusters"]].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
