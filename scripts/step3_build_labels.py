"""Build the labels table every model reads (docs/DATA.md): labels_v1, or labels_v2 with --version 2.

    python scripts/step3_build_labels.py               # data/processed/labels_v1.parquet (frozen)
    python scripts/step3_build_labels.py --version 2   # data/v2/processed/labels_v2.parquet

Offline: reads data/audit, data/v2/audit (v2: Malawi 2022 only) and data/raw. Stops with a non-zero exit code
when a check fails and writes nothing in that case. A file that exists is frozen: the script never changes it
and only confirms when the rebuild gives the same bytes. Version 2 also checks that every row outside Malawi 2022
equals labels_v1. Prints the SHA-256 for the line in docs/DECISIONS.md.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.labels import (LABELS_PATH, LABELS_V2_PATH, build_labels, check_against_raw,  # noqa: E402
                                   check_labels, lacuna_groups, oaf_groups, sha256)

# What a Malawi 2022 row may change in v2: its inclusion, and what follows from the EPSG:1113 polygons.
MALAWI_2022_V2_COLUMNS = {"role", "include_primary", "exclusion_reason", "geometry_wkt", "lat", "lon", "source_crs",
                          "source_sha256", "cluster_2km", "near_dup_10m", "polygon_overlap_dup"}


def parquet_bytes(labels: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    labels.to_parquet(buffer, index=False)
    return buffer.getvalue()


def v2_differences(v2: pd.DataFrame, v1: pd.DataFrame) -> list[str]:
    """Where v2 differs from v1 although it must not: any column outside Malawi 2022, other columns inside it."""
    if not v2["obs_id"].equals(v1["obs_id"]):
        return ["v2 does not hold the rows of v1 in the same order"]
    malawi_2022 = v2["cohort"] == "malawi_2022"
    problems = []
    for column in v1.columns:
        a, b = v2[column], v1[column]
        changed = ~((a == b).fillna(False).astype(bool) | (a.isna() & b.isna()))
        if (changed & ~malawi_2022).any():
            problems.append(f"{column}: differs from labels_v1 outside Malawi 2022 ({int((changed & ~malawi_2022).sum())} rows)")
        if (changed & malawi_2022).any() and column not in MALAWI_2022_V2_COLUMNS:
            problems.append(f"{column}: differs from labels_v1 in Malawi 2022")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    path = LABELS_V2_PATH if args.version == 2 else LABELS_PATH
    oaf, lacuna = oaf_groups(), lacuna_groups()  # the OAF workbook takes about a minute
    labels = build_labels(oaf, lacuna, args.version)
    problems = check_labels(labels) + check_against_raw(labels, oaf, lacuna)
    new = parquet_bytes(labels)
    if args.version == 2:  # compare as written to disk, so None and NaN read back alike
        problems += v2_differences(pd.read_parquet(io.BytesIO(new)), pd.read_parquet(LABELS_PATH))
    if problems:
        print(f"{path.name} NOT written:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    if path.exists():
        if sha256(path) != hashlib.sha256(new).hexdigest():
            print(f"{path.relative_to(ROOT)} exists and the rebuild differs. It is frozen; stop here.", file=sys.stderr)
            return 1
        print(f"{path.relative_to(ROOT)} unchanged: the rebuild gives the same bytes")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new)
    summary = labels.groupby(["role", "cohort", "season_year"], sort=False).agg(
        rows=("obs_id", "size"), included=("include_primary", "sum"),
        median_kg_ha=("yield_kg_ha", "median"), zeros=("is_zero", "sum"))
    print(summary.to_string())
    print(labels.loc[~labels["include_primary"], "exclusion_reason"].value_counts().to_string())
    print(f"{path.relative_to(ROOT)}  sha256 {sha256(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
