"""Pixel-based SCL cloud review, with original database/labels/splits preserved.

    python scripts/review_clouds.py plan
    python scripts/review_clouds.py review --scope all-retained --workers 8

Downloads only public scene metadata and SCL image windows. The conservative
derivative drops whole field-months when any touched field pixel fails; it does
not reconstruct within-field reflectance medians or update pretrained embeddings.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.satellite.cloud_review import (CORE, derived_tables, load_inputs, policy, run_reviews, sha256)  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["plan", "review"])
    parser.add_argument("--scope", choices=["all-retained", "core"], default="all-retained")
    parser.add_argument("--db", type=Path, default=ROOT / "data/cropyield.duckdb")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/runs/cloud_review/cache")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--buffer-metres", type=float, default=60)
    parser.add_argument("--max-scenes", type=int, help="Explicit pilot limit; unreviewed months remain unverified")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 16 or (args.max_scenes is not None and args.max_scenes < 1):
        parser.error("workers must be 1–16 and max-scenes positive")
    mask_policy = policy(args.buffer_metres)
    labels_path = ROOT / "data/processed/labels_v1.parquet"
    selected, scenes, monthly = load_inputs(args.db, labels_path, args.scope)
    plan = {"scope": args.scope, "fields": len(selected), "accepted_field_months": len(scenes),
            "unique_scenes": int(scenes.item_id.nunique()), "monthly_rows_including_missing": len(monthly),
            "policy": mask_policy}
    print(json.dumps(plan, indent=2), flush=True)
    if args.command == "plan":
        return 0
    spec = json.loads((ROOT / "configs/team_database_v1.json").read_text())
    split_manifest = json.loads((ROOT / "data/splits/manifest.json").read_text())
    protected = [args.db, labels_path, ROOT / "configs/sentinel2_scenes_v1.parquet",
                 ROOT / "configs/team_database_v1.json", ROOT / "data/splits/manifest.json"]
    protected += [ROOT / "data/splits" / name for name in split_manifest["files"]]
    before = {str(p.resolve()): sha256(p) for p in protected}
    if before[str(args.db.resolve())] != spec["sha256"] or args.db.stat().st_size != spec["bytes"]:
        raise ValueError("Use the immutable shared database specified in team_database_v1.json")
    if before[str(labels_path.resolve())] != split_manifest["labels_sha256"]:
        raise ValueError("Frozen labels differ from split manifest")
    frozen = pd.read_parquet(ROOT / "configs/sentinel2_scenes_v1.parquet")
    expected = frozen[frozen.obs_id.isin(selected.obs_id)][["obs_id", "month", "item_id"]]
    actual = scenes[["obs_id", "month", "item_id"]]
    keys = ["obs_id", "month", "item_id"]
    if not actual.sort_values(keys).reset_index(drop=True).equals(expected.sort_values(keys).reset_index(drop=True)):
        raise ValueError("Scene selection differs from frozen scene list")
    output = args.output or ROOT / "data/runs/cloud_review" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    if args.max_scenes:
        chosen = sorted(scenes.item_id.unique())[:args.max_scenes]
        review_scenes = scenes[scenes.item_id.isin(chosen)]
    else:
        review_scenes = scenes
    reviews, errors = run_reviews(review_scenes, args.cache.resolve(), mask_policy, args.workers)
    clean, indices, season, fields = derived_tables(monthly, reviews, selected)
    summary = fields.groupby(["country_iso3", "cohort", "include_primary"]).agg(
        fields=("obs_id", "size"), original_months=("original_months_with_data", "sum"),
        retained_months=("retained_months", "sum"), fields_with_four_retained_months=("retains_four_months", "sum")).reset_index()
    after = {str(p.resolve()): sha256(p) for p in protected}
    if before != after:
        raise ValueError("Protected source inputs changed during cloud review")
    output.mkdir(parents=True)
    reviews.to_parquet(output / "cloud_review.parquet", index=False)
    clean.to_parquet(output / "cleaned_monthly_bands.parquet", index=False)
    indices.to_parquet(output / "clean_monthly_indices.parquet", index=False)
    season.to_parquet(output / "clean_season_indices.parquet", index=False)
    fields.to_parquet(output / "field_coverage.parquet", index=False)
    summary.to_csv(output / "coverage_by_cohort.csv", index=False)
    for (country, cohort), part in fields.groupby(["country_iso3", "cohort"]):
        folder = output / country / cohort
        folder.mkdir(parents=True)
        ids = set(part.obs_id)
        clean[clean.obs_id.isin(ids)].to_parquet(folder / "cleaned_monthly_bands.parquet", index=False)
        season[season.obs_id.isin(ids)].to_parquet(folder / "clean_season_indices.parquet", index=False)
        part.to_parquet(folder / "field_coverage.parquet", index=False)
        reviews[reviews.obs_id.isin(ids)].to_parquet(folder / "cloud_review.parquet", index=False)
    metadata = {**plan, "created_at": datetime.now(UTC).isoformat(),
                "attempted_scope_complete": len(reviews) == len(scenes),
                "scope_complete": len(reviews) == len(scenes) and not errors,
                "reviewed_field_months": len(reviews), "verified_field_months": int(reviews.assessment.eq("verified_scl").sum()),
                "kept_field_months": int(reviews.keep_whole_month.sum()),
                "unverified_field_months": int(reviews.assessment.ne("verified_scl").sum()),
                "unreviewed_field_months": len(scenes) - len(reviews), "failed_scenes": errors,
                "core_accepted_field_months": int((scenes.cohort.isin(CORE) & scenes.include_primary).sum()),
                "source_inputs_unchanged": before == after, "input_sha256": before,
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source_code_sha256": {name: sha256(ROOT / name) for name in
                    ["src/cropyield/satellite/cloud_review.py", "scripts/review_clouds.py"]},
                "output_sha256": {str(p.relative_to(output)): sha256(p) for p in output.rglob("*") if p.is_file()},
                "limitations": ["SCL can miss thin clouds or misclassify land; passing is not proof of cloud-free pixels.",
                                "Native 20m SCL is nearest-neighbor sampled on the original 10m grid; no resolution is gained.",
                                "60m default buffer is a conservative project choice, not a validated universal threshold.",
                                "Whole monthly aggregates are retained or nulled; partly masked pixel medians were not recomputed.",
                                "Original MOSAIKS and Presto embeddings were not refreshed and are not clean-cloud derivatives.",
                                "No new scenes or missing-month values were filled; no models trained or scored.",
                                "GDAL uses COG block requests; exact network bytes are not measured."]}
    (output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(summary.to_string(index=False), flush=True)
    print(f"Cloud review: {output}; failed scenes: {len(errors)}; source inputs unchanged.", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
