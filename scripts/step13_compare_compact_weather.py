"""Run the fixed 2/4-feature weather ablation using unchanged Zimbabwe spatial splits.

    python scripts/step13_compare_compact_weather.py                                                # v1
    python scripts/step13_compare_compact_weather.py --config configs/zimbabwe_weather_compact_v2.json

The default output is data/runs/<experiment> from the config.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cropyield.experiments.zimbabwe_merge import default_output
from cropyield.experiments.zimbabwe_weather_compact import CONFIG, run_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=CONFIG)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    output = args.output or default_output(json.loads(args.config.read_text()))
    run_experiment(output.resolve(),args.config.resolve())


if __name__=="__main__":
    main()
