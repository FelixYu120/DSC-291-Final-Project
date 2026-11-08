"""Reconcile and export the Zimbabwe midterm package without rewriting team data.

    python scripts/step8_build_zimbabwe_handoff.py
    python scripts/step8_build_zimbabwe_handoff.py --output /tmp/zimbabwe-rebuild
    python scripts/step8_build_zimbabwe_handoff.py --config configs/zimbabwe_midterm_v1.json   # legacy fold roles

The default config is release v2: folds 1-4 are cross-validated (partition "cv") and fold 0 is held back
(partition "holdout"), the team protocol of docs/EVALUATION.md. Release v1 labelled fold 1 "validation" and
folds 2-4 "train"; it stays published unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.handoff import TEAM_CONFIG, build_handoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=TEAM_CONFIG)
    parser.add_argument("--output", type=Path, default=None, help="default: data/processed/<release of the config>")
    parser.add_argument("--database", type=Path, default=ROOT / "data/cropyield.duckdb")
    args = parser.parse_args()
    config_path = args.config.resolve()
    output = args.output or ROOT / "data/processed" / json.loads(config_path.read_text())["release"]
    try:
        result = build_handoff(output.resolve(), args.database.resolve(), config_path=config_path)
    except (ValueError, OSError) as exc:
        print(f"Zimbabwe release not written: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {result['raw_maize']:,} raw maize rows -> {result['cleaned_labels']:,} cleaned labels "
          f"-> {result['model_rows']:,} model rows")
    print(f"Primary partitions: {result['splits']['s1_cc2km']['rows']}")
    print(f"Fold 0 remains restricted; {result['postharvest_fields']:,} fields have post-harvest imagery.")
    print(output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
