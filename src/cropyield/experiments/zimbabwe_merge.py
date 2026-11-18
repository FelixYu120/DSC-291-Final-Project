"""Compatibility audit and nested spatial comparison of Lacuna vs Lacuna + Zimbabwe 2024."""
from __future__ import annotations

import importlib.metadata
import itertools
import json
import platform
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from cropyield import ROOT
from cropyield.data.handoff import (
    COHORT,
    csv_write,
    json_write,
    publish_release,
    read_raw,
    reconcile_labels,
    require,
    verify_inputs,
)
from cropyield.data.labels import sha256
from cropyield.data.xy import FEATURES
from cropyield.eval.splits import EARTH_RADIUS_KM, unit_xyz

AUXILIARY = "zimbabwe_2024"
CONFIG = ROOT / "configs/zimbabwe_merge_v1.json"
OUTPUT = ROOT / "data/runs/zimbabwe_merge_v1"
# "all_screened" is the v1 legacy pool (every audited 2024 row, recorded zeros included); it trains on rows
# the team excludes. "include_primary" follows labels_v1.include_primary, the team rule. Absent key = v1.
TRAINING_ROWS = ("all_screened", "include_primary")
ZERO_POLICY_METHODS = ("pooled_positive_sensitivity", "pooled_zero_weight_sensitivity")


def training_rows(config: dict) -> str:
    rule = config.get("training_rows", "all_screened")
    require(rule in TRAINING_ROWS, f"Unknown training_rows rule: {rule}")
    return rule


def require_training_rows(frame: pd.DataFrame, config: dict, what: str = "training pool") -> None:
    """Under the team rule, every row that can enter a fit must have labels_v1.include_primary = True."""
    if training_rows(config) == "include_primary":
        require("include_primary" in frame.columns and frame["include_primary"].eq(True).all(),
                f"{what} holds rows outside labels_v1.include_primary")


def default_output(config: dict) -> Path:
    return ROOT / "data/runs" / config["experiment"]


def audit_2024(path: Path) -> pd.DataFrame:
    """Keep true missing yields separate from recorded zeros; verify available crop-cut boxes."""
    frame = pd.read_csv(path, dtype={"cce_id": str})
    frame["source_row"] = np.arange(len(frame)) + 2
    keep = (frame.country.str.lower().eq("zimbabwe") & frame.data_collection_year.eq(2024)
            & frame.crop.str.lower().str.contains("maize|corn", regex=True))
    frame = frame.loc[keep].copy()
    require(frame.cce_id.notna().all() and frame.cce_id.is_unique, "2024 IDs missing or duplicated")
    out = pd.DataFrame({"obs_id": "vision_guided_yield_estimation:" + frame.cce_id,
                        "source_id": frame.cce_id, "source_row": frame.source_row,
                        "lat": pd.to_numeric(frame.latitude, errors="coerce"),
                        "lon": pd.to_numeric(frame.longitude, errors="coerce"),
                        "yield_t_ha": pd.to_numeric(frame.Avg_yield_mt_ha, errors="coerce"),
                        "box_used_raw": frame["Box used"]})
    for box in [1, 2]:
        for dst, src in [("dry_kg", f"box{box}_dry_weight_confirmation"),
                         ("wet_kg", f"box{box}_wet_weight_confirmation"),
                         ("yield_t_ha", f"box{box}_into_mt_ha")]:
            out[f"box{box}_{dst}"] = pd.to_numeric(frame[src], errors="coerce")
    out["n_cuts_observed"] = out[["box1_yield_t_ha", "box2_yield_t_ha"]].notna().sum(axis=1)
    out["recomputed_yield_t_ha"] = out[["box1_yield_t_ha", "box2_yield_t_ha"]].mean(axis=1)
    out["outcome_status"] = np.where(out.yield_t_ha.isna(), "missing",
                                     np.where(out.yield_t_ha.eq(0), "recorded_zero", "recorded_positive"))
    flags = {
        "missing_yield": out.yield_t_ha.isna(),
        "invalid_yield": ~np.isfinite(out.yield_t_ha) | ~out.yield_t_ha.between(0, 15),
        "invalid_location": ~out.lon.between(25.1, 33.1) | ~out.lat.between(-22.5, -15.5),
        "no_used_cut": out.n_cuts_observed.eq(0),
        "average_mismatch": ~np.isclose(out.yield_t_ha, out.recomputed_yield_t_ha, rtol=0, atol=1e-6),
    }
    for box in [1, 2]:
        dry, wet, y = (out[f"box{box}_{v}"] for v in ["dry_kg", "wet_kg", "yield_t_ha"])
        used = y.notna()
        flags[f"box{box}_invalid_used_cut"] = used & (~np.isfinite(dry) | dry.lt(0) | ~np.isfinite(y) | y.lt(0))
        flags[f"box{box}_conversion_mismatch"] = used & ~np.isclose(y, dry * .25, rtol=0, atol=1e-6)
        flags[f"box{box}_dry_above_wet"] = dry.notna() & wet.notna() & dry.gt(wet)
    out = out.reset_index(drop=True)
    flags = {name: np.asarray(value) for name, value in flags.items()}
    out["exclusion_reason"] = [";".join(name for name, mask in flags.items() if mask[i]) for i in range(len(out))]
    out["label_eligible"] = out.exclusion_reason.eq("")
    return out


def prepare_data(root: Path, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    database = root / "data/cropyield.duckdb"
    verify_inputs(root, database)
    labels = pd.read_parquet(root / "data/processed/labels_v1.parquet")
    lacuna_raw, _ = read_raw(root / "data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson")
    lacuna = reconcile_labels(lacuna_raw, labels)
    target = lacuna[lacuna.include_primary & lacuna.season_year.eq(config["target_year"])].copy()
    source_audit = audit_2024(root / "data/raw/vision_guided_yield_estimation/metadata.csv")
    rule = training_rows(config)
    screened = labels[labels.cohort.eq(AUXILIARY)].copy()
    require(set(source_audit.loc[source_audit.label_eligible, "obs_id"]) == set(screened.obs_id),
            "Independent 2024 label screen differs from frozen screened IDs")
    raw_check = screened.merge(source_audit, on="obs_id", suffixes=("_frozen", "_raw"), validate="one_to_one")
    for col in ["lat", "lon", "source_row"]:
        require(np.isclose(raw_check[f"{col}_frozen"], raw_check[f"{col}_raw"], rtol=0, atol=1e-7).all(),
                f"2024 raw/frozen disagreement: {col}")
    require(np.isclose(raw_check.yield_kg_ha / 1000, raw_check.yield_t_ha, rtol=0, atol=1e-6).all(),
            "2024 raw/frozen yield disagreement")
    split_path = root / f"data/splits/{COHORT}__s1_cc2km.csv"
    split = pd.read_csv(split_path, dtype={"group_id": str})
    require(split.obs_id.is_unique and set(split.obs_id) == set(target.obs_id), "Target splits do not match labels")
    target = target.merge(split[["obs_id", "fold", "group_id"]], on="obs_id", validate="one_to_one")
    target["domain"] = "lacuna"
    target["n_cuts_observed"] = 1
    screened["domain"] = "zimbabwe_2024"
    screened = screened.merge(source_audit[["obs_id", "n_cuts_observed"]], on="obs_id", validate="one_to_one")
    # v1 ("all_screened") superseded positive-only inclusion; v2 ("include_primary") keeps the team rule.
    aux = (screened if rule == "all_screened" else screened[screened.include_primary.eq(True)]).copy()
    aux["fold"] = -1
    aux["group_id"] = "auxiliary"
    catalog_lacuna = lacuna.copy()
    catalog_lacuna["domain"] = "lacuna"
    catalog_lacuna["n_cuts_observed"] = 1
    catalog = pd.concat([catalog_lacuna, screened], ignore_index=True)
    catalog["yield_t_ha"] = catalog.yield_kg_ha / 1000
    catalog["season_label"] = (catalog.season_year - 1).astype(str) + "/" + catalog.season_year.astype(str)
    catalog["comparison_candidate"] = catalog.obs_id.isin(target.obs_id) | catalog.obs_id.isin(aux.obs_id)
    catalog = catalog.sort_values("obs_id").reset_index(drop=True)
    combined = pd.concat([target, aux], ignore_index=True)
    require_training_rows(combined, config, "Combined comparison table")
    combined["yield_t_ha"] = combined.yield_kg_ha / 1000
    combined["season_label"] = (combined.season_year - 1).astype(str) + "/" + combined.season_year.astype(str)
    with duckdb.connect(str(database), read_only=True) as con:
        con.register("selected", combined[["obs_id", "season_year"]])
        monthly = con.execute("""SELECT v.*, b.missing, s.season_year FROM vegetation_indices v
            JOIN monthly_bands b USING (obs_id, month) JOIN selected s USING (obs_id)
            WHERE v.month >= CAST(s.season_year - 1 AS VARCHAR) || '-12'
              AND v.month <= CAST(s.season_year AS VARCHAR) || '-06' ORDER BY obs_id, month""").df()
    require(not monthly.duplicated(["obs_id", "month"]).any(), "Duplicate monthly key")
    require(set(monthly.obs_id) == set(combined.obs_id) and monthly.groupby("obs_id").size().eq(7).all(),
            "Common-window spine is incomplete")
    aggregate = {f"{index}_season_{stat}": (index, stat) for index in ["ndvi", "gcvi", "mtci", "ndvi705", "ndvi740"]
                 for stat in ["max", "mean"]}
    feature_frame = monthly.groupby("obs_id").agg(**aggregate)
    feature_frame["observed_months"] = monthly.assign(observed=~monthly.missing).groupby("obs_id")["observed"].sum()
    combined = combined.merge(feature_frame, on="obs_id", validate="one_to_one")
    finite = np.isfinite(combined[FEATURES].to_numpy()).all(axis=1)
    combined["feature_eligible"] = finite & combined.observed_months.ge(config["minimum_clear_months"])
    require(combined.loc[combined.domain.eq("lacuna"), "feature_eligible"].all(), "Target rows lost in common-window comparison")
    columns = ["obs_id", "cohort", "domain", "source_id", "source_row", "season_year", "season_label",
               "lat", "lon", "yield_kg_ha", "yield_t_ha", "yield_definition", "cut_area_m2", "n_cuts_observed",
               "moisture_basis_pct", "unit_provisional", "intercropped", "irrigated", "admin_unit",
               "is_zero", "include_primary", "fold", "group_id", "observed_months", "feature_eligible", *FEATURES]
    combined = combined[columns].sort_values("obs_id").reset_index(drop=True)
    catalog = catalog.merge(combined[["obs_id", "feature_eligible", "observed_months", "fold", "group_id"]],
                            on="obs_id", how="left", validate="one_to_one")
    source_audit = source_audit.merge(combined[["obs_id", "feature_eligible", "observed_months"]],
                                     on="obs_id", how="left", validate="one_to_one")
    summary = {
        "harmonized_labels": len(catalog), "lacuna_screened_labels": len(lacuna),
        "target_primary": len(target), "target_evaluation": int(target.fold.isin(config["target_folds"]).sum()),
        "target_reserved": int(target.fold.eq(config["reserved_fold"]).sum()),
        "raw_2024_maize": len(source_audit), "raw_2024_missing_yield": int(source_audit.yield_t_ha.isna().sum()),
        "source_labels": len(aux), "source_zeros": int(aux.is_zero.sum()),
        "source_single_cut": int(aux.n_cuts_observed.eq(1).sum()),
        "source_feature_eligible": int(combined.loc[combined.domain.eq("zimbabwe_2024"), "feature_eligible"].sum()),
        "feature_names": FEATURES, "common_window": "December through June of each agricultural season",
    }
    if rule != "all_screened":
        summary.update({"training_rows": rule, "source_screened_labels": len(screened),
                        "source_screened_zeros": int(screened.is_zero.sum()),
                        "source_excluded_by_training_rule": len(screened) - len(aux),
                        "source_exclusion_reasons": screened.loc[~screened.obs_id.isin(aux.obs_id), "exclusion_reason"]
                        .value_counts().sort_index().to_dict()})
    return combined, source_audit, catalog, summary


def purge_source(source: pd.DataFrame, protected: pd.DataFrame, km: float) -> tuple[pd.DataFrame, np.ndarray]:
    """Remove auxiliary points near protected target coordinates, never using target labels."""
    if source.empty:
        return source.copy(), np.array([])
    require(len(protected) > 0, "No protected coordinates supplied")
    a = unit_xyz(source.lat.to_numpy(), source.lon.to_numpy())
    b = unit_xyz(protected.lat.to_numpy(), protected.lon.to_numpy())
    chord = cKDTree(b).query(a)[0]
    distances = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / (2 * EARTH_RADIUS_KM), 0, 1))
    return source.loc[distances >= km].copy(), distances


class TargetPreprocessor:
    """Identical target-training-only clipping and feature scaling for every model arm."""
    def fit(self, x: np.ndarray):
        self.low, self.high = np.quantile(x, [.01, .99], axis=0)
        clipped = np.clip(x, self.low, self.high)
        self.mean = clipped.mean(axis=0)
        self.scale = clipped.std(axis=0)
        self.scale[self.scale < 1e-12] = 1
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (np.clip(x, self.low, self.high) - self.mean) / self.scale


def prepare_training(target: pd.DataFrame, source: pd.DataFrame, query: pd.DataFrame) -> dict:
    transformer = TargetPreprocessor().fit(target[FEATURES].to_numpy(float))
    return {"xt": transformer.transform(target[FEATURES].to_numpy(float)),
            "xs": transformer.transform(source[FEATURES].to_numpy(float)),
            "xq": transformer.transform(query[FEATURES].to_numpy(float)),
            "yt": target.yield_t_ha.to_numpy(float), "ys": source.yield_t_ha.to_numpy(float)}


def source_policy(method: str, y: np.ndarray, zero_weight: float) -> tuple[np.ndarray, np.ndarray]:
    keep = np.ones(len(y), dtype=bool)
    if method == "pooled_positive_sensitivity":
        keep = y > 0
    weights = np.ones(int(keep.sum()))
    if method == "pooled_zero_weight_sensitivity":
        weights[y[keep] == 0] = zero_weight
    return keep, weights


def predict_model(data: dict, method: str, parameters: dict, config: dict) -> np.ndarray:
    xt, xs, xq, yt, ys = (data[k] for k in ["xt", "xs", "xq", "yt", "ys"])
    if method == "train_mean":
        return np.full(len(xq), yt.mean())
    keep, source_weights = source_policy(method, ys, config.get("zero_sensitivity_weight", 1.))
    xs, ys = xs[keep], ys[keep]
    ratio = parameters.get("source_ratio", 0)
    use_source = len(xs) > 0 and ratio > 0
    if method in ["lacuna_tree", "pooled_tree"]:
        x = np.c_[xt, np.zeros(len(xt))]
        y, weight = yt, np.ones(len(yt))
        if use_source:
            x = np.r_[x, np.c_[xs, np.ones(len(xs))]]
            y = np.r_[yt, ys]
            weight = np.r_[weight, source_weights / source_weights.sum() * len(yt) * ratio]
        tree = HistGradientBoostingRegressor(max_iter=config["tree_iterations"], learning_rate=.05,
                                             max_leaf_nodes=parameters["leaf_nodes"], min_samples_leaf=20,
                                             l2_regularization=1., early_stopping=False, random_state=config["seed"])
        prediction = tree.fit(x, y, sample_weight=weight).predict(np.c_[xq, np.zeros(len(xq))])
    elif not use_source:
        prediction = Ridge(alpha=parameters["alpha"]).fit(xt, yt).predict(xq)
    elif method == "pooled_naive":
        prediction = Ridge(alpha=parameters["alpha"]).fit(np.r_[xt, xs], np.r_[yt, ys]).predict(xq)
    else:
        # Separate cohort centering gives unpenalized, training-only source/target intercepts.
        mt, ms = yt.mean(), np.average(ys, weights=source_weights)
        ct, cs = xt.mean(axis=0), np.average(xs, axis=0, weights=source_weights)
        zt, zs, zq = xt - ct, xs - cs, xq - ct
        weight = np.r_[np.ones(len(yt)), source_weights / source_weights.sum() * len(yt) * ratio]
        if method == "pooled_intercept":
            x, y, query = np.r_[zt, zs], np.r_[yt - mt, ys - ms], zq
            target_scale = 1.
        else:
            target_scale = max(yt.std(), 1e-12)
            source_scale = max(float(np.sqrt(np.average((ys - ms) ** 2, weights=source_weights))), 1e-12)
            zeros_t, zeros_s = np.zeros_like(zt), np.zeros_like(zs)
            x = np.r_[np.c_[zt, zt, zeros_t], np.c_[zs, zeros_s, zs]] / np.sqrt(2)
            query = np.c_[zq, zq, np.zeros_like(zq)] / np.sqrt(2)
            y = np.r_[(yt - mt) / target_scale, (ys - ms) / source_scale]
        ridge = Ridge(alpha=parameters["alpha"], fit_intercept=False)
        prediction = mt + target_scale * ridge.fit(x, y, sample_weight=weight).predict(query)
    return np.maximum(prediction, 0)


def candidates(method: str, config: dict) -> list[dict]:
    if method == "train_mean":
        return [{}]
    if method in ["lacuna_only", "lacuna_tree"]:
        ratios = [0.]
    elif method == "pooled_naive":
        ratios = [1.]  # equal per-row weights, deliberately NOT source-mass normalized
    elif method == "pooled_intercept":
        ratios = [v for v in config["source_weight_ratios"] if v > 0]
    else:
        ratios = config["source_weight_ratios"]
    if method in ["lacuna_tree", "pooled_tree"]:
        return [{"leaf_nodes": leaves, "source_ratio": ratio}
                for ratio, leaves in itertools.product(ratios, config["tree_leaf_nodes"])]
    return [{"alpha": alpha, "source_ratio": ratio} for ratio, alpha in itertools.product(ratios, config["ridge_alphas"])]


def score_predictions(y: np.ndarray, prediction: np.ndarray) -> dict:
    error = prediction - y
    total = np.sum((y - y.mean()) ** 2)
    rank = float(spearmanr(y, prediction).statistic) if np.ptp(prediction) and np.ptp(y) else np.nan
    return {"rmse_t_ha": float(np.sqrt(np.mean(error ** 2))), "mae_t_ha": float(np.mean(abs(error))),
            "bias_t_ha": float(error.mean()), "r2": float(1 - np.sum(error ** 2) / total), "spearman": rank}


def run_folds(combined: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, ...]:
    target = combined[combined.domain.eq("lacuna")].copy()
    source = combined[combined.domain.eq("zimbabwe_2024") & combined.feature_eligible].copy()
    require_training_rows(target, config, "Lacuna target pool")
    require_training_rows(source, config, "Zimbabwe 2024 source pool")
    reserved = target[target.fold.eq(config["reserved_fold"])]
    development = target[target.fold.isin(config["target_folds"])].copy()
    require(config["reserved_fold"] == 0 and 0 not in config["target_folds"], "Fold 0 cannot enter this experiment")
    require(len(development) + len(reserved) == len(target), "Target fold coverage incomplete")
    predictions, tuning, chosen, permissions, memberships = [], [], [], [], []
    for outer in config["target_folds"]:
        train, evaluation = development[development.fold.ne(outer)].copy(), development[development.fold.eq(outer)].copy()
        require(set(train.group_id).isdisjoint(evaluation.group_id), "Outer group leakage")
        allowed, distances = purge_source(source, pd.concat([reserved, evaluation]), config["auxiliary_buffer_km"])
        permissions.append(pd.DataFrame({"obs_id": source.obs_id, "outer_fold": outer, "inner_fold": 0,
                                         "minimum_distance_to_protected_km": distances,
                                         "allowed_by_spatial_rule": distances >= config["auxiliary_buffer_km"]}))
        inner_data, inner_y = [], []
        for role, rows in [("fit", train), ("evaluation", evaluation), ("reserved", reserved)]:
            memberships.append(rows[["obs_id", "group_id"]].assign(outer_fold=outer, inner_fold=0, role=role))
        for inner, (fit, val) in enumerate(GroupKFold(config["inner_folds"]).split(train, groups=train.group_id), 1):
            inner_train, inner_val = train.iloc[fit], train.iloc[val]
            require(set(inner_train.group_id).isdisjoint(inner_val.group_id), "Inner group leakage")
            inner_source, inner_distances = purge_source(source, pd.concat([reserved, evaluation, inner_val]),
                                                        config["auxiliary_buffer_km"])
            permissions.append(pd.DataFrame({"obs_id": source.obs_id, "outer_fold": outer, "inner_fold": inner,
                                             "minimum_distance_to_protected_km": inner_distances,
                                             "allowed_by_spatial_rule": inner_distances >= config["auxiliary_buffer_km"]}))
            for role, rows in [("fit", inner_train), ("validation", inner_val)]:
                memberships.append(rows[["obs_id", "group_id"]].assign(outer_fold=outer, inner_fold=inner, role=role))
            inner_data.append(prepare_training(inner_train, inner_source, inner_val))
            inner_y.append(inner_val.yield_t_ha.to_numpy())
        truth = np.concatenate(inner_y)
        outer_data = prepare_training(train, allowed, evaluation)
        for method in config["methods"]:
            trials = []
            for params in candidates(method, config):
                pred = np.concatenate([predict_model(data, method, params, config) for data in inner_data])
                loss = float(np.mean((truth - pred) ** 2))
                trials.append((loss, params))
                tuning.append({"outer_fold": outer, "method": method, **params, "inner_rmse_t_ha": np.sqrt(loss)})
            _, params = min(trials, key=lambda item: item[0])
            pred = predict_model(outer_data, method, params, config)
            keep, _ = source_policy(method, allowed.yield_t_ha.to_numpy(), config.get("zero_sensitivity_weight", 1.))
            selected_source_count = int(keep.sum()) if params.get("source_ratio", 0) > 0 else 0
            chosen.append({"outer_fold": outer, "method": method, **params,
                           "n_target_train": len(train), "n_target_evaluation": len(evaluation),
                           "source_after_spatial_buffer": len(allowed), "source_used": selected_source_count,
                           "inner_rmse_t_ha": np.sqrt(min(v[0] for v in trials))})
            predictions.append(pd.DataFrame({"obs_id": evaluation.obs_id, "group_id": evaluation.group_id,
                                              "outer_fold": outer, "method": method,
                                              "yield_t_ha": evaluation.yield_t_ha, "prediction_t_ha": pred}))
            print(f"fold {outer} {method}: trained on {len(train)} target / {selected_source_count} source; {params}", flush=True)
    return (pd.concat(predictions, ignore_index=True), pd.DataFrame(tuning), pd.DataFrame(chosen),
            pd.concat(permissions, ignore_index=True), pd.concat(memberships, ignore_index=True))


def evaluate(predictions: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metrics, fold_metrics = [], []
    for method in config["methods"]:
        part = predictions[predictions.method.eq(method)]
        require(part.obs_id.is_unique and not part.outer_fold.eq(0).any(), "Duplicate evaluation / fold 0 exposure")
        metrics.append({"method": method, "n": len(part), **score_predictions(part.yield_t_ha.to_numpy(), part.prediction_t_ha.to_numpy())})
        for fold, rows in part.groupby("outer_fold"):
            fold_metrics.append({"method": method, "fold": fold, "n": len(rows),
                                 **score_predictions(rows.yield_t_ha.to_numpy(), rows.prediction_t_ha.to_numpy())})
    wide = predictions.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()
    truth = predictions[predictions.method.eq("lacuna_only")].set_index("obs_id").loc[wide.index]
    require(wide.notna().all().all(), "Methods did not predict the same fields")
    y, group = truth.yield_t_ha.to_numpy(), truth.group_id.to_numpy()
    group_ids = np.unique(group)
    members = [np.flatnonzero(group == g) for g in group_ids]
    rng = np.random.default_rng(config["seed"])
    draws = [np.concatenate([members[i] for i in rng.integers(len(members), size=len(members))])
             for _ in range(config["bootstrap_draws"])]
    differences = []
    for method in config["methods"]:
        reference = "lacuna_tree" if method == "pooled_tree" else "lacuna_only"
        p, base = wide[method].to_numpy(), wide[reference].to_numpy()
        values = [np.sqrt(np.mean((p[ix] - y[ix]) ** 2)) - np.sqrt(np.mean((base[ix] - y[ix]) ** 2)) for ix in draws]
        low, high = np.quantile(values, [.025, .975])
        delta = np.sqrt(np.mean((p-y)**2)) - np.sqrt(np.mean((base-y)**2))
        differences.append({"method": method, "reference": reference, "delta_rmse_t_ha": delta,
                            "ci_low": low, "ci_high": high, "bootstrap_fraction_lower_rmse": np.mean(np.array(values) < 0),
                            "primary_comparison": method == config["primary_method"]})
    return pd.DataFrame(metrics), pd.DataFrame(differences), pd.DataFrame(fold_metrics)


def plot_results(path: Path, metrics: pd.DataFrame, differences: pd.DataFrame, config: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = {"train_mean": "Training mean", "lacuna_only": "Lacuna only · Ridge", "pooled_naive": "Naive merge",
             "pooled_intercept": "Separate cohort intercepts", "pooled_adaptive": "Adaptive merge (primary)",
             "pooled_positive_sensitivity": "Adaptive · source positives only", "pooled_zero_weight_sensitivity": "Adaptive · zeros weighted 0.25",
             "lacuna_tree": "Lacuna only · boosted trees", "pooled_tree": "Merged · boosted trees"}
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), layout="constrained")
    order = config["methods"][::-1]
    values = metrics.set_index("method").loc[order]
    axes[0].barh([names[m] for m in order], values.rmse_t_ha, color=["#136f63" if m == config["primary_method"] else "#3973ac" for m in order])
    for i, value in enumerate(values.rmse_t_ha):
        axes[0].text(value+.02, i, f"{value:.3f}", va="center")
    axes[0].set(xlabel="Lacuna RMSE (t/ha), lower is better", xlim=(0, values.rmse_t_ha.max()*1.15))
    rows = differences.set_index("method").loc[order]
    for i, (_, row) in enumerate(rows.iterrows()):
        axes[1].plot([row.ci_low, row.ci_high], [i, i], color="#3973ac", linewidth=2)
        axes[1].plot(row.delta_rmse_t_ha, i, "o", color="#136f63" if row.primary_comparison else "#3973ac")
    axes[1].axvline(0, color="#666666", linewidth=1)
    axes[1].set_yticks(range(len(order)), [""] * len(order))
    axes[1].set(xlabel="RMSE difference vs reference (t/ha)\nNegative favors merging; paired 95% group-bootstrap intervals")
    axes[0].set_title("Same held-out Lacuna fields")
    axes[1].set_title("Ridge reference; pooled trees use tree reference")
    fig.suptitle("Lacuna vs Lacuna + Zimbabwe 2024\nExploratory spatial CV on folds 1–4; fold 0 unused", fontsize=14)
    fig.savefig(path, dpi=160, metadata={"Software": "cropyield Zimbabwe merge"})
    plt.close(fig)


def write_report(path: Path, config: dict, summary: dict, metrics: pd.DataFrame,
                 differences: pd.DataFrame, selected: pd.DataFrame,
                 config_name: str = "configs/zimbabwe_merge_v1.json",
                 output_name: str = "data/runs/zimbabwe_merge_v1") -> None:
    legacy = training_rows(config) == "all_screened"
    if legacy:
        sensitivity = ("Positive-only/zero-downweight and tree comparisons are\n"
                       "sensitivity analyses, not separately confirmed discoveries or evidence that zeros are invalid.")
        source_text = (f"- **{summary['source_labels']:,}** 2024 labels pass the independent measurement audit. Of these,\n"
                       f"  **{summary['source_single_cut']}** have one measured box. Their available-box averages are respected.")
        zero_text = f"These are distinguishable from **{summary['source_zeros']:,}** recorded zero yields."
        rule_text = "Original `include_primary` is retained as legacy metadata; the new experiment intentionally allows valid 2024 zeros."
    else:
        sensitivity = ("The v1 positive-only and zero-weight arms are not run: the `include_primary`\n"
                       "pool holds no zeros, so both would equal the primary adaptive arm. Tree comparisons are sensitivity analyses.")
        source_text = (f"- **{summary['source_screened_labels']:,}** 2024 labels pass the independent measurement audit. Training rows follow\n"
                       f"  `labels_v1.include_primary`: **{summary['source_labels']:,}** rows. The **{summary['source_excluded_by_training_rule']:,}**\n"
                       f"  excluded rows are the recorded zeros (`zimbabwe_2024_zero_likely_not_measured`); they stay in the catalog only.\n"
                       f"  **{summary['source_single_cut']}** training rows have one measured box. Their available-box averages are respected.")
        zero_text = f"These are distinguishable from **{summary['source_screened_zeros']:,}** recorded zero yields."
        rule_text = ("Every training row has `include_primary = True` (config `training_rows: include_primary`);\n"
                     "  the run stops if a fit pool holds another row.")
    rows = []
    for _, r in metrics.iterrows():
        rank = "n/a" if not np.isfinite(r.spearman) else f"{r.spearman:.3f}"
        rows.append(f"| {r.method} | {r.rmse_t_ha:.4f} | {r.mae_t_ha:.4f} | {r.bias_t_ha:+.4f} | {r.r2:.3f} | {rank} |")
    primary = differences[differences.method.eq(config["primary_method"])].iloc[0]
    selections = selected[selected.method.eq(config["primary_method"])]
    ratio_text = ", ".join(f"fold {int(r.outer_fold)}: {r.source_ratio:g}" for _, r in selections.iterrows())
    verdict = ("lower" if primary.ci_high < 0 else "higher" if primary.ci_low > 0 else "not clearly different")
    text = f"""# Lacuna plus Zimbabwe 2024: results

## Primary comparison

The pre-specified adaptive merge has RMSE **{verdict}** than Lacuna-only Ridge under this protocol.
Paired ΔRMSE (adaptive − Lacuna only): **{primary.delta_rmse_t_ha:+.4f} t/ha**;
95% spatial-group bootstrap interval **[{primary.ci_low:+.4f}, {primary.ci_high:+.4f}]**.
Source-to-target training weight ratios chosen internally: {ratio_text}.
A ratio of zero means auxiliary data were rejected for that fold, not used successfully.

This is exploratory nested spatial cross-validation, not a new blind-test result. Both methods predict the same
**{summary['target_evaluation']:,} Lacuna 2023 fields**. Historical fold 0 (**{summary['target_reserved']} fields**) is
excluded from every model fit and score. Auxiliary rows near it are excluded too. Source observations are 2024,
so this is a retrospective data-sharing experiment, not a real-time 2023 forecasting result.

## Complete results

| Method | RMSE t/ha | MAE t/ha | Bias t/ha | R² | Spearman |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

All negative predictions are clipped to zero by the same rule. Metrics are within Lacuna only; no score combines
the target and source outcome distributions. `paired_differences.csv` contains every uncertainty interval;
the primary method was specified before the run. {sensitivity}

## What was merged and corrected

- **{summary['harmonized_labels']:,}** screened labels in the complete harmonized catalog: all
  **{summary['lacuna_screened_labels']:,}** Lacuna 2022/2023 labels plus all screened 2024 labels.
  The controlled comparison uses **{summary['target_primary']:,}** primary Lacuna 2023 labels.
  The existing three inconsistent raw Lacuna conversions remain excluded.
- **{summary['raw_2024_maize']:,}** raw 2024 Zimbabwe maize records inspected. **{summary['raw_2024_missing_yield']:,}** have
  explicitly missing yields. {zero_text}
{source_text}
- No blanket multiplicative conversion was needed: available per-box yields equal dry kg × 0.25, and available-box
  averages equal reported field yield. This confirms numeric consistency, not physical moisture equivalence.
- **{summary['source_feature_eligible']:,}** source rows meet common-window feature eligibility before fold-specific spatial buffering.
- Both cohorts use December–June aggregates, the same ten spectral predictors, and at least four observed months.
  `combined_data.parquet` preserves the harmonized labels, source/season/management metadata, eligibility and features.
  {rule_text}

## How incompatibilities were handled

The primary model centers/scales targets separately within each training cohort and learns shared plus cohort-specific
feature slopes. Predictions are restored to the Lacuna training scale. This makes the source contribution invariant
to a fixed positive affine change of source label units, while leaving the physical exported labels unchanged.
It does not identify a true moisture conversion or distinguish drought from provider effects. Source weight is
selected by inner target-only validation and may be zero. Unknown irrigation/intercropping are not fabricated.
The naive merge and intercept-only comparison quantify how much these modeling choices matter.

Every inner and outer split independently removes source points within 2 km of protected target observations.
Clipping and feature scaling use target-training rows only; cohort centering and outcome scaling use allowed training
rows only. Neither outer evaluation outcomes nor reserved outcomes enter tuning or normalization.

The full problem/action/remaining-limitation register is in `PROTOCOL.md`. Issues that cannot be inferred from
the released files are explicitly modeled or bounded through sensitivity analyses, not declared physically solved.

## Reproduce and inspect

From the repository root: `python scripts/step9_compare_zimbabwe_merge.py{"" if legacy else " --config " + config_name}`.
Config: `{config_name}`. Results are generated in `{output_name}/`.
Use a new `--output` directory when changing the code/config. The manifest records inputs, code and outputs.

- `source_2024_audit.csv`: all raw 2024 maize records, measurement checks and exclusion reasons.
- `source_spatial_permissions.csv`: auxiliary access and distances for every outer and inner fold (inner 0 denotes outer fit).
- `target_memberships.csv`: exact target fit, validation, evaluation and reserved memberships.
- `tuning.csv`: all inner-CV candidates and scores; `selected_parameters.csv`: chosen parameters and source counts.
- `predictions.csv`: paired out-of-fold target predictions; `metrics.csv` and `fold_metrics.csv`: results.
- `paired_differences.csv`: paired group-bootstrap intervals, with the pre-specified primary comparison marked.
- `combined_data.parquet` / `.csv`: harmonized data, including reserved rows clearly marked as fold 0.
- `harmonized_labels.parquet`: complete screened catalog, including Lacuna 2022 and non-primary management groups.
  `comparison_candidate` distinguishes inclusion in this experiment; null feature eligibility means not evaluated here.

![Comparison](comparison.png)

Sources: [Lacuna](https://doi.org/10.5281/zenodo.10060610),
[2024 paper](https://arxiv.org/html/2511.12999v1),
[shared/domain-specific feature augmentation](https://aclanthology.org/P07-1033/).
"""
    path.write_text(text, encoding="utf-8")


def experiment_inputs(root: Path, config_path: Path) -> dict:
    paths = ["data/processed/labels_v1.parquet", "data/cropyield.duckdb", "configs/team_database_v1.json",
             "data/splits/manifest.json", f"data/splits/{COHORT}__s1_cc2km.csv",
             "data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson",
             "data/raw/vision_guided_yield_estimation/metadata.csv",
             "src/cropyield/experiments/zimbabwe_merge.py", "src/cropyield/data/handoff.py",
             "src/cropyield/eval/splits.py", "src/cropyield/data/xy.py", "src/cropyield/data/labels.py",
             "scripts/step9_compare_zimbabwe_merge.py", "docs/ZIMBABWE_MERGE_PROTOCOL.md", "requirements.txt"]
    result = {name: sha256(root / name) for name in paths}
    result[str(config_path.relative_to(root)) if config_path.is_relative_to(root) else str(config_path)] = sha256(config_path)
    return result


def relative_name(path: Path, root: Path = ROOT) -> str:
    path = Path(path)
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def run_experiment(output: Path = OUTPUT, config_path: Path = CONFIG, root: Path = ROOT) -> dict:
    config = json.loads(config_path.read_text())
    require(config["target_folds"] == [1, 2, 3, 4] and config["reserved_fold"] == 0, "Do not change target evaluation population")
    require(config["calendar_months"] == [12, 1, 2, 3, 4, 5, 6], "This implementation requires December–June")
    if training_rows(config) == "include_primary":
        # include_primary 2024 rows hold no zeros, so these arms would only duplicate pooled_adaptive.
        require(not set(config["methods"]) & set(ZERO_POLICY_METHODS),
                "Zero-policy arms equal pooled_adaptive under include_primary; drop them from the config")
    before = experiment_inputs(root, config_path)
    combined, audit, catalog, summary = prepare_data(root, config)
    with threadpool_limits(limits=1):
        predictions, tuning, selected, permissions, memberships = run_folds(combined, config)
        metrics, differences, fold_metrics = evaluate(predictions, config)
    with tempfile.TemporaryDirectory(prefix="zimbabwe-merge-") as tmp:
        staged = Path(tmp)
        for name, table in {"combined_data": combined, "source_2024_audit": audit, "predictions": predictions,
                            "tuning": tuning, "selected_parameters": selected, "source_spatial_permissions": permissions,
                            "target_memberships": memberships,
                            "metrics": metrics, "paired_differences": differences, "fold_metrics": fold_metrics}.items():
            csv_write(table, staged / f"{name}.csv")
        combined.to_parquet(staged / "combined_data.parquet", index=False)
        catalog.to_parquet(staged / "harmonized_labels.parquet", index=False)
        json_write(summary, staged / "data_summary.json")
        (staged / "PROTOCOL.md").write_text((root / "docs/ZIMBABWE_MERGE_PROTOCOL.md").read_text(), encoding="utf-8")
        write_report(staged / "RESULTS.md", config, summary, metrics, differences, selected,
                     relative_name(config_path, root), relative_name(output, root))
        plot_results(staged / "comparison.png", metrics, differences, config)
        require(before == experiment_inputs(root, config_path), "Input/code changed during the run")
        manifest = {"config": config, "inputs": before, "python": platform.python_version(),
                    "versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "scikit-learn", "duckdb", "pyarrow", "matplotlib"]},
                    "outputs": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted(staged.iterdir())}}
        json_write(manifest, staged / "manifest.json")
        publish_release(staged, output)
    print(metrics.round(4).to_string(index=False), flush=True)
    print(differences[["method", "delta_rmse_t_ha", "ci_low", "ci_high"]].round(4).to_string(index=False), flush=True)
    return summary
