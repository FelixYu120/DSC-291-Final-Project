"""Download the pretrained Presto weights pinned in cropyield.models.presto and verify them.

Writes data/models/presto/default_model.pt (git-ignored) plus a provenance JSON beside it.
A file that already matches the pinned size and SHA-256 is reused. Downloads go to a .part
file and are renamed only after size and hash match, so a partial download never sits at the
final path. A file at the final path that does not match is reported and left alone unless
--replace is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.models.presto_weights import (
    PRESTO_COMMIT,
    PRESTO_REPO,
    PRESTO_WEIGHTS_BYTES,
    PRESTO_WEIGHTS_PATH,
    PRESTO_WEIGHTS_SHA256,
    PRESTO_WEIGHTS_URL,
    weights_verified,
)


def download(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    digest = hashlib.sha256()
    try:
        with requests.get(PRESTO_WEIGHTS_URL, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            with part.open("wb") as handle:
                for block in response.iter_content(1 << 20):
                    handle.write(block)
                    digest.update(block)
    except BaseException:
        part.unlink(missing_ok=True)  # an interrupted stream leaves no stray file behind
        raise
    size = part.stat().st_size
    if size != PRESTO_WEIGHTS_BYTES or digest.hexdigest() != PRESTO_WEIGHTS_SHA256:
        part.unlink()
        raise ValueError(f"download incomplete or altered: {size} bytes, sha256 {digest.hexdigest()[:16]}...")
    part.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=PRESTO_WEIGHTS_PATH)
    parser.add_argument("--replace", action="store_true", help="overwrite a file at --path that does not match the pin")
    args = parser.parse_args(argv)
    path = args.path
    if weights_verified(path):
        print(f"OK  {path} already present and verified (sha256 {PRESTO_WEIGHTS_SHA256[:16]}...)")
    else:
        if path.exists():
            if not args.replace:
                raise ValueError(f"{path} exists but is not the pinned Presto checkpoint "
                                 f"({path.stat().st_size} bytes, expected {PRESTO_WEIGHTS_BYTES}); "
                                 "rerun with --replace to overwrite it")
            print(f"!!  {path} does not match the pin ({path.stat().st_size} bytes); replacing it")
        print(f"..  downloading {PRESTO_WEIGHTS_URL}")
        download(path)
        print(f"OK  {path} downloaded and verified ({PRESTO_WEIGHTS_BYTES} bytes)")
    provenance = {"repository": PRESTO_REPO, "commit": PRESTO_COMMIT, "url": PRESTO_WEIGHTS_URL,
                  "sha256": PRESTO_WEIGHTS_SHA256, "bytes": PRESTO_WEIGHTS_BYTES,
                  "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                  "verified_at": datetime.now(timezone.utc).isoformat()}
    path.with_suffix(".json").write_text(json.dumps(provenance, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, requests.RequestException) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
