"""Audit all Zimbabwe years and compare imagery-eligible training pools on frozen targets."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_multiyear import CONFIG, OUTPUT, run_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    run_experiment(args.output.resolve(), args.config.resolve())


if __name__ == "__main__":
    main()
