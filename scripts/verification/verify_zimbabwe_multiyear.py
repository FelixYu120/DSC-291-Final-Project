"""Independently verify the same-split Zimbabwe multiyear release.

No experiment implementation is imported. Feature windows, eligibility, spherical
distances, scores, and selected Ridge predictions are recomputed from exports.
Spearman alone permits 5e-6 error because twelve-significant-digit CSV rounding
can create rank ties. R², RMSE and the other continuous scores remain strict.

Under the team-rule v2 config (``window_anchor: calendar``, ``training_rows: include_primary``)
it also checks that no crop date is read for features or eligibility, that every fitted row is
``labels_v1.include_primary`` (read from the frozen labels), and that each new arm marked
``identical_to`` equals its step 14 control. Code/doc/config inputs that differ in the working tree
are accepted only if the recorded bytes exist in Git history for this release or differ by CRLF only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.neighbors import BallTree
from threadpoolctl import threadpool_limits


ROOT = Path(__file__).resolve().parents[2]
BANDS = ["b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12"]
INDICES = ["ndvi", "gcvi", "mtci", "ndvi705", "ndvi740"]
EARTH_RADIUS_KM = 6371.0088
SPEARMAN_TOLERANCE = 5e-6


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def close(actual, expected, label, atol=1e-9, rtol=0):
    np.testing.assert_allclose(
        np.asarray(actual, float), np.asarray(expected, float),
        atol=atol, rtol=rtol, equal_nan=True, err_msg=label,
    )


def release_commits(release):
    try:
        relative = (release / "manifest.json").relative_to(ROOT).as_posix()
        return subprocess.run(["git", "-C", str(ROOT), "log", "--all", "--format=%H", "--", relative],
                              capture_output=True, text=True, check=True).stdout.split()
    except (ValueError, OSError, subprocess.CalledProcessError):
        return []


def input_source(name, expected, commits):
    """Where the recorded input bytes were found; data files must match the working tree."""
    path = ROOT / name
    if path.is_file() and sha(path) == expected:
        return "working_tree"
    if name.startswith("data/"):
        return None
    if path.is_file() and hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected:
        return "working_tree_crlf_checkout"
    for commit in commits:
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{name}"], capture_output=True)
        if blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == expected:
            return "recorded_git_history"
    return None


def independent_mode(values):
    """Recursive shortest-half estimator, with an equal average over ties."""
    ordered = sorted(float(value) for value in values if np.isfinite(value))
    count = len(ordered)
    if count == 0:
        return np.nan
    if count < 3:
        return sum(ordered) / count
    keep = (count + 1) // 2
    intervals = [ordered[i:i + keep] for i in range(count - keep + 1)]
    widths = [part[-1] - part[0] for part in intervals]
    shortest = min(widths)
    answers = [independent_mode(part) for part, width in zip(intervals, widths)
               if abs(width - shortest) <= 1e-12 + 1e-12 * abs(shortest)]
    return sum(answers) / len(answers)


def scores(part):
    truth = part.yield_t_ha.to_numpy(float)
    prediction = part.prediction_t_ha.to_numpy(float)
    error = prediction - truth
    return {
        "rmse_t_ha": np.sqrt(np.mean(error ** 2)),
        "mae_t_ha": np.mean(np.abs(error)),
        "bias_t_ha": np.mean(error),
        "r2": 1 - np.sum(error ** 2) / np.sum((truth - truth.mean()) ** 2),
        "spearman": spearmanr(truth, prediction).statistic,
    }


def reconstruct_features(out, observations, config, dictionary):
    monthly = pd.read_parquet(out / "monthly_observations.parquet")
    require(not monthly.duplicated(["obs_id", "month"]).any(), "Duplicate monthly key")
    require(set(monthly.obs_id) == set(observations.index), "Monthly IDs differ from catalog")
    require(monthly.groupby("obs_id").size().eq(7).all(), "Incomplete December–June spine")
    crop_dates = config.get("window_anchor", "crop_dates") == "crop_dates"
    variants = config.get("variants", ["v0_mean", "v1_preharvest_mean", "v1_calendar_mean", "v2_max", "v3_median", "v3_mode"])
    frame = monthly.merge(observations[["season_year", "plant_date", "harvest_date"] if crop_dates else ["season_year"]],
                          left_on="obs_id", right_index=True, validate="many_to_one")
    frame["acquired"] = pd.to_datetime(frame.acquired)
    start = pd.to_datetime((frame.season_year - 1).astype(str) + "-12-01")
    end = pd.to_datetime(frame.season_year.astype(str) + "-07-01")
    cutoff = pd.to_datetime(frame.season_year.astype(str) + "-" + config["calendar_cutoff_month_day"])
    finite = np.isfinite(frame[BANDS + INDICES].to_numpy(float)).all(axis=1)
    require(np.array_equal(finite, ~frame.missing.astype(bool)), "Monthly missing flags differ from complete finite values")
    require(frame.loc[finite, "acquired"].notna().all(), "Available imagery lacks acquisition date")
    valid = finite & ~frame.missing.astype(bool) & frame.acquired.ge(start) & frame.acquired.lt(end)
    require(np.array_equal(valid, finite), "Available imagery falls outside the common season")
    calendar = valid & frame.acquired.lt(cutoff)
    masks = {"season": valid, "calendar": calendar}
    if crop_dates:
        planted = pd.to_datetime(frame.plant_date)
        harvested = pd.to_datetime(frame.harvest_date)
        lower = planted.where(planted.notna() & planted.gt(start), start)
        upper = harvested.fillna(cutoff)
        masks["preharvest"] = valid & frame.acquired.ge(lower) & frame.acquired.lt(upper)
    counts = pd.DataFrame(index=observations.index)
    for scope, mask in masks.items():
        counts[f"n_{scope}"] = frame.loc[mask].groupby("obs_id").size().reindex(counts.index, fill_value=0)
    saved_audit = pd.read_csv(out / "window_audit.csv").set_index("obs_id").loc[counts.index]
    close(saved_audit[counts.columns], counts, "Monthly window counts", atol=0)
    definitions = {
        "v0_mean": (valid, "mean"), "v1_calendar_mean": (calendar, "mean"), "v2_max": (valid, "max"),
        "v3_median": (valid, "median"), "v3_mode": (valid, independent_mode),
    }
    if crop_dates:
        definitions["v1_preharvest_mean"] = (masks["preharvest"], "mean")
    definitions = {name: definitions[name] for name in variants}
    expected = {}
    for variant, (mask, stat) in definitions.items():
        grouped = frame.loc[mask].groupby("obs_id")[BANDS + INDICES].agg(stat).reindex(counts.index)
        for family, variables in [("bands", BANDS), ("indices", INDICES)]:
            key = f"{family}_{variant}"
            expected[key] = grouped[variables].set_axis(dictionary[key], axis=1)
    legacy = pd.DataFrame(index=counts.index)
    for index in INDICES:
        for stat in ["max", "mean"]:
            name = f"{index}_season_{stat}"
            legacy[f"legacy_indices_mean_max__{name}"] = frame.loc[valid].groupby("obs_id")[index].agg(stat)
    expected["legacy_indices_mean_max"] = legacy[dictionary["legacy_indices_mean_max"]]
    wide = pd.read_parquet(out / "features.parquet")
    require(wide.index.is_unique and set(wide.index) == set(counts.index), "Feature IDs differ")
    require(set(dictionary) == set(expected), "Unexpected feature family")
    for name, reconstructed in expected.items():
        close(wide.loc[counts.index, dictionary[name]], reconstructed,
              f"Feature reconstruction: {name}", atol=1e-12, rtol=1e-12)
    return wide, counts, expected


def independent_prediction(x, observations, fit_ids, source_ids, query_ids, alpha, ratio):
    """Replay clipping, scaling and Ridge via normal equations, without production helpers."""
    fit = x.loc[fit_ids].to_numpy(float)
    source = x.loc[source_ids].to_numpy(float)
    query = x.loc[query_ids].to_numpy(float)
    require(all(np.isfinite(values).all() for values in [fit, source, query]),
            "A selected model consumes unavailable imagery")
    low, high = np.quantile(fit, [.01, .99], axis=0)
    clipped = np.clip(fit, low, high)
    mean, scale = clipped.mean(axis=0), clipped.std(axis=0)
    scale[scale < 1e-12] = 1
    xt, xs, xq = [(np.clip(values, low, high) - mean) / scale for values in [fit, source, query]]
    yt = observations.loc[fit_ids, "yield_t_ha"].to_numpy(float)
    ys = observations.loc[source_ids, "yield_t_ha"].to_numpy(float)
    target_mean = yt.mean()
    target_center = xt.mean(axis=0)
    zt, zq = xt - target_center, xq - target_center
    if ratio == 0 or len(source_ids) == 0:
        coefficients = np.linalg.solve(zt.T @ zt + alpha * np.eye(zt.shape[1]), zt.T @ (yt - target_mean))
        return np.maximum(target_mean + zq @ coefficients, 0)
    source_mean, source_center = ys.mean(), xs.mean(axis=0)
    zs = xs - source_center
    target_scale, source_scale = max(yt.std(), 1e-12), max(ys.std(), 1e-12)
    design = np.vstack([
        np.column_stack([zt, zt, np.zeros_like(zt)]),
        np.column_stack([zs, np.zeros_like(zs), zs]),
    ]) / np.sqrt(2)
    outcomes = np.r_[(yt - target_mean) / target_scale, (ys - source_mean) / source_scale]
    weights = np.r_[np.ones(len(yt)), np.full(len(ys), len(yt) * ratio / len(ys))]
    normal = design.T @ (design * weights[:, None]) + alpha * np.eye(design.shape[1])
    coefficients = np.linalg.solve(normal, design.T @ (outcomes * weights))
    query_design = np.column_stack([zq, zq, np.zeros_like(zq)]) / np.sqrt(2)
    return np.maximum(target_mean + target_scale * (query_design @ coefficients), 0)


def verify(out):
    original = ROOT / "data/runs/zimbabwe_merge_v1"
    manifest = json.loads((out / "manifest.json").read_text())
    config = manifest["config"]
    prior = ROOT / config.get("controls_release", "data/runs/zimbabwe_aggregation_v1")
    anchor = config.get("window_anchor", "crop_dates")
    rule = config.get("training_rows", "all_screened")
    require(anchor in {"crop_dates", "calendar"} and rule in {"all_screened", "include_primary"}, "Unknown team-rule switch")
    if anchor == "calendar":
        require("v1_preharvest_mean" not in config["variants"], "Crop-date window is a model candidate")
        require("preharvest" not in config["primary_method"] + config["primary_reference"], "Crop-date headline comparison")
    commits = release_commits(out)
    input_sources = {}
    for name, expected in manifest["inputs"].items():
        found = input_source(name, expected, commits)
        require(found is not None, f"Input hash differs: {name}")
        input_sources[found] = input_sources.get(found, 0) + 1
    for name, expected in manifest["outputs"].items():
        require(sha(out / name) == expected["sha256"], f"Output hash differs: {name}")
        require((out / name).stat().st_size == expected["bytes"], f"Output size differs: {name}")
    for name in ["target_memberships.csv", "source_spatial_permissions.csv"]:
        require((out / name).read_bytes() == (original / name).read_bytes(), f"Original split bytes changed: {name}")
        require((out / name).read_bytes() == (prior / name).read_bytes(), f"Step14 split bytes changed: {name}")
    require((out / "historical_control_predictions.csv").read_bytes() == (prior / "predictions.csv").read_bytes(),
            "Historical control prediction copy changed")
    observations = pd.read_csv(out / "observations.csv", dtype={"group_id": str}).set_index("obs_id")
    require(observations.index.is_unique and len(observations) == 6598, "Wrong screened catalog")
    frozen_labels = pd.read_parquet(ROOT / "data/processed/labels_v1.parquet").set_index("obs_id")
    labels = frozen_labels[frozen_labels.cohort.isin(["zimbabwe_lacuna_2022_2023", "zimbabwe_2024"])]
    require(set(observations.index) == set(labels.index), "Catalog differs from screened Zimbabwe labels")
    close(observations.yield_t_ha, labels.loc[observations.index].yield_kg_ha / 1000, "Harmonized outcomes", atol=1e-9)
    close(observations[["lat", "lon"]], labels.loc[observations.index, ["lat", "lon"]], "Coordinates", atol=1e-9)
    for name in ["season_year", "cohort"]:
        require(np.array_equal(observations[name], labels.loc[observations.index, name]), f"Label metadata differs: {name}")
    for name in ["plant_date", "harvest_date"]:
        pd.testing.assert_series_equal(pd.to_datetime(observations[name]).astype("datetime64[ns]"),
                                       pd.to_datetime(labels.loc[observations.index, name]).astype("datetime64[ns]"),
                                       check_names=False)
    dictionary = json.loads((out / "feature_dictionary.json").read_text())
    wide, counts, reconstructed = reconstruct_features(out, observations, config, dictionary)
    finite_features = pd.DataFrame({name: np.isfinite(frame.to_numpy()).all(axis=1)
                                    for name, frame in reconstructed.items()}, index=observations.index)
    minimum_months = config.get("minimum_clear_months", 4)
    require(minimum_months == 4, "Four-month season threshold changed")
    eligible = counts.n_season.ge(minimum_months) & finite_features.all(axis=1)
    require(eligible.equals(observations.model_eligible.rename(eligible.name)), "Catalog model eligibility differs")
    require(eligible.groupby(observations.season_year).sum().to_dict() == {2022: 0, 2023: 2097, 2024: 4330},
            "Unexpected eligible year counts")
    require(counts.loc[observations.season_year.eq(2022), "n_season"].value_counts().to_dict() == {1: 101, 2: 68},
            "2022 imagery availability differs")
    eligibility = pd.read_csv(out / "eligibility_audit.csv")
    require(not eligibility.duplicated(["feature_set", "obs_id"]).any(), "Duplicate eligibility audit")
    require(set(eligibility.feature_set) == set(dictionary), "Incomplete feature eligibility audit")
    for name, part in eligibility.groupby("feature_set"):
        part = part.set_index("obs_id").loc[observations.index]
        require(len(part) == len(observations), f"Eligibility rows missing: {name}")
        close(part.observed_season_months, counts.n_season, f"Season availability: {name}", atol=0)
        require(np.array_equal(part.finite_features, finite_features[name]), f"Finite-feature audit: {name}")
        require(np.array_equal(part.model_eligible, eligible), f"Common eligibility audit: {name}")
        require(part.loc[~eligible, "exclusion_reason"].notna().all(), f"Missing exclusion reason: {name}")
    membership = pd.read_csv(out / "target_memberships.csv", dtype={"group_id": str})
    source_permission = pd.read_csv(out / "source_spatial_permissions.csv")
    extra_permission = pd.read_csv(out / "extra_lacuna_spatial_permissions.csv")
    fit_membership = pd.read_csv(out / "fit_memberships.csv")
    old_obs = pd.read_csv(prior / "observations.csv").set_index("obs_id")
    primary_ids = set(old_obs.index[old_obs.domain.eq("lacuna")])
    evaluation_ids = set(old_obs.index[old_obs.domain.eq("lacuna") & old_obs.fold.isin([1, 2, 3, 4])])
    reserved_ids = old_obs.index[old_obs.domain.eq("lacuna") & old_obs.fold.eq(0)].tolist()
    primary_flag = frozen_labels.include_primary.reindex(observations.index).fillna(False).astype(bool)
    pool = eligible & (primary_flag if rule == "include_primary" else True)
    extra_ids = set(observations.index[pool & observations.cohort.eq("zimbabwe_lacuna_2022_2023")]) - primary_ids
    expected_extra = 217 if rule == "all_screened" else 0
    require(len(evaluation_ids) == 1504 and len(reserved_ids) == 376 and len(extra_ids) == expected_extra, "Unexpected population")
    require(primary_flag.loc[list(primary_ids)].all(), "Primary Lacuna rows outside include_primary")
    require(set(extra_permission.obs_id) == extra_ids, "Extra permissions differ from eligible supplementary Lacuna")
    require(not extra_permission.duplicated(["obs_id", "outer_fold", "inner_fold"]).any(), "Duplicate extra permission")
    require(not fit_membership.duplicated(["obs_id", "outer_fold", "inner_fold"]).any(), "Duplicate fit membership")
    split_ids, extra_counts = {}, {}
    for outer in [1, 2, 3, 4]:
        outer_eval = membership.loc[membership.outer_fold.eq(outer) & membership.inner_fold.eq(0)
                                    & membership.role.eq("evaluation"), "obs_id"].tolist()
        for inner in range(4):
            subset = membership[membership.outer_fold.eq(outer) & membership.inner_fold.eq(inner)]
            original_fit = subset.loc[subset.role.eq("fit"), "obs_id"].tolist()
            query = subset.loc[subset.role.eq("evaluation" if inner == 0 else "validation"), "obs_id"].tolist()
            protected = reserved_ids + outer_eval + (query if inner else [])
            source = source_permission[source_permission.outer_fold.eq(outer)
                                       & source_permission.inner_fold.eq(inner)
                                       & source_permission.allowed_by_spatial_rule].obs_id.tolist()
            if rule == "include_primary":
                source = [obs_id for obs_id in source if pool.loc[obs_id]]
            permission = extra_permission[extra_permission.outer_fold.eq(outer) & extra_permission.inner_fold.eq(inner)]
            require(set(permission.obs_id) == extra_ids, f"Incomplete extra permissions: {outer}/{inner}")
            # Frozen label coordinates retain precision that the observation CSV
            # rounds away; their agreement with the exported coordinates is checked above.
            tree = BallTree(np.radians(labels.loc[protected, ["lat", "lon"]].to_numpy()), metric="haversine")
            distance = (tree.query(np.radians(labels.loc[permission.obs_id, ["lat", "lon"]].to_numpy()), k=1)[0][:, 0]
                        * EARTH_RADIUS_KM if len(permission) else np.array([]))
            close(permission.minimum_distance_to_protected_km, distance, f"Haversine buffer: {outer}/{inner}", atol=1e-8)
            allowed = distance >= config["auxiliary_buffer_km"]
            require(np.array_equal(permission.allowed_by_spatial_rule, allowed), f"Wrong extra spatial permission: {outer}/{inner}")
            extra = permission.loc[permission.allowed_by_spatial_rule, "obs_id"].tolist()
            fits = fit_membership[fit_membership.outer_fold.eq(outer) & fit_membership.inner_fold.eq(inner)]
            require({"primary_fit", "source_allowed", "query"} <= set(fits.role)
                    <= {"primary_fit", "extra_lacuna_fit", "source_allowed", "query"}, "Unknown fit role")
            expected_roles = {"primary_fit": original_fit, "extra_lacuna_fit": extra, "source_allowed": source, "query": query}
            for role, expected in expected_roles.items():
                actual = fits[fits.role.eq(role)].sort_values("position").obs_id.tolist()
                require(actual == expected, f"Fit membership/order differs: {outer}/{inner}/{role}")
            require(eligible.loc[original_fit + extra + source + query].all(), "Ineligible field included in a model")
            if rule == "include_primary":
                require(primary_flag.loc[original_fit + extra + source].all(), "Fit holds rows outside labels_v1.include_primary")
            require(set(original_fit + extra + source).isdisjoint(protected), "Protected observation included in fit")
            split_ids[outer, inner] = (original_fit + extra, source, query)
            extra_counts[f"{outer}/{inner}"] = len(extra)
    pred = pd.read_csv(out / "predictions.csv", dtype={"group_id": str})
    metrics = pd.read_csv(out / "metrics.csv").set_index("method")
    folds = pd.read_csv(out / "fold_metrics.csv").set_index(["method", "fold"])
    n_arms = 4 * len(dictionary)
    require(pred.method.nunique() == n_arms and set(metrics.index) == set(pred.method), f"Expected {n_arms} arms")
    if anchor == "calendar":
        require(not any("preharvest" in name for name in list(dictionary) + list(pred.method)), "Crop-date feature in a model")
    expected_methods = {f"{name}_{training}" for name in dictionary
                        for training in ["target", "merged", "all_lacuna", "all_zimbabwe"]}
    require(set(pred.method) == expected_methods, "Unexpected comparison methods")
    require(len(pred) == n_arms * 1504 and np.isfinite(pred.prediction_t_ha).all(), "Wrong prediction population")
    maximum_spearman_error = 0.0
    for method, part in pred.groupby("method"):
        require(part.obs_id.is_unique and set(part.obs_id) == evaluation_ids, f"Evaluation IDs differ: {method}")
        require(part.groupby("outer_fold").size().to_dict() == {1: 376, 2: 376, 3: 376, 4: 376}, f"Evaluation fold sizes: {method}")
        require(np.array_equal(part.outer_fold, old_obs.loc[part.obs_id, "fold"]), f"Original evaluation folds changed: {method}")
        require(np.array_equal(part.group_id, observations.loc[part.obs_id, "group_id"]), f"Evaluation groups changed: {method}")
        require(metrics.loc[method, "n"] == 1504, f"Pooled metric count: {method}")
        close(part.yield_t_ha, observations.loc[part.obs_id, "yield_t_ha"], f"Outcome mismatch: {method}")
        for score, expected in scores(part).items():
            tolerance = SPEARMAN_TOLERANCE if score == "spearman" else 1e-9
            close(metrics.loc[method, score], expected, f"Pooled score: {method}/{score}", atol=tolerance)
            if score == "spearman":
                maximum_spearman_error = max(maximum_spearman_error, abs(float(metrics.loc[method, score]) - expected))
        truth = part.yield_t_ha.to_numpy(float)
        prediction = part.prediction_t_ha.to_numpy(float)
        close(metrics.loc[method, "sse_t_ha_squared"], np.sum((prediction - truth) ** 2),
              f"Pooled SSE: {method}", atol=1e-7)
        close(metrics.loc[method, "sst_t_ha_squared"], np.sum((truth - truth.mean()) ** 2),
              f"Pooled SST: {method}", atol=1e-7)
        for outer, group in part.groupby("outer_fold"):
            require(folds.loc[(method, outer), "n"] == 376, f"Fold metric count: {method}/{outer}")
            for score, expected in scores(group).items():
                tolerance = SPEARMAN_TOLERANCE if score == "spearman" else 1e-9
                close(folds.loc[(method, outer), score], expected, f"Fold score: {method}/{outer}/{score}", atol=tolerance)
                if score == "spearman":
                    maximum_spearman_error = max(maximum_spearman_error, abs(float(folds.loc[(method, outer), score]) - expected))
    controls = pd.read_csv(prior / "predictions.csv", dtype={"group_id": str})
    require(controls.method.nunique() == 2 * len(dictionary), "Unexpected step14 controls")
    for method, part in controls.groupby("method"):
        actual = pred[pred.method.eq(method)].set_index("obs_id").sort_index()
        expected = part.set_index("obs_id").sort_index()
        pd.testing.assert_frame_equal(actual[expected.columns], expected, check_exact=True)
    old_metrics = pd.read_csv(prior / "metrics.csv").set_index("method")
    # Step14 scored full-precision predictions before exporting them with twelve
    # significant digits. Step15 reuses those CSV predictions; only rounding can differ.
    numeric_columns = [name for name in old_metrics.columns if name != "spearman"]
    close(metrics.loc[old_metrics.index, numeric_columns], old_metrics[numeric_columns],
          "Step14 control scores preserved up to CSV rounding", atol=1e-10)
    old_spearman_error = np.abs(metrics.loc[old_metrics.index, "spearman"] - old_metrics.spearman)
    close(metrics.loc[old_metrics.index, "spearman"], old_metrics.spearman,
          "Step14 Spearman preserved up to CSV rank ties", atol=SPEARMAN_TOLERANCE)
    maximum_spearman_error = max(maximum_spearman_error, float(old_spearman_error.max()))
    selections = pd.read_csv(out / "selected_parameters.csv")
    tuning = pd.read_csv(out / "tuning.csv")
    require(len(selections) == n_arms * 4 and not selections.duplicated(["method", "outer_fold"]).any(), "Wrong selections")
    replayed = 0
    largest_replay_error = 0.0
    for selected in selections.itertuples():
        if not selected.method.endswith(("_all_lacuna", "_all_zimbabwe")):
            continue
        feature_name = selected.method.removesuffix("_all_lacuna").removesuffix("_all_zimbabwe")
        require(feature_name in dictionary, f"Unknown selected feature set: {feature_name}")
        fit, source, query = split_ids[selected.outer_fold, 0]
        require(selected.target_fit == len(fit) and selected.primary_target_fit == 1128
                and selected.extra_lacuna_fit == len(fit) - 1128 and selected.target_evaluation == 376,
                "Selected target fit counts differ")
        require(selected.source_allowed == len(source)
                and selected.source_used == (len(source) if selected.source_ratio > 0 else 0), "Selected source counts differ")
        if selected.method.endswith("_all_lacuna"):
            require(selected.source_ratio == 0, "Lacuna-only arm uses 2024")
        candidates = tuning[tuning.method.eq(selected.method) & tuning.outer_fold.eq(selected.outer_fold)]
        require(len(candidates) > 0, "Missing tuning candidates")
        require(selected.inner_rmse_t_ha <= candidates.inner_rmse_t_ha.min() + 1e-9, "Selected tuning loss is not minimum")
        require(((candidates.alpha == selected.alpha) & (candidates.source_ratio == selected.source_ratio)).any(),
                "Selected parameters absent from tuning grid")
        estimated = independent_prediction(wide[dictionary[feature_name]], observations, fit, source, query,
                                           selected.alpha, selected.source_ratio)
        saved = pred[pred.method.eq(selected.method) & pred.outer_fold.eq(selected.outer_fold)].set_index("obs_id").loc[query]
        close(saved.prediction_t_ha, estimated, f"Independent Ridge replay: {selected.method}/{selected.outer_fold}", atol=1e-8)
        largest_replay_error = max(largest_replay_error, float(np.abs(saved.prediction_t_ha.to_numpy() - estimated).max()))
        replayed += 1
    require(replayed == 2 * len(dictionary) * 4, f"Expected {2 * len(dictionary) * 4} new selected fits")
    identity = {}
    if rule == "include_primary":
        # Under the team rule both broader pools collapse to step 14 rows; check each marked twin directly.
        recorded = pd.read_csv(out / "arm_identity.csv", keep_default_na=False).set_index("method")
        tolerance = config["identity_tolerance_t_ha"]
        for method in recorded.index:
            twin = method.replace("_all_lacuna", "_target").replace("_all_zimbabwe", "_merged")
            a = pred[pred.method.eq(method)].set_index("obs_id").prediction_t_ha.sort_index()
            b = pred[pred.method.eq(twin)].set_index("obs_id").prediction_t_ha.sort_index()
            difference = float(np.abs(a - b).max())
            require(recorded.loc[method, "twin_control"] == twin, f"Wrong twin: {method}")
            require(bool(recorded.loc[method, "identical"]) == (difference <= tolerance), f"Identity flag differs: {method}")
            require(recorded.loc[method, "identical_to"] == (twin if difference <= tolerance else ""), f"identical_to differs: {method}")
            identity[method] = difference
        metadata = pd.read_csv(out / "method_metadata.csv", keep_default_na=False).set_index("method")
        require(all(metadata.loc[m, "identical_to"] == recorded.loc[m, "identical_to"] for m in recorded.index), "Metadata identity differs")
    return {
        "all_checks_passed": True, "catalog_rows": len(observations), "model_arms": n_arms,
        "predictions": len(pred), "same_evaluation_ids_per_arm": 1504, "model_arms_checked": n_arms,
        "eligible_by_harvest_year": {str(k): int(v) for k, v in eligible.groupby(observations.season_year).sum().items()},
        "feature_sets_independently_reconstructed": len(dictionary),
        "extra_lacuna_permissions_checked": len(extra_permission), "extra_lacuna_allowed_by_split": extra_counts,
        "original_memberships_and_source_permissions": "byte-identical",
        "step14_control_arms": f"{2 * len(dictionary)} prediction tables exactly preserved; continuous metrics within 1e-10; Spearman within 5e-6",
        "spearman_csv_tie_tolerance": SPEARMAN_TOLERANCE,
        "maximum_observed_spearman_error": maximum_spearman_error,
        "selected_fits_independently_replayed": replayed, "maximum_prediction_replay_error": largest_replay_error,
        "input_hashes": len(manifest["inputs"]), "input_sources": input_sources, "output_hashes": len(manifest["outputs"]),
        "window_anchor": anchor, "training_rows": rule, "controls_release": str(prior.relative_to(ROOT).as_posix()),
        "new_arms_identical_to_control": sum(v <= config.get("identity_tolerance_t_ha", 0) for v in identity.values()),
        "maximum_identity_difference_t_ha": max(identity.values(), default=None),
        "verifier_sha256": sha(Path(__file__)), "manifest_sha256": sha(out / "manifest.json"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=ROOT / "data/runs/zimbabwe_multiyear_v1")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        result = verify(args.release.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
