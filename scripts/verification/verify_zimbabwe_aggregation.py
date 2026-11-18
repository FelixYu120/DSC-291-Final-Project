"""Independently verify the released V0–V3 aggregates, splits, scores and primary interval.

Works for v1 and for the team-rule v2 release (``window_anchor: calendar``, ``training_rows:
include_primary``). Under v2 it also checks, without experiment code, that no feature uses a crop
date and that every permitted 2024 training row is ``labels_v1.include_primary``.
Recorded code/doc/config inputs that differ in the working tree are accepted only when the same
bytes exist in Git history at a commit that recorded this release (or differ only by CRLF checkout).
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--release", type=Path, default=root / "data/runs/zimbabwe_aggregation_v1"
)
parser.add_argument("--report", type=Path)
args = parser.parse_args()
out = args.release.resolve()
prior = root / "data/runs/zimbabwe_merge_v1"
manifest = json.loads((out / "manifest.json").read_text())
config = manifest["config"]


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


anchor = config.get("window_anchor", "crop_dates")
rule = config.get("training_rows", "all_screened")
assert anchor in {"crop_dates", "calendar"} and rule in {"all_screened", "include_primary"}
all_variants = ["v0_mean", "v1_preharvest_mean", "v1_calendar_mean", "v2_max", "v3_median", "v3_mode"]
variants = config.get("variants", all_variants)
if anchor == "calendar":
    assert "v1_preharvest_mean" not in variants
    assert "preharvest" not in config["primary_method"] + config["primary_reference"]


def release_commits(release):
    try:
        relative = (release / "manifest.json").relative_to(root).as_posix()
        return subprocess.run(["git", "-C", str(root), "log", "--all", "--format=%H", "--", relative],
                              capture_output=True, text=True, check=True).stdout.split()
    except (ValueError, OSError, subprocess.CalledProcessError):
        return []


def input_source(name, expected, commits):
    """Where the recorded input bytes were found; data files must match the working tree."""
    path = root / name
    if path.is_file() and sha(path) == expected:
        return "working_tree"
    if name.startswith("data/"):
        return None
    if path.is_file() and hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected:
        return "working_tree_crlf_checkout"
    for commit in commits:
        blob = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{name}"], capture_output=True)
        if blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == expected:
            return "recorded_git_history"
    return None


commits = release_commits(out)
input_sources = {}
for name, value in manifest["inputs"].items():
    found = input_source(name, value, commits)
    assert found is not None, ("input", name)
    input_sources[found] = input_sources.get(found, 0) + 1
for name, value in manifest["outputs"].items():
    assert sha(out / name) == value["sha256"], ("output", name)
for name in ["target_memberships.csv", "source_spatial_permissions.csv"]:
    assert (out / name).read_bytes() == (prior / name).read_bytes(), name
pred = pd.read_csv(out / "predictions.csv", dtype={"group_id": str})
obs = pd.read_csv(out / "observations.csv", dtype={"group_id": str}).set_index("obs_id")
metrics = pd.read_csv(out / "metrics.csv").set_index("method")
assert pred.groupby("method").size().eq(1504).all()
assert pred.groupby(["method", "outer_fold"]).size().eq(376).all()
assert set(pred.outer_fold) == {1, 2, 3, 4}
ids = set(obs.index[obs.domain.eq("lacuna") & obs.fold.isin([1, 2, 3, 4])])
for method, p in pred.groupby("method"):
    assert set(p.obs_id) == ids and p.obs_id.is_unique
    y = p.yield_t_ha.to_numpy()
    q = p.prediction_t_ha.to_numpy()
    e = q - y
    expected = [
        np.sqrt(np.mean(e**2)),
        np.mean(abs(e)),
        np.mean(e),
        1 - np.sum(e**2) / np.sum((y - y.mean()) ** 2),
    ]
    np.testing.assert_allclose(
        metrics.loc[method, ["rmse_t_ha", "mae_t_ha", "bias_t_ha", "r2"]].astype(float),
        expected,
        rtol=0,
        atol=1e-9,
    )
legacy = pd.read_csv(prior / "predictions.csv", dtype={"group_id": str})
# The step 9 pooled control trained on 2024 zeros; under include_primary only the
# Lacuna-only control is a reproduction of saved predictions.
for old, new in [
    ("lacuna_only", "legacy_indices_mean_max_target"),
    ("pooled_adaptive", "legacy_indices_mean_max_merged"),
][: 2 if rule == "all_screened" else 1]:
    a = legacy[legacy.method.eq(old)].set_index("obs_id").sort_index()
    b = pred[pred.method.eq(new)].set_index("obs_id").sort_index()
    assert a.index.equals(b.index)
    np.testing.assert_allclose(a.prediction_t_ha, b.prediction_t_ha, rtol=0, atol=1e-12)
# Direct cluster bootstrap of primary contrast, avoiding production's matrix-count formula.
methods = [config["primary_method"], config["primary_reference"]]
a = pred[pred.method.eq(methods[0])].set_index("obs_id").sort_index()
b = pred[pred.method.eq(methods[1])].set_index("obs_id").loc[a.index]
y = a.yield_t_ha.to_numpy()
p = a.prediction_t_ha.to_numpy()
q = b.prediction_t_ha.to_numpy()
groups = a.group_id.to_numpy()
uniq = np.unique(groups)
members = [np.flatnonzero(groups == g) for g in uniq]
rng = np.random.default_rng(config["seed"])
delta = []
for _ in range(config["bootstrap_draws"]):
    ix = np.concatenate([members[i] for i in rng.integers(len(uniq), size=len(uniq))])
    delta.append(
        np.sqrt(np.mean((p[ix] - y[ix]) ** 2)) - np.sqrt(np.mean((q[ix] - y[ix]) ** 2))
    )
ci = np.quantile(delta, [0.025, 0.975])
contrasts = pd.read_csv(out / "paired_differences.csv")
primary = contrasts[contrasts.primary_comparison].iloc[0]
np.testing.assert_allclose([primary.ci_low, primary.ci_high], ci, rtol=0, atol=1e-9)
# Reconstruct all temporal features without importing experiment code.
monthly = pd.read_parquet(out / "monthly_observations.parquet")
wide = pd.read_parquet(out / "features.parquet")
dictionary = json.loads((out / "feature_dictionary.json").read_text())
bands = ["b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12"]
indices = ["ndvi", "gcvi", "mtci", "ndvi705", "ndvi740"]
cols = bands + indices
# Under the calendar rule the reconstruction never reads a crop date.
m = monthly.merge(
    obs[["season_year", "plant_date", "harvest_date"] if anchor == "crop_dates" else ["season_year"]],
    left_on="obs_id",
    right_index=True,
    validate="many_to_one",
)
m["acquired"] = pd.to_datetime(m.acquired)
start = pd.to_datetime((m.season_year - 1).astype(str) + "-12-01")
end = pd.to_datetime(m.season_year.astype(str) + "-07-01")
cut = pd.to_datetime(
    m.season_year.astype(str) + "-" + config["calendar_cutoff_month_day"]
)
valid = ~m.missing & m.acquired.ge(start) & m.acquired.lt(end)
scopes = {
    "v0_mean": valid,
    "v2_max": valid,
    "v3_median": valid,
    "v1_calendar_mean": valid & m.acquired.lt(cut),
}
if anchor == "crop_dates":
    plant = pd.to_datetime(m.plant_date)
    harvest = pd.to_datetime(m.harvest_date)
    lower = plant.where(plant.notna() & plant.gt(start), start)
    upper = harvest.fillna(cut)
    scopes["v1_preharvest_mean"] = valid & m.acquired.ge(lower) & m.acquired.lt(upper)
expected_sets = {f"{family}_{variant}" for family in ["bands", "indices"] for variant in variants}
assert set(dictionary) == expected_sets | {"legacy_indices_mean_max"}, sorted(dictionary)
assert set(pred.method) == {f"{name}_{training}" for name in dictionary for training in ["target", "merged"]}
if anchor == "calendar":
    assert not any("preharvest" in name for name in list(dictionary) + list(pred.method))
for variant, mask in scopes.items():
    if variant not in variants:
        continue
    stat = (
        "max" if variant == "v2_max" else "median" if variant == "v3_median" else "mean"
    )
    agg = m[mask].groupby("obs_id")[cols].agg(stat).reindex(wide.index)
    for family, variables in [("bands", bands), ("indices", indices)]:
        expected = wide[dictionary[family + "_" + variant]]
        np.testing.assert_allclose(
            expected.to_numpy(),
            agg[variables].to_numpy(),
            rtol=1e-12,
            atol=1e-12,
            equal_nan=True,
        )


def independent_mode(values):
    a = sorted(float(x) for x in values if np.isfinite(x))
    n = len(a)
    if n == 0:
        return np.nan
    if n < 3:
        return sum(a) / n
    keep = (n + 1) // 2
    parts = [a[i : i + keep] for i in range(n - keep + 1)]
    widths = [p[-1] - p[0] for p in parts]
    minimum = min(widths)
    answer = [
        independent_mode(part)
        for part, w in zip(parts, widths)
        if abs(w - minimum) <= 1e-12 + 1e-12 * abs(minimum)
    ]
    return sum(answer) / len(answer)


agg = m[valid].groupby("obs_id")[cols].agg(independent_mode).reindex(wide.index)
for family, variables in [("bands", bands), ("indices", indices)] if "v3_mode" in variants else []:
    np.testing.assert_allclose(
        wide[dictionary[family + "_v3_mode"]].to_numpy(),
        agg[variables].to_numpy(),
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )
# Check selected source counts against the original permission table.
select = pd.read_csv(out / "selected_parameters.csv")
perm = pd.read_csv(out / "source_spatial_permissions.csv")
training_rows = {"rule": rule}
if rule == "include_primary":
    # Read the team flag straight from the frozen labels, not from the release.
    labels = pd.read_parquet(root / "data/processed/labels_v1.parquet").set_index("obs_id")
    primary_flag = labels.include_primary.reindex(obs.index).fillna(False).astype(bool)
    pool = obs.index[obs.domain.eq("zimbabwe_2024") & obs.feature_eligible.astype(bool) & primary_flag]
    dropped = obs.index[obs.domain.eq("zimbabwe_2024") & obs.feature_eligible.astype(bool) & ~primary_flag]
    assert primary_flag.loc[obs.domain.eq("lacuna")].all()
    assert len(pool) == 2456 and len(dropped) == 1874
    assert set(labels.loc[dropped, "exclusion_reason"]) == {"zimbabwe_2024_zero_likely_not_measured"}
    assert obs.loc[dropped, "yield_t_ha"].eq(0).all()
    audit_rows = pd.read_csv(out / "training_rows_audit.csv").set_index("obs_id").loc[obs.index]
    assert np.array_equal(audit_rows.training_pool.astype(bool), obs.index.isin(pool) | obs.domain.eq("lacuna"))
    assert np.array_equal(audit_rows.include_primary.astype(bool), primary_flag)
    perm = perm[perm.obs_id.isin(pool)]
    training_rows.update({"source_training_pool": len(pool), "source_excluded_zero_rows": len(dropped),
                          "lacuna_rows_all_include_primary": True})
allows = (
    perm[perm.inner_fold.eq(0) & perm.allowed_by_spatial_rule]
    .groupby("outer_fold")
    .size()
)
for r in select.itertuples():
    assert r.source_allowed == allows.loc[r.outer_fold]
    assert r.source_used == (r.source_allowed if r.source_ratio > 0 else 0)
    assert r.target_fit == 1128 and r.target_evaluation == 376
result = {
    "all_checks_passed": True,
    "model_arms": int(pred.method.nunique()),
    "predictions": len(pred),
    "primary_delta_rmse": float(primary.delta_rmse_t_ha),
    "primary_ci_independent": ci.tolist(),
    "input_hashes": len(manifest["inputs"]),
    "input_sources": input_sources,
    "window_anchor": anchor,
    "training_rows": training_rows,
    "output_hashes": len(manifest["outputs"]),
    "feature_reconstruction": f"all {len(variants)} model variants for all 6212 candidates and all 15 variables"
    + ("; no crop date read" if anchor == "calendar" else ""),
    "mode": "separate recursive implementation",
    "membership_and_permissions": "byte-identical to original",
    "original_control_predictions": "exact within 1e-12" + ("" if rule == "all_screened" else " (Lacuna-only control)"),
    "source_usage_by_method": select.groupby("method")
    .source_used.apply(list)
    .to_dict(),
}
result["verifier_sha256"] = sha(Path(__file__))
result["manifest_sha256"] = sha(out / "manifest.json")
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
