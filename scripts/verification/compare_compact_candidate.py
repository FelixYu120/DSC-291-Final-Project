"""Post-hoc benchmark checks for the best observed compact-weather arm; no refitting."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_merge import default_output
from cropyield.experiments.zimbabwe_weather import verify_release
from cropyield.experiments.zimbabwe_weather_compact import CONFIG


def compare(config_path=CONFIG):
    config = json.loads(Path(config_path).read_text())
    output = default_output(config)
    verify_release(output)
    p = pd.read_csv(output / "predictions.csv", dtype={"group_id": str})
    wide = p.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()
    truth = p[p.method.eq("monthly_tree_target")].set_index("obs_id").loc[wide.index]
    weather = pd.read_parquet(output / "compact_weather.parquet").loc[wide.index]
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


def candidate_output(config_path) -> Path:
    """Default CSV of a config: its own version, so a v2 run never overwrites the v1 file."""
    version = json.loads(Path(config_path).read_text())["experiment"].rsplit("_", 1)[-1]
    return ROOT / f"data/runs/zimbabwe_weather_compact_candidate_{version}.csv"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, help="CSV path; default data/runs/zimbabwe_weather_compact_candidate_<version>.csv")
    args = parser.parse_args()
    comparisons = compare(args.config.resolve())
    comparisons.to_csv(args.output or candidate_output(args.config), index=False)
    print(comparisons.to_string(index=False))
