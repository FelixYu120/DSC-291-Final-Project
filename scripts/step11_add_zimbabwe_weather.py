"""Download/cache NASA POWER weather, then enrich the complete Zimbabwe label catalog."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cropyield.data.weather import CONFIG, OUTPUT, build_weather, download_weather


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only",action="store_true")
    parser.add_argument("--allow-download",action="store_true")
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args = parser.parse_args()
    if args.download_only:
        download_weather(json.loads(CONFIG.read_text()))
    else:
        build_weather(args.output.resolve(),offline=not args.allow_download)
    return 0


if __name__ == "__main__":
    sys.exit(main())
