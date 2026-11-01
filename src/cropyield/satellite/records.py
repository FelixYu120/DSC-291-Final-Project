"""Which downloaded chip folder belongs to which labelled observation.

The downloader writes one folder per record under ``<imagery_dir>/run-<config>/records/``. A
folder counts for an observation only when it was searched over exactly the observation's season
window: months a folder never searched would look like cloudy months. When several runs hold
one, the newest record.json wins.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from cropyield.data.cohorts import obs_id as make_obs_id
from cropyield.longpath import filesystem_path, path_exists
from cropyield.satellite.chips import Chip


@dataclass
class Download:
    """One labelled observation and the chip folder downloaded for its season window."""
    obs_id: str
    record_dir: Path
    meta: dict            # the folder's record.json
    season_start: date
    season_end: date


def record_folders(imagery_dir: Path) -> list[tuple[Path, dict]]:
    """Every chip folder under imagery_dir with its record.json, newest file first."""
    folders = [folder for folder in imagery_dir.glob("run-*/records/*") if path_exists(folder / "record.json")]
    folders.sort(key=lambda folder: Path(filesystem_path(folder / "record.json")).stat().st_mtime, reverse=True)
    return [(folder, json.loads(Path(filesystem_path(folder / "record.json")).read_text())) for folder in folders]


def folder_bytes(folder: Path | str) -> int:
    """Bytes of every file under ``folder``; 0 when the folder does not exist yet."""
    if not path_exists(folder):
        return 0
    total, waiting = 0, [filesystem_path(folder, force=True)]
    while waiting:
        with os.scandir(waiting.pop()) as entries:
            for entry in entries:
                if entry.is_dir():
                    waiting.append(entry.path)
                    continue
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass  # a .part file the downloader has just renamed
    return total


class RecordScan:
    """What the record folders under imagery_dir hold now, for a loading bar that asks every few seconds.

    Reading all 11,364 record.json files takes a minute, so a repeat scan looks at the file times
    and reads only the files that changed. record.json comes last: a folder without one is still
    downloading, and it counts for nothing yet.
    """

    def __init__(self, imagery_dir: Path):
        self.imagery_dir = imagery_dir
        self.seen: dict[str, tuple[int, tuple, str]] = {}    # folder -> (file time, record key, status)
        self.sizes: dict[str, tuple[int, int]] = {}          # folder -> (file time, bytes)

    def statuses(self) -> dict[tuple[str, str, str, str], str]:
        """(dataset, source_id, start_date, end_date) -> status; the newest record.json wins."""
        for records in self.imagery_dir.glob("run-*/records"):
            with os.scandir(filesystem_path(records)) as folders:
                for folder in folders:
                    self._read(folder.path)
        return {key: status for _, key, status in sorted(self.seen.values(), key=lambda row: row[0])}

    def _read(self, folder: str) -> None:
        path = filesystem_path(os.path.join(folder, "record.json"))
        try:
            changed = os.stat(path).st_mtime_ns
        except OSError:
            return
        if folder not in self.seen or self.seen[folder][0] != changed:
            meta = json.loads(Path(path).read_text())
            record = meta["record"]
            key = (record["dataset"], record["source_id"], record["start_date"], record["end_date"])
            self.seen[folder] = (changed, key, meta["status"])

    def gigabytes(self) -> float:
        """GB on disk after the last statuses() call: the finished record folders and the catalogue cache."""
        for folder, (changed, _, _) in self.seen.items():
            if folder not in self.sizes or self.sizes[folder][0] != changed:
                self.sizes[folder] = (changed, folder_bytes(folder))
        return (sum(size for _, size in self.sizes.values()) + folder_bytes(self.imagery_dir / "catalog_cache")) / 1e9


def match_downloads(labels: pd.DataFrame, imagery_dir: Path) -> list[Download]:
    """The chip folder of each labelled observation, in labels order; observations without one are left out.

    ``labels`` needs the columns obs_id, season_start and season_end (ISO date text, as load_cohort gives).
    """
    seasons = labels.set_index("obs_id")[["season_start", "season_end"]]
    chosen: dict[str, Download] = {}
    for folder, meta in record_folders(imagery_dir):
        record = meta["record"]
        obs_id = make_obs_id(record["dataset"], record["source_id"])
        if obs_id in chosen or obs_id not in seasons.index:
            continue
        start, end = seasons.loc[obs_id]
        if (record.get("start_date"), record.get("end_date")) != (start, end):
            continue
        chosen[obs_id] = Download(obs_id, folder, meta, date.fromisoformat(start), date.fromisoformat(end))
    return [chosen[obs_id] for obs_id in labels["obs_id"] if obs_id in chosen]


def field_mask(chip: Chip) -> np.ndarray:
    """Pixels used as the field: centres inside the polygon, else the touched mask (as monthly_series does)."""
    return chip.aoi_interior if chip.aoi_interior.any() else chip.aoi
