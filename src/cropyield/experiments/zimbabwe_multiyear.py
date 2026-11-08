"""Audit all Zimbabwe years; compare broader training pools on frozen Lacuna targets."""
from __future__ import annotations

import importlib.metadata
import itertools
import json
import platform
import subprocess
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from cropyield import ROOT
from cropyield.data.handoff import csv_write, json_write, publish_release, require, verify_inputs
from cropyield.data.labels import sha256
from cropyield.data.xy import FEATURES
from cropyield.experiments.zimbabwe_aggregation import VARIANTS, aggregate_monthly
from cropyield.experiments.zimbabwe_diagnosis import BANDS, INDICES, TrainingTransform
from cropyield.experiments.zimbabwe_merge import predict_model, purge_source, score_predictions

CONFIG = ROOT / "configs/zimbabwe_multiyear_v1.json"
OUTPUT = ROOT / "data/runs/zimbabwe_multiyear_v1"
PROTOCOL = ROOT / "docs/zimbabwe/MULTIYEAR_PROTOCOL.md"
PRIOR = ROOT / "data/runs/zimbabwe_merge_v1"
CONTROLS = ROOT / "data/runs/zimbabwe_aggregation_v1"
NEW_TRAINING = ["all_lacuna", "all_zimbabwe"]


def verify_release(path):
    manifest = json.loads((path / "manifest.json").read_text())
    for name, info in manifest["outputs"].items():
        require(sha256(path / name) == info["sha256"], f"Frozen output changed: {path.name}/{name}")


def build_eligibility(rows, features, audit, config):
    """Require shared observed support and finite predictors; never impute missing imagery."""
    require(rows.index.is_unique and audit.index.equals(rows.index), "Eligibility index mismatch")
    season_ok = audit.n_season.ge(config["minimum_clear_months"])
    finite = pd.DataFrame({name: np.isfinite(frame.loc[rows.index].to_numpy(float)).all(axis=1)
                           for name, frame in features.items()}, index=rows.index)
    eligible = season_ok & finite.all(axis=1)
    pieces = []
    for name in features:
        reasons = pd.Series("", index=rows.index)
        reasons.loc[~season_ok] = "fewer_than_four_common_season_months"
        reasons.loc[~finite[name]] += ";nonfinite_aggregate_predictor"
        reasons.loc[season_ok & finite[name] & ~eligible] = "nonfinite_predictor_in_another_feature_set"
        pieces.append(pd.DataFrame({"obs_id": rows.index, "feature_set": name,
                                   "observed_season_months": audit.n_season.to_numpy(),
                                   "finite_features": finite[name].to_numpy(), "model_eligible": eligible.to_numpy(),
                                   "exclusion_reason": reasons.str.lstrip(";").to_numpy()}))
    return eligible, pd.concat(pieces, ignore_index=True)


def load_inputs(config):
    verify_inputs(ROOT, ROOT / "data/cropyield.duckdb")
    verify_release(PRIOR)
    verify_release(CONTROLS)
    rows = pd.read_parquet(PRIOR / "harmonized_labels.parquet").set_index("obs_id").sort_index()
    require(len(rows) == 6598 and rows.index.is_unique, "Screened Zimbabwe catalog changed")
    require(np.isfinite(rows[["lat", "lon", "yield_t_ha"]].to_numpy(float)).all(), "Invalid screened labels")
    rows["fold"] = rows.fold.fillna(-1).astype(int)
    rows["group_id"] = rows.group_id.fillna("extra_lacuna").astype(str)
    with duckdb.connect(str(ROOT / "data/cropyield.duckdb"), read_only=True) as con:
        con.register("selected", rows.reset_index()[["obs_id", "season_year"]])
        monthly = con.execute("""SELECT b.*, v.ndvi,v.gcvi,v.mtci,v.ndvi705,v.ndvi740,sc.acquired
            FROM monthly_bands b JOIN vegetation_indices v USING(obs_id,month)
            JOIN selected s USING(obs_id) LEFT JOIN scenes sc USING(obs_id,month)
            WHERE b.month >= CAST(s.season_year-1 AS VARCHAR)||'-12'
              AND b.month <= CAST(s.season_year AS VARCHAR)||'-06'
            ORDER BY b.obs_id,b.month""").df()
    require(set(monthly.obs_id) == set(rows.index) and monthly.groupby("obs_id").size().eq(7).all(),
            "Common-window monthly spine changed")
    features, audit = aggregate_monthly(monthly, rows, config)
    legacy = pd.concat([features[f"indices_{variant}"].rename(columns={c: f"{c}_season_{stat}" for c in INDICES})
                        for variant, stat in [("v0_mean", "mean"), ("v2_max", "max")]], axis=1)
    features["legacy_indices_mean_max"] = legacy[FEATURES]
    original = pd.read_parquet(PRIOR / "combined_data.parquet").set_index("obs_id")
    np.testing.assert_allclose(legacy.loc[original.index, FEATURES], original[FEATURES], atol=1e-12, rtol=1e-12,
                               equal_nan=True, err_msg="Legacy predictors changed")
    rows["model_eligible"], eligibility = build_eligibility(rows, features, audit, config)
    rows["observed_common_season_months"] = audit.n_season
    membership = pd.read_csv(PRIOR / "target_memberships.csv", dtype={"group_id": str})
    permission = pd.read_csv(PRIOR / "source_spatial_permissions.csv")
    require((PRIOR / "target_memberships.csv").read_bytes() == (CONTROLS / "target_memberships.csv").read_bytes(),
            "Step 14 target membership differs")
    require((PRIOR / "source_spatial_permissions.csv").read_bytes() == (CONTROLS / "source_spatial_permissions.csv").read_bytes(),
            "Step 14 source permission differs")
    primary = rows.domain.eq("lacuna") & rows.include_primary
    require(primary.sum() == 1880 and rows.loc[primary, "model_eligible"].all(), "Primary population changed")
    require((primary & rows.fold.eq(0)).sum() == 376, "Reserved population changed")
    require((primary & rows.fold.isin(config["target_folds"])).sum() == 1504, "Evaluation population changed")
    expected = {("lacuna", 2022): (169, 0), ("lacuna", 2023): (2097, 2097), ("zimbabwe_2024", 2024): (4332, 4330)}
    for (domain, year), (count, allowed) in expected.items():
        part = rows[rows.domain.eq(domain) & rows.season_year.eq(year)]
        require(len(part) == count and int(part.model_eligible.sum()) == allowed, f"Coverage changed: {domain}/{year}")
    return rows, features, audit, eligibility, monthly, membership, permission


def build_permissions(rows, membership, source_permission, config):
    """Recheck frozen source buffers and derive allowed extras for each nested split."""
    extras = rows[rows.domain.eq("lacuna") & ~rows.include_primary & rows.model_eligible]
    source = rows[rows.domain.eq("zimbabwe_2024") & rows.model_eligible]
    reserved = rows[rows.domain.eq("lacuna") & rows.fold.eq(config["reserved_fold"])]
    require(len(reserved) > 0, "Reserved targets missing")
    records, fitting = [], []
    for outer in config["target_folds"]:
        outer_membership = membership[membership.outer_fold.eq(outer) & membership.inner_fold.eq(0)]
        outer_eval = outer_membership[outer_membership.role.eq("evaluation")].obs_id.tolist()
        require(len(outer_eval) > 0, "Outer evaluation missing")
        outer_protected = pd.concat([reserved, rows.loc[outer_eval]])
        for inner in sorted(membership.loc[membership.outer_fold.eq(outer), "inner_fold"].unique()):
            part = membership[membership.outer_fold.eq(outer) & membership.inner_fold.eq(inner)]
            fit_ids = part[part.role.eq("fit")].obs_id.tolist()
            query_ids = part[part.role.eq("evaluation" if inner == 0 else "validation")].obs_id.tolist()
            require(fit_ids and query_ids and set(fit_ids).isdisjoint(query_ids), "Invalid fitting membership")
            require(rows.loc[fit_ids + query_ids, "include_primary"].all(), "Frozen membership contains non-primary rows")
            require(rows.loc[fit_ids + query_ids, "fold"].ne(config["reserved_fold"]).all(), "Reserved target exposure")
            require(set(rows.loc[fit_ids].group_id).isdisjoint(rows.loc[query_ids].group_id), "Target spatial group leakage")
            protected = outer_protected if inner == 0 else pd.concat([outer_protected, rows.loc[query_ids]])
            allowed, distances = purge_source(extras, protected, config["auxiliary_buffer_km"])
            records.append(pd.DataFrame({"obs_id": extras.index, "outer_fold": outer, "inner_fold": inner,
                                         "minimum_distance_to_protected_km": distances,
                                         "allowed_by_spatial_rule": distances >= config["auxiliary_buffer_km"]}))
            _, source_distances = purge_source(source, protected, config["auxiliary_buffer_km"])
            frozen = source_permission[source_permission.outer_fold.eq(outer) & source_permission.inner_fold.eq(inner)]
            require(frozen.obs_id.is_unique and set(frozen.obs_id) == set(source.index), "Frozen source population changed")
            aligned = frozen.set_index("obs_id").loc[source.index]
            np.testing.assert_allclose(aligned.minimum_distance_to_protected_km, source_distances, atol=1e-8, rtol=0,
                                       err_msg="Frozen source distance mismatch")
            require(np.array_equal(aligned.allowed_by_spatial_rule, source_distances >= config["auxiliary_buffer_km"]),
                    "Frozen source permission changed")
            source_ids = frozen.loc[frozen.allowed_by_spatial_rule, "obs_id"].tolist()
            for role, ids in [("primary_fit", fit_ids), ("extra_lacuna_fit", allowed.index.tolist()),
                              ("source_allowed", source_ids), ("query", query_ids)]:
                fitting.append(pd.DataFrame({"obs_id": ids, "outer_fold": outer, "inner_fold": inner,
                                             "role": role, "position": np.arange(len(ids))}))
    return pd.concat(records, ignore_index=True), pd.concat(fitting, ignore_index=True)


def make_context(rows, x, fit_ids, source_ids, query_ids):
    """Build training-only transforms after rejecting all unavailable predictors."""
    require(set(fit_ids).isdisjoint(query_ids), "Query/training overlap")
    require(set(source_ids).isdisjoint(fit_ids + query_ids), "Source overlaps target")
    require(rows.loc[fit_ids + query_ids].domain.eq("lacuna").all(), "Invalid Lacuna context")
    require(rows.loc[fit_ids + query_ids].fold.ne(0).all(), "Reserved fold exposure")
    require(rows.loc[source_ids].domain.eq("zimbabwe_2024").all(), "Invalid source context")
    all_ids = fit_ids + source_ids + query_ids
    require(len(fit_ids) == len(set(fit_ids)) and len(query_ids) == len(set(query_ids))
            and len(source_ids) == len(set(source_ids)), "Duplicate context IDs")
    require(rows.loc[all_ids].model_eligible.all(), "Ineligible imagery in model context")
    require(np.isfinite(x.loc[all_ids].to_numpy(float)).all(), "Missing imagery predictor; imputation forbidden")
    require(np.isfinite(rows.loc[all_ids, "yield_t_ha"].to_numpy(float)).all(), "Nonfinite yield")
    transform = TrainingTransform().fit(x.loc[fit_ids])
    return {"xt": transform.transform(x.loc[fit_ids]), "xs": transform.transform(x.loc[source_ids]),
            "xq": transform.transform(x.loc[query_ids]), "yt": rows.loc[fit_ids].yield_t_ha.to_numpy(float),
            "ys": rows.loc[source_ids].yield_t_ha.to_numpy(float)}


def split_ids(fitting, outer, inner):
    part = fitting[fitting.outer_fold.eq(outer) & fitting.inner_fold.eq(inner)]
    ids = {role: group.sort_values("position").obs_id.tolist() for role, group in part.groupby("role")}
    primary, extra = ids.get("primary_fit", []), ids.get("extra_lacuna_fit", [])
    return primary + extra, ids.get("source_allowed", []), ids.get("query", []), len(primary), len(extra)


def run_models(rows, features, fitting, config):
    predictions, selections, trials, gaps = [], [], [], []
    for outer in config["target_folds"]:
        ids = [split_ids(fitting, outer, inner) for inner in range(4)]
        for feature_name, x in features.items():
            contexts = [make_context(rows, x, *item[:3]) for item in ids]
            truth = np.concatenate([rows.loc[item[2]].yield_t_ha.to_numpy(float) for item in ids[1:]])
            for training in config["training_sets"]:
                method = f"{feature_name}_{training}"
                kind = "lacuna_only" if training == "all_lacuna" else "pooled_adaptive"
                ratios = [0.] if training == "all_lacuna" else config["source_weight_ratios"]
                candidates = []
                for ratio, alpha in itertools.product(ratios, config["ridge_alphas"]):
                    params = {"alpha": alpha, "source_ratio": ratio}
                    estimate = np.concatenate([predict_model(c, kind, params, config) for c in contexts[1:]])
                    loss = float(np.mean((estimate - truth) ** 2))
                    candidates.append((loss, params))
                    trials.append({"method": method, "outer_fold": outer, **params, "inner_rmse_t_ha": np.sqrt(loss),
                                   "origin": "new_expanded_training"})
                loss, params = min(candidates, key=lambda value: value[0])
                fit_ids, source_ids, query_ids, n_primary, n_extra = ids[0]
                pred = predict_model(contexts[0], kind, params, config)
                train_pred = predict_model({**contexts[0], "xq": contexts[0]["xt"]}, kind, params, config)
                require(np.isfinite(pred).all(), "Nonfinite prediction")
                selections.append({"method": method, "outer_fold": outer, **params, "inner_rmse_t_ha": np.sqrt(loss),
                                   "n_features": x.shape[1], "primary_target_fit": n_primary, "extra_lacuna_fit": n_extra,
                                   "target_fit": len(fit_ids), "target_evaluation": len(query_ids),
                                   "source_allowed": len(source_ids), "source_used": len(source_ids) if params["source_ratio"] > 0 else 0,
                                   "origin": "new_expanded_training"})
                gaps.append({"method": method, "outer_fold": outer, "train_n": len(train_pred), "evaluation_n": len(pred),
                             "train_rmse_t_ha": np.sqrt(np.mean((train_pred - contexts[0]["yt"]) ** 2)),
                             "evaluation_rmse_t_ha": np.sqrt(np.mean((pred - rows.loc[query_ids].yield_t_ha.to_numpy()) ** 2))})
                predictions.append(pd.DataFrame({"obs_id": query_ids, "group_id": rows.loc[query_ids].group_id.to_numpy(),
                                                 "outer_fold": outer, "method": method,
                                                 "yield_t_ha": rows.loc[query_ids].yield_t_ha.to_numpy(float),
                                                 "prediction_t_ha": pred}))
            print(f"fold {outer}: {feature_name} broader populations complete", flush=True)
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(selections), pd.DataFrame(trials), pd.DataFrame(gaps)


def method_parts(method):
    for training in NEW_TRAINING + ["target", "merged"]:
        suffix = "_" + training
        if method.endswith(suffix):
            return method.removesuffix(suffix), training
    raise ValueError(f"Unknown method: {method}")


def comparison_references(method):
    feature, training = method_parts(method)
    references = []
    if training in NEW_TRAINING:
        references.append(f"{feature}_{'target' if training == 'all_lacuna' else 'merged'}")
    if training == "all_zimbabwe":
        references.append(f"{feature}_all_lacuna")
    elif training == "merged":
        references.append(f"{feature}_target")
    if not feature.startswith("legacy_"):
        family = feature.split("_")[0]
        references += [f"{family}_v0_mean_{training}", f"legacy_indices_mean_max_{training}"]
        if "v1_preharvest_mean" in feature:
            references.append(f"{feature.replace('v1_preharvest_mean', 'v1_calendar_mean')}_{training}")
    return [ref for ref in dict.fromkeys(references) if ref != method]


def evaluate(predictions, config):
    """Same-target metrics and paired spatial-group uncertainty for all 52 methods."""
    metrics, folds = [], []
    methods = predictions.method.unique().tolist()
    reference_rows = None
    for method, part in predictions.groupby("method", sort=False):
        require(len(part) == 1504 and part.obs_id.is_unique and part.outer_fold.ne(0).all(), "Wrong evaluation membership")
        identity = part.set_index("obs_id")[["group_id", "outer_fold", "yield_t_ha"]].sort_index()
        if reference_rows is None:
            reference_rows = identity
        else:
            pd.testing.assert_frame_equal(identity, reference_rows, check_exact=True)
        require(np.isfinite(part[["yield_t_ha", "prediction_t_ha"]].to_numpy(float)).all(), "Nonfinite scored values")
        outcome = part.yield_t_ha.to_numpy(float)
        estimate = part.prediction_t_ha.to_numpy(float)
        metrics.append({"method": method, "n": len(part),
                        "sse_t_ha_squared": float(np.sum((estimate - outcome) ** 2)),
                        "sst_t_ha_squared": float(np.sum((outcome - outcome.mean()) ** 2)),
                        **score_predictions(outcome, estimate)})
        for fold, group in part.groupby("outer_fold"):
            folds.append({"method": method, "fold": fold, "n": len(group),
                          **score_predictions(group.yield_t_ha.to_numpy(), group.prediction_t_ha.to_numpy())})
    wide = predictions.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()[methods]
    require(wide.notna().all().all(), "Different evaluation IDs across arms")
    truth = reference_rows.loc[wide.index]
    y = truth.yield_t_ha.to_numpy(float)
    groups = np.unique(truth.group_id)
    square = (wide.to_numpy(float) - y[:, None]) ** 2
    members = [np.flatnonzero(truth.group_id.to_numpy() == group) for group in groups]
    sums = np.array([square[index].sum(axis=0) for index in members])
    sizes = np.array([len(index) for index in members])
    y_sums = np.array([y[index].sum() for index in members])
    y_squares = np.array([(y[index] ** 2).sum() for index in members])
    rng = np.random.default_rng(config["seed"])
    draws = np.array([np.bincount(rng.integers(len(groups), size=len(groups)), minlength=len(groups))
                      for _ in range(config["bootstrap_draws"])])
    n_draw = draws @ sizes
    sse = draws @ sums
    rmse_draw = np.sqrt(sse / n_draw[:, None])
    sst = draws @ y_squares - (draws @ y_sums) ** 2 / n_draw
    require(np.all(sst > 0), "Degenerate bootstrap yield variance")
    r2_draw = 1 - sse / sst[:, None]
    scores = pd.DataFrame(metrics).set_index("method")
    contrasts = []
    for method in methods:
        for reference in comparison_references(method):
            require(reference in methods, f"Missing contrast reference: {reference}")
            j, k = methods.index(method), methods.index(reference)
            low, high = np.quantile(rmse_draw[:, j] - rmse_draw[:, k], [.025, .975])
            rlow, rhigh = np.quantile(r2_draw[:, j] - r2_draw[:, k], [.025, .975])
            contrasts.append({"method": method, "reference": reference,
                              "delta_rmse_t_ha": scores.loc[method, "rmse_t_ha"] - scores.loc[reference, "rmse_t_ha"],
                              "ci_low": low, "ci_high": high,
                              "delta_r2": scores.loc[method, "r2"] - scores.loc[reference, "r2"],
                              "r2_ci_low": rlow, "r2_ci_high": rhigh, "groups": len(groups),
                              "primary_comparison": method == config["primary_method"] and reference == config["primary_reference"]})
    return pd.DataFrame(metrics), pd.DataFrame(folds), pd.DataFrame(contrasts)


def write_report(path, metrics, contrasts, summary):
    """Concise deterministic release summary; detailed interpretation lives in project docs."""
    scores = metrics.set_index("method")
    names = {"v0_mean": "V0 / V3 mean", "v1_preharvest_mean": "V1 crop-date mean",
             "v1_calendar_mean": "V1 calendar mean", "v2_max": "V2 maximum",
             "v3_median": "V3 median", "v3_mode": "V3 modal estimate"}
    lines = ["# Broader Zimbabwe training: results", "",
             "All scores use the same 1,504 original Lacuna 2023 development fields and unchanged nested spatial folds. "
             "RMSE is in t/ha (lower is better); R² is pooled out-of-fold (higher is better). Fold 0 remains reserved.", "",
             "**2022 imagery is insufficient:** all 169 Lacuna 2022 rows have fewer than four observed December–June months "
             "and are excluded. Two 2024 rows also fail this requirement. No missing imagery predictors were imputed. "
             "The actual eligible training pools are 2,097 Lacuna 2023 fields, or those fields plus 4,330 Zimbabwe 2024 fields, "
             "before fold-specific buffers. These results cannot establish the benefit of adding 2022.", "",
             "All-Lacuna adds 212 intercropped rainfed and five irrigated 2023 fields to the original primary pool. "
             "Only 132–150 of these extras are allowed in an outer fit after the 2 km buffer. The comparison therefore changes management coverage.", "",
             "| Predictors | Aggregation | All-Lacuna RMSE | All-Lacuna R² | Full-Zimbabwe RMSE | Full-Zimbabwe R² |",
             "|---|---|---:|---:|---:|---:|"]
    for family, label in [("bands", "10 bands"), ("indices", "5 indices")]:
        for variant in VARIANTS:
            a = scores.loc[f"{family}_{variant}_all_lacuna"]
            b = scores.loc[f"{family}_{variant}_all_zimbabwe"]
            lines.append(f"| {label} | {names[variant]} | {a.rmse_t_ha:.4f} | {a.r2:.4f} | {b.rmse_t_ha:.4f} | {b.r2:.4f} |")
    a = scores.loc["legacy_indices_mean_max_all_lacuna"]
    b = scores.loc["legacy_indices_mean_max_all_zimbabwe"]
    lines.append(f"| 10 index features | Legacy mean + maximum | {a.rmse_t_ha:.4f} | {a.r2:.4f} | {b.rmse_t_ha:.4f} | {b.r2:.4f} |")
    new = metrics[metrics.method.str.endswith(tuple(NEW_TRAINING))].sort_values("rmse_t_ha")
    best = new.iloc[0]
    primary = contrasts[contrasts.primary_comparison].iloc[0]
    lines += ["", f"Best observed new arm: **{best.method}**, RMSE **{best.rmse_t_ha:.4f}**, R² **{best.r2:.4f}**. "
              "This ranking is exploratory; many methods share the same development data.", "",
              f"Prespecified ten-band preharvest comparison, full-Zimbabwe minus all-Lacuna: RMSE difference "
              f"**{primary.delta_rmse_t_ha:+.4f}** (95% spatial-group interval **[{primary.ci_low:+.4f}, {primary.ci_high:+.4f}]**); "
              f"R² difference **{primary.delta_r2:+.4f}**.", "",
              "The full-Zimbabwe model uses separate provider calibration and a tuned 2024 weight that may be zero. "
              "Actual crop dates are available for Lacuna; 2024 uses a December–March proxy. The calendar arm applies that proxy to both providers.", "",
              "R² = 1 − SSE/SST, using all 1,504 out-of-fold predictions together. `metrics.csv` includes SSE and SST for an exact audit. "
              "A mean of fold-level R² values is a different statistic.", "",
              "Files: `coverage_summary.csv` and `eligibility_audit.csv` document exclusions; `features.parquet` and "
              "`monthly_observations.parquet` contain actual features and their observations; `fit_memberships.csv` and "
              "`extra_lacuna_spatial_permissions.csv` document training access. `metrics.csv` contains all 52 arms, including "
              "26 unchanged step 14 controls. `predictions.csv`, `fold_metrics.csv`, `paired_differences.csv`, "
              "`selected_parameters.csv` and `tuning.csv` preserve results and choices. `PROTOCOL.md` and `manifest.json` "
              "record methods, sources, pinned inputs and output hashes.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def input_hashes(config_path):
    paths = ["data/cropyield.duckdb", "data/processed/labels_v1.parquet", "configs/team_database_v1.json",
             "configs/zimbabwe_merge_v1.json", "configs/zimbabwe_aggregation_v1.json", "data/splits/manifest.json",
             "data/splits/zimbabwe_lacuna_2022_2023__s1_cc2km.csv", "data/splits/zimbabwe_lacuna_2022_2023__s2_region.csv",
             "data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson", "data/metadata/zimbabwe.json",
             "data/raw/vision_guided_yield_estimation/metadata.csv",
             "src/cropyield/__init__.py", "src/cropyield/data/handoff.py", "src/cropyield/data/labels.py",
             "src/cropyield/data/cohorts.py", "src/cropyield/data/xy.py", "src/cropyield/eval/splits.py",
             "src/cropyield/experiments/zimbabwe_merge.py", "src/cropyield/experiments/zimbabwe_diagnosis.py",
             "src/cropyield/experiments/zimbabwe_aggregation.py", "src/cropyield/experiments/zimbabwe_multiyear.py",
             "scripts/step15_compare_zimbabwe_multiyear.py", "docs/zimbabwe/MULTIYEAR_PROTOCOL.md",
             "docs/zimbabwe/AGGREGATION_PROTOCOL.md", "requirements.txt", "pyproject.toml"]
    for release in [PRIOR, CONTROLS]:
        paths += [str(path.relative_to(ROOT)) for path in release.iterdir() if path.is_file()]
    paths.append(str(config_path.relative_to(ROOT)) if config_path.is_relative_to(ROOT) else str(config_path))
    return {name: sha256(ROOT / name) for name in sorted(set(paths))}


def run_experiment(output=OUTPUT, config_path=CONFIG):
    config = json.loads(config_path.read_text())
    require(config["target_folds"] == [1, 2, 3, 4] and config["reserved_fold"] == 0, "Preserve frozen splits")
    require(config["variants"] == VARIANTS and config["feature_families"] == ["bands", "indices"], "Unexpected features")
    require(config["training_sets"] == NEW_TRAINING and config["minimum_clear_months"] == 4, "Unexpected training design")
    require(config["auxiliary_buffer_km"] == 2.0, "Preserve 2 km source buffering")
    before = input_hashes(config_path)
    rows, features, audit, eligibility, monthly, membership, permission = load_inputs(config)
    extra_permission, fitting = build_permissions(rows, membership, permission, config)
    require(extra_permission.obs_id.nunique() == 217, "Eligible additional Lacuna population changed")
    controls = pd.read_csv(CONTROLS / "predictions.csv", dtype={"group_id": str})
    expected_controls = {f"{feature}_{training}" for feature in features for training in ["target", "merged"]}
    require(set(controls.method) == expected_controls and len(controls) == 26 * 1504, "Historical controls changed")
    # Historical CSVs contain 12 significant decimal digits. Preserve their outcomes exactly
    # across all new predictions so identity checks and paired scores have one frozen truth.
    frozen_truth = controls.drop_duplicates("obs_id").set_index("obs_id").yield_t_ha
    np.testing.assert_allclose(rows.loc[frozen_truth.index].yield_t_ha, frozen_truth, atol=1e-9, rtol=0)
    with threadpool_limits(limits=1):
        new_predictions, selected, tuning, gaps = run_models(rows, features, fitting, config)
        new_predictions["yield_t_ha"] = new_predictions.obs_id.map(frozen_truth)
        predictions = pd.concat([controls, new_predictions], ignore_index=True)
        require(predictions.method.nunique() == 52, "Wrong number of comparison arms")
        metrics, folds, contrasts = evaluate(predictions, config)
    old_selected = pd.read_csv(CONTROLS / "selected_parameters.csv")
    old_selected["primary_target_fit"] = old_selected.target_fit
    old_selected["extra_lacuna_fit"] = 0
    old_selected["origin"] = "frozen_step14_control"
    selected = pd.concat([old_selected, selected], ignore_index=True)
    old_tuning = pd.read_csv(CONTROLS / "tuning.csv").assign(origin="frozen_step14_control")
    tuning = pd.concat([old_tuning, tuning], ignore_index=True)
    coverage = rows.reset_index().groupby(["domain", "cohort", "season_year"], as_index=False).agg(
        catalog_rows=("obs_id", "size"), model_eligible_rows=("model_eligible", "sum"),
        minimum_observed_months=("observed_common_season_months", "min"),
        maximum_observed_months=("observed_common_season_months", "max"))
    coverage["excluded_rows"] = coverage.catalog_rows - coverage.model_eligible_rows
    metadata = []
    for method in predictions.method.unique():
        feature, training = method_parts(method)
        metadata.append({"method": method, "feature_set": feature, "training_population": training,
                         "n_features": features[feature].shape[1], "origin": "new_expanded_training" if training in NEW_TRAINING else "frozen_step14_control",
                         "eligible_lacuna_years": "2023", "eligible_source_years": "2024" if training in ["merged", "all_zimbabwe"] else "",
                         "evaluation_year": 2023, "evaluation_n": 1504})
    summary = {"catalog_rows": len(rows), "requested_lacuna_years": [2022, 2023], "requested_zimbabwe_years": [2022, 2023, 2024],
               "actual_lacuna_training_years": [2023], "actual_zimbabwe_training_years": [2023, 2024],
               "lacuna_2022_excluded_insufficient_imagery": 169, "source_2024_excluded_insufficient_imagery": 2,
               "eligible_lacuna": 2097, "eligible_source_2024": 4330, "eligible_extra_lacuna": 217,
               "extra_intercropped_rainfed": 212, "extra_irrigated": 5,
               "target_evaluation": 1504, "target_reserved": 376, "historical_control_arms": 26, "new_arms": 26,
               "arms": 52, "imagery_imputation": False, "coverage": coverage.to_dict("records"),
               "extra_lacuna_outer_fit_counts": {str(outer): int(extra_permission[extra_permission.outer_fold.eq(outer)
                    & extra_permission.inner_fold.eq(0)].allowed_by_spatial_rule.sum()) for outer in config["target_folds"]}}
    with tempfile.TemporaryDirectory(prefix="zimbabwe-multiyear-") as temporary:
        stage = Path(temporary)
        tables = {"observations": rows.reset_index(), "window_audit": audit.reset_index(), "eligibility_audit": eligibility,
                  "coverage_summary": coverage, "extra_lacuna_spatial_permissions": extra_permission,
                  "fit_memberships": fitting, "method_metadata": pd.DataFrame(metadata), "predictions": predictions,
                  "selected_parameters": selected, "tuning": tuning, "training_outer_diagnostics": gaps,
                  "metrics": metrics, "fold_metrics": folds, "paired_differences": contrasts}
        for name, table in tables.items():
            csv_write(table, stage / f"{name}.csv")
        for name in ["target_memberships.csv", "source_spatial_permissions.csv"]:
            (stage / name).write_bytes((PRIOR / name).read_bytes())
        (stage / "historical_control_predictions.csv").write_bytes((CONTROLS / "predictions.csv").read_bytes())
        dictionary = {name: [f"{name}__{column}" for column in frame] for name, frame in features.items()}
        pd.concat([frame.set_axis(dictionary[name], axis=1) for name, frame in features.items()], axis=1).to_parquet(stage / "features.parquet", index=True)
        monthly.to_parquet(stage / "monthly_observations.parquet", index=False)
        json_write(dictionary, stage / "feature_dictionary.json")
        json_write(summary, stage / "data_summary.json")
        json_write(config, stage / "config.json")
        (stage / "PROTOCOL.md").write_bytes(PROTOCOL.read_bytes())
        write_report(stage / "RESULTS.md", metrics, contrasts, summary)
        require(before == input_hashes(config_path), "Inputs changed during run")
        manifest = {"config": config, "inputs": before,
                    "base_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    "source_hashes_record_actual_working_tree": True, "python": platform.python_version(),
                    "versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "scikit-learn", "duckdb", "pyarrow"]},
                    "outputs": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in sorted(stage.iterdir())}}
        json_write(manifest, stage / "manifest.json")
        publish_release(stage, output)
    print(metrics.round(5).to_string(index=False), flush=True)
    print(contrasts[contrasts.primary_comparison].to_string(index=False), flush=True)
    return summary
