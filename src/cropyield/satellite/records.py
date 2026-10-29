"""Which downloaded chip folder belongs to which labelled observation.

The downloader writes one folder per record under ``<imagery_dir>/run-<config>/records/``. A
folder counts for an observation only when it was searched over exactly the observation's season
window: months a folder never searched would look like cloudy months. When several runs hold
one, the newest record.json wins.
"""
from __future__ import annotations

import json
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
