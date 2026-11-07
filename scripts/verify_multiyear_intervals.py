"""Check paired Zimbabwe bootstrap intervals by explicitly resampling observation rows.

This deliberately does not import experiment code or reuse its grouped sufficient
statistics. Every replicate concatenates all rows from sampled spatial groups,
recalculates the outcome mean, and scores the sampled predictions directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def direct_scores(outcomes, estimates):
    residuals = estimates - outcomes[:, None]
    sse = np.sum(residuals ** 2, axis=0)
    sst = np.sum((outcomes - np.mean(outcomes)) ** 2)
    if not sst > 0:
        raise AssertionError("Bootstrap replicate has no outcome variance")
    return np.sqrt(sse / len(outcomes)), 1 - sse / sst


def verify(release, output, tolerance=1e-9):
    paths = {name: release / name for name in ["predictions.csv", "paired_differences.csv", "config.json"]}
    before = {name: sha256(path) for name, path in paths.items()}
    config = json.loads(paths["config.json"].read_text())
    predictions = pd.read_csv(paths["predictions.csv"], dtype={"obs_id": str, "group_id": str})
    contrasts = pd.read_csv(paths["paired_differences.csv"])
    methods = predictions.method.unique().tolist()
    if predictions.duplicated(["obs_id", "method"]).any():
        raise AssertionError("Duplicate method/observation predictions")
    wide = predictions.pivot(index="obs_id", columns="method", values="prediction_t_ha").sort_index()[methods]
    if not np.isfinite(wide.to_numpy(float)).all():
        raise AssertionError("Unavailable predictions or differing observation populations")
    identity = predictions[predictions.method.eq(methods[0])].set_index("obs_id").loc[wide.index]
    for method in methods:
        part = predictions[predictions.method.eq(method)].set_index("obs_id").loc[wide.index]
        pd.testing.assert_frame_equal(part[["yield_t_ha", "group_id", "outer_fold"]],
                                      identity[["yield_t_ha", "group_id", "outer_fold"]], check_exact=True)
    outcomes = identity.yield_t_ha.to_numpy(float)
    estimates = wide.to_numpy(float)
    unique_groups = sorted(identity.group_id.unique())
    row_groups = [np.flatnonzero(identity.group_id.to_numpy() == group) for group in unique_groups]
    rng = np.random.default_rng(config["seed"])
    rmse_samples, r2_samples, sample_sizes = [], [], []
    for _ in range(config["bootstrap_draws"]):
        selected_groups = rng.integers(0, len(unique_groups), size=len(unique_groups))
        # Replicate sampled groups literally, including every duplicated member row.
        selected_rows = np.concatenate([row_groups[index] for index in selected_groups])
        rmse, r2 = direct_scores(outcomes[selected_rows], estimates[selected_rows])
        rmse_samples.append(rmse)
        r2_samples.append(r2)
        sample_sizes.append(len(selected_rows))
    rmse_samples, r2_samples = np.array(rmse_samples), np.array(r2_samples)
    rmse_point, r2_point = direct_scores(outcomes, estimates)
    errors, records = [], []
    for contrast in contrasts.itertuples(index=False):
        method, reference = methods.index(contrast.method), methods.index(contrast.reference)
        rmse_interval = np.quantile(rmse_samples[:, method] - rmse_samples[:, reference], [.025, .975])
        r2_interval = np.quantile(r2_samples[:, method] - r2_samples[:, reference], [.025, .975])
        computed = {"delta_rmse_t_ha": float(rmse_point[method] - rmse_point[reference]),
                    "ci_low": float(rmse_interval[0]), "ci_high": float(rmse_interval[1]),
                    "delta_r2": float(r2_point[method] - r2_point[reference]),
                    "r2_ci_low": float(r2_interval[0]), "r2_ci_high": float(r2_interval[1])}
        recorded = {name: float(getattr(contrast, name)) for name in computed}
        discrepancy = {name: abs(computed[name] - recorded[name]) for name in computed}
        np.testing.assert_allclose(list(computed.values()), list(recorded.values()), rtol=0, atol=tolerance,
                                   err_msg=f"Paired interval mismatch: {contrast.method} versus {contrast.reference}")
        if int(contrast.groups) != len(unique_groups):
            raise AssertionError("Reported bootstrap group count differs")
        errors.extend(discrepancy.values())
        records.append({"method": contrast.method, "reference": contrast.reference,
                        "recomputed": computed, "reported": recorded,
                        "maximum_absolute_error": max(discrepancy.values())})
    after = {name: sha256(path) for name, path in paths.items()}
    if before != after:
        raise AssertionError("Release inputs changed during independent verification")
    result = {
        "status": "passed",
        "release": str(release.relative_to(ROOT)) if release.is_relative_to(ROOT) else str(release),
        "method": "Explicit spatial-group row concatenation; fresh outcome mean, SSE and SST in every replicate; paired percentile differences",
        "seed": config["seed"], "bootstrap_draws": config["bootstrap_draws"],
        "observations_per_method": len(outcomes), "methods": len(methods), "spatial_groups": len(unique_groups),
        "contrasts_verified": len(records), "scalar_checks": len(errors),
        "absolute_tolerance": tolerance, "maximum_absolute_error": max(errors),
        "resampled_observation_count_minimum": min(sample_sizes),
        "resampled_observation_count_maximum": max(sample_sizes),
        "input_sha256": before,
        "verification_script_sha256": sha256(Path(__file__).resolve()),
        "versions": {"numpy": np.__version__, "pandas": pd.__version__},
        "comparisons": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "comparisons"}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=ROOT / "data/runs/zimbabwe_multiyear_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "results/multiyear/interval_verification.json")
    args = parser.parse_args()
    verify(args.release.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
