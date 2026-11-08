"""Build harmonized Zimbabwe data and compare Lacuna-only vs merged training.

    python scripts/step9_compare_zimbabwe_merge.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_merge import CONFIG, OUTPUT, run_experiment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    try:
        run_experiment(args.output.resolve(), args.config.resolve())
    except (ValueError, OSError) as exc:
        print(f"Comparison not published: {exc}", file=sys.stderr)
        return 1
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
