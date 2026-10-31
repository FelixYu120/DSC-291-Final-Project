"""Build data/processed/labels_v1.parquet, the one table every model reads (docs/DATA.md).

    python scripts/labels/build_labels.py

Offline: reads data/audit and data/raw. Stops with a non-zero exit code when a check fails and
writes nothing in that case. Prints the SHA-256 for the line in docs/DECISIONS.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.labels import (LABELS_PATH, build_labels, check_against_raw, check_labels,  # noqa: E402
                                   lacuna_groups, oaf_groups, sha256)


def main() -> int:
    oaf, lacuna = oaf_groups(), lacuna_groups()  # the OAF workbook takes about a minute
    labels = build_labels(oaf, lacuna)
    problems = check_labels(labels) + check_against_raw(labels, oaf, lacuna)
    if problems:
        print("labels_v1 NOT written:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(LABELS_PATH, index=False)
    summary = labels.groupby(["role", "cohort", "season_year"], sort=False).agg(
        rows=("obs_id", "size"), included=("include_primary", "sum"),
        median_kg_ha=("yield_kg_ha", "median"), zeros=("is_zero", "sum"))
    print(summary.to_string())
    print(labels.loc[~labels["include_primary"], "exclusion_reason"].value_counts().to_string())
    print(f"{LABELS_PATH.relative_to(ROOT)}  sha256 {sha256(LABELS_PATH)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
