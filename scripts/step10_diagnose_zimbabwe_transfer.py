"""Diagnose data quality, domain shift and model limits in Zimbabwe transfer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_diagnosis import CONFIG, OUTPUT, run_diagnosis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    try:
        run_diagnosis(args.output.resolve(), args.config.resolve())
    except (ValueError, OSError) as exc:
        print(f"Diagnosis not published: {exc}", file=sys.stderr)
        return 1
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
