"""Download the public field-photo yield dataset from Zenodo record 17626117.

The metadata CSV is about 6 MB. The original photo archive is about 4.9 GB and
is kept out of Git; pass --metadata-only to fetch only the tabular data.
Downloads are streamed, resumable, and checked against Zenodo's published MD5.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RECORD_ID = "17626117"
RECORD_URL = f"https://zenodo.org/api/records/{RECORD_ID}"
OUT = ROOT / "data" / "raw" / "vision_guided_yield_estimation"
META = ROOT / "data" / "metadata"
RECORD_CACHE = META / f"zenodo_{RECORD_ID}_record.json"
MANIFEST = META / "vision_guided_yield_download_manifest.json"
WANTED = {"metadata.csv"}
PHOTO_ARCHIVE = "q_field_photo.zip"
CHUNK_SIZE = 1024 * 1024


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"User-Agent": "DSC190-academic-data-download/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(item: dict) -> dict:
    name = item["key"]
    destination = OUT / name
    partial = destination.with_name(destination.name + ".part")
    expected_size = int(item["size"])
    expected_md5 = item.get("checksum", "").removeprefix("md5:") or None

    if destination.exists():
        if destination.stat().st_size == expected_size and (
            not expected_md5 or md5_file(destination) == expected_md5
        ):
            print(f"Already verified: {destination.relative_to(ROOT)}", flush=True)
            return file_record(destination, item)
        raise ValueError(f"Existing file does not match Zenodo metadata: {destination}")

    offset = partial.stat().st_size if partial.exists() else 0
    if offset > expected_size:
        partial.unlink()
        offset = 0

    if offset == expected_size and expected_md5 and md5_file(partial) != expected_md5:
        partial.unlink()
        offset = 0

    response = None
    if offset < expected_size:
        url = item["links"]["self"]
        headers = {"User-Agent": "DSC190-academic-data-download/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and offset == expected_size:
                response = None
            else:
                raise

    if response is not None:
        status = getattr(response, "status", response.getcode())
        if offset and status != 206:
            # The server ignored Range; restart rather than append duplicate bytes.
            offset = 0
        mode = "ab" if offset else "wb"
        received = offset
        started = time.monotonic()
        last_report = started
        with response, partial.open(mode) as output:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                received += len(chunk)
                now = time.monotonic()
                if now - last_report >= 15:
                    elapsed = max(now - started, 1)
                    rate = (received - offset) / elapsed / (1024 * 1024)
                    print(
                        f"{name}: {received:,}/{expected_size:,} bytes "
                        f"({received / expected_size:.1%}, {rate:.1f} MiB/s)",
                        flush=True,
                    )
                    last_report = now

    if not partial.exists() or partial.stat().st_size != expected_size:
        actual = partial.stat().st_size if partial.exists() else 0
        raise ValueError(
            f"Incomplete download for {name}: {actual:,} bytes, expected {expected_size:,}; "
            "rerun the command to resume"
        )
    if expected_md5 and md5_file(partial) != expected_md5:
        raise ValueError(f"Zenodo MD5 checksum mismatch for {name}; partial file retained")
    partial.replace(destination)
    print(f"Downloaded and verified: {destination.relative_to(ROOT)}", flush=True)
    return file_record(destination, item)


def file_record(path: Path, item: dict) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "zenodo_md5": item.get("checksum"),
        "sha256": digest.hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="download only metadata.csv and skip the approximately 4.9 GB photo archive",
    )
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)
    record = get_json(RECORD_URL)
    if record.get("id") != int(RECORD_ID):
        raise ValueError("Zenodo API returned an unexpected record")
    RECORD_CACHE.write_text(json.dumps(record, indent=2) + "\n")

    license_id = record.get("metadata", {}).get("license", {}).get("id")
    if license_id != "cc-by-4.0":
        raise ValueError(f"Unexpected Zenodo license: {license_id!r}")
    files = {item["key"]: item for item in record.get("files", [])}
    missing = WANTED - files.keys()
    if missing:
        raise ValueError(f"Expected Zenodo files are missing: {sorted(missing)}")
    selected = [files["metadata.csv"]]
    if not args.metadata_only:
        if PHOTO_ARCHIVE not in files:
            raise ValueError(f"Expected archive is missing: {PHOTO_ARCHIVE}")
        selected.append(files[PHOTO_ARCHIVE])

    current = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    checksums = current.get("files", {})
    for item in selected:
        checksums[item["key"]] = download(item)
        MANIFEST.write_text(json.dumps({
            "record_id": int(RECORD_ID),
            "record_url": f"https://zenodo.org/records/{RECORD_ID}",
            "title": record["metadata"].get("title"),
            "license": license_id,
            "files": checksums,
        }, indent=2) + "\n")
    print(json.dumps({"downloaded_or_verified": list(checksums), "manifest": str(MANIFEST.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
