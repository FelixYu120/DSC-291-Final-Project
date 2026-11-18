"""Same-split V0–V3 satellite aggregation comparison.

Two config switches select the design; an absent key keeps the published v1 behaviour:

- ``window_anchor``: ``"crop_dates"`` (v1) builds V1 from each field's survey planting/harvest dates;
  ``"calendar"`` (v2, team rule) is label-free: V1 is December–March for every source and the crop-date
  variant cannot be a model candidate. Crop-date counts survive only as ``diagnostic_`` audit columns.
- ``training_rows``: ``"all_screened"`` (v1) trains on every feature-eligible 2024 row, recorded zeros
  included; ``"include_primary"`` (v2, team rule) admits only ``labels_v1.include_primary`` rows.
"""
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
from cropyield.data.handoff import (
    csv_write,
    json_write,
    publish_release,
    require,
    verify_inputs,
)
from cropyield.data.labels import sha256
from cropyield.data.xy import FEATURES
from cropyield.experiments.zimbabwe_diagnosis import BANDS, INDICES, TrainingTransform
from cropyield.experiments.zimbabwe_merge import predict_model, score_predictions

CONFIG = ROOT / "configs/zimbabwe_aggregation_v2.json"
OUTPUT = ROOT / "data/runs/zimbabwe_aggregation_v2"
PRIOR = ROOT / "data/runs/zimbabwe_merge_v1"
PROTOCOL = ROOT / "docs/zimbabwe/AGGREGATION_PROTOCOL.md"
VARIANTS = ["v0_mean", "v1_preharvest_mean", "v1_calendar_mean", "v2_max", "v3_median", "v3_mode"]
CROP_DATE_VARIANT = "v1_preharvest_mean"
CALENDAR_VARIANTS = [v for v in VARIANTS if v != CROP_DATE_VARIANT]
WINDOW_ANCHORS = ("crop_dates", "calendar")
TRAINING_ROWS = ("all_screened", "include_primary")
SOURCE_TRAINING_ROWS = {"all_screened": 4330, "include_primary": 2456}
# Under the calendar rule these date-based audit columns stay as explicitly labelled diagnostics only.
DIAGNOSTIC_COLUMNS = {"preharvest_start": "diagnostic_crop_date_window_start",
                      "preharvest_cutoff": "diagnostic_crop_date_window_end",
                      "has_harvest_date": "diagnostic_has_harvest_date",
                      "has_plant_date": "diagnostic_has_plant_date",
                      "n_preharvest": "diagnostic_n_crop_date_window",
                      "n_calendar_on_or_after_harvest": "diagnostic_n_calendar_on_or_after_harvest",
                      "n_before_harvest_but_preplant": "diagnostic_n_before_harvest_but_preplant"}


def window_anchor(config):
    """'crop_dates' = v1 survey-date V1 window; 'calendar' = v2 label-free windows. Absent = v1."""
    anchor = config.get("window_anchor", "crop_dates")
    require(anchor in WINDOW_ANCHORS, f"Unknown window_anchor: {anchor}")
    return anchor


def model_variants(config):
    """Variants that may become model candidates, in canonical order."""
    variants = list(config.get("variants", VARIANTS))
    require(set(variants) <= set(VARIANTS), "Unknown aggregation variant")
    if window_anchor(config) == "calendar":
        require(CROP_DATE_VARIANT not in variants,
                "Survey crop dates cannot anchor a model window under the calendar rule")
    return [v for v in VARIANTS if v in variants]


def training_rows(config):
    """'all_screened' = v1 pool (2024 zeros included); 'include_primary' = team rule. Absent = v1."""
    rule = config.get("training_rows", "all_screened")
    require(rule in TRAINING_ROWS, f"Unknown training_rows rule: {rule}")
    return rule


def require_training_rows(rows, ids, config):
    """Under the team rule every row that can enter a fit has labels_v1.include_primary = True."""
    if training_rows(config) == "include_primary":
        ids = list(ids)
        require("include_primary" in rows.columns and rows.loc[ids, "include_primary"].eq(True).all(),
                "Training pool holds rows outside labels_v1.include_primary")


def default_output(config):
    return ROOT / "data/runs" / config["experiment"]


def _hsm(sorted_values):
    n = len(sorted_values)
    if n == 0:
        return np.nan, False
    if n <= 2:
        return float(np.mean(sorted_values)), False
    half = (n + 1) // 2
    widths = sorted_values[half-1:] - sorted_values[:n-half+1]
    choices = np.flatnonzero(np.isclose(widths, widths.min(), rtol=1e-12, atol=1e-12))
    results = [_hsm(sorted_values[i:i+half]) for i in choices]
    return float(np.mean([v[0] for v in results])), len(choices) > 1 or any(v[1] for v in results)


def half_sample_mode(values):
    """Continuous-mode estimate; tied shortest intervals contribute equally."""
    values = np.asarray(values, float)
    return _hsm(np.sort(values[np.isfinite(values)]))[0]


def aggregate_monthly(monthly, rows, config):
    """Aggregate features without using outcomes; preserve rows with unavailable windows as NaN."""
    require(rows.index.is_unique, "Duplicate observation ID")
    require(not monthly.duplicated(["obs_id", "month"]).any(), "Duplicate monthly key")
    require(set(monthly.obs_id).issubset(rows.index), "Unknown monthly observation")
    require(config["calendar_months"] == [12, 1, 2, 3, 4, 5, 6], "Use the common December–June season")
    anchor, variants = window_anchor(config), model_variants(config)
    dates = pd.DataFrame(index=rows.index)
    dates["season_start"] = pd.to_datetime((rows.season_year-1).astype(str) + "-12-01")
    dates["season_end"] = pd.to_datetime(rows.season_year.astype(str) + "-07-01")
    dates["calendar_cutoff"] = pd.to_datetime(rows.season_year.astype(str) + "-" + config["calendar_cutoff_month_day"])
    for name in ["harvest_date", "plant_date"]:
        dates[name] = pd.to_datetime(rows[name], errors="coerce") if name in rows else pd.NaT
    both = dates.harvest_date.notna() & dates.plant_date.notna()
    require((dates.loc[both, "plant_date"] < dates.loc[both, "harvest_date"]).all(), "Harvest must follow planting")
    dates["preharvest_start"] = pd.concat([dates.season_start, dates.plant_date], axis=1).max(axis=1)
    dates["preharvest_cutoff"] = dates.harvest_date.fillna(dates.calendar_cutoff)
    frame = monthly.copy().merge(dates, left_on="obs_id", right_index=True, validate="many_to_one")
    frame["acquired"] = pd.to_datetime(frame.acquired, errors="coerce")
    values = frame[BANDS+INDICES].apply(pd.to_numeric, errors="coerce")
    values = values.where(np.isfinite(values))
    require(frame.loc[values.notna().any(axis=1) & ~frame.missing.astype(bool), "acquired"].notna().all(),
            "Valid monthly data needs an acquisition date")
    in_season = frame.acquired.ge(frame.season_start) & frame.acquired.lt(frame.season_end)
    observed = ~frame.missing.astype(bool) & values.notna().any(axis=1)
    frame[BANDS+INDICES] = values
    frame.loc[~(observed & in_season), BANDS+INDICES] = np.nan
    usable = observed & in_season
    preharvest = usable & frame.acquired.ge(frame.preharvest_start) & frame.acquired.lt(frame.preharvest_cutoff)
    calendar = usable & frame.acquired.lt(frame.calendar_cutoff)
    scopes = {"season": usable, "preharvest": preharvest, "calendar": calendar}
    frames, audit = {}, dates[["preharvest_start", "preharvest_cutoff"]].copy()
    audit["has_harvest_date"] = dates.harvest_date.notna()
    audit["has_plant_date"] = dates.plant_date.notna()
    for name, mask in scopes.items():
        audit[f"n_{name}"] = frame.loc[mask].groupby("obs_id").size().reindex(rows.index, fill_value=0)
    audit["n_calendar_on_or_after_harvest"] = frame.loc[calendar & frame.harvest_date.notna() & frame.acquired.ge(frame.harvest_date)].groupby("obs_id").size().reindex(rows.index, fill_value=0)
    audit["n_before_harvest_but_preplant"] = frame.loc[usable & frame.harvest_date.notna() & frame.acquired.lt(frame.harvest_date) & frame.plant_date.notna() & frame.acquired.lt(frame.plant_date)].groupby("obs_id").size().reindex(rows.index, fill_value=0)
    for family, columns in [("bands", BANDS), ("indices", INDICES)]:
        grouped = frame.loc[usable].groupby("obs_id")[columns]
        for variant, mask, stat in [("v0_mean", usable, "mean"), ("v1_preharvest_mean", preharvest, "mean"),
                                    ("v1_calendar_mean", calendar, "mean"), ("v2_max", usable, "max"),
                                    ("v3_median", usable, "median")]:
            if variant in variants:  # the crop-date window never becomes a calendar-rule feature
                frames[f"{family}_{variant}"] = frame.loc[mask].groupby("obs_id")[columns].agg(stat).reindex(rows.index)
        if "v3_mode" in variants:
            frames[f"{family}_v3_mode"] = grouped.agg(half_sample_mode).reindex(rows.index)
        all_unique = grouped.agg(lambda x: len(x.dropna()) > 1 and x.nunique() == x.notna().sum())
        tied = grouped.agg(lambda x: _hsm(np.sort(x.dropna().to_numpy(float)))[1])
        audit[f"{family}_all_unique_series"] = all_unique.sum(axis=1).reindex(rows.index, fill_value=0)
        audit[f"{family}_mode_interval_tied_series"] = tied.sum(axis=1).reindex(rows.index, fill_value=0)
    if anchor == "calendar":
        audit = audit.rename(columns=DIAGNOSTIC_COLUMNS)
    return frames, audit


def load_inputs(config):
    verify_inputs(ROOT, ROOT/"data/cropyield.duckdb")
    manifest = json.loads((PRIOR/"manifest.json").read_text())
    for name, info in manifest["outputs"].items():
        require(sha256(PRIOR/name) == info["sha256"], f"Frozen merge output changed: {name}")
    rows = pd.read_parquet(PRIOR/"combined_data.parquet").set_index("obs_id").sort_index()
    labels = pd.read_parquet(ROOT/"data/processed/labels_v1.parquet").set_index("obs_id")
    rows = rows.join(labels[["plant_date", "harvest_date"]], validate="one_to_one")
    require(rows.include_primary.eq(labels.loc[rows.index, "include_primary"]).all(),
            "Merge include_primary differs from labels_v1")
    rule = training_rows(config)
    if rule == "include_primary":
        rows["label_exclusion_reason"] = labels.loc[rows.index, "exclusion_reason"]
        # Target rows are all include_primary; 2024 rows also need common-window features.
        rows["training_pool"] = rows.include_primary.eq(True) & (rows.domain.eq("lacuna") | rows.feature_eligible)
    with duckdb.connect(str(ROOT/"data/cropyield.duckdb"), read_only=True) as con:
        con.register("selected", rows.reset_index()[["obs_id", "season_year"]])
        monthly = con.execute("""SELECT b.*, v.ndvi,v.gcvi,v.mtci,v.ndvi705,v.ndvi740, sc.acquired
            FROM monthly_bands b JOIN vegetation_indices v USING(obs_id,month)
            JOIN selected s USING(obs_id) LEFT JOIN scenes sc USING(obs_id,month)
            WHERE b.month >= CAST(s.season_year-1 AS VARCHAR)||'-12'
            AND b.month <= CAST(s.season_year AS VARCHAR)||'-06' ORDER BY b.obs_id,b.month""").df()
    require(len(rows) == 6212 and monthly.groupby("obs_id").size().eq(7).all(), "Candidate/monthly population changed")
    features, audit = aggregate_monthly(monthly, rows, config)
    features["legacy_indices_mean_max"] = rows[FEATURES].copy()
    for column in INDICES:
        for stat, variant in [("mean", "v0_mean"), ("max", "v2_max")]:
            np.testing.assert_allclose(features[f"indices_{variant}"][column], rows[f"{column}_season_{stat}"], atol=1e-12, rtol=1e-12)
    membership = pd.read_csv(PRIOR/"target_memberships.csv", dtype={"group_id": str})
    permission = pd.read_csv(PRIOR/"source_spatial_permissions.csv")
    target = rows.domain.eq("lacuna")
    require((rows.loc[target, "fold"].isin([0, 1, 2, 3, 4])).all(), "Unexpected target folds")
    require(target.sum() == 1880 and (target & rows.fold.eq(0)).sum() == 376, "Target count changed")
    require((rows.domain.eq("zimbabwe_2024") & rows.feature_eligible).sum() == 4330, "Source count changed")
    require(set(permission.obs_id) == set(rows.index[rows.domain.eq("zimbabwe_2024") & rows.feature_eligible]), "Source permissions differ")
    require(rows.loc[target, "include_primary"].all(), "Target rows outside include_primary")
    if rule == "include_primary":
        # Buffer distances depend on source and protected coordinates only, so the frozen
        # decisions stay valid after dropping rows; nothing is recomputed.
        pool = rows.index[rows.domain.eq("zimbabwe_2024") & rows.training_pool]
        require(len(pool) == SOURCE_TRAINING_ROWS[rule], "include_primary source count changed")
        permission = permission[permission.obs_id.isin(pool)].reset_index(drop=True)
    return rows, features, audit, monthly, membership, permission


def make_context(rows, x, fit_ids, source_ids, query_ids, config=None):
    require(rows.loc[fit_ids].domain.eq("lacuna").all() and rows.loc[query_ids].domain.eq("lacuna").all(), "Target context must be Lacuna")
    require(rows.loc[fit_ids].fold.ne(0).all() and rows.loc[query_ids].fold.ne(0).all(), "Fold zero exposure")
    require(rows.loc[source_ids].domain.eq("zimbabwe_2024").all(), "Invalid source context")
    if config is not None:
        require_training_rows(rows, list(fit_ids) + list(source_ids), config)
    fit = TrainingTransform().fit(x.loc[fit_ids])
    return {"xt": fit.transform(x.loc[fit_ids]), "xs": fit.transform(x.loc[source_ids]),
            "xq": fit.transform(x.loc[query_ids]), "yt": rows.loc[fit_ids].yield_t_ha.to_numpy(float),
            "ys": rows.loc[source_ids].yield_t_ha.to_numpy(float)}


def run_models(rows, features, membership, permission, config):
    predictions, selections, trials, gaps = [], [], [], []
    saved = pd.read_csv(PRIOR/"predictions.csv", dtype={"group_id": str})
    rule = training_rows(config)
    for outer in config["target_folds"]:
        split_ids = []
        for inner in range(4):
            m = membership[membership.outer_fold.eq(outer) & membership.inner_fold.eq(inner)]
            fit_ids = m[m.role.eq("fit")].obs_id.tolist()
            query_ids = m[m.role.eq("evaluation" if inner == 0 else "validation")].obs_id.tolist()
            p = permission[permission.outer_fold.eq(outer) & permission.inner_fold.eq(inner) & permission.allowed_by_spatial_rule]
            require(p.minimum_distance_to_protected_km.ge(config["auxiliary_buffer_km"]).all(), "Invalid spatial buffer")
            require(set(rows.loc[fit_ids].group_id).isdisjoint(rows.loc[query_ids].group_id), "Spatial group leakage")
            split_ids.append((fit_ids, p.obs_id.tolist(), query_ids))
        for feature_name, x in features.items():
            contexts = [make_context(rows, x, *ids, config=config) for ids in split_ids]
            truth = np.concatenate([rows.loc[ids[2]].yield_t_ha.to_numpy() for ids in split_ids[1:]])
            for training in config["training_sets"]:
                method = f"{feature_name}_{training}"
                kind = "lacuna_only" if training == "target" else "pooled_adaptive"
                ratios = [0.] if training == "target" else config["source_weight_ratios"]
                candidates = []
                for ratio, alpha in itertools.product(ratios, config["ridge_alphas"]):
                    params = {"alpha": alpha, "source_ratio": ratio}
                    estimate = np.concatenate([predict_model(c, kind, params, config) for c in contexts[1:]])
                    loss = float(np.mean((estimate-truth)**2))
                    candidates.append((loss, params))
                    trials.append({"method": method, "outer_fold": outer, **params, "inner_rmse_t_ha": np.sqrt(loss)})
                loss, params = min(candidates, key=lambda v: v[0])
                query = split_ids[0][2]
                pred = predict_model(contexts[0], kind, params, config)
                train_pred = predict_model({**contexts[0], "xq": contexts[0]["xt"]}, kind, params, config)
                # The step 9 pooled control trained on every 2024 row; under include_primary only
                # the Lacuna-only control can (and must) reproduce its saved predictions.
                if feature_name == "legacy_indices_mean_max" and (kind == "lacuna_only" or rule == "all_screened"):
                    expected = saved[saved.method.eq(kind) & saved.outer_fold.eq(outer)].set_index("obs_id").loc[query]
                    np.testing.assert_allclose(pred, expected.prediction_t_ha, atol=1e-9, rtol=0)
                    pred = expected.prediction_t_ha.to_numpy()  # retain original saved controls exactly
                selections.append({"method": method, "outer_fold": outer, **params, "inner_rmse_t_ha": np.sqrt(loss),
                                   "n_features": x.shape[1], "target_fit": len(split_ids[0][0]), "target_evaluation": len(query),
                                   "source_allowed": len(split_ids[0][1]), "source_used": len(split_ids[0][1]) if params["source_ratio"] > 0 else 0})
                gaps.append({"method": method, "outer_fold": outer, "train_n": len(train_pred), "evaluation_n": len(pred),
                             "train_rmse_t_ha": np.sqrt(np.mean((train_pred-contexts[0]["yt"])**2)),
                             "evaluation_rmse_t_ha": np.sqrt(np.mean((pred-rows.loc[query].yield_t_ha.to_numpy())**2))})
                predictions.append(pd.DataFrame({"obs_id": query, "group_id": rows.loc[query].group_id.to_numpy(),
                                                 "outer_fold": outer, "method": method, "yield_t_ha": rows.loc[query].yield_t_ha.to_numpy(),
                                                 "prediction_t_ha": pred}))
            print(f"fold {outer}: {feature_name} complete", flush=True)
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(selections), pd.DataFrame(trials), pd.DataFrame(gaps)


def evaluate(predictions, config):
    metrics, folds = [], []
    methods = predictions.method.unique().tolist()
    for name, part in predictions.groupby("method", sort=False):
        require(len(part) == 1504 and part.obs_id.is_unique and part.outer_fold.ne(0).all(), "Wrong evaluation membership")
        metrics.append({"method": name, "n": len(part), **score_predictions(part.yield_t_ha.to_numpy(), part.prediction_t_ha.to_numpy())})
        for fold, group in part.groupby("outer_fold"):
            folds.append({"method": name, "fold": fold, "n": len(group), **score_predictions(group.yield_t_ha.to_numpy(), group.prediction_t_ha.to_numpy())})
    wide = predictions.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()[methods]
    require(wide.notna().all().all(), "Different evaluation IDs across arms")
    truth = predictions[predictions.method.eq(methods[0])].set_index("obs_id").loc[wide.index]
    groups = np.unique(truth.group_id)
    square = (wide.to_numpy()-truth.yield_t_ha.to_numpy()[:, None])**2
    members = [np.flatnonzero(truth.group_id.to_numpy() == group) for group in groups]
    sums = np.array([square[i].sum(axis=0) for i in members])
    sizes = np.array([len(i) for i in members])
    rng = np.random.default_rng(config["seed"])
    draws = np.array([np.bincount(rng.integers(len(groups), size=len(groups)), minlength=len(groups)) for _ in range(config["bootstrap_draws"])])
    distribution = np.sqrt((draws@sums)/(draws@sizes)[:, None])
    point = np.sqrt(square.mean(axis=0))
    contrasts = []
    for method in methods:
        if method.startswith("legacy"):
            references = ["legacy_indices_mean_max_target"] if method.endswith("_merged") else []
        else:
            family, training = method.split("_")[0], method.rsplit("_", 1)[1]
            references = [f"{family}_v0_mean_{training}", f"legacy_indices_mean_max_{training}"]
            if "v1_preharvest_mean" in method:
                references.append(method.replace("v1_preharvest_mean", "v1_calendar_mean"))
            if training == "merged":
                references.append(method.removesuffix("_merged")+"_target")
        for reference in references:
            if method == reference:
                continue
            j, k = methods.index(method), methods.index(reference)
            low, high = np.quantile(distribution[:, j]-distribution[:, k], [.025, .975])
            contrasts.append({"method": method, "reference": reference, "delta_rmse_t_ha": point[j]-point[k],
                              "ci_low": low, "ci_high": high, "groups": len(groups),
                              "primary_comparison": method == config["primary_method"] and reference == config["primary_reference"]})
    return pd.DataFrame(metrics), pd.DataFrame(folds), pd.DataFrame(contrasts)


def input_hashes(config_path):
    paths = ["data/cropyield.duckdb", "data/processed/labels_v1.parquet", "configs/team_database_v1.json",
             "configs/zimbabwe_merge_v1.json", "data/splits/manifest.json",
             "src/cropyield/__init__.py", "src/cropyield/data/handoff.py", "src/cropyield/data/labels.py",
             "src/cropyield/data/cohorts.py", "src/cropyield/data/xy.py", "src/cropyield/eval/splits.py",
             "src/cropyield/experiments/zimbabwe_merge.py", "src/cropyield/experiments/zimbabwe_diagnosis.py",
             "src/cropyield/experiments/zimbabwe_aggregation.py", "scripts/step14_compare_zimbabwe_aggregation.py",
             "docs/zimbabwe/AGGREGATION_PROTOCOL.md", "requirements.txt", "pyproject.toml"]
    paths += [str(p.relative_to(ROOT)) for p in PRIOR.iterdir() if p.is_file()]
    paths.append(str(config_path.relative_to(ROOT)))
    return {p: sha256(ROOT/p) for p in sorted(set(paths))}


VARIANT_LABELS = {"v0_mean": "V0 / V3 mean", "v1_preharvest_mean": "V1 crop dates", "v1_calendar_mean": "V1 calendar",
                  "v2_max": "V2 max", "v3_median": "V3 median", "v3_mode": "V3 mode estimate"}


def plot_results(path, metrics, variants=VARIANTS, merged_label="Lacuna + 2024",
                 title="Satellite aggregation: same 1,504 Lacuna fields · Ridge\nExploratory spatial validation; fold 0 excluded"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = [VARIANT_LABELS[v] for v in variants]
    scores = metrics.set_index("method")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), layout="constrained")
    for family, ax in zip(["bands", "indices"], axes, strict=True):
        for training, offset, color in [("target", -.18, "#3973ac"), ("merged", .18, "#13806a")]:
            values = [scores.loc[f"{family}_{v}_{training}", "rmse_t_ha"] for v in variants]
            ax.barh(np.arange(len(variants))+offset, values, height=.34, label="Lacuna only" if training == "target" else merged_label, color=color)
            for i, value in enumerate(values):
                ax.text(value+.01, i+offset, f"{value:.3f}", va="center", fontsize=8)
        ax.set_yticks(np.arange(len(variants)), names)
        ax.invert_yaxis()
        ax.set(xlabel="RMSE (t/ha); lower is better", title="10 reflectance bands" if family == "bands" else "5 vegetation indices")
        ax.set_xlim(0, max(scores.rmse_t_ha)*1.13)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=2)
    fig.suptitle(title, fontsize=13)
    fig.savefig(path, dpi=160, metadata={"Software": "cropyield aggregation"})
    plt.close(fig)


def write_report(path, metrics, contrasts, summary, selected):
    scores = metrics.set_index("method")
    primary = contrasts[contrasts.primary_comparison].iloc[0]
    lines = ["# Satellite aggregation V0–V3: results", "", ("All models use Ridge and the same 1,504 Lacuna 2023 development fields. "
             "Lower RMSE is better. Fold 0 was neither fit nor scored. Results are exploratory, not a new blind test."), "",
             (f"Primary contrast (10 bands, crop-date preharvest mean minus full-season mean, Lacuna only): **{primary.delta_rmse_t_ha:+.4f} t/ha**, "
             f"95% spatial-group interval **[{primary.ci_low:+.4f}, {primary.ci_high:+.4f}]**."), "",
             "| Aggregation | Bands: Lacuna | Bands: merged | Indices: Lacuna | Indices: merged |", "|---|---:|---:|---:|---:|"]
    for variant in VARIANTS:
        values = [scores.loc[f"{family}_{variant}_{training}", "rmse_t_ha"] for family in ["bands", "indices"] for training in ["target", "merged"]]
        lines.append(f"| {variant} | " + " | ".join(f"{v:.4f}" for v in values) + " |")
    lines += ["", "V0 and V3 mean are identical, so fitted once. V3 median and mode are separate models, not concatenated features.",
              "The historical index mean+max control reproduced its original selected models; saved control predictions are unchanged:", "",
              f"- Lacuna only: **{scores.loc['legacy_indices_mean_max_target', 'rmse_t_ha']:.4f}** t/ha.",
              f"- Adaptive merged: **{scores.loc['legacy_indices_mean_max_merged', 'rmse_t_ha']:.4f}** t/ha.", "",
              "![Aggregation comparison](comparison.png)", "", "## What changed", "",
              ("Bands are monthly field-pixel median reflectances; indices are derived from those values. These models change temporal aggregation only. "
              "The two feature families are evaluated separately to avoid confusing a band/index change with a statistic change."), "",
              ("V1 uses recorded planting <= actual image acquisition < recorded harvest for Lacuna, within December–June. "
              "2024 has neither date and uses December–March as a calendar proxy. The additional common-calendar arm applies December–March to both sources."), "",
              (f"All evaluation fields remain included. Crop-date V1 has {summary['target_preharvest_under_four_months']} evaluation fields with fewer than four observations; "
              f"{summary['target_preharvest_missing_fields']} have no observations. A new four-month filter would change the population. "
              f"The fixed calendar arm includes on/after-harvest scenes for {summary['target_calendar_postharvest_fields']} evaluation fields."), "",
              ("The seasonal mode is a half-sample **modal estimate** with averaged tie branches. Exact modes are usually tied because observations are continuous. "
              "With only 1–7 months, this estimate can be unstable; it is not a well-established population mode."), "",
              "## Evaluation and interpretation", "",
              ("All outer/inner memberships and 2 km auxiliary exclusions are copied from the original comparison. Imputation, clipping, scaling, "
              "yield calibration and tuning use training observations only. Source ratios include zero; selected_parameters.csv shows whether each merged fit actually used 2024."), "",
              ("Actual crop dates are retrospective metadata. This design does not establish forecast skill, and mixing known crop dates with a calendar proxy "
              "does not remove the source mismatch. The common-calendar arm helps expose that difference. Maxima can be sensitive to extremes; the mode estimator can be noisy with few months."), "",
              ("Intervals resample spatial groups and condition on the saved predictions. There are many unadjusted secondary comparisons; the best observed score "
              "is descriptive and requires independent validation. No window or grid was retuned after scoring."), "",
              "## Files and provenance", "",
              "- `observations.csv`: source/season, outcomes, original eligibility and frozen fold IDs, with crop dates.",
              "- `monthly_observations.parquet`: December–June values and actual image acquisition dates.",
              "- `features.parquet` / `feature_dictionary.json`: all variant predictors, with an explicit column allowlist for each model.",
              "- `window_audit.csv`, `data_summary.json`: crop-date availability, observation counts, mode ties and cutoff diagnostics.",
              "- `target_memberships.csv`, `source_spatial_permissions.csv`: unchanged fit/evaluation permissions.",
              "- `predictions.csv`, `metrics.csv`, `fold_metrics.csv`, `paired_differences.csv`: all 26 model arms and paired uncertainty.",
              "- `tuning.csv`, `selected_parameters.csv`, `training_outer_diagnostics.csv`: training choices and fit gaps.",
              "- `PROTOCOL.md`, `manifest.json`: fixed design, source links, input/output hashes and software versions.", "",
              ("Calendar sources: [FEWS NET p. 4](https://fews.net/sites/default/files/documents/reports/ZW_February_to_September_2023_FSO_Final_jh.pdf) "
              "for the typical maize cycle; [Zimbabwe NAP 2024, section 2.1](https://unfccc.int/sites/default/files/resource/NAP-Zimbabwe-2024.pdf) "
              "for climatic seasons. Neither supplies the missing 2024 field-level crop dates."), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report_v2(path, metrics, contrasts, summary, selected, config):
    """Release summary for the team-rule design: calendar windows and include_primary training rows."""
    scores = metrics.set_index("method")
    variants = model_variants(config)
    primary = contrasts[contrasts.primary_comparison].iloc[0]
    pairs = contrasts.set_index(["method", "reference"])
    lines = [f"# Satellite aggregation V0–V3 ({config['experiment']}): results", "",
             ("All models use Ridge and the same 1,504 Lacuna 2023 development fields. RMSE is in t/ha (lower is better); "
              "R² is pooled out-of-fold (higher is better). Fold 0 was neither fit nor scored. Results are exploratory, not a new blind test."), "",
             "## Team-rule changes from v1", "",
             ("- **Label-free windows.** No survey date (planting, harvest, crop cut) is a model input or a window anchor. "
              "The v1 crop-date window `v1_preharvest_mean` is not a model candidate; V1 is the December 1 – April 1 calendar mean for both sources. "
              "`window_audit.csv` keeps crop-date counts only as `diagnostic_` columns that no model or headline uses."),
             (f"- **Training rows follow `labels_v1.include_primary`.** Merged arms may use {summary['source_training_pool']:,} Zimbabwe 2024 rows "
              f"(v1: {summary['source_feature_eligible']:,}). The {summary['source_excluded_not_include_primary']:,} removed rows are recorded zeros "
              "(`zimbabwe_2024_zero_likely_not_measured`). Lacuna-only arms already used only include_primary rows; their predictions equal v1."),
             "- Unchanged: evaluation fields, outer folds 1–4 of `s1_cc2km`, inner folds, 2 km source buffer, alpha and source-weight grids, seed and 2,000 bootstrap draws.", "",
             (f"Primary contrast (10 bands, December–March calendar mean minus full-season mean, Lacuna only): **{primary.delta_rmse_t_ha:+.4f} t/ha**, "
              f"95% spatial-group interval **[{primary.ci_low:+.4f}, {primary.ci_high:+.4f}]**."), "",
             "| Aggregation | Bands: Lacuna RMSE | R² | Bands: merged RMSE | R² | Indices: Lacuna RMSE | R² | Indices: merged RMSE | R² |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for variant in variants + ["legacy"]:
        feature = "legacy_indices_mean_max" if variant == "legacy" else None
        cells = []
        for family in ["bands", "indices"]:
            for training in ["target", "merged"]:
                name = f"{feature}_{training}" if feature else f"{family}_{variant}_{training}"
                cells += ["—", "—"] if feature and family == "bands" else [f"{scores.loc[name, 'rmse_t_ha']:.4f}", f"{scores.loc[name, 'r2']:.4f}"]
        label = "index mean + max control (10 features)" if feature else variant
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "Merged minus Lacuna-only, same predictors (paired RMSE difference and 95% spatial-group interval):", "",
              "| Predictors | Δ RMSE | Interval | Folds using 2024 |", "|---|---:|---|---:|"]
    for feature in [f"{family}_{variant}" for family in ["bands", "indices"] for variant in variants] + ["legacy_indices_mean_max"]:
        row = pairs.loc[(f"{feature}_merged", f"{feature}_target")]
        used = int(selected[selected.method.eq(f"{feature}_merged")].source_used.gt(0).sum())
        lines.append(f"| {feature} | {row.delta_rmse_t_ha:+.4f} | [{row.ci_low:+.4f}, {row.ci_high:+.4f}] | {used} of 4 |")
    lines += ["", ("V0 and V3 mean are identical, so fitted once. Median and mode are separate models. The Lacuna-only index mean+max "
                   "control reproduces the saved step 9 predictions exactly; its merged twin is refitted on include_primary 2024 rows."), "",
              ("The calendar cutoff includes on/after-harvest scenes for "
               f"{summary['diagnostic_target_calendar_postharvest_fields']} evaluation fields (diagnostic from recorded harvest dates; not a model input)."), "",
              "![Aggregation comparison](comparison.png)", "",
              "## Files", "",
              "- `observations.csv`: candidates with `include_primary`, `label_exclusion_reason` and `training_pool`; crop dates are metadata only.",
              "- `training_rows_audit.csv`: every candidate row and whether it may enter a fit.",
              "- `features.parquet` / `feature_dictionary.json`: label-free predictors only; `window_audit.csv`: counts and `diagnostic_` crop-date columns.",
              "- `target_memberships.csv`, `source_spatial_permissions.csv`: frozen v1 copies; the source table is filtered to include_primary rows at fit time.",
              "- `predictions.csv`, `metrics.csv`, `fold_metrics.csv`, `paired_differences.csv`, `tuning.csv`, `selected_parameters.csv`, `training_outer_diagnostics.csv`.",
              "- `PROTOCOL.md`, `manifest.json`: fixed design, input/output hashes and software versions.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def make_summary_v2(rows, features, audit, development, config):
    source = rows.domain.eq("zimbabwe_2024") & rows.feature_eligible
    pool = rows.domain.eq("zimbabwe_2024") & rows.training_pool
    eligible = development | pool
    dropped = source & ~pool
    return {"candidate_rows": len(rows), "window_anchor": window_anchor(config), "training_rows": training_rows(config),
            "target_evaluation": int(development.sum()), "target_reserved": 376,
            "source_feature_eligible": int(source.sum()), "source_training_pool": int(pool.sum()),
            "source_excluded_not_include_primary": int(dropped.sum()),
            "source_excluded_reasons": {str(k): int(v) for k, v in rows.loc[dropped, "label_exclusion_reason"].value_counts().items()},
            "source_excluded_zero_yield": int((dropped & rows.yield_t_ha.eq(0)).sum()),
            "model_variants": model_variants(config), "arms": len(features)*2,
            "missing_feature_rows_by_variant": {name: int((~np.isfinite(frame.loc[eligible].to_numpy()).all(axis=1)).sum())
                                                for name, frame in features.items()},
            "diagnostic_target_calendar_postharvest_fields": int(audit.loc[development, "diagnostic_n_calendar_on_or_after_harvest"].gt(0).sum()),
            "all_unique_series": {name: int(audit.loc[eligible, name].sum()) for name in audit if name.endswith("all_unique_series")},
            "mode_tied_interval_series": {name: int(audit.loc[eligible, name].sum()) for name in audit if name.endswith("mode_interval_tied_series")}}


def run_experiment(output=None, config_path=CONFIG):
    config = json.loads(config_path.read_text())
    output = default_output(config) if output is None else output
    anchor, rule = window_anchor(config), training_rows(config)
    require(config["target_folds"] == [1, 2, 3, 4] and config["reserved_fold"] == 0, "Preserve reserved fold and development splits")
    expected_variants = VARIANTS if anchor == "crop_dates" else CALENDAR_VARIANTS
    require(config["variants"] == expected_variants and config["feature_families"] == ["bands", "indices"], "Unexpected feature design")
    if anchor == "calendar":
        require(CROP_DATE_VARIANT not in config["primary_method"] + config["primary_reference"],
                "A crop-date window cannot be a headline comparison")
    before = input_hashes(config_path)
    rows, features, audit, monthly, membership, permission = load_inputs(config)
    development = rows.domain.eq("lacuna") & rows.fold.isin(config["target_folds"])
    if rule == "include_primary" or anchor == "calendar":
        require(rule == "include_primary" and anchor == "calendar", "v2 releases apply both team rules together")
        summary = make_summary_v2(rows, features, audit, development, config)
        with threadpool_limits(limits=1):
            predictions, selected, tuning, gaps = run_models(rows, features, membership, permission, config)
            metrics, folds, contrasts = evaluate(predictions, config)
        return publish(output, config, config_path, before, rows, features, audit, monthly, summary,
                       predictions, selected, tuning, gaps, metrics, folds, contrasts)
    eligible = development | (rows.domain.eq("zimbabwe_2024") & rows.feature_eligible)
    missing = {name: int((~np.isfinite(frame.loc[eligible].to_numpy()).all(axis=1)).sum()) for name, frame in features.items()}
    summary = {"candidate_rows": len(rows), "target_evaluation": int(development.sum()), "target_reserved": 376,
               "source_eligible": 4330, "source_missing_harvest_dates": int((rows.domain.eq("zimbabwe_2024") & rows.harvest_date.isna()).sum()),
               "source_missing_plant_dates": int((rows.domain.eq("zimbabwe_2024") & rows.plant_date.isna()).sum()), "arms": len(features)*2, "missing_feature_rows_by_variant": missing,
               "target_preharvest_under_four_months": int(audit.loc[development, "n_preharvest"].lt(4).sum()),
               "target_preharvest_missing_fields": int(audit.loc[development, "n_preharvest"].eq(0).sum()),
               "target_calendar_postharvest_fields": int(audit.loc[development, "n_calendar_on_or_after_harvest"].gt(0).sum()),
               "target_preplant_fields_removed": int(audit.loc[development, "n_before_harvest_but_preplant"].gt(0).sum()),
               "preharvest_counts_development": {str(k): int(v) for k,v in audit.loc[development, "n_preharvest"].value_counts().sort_index().items()},
               "all_unique_series": {name: int(audit.loc[eligible, name].sum()) for name in audit if name.endswith("all_unique_series")},
               "mode_tied_interval_series": {name: int(audit.loc[eligible, name].sum()) for name in audit if name.endswith("mode_interval_tied_series")}}
    with threadpool_limits(limits=1):
        predictions, selected, tuning, gaps = run_models(rows, features, membership, permission, config)
        metrics, folds, contrasts = evaluate(predictions, config)
    return publish(output, config, config_path, before, rows, features, audit, monthly, summary,
                   predictions, selected, tuning, gaps, metrics, folds, contrasts)


def publish(output, config, config_path, before, rows, features, audit, monthly, summary,
            predictions, selected, tuning, gaps, metrics, folds, contrasts):
    v2 = training_rows(config) == "include_primary"
    with tempfile.TemporaryDirectory(prefix="zimbabwe-aggregation-") as temporary:
        stage = Path(temporary)
        tables = {"observations": rows.reset_index(), "window_audit": audit.reset_index(), "predictions": predictions,
                  "selected_parameters": selected, "tuning": tuning, "training_outer_diagnostics": gaps,
                  "metrics": metrics, "fold_metrics": folds, "paired_differences": contrasts}
        if v2:
            tables["training_rows_audit"] = rows.reset_index()[["obs_id", "domain", "season_year", "yield_t_ha", "include_primary",
                                                                "label_exclusion_reason", "feature_eligible", "fold", "training_pool"]]
        for name, table in tables.items():
            csv_write(table, stage/f"{name}.csv")
        for name in ["target_memberships.csv", "source_spatial_permissions.csv"]:
            (stage/name).write_bytes((PRIOR/name).read_bytes())
        dictionary = {name: [f"{name}__{column}" for column in frame] for name, frame in features.items()}
        wide = pd.concat([frame.set_axis(dictionary[name], axis=1) for name, frame in features.items()], axis=1)
        wide.to_parquet(stage/"features.parquet", index=True)
        monthly.to_parquet(stage/"monthly_observations.parquet", index=False)
        json_write(dictionary, stage/"feature_dictionary.json")
        json_write(summary, stage/"data_summary.json")
        (stage/"PROTOCOL.md").write_bytes(PROTOCOL.read_bytes())
        if v2:
            write_report_v2(stage/"RESULTS.md", metrics, contrasts, summary, selected, config)
            plot_results(stage/"comparison.png", metrics, model_variants(config), "Lacuna + 2024 include_primary",
                         "Satellite aggregation v2: same 1,504 Lacuna fields · Ridge · calendar windows, include_primary rows\n"
                         "Exploratory spatial validation; fold 0 excluded")
        else:
            write_report(stage/"RESULTS.md", metrics, contrasts, summary, selected)
            plot_results(stage/"comparison.png", metrics)
        require(before == input_hashes(config_path), "Inputs changed during the run")
        manifest = {"config": config, "inputs": before, "base_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    "source_hashes_record_actual_working_tree": True, "python": platform.python_version(),
                    "versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "scikit-learn", "duckdb", "pyarrow", "matplotlib"]},
                    "outputs": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted(stage.iterdir())}}
        json_write(manifest, stage/"manifest.json")
        publish_release(stage, output)
    print(metrics.round(5).to_string(index=False), flush=True)
    print(contrasts[contrasts.primary_comparison].to_string(index=False), flush=True)
    return summary
