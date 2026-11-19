"""Every directory the pass-archive build reads or writes.

Inputs are read-only: ``data/raw``, ``data/splits``, ``data/v2`` and the old databases. Outputs live under one
root, ``data/passarchive_v1`` (override with ``PASSARCHIVE_DIR``): ``staging`` (Parquet, rebuilt) and ``release``
(the folder that is shared).
"""
from __future__ import annotations

import os
from pathlib import Path

from cropyield import ROOT
from cropyield.archive import RELEASE


def data_dir() -> Path:
    """The project data folder: ``CROPYIELD_DATA_DIR`` or ``<repository>/data``."""
    return Path(os.environ.get("CROPYIELD_DATA_DIR") or ROOT / "data")


def archive_dir() -> Path:
    """Root of all pass-archive outputs: ``PASSARCHIVE_DIR`` or ``<data>/passarchive_v1``."""
    return Path(os.environ.get("PASSARCHIVE_DIR") or data_dir() / RELEASE)


def raw_dir() -> Path:
    return data_dir() / "raw"


def staging_dir(part: str) -> Path:
    """Staging folder of one step: ``survey``, ``catalog`` or ``samples``."""
    if part not in {"survey", "catalog", "samples"}:
        raise ValueError(f"unknown staging part: {part}")
    return archive_dir() / "staging" / part


def release_dir() -> Path:
    """The shareable folder: the DuckDB file, README, dictionary, manifest, checksum."""
    return archive_dir() / "release"


def team_database() -> Path:
    return release_dir() / f"{RELEASE}.duckdb"
