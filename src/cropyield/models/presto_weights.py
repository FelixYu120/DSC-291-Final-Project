"""Where the pretrained Presto weights come from, and how to recognise the right file.

Kept free of torch so scripts/get_presto.py can run before the model dependencies exist.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from cropyield import ROOT

PRESTO_REPO = "https://github.com/nasaharvest/presto"
PRESTO_COMMIT = "11e207a668a34336ced1d8e492a1bd5849b96c4a"
# single_file_presto.py at that commit, vendored byte-identical as presto_single_file.py.
PRESTO_SOURCE_SHA256 = "fb487a3a9ceb6040eaa8e97b9cd2dd9df8cb6c650ab889ac0868944ed55700df"
PRESTO_SOURCE_PATH = Path(__file__).with_name("presto_single_file.py")
# data/default_model.pt at that commit.
PRESTO_WEIGHTS_URL = f"https://raw.githubusercontent.com/nasaharvest/presto/{PRESTO_COMMIT}/data/default_model.pt"
PRESTO_WEIGHTS_SHA256 = "559c9d76f525bdf2dd3774da8b1e7f1510769b73baacac12e9e4d8d5c67fbe65"
PRESTO_WEIGHTS_BYTES = 3_321_716
PRESTO_WEIGHTS_PATH = ROOT / "data" / "models" / "presto" / "default_model.pt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def weights_verified(path: Path = PRESTO_WEIGHTS_PATH) -> bool:
    """True when the file exists with the pinned size and SHA-256."""
    path = Path(path)
    return path.exists() and path.stat().st_size == PRESTO_WEIGHTS_BYTES and sha256(path) == PRESTO_WEIGHTS_SHA256
