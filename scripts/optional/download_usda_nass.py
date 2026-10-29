"""Download USDA NASS Quick Stats county-level corn yield estimates.

The API key is read only from USDA_NASS_API_KEY and is never written to disk.
See data/raw/USA/USDA_NASS/README.md for scope and interpretation.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
API = "https://quickstats.nass.usda.gov/api"
DEFAULT_OUTPUT_DIR = ROOT / "data/raw/USA/USDA_NASS/county_yield"


def get_json(endpoint: str, params: dict[str, str]) -> dict:
    url = f"{API}/{endpoint}/?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "DSC-291-maize-yield-research/1.0"})
    try:
        with urlopen(request, timeout=90) as response:
            payload = response.read().decode("utf-8-sig")
    except HTTPError as error:
        raise RuntimeError(f"USDA NASS API returned HTTP {error.code}: {error.reason}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach the USDA NASS API: {error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError("USDA NASS API request timed out") from error
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"USDA NASS returned a non-JSON response: {payload[:300]}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"Unexpected USDA NASS response: {str(value)[:300]}")
    if "error" in value:
        raise RuntimeError(f"USDA NASS API error: {value['error']}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2024,
                        help="default matches the currently listed AlphaEarth annual years")
    parser.add_argument("--output", type=Path, default=None,
                        help="CSV destination (default name includes the requested years)")
    args = parser.parse_args()
    if args.start_year < 1866 or args.end_year < args.start_year:
        parser.error("Provide an ordered year range (start year must be at least 1866)")
    output_path = args.output or DEFAULT_OUTPUT_DIR / f"corn_county_yield_{args.start_year}-{args.end_year}.csv"
    api_key = os.environ.get("USDA_NASS_API_KEY", "").strip()
    if not api_key:
        print("Set USDA_NASS_API_KEY in your shell. Request a free API key from the USDA NASS Quick Stats API page.", file=sys.stderr)
        return 2

    filters = {
        "sector_desc": "CROPS",
        "commodity_desc": "CORN",
        "statisticcat_desc": "YIELD",
        "agg_level_desc": "COUNTY",
        "freq_desc": "ANNUAL",
        "year__GE": str(args.start_year),
        "year__LE": str(args.end_year),
    }
    count_response = get_json("get_counts", {"key": api_key, **filters})
    try:
        count = int(count_response["count"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"Unexpected response from USDA NASS count endpoint: {count_response}") from error
    if count > 50_000:
        raise RuntimeError(f"The query matches {count:,} rows, above the API's 50,000-row limit. Narrow the years or filters.")
    if count == 0:
        print("The query returned no USDA NASS rows; no output was written.", file=sys.stderr)
        return 1

    response = get_json("api_GET", {"key": api_key, **filters, "format": "JSON"})
    records = response.get("data")
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"Unexpected or empty USDA NASS data response: {str(response)[:500]}")
    fieldnames = list(dict.fromkeys(k for record in records for k in record))
    if "county_fips" not in fieldnames:
        fieldnames.append("county_fips")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            state, county = str(record.get("state_ansi", "")).strip(), str(record.get("county_ansi", "")).strip()
            fips = f"{state.zfill(2)}{county.zfill(3)}" if state.isdigit() and county.isdigit() and county else ""
            writer.writerow({**record, "county_fips": fips})

    provenance = {
        "source": "USDA National Agricultural Statistics Service Quick Stats API",
        "api_endpoint": f"{API}/api_GET/",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "query_parameters_without_secret": filters,
        "count_endpoint_reported_rows": count,
        "downloaded_rows": len(records),
        "output_file": output_path.name,
        "api_key_saved": False,
        "interpretation": "County-level published estimates, not field-level yield labels or field locations.",
    }
    output_path.with_name("query_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
