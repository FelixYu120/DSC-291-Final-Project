"""Diagnose data quality, domain shift and model limits in Zimbabwe transfer.

    python scripts/step10_diagnose_zimbabwe_transfer.py                                                  # v1
    python scripts/step10_diagnose_zimbabwe_transfer.py --config configs/zimbabwe_transfer_diagnosis_v2.json

The default output is data/runs/<experiment> from the config.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.experiments.zimbabwe_diagnosis import CONFIG, run_diagnosis
from cropyield.experiments.zimbabwe_merge import default_output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    if args.output is None:
        args.output = default_output(json.loads(args.config.read_text()))
    try:
        run_diagnosis(args.output.resolve(), args.config.resolve())
    except (ValueError, OSError) as exc:
        print(f"Diagnosis not published: {exc}", file=sys.stderr)
        return 1
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
