"""Fetch a bounded same-year FTW pilot for Malawi polygons and repeated Kenya GPS points."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.boundary_candidates import run_boundary_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/runs/boundary_review")
    parser.add_argument("--per-cohort-limit", type=int, default=2, help="Rows per country/year; 0 reviews all 463 rows")
    parser.add_argument("--max-seconds", type=float, default=180)
    args = parser.parse_args()
    if args.per_cohort_limit < 0 or args.max_seconds <= 0:
        parser.error("limit must be nonnegative and time budget positive")
    output = run_boundary_review(args.output_root, args.per_cohort_limit or None, args.max_seconds)
    print(output)
    print((output / "summary.json").read_text())


if __name__ == "__main__":
    main()
