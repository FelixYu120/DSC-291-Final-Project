"""cropyield.satellite.records.match_downloads: the right chip folder for each labelled observation."""
import os
from pathlib import Path

import pandas as pd
from conftest import RECORD, make_record_dir

from cropyield.longpath import filesystem_path
from cropyield.satellite.records import match_downloads

OBS_ID = f"{RECORD['dataset']}:{RECORD['source_id']}"
SEASON = {"start_date": "2022-10-01", "end_date": "2023-06-30"}
LABELS = pd.DataFrame({"obs_id": [OBS_ID], "season_start": [SEASON["start_date"]], "season_end": [SEASON["end_date"]]})


def record_in_run(imagery: Path, run: str, window: dict, modified: float) -> Path:
    """A synthetic record folder of OBS_ID in run-<run>, searched over ``window``, with record.json at time ``modified``."""
    record_dir, _ = make_record_dir(imagery / f"run-{run}" / "records", {**RECORD, **window})
    os.utime(filesystem_path(record_dir / "record.json"), (modified, modified))
    return record_dir


def test_the_newest_record_json_wins_when_several_runs_hold_one(tmp_path):
    record_in_run(tmp_path, "old", SEASON, modified=1_000_000)
    newest = record_in_run(tmp_path, "new", SEASON, modified=2_000_000)
    (match,) = match_downloads(LABELS, tmp_path)
    assert match.obs_id == OBS_ID and match.record_dir == newest


def test_a_folder_searched_over_another_window_does_not_count(tmp_path):
    record_in_run(tmp_path, "pilot", {"start_date": "2023-03-01", "end_date": "2023-06-30"}, modified=3_000_000)
    assert match_downloads(LABELS, tmp_path) == []
    matching = record_in_run(tmp_path, "season", SEASON, modified=1_000_000)   # older, but the right window
    (match,) = match_downloads(LABELS, tmp_path)
    assert match.record_dir == matching


def test_observations_without_a_label_row_are_ignored(tmp_path):
    record_in_run(tmp_path, "run", SEASON, modified=1_000_000)
    assert match_downloads(LABELS.assign(obs_id="malawi_2023:someone-else"), tmp_path) == []
