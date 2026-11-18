"""Download/cache NASA POWER weather, then enrich the complete Zimbabwe label catalog.

    python scripts/step11_add_zimbabwe_weather.py                                        # v1
    python scripts/step11_add_zimbabwe_weather.py --config configs/zimbabwe_weather_v2.json

The config names the merge release whose catalog is enriched ("merge_run") and the output
("weather_release"); both default to v1. The committed NASA POWER cache is reused offline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cropyield.data.weather import CONFIG, build_weather, download_weather, release_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only",action="store_true")
    parser.add_argument("--allow-download",action="store_true")
    parser.add_argument("--config",type=Path,default=CONFIG)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.download_only:
        download_weather(config)
    else:
        output = args.output or release_path(config)
        build_weather(output.resolve(),args.config.resolve(),offline=not args.allow_download)
    return 0


if __name__ == "__main__":
    sys.exit(main())
