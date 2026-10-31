"""Write the week-0 pilot selection as a downloader window file.

Rule (docs/DECISIONS.md, 28 Oct 2026): for each cohort, the first rows of its screened audit
file in file order, split evenly over the cohort's harvest years. Sizes follow the week-0
pilot in docs/ROADMAP.md: 12 Malawi 2023, 12 Kenya OAF, 16 Zimbabwe 2024, 8 Zimbabwe Lacuna.
Each row carries its cohort's fixed season window, so the file feeds
``download_sentinel2.py download --date-overrides <file> --only-listed`` directly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.cohorts import date_overrides, load_cohort  # noqa: E402

PILOT_SIZES = {"malawi_2023": 12, "kenya_oaf_2019_2020": 12, "zimbabwe_2024": 16, "zimbabwe_lacuna_2022_2023": 8}
PILOT_PATH = ROOT / "configs" / "sentinel2_windows_pilot48.csv"


def pilot_rows(sizes: dict[str, int] = PILOT_SIZES) -> pd.DataFrame:
    """Cohort rows of the pilot: per cohort and harvest year, the first rows in audit-file order."""
    parts = []
    for name, size in sizes.items():
        cohort = load_cohort(name)
        years = sorted(cohort["year"].unique())
        if size % len(years):
            raise ValueError(f"{name}: {size} records do not split evenly over the years {years}")
        for year in years:
            rows = cohort[cohort["year"] == year].head(size // len(years))
            if len(rows) < size // len(years):
                raise ValueError(f"{name} {year}: only {len(rows)} rows")
            parts.append(rows)
    return pd.concat(parts, ignore_index=True)


def window_table(rows: pd.DataFrame) -> pd.DataFrame:
    """Window-file rows for the downloader: cohort, dataset, source_id and the fixed season window."""
    table = date_overrides(rows)
    table.insert(0, "cohort", rows["cohort"].to_numpy())
    return table


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PILOT_PATH)
    args = parser.parse_args(argv)
    rows = pilot_rows()
    table = window_table(rows)
    table.to_csv(args.out, index=False, lineterminator="\n")
    print(rows.groupby(["cohort", "year"]).size().to_string())
    print(f"{len(table)} records -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
