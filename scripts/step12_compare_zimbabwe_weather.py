"""Compare Lacuna-only and merged models with NASA POWER weather on unchanged splits."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cropyield.experiments.zimbabwe_weather import OUTPUT, run_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args = parser.parse_args()
    run_experiment(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
