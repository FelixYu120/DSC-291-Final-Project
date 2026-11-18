"""Audit all Zimbabwe years and compare imagery-eligible training pools on frozen targets."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_multiyear import CONFIG, run_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG,
                        help="Default: the team-rule v2 config; pass the v1 config to replay v1")
    parser.add_argument("--output", type=Path, help="Default: data/runs/<config experiment>; must be new or identical")
    args = parser.parse_args()
    run_experiment(args.output.resolve() if args.output else None, args.config.resolve())


if __name__ == "__main__":
    main()
