"""Reconcile and export the Zimbabwe midterm package without rewriting team data.

    python scripts/step8_build_zimbabwe_handoff.py
    python scripts/step8_build_zimbabwe_handoff.py --output /tmp/zimbabwe-rebuild
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.handoff import DEFAULT_OUTPUT, build_handoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--database", type=Path, default=ROOT / "data/cropyield.duckdb")
    args = parser.parse_args()
    try:
        result = build_handoff(args.output.resolve(), args.database.resolve())
    except (ValueError, OSError) as exc:
        print(f"Zimbabwe release not written: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {result['raw_maize']:,} raw maize rows → {result['cleaned_labels']:,} cleaned labels "
          f"→ {result['model_rows']:,} model rows")
    print(f"Primary partitions: {result['splits']['s1_cc2km']['rows']}")
    print(f"Historical test remains restricted; {result['postharvest_fields']:,} fields have post-harvest imagery.")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
