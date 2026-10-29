"""scripts/get_data.py: batch slices, the window file it writes, and an offline --plan run."""
import argparse
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.cohorts import load_cohort

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "get_data.py"
spec = importlib.util.spec_from_file_location("get_data", SCRIPT)
get_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(get_data)

COLUMNS = ["cohort", "dataset", "source_id", "start_date", "end_date"]


@pytest.mark.parametrize("total, count", [(10, 3), (48, 1), (7, 7), (3, 10), (0, 2)])
def test_batch_slices_cover_every_record_once(total, count):
    slices = [get_data.batch_slice(total, i, count) for i in range(1, count + 1)]
    rows = [row for offset, size in slices for row in range(offset, offset + size)]
    assert rows == list(range(total))  # contiguous, in order, no gaps, no repeats


def test_batch_argument_is_validated():
    assert get_data.parse_batch("3/10") == (3, 10)
    for bad in ("0/3", "4/3", "3", "a/b", "1/2/3"):
        with pytest.raises(argparse.ArgumentTypeError):
            get_data.parse_batch(bad)


def test_cohort_window_file_matches_load_cohort(tmp_path):
    names = ["malawi_2022", "malawi_2023"]
    path = tmp_path / "windows.csv"
    table = get_data.write_windows(get_data.window_rows("cohorts", names), path)
    expected = pd.concat([load_cohort(name) for name in names], ignore_index=True)
    assert list(table.columns) == COLUMNS
    assert len(table) == len(expected) == 529 + 260
    assert table["cohort"].tolist() == expected["cohort"].tolist()
    assert table["source_id"].tolist() == expected["source_id"].tolist()
    assert table["start_date"].tolist() == expected["season_start"].tolist()
    assert table["end_date"].tolist() == expected["season_end"].tolist()
    pd.testing.assert_frame_equal(pd.read_csv(path, dtype=str), table)


def test_pilot_window_file_is_the_committed_one(tmp_path):
    path = tmp_path / "pilot.csv"
    get_data.write_windows(get_data.window_rows("pilot", get_data.scope_cohorts("pilot", None)), path)
    assert path.read_bytes() == (ROOT / "configs" / "sentinel2_windows_pilot48.csv").read_bytes()


def test_plan_runs_offline_and_slices_match_the_window_file(tmp_path, monkeypatch):
    monkeypatch.setattr(get_data.get_presto, "main", lambda argv: pytest.fail("--plan must not fetch Presto"))
    code = get_data.main(["--scope", "cohorts", "--cohorts", "malawi_2023", "malawi_2022", "--plan",
                          "--batch", "2/2", "--output-dir", str(tmp_path)])
    assert code == 0
    windows = pd.read_csv(tmp_path / "windows" / "sentinel2_windows_malawi_2022_malawi_2023.csv", dtype=str)
    assert len(windows) == 529 + 260
    (plan_file,) = tmp_path.glob("run-*/plan-*.jsonl")
    planned = [json.loads(line) for line in plan_file.read_text().splitlines()]
    # The downloader keeps the window file's order, so slice 2/2 is the second half of its rows.
    second_half = windows.iloc[len(windows) // 2:]
    assert [r["source_id"] for r in planned] == second_half["source_id"].tolist()
    assert [r["start_date"] for r in planned] == second_half["start_date"].tolist()


def test_pilot_plan_slices_follow_the_window_file_order(tmp_path, monkeypatch):
    # The pilot file is ordered by cohort as select_pilot lists them, not as the downloader lists datasets.
    monkeypatch.setattr(get_data.get_presto, "main", lambda argv: pytest.fail("--plan must not fetch Presto"))
    assert get_data.main(["--plan", "--batch", "2/3", "--output-dir", str(tmp_path)]) == 0
    windows = pd.read_csv(ROOT / "configs" / "sentinel2_windows_pilot48.csv", dtype=str)
    (plan_file,) = tmp_path.glob("run-*/plan-*.jsonl")
    planned = [json.loads(line)["source_id"] for line in plan_file.read_text().splitlines()]
    assert planned == windows["source_id"].iloc[16:32].tolist()


def test_status_reads_the_disk_and_downloads_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(get_data.download_sentinel2, "main", lambda argv: pytest.fail("--status must not download"))
    monkeypatch.setattr(get_data.get_presto, "main", lambda argv: pytest.fail("--status must not fetch Presto"))
    assert get_data.main(["--status", "--output-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "malawi_2023                      12 records: 12 not_on_disk" in out
    assert "zimbabwe_2024                    16 records: 16 not_on_disk" in out


def test_empty_batch_does_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(get_data.download_sentinel2, "main", lambda argv: pytest.fail("no records, no downloader"))
    code = get_data.main(["--scope", "cohorts", "--cohorts", "malawi_2023", "--plan",
                          "--batch", "1/1000", "--output-dir", str(tmp_path)])
    assert code == 0
    assert "nothing to do" in capsys.readouterr().out
