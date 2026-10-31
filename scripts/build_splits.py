"""Write the frozen split files data/splits/<cohort>__<family>.csv and manifest.json (docs/EVALUATION.md).

    python scripts/build_splits.py

Run once, from labels_v1, before any model is trained. Rows are the labels_v1 rows with
include_primary, with or without imagery, so a split never changes when coverage changes. The
script refuses to overwrite existing split files unless they would come out byte-identical.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.labels import LABELS_PATH, sha256  # noqa: E402
from cropyield.eval.splits import (FOLDS, SEED, check_split, new_region, new_season, new_village,  # noqa: E402
                                   random_diagnostic)

SPLITS_DIR = ROOT / "data" / "splits"
# cohort -> region unit of s2_region: a labels_v1 column, a cluster distance in km, or k-means blocks.
REGION_UNITS = {"malawi_2023": 5.0, "kenya_oaf_2019_2020": "admin_unit",
                "zimbabwe_lacuna_2022_2023": "admin_unit", "zimbabwe_2024": "kmeans20"}
TEMPORAL = {"kenya_oaf_2019_2020": (2019, 2020)}


def cohort_splits(rows: pd.DataFrame, cohort: str) -> list[pd.DataFrame]:
    splits = [new_village(rows), new_region(rows, REGION_UNITS[cohort]), random_diagnostic(rows)]
    if cohort in TEMPORAL:
        splits.append(new_season(rows, *TEMPORAL[cohort]))
    return splits


def git_commit() -> str:
    run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return run.stdout.strip() or "unknown"


def main() -> int:
    labels = pd.read_parquet(LABELS_PATH)
    manifest = {"seed": SEED, "folds": FOLDS, "generator_commit": git_commit(), "labels_sha256": sha256(LABELS_PATH),
                "region_units": REGION_UNITS, "temporal": TEMPORAL, "files": {}}
    written = []
    for cohort in REGION_UNITS:
        rows = labels[(labels["cohort"] == cohort) & labels["include_primary"]].reset_index(drop=True)
        for split in cohort_splits(rows, cohort):
            problems = check_split(split, rows)
            if problems:
                print("\n".join(problems), file=sys.stderr)
                return 1
            family = split["family"].iloc[0]
            path = SPLITS_DIR / f"{cohort}__{family}.csv"
            text = split.to_csv(index=False, lineterminator="\n")
            if path.exists() and path.read_text(encoding="utf-8") != text:
                print(f"{path.name} exists and would change. Splits are frozen; stop here.", file=sys.stderr)
                return 1
            written.append((path, text))
            sizes = split[split["repeat"] == 0].groupby("fold").size()
            print(f"{cohort:<28} {family:<12} rows {len(rows):>5}  groups {split['group_id'].nunique():>4}  "
                  f"fold sizes {sizes.tolist()}")
    for path, text in written:
        path.write_text(text, encoding="utf-8", newline="\n")
        manifest["files"][path.name] = {"sha256": sha256(path), "rows": text.count("\n") - 1}
    (SPLITS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(written)} files in {SPLITS_DIR.relative_to(ROOT)}, labels sha256 {manifest['labels_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
