"""Download the original OAF, Zimbabwe and Malawi public data, without editing it.

Run with Python 3. Uses the standard library only. Existing downloads are reused
after size/hash checks. Provider metadata and download checksums are preserved.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
META = ROOT / "data" / "metadata"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "DSC190-academic-data-audit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def metadata(name: str, url: str) -> dict:
    path = META / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        raw = fetch(url)
        json.loads(raw)
        path.write_bytes(raw)
    return json.loads(path.read_text())


def save(group: str, name: str, url: str, expected_size=None, md5=None) -> dict:
    path = RAW / group / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print(f"Downloading {group}/{name}", flush=True)
        part = path.with_name(path.name + ".part")
        part.write_bytes(fetch(url))
        os.replace(part, path)
    raw = path.read_bytes()
    if expected_size and len(raw) != expected_size:
        raise ValueError(f"Size mismatch: {path}: {len(raw)} != {expected_size}")
    if md5 and hashlib.md5(raw).hexdigest() != md5:
        raise ValueError(f"MD5 mismatch: {path}")
    result = {"path": str(path.relative_to(ROOT)), "url": url,
              "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    print(f"Verified {group}/{name}: {len(raw):,} bytes", flush=True)
    return result


def zenodo(name: str, record: str) -> list[dict]:
    data = metadata(name, f"https://zenodo.org/api/records/{record}")
    results = []
    for item in data["files"]:
        results.append(save(name, item["key"], item["links"]["self"],
                            item["size"], item.get("checksum", "").removeprefix("md5:") or None))
    return results


def harvest(name: str, package: str) -> list[dict]:
    data = metadata(name, f"https://data.harvestportal.org/api/3/action/package_show?id={package}")["result"]
    results = []
    for item in data["resources"]:
        url = item["url"]
        filename = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
        if name == "malawi_field_dictionary" and filename not in {
            "mwi_cc_22_fieldnames.xlsx", "mwi_cc_2023_fieldnames.xlsx"
        }:
            continue
        results.append(save(name, filename, url, item.get("size")))
    return results


def main():
    tasks = [
        (harvest, "one_acre_fund_full", "oaf_mel"),
        (zenodo, "one_acre_fund_curated", "11122388"),
        (zenodo, "zimbabwe", "10060610"),
        (harvest, "malawi", "fao-bha-nasa-harvest-public-yield-datasets"),
        (harvest, "malawi_field_dictionary", "fao-bha-nasa-harvest-public-dataset-field-names"),
        (harvest, "malawi_metadata", "public-crop-cut-yield-dataset-metadata"),
    ]
    manifest = {"catalogue_checked_date": "2026-10-20", "files": [], "errors": []}
    for func, name, identifier in tasks:
        try:
            manifest["files"].extend(func(name, identifier))
        except Exception as exc:
            manifest["errors"].append({"dataset": name, "error": str(exc)})
            print(f"ERROR {name}: {exc}", flush=True)
        (META / "download_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"files": len(manifest["files"]),
                      "total_bytes": sum(f["bytes"] for f in manifest["files"]),
                      "errors": manifest["errors"]}, indent=2))


if __name__ == "__main__":
    main()
