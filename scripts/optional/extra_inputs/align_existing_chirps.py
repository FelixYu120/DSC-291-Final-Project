"""Align the previously downloaded CHIRPS v2 monthly data to the canonical keys.

This script does not download or modify the source data.  It checks that every
Zimbabwe observation-month has exactly one CHIRPS value and writes a compact,
model-ready table plus a machine-readable audit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--chirps", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    keys = pd.read_csv(args.keys, dtype={"obs_id": "string", "month": "string"})
    source = pd.read_csv(
        args.chirps, dtype={"obs_id": "string", "month": "string"}
    ).rename(columns={"year": "season_year", "precip": "chirps_precip_mm"})
    # The older notebook serialized months as YYYY-MM-01; canonical project
    # keys use YYYY-MM.  Both refer to the same monthly interval.
    source["month"] = source["month"].str.slice(0, 7)

    required = {"obs_id", "season_year", "month", "chirps_precip_mm"}
    missing = required.difference(source.columns)
    if missing:
        raise ValueError(f"CHIRPS source lacks columns: {sorted(missing)}")

    join_cols = ["obs_id", "season_year", "month"]
    if source.duplicated(join_cols).any():
        raise ValueError("CHIRPS source contains duplicate observation-month keys")

    keep = join_cols + [
        "chirps_precip_mm",
        "chirps_lat",
        "chirps_lon",
    ]
    aligned = keys[join_cols].merge(
        source[keep], on=join_cols, how="left", validate="one_to_one"
    )
    aligned["chirps_available"] = aligned["chirps_precip_mm"].notna()

    out_dir = args.output_dir
    (out_dir / "derived").mkdir(parents=True, exist_ok=True)
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    output = out_dir / "derived" / "chirps_monthly.csv"
    aligned.to_csv(output, index=False)

    audit = {
        "source": str(args.chirps.resolve()),
        "product": "CHIRPS v2 monthly precipitation",
        "expected_rows": int(len(keys)),
        "output_rows": int(len(aligned)),
        "complete_rows": int(aligned["chirps_available"].sum()),
        "missing_rows": int((~aligned["chirps_available"]).sum()),
        "observations": int(aligned["obs_id"].nunique()),
        "months_per_observation_min": int(aligned.groupby("obs_id").size().min()),
        "months_per_observation_max": int(aligned.groupby("obs_id").size().max()),
        "unique_chirps_cells": int(
            aligned[["chirps_lat", "chirps_lon"]].drop_duplicates().shape[0]
        ),
    }
    (out_dir / "reports" / "chirps_summary.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
