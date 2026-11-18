"""Follow-up spatial transfer diagnostics; no evaluation or fitting on frozen fold zero."""
from __future__ import annotations

import hashlib
import importlib.metadata
import itertools
import json
import platform
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import KNeighborsRegressor
from threadpoolctl import threadpool_limits

from cropyield import ROOT
from cropyield.data.handoff import csv_write, json_write, publish_release, require
from cropyield.data.labels import sha256
from cropyield.data.xy import FEATURES
from cropyield.eval.splits import connected_clusters, unit_xyz
from cropyield.experiments.zimbabwe_merge import (
    purge_source,
    require_training_rows,
    score_predictions,
    training_rows,
)

CONFIG = ROOT / "configs/zimbabwe_transfer_diagnosis_v1.json"
OUTPUT = ROOT / "data/runs/zimbabwe_transfer_diagnosis_v1"
PRIOR = ROOT / "data/runs/zimbabwe_merge_v1"


def prior_run(config: dict) -> Path:
    """Merge release whose rows, memberships and source permissions this diagnosis inherits (v1 by default)."""
    return ROOT / config.get("merge_run", "data/runs/zimbabwe_merge_v1")
INDICES = ["ndvi", "gcvi", "mtci", "ndvi705", "ndvi740"]
BANDS = ["b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12"]


class TrainingTransform:
    """Missing values, clipping and scaling are fitted on the designated training population only."""
    def fit(self, x):
        x = np.asarray(x, float).copy()
        x[~np.isfinite(x)] = np.nan
        empty = np.isnan(x).all(axis=0)
        x[:, empty] = 0.
        self.low, self.median, self.high = np.nanquantile(x, [.01, .5, .99], axis=0)
        clipped = np.clip(np.where(np.isnan(x), self.median, x), self.low, self.high)
        self.mean, self.scale = clipped.mean(axis=0), clipped.std(axis=0)
        self.scale[self.scale < 1e-12] = 1.
        return self

    def transform(self, x):
        x = np.asarray(x, float)
        x = np.where(np.isfinite(x), x, self.median)
        return (np.clip(x, self.low, self.high) - self.mean) / self.scale


def load_data(config):
    prior = prior_run(config)
    old = json.loads((prior / "manifest.json").read_text())
    for name, entry in old["outputs"].items():
        require(sha256(prior / name) == entry["sha256"], f"Prior output hash changed: {name}")
    for name, value in old["inputs"].items():
        require(sha256(ROOT / name) == value, f"Prior input changed: {name}")
    require(training_rows(old["config"]) == training_rows(config), "Prior merge run uses a different training-row rule")
    rows = pd.read_parquet(prior / "combined_data.parquet").set_index("obs_id").sort_index()
    require_training_rows(rows, config, "Prior combined table")
    audit = pd.read_csv(prior / "source_2024_audit.csv").set_index("obs_id")
    cuts = audit[["box1_yield_t_ha", "box2_yield_t_ha"]]
    audit["relative_cut_difference"] = (cuts.iloc[:, 0] - cuts.iloc[:, 1]).abs() / cuts.mean(axis=1).replace(0, np.nan)
    both_zero = cuts.eq(0).all(axis=1)
    audit.loc[both_zero, "relative_cut_difference"] = 0.
    rows["relative_cut_difference"] = audit.relative_cut_difference.reindex(rows.index)
    rows["quality_subset"] = (rows.n_cuts_observed.eq(2)
                              & rows.observed_months.ge(config["quality_min_months"])
                              & rows.relative_cut_difference.le(config["quality_max_relative_cut_difference"]))
    with duckdb.connect(str(ROOT / "data/cropyield.duckdb"), read_only=True) as con:
        con.register("chosen", rows.reset_index()[["obs_id", "season_year"]])
        monthly = con.execute("""SELECT b.*, v.ndvi,v.gcvi,v.mtci,v.ndvi705,v.ndvi740
            FROM monthly_bands b JOIN vegetation_indices v USING(obs_id,month) JOIN chosen c USING(obs_id)
            WHERE b.month >= CAST(c.season_year - 1 AS VARCHAR)||'-12'
            AND b.month <= CAST(c.season_year AS VARCHAR)||'-06' ORDER BY obs_id,month""").df()
        embeddings = con.execute("SELECT p.* FROM presto_embeddings p JOIN chosen USING(obs_id) ORDER BY obs_id").df()
    require(not monthly.duplicated(["obs_id", "month"]).any(), "Duplicate field-month")
    require(monthly.groupby("obs_id").size().eq(7).all(), "Incomplete monthly spine")
    monthly["calendar_month"] = monthly.month.str[-2:]
    temporal = monthly.pivot(index="obs_id", columns="calendar_month", values=BANDS + INDICES)
    temporal.columns = [f"{variable}_month_{month}" for variable, month in temporal.columns]
    masks = monthly.pivot(index="obs_id", columns="calendar_month", values="missing").astype(float)
    masks.columns = [f"missing_month_{month}" for month in masks.columns]
    require(embeddings.obs_id.is_unique and set(embeddings.obs_id) == set(rows.index), "Embedding IDs differ")
    presto = pd.DataFrame(np.stack(embeddings.embedding), index=embeddings.obs_id,
                          columns=[f"presto_{i:03}" for i in range(128)])
    features = {"seasonal": rows[FEATURES].copy(),
                "monthly": pd.concat([rows[FEATURES], temporal, masks], axis=1).reindex(rows.index),
                "presto": presto.reindex(rows.index),
                "coordinates": pd.DataFrame(unit_xyz(rows.lat.to_numpy(), rows.lon.to_numpy()), index=rows.index)}
    require(np.isfinite(features["presto"]).all().all(), "Nonfinite pretrained embeddings")
    memberships = pd.read_csv(prior / "target_memberships.csv", dtype={"group_id": str})
    permissions = pd.read_csv(prior / "source_spatial_permissions.csv")
    reserved = set(rows[rows.domain.eq("lacuna") & rows.fold.eq(0)].index)
    require(reserved.isdisjoint(memberships[memberships.role.ne("reserved")].obs_id), "Reserved target used")
    return rows, audit, features, memberships, permissions


def specifications(config):
    specs = []
    for family in config["feature_families"]:
        specs.extend([{"name": f"{family}_target", "family": family, "kind": "ridge", "select": "target"},
                      {"name": f"{family}_adaptive", "family": family, "kind": "adaptive", "select": "transfer"},
                      {"name": f"{family}_quality", "family": family, "kind": "adaptive", "policy": "quality", "select": "transfer"},
                      {"name": f"{family}_relevance", "family": family, "kind": "adaptive", "policy": "relevance", "select": "transfer"}])
    specs.extend([{"name": "monthly_tree_target", "family": "monthly", "kind": "tree", "select": "target"},
                  {"name": "monthly_tree_transfer", "family": "monthly", "kind": "tree", "select": "transfer"},
                  {"name": "monthly_source_signal", "family": "monthly", "kind": "signal", "select": "transfer"},
                  {"name": "coordinates_only", "family": "coordinates", "kind": "coordinates"}])
    for seed in config["shuffle_seeds"]:
        specs.append({"name": f"seasonal_shuffle_{seed}", "family": "seasonal", "kind": "adaptive", "policy": "shuffle", "policy_seed": seed})
    for seed in config["matched_subset_seeds"]:
        specs.append({"name": f"seasonal_matched_{seed}", "family": "seasonal", "kind": "adaptive", "policy": "matched", "policy_seed": seed})
    for fraction in config["learning_fractions"]:
        for kind in ["ridge", "adaptive"]:
            specs.append({"name": f"seasonal_{kind}_fraction_{fraction:g}", "family": "seasonal", "kind": kind, "fraction": fraction})
    return specs


def choose_target_groups(ids, rows, fraction, seed):
    if fraction == 1:
        return list(ids)
    groups = np.sort(rows.loc[ids].group_id.unique())
    selected = np.random.default_rng(seed).permutation(groups)[:max(2, int(np.ceil(len(groups)*fraction)))]
    return rows.loc[ids].index[rows.loc[ids].group_id.isin(selected)].tolist()


def source_mask(source, policy, seed):
    if policy == "quality":
        return source.quality_subset.to_numpy()
    if policy == "matched":
        rng = np.random.default_rng(seed)
        mask = np.zeros(len(source), bool)
        for zero in [False, True]:
            eligible = np.flatnonzero(source.yield_t_ha.eq(0).to_numpy() == zero)
            count = int((source.quality_subset & source.yield_t_ha.eq(0).eq(zero)).sum())
            if count:  # an include_primary pool has no zeros; drawing nothing must not touch the RNG
                mask[rng.choice(eligible, count, replace=False)] = True
        return mask
    return np.ones(len(source), bool)


def make_context(rows, features, fit_ids, source_ids, query_ids, spec, config):
    fit_ids = choose_target_groups(fit_ids, rows, spec.get("fraction", 1), config["seed"])
    policy = spec.get("policy", "all")
    source = rows.loc[source_ids]
    source = source.loc[source_mask(source, policy, spec.get("policy_seed", 0))]
    x = features[spec["family"]]
    if spec["kind"] == "coordinates":
        transform = lambda ids: x.loc[ids].to_numpy(float)
    else:
        fitted = TrainingTransform().fit(x.loc[fit_ids])
        transform = lambda ids: fitted.transform(x.loc[ids])
    data = {"xt": transform(fit_ids), "xs": transform(source.index), "xq": transform(query_ids),
            "yt": rows.loc[fit_ids].yield_t_ha.to_numpy(float), "ys": source.yield_t_ha.to_numpy(float),
            "weights": np.ones(len(source)), "fit_ids": fit_ids, "source_ids": source.index.tolist()}
    if policy == "shuffle":
        data["ys"] = np.random.default_rng(spec["policy_seed"]).permutation(data["ys"])
    if policy == "relevance" and len(source):
        classifier = LogisticRegression(C=1, max_iter=2000).fit(np.r_[data["xt"], data["xs"]],
                                        np.r_[np.ones(len(fit_ids)), np.zeros(len(source))])
        p = np.clip(classifier.predict_proba(data["xs"])[:, 1], 1e-6, 1-1e-6)
        data["weights"] = np.clip(p/(1-p)*len(source)/len(fit_ids), *config["domain_weight_clip"])
    if spec["kind"] == "signal":
        require(len(source) > 0, "Source signal requires auxiliary rows")
        teacher = HistGradientBoostingRegressor(max_iter=config["tree_iterations"], max_leaf_nodes=15,
                    min_samples_leaf=20, l2_regularization=1, learning_rate=.05, early_stopping=False, random_state=config["seed"])
        teacher.fit(data["xs"], data["ys"])
        train_signal, query_signal = teacher.predict(data["xt"]), teacher.predict(data["xq"])
        mu, sd = train_signal.mean(), max(train_signal.std(), 1e-12)
        data["xt"] = np.c_[data["xt"], (train_signal-mu)/sd]
        data["xq"] = np.c_[data["xq"], (query_signal-mu)/sd]
    return data


def parameter_grid(spec, config):
    kind = spec["kind"]
    if kind == "coordinates":
        return [{}]
    ratios = config["source_ratios"] if kind == "adaptive" or (kind == "tree" and spec.get("select") == "transfer") else [0]
    key, grid = ("leaves", config["tree_leaf_nodes"]) if kind == "tree" else ("alpha", config["alphas"])
    return [{key: value, "ratio": ratio} for ratio, value in itertools.product(ratios, grid)]


def predict(data, kind, params, config):
    xt, xs, xq, yt, ys, sw = (data[k] for k in ["xt", "xs", "xq", "yt", "ys", "weights"])
    ratio = params.get("ratio", 0)
    transfer = ratio > 0 and len(xs) > 0
    if kind == "coordinates":
        result = KNeighborsRegressor(n_neighbors=min(10, len(yt)), weights="distance").fit(xt, yt).predict(xq)
    elif kind == "tree":
        x, y, weight = np.c_[xt, np.zeros(len(xt))], yt, np.ones(len(yt))
        if transfer:
            x, y = np.r_[x, np.c_[xs, np.ones(len(xs))]], np.r_[yt, ys]
            weight = np.r_[weight, sw/sw.sum()*len(yt)*ratio]
        model = HistGradientBoostingRegressor(max_iter=config["tree_iterations"], max_leaf_nodes=params["leaves"],
                    min_samples_leaf=20, learning_rate=.05, l2_regularization=1, early_stopping=False, random_state=config["seed"])
        result = model.fit(x, y, sample_weight=weight).predict(np.c_[xq, np.zeros(len(xq))])
    elif kind != "adaptive" or not transfer:
        result = Ridge(alpha=params["alpha"]).fit(xt, yt).predict(xq)
    else:
        mt, ms = yt.mean(), np.average(ys, weights=sw)
        st, ss = max(yt.std(), 1e-12), max(float(np.sqrt(np.average((ys-ms)**2, weights=sw))), 1e-12)
        ct, cs = xt.mean(axis=0), np.average(xs, axis=0, weights=sw)
        zt, zs, zq = xt-ct, xs-cs, xq-ct
        x = np.r_[np.c_[zt, zt, np.zeros_like(zt)], np.c_[zs, np.zeros_like(zs), zs]]/np.sqrt(2)
        q = np.c_[zq, zq, np.zeros_like(zq)]/np.sqrt(2)
        y = np.r_[(yt-mt)/st, (ys-ms)/ss]
        weights = np.r_[np.ones(len(yt)), sw/sw.sum()*len(yt)*ratio]
        result = mt+st*Ridge(alpha=params["alpha"], fit_intercept=False).fit(x, y, sample_weight=weights).predict(q)
    return np.maximum(result, 0)


def reference_for(name):
    if name == "transfer_selector":
        return "target_selector"
    if "fraction" in name:
        return name.replace("adaptive", "ridge")
    if name.startswith("monthly_tree"):
        return "monthly_tree_target"
    if name.startswith("monthly"):
        return "monthly_target"
    if name.startswith("presto"):
        return "presto_target"
    return "seasonal_target"


def run_target_models(rows, features, membership, permission, config):
    specs = specifications(config)
    all_predictions, selected, tuning, accounting = [], [], [], []
    for outer in config["target_folds"]:
        part = membership[membership.outer_fold.eq(outer)]
        query_ids = part[part.inner_fold.eq(0) & part.role.eq("evaluation")].obs_id.tolist()
        truths, index = [], []
        for inner in range(4):
            m = part[part.inner_fold.eq(inner)]
            fit_ids = m[m.role.eq("fit")].obs_id.tolist()
            val_ids = query_ids if inner == 0 else m[m.role.eq("validation")].obs_id.tolist()
            allowed = permission[permission.outer_fold.eq(outer) & permission.inner_fold.eq(inner) & permission.allowed_by_spatial_rule]
            require(rows.loc[fit_ids].fold.ne(0).all() and rows.loc[val_ids].fold.ne(0).all(), "Fold zero exposure")
            require(set(rows.loc[fit_ids].group_id).isdisjoint(rows.loc[val_ids].group_id), "Target spatial group leakage")
            require(allowed.minimum_distance_to_protected_km.ge(config["buffer_km"]).all(), "Source buffer failure")
            require_training_rows(rows.loc[fit_ids + allowed.obs_id.tolist()], config, f"Fit pool {outer}/{inner}")
            index.append((fit_ids, allowed.obs_id.tolist(), val_ids))
            if inner:
                truths.append(rows.loc[val_ids].yield_t_ha.to_numpy())
        truth = np.concatenate(truths)
        outcomes = {}
        context_cache = {}
        for spec in specs:
            cache_key = (spec["family"], spec.get("policy", "all"), spec.get("policy_seed", 0),
                         spec.get("fraction", 1), spec["kind"] == "signal")
            if cache_key not in context_cache:
                context_cache[cache_key] = [make_context(rows, features, *indices, spec, config) for indices in index]
            contexts = context_cache[cache_key]
            trials = []
            for params in parameter_grid(spec, config):
                pred = np.concatenate([predict(data, spec["kind"], params, config) for data in contexts[1:]])
                loss = float(np.mean((truth-pred)**2))
                trials.append((loss, params))
                tuning.append({"outer_fold": outer, "method": spec["name"], **params, "inner_rmse_t_ha": np.sqrt(loss)})
            loss, best = min(trials, key=lambda v: v[0])
            pred = predict(contexts[0], spec["kind"], best, config)
            uses_source = spec["kind"] == "signal" or best.get("ratio", 0) > 0
            record = {"outer_fold": outer, "method": spec["name"], "chosen_method": spec["name"], **best,
                      "inner_rmse_t_ha": np.sqrt(loss), "n_target_train": len(contexts[0]["yt"]),
                      "source_available": len(contexts[0]["ys"]), "source_used": len(contexts[0]["ys"]) if uses_source else 0}
            selected.append(record)
            outcomes[spec["name"]] = {"loss": loss, "prediction": pred, "spec": spec, "record": record}
            for inner, data in enumerate(contexts):
                accounting.append({"outer_fold": outer, "inner_fold": inner, "method": spec["name"],
                                   "n_target": len(data["yt"]), "n_source": len(data["ys"]),
                                   "n_source_zero": int((data["ys"] == 0).sum()),
                                   "source_effective_n": float(data["weights"].sum()**2/np.sum(data["weights"]**2)) if len(data["ys"]) else 0,
                                   "target_ids_sha256": hashlib.sha256("|".join(data["fit_ids"]).encode()).hexdigest(),
                                   "source_ids_sha256": hashlib.sha256("|".join(data["source_ids"]).encode()).hexdigest()})
            print(f"target fold {outer} {spec['name']}: inner RMSE {np.sqrt(loss):.4f}; {best}", flush=True)
        for selector in ["target_selector", "transfer_selector"]:
            allowed = [v for v in outcomes.values() if v["spec"].get("select") == "target"
                       or (selector == "transfer_selector" and v["spec"].get("select") == "transfer")]
            chosen = min(allowed, key=lambda v: v["loss"])
            selected.append({**chosen["record"], "method": selector})
            outcomes[selector] = {**chosen, "spec": {"name": selector}}
        for name, outcome in outcomes.items():
            all_predictions.append(pd.DataFrame({"obs_id": query_ids, "group_id": rows.loc[query_ids].group_id.to_numpy(),
                    "outer_fold": outer, "method": name, "yield_t_ha": rows.loc[query_ids].yield_t_ha.to_numpy(),
                    "prediction_t_ha": outcome["prediction"]}))
    return pd.concat(all_predictions, ignore_index=True), pd.DataFrame(tuning), pd.DataFrame(selected), pd.DataFrame(accounting)


def paired_metrics(predictions, config):
    metrics, folds = [], []
    for name, part in predictions.groupby("method", sort=False):
        require(part.obs_id.is_unique and len(part) == 1504 and part.outer_fold.ne(0).all(), "Invalid target evaluation population")
        metrics.append({"method": name, "reference": reference_for(name), "n": len(part),
                        **score_predictions(part.yield_t_ha.to_numpy(), part.prediction_t_ha.to_numpy())})
        for fold, one in part.groupby("outer_fold"):
            folds.append({"method": name, "fold": fold, **score_predictions(one.yield_t_ha.to_numpy(), one.prediction_t_ha.to_numpy())})
    wide = predictions.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()
    truth = predictions[predictions.method.eq("seasonal_target")].set_index("obs_id").loc[wide.index]
    require(wide.notna().all().all(), "Unequal evaluation IDs")
    groups = truth.group_id.to_numpy()
    members = [np.flatnonzero(groups == group) for group in np.unique(groups)]
    rng = np.random.default_rng(config["seed"])
    draws = [np.concatenate([members[i] for i in rng.integers(len(members), size=len(members))])
             for _ in range(config["bootstrap_draws"])]
    comparisons = [(name, reference_for(name)) for name in wide.columns]
    comparisons += [("transfer_selector", "seasonal_target"), ("presto_target", "seasonal_target"),
                    ("monthly_target", "seasonal_target")]
    comparisons += [("seasonal_adaptive", f"seasonal_shuffle_{seed}") for seed in config["shuffle_seeds"]]
    comparisons += [("seasonal_quality", f"seasonal_matched_{seed}") for seed in config["matched_subset_seeds"]]
    differences = []
    y = truth.yield_t_ha.to_numpy()
    for name, reference in comparisons:
        e, base = (wide[name].to_numpy()-y)**2, (wide[reference].to_numpy()-y)**2
        values = [np.sqrt(e[ix].mean()) - np.sqrt(base[ix].mean()) for ix in draws]
        low, high = np.quantile(values, [.025, .975])
        differences.append({"method": name, "reference": reference, "delta_rmse_t_ha": np.sqrt(e.mean())-np.sqrt(base.mean()),
                            "ci_low": low, "ci_high": high,
                            "primary_comparison": name == config["primary_method"] and reference == config["primary_reference"]})
    return pd.DataFrame(metrics), pd.DataFrame(folds), pd.DataFrame(differences)


def quality_and_error_audit(rows, audit, features, prior=PRIOR):
    summaries, correlations = [], []
    for name, part in rows[rows.domain.ne("lacuna") | rows.fold.ne(0)].groupby("domain"):
        y = part.yield_t_ha
        summaries.append({"domain": name, "n": len(part), "mean_t_ha": y.mean(), "std_t_ha": y.std(),
                          "median_t_ha": y.median(), "zero_share": y.eq(0).mean(), "q90_t_ha": y.quantile(.9),
                          "mean_observed_months": part.observed_months.mean(),
                          "repeated_coordinate_rows": int(part.duplicated(["lat", "lon"], keep=False).sum()),
                          "feature_eligible": int(part.feature_eligible.sum()), "quality_subset": int(part.quality_subset.sum())})
        for feature in FEATURES:
            value = features["seasonal"].loc[part.index, feature]
            correlations.append({"domain": name, "feature": feature, "spearman_yield": spearmanr(value, y).statistic,
                                 "mean": value.mean(), "median": value.median(), "std": value.std()})
    cuts = audit[audit.label_eligible & audit.n_cuts_observed.eq(2)]
    positive = cuts[cuts.yield_t_ha.gt(0)]
    quality = {"two_cut_n": len(cuts), "two_cut_positive_n": len(positive),
               "box_pearson_all": cuts.box1_yield_t_ha.corr(cuts.box2_yield_t_ha),
               "box_pearson_positive": positive.box1_yield_t_ha.corr(positive.box2_yield_t_ha),
               "positive_median_relative_difference": positive.relative_cut_difference.median(),
               "positive_relative_difference_gt_1": int(positive.relative_cut_difference.gt(1).sum()),
               "positive_exactly_equal_cuts": int(positive.box1_yield_t_ha.eq(positive.box2_yield_t_ha).sum()),
               "missing_labels": int(audit.yield_t_ha.isna().sum()),
               "recorded_zeros": int(audit[audit.label_eligible].yield_t_ha.eq(0).sum())}
    old_predictions = pd.read_csv(prior / "predictions.csv")
    decomposition = []
    for method, part in old_predictions.groupby("method"):
        e = part.prediction_t_ha - part.yield_t_ha
        decomposition.append({"method": method, "mse": np.mean(e**2), "squared_bias": e.mean()**2,
                              "centered_error_variance": e.var(ddof=0), "bias": e.mean()})
    decomp = pd.DataFrame(decomposition).set_index("method")
    quality["naive_excess_mse_share_from_squared_bias"] = float(
        (decomp.loc["pooled_naive", "squared_bias"]-decomp.loc["lacuna_only", "squared_bias"])
        /(decomp.loc["pooled_naive", "mse"]-decomp.loc["lacuna_only", "mse"]))
    return pd.DataFrame(summaries), pd.DataFrame(correlations), quality, decomp.reset_index()


def domain_separability(rows, features):
    use = rows[(rows.domain.ne("lacuna") | rows.fold.ne(0)) & rows.feature_eligible].copy()
    groups = connected_clusters(use.lat.to_numpy(), use.lon.to_numpy(), 2.)
    y = use.domain.eq("lacuna").to_numpy(int)
    results = []
    for family, x in features.items():
        probabilities = np.full(len(use), np.nan)
        for fit, val in GroupKFold(3).split(use, groups=groups):
            transformer = TrainingTransform().fit(x.loc[use.index[fit]])
            model = LogisticRegression(C=1, max_iter=2000, class_weight="balanced")
            model.fit(transformer.transform(x.loc[use.index[fit]]), y[fit])
            probabilities[val] = model.predict_proba(transformer.transform(x.loc[use.index[val]]))[:, 1]
        results.append({"feature_family": family, "n": len(use), "source_target_auc": roc_auc_score(y, probabilities),
                        "cv_groups": len(np.unique(groups))})
    return pd.DataFrame(results)


def source_predictability(rows, features, config):
    filename = "zimbabwe_2024__s1_cc2km.csv"
    path = ROOT / "data/splits" / filename
    pinned = json.loads((ROOT / "data/splits/manifest.json").read_text())
    require(sha256(path) == pinned["files"][filename]["sha256"], "Source frozen split hash changed")
    old_split = pd.read_csv(path)
    original_reserved = old_split[old_split.fold.eq(0)].obs_id.tolist()
    protected = pd.concat([rows.loc[original_reserved], rows[rows.domain.eq("lacuna") & rows.fold.eq(0)]])
    source, distances = purge_source(rows[rows.domain.eq("zimbabwe_2024") & rows.feature_eligible], protected, config["buffer_km"])
    source = source.copy()
    require_training_rows(source, config, "Source learnability pool")
    source["group_id"] = connected_clusters(source.lat.to_numpy(), source.lon.to_numpy(), 2.).astype(str)
    require(set(original_reserved).isdisjoint(source.index), "Source fold zero exposed")
    outputs, selections, assignment = [], [], []
    source_specs = [{"name": f"{f}_ridge", "family": f, "kind": "ridge"} for f in config["feature_families"]]
    source_specs += [{"name": "monthly_tree", "family": "monthly", "kind": "tree"},
                     {"name": "coordinates", "family": "coordinates", "kind": "coordinates"}]
    for outer, (fit, val) in enumerate(GroupKFold(4).split(source, groups=source.group_id), 1):
        train, evaluation = source.iloc[fit], source.iloc[val]
        assignment.append(pd.DataFrame({"obs_id": evaluation.index, "diagnostic_fold": outer, "group_id": evaluation.group_id.to_numpy()}))
        means = np.full(len(evaluation), train.yield_t_ha.mean())
        outputs.append(pd.DataFrame({"obs_id": evaluation.index, "fold": outer, "method": "training_mean",
                                     "yield_t_ha": evaluation.yield_t_ha.to_numpy(), "prediction_t_ha": means}))
        for spec in source_specs:
            contexts, inner_y = [], []
            for inner_fit, inner_val in GroupKFold(3).split(train, groups=train.group_id):
                a, b = train.iloc[inner_fit], train.iloc[inner_val]
                contexts.append(make_context(rows, features, a.index.tolist(), [], b.index.tolist(), spec, config))
                inner_y.append(b.yield_t_ha.to_numpy())
            truth = np.concatenate(inner_y)
            choices = []
            for params in parameter_grid(spec, config):
                pred = np.concatenate([predict(context, spec["kind"], params, config) for context in contexts])
                choices.append((np.mean((pred-truth)**2), params))
            loss, best = min(choices, key=lambda v: v[0])
            context = make_context(rows, features, train.index.tolist(), [], evaluation.index.tolist(), spec, config)
            pred = predict(context, spec["kind"], best, config)
            outputs.append(pd.DataFrame({"obs_id": evaluation.index, "fold": outer, "method": spec["name"],
                                         "yield_t_ha": evaluation.yield_t_ha.to_numpy(), "prediction_t_ha": pred}))
            selections.append({"fold": outer, "method": spec["name"], **best, "inner_rmse_t_ha": np.sqrt(loss)})
        print(f"source learnability fold {outer} complete: {len(train)} fit / {len(evaluation)} evaluation", flush=True)
    predictions = pd.concat(outputs, ignore_index=True)
    results = []
    for name, part in predictions.groupby("method"):
        # Zero/positive ranking is undefined for an include_primary pool, which holds no zeros.
        both = part.yield_t_ha.gt(0).nunique() == 2
        results.append({"method": name, "n": len(part), **score_predictions(part.yield_t_ha.to_numpy(), part.prediction_t_ha.to_numpy()),
                        "nonzero_auc": roc_auc_score(part.yield_t_ha.gt(0), part.prediction_t_ha) if both else np.nan})
    info = {"original_source_reserved_n": len(original_reserved), "source_diagnostic_n": len(source),
            "source_diagnostic_groups": source.group_id.nunique(), "source_zero_share": source.yield_t_ha.eq(0).mean(),
            "source_excluded_by_reserved_buffer": int((distances < config["buffer_km"]).sum())}
    return predictions, pd.DataFrame(results), pd.DataFrame(selections), pd.concat(assignment, ignore_index=True), info


def plot_diagnosis(path, metrics, differences, decomposition, source_metrics):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), layout="constrained")
    error = decomposition.set_index("method").loc[["lacuna_only", "pooled_naive", "pooled_adaptive"]]
    names = ["Lacuna only", "Naive pooling", "Adaptive pooling"]
    axes[0, 0].bar(names, error.centered_error_variance, label="Centered error variance", color="#4779aa")
    axes[0, 0].bar(names, error.squared_bias, bottom=error.centered_error_variance, label="Squared bias", color="#d9853b")
    axes[0, 0].set(title="Why naive pooling worsened", ylabel="Mean squared error (t/ha)²")
    axes[0, 0].legend()
    indexed = metrics.set_index("method")
    x = np.arange(3)
    families = ["seasonal", "monthly", "presto"]
    for offset, kind, label, color in [(-.18, "target", "Lacuna only", "#4779aa"), (.18, "adaptive", "With 2024", "#168373")]:
        axes[0, 1].bar(x+offset, [indexed.loc[f"{f}_{kind}", "rmse_t_ha"] for f in families], .35, label=label, color=color)
    axes[0, 1].set(xticks=x, xticklabels=["Seasonal indices", "Monthly bands/indices", "Frozen Presto"],
                   ylabel="Target RMSE (t/ha); lower is better", title="Representation versus extra source data")
    axes[0, 1].legend()
    chosen = ["seasonal_adaptive", "monthly_adaptive", "presto_adaptive", "monthly_source_signal", "transfer_selector"]
    pairs = differences[(differences.method.isin(chosen)) &
                        (differences.reference == differences.method.map(reference_for))].set_index("method")
    for i, name in enumerate(chosen):
        row = pairs.loc[name]
        axes[1, 0].plot([row.ci_low, row.ci_high], [i, i], color="#4779aa", lw=2)
        axes[1, 0].plot(row.delta_rmse_t_ha, i, "o", color="#168373")
    axes[1, 0].axvline(0, color="gray", lw=1)
    axes[1, 0].set(yticks=range(len(chosen)), yticklabels=["Seasonal adaptive", "Monthly adaptive", "Presto adaptive", "Source nonlinear signal", "Nested selector (primary)"],
                   xlabel="ΔRMSE versus matched target-only reference (t/ha)", title="Paired 95% group-bootstrap intervals")
    sm = source_metrics.set_index("method").loc[["training_mean", "seasonal_ridge", "monthly_ridge", "presto_ridge", "monthly_tree", "coordinates"]]
    axes[1, 1].barh(["Training mean", "Seasonal Ridge", "Monthly Ridge", "Presto Ridge", "Monthly trees", "Coordinates"], sm.r2, color="#4779aa")
    axes[1, 1].axvline(0, color="gray", lw=1)
    axes[1, 1].set(xlabel="Within-2024 spatial CV R²", title="Is source yield learnable in its own population?")
    fig.suptitle("Zimbabwe transfer diagnosis · exploratory development results\nNo fitting/scoring of reserved fold 0", fontsize=15)
    fig.savefig(path, dpi=160, metadata={"Software": "cropyield transfer diagnosis"})
    plt.close(fig)


def write_results(path, metrics, differences, quality, shifts, source_metrics, selected, summary, config=None):
    config = config or {}
    legacy = training_rows(config) == "all_screened"
    title = "Why pooling Zimbabwe data added little: diagnostic results" if legacy else "Zimbabwe transfer diagnosis: results"
    rule_text = "" if legacy else f"""
Training rows follow `labels_v1.include_primary` (config `training_rows`). Rows, memberships and source permissions
come from `{config.get('merge_run')}`, so the 2024 pool holds no recorded zeros. The source-quality statistics
below still describe all screened 2024 records, zeros included; they are data checks, not training rows.
"""
    primary = differences[differences.primary_comparison].iloc[0]
    rows = [f"| {r.method} | {r.rmse_t_ha:.4f} | {r.mae_t_ha:.4f} | {r.r2:.3f} | {r.reference} |" for _, r in metrics.iterrows()]
    source_rows = [f"| {r.method} | {r.rmse_t_ha:.4f} | {r.r2:.3f} | {r.spearman:.3f} | {r.nonzero_auc:.3f} |" for _, r in source_metrics.iterrows()]
    selector_rows = [f"| {int(r.outer_fold)} | {r.method} | {r.chosen_method} | {int(r.source_used)} |"
                     for _, r in selected[selected.method.isin(["target_selector", "transfer_selector"])].iterrows()]
    shift_text = ", ".join(f"{r.feature_family}: {r.source_target_auc:.3f}" for _, r in shifts.iterrows())
    text = f"""# {title}
{rule_text}
## Primary nested comparison

Transfer selector minus target-only selector ΔRMSE: **{primary.delta_rmse_t_ha:+.4f} t/ha**;
paired 95% spatial-group interval **[{primary.ci_low:+.4f}, {primary.ci_high:+.4f}]**.
All target scores use the same 1,504 Lacuna 2023 development fields. Each selector chooses its method using only
inner validation within the outer training set. This follow-up is informed by the first experiment; it is exploratory,
not a new blind test. Both target and source historical fold-0 outcomes remain unscored.

## Evidence about the cause

- **{quality['naive_excess_mse_share_from_squared_bias']:.1%} of naive pooling's extra MSE is accounted for by the increase
  in squared bias.** This is the identity MSE = squared mean error + centered error variance, not a proposed correction
  fitted using held-out labels. See `error_decomposition.csv`.
- The source's two-cut correlation is **{quality['box_pearson_all']:.3f}** across all paired rows and
  **{quality['box_pearson_positive']:.3f}** among positive fields. Both-zero agreement alone is not evidence of reliability.
  **{quality['positive_relative_difference_gt_1']} / {quality['two_cut_positive_n']}** positive paired records exceed the
  relative-difference threshold of 1. Agreement cannot detect shared recording errors or verify moisture equivalence.
- Source-versus-target classifier AUC (three spatial folds; chance 0.5): **{shift_text}**. Distinguishability measures
  distribution shift, not label quality. The year, sampling frame and provider protocol remain confounded.
- The source learnability diagnostic uses **{summary['source_diagnostic_n']}** fields after removing old source fold 0 and
  neighbours, and protecting target fold 0. Its task difficulty/distribution differs from target prediction; compare its
  models with the source training mean rather than directly comparing source and target RMSE.

## All target results (lower RMSE is better)

| Method | RMSE t/ha | MAE t/ha | R² | Matched reference |
|---|---:|---:|---:|---|
{chr(10).join(rows)}

Every paired interval is in `paired_differences.csv`; within-fold metrics are in `fold_metrics.csv`.
The five shuffle seeds and three random matched subsets are all reported; none is chosen as the best control.
Shuffles destroy source feature-label pairing while retaining marginal outcomes. A transfer gain similar to shuffled
controls can arise from regularization rather than useful source relationships. Five shuffles are not a formal test.
Quality subsets may alter the population; matched controls preserve their size and zero/positive composition.

## What each selector actually used

| Outer fold | Selector | Inner-selected model | Source training rows used |
|---:|---|---|---:|
{chr(10).join(selector_rows)}

A zero source count means that fold selected target-only fitting. Do not attribute a better representation's benefit
to adding source data. Compare each feature family's adaptation with its own target-only baseline.

## Learnability within 2024

| Source diagnostic model | RMSE t/ha | R² | Spearman | Nonzero-ranking AUC |
|---|---:|---:|---:|---:|
{chr(10).join(source_rows)}

Models use grouped outer validation with inner tuning. Positive/zero ranking uses predicted yield as the ranking
score; it is not a calibrated probability. Original source fold-0 IDs and any points within 2 km are excluded from
this diagnostic. Its new folds do not restore blindness to historically explored source observations.

## Scope and reproducibility

The complete design and interpretation limits are in `PROTOCOL.md`. Only training observations determine imputation,
clipping, scaling, outcome calibration, density weights, source teacher models and hyperparameters. Source permissions
and target membership are inherited from the hash-verified first release. The full catalog and source observations
are preserved; quality masks are experimental training policies, not permanent deletion decisions.

Common-window monthly features contain 122 predictors (10 seasonal statistics, 105 month/band/index values and seven
missing-scene masks). Presto uses 128 existing frozen whole-window embeddings; it has different window/mask conventions
and is not an otherwise identical monthly representation. No new imagery was downloaded and the database was read-only.

Run `python scripts/step10_diagnose_zimbabwe_transfer.py{"" if legacy else " --config configs/" + config.get("experiment", "") + ".json"}` from the repository root. Input/code/config/output hashes
and library versions are in `manifest.json`. Use a new `--output` directory for intentional changes.

Files include: `quality_summary.json`, `cohort_summary.csv`, `feature_correlations.csv`, `domain_separability.csv`,
`row_quality.csv`, `error_decomposition.csv`, `source_predictions.csv`, `source_metrics.csv`, `source_splits.csv`,
`source_selected_parameters.csv`, `target_memberships.csv`, `source_spatial_permissions.csv`, `fit_accounting.csv`,
`predictions.csv`, `metrics.csv`, `fold_metrics.csv`, `paired_differences.csv`, `tuning.csv`, `selected_parameters.csv`,
`features_monthly.parquet`, `features_presto.parquet` and `feature_dictionary.json`.

![Diagnosis](diagnosis.png)
"""
    path.write_text(text, encoding="utf-8")


def input_hashes(config_path, prior=PRIOR):
    paths = [Path(__file__), ROOT / "scripts/step10_diagnose_zimbabwe_transfer.py",
             ROOT / "docs/ZIMBABWE_TRANSFER_DIAGNOSIS_PROTOCOL.md", ROOT / "data/cropyield.duckdb",
             ROOT / "data/splits/zimbabwe_2024__s1_cc2km.csv", ROOT / "requirements.txt"]
    paths += list(prior.iterdir())
    paths += [ROOT / p for p in ["src/cropyield/experiments/zimbabwe_merge.py", "src/cropyield/eval/splits.py",
                               "src/cropyield/data/xy.py", "src/cropyield/data/handoff.py", "src/cropyield/data/labels.py"]]
    paths.append(config_path)
    return {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha256(p) for p in paths if p.is_file()}


def run_diagnosis(output=OUTPUT, config_path=CONFIG):
    config = json.loads(config_path.read_text())
    require(config["target_folds"] == [1, 2, 3, 4] and config["reserved_fold"] == 0, "Reserved folds cannot change")
    prior = prior_run(config)
    before = input_hashes(config_path, prior)
    rows, audit, features, membership, permission = load_data(config)
    with threadpool_limits(limits=1):
        cohorts, feature_correlations, quality, decomposition = quality_and_error_audit(rows, audit, features, prior)
        shifts = domain_separability(rows, features)
        print("Quality and distribution audit complete", flush=True)
        predictions, tuning, selected, accounting = run_target_models(rows, features, membership, permission, config)
        metrics, folds, differences = paired_metrics(predictions, config)
        source_predictions, source_metrics, source_selected, source_splits, summary = source_predictability(rows, features, config)
    # The seasonal controls must independently reproduce the original experiment's predictions.
    prior_predictions = pd.read_csv(prior / "predictions.csv")
    for current, old in [("seasonal_target", "lacuna_only"), ("seasonal_adaptive", "pooled_adaptive")]:
        a = predictions[predictions.method.eq(current)].set_index("obs_id").prediction_t_ha.sort_index()
        b = prior_predictions[prior_predictions.method.eq(old)].set_index("obs_id").prediction_t_ha.sort_index()
        require(a.index.equals(b.index) and np.allclose(a, b, rtol=0, atol=1e-9), f"Original baseline not reproduced: {current}")
    with tempfile.TemporaryDirectory(prefix="zimbabwe-diagnosis-") as tmp:
        staged = Path(tmp)
        tables = {"cohort_summary": cohorts, "feature_correlations": feature_correlations, "domain_separability": shifts,
                  "error_decomposition": decomposition, "row_quality": rows.reset_index(), "predictions": predictions,
                  "tuning": tuning, "selected_parameters": selected, "fit_accounting": accounting, "metrics": metrics,
                  "fold_metrics": folds, "paired_differences": differences, "source_predictions": source_predictions,
                  "source_metrics": source_metrics, "source_selected_parameters": source_selected, "source_splits": source_splits,
                  "target_memberships": membership, "source_spatial_permissions": permission}
        for name, table in tables.items():
            csv_write(table, staged / f"{name}.csv")
        for family in ["monthly", "presto"]:
            features[family].to_parquet(staged / f"features_{family}.parquet", index=True)
        json_write({f: list(x.columns) for f, x in features.items()}, staged / "feature_dictionary.json")
        json_write(quality, staged / "quality_summary.json")
        json_write(summary, staged / "source_diagnostic_summary.json")
        (staged / "PROTOCOL.md").write_text((ROOT / "docs/ZIMBABWE_TRANSFER_DIAGNOSIS_PROTOCOL.md").read_text(), encoding="utf-8")
        write_results(staged / "RESULTS.md", metrics, differences, quality, shifts, source_metrics, selected, summary, config)
        plot_diagnosis(staged / "diagnosis.png", metrics, differences, decomposition, source_metrics)
        require(before == input_hashes(config_path, prior), "Inputs changed during the run")
        manifest = {"config": config, "inputs": before, "python": platform.python_version(),
                    "versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "scikit-learn", "duckdb", "pyarrow", "matplotlib"]},
                    "outputs": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted(staged.iterdir())}}
        json_write(manifest, staged / "manifest.json")
        publish_release(staged, output)
    print(metrics.round(4).to_string(index=False), flush=True)
    print(differences[differences.primary_comparison].round(5).to_string(index=False), flush=True)
    print(source_metrics.round(4).to_string(index=False), flush=True)
    return metrics
