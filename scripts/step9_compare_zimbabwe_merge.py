"""Build harmonized Zimbabwe data and compare Lacuna-only vs merged training.

    python scripts/step9_compare_zimbabwe_merge.py                                    # v1 (legacy pool)
    python scripts/step9_compare_zimbabwe_merge.py --config configs/zimbabwe_merge_v2.json   # team rule

The default output is data/runs/<experiment> from the config.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_merge import CONFIG, default_output, run_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    if args.output is None:
        args.output = default_output(json.loads(args.config.read_text()))
    try:
        run_experiment(args.output.resolve(), args.config.resolve())
    except (ValueError, OSError) as exc:
        print(f"Comparison not published: {exc}", file=sys.stderr)
        return 1
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
