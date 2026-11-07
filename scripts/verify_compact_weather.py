"""Independent accounting, feature reconstruction and replay for the compact ablation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_weather import make_context, predict, verify_release
from cropyield.experiments.zimbabwe_weather_compact import (
    CONFIG,
    CONTROL_NAMES,
    FULL_WEATHER,
    OUTPUT,
    PRIOR,
    WEATHER,
    load_compact,
)


def verify():
    config = json.loads(CONFIG.read_text())
    verify_release(OUTPUT)
    rows, features, _, membership, permission, controls = load_compact(config)
    for name in ["target_memberships.csv", "source_spatial_permissions.csv"]:
        assert (OUTPUT / name).read_bytes() == (PRIOR / name).read_bytes()
    stored = pd.read_parquet(OUTPUT / "compact_weather.parquet").sort_index()
    assert len(stored) == 6212
    pd.testing.assert_frame_equal(stored, rows[stored.columns])
    # Descriptive support check only: no yields, parameter selection or filtering.
    target = rows[rows.domain.eq("lacuna") & rows.fold.isin([1, 2, 3, 4])]
    source = rows[rows.domain.eq("zimbabwe_2024") & rows.feature_eligible]
    support = []
    for column in config["feature_sets"]["compact4"]:
        t, s = target[column], source[column]
        support.append({"feature": column, "target_min": float(t.min()), "target_max": float(t.max()),
                        "source_min": float(s.min()), "source_max": float(s.max()),
                        "source_rows_outside_target_range": int(((s < t.min()) | (s > t.max())).sum()),
                        "eligible_source_rows": len(s)})

    # Reconstruct the two early-season columns directly from the history and
    # historical normal rates, independently of early_weather/cell-month helpers.
    history = pd.read_parquet(WEATHER / "weather_history.parquet")
    normal = history[history.year.between(1991, 2020)].groupby(["weather_grid_id", "calendar_month"])
    rain_normal, temp_normal = normal.rain_rate_mm_day.mean(), normal.t2m_c.mean()
    hist = history.set_index(["weather_grid_id", "year", "calendar_month"])
    checks = 0
    for (cell, season), group in stored.groupby(["weather_grid_id", "season_year"]):
        rain, expected, temperature, days = 0., 0., 0., 0
        for month in [10, 11, 12]:
            h = hist.loc[(cell, season - 1, month)]
            rain += h.rain_total_mm
            expected += rain_normal.loc[(cell, month)] * h.days_in_month
            temperature += (h.t2m_c - temp_normal.loc[(cell, month)]) * h.days_in_month
            days += h.days_in_month
        np.testing.assert_allclose(group.wx_rain_percent_normal_oct_dec, 100 * rain / expected, rtol=0, atol=1e-10)
        np.testing.assert_allclose(group.wx_t2m_anomaly_c_oct_dec, temperature / days, rtol=0, atol=1e-10)
        checks += len(group) * 2
    for family, expected in features.items():
        pd.testing.assert_frame_equal(pd.read_parquet(OUTPUT / f"features_{family}.parquet"), expected)

    pred = pd.read_csv(OUTPUT / "predictions.csv", dtype={"group_id": str})
    metrics = pd.read_csv(OUTPUT / "metrics.csv").set_index("method")
    reserved = set(rows[rows.domain.eq("lacuna") & rows.fold.eq(0)].index)
    expected_ids = set(rows[rows.domain.eq("lacuna") & rows.fold.isin([1, 2, 3, 4])].index)
    assert pred.method.nunique() == 19 and len(expected_ids) == 1504
    for method, group in pred.groupby("method"):
        assert group.obs_id.is_unique and set(group.obs_id) == expected_ids
        assert reserved.isdisjoint(group.obs_id) and group.prediction_t_ha.ge(0).all()
        np.testing.assert_array_equal(group.yield_t_ha, rows.loc[group.obs_id].yield_t_ha)
        np.testing.assert_array_equal(group.outer_fold, rows.loc[group.obs_id].fold)
        error = group.prediction_t_ha - group.yield_t_ha
        assert np.isclose(np.sqrt(np.mean(error**2)), metrics.loc[method, "rmse_t_ha"], rtol=0, atol=1e-10)
        assert np.isclose(abs(error).mean(), metrics.loc[method, "mae_t_ha"], rtol=0, atol=1e-10)
    for method in CONTROL_NAMES:
        a = pred[pred.method.eq(method)].set_index("obs_id").sort_index()
        b = controls[controls.method.eq(method)].set_index("obs_id").sort_index()
        pd.testing.assert_frame_equal(a, b)
        np.testing.assert_array_equal(a.prediction_t_ha, b.prediction_t_ha)

    tuning = pd.read_csv(OUTPUT / "tuning.csv")
    selected = pd.read_csv(OUTPUT / "selected_parameters.csv")
    accounting = pd.read_csv(OUTPUT / "fit_accounting.csv")
    assert len(selected) == 40 and len(accounting) == 160
    for pick in selected.itertuples():
        choices = tuning[tuning.outer_fold.eq(pick.outer_fold) & tuning.method.eq(pick.method)]
        best = choices.iloc[np.argmin(choices.inner_rmse_t_ha.to_numpy())]
        key = "leaves" if "tree" in pick.method else "alpha"
        assert getattr(pick, key) == best[key] and pick.ratio == best.ratio
        assert np.isclose(pick.inner_rmse_t_ha, best.inner_rmse_t_ha)
        assert pick.n_target_train == 1128
        assert pick.source_used == (pick.source_available if pick.ratio else 0)
    for a in accounting.itertuples():
        m = membership[membership.outer_fold.eq(a.outer_fold) & membership.inner_fold.eq(a.inner_fold)]
        fit = m[m.role.eq("fit")].obs_id.tolist()
        p = permission[permission.outer_fold.eq(a.outer_fold) & permission.inner_fold.eq(a.inner_fold) & permission.allowed_by_spatial_rule]
        assert len(fit) == a.n_target and len(p) == a.n_source
        assert a.target_ids_sha256 == hashlib.sha256("|".join(fit).encode()).hexdigest()
        assert a.source_ids_sha256 == hashlib.sha256("|".join(p.obs_id).encode()).hexdigest()
        assert p.minimum_distance_to_protected_km.ge(2).all() and reserved.isdisjoint(fit)

    # Direct row resampling verifies every interval, using both spatial groups
    # and coarse weather cells. It does not reuse the experiment's SSE shortcut.
    wide = pred.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()
    truth = pred[pred.method.eq("monthly_tree_target")].set_index("obs_id").loc[wide.index]
    error = (wide - truth.yield_t_ha.to_numpy()[:, None])**2
    pairs = pd.read_csv(OUTPUT / "paired_differences.csv")
    interactions = pd.read_csv(OUTPUT / "transfer_benefit_interaction.csv")
    for unit, labels in [("spatial_group", truth.group_id), ("weather_cell", rows.loc[wide.index].weather_grid_id)]:
        labels = labels.to_numpy()
        members = [np.flatnonzero(labels == g) for g in np.unique(labels)]
        rng = np.random.default_rng(config["seed"])
        draws = []
        for _ in range(config["bootstrap_draws"]):
            index = np.concatenate([members[i] for i in rng.integers(len(members), size=len(members))])
            draws.append(np.sqrt(error.iloc[index].mean()).to_numpy())
        boot = pd.DataFrame(draws, columns=wide.columns)
        point = np.sqrt(error.mean())
        for p in pairs[pairs.bootstrap_unit.eq(unit)].itertuples():
            assert np.isclose(p.delta_rmse_t_ha, point[p.method] - point[p.reference], atol=1e-10)
            np.testing.assert_allclose(np.quantile(boot[p.method] - boot[p.reference], [.025, .975]), [p.ci_low, p.ci_high], rtol=0, atol=1e-10)
        i = interactions[interactions.bootstrap_unit.eq(unit)].iloc[0]
        difference = boot.compact4_tree_transfer - boot.compact4_tree_target - boot.monthly_tree_transfer + boot.monthly_tree_target
        np.testing.assert_allclose(np.quantile(difference, [.025, .975]), [i.ci_low, i.ci_high], rtol=0, atol=1e-10)

    # Replay the selected four-feature merged tree, including the training gap.
    pick = selected[selected.outer_fold.eq(1) & selected.method.eq("compact4_tree_transfer")].iloc[0]
    m = membership[membership.outer_fold.eq(1) & membership.inner_fold.eq(0)]
    p = permission[permission.outer_fold.eq(1) & permission.inner_fold.eq(0) & permission.allowed_by_spatial_rule]
    fit, query = m[m.role.eq("fit")].obs_id.tolist(), m[m.role.eq("evaluation")].obs_id.tolist()
    data = make_context(rows, features["compact4"], fit, p.obs_id.tolist(), query + fit)
    with threadpool_limits(limits=1):
        replay = predict(data, "tree", {"leaves": int(pick.leaves), "ratio": pick.ratio}, config)
    saved = pred[pred.method.eq(pick.method)].set_index("obs_id").loc[query].prediction_t_ha
    np.testing.assert_allclose(replay[:len(query)], saved, rtol=0, atol=1e-9)
    gap = pd.read_csv(OUTPUT / "training_outer_diagnostics.csv")
    g = gap[gap.outer_fold.eq(1) & gap.method.eq(pick.method)].iloc[0]
    assert np.isclose(g.training_rmse_t_ha, np.sqrt(np.mean((replay[len(query):] - data["yt"])**2)), atol=1e-10)
    verify_release(FULL_WEATHER)
    return {"status": "passed", "arms": 19, "evaluation_fields_per_arm": 1504,
            "compact_feature_rows": len(stored), "new_weather_values_reconstructed": checks,
            "old_controls_unchanged": len(CONTROL_NAMES), "selected_models_checked": len(selected),
            "accounting_records_checked": len(accounting), "intervals_replayed": len(pairs),
            "bootstrap_units": ["232 spatial groups", "30 weather cells"],
            "selected_tree_replayed": True, "reserved_fold_scored": False,
            "frozen_split_files_identical": True, "input_and_output_hashes_verified": True,
            "descriptive_weather_support": support}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/runs/zimbabwe_weather_compact_validation_v1.json")
    args = parser.parse_args()
    result = verify()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    pd.DataFrame(result["descriptive_weather_support"]).to_csv(
        args.output.with_name("zimbabwe_weather_compact_support_v1.csv"), index=False)
    print(json.dumps(result, indent=2))
