"""Post-hoc benchmark checks for the best observed compact-weather arm; no refitting."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_weather import verify_release
from cropyield.experiments.zimbabwe_weather_compact import CONFIG, OUTPUT


def compare():
    verify_release(OUTPUT)
    config = json.loads(CONFIG.read_text())
    p = pd.read_csv(OUTPUT / "predictions.csv", dtype={"group_id": str})
    wide = p.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()
    truth = p[p.method.eq("monthly_tree_target")].set_index("obs_id").loc[wide.index]
    weather = pd.read_parquet(OUTPUT / "compact_weather.parquet").loc[wide.index]
    errors = (wide - truth.yield_t_ha.to_numpy()[:, None])**2
    point = np.sqrt(errors.mean())
    method = "compact4_shared"
    result = []
    for unit, groups in [("spatial_group", truth.group_id), ("weather_cell", weather.weather_grid_id)]:
        members = [np.flatnonzero(groups.to_numpy() == g) for g in np.unique(groups)]
        rng = np.random.default_rng(config["seed"])
        scores = []
        for _ in range(config["bootstrap_draws"]):
            indices = np.concatenate([members[i] for i in rng.integers(len(members), size=len(members))])
            scores.append(np.sqrt(errors.iloc[indices].mean()).to_numpy())
        boot = pd.DataFrame(scores, columns=wide.columns)
        for reference in ["monthly_target", "monthly_tree_target", "monthly_tree_transfer"]:
            low, high = np.quantile(boot[method] - boot[reference], [.025, .975])
            result.append({"method": method, "reference": reference, "bootstrap_unit": unit,
                           "clusters": len(members), "delta_rmse_t_ha": point[method] - point[reference],
                           "ci_low": low, "ci_high": high,
                           "comparison_status": "posthoc_best_observed_arm_benchmark_not_primary"})
    return pd.DataFrame(result)


if __name__ == "__main__":
    comparisons = compare()
    comparisons.to_csv(ROOT / "data/runs/zimbabwe_weather_compact_candidate_v1.csv", index=False)
    print(comparisons.to_string(index=False))
