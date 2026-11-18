"""Write the frozen split files <cohort>__<family>.csv and manifest.json (docs/EVALUATION.md).

    python scripts/step4_build_splits.py               # data/splits/ from labels_v1 (frozen)
    python scripts/step4_build_splits.py --version 2   # data/v2/splits/ from labels_v2

Run once, before any model is trained. Rows are the include_primary rows, with or without imagery, so a split
never changes when coverage changes. Existing files are frozen: the script never changes a split file or the
manifest, and stops if a rebuild would differ. Version 2 rebuilds every v1 file, checks it equals the file in
data/splits/ byte for byte, and adds Malawi 2022 and the Malawi 2022 <-> 2023 rank-only season split.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.labels import LABELS_PATH, LABELS_V2_PATH, V2_DIR, sha256  # noqa: E402
from cropyield.eval.splits import (FOLDS, SEED, check_split, new_region, new_season, new_village,  # noqa: E402
                                   random_diagnostic, temporal_rank)

SPLITS_DIR = ROOT / "data" / "splits"
SPLITS_V2_DIR = V2_DIR / "splits"
# cohort -> region unit of s2_region: a labels column, a cluster distance in km, or k-means blocks.
REGION_UNITS = {"malawi_2023": 5.0, "kenya_oaf_2019_2020": "admin_unit",
                "zimbabwe_lacuna_2022_2023": "admin_unit", "zimbabwe_2024": "kmeans20"}
# Malawi 2022 has no district column, so its region test uses 20 k-means blocks, like Zimbabwe 2024.
REGION_UNITS_V2 = {**REGION_UNITS, "malawi_2022": "kmeans20"}
TEMPORAL = {"kenya_oaf_2019_2020": (2019, 2020)}
TEMPORAL_RANK_V2 = {"malawi_2022_2023": ("malawi_2022", "malawi_2023")}


def cohort_splits(rows: pd.DataFrame, cohort: str, units: dict = REGION_UNITS) -> list[pd.DataFrame]:
    splits = [new_village(rows), new_region(rows, units[cohort]), random_diagnostic(rows)]
    if cohort in TEMPORAL:
        splits.append(new_season(rows, *TEMPORAL[cohort]))
    return splits


def shown(path: Path) -> str:
    """A path for messages: relative to the repository when it is inside it."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def git_commit() -> str:
    run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return run.stdout.strip() or "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    v2 = args.version == 2
    labels_path, out_dir, units = (LABELS_V2_PATH, SPLITS_V2_DIR, REGION_UNITS_V2) if v2 else (LABELS_PATH, SPLITS_DIR, REGION_UNITS)
    labels = pd.read_parquet(labels_path)
    primary = labels[labels["include_primary"]]

    def rows_of(cohort: str) -> pd.DataFrame:
        return primary[primary["cohort"] == cohort].reset_index(drop=True)

    tables = [(cohort, rows_of(cohort), split) for cohort in units for split in cohort_splits(rows_of(cohort), cohort, units)]
    if v2:
        for name, (first, second) in TEMPORAL_RANK_V2.items():
            split = temporal_rank(rows_of(first), rows_of(second))
            tables.append((name, primary.set_index("obs_id").loc[split["obs_id"].unique()].reset_index(), split))
    written, same_as_v1 = [], {}
    for cohort, rows, split in tables:
        problems = check_split(split, rows)
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        family = split["family"].iloc[0]
        path = out_dir / f"{cohort}__{family}.csv"
        text = split.to_csv(index=False, lineterminator="\n")
        if path.exists() and path.read_bytes() != text.encode("utf-8"):
            print(f"{path.name} exists and would change. Splits are frozen; stop here.", file=sys.stderr)
            return 1
        v1_file = SPLITS_DIR / path.name
        if v2 and v1_file.exists():
            if v1_file.read_bytes() != text.encode("utf-8"):
                print(f"{path.name}: the v2 rebuild differs from data/splits/. v1 cohorts must not change; stop here.",
                      file=sys.stderr)
                return 1
            same_as_v1[path.name] = True
        written.append((path, text))
        sizes = split[split["repeat"] == 0].groupby("fold").size()
        print(f"{cohort:<28} {family:<14} rows {split['obs_id'].nunique():>5}  groups {split['group_id'].nunique():>4}  "
              f"fold sizes {sizes.tolist()}")
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded = frozen["files"]
        if (frozen["labels_sha256"] == sha256(labels_path) and len(recorded) == len(written)
                and all(path.exists() and recorded.get(path.name, {}).get("sha256") == sha256(path) for path, _ in written)):
            print(f"{shown(out_dir)} unchanged: every file and the manifest stay as they are")
            return 0
        print(f"{shown(manifest_path)} exists and would change. Splits are frozen; stop here.", file=sys.stderr)
        return 1
    manifest = {"seed": SEED, "folds": FOLDS, "generator_commit": git_commit(), "labels_sha256": sha256(labels_path),
                "region_units": units, "temporal": TEMPORAL, "files": {}}
    if v2:
        manifest.update(temporal_rank=TEMPORAL_RANK_V2, v1_manifest_sha256=sha256(SPLITS_DIR / "manifest.json"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, text in written:
        path.write_text(text, encoding="utf-8", newline="\n")
        manifest["files"][path.name] = {"sha256": sha256(path), "rows": text.count("\n") - 1,
                                        **({"same_as_v1": same_as_v1.get(path.name, False)} if v2 else {})}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(written)} files in {shown(out_dir)}, labels sha256 {manifest['labels_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
