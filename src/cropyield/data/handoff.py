"""Verified Zimbabwe release, derived without changing the frozen team data.

Raw values are independently reconciled with labels_v1. The existing folds are
mapped to explicit roles; no model is trained and no new holdout is claimed.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import itertools
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from cropyield import ROOT
from cropyield.data.labels import sha256
from cropyield.data.xy import FEATURES
from cropyield.eval.splits import EARTH_RADIUS_KM, connected_clusters, unit_xyz

COHORT = "zimbabwe_lacuna_2022_2023"
BANDS = ["b02", "b03", "b04", "b05", "b06", "b07", "b08", "b8a", "b11", "b12"]
INDICES = ["ndvi", "gcvi", "mtci", "ndvi705", "ndvi740"]
DEFAULT_OUTPUT = ROOT / "data/processed/zimbabwe_midterm_v1"
CONFIG = ROOT / "configs/zimbabwe_midterm_v1.json"
TEAM_OUTPUT = ROOT / "data/processed/zimbabwe_midterm_v2"
TEAM_CONFIG = ROOT / "configs/zimbabwe_midterm_v2.json"
# Fold roles. The legacy scheme of release v1 names fold 1 "validation" and folds 2-4 "train". The team rule
# (docs/EVALUATION.md) cross-validates over folds 1-4 and holds fold 0 back; release v2 records that scheme.
LEGACY_ROLES = {"0": "test", "1": "validation", "2": "train", "3": "train", "4": "train"}
TEAM_ROLES = {"0": "holdout", "1": "cv", "2": "cv", "3": "cv", "4": "cv"}
RESTRICTED_PARTITIONS = {"test", "holdout"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def partition_order(roles: dict) -> list[str]:
    """The partitions of one of the two allowed role schemes, in reporting order."""
    require(roles in (LEGACY_ROLES, TEAM_ROLES), "Changing role assignment requires a separately reviewed protocol")
    return ["train", "validation", "test"] if roles == LEGACY_ROLES else ["cv", "holdout"]


def read_raw(path: Path) -> tuple[pd.DataFrame, dict]:
    """Independent maize extraction with all rows retained, including rejected rows."""
    source = json.loads(path.read_text(encoding="utf-8"))
    records, crops = [], {}
    for number, feature in enumerate(source["features"], 1):
        p = feature["properties"]
        crops[p["Crop_Type"]] = crops.get(p["Crop_Type"], 0) + 1
        if p["Crop_Type"] != "Maize/Corn":
            continue
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or [None, None]
        require(geometry.get("type") == "Point", f"Raw row {number}: expected point geometry")
        records.append({
            "obs_id": f"zimbabwe:{p['Case_ID']}", "source_id": p["Case_ID"], "source_row": number,
            "lat": coordinates[1], "lon": coordinates[0], "country": p.get("Adm0"),
            "source_yield_t_ha": p.get("Yield(Mt/H"), "dry_weight_kg": p.get("Dry_weight"),
            "wet_weight_kg": p.get("Wet_Weight"), "plant_date": p.get("Planting_D"),
            "harvest_date": p.get("Harvesting"), "intercropping_raw": p.get("Intercropp"),
            "irrigation_raw": p.get("Field_Irri"), "admin_unit_raw": p.get("Admin1"),
            "crop_condition_raw": p.get("Crop_Condi"), "crop_variety_raw": p.get("Crop_Varie"),
        })
    raw = pd.DataFrame(records)
    require(len(raw) > 0, "No maize records in provider file")
    require(raw.source_id.notna().all() and raw.source_id.is_unique, "Missing or duplicate provider Case_ID")
    require(raw.source_id.astype(str).str.strip().ne("").all(), "Empty provider Case_ID")
    for name in ["lat", "lon", "source_yield_t_ha", "dry_weight_kg", "wet_weight_kg"]:
        raw[name] = pd.to_numeric(raw[name], errors="coerce")
    for name in ["plant_date", "harvest_date"]:
        raw[name] = pd.to_datetime(raw[name], format="ISO8601", errors="coerce")
    for src, dst in [("intercropping_raw", "intercropped"), ("irrigation_raw", "irrigated")]:
        text = raw[src].astype("string").str.strip().str.lower()
        require(text.isin(["yes", "no"]).all(), f"Unknown {src}: never infer unknown means no")
        raw[dst] = text.eq("yes")
    raw["admin_unit"] = raw.admin_unit_raw.astype("string").str.strip().str.lower()
    require(raw.admin_unit.notna().all() and raw.admin_unit.ne("").all(), "Missing Admin1")
    raw["season_year"] = raw.harvest_date.dt.year.astype("Int64")
    require(raw.season_year.notna().all() and raw.season_year.isin([2022, 2023]).all(), "Unexpected harvest year")
    raw["yield_kg_ha"] = raw.source_yield_t_ha * 1000
    raw["expected_t_ha_from_dry_weight"] = raw.dry_weight_kg * 0.25
    tolerance = np.maximum(0.001, 0.001 * np.maximum(raw.source_yield_t_ha.abs(), raw.expected_t_ha_from_dry_weight.abs()))
    raw["yield_conversion_mismatch"] = (
        ~np.isfinite(raw.source_yield_t_ha) | ~np.isfinite(raw.expected_t_ha_from_dry_weight)
        | (raw.source_yield_t_ha - raw.expected_t_ha_from_dry_weight).abs().gt(tolerance))
    raw["dry_weight_exceeds_wet_weight"] = raw.dry_weight_kg > raw.wet_weight_kg
    raw["valid_yield"] = np.isfinite(raw.yield_kg_ha) & raw.yield_kg_ha.between(0, 30000)
    # Same coarse envelope as the frozen screen. This is NOT a country-boundary test.
    raw["within_screening_envelope"] = raw.lon.between(25.1, 33.1) & raw.lat.between(-22.5, -15.5)
    raw["valid_weights"] = (np.isfinite(raw.dry_weight_kg) & np.isfinite(raw.wet_weight_kg)
                            & raw.dry_weight_kg.ge(0) & raw.wet_weight_kg.ge(0))
    raw["screened_in"] = (raw.valid_yield & raw.within_screening_envelope & raw.valid_weights
                           & ~raw.yield_conversion_mismatch & ~raw.dry_weight_exceeds_wet_weight)
    raw["growing_days"] = (raw.harvest_date - raw.plant_date).dt.days
    raw["invalid_date_order"] = raw.growing_days.isna() | raw.growing_days.le(0)
    raw["exact_coordinate_reuse"] = raw.duplicated(["lat", "lon"], keep=False)
    raw["is_zero"] = raw.yield_kg_ha.eq(0)
    # Multiple reasons are kept, alongside the legacy first-reason field below.
    rules = [
        (~raw.valid_yield, "invalid_or_extreme_yield"),
        (~raw.within_screening_envelope, "outside_screening_envelope"),
        (~raw.valid_weights, "invalid_weights"),
        (raw.yield_conversion_mismatch, "yield_conversion_mismatch"),
        (raw.dry_weight_exceeds_wet_weight, "dry_weight_exceeds_wet_weight"),
        (raw.season_year.eq(2022), "2022_imagery_policy"),
        (raw.intercropped, "intercropped"), (raw.irrigated, "irrigated"),
        (raw.yield_kg_ha.gt(15000), "yield_above_15_t_ha"),
    ]
    raw["all_exclusion_reasons"] = [
        ";".join(name for mask, name in rules if mask.iloc[i]) for i in range(len(raw))]
    raw["include_primary_rederived"] = raw.all_exclusion_reasons.eq("")
    return raw, {"source_records": len(source["features"]), "crop_counts": crops}


def reconcile_labels(raw: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Fail on stale or corrupted labels, including dropped/extra joins and unknown management."""
    labels = labels.loc[labels.cohort.eq(COHORT)].copy()
    require(labels.obs_id.is_unique and labels.obs_id.notna().all(), "Frozen labels have duplicate/missing IDs")
    require(set(raw.loc[raw.screened_in, "obs_id"]) == set(labels.obs_id), "Raw screen and frozen IDs disagree")
    pairs = raw.merge(labels, on="obs_id", how="inner", validate="one_to_one", suffixes=("__raw", "__label"))
    for name, tolerance in [("yield_kg_ha", 1e-6), ("lat", 1e-7), ("lon", 1e-7), ("source_row", 0)]:
        require(np.isclose(pairs[f"{name}__raw"].astype(float), pairs[f"{name}__label"].astype(float),
                           rtol=0, atol=tolerance).all(), f"Raw vs frozen mismatch: {name}")
    for name in ["source_id", "season_year", "plant_date", "harvest_date", "admin_unit", "intercropped", "irrigated"]:
        require(pairs[f"{name}__label"].notna().all(), f"Missing frozen {name}")
        require(pairs[f"{name}__raw"].eq(pairs[f"{name}__label"]).all(), f"Raw vs frozen mismatch: {name}")
    require(pairs.include_primary_rederived.eq(pairs.include_primary).all(), "Inclusion rules no longer match frozen labels")
    require(labels.unit_provisional.eq(True).all(), "Unit uncertainty was silently removed")
    require(labels.moisture_basis_pct.isna().all(), "Unsupported moisture correction")
    return labels.sort_values("obs_id").reset_index(drop=True)


def explicit_split(split: pd.DataFrame, labels: pd.DataFrame, roles: dict, family: str) -> tuple[pd.DataFrame, dict]:
    """Keep immutable fold membership and label each fold's use: legacy train/validation/test or team cv/holdout."""
    require(split.obs_id.is_unique, f"{family}: duplicate split ID")
    require(set(split.obs_id) == set(labels.obs_id), f"{family}: split coverage differs from primary labels")
    require(split.family.eq(family).all() and split["repeat"].eq(0).all(), f"{family}: unexpected family/repeat")
    require(split.cohort.eq(COHORT).all(), f"{family}: wrong cohort")
    table = split.copy()
    table["partition"] = table.fold.astype(str).map(roles)
    require(table.partition.notna().all(), f"{family}: unknown fold")
    order = partition_order(roles)
    require(set(table.partition) == set(order), f"{family}: an empty partition")
    require(table.groupby("group_id").partition.nunique().max() == 1, f"{family}: split group leakage")
    where = table.merge(labels[["obs_id", "lat", "lon", "admin_unit", "season_year"]],
                        on="obs_id", validate="one_to_one", suffixes=("", "_label"))
    require(where.season_year.eq(where.season_year_label).all(), f"{family}: wrong season")
    # Recompute near-neighbour groups on the retained population, not on discarded bridging rows.
    near = connected_clusters(where.lat.to_numpy(), where.lon.to_numpy(), 0.01)
    require(where.partition.groupby(near).nunique().max() == 1, f"{family}: near-duplicate leakage")
    if family == "s2_region":
        require(where.groupby("admin_unit").partition.nunique().max() == 1, "Admin1 crosses partitions")
    xyz = unit_xyz(where.lat.to_numpy(), where.lon.to_numpy())
    distances = {}
    pairs = [("partition", left, right) for left, right in itertools.combinations(order, 2)]
    if roles == TEAM_ROLES:  # the cross-validation folds must also be 2 km apart from each other
        folds = sorted(where.fold.astype(str).unique())
        pairs += [("fold", left, right) for left, right in itertools.combinations(folds, 2)]
    for column, left, right in pairs:
        a, b = xyz[where[column].astype(str).eq(left)], xyz[where[column].astype(str).eq(right)]
        chord = cKDTree(b).query(a)[0].min()
        distance = 2 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / (2 * EARTH_RADIUS_KM), 0, 1))
        name = f"{left}_to_{right}" if column == "partition" else f"fold{left}_to_fold{right}"
        distances[name] = float(distance)
        if family == "s1_cc2km":
            require(distance >= 2 - 1e-8, f"{family}: {left}/{right} separation below 2 km")
    summary = {"rows": table.partition.value_counts().sort_index().to_dict(),
               "groups": table.groupby("partition").group_id.nunique().to_dict(),
               "minimum_distance_km": distances,
               "test_status": "historical_previously_evaluated", "new_models_may_score_test": False}
    return table.sort_values("obs_id").reset_index(drop=True), summary


def database_tables(database: Path, labels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Extract scalar features/series from a read-only connection. Never rebuild the shared DB."""
    with duckdb.connect(str(database), read_only=True) as con:
        master = con.execute(f"""SELECT obs_id, yield_kg_ha, include_primary, months_with_data,
            {', '.join(FEATURES)} FROM master WHERE cohort = ? ORDER BY obs_id""", [COHORT]).df()
        require(master.obs_id.is_unique and set(master.obs_id) == set(labels.obs_id), "Database ID mismatch")
        check = master.merge(labels[["obs_id", "yield_kg_ha", "include_primary"]], on="obs_id", validate="one_to_one")
        require(np.isclose(check.yield_kg_ha_x, check.yield_kg_ha_y, rtol=0, atol=1e-6).all(), "Database yield mismatch")
        require(check.include_primary_x.eq(check.include_primary_y).all(), "Database inclusion mismatch")
        monthly = con.execute(f"""SELECT c.obs_id, c.month, c.state AS coverage_state,
            s.acquired AS acquired_date, b.field_pixels, b.missing,
            {', '.join('b.' + name for name in BANDS)}, {', '.join('v.' + name for name in INDICES)}
            FROM coverage c JOIN labels l USING (obs_id)
            LEFT JOIN scenes s USING (obs_id, month)
            LEFT JOIN monthly_bands b USING (obs_id, month)
            LEFT JOIN vegetation_indices v USING (obs_id, month)
            WHERE l.cohort = ? ORDER BY c.obs_id, c.month""", [COHORT]).df()
    require(not monthly.duplicated(["obs_id", "month"]).any(), "Duplicate observation-month; join would inflate sequences")
    require(set(monthly.obs_id) == set(labels.obs_id), "Missing monthly observation")
    for year, part in labels.groupby("season_year"):
        rows = monthly[monthly.obs_id.isin(part.obs_id)]
        expected = set(pd.period_range(f"{int(year)-1}-10", f"{int(year)}-06", freq="M").astype(str))
        require(set(rows.month) == expected and rows.groupby("obs_id").size().eq(9).all(), "Incomplete season spine")
    require(monthly.missing.notna().all(), "Missing monthly missingness flag")
    require(monthly.loc[monthly.missing, BANDS].isna().all().all(), "Missing month has reflectance values")
    require(np.isfinite(monthly.loc[~monthly.missing, BANDS].to_numpy()).all(), "Observed month has invalid reflectance")
    require(monthly.loc[~monthly.missing, "acquired_date"].notna().all(), "Observed month has no acquisition date")
    counts = monthly.assign(observed=~monthly.missing).groupby("obs_id")["observed"].sum()
    require(master.set_index("obs_id").months_with_data.eq(counts.reindex(master.obs_id).to_numpy()).all(),
            "Clear month counts disagree")
    timeline = monthly.merge(labels[["obs_id", "plant_date", "harvest_date", "include_primary", "season_year"]],
                             on="obs_id", validate="many_to_one")
    timeline["after_harvest"] = timeline.acquired_date > timeline.harvest_date
    timeline["before_planting"] = timeline.acquired_date < timeline.plant_date
    timing = timeline.groupby("obs_id").agg(postharvest_scenes=("after_harvest", "sum"),
                                             preplanting_scenes=("before_planting", "sum"))
    monthly["time_index"] = monthly.groupby("obs_id").cumcount()
    primary = timeline[timeline.include_primary]
    coverage = primary.groupby(["month", "coverage_state"]).size().rename("records").reset_index()
    stats = {
        "postharvest_fields": int(primary.loc[primary.after_harvest, "obs_id"].nunique()),
        "postharvest_scenes": int(primary.after_harvest.sum()),
        "preplanting_fields": int(primary.loc[primary.before_planting, "obs_id"].nunique()),
        "clear_months_by_year": master.merge(labels[["obs_id", "season_year"]], on="obs_id")
            .groupby(["season_year", "months_with_data"]).size().rename("records").reset_index().to_dict("records"),
    }
    return master.merge(timing, on="obs_id", validate="one_to_one"), monthly, coverage, stats


def csv_write(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", date_format="%Y-%m-%d", float_format="%.12g")


def json_write(value: dict, path: Path) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def input_hashes(root: Path, database: Path, config_path: Path) -> dict:
    paths = [root / "data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson",
             root / "data/metadata/zimbabwe.json", root / "data/processed/labels_v1.parquet",
             root / "data/splits/manifest.json", root / "configs/team_database_v1.json",
             root / "data/audit/zimbabwe_screened_candidates.csv",
             root / "data/raw/zimbabwe/Yield_forecasting _and_Crop_Mask_LACUNA_Technical_Manual.py",
             root / "docs/DECISIONS.md", root / "docs/EVALUATION.md", root / "docs/ZIMBABWE_DATA_HANDOFF.md",
             root / "requirements.txt", root / "pyproject.toml", config_path, database]
    paths += [root / f"data/splits/{COHORT}__{family}.csv" for family in ["s1_cc2km", "s2_region"]]
    paths += [root / "src/cropyield/data/handoff.py", root / "src/cropyield/eval/splits.py",
              root / "src/cropyield/data/xy.py", root / "scripts/step8_build_zimbabwe_handoff.py"]
    return {str(p.relative_to(root)) if p.is_relative_to(root) else str(p): sha256(p) for p in paths}


def verify_inputs(root: Path, database: Path) -> None:
    manifest = json.loads((root / "data/splits/manifest.json").read_text())
    require(sha256(root / "data/processed/labels_v1.parquet") == manifest["labels_sha256"], "Frozen label hash mismatch")
    for family in ["s1_cc2km", "s2_region"]:
        name = f"{COHORT}__{family}.csv"
        require(sha256(root / "data/splits" / name) == manifest["files"][name]["sha256"], f"Frozen split hash mismatch: {name}")
    expected = json.loads((root / "configs/team_database_v1.json").read_text())
    require(database.stat().st_size == expected["bytes"] and sha256(database) == expected["sha256"],
            "Database differs from the pinned team copy; do not rebuild or silently accept a partial copy")
    metadata = json.loads((root / "data/metadata/zimbabwe.json").read_text())
    provider = root / "data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson"
    entry = next(f for f in metadata["files"] if f["key"] == provider.name)
    require("md5:" + hashlib.md5(provider.read_bytes()).hexdigest() == entry["checksum"], "Provider checksum mismatch")


def write_overview(path: Path, summary: dict, labels: pd.DataFrame, split: pd.DataFrame, coverage: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
    stages = ["Raw maize", "Consistent labels", "2023 labels", "Primary / model"]
    counts = [summary[k] for k in ["raw_maize", "cleaned_labels", "screened_2023", "model_rows"]]
    axes[0].barh(stages[::-1], counts[::-1], color="#2176ae")
    for y, value in enumerate(counts[::-1]):
        axes[0].text(value + 18, y, f"{value:,}", va="center", fontsize=10)
    axes[0].set(xlabel="Records", title="Inclusion accounting", xlim=(0, max(counts) * 1.2))
    months = sorted(coverage.month.unique())
    bottom = np.zeros(len(months))
    for state, color in [("clear", "#2176ae"), ("cloudy", "#eea236"), ("no_scene", "#b6bbc2")]:
        values = coverage[coverage.coverage_state.eq(state)].set_index("month").records.reindex(months, fill_value=0).to_numpy()
        axes[1].bar(range(len(months)), values, bottom=bottom, label=state.replace("_", " "), color=color)
        bottom += values
    axes[1].set_xticks(range(len(months)), months, rotation=60, ha="right")
    axes[1].set(ylabel="Primary fields", title="Monthly satellite coverage", ylim=(0, bottom.max() * 1.16))
    axes[1].legend(frameon=False, fontsize=9, loc="upper center", ncol=3)
    points = split.merge(labels[["obs_id", "lat", "lon"]], on="obs_id", validate="one_to_one")
    styles = {"train": ("#2176ae", ".", "train"), "validation": ("#eea236", "+", "validation"),
              "test": ("#b2425b", "x", "test (historical)"), "cv": ("#2176ae", ".", "cross-validation, folds 1–4"),
              "holdout": ("#b2425b", "x", "fold 0, held back")}
    for part, (color, marker, label) in styles.items():
        group = points[points.partition.eq(part)]
        if len(group):
            axes[2].scatter(group.lon, group.lat, s=13, c=color, marker=marker, alpha=.7, label=label)
    axes[2].set(xlabel="Longitude (degrees)", ylabel="Latitude (degrees)", title="Primary split: field coordinates")
    axes[2].legend(frameon=False, fontsize=9)
    fig.suptitle("Zimbabwe Lacuna data audit — November 7, 2026", fontsize=14)
    fig.savefig(path, dpi=160, metadata={"Software": "cropyield Zimbabwe handoff"})
    plt.close(fig)


def write_report(path: Path, summary: dict, config: dict) -> None:
    s = summary
    order = partition_order(config["fold_roles"])
    legacy = config["fold_roles"] == LEGACY_ROLES
    split_lines = []
    for name, info in s["splits"].items():
        counts = info["rows"]
        distances = info["minimum_distance_km"]
        split_lines.append(f"| {name} | " + " | ".join(str(counts[part]) for part in order) + " | "
                           f"{min(distances.values()):.3f} |")
    pair_check = ("Primary split train/validation/test pairs are separated by at least 2 km." if legacy else
                  "In the primary split every pair of folds is separated by at least 2 km.")
    table = chr(10).join(split_lines)
    if legacy:
        partitions = f"""Existing fold 0 → test; fold 1 → validation; folds 2–4 → train. No frozen assignment is changed.

| Family | Train | Validation | Test | Minimum across partition pairs (km) |
|---|---:|---:|---:|---:|
{table}

`s1_cc2km` is the primary new-location comparison. `s2_region` is the Admin1 holdout sensitivity analysis; it does not promise 2 km separation.
Fit clipping, imputation, scaling and hyperparameters on training data only. Use grouped internal CV or the validation partition for tuning.
Monthly rows inherit their field's partition; never randomly split observation-month rows.

**Evaluation history:** test is a historical, previously evaluated partition, not an untouched prospective holdout.
The November 1 decision permits no new model arm to score fold 0 in any family. This release preserves that restriction and trains no models.
New models can develop on training/validation data; a genuinely fresh confirmation needs new unexamined observations or an explicitly revised protocol."""
    else:
        partitions = f"""Folds 1–4 → cv; fold 0 → holdout. This is the team protocol (`docs/EVALUATION.md`): cross-validate over folds 1–4
(fit on three folds, predict the fourth) and score the pooled out-of-fold predictions; fold 0 is held back. No frozen
assignment is changed; `fold` keeps the original fold number.

| Family | Cross-validation (folds 1–4) | Held back (fold 0) | Minimum across fold pairs (km) |
|---|---:|---:|---:|
{table}

`s1_cc2km` is the primary new-location comparison. `s2_region` is the Admin1 holdout sensitivity analysis; it does not promise 2 km separation.
Fit clipping, imputation, scaling and hyperparameters on the training folds only, with grouped inner CV.
Monthly rows inherit their field's partition and fold; never randomly split observation-month rows.

**Evaluation history:** R0, R1, R2 and A1 were already scored on fold 0 (owner ruling, 1 Nov 2026). No new model arm
scores fold 0 in any family, except one pre-registered final test. This release trains no models."""
    text = f"""# Zimbabwe Lacuna data audit

Generated by `python scripts/step8_build_zimbabwe_handoff.py`, release `{config['release']}`.
This is a data audit, not a model evaluation. Every reported count is calculated from the pinned local files.

## Population and inclusion

| Stage | Records | Rule |
|---|---:|---|
| Provider file, all crops | {s['source_records']:,} | Original GeoJSON |
| Raw maize | {s['raw_maize']:,} | Crop_Type = Maize/Corn |
| Consistent maize labels | {s['cleaned_labels']:,} | Reject {s['unit_mismatch_rows']} crop-cut conversion mismatches; preserve originals in row_audit.csv |
| 2023 consistent labels | {s['screened_2023']:,} | Keep {s['screened_2022']} 2022 rows in the label export, outside primary modeling |
| 2023 pure stand | {s['screened_2023'] - s['intercrop_exclusions']:,} | Exclude {s['intercrop_exclusions']} intercropped records |
| 2023 pure stand, rainfed | {s['primary_labels']:,} | Exclude {s['irrigation_exclusions']} irrigated records |
| Model table | {s['model_rows']:,} | At least {config['minimum_clear_months']} observed months, all 10 seasonal features finite |

Exclusion counts above are sequential, not overlapping flag totals. All {s['zero_yield_primary']} primary zero yields stay.
The filename contains 2022–2023; the delivered primary model population is 2023 only.

## Checks completed

- Provider MD5, frozen labels SHA-256, both split SHA-256 values and complete team database SHA-256 match their manifests.
- Raw IDs, source-row numbers, coordinates (both longitude and latitude), yield, dates, management and normalized Admin1 agree with frozen labels.
- Independently reconstructed screening and primary inclusion match the frozen IDs and flags.
- Label IDs and database IDs are unique. Observation-month keys are unique; each observation has nine ordered season months.
- Database yields and inclusion flags match the label file; observed-month counts match the monthly table.
- Missing months contain missing reflectance, rather than fabricated zeros. Observed reflectance and model features are finite.
- Split membership covers every primary observation exactly once, and keeps each splitting group whole.
- No pair within 10 m crosses partitions. {pair_check}

## Yield and source limitations

The source column `Yield(Mt/H` is interpreted as metric tonnes/ha, multiplied by 1,000 once to obtain kg/ha.
For a 40 m² cut, dry kg × 10,000 / 40 / 1,000 = dry kg × 0.25 t/ha. The {s['unit_mismatch_rows']} rejected rows
instead have dry kg × 0.5. Their true cut area is unknown, so no automatic correction is made.
The metadata says “Megatonnes”; the provider Python manual describes Mg/ha, consistent with the numeric identity.
`unit_provisional=true` remains in the frozen labels. Moisture percentage and grain-versus-cob basis remain unverified.
Dry weight, wet weight, reported yield and crop-condition labels are audit fields, never satellite-model predictors.

## Spatial and temporal quality

- Primary rows with exactly reused coordinates: **{s['exact_coordinate_reuse_primary']}**. Proximity alone does not prove duplicate farms.
- Primary rows with another primary row within 10 m: **{s['near_duplicate_primary']}**. They stay grouped, with their original yields.
- Legacy near_dup_10m flags can also refer to excluded rows; use the population-specific flag in row_audit.csv for this count.
- Primary records with harvest dates outside the fixed Oct–Jun window: **{s['outside_window_primary']}**.
- Raw records with absent or nonpositive growing duration: **{s['invalid_dates_raw']}**.
- Admin1 has **{s['admin_units_primary']}** values among primary rows, but mixes administrative levels; call these Admin1 groups, not verified districts.
- Location screening uses a bounding box, not a national boundary polygon or field-boundary verification. GPS accuracy is undocumented.
- Observed scenes after the recorded harvest: **{s['postharvest_scenes']:,}**, affecting **{s['postharvest_fields']:,}/{s['primary_labels']:,}** primary fields.
  Full-season features are retrospective yield-estimation inputs. A forecasting experiment needs a declared prediction date and separately built features
  restricted to information available by that date; filtering by the future actual harvest date is not a deployable forecasting rule.
- October and November 2022 have no accepted scenes in this pinned extraction. Do not describe missing months as crop absence.
- 2022 has limited imagery (see audit_summary.json); the existing policy excludes it. This is not proof that imagery is unavailable from every archive.

## Explicit partitions

{partitions}

## Reproducibility and handoff

`manifest.json` records config, package versions, code/input hashes, output hashes and the repository commit.
The builder uses a read-only database connection, stages outputs in a temporary directory, and refuses to replace an existing non-identical release.
Rebuild with the same inputs to verify byte-identical outputs. Choose a new output directory for a revised release.
See [the handoff guide](README.md) for the code map, dictionary, usage and methodological limitations.
`label_summary.csv` gives descriptive yield statistics by harvest year and inclusion status;
`feature_quality.csv` lists finite/missing counts and numerical ranges without removing outliers or fitting transforms.

![Data overview](data_overview.png)

Sources: [PULA / Lacuna release](https://doi.org/10.5281/zenodo.10060610), its local GeoJSON and Python manual;
`docs/DECISIONS.md`; `docs/EVALUATION.md`; [grouped evaluation guidance](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).
"""
    path.write_text(text, encoding="utf-8")


def write_dictionary(path: Path, tables: dict[str, pd.DataFrame], roles: dict = LEGACY_ROLES) -> None:
    descriptions = {
        "obs_id": "Stable field-season key; join tables using this, never row order",
        "source_id": "Provider Case_ID; no verified longitudinal farm identifier",
        "source_row": "1-based position in provider GeoJSON features array",
        "source_sha256": "Legacy provenance: SHA-256 of screened audit CSV, not the raw GeoJSON",
        "role": "Legacy cohort priority; superseded for midterm scope, retained for snapshot compatibility",
        "season_year": "Harvest calendar year; primary release uses 2023",
        "season_start": "Fixed October 1 of prior calendar year",
        "season_end": "Fixed June 30 of harvest year",
        "yield_kg_ha": "Target: provider metric tonnes/ha multiplied by 1000; provisional measurement basis",
        "yield_t_ha": "Target in metric tonnes/ha; yield_kg_ha / 1000",
        "lat": "WGS84 latitude, degrees north (negative in Zimbabwe)",
        "lon": "WGS84 longitude, degrees east",
        "geometry_type": "Point for Zimbabwe; not a field polygon",
        "geometry_wkt": "Null: no walked field boundary supplied",
        "field_area_ha": "Null: no whole-field area supplied; not the crop-cut area",
        "cut_area_m2": "Declared crop-cut area, 40 square metres",
        "n_cuts": "One declared crop cut per observation",
        "yield_definition": "cut_8x5m_dry_weight; measurement protocol identifier",
        "moisture_basis_pct": "Null means unknown, never zero percent",
        "unit_provisional": "True: unresolved source terminology / measurement basis retained",
        "cut1_kg_ha": "Null for Lacuna; no separately released repeat-cut yield",
        "cut2_kg_ha": "Null for Lacuna; no repeat-cut noise estimate available",
        "plant_date": "Recorded planting date; source value, never inferred",
        "harvest_date": "Recorded harvest date; source value, never inferred",
        "obs_date": "Legacy observation date: harvest date for Lacuna",
        "obs_date_source": "harvest_date for Lacuna",
        "intercropped": "True means maize intercropped; excluded from primary analysis",
        "irrigated": "True means irrigated; excluded from primary analysis",
        "admin_unit": "Trimmed lower-case provider Admin1, with mixed administrative levels",
        "site_unit": "Null: provider has no corresponding site grouping",
        "site_distance_km": "Null: provider has no site coordinate pair",
        "cluster_2km": "Legacy cluster computed over all screened cohort years; use split group_id to partition",
        "near_dup_10m": "Legacy neighbour flag over all screened rows, including excluded rows",
        "near_duplicate_primary": "Has another primary observation within 10 m, recomputed on primary population",
        "polygon_overlap_dup": "False for point data; does not establish absence of overlapping fields",
        "is_zero": "True for reported zero yield; retained in primary analysis",
        "date_outside_window": "Recorded observation date outside fixed Oct–Jun extraction window",
        "impossible_date": "Legacy flag for incompatible planting/harvest ordering or year",
        "source_flags": "Semicolon-separated legacy audit warnings",
        "include_primary": "True for 2023, pure stand, rainfed and existing label-quality rules",
        "exclusion_reason": "Legacy first exclusion reason; raw row audit also carries all applicable reasons",
        "screened_in": "Independent raw label-quality screen; includes both years",
        "include_primary_rederived": "Independent reconstruction of primary eligibility from raw provider values",
        "all_exclusion_reasons": "All applicable independent reasons; empty means primary eligible",
        "dry_weight_kg": "Provider crop-cut dry mass; directly determines target, forbidden model predictor",
        "wet_weight_kg": "Provider crop-cut harvest mass; unavailable for preharvest prediction",
        "source_yield_t_ha": "Original yield column interpreted as metric tonnes/ha, never overwritten",
        "expected_t_ha_from_dry_weight": "dry_weight_kg × 0.25 for the declared 40 m² cut; audit only",
        "yield_conversion_mismatch": "Provider yield disagrees with dry mass conversion (rtol=0.001, atol=0.001 t/ha)",
        "dry_weight_exceeds_wet_weight": "Dry mass exceeds wet mass; screening failure",
        "valid_yield": "Finite, nonnegative yield at most 30000 kg/ha for raw screening",
        "within_screening_envelope": "Inside coarse Zimbabwe bounding box; not country-polygon verification",
        "valid_weights": "Both dry and wet masses are finite and nonnegative",
        "growing_days": "Recorded harvest minus planting, days; audit only",
        "invalid_date_order": "Missing dates or nonpositive growing duration",
        "exact_coordinate_reuse": "Two or more raw maize observations share coordinates; not proof of duplicate farm",
        "months_with_data": "Count of months with at least one valid field pixel, not independent samples",
        "postharvest_scenes": "Accepted acquisitions after recorded harvest; audit only",
        "preplanting_scenes": "Accepted acquisitions before recorded planting; audit only",
        "month": "YYYY-MM calendar month; nine months per field, including missing months",
        "time_index": "Zero-based position in fixed season, 0=October, 8=June",
        "coverage_state": "clear, cloudy, no_scene or download_error from pinned extraction",
        "acquired_date": "Date of accepted scene; null for a month without a scene",
        "field_pixels": "Number of clear field pixels used; point fields usually one",
        "missing": "True means no valid field reflectance; retain mask, do not interpret as bare ground",
        "group_id": "Actual grouping used by this frozen split; keep whole in all partitions",
        "cluster_id": "Legacy cluster identifier copied into original split; group_id is authoritative",
        "fold": "Original immutable fold number 0–4",
        "partition": ("train (folds 2–4), validation (fold 1), historical restricted test (fold 0)" if roles == LEGACY_ROLES
                      else "cv (folds 1–4, cross-validated, pooled out-of-fold scores) or holdout (fold 0, held back)"),
        "repeat": "Zero for these spatial split families",
        "family": "s1_cc2km or s2_region; separate evaluation questions",
        "dataset": "zimbabwe, the provider/audit dataset key",
        "cohort": "zimbabwe_lacuna_2022_2023, the historical cohort identifier",
        "country_iso3": "ZWE",
        "country": "Provider country text",
        "location_source": "field_gps; accuracy undocumented",
        "source_crs": "OGC:CRS84; longitude then latitude in source geometry",
    }
    records = []
    for table_name, table in tables.items():
        for col in table.columns:
            if col in BANDS:
                meaning = f"Sentinel-2 {col.upper()} L2A surface reflectance, unitless; null when missing"
            elif col in INDICES or col in FEATURES:
                meaning = f"{col}: unitless vegetation index" + ("; statistic across observed months" if "season" in col else " from monthly reflectance")
            elif col.endswith("_raw"):
                meaning = "Unmodified provider text; audit metadata, excluded from model feature allowlist"
            else:
                require(col in descriptions, f"Data dictionary lacks {col}")
                meaning = descriptions[col]
            records.append({"table": table_name, "column": col, "dtype": str(table[col].dtype),
                            "null_count": int(table[col].isna().sum()), "meaning": meaning})
    csv_write(pd.DataFrame(records), path)


def publish_release(staged: Path, destination: Path) -> None:
    """Idempotent publication; any changed file requires a new release directory."""
    if destination.exists():
        old = {p.relative_to(destination).as_posix(): sha256(p) for p in destination.rglob("*") if p.is_file()}
        new = {p.relative_to(staged).as_posix(): sha256(p) for p in staged.rglob("*") if p.is_file()}
        require(old == new, "Existing release differs; use --output with a new directory. No files overwritten.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".handoff-stage-", dir=destination.parent) as tmp:
            sibling = Path(tmp) / "release"
            shutil.copytree(staged, sibling)
            sibling.rename(destination)


def build_handoff(output: Path = DEFAULT_OUTPUT, database: Path | None = None,
                  root: Path = ROOT, config_path: Path = CONFIG) -> dict:
    database = database or root / "data/cropyield.duckdb"
    config = json.loads(config_path.read_text())
    partition_order(config["fold_roles"])  # only the legacy or the team role scheme
    require(config["new_models_may_score_test"] is False, "Historical test restrictions cannot be removed by config")
    verify_inputs(root, database)
    before = input_hashes(root, database, config_path)
    raw, summary = read_raw(root / "data/raw/zimbabwe/Lacuna_Yield_data_geojson-2023.geojson")
    labels = reconcile_labels(raw, pd.read_parquet(root / "data/processed/labels_v1.parquet"))
    master, monthly, coverage, timing = database_tables(database, labels)
    primary = labels[labels.include_primary].copy()
    model = master[master.include_primary & master.months_with_data.ge(config["minimum_clear_months"])].copy()
    require(set(primary.obs_id) == set(model.obs_id), "Primary rows lost by imagery threshold; investigate before changing population")
    require(np.isfinite(model[FEATURES].to_numpy()).all(), "Invalid model feature; do not silently remove rows")
    model["yield_t_ha"] = model.yield_kg_ha / 1000
    model = model[["obs_id", "yield_t_ha", *FEATURES]].sort_values("obs_id").reset_index(drop=True)
    series = monthly[monthly.obs_id.isin(primary.obs_id)].reset_index(drop=True)
    splits, split_stats = {}, {}
    for family in ["s1_cc2km", "s2_region"]:
        source_split = pd.read_csv(root / f"data/splits/{COHORT}__{family}.csv", dtype={"fold": str, "group_id": str})
        splits[family], split_stats[family] = explicit_split(source_split, primary, config["fold_roles"], family)
    raw = raw.merge(labels[["obs_id", "exclusion_reason"]], on="obs_id", how="left", validate="one_to_one")
    raw["exclusion_reason"] = raw.exclusion_reason.fillna("failed_raw_screen")
    raw = raw.merge(master[["obs_id", "months_with_data", "postharvest_scenes", "preplanting_scenes"]],
                    on="obs_id", how="left", validate="one_to_one")
    groups = connected_clusters(primary.lat.to_numpy(), primary.lon.to_numpy(), 0.01)
    near = pd.Series(groups).map(pd.Series(groups).value_counts()).gt(1).to_numpy()
    raw["near_duplicate_primary"] = raw.obs_id.isin(primary.loc[near, "obs_id"])
    raw = raw.sort_values("source_row").reset_index(drop=True)
    summary.update(timing)
    summary.update({
        "raw_maize": len(raw), "cleaned_labels": len(labels), "primary_labels": len(primary), "model_rows": len(model),
        "screened_2022": int(labels.season_year.eq(2022).sum()), "screened_2023": int(labels.season_year.eq(2023).sum()),
        "unit_mismatch_rows": int(raw.yield_conversion_mismatch.sum()),
        "intercrop_exclusions": int(labels.exclusion_reason.eq("lacuna_intercropped").sum()),
        "irrigation_exclusions": int(labels.exclusion_reason.eq("lacuna_irrigated").sum()),
        "zero_yield_primary": int(primary.is_zero.sum()),
        "exact_coordinate_reuse_primary": int(primary.duplicated(["lat", "lon"], keep=False).sum()),
        "near_duplicate_primary": int(near.sum()), "outside_window_primary": int(primary.date_outside_window.sum()),
        "invalid_dates_raw": int(raw.invalid_date_order.sum()), "admin_units_primary": int(primary.admin_unit.nunique()),
        "splits": split_stats,
    })
    tables = {"cleaned_labels": labels, "row_audit": raw, "model_table": model, "monthly_features": series,
              **{f"split_{name}": table for name, table in splits.items()}}
    with tempfile.TemporaryDirectory(prefix="zimbabwe-handoff-") as tmp:
        staged = Path(tmp)
        for name, table in tables.items():
            csv_write(table, staged / f"{name}.csv")
            if not name.startswith("split_") and name != "row_audit":
                table.to_parquet(staged / f"{name}.parquet", index=False)
        csv_write(coverage, staged / "monthly_coverage.csv")
        label_summary = labels.groupby(["season_year", "include_primary"]).agg(
            records=("obs_id", "size"), zero_yields=("is_zero", "sum"),
            yield_min_kg_ha=("yield_kg_ha", "min"), yield_median_kg_ha=("yield_kg_ha", "median"),
            yield_mean_kg_ha=("yield_kg_ha", "mean"), yield_max_kg_ha=("yield_kg_ha", "max")).reset_index()
        csv_write(label_summary, staged / "label_summary.csv")
        quality = []
        for table_name, table, columns in [("model_table", model, FEATURES), ("monthly_features", series, BANDS + INDICES)]:
            for col in columns:
                values = table[col].to_numpy(dtype=float)
                finite = values[np.isfinite(values)]
                q = np.quantile(finite, [0, .01, .5, .99, 1]) if len(finite) else [np.nan] * 5
                quality.append(dict(table=table_name, feature=col, rows=len(values), finite=int(np.isfinite(values).sum()),
                                    missing=int(np.isnan(values).sum()), infinite=int(np.isinf(values).sum()),
                                    **dict(zip(["min", "p01", "median", "p99", "max"], q))))
        csv_write(pd.DataFrame(quality), staged / "feature_quality.csv")
        handbook = (root / "docs/ZIMBABWE_DATA_HANDOFF.md").read_text(encoding="utf-8")
        handbook = handbook.replace(f"../data/processed/{config['release']}/", "./")
        (staged / "README.md").write_text(handbook, encoding="utf-8")
        json_write(summary, staged / "audit_summary.json")
        write_report(staged / "audit_report.md", summary, config)
        write_dictionary(staged / "data_dictionary.csv", tables, config["fold_roles"])
        write_overview(staged / "data_overview.png", summary, primary, splits["s1_cc2km"], coverage)
        after = input_hashes(root, database, config_path)
        require(before == after, "An input changed while building; release not published")
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        manifest = {"config": config, "git_base_commit": commit, "inputs": before, "python": platform.python_version(),
                    "versions": {p: importlib.metadata.version(p) for p in ["pandas", "numpy", "pyarrow", "duckdb", "scipy", "matplotlib"]},
                    "outputs": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size}
                                for p in sorted(staged.iterdir()) if p.is_file()}}
        json_write(manifest, staged / "manifest.json")
        publish_release(staged, output)
    return summary


def load_handoff(output: Path = DEFAULT_OUTPUT, partition: str = "train", family: str = "s1_cc2km",
                 allow_historical_test: bool = False) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return allowlisted X, y (t/ha), groups in identical obs_id order.

    Test access is explicit because these fields have already been evaluated.
    The override is for reproducing permitted historical baselines, not new arms.
    """
    require(partition in {"train", "validation", "test", "cv", "holdout"}, "Unknown partition")
    require(family in {"s1_cc2km", "s2_region"}, "Unknown split family")
    require(partition not in RESTRICTED_PARTITIONS or allow_historical_test,
            "Fold 0 (test or holdout) is restricted; new arms must not score it")
    manifest = json.loads((output / "manifest.json").read_text())
    for name in ["model_table.parquet", f"split_{family}.csv"]:
        require(sha256(output / name) == manifest["outputs"][name]["sha256"], f"Release hash mismatch: {name}")
    model = pd.read_parquet(output / "model_table.parquet")
    split = pd.read_csv(output / f"split_{family}.csv", dtype={"group_id": str})
    rows = split[split.partition.eq(partition)].merge(model, on="obs_id", validate="one_to_one").set_index("obs_id").sort_index()
    require(len(rows) == split.partition.eq(partition).sum(), "Split/model join lost rows")
    return rows[FEATURES], rows["yield_t_ha"], rows["group_id"]
