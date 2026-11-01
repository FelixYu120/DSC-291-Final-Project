"""scripts/get_all_data.py: batch slices, the window file, an offline --plan run, and the notebook download."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.cohorts import load_cohort
from cropyield.satellite import records
from cropyield.satellite.records import RecordScan

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "get_all_data.py"
spec = importlib.util.spec_from_file_location("get_all_data", SCRIPT)
get_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(get_data)

COLUMNS = ["cohort", "dataset", "source_id", "start_date", "end_date"]


def test_requirements_pin_exactly_the_packages_of_pyproject():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pinned = [line.split("==")[0] for line in lines if "==" in line]
    assert pinned == project["dependencies"] + project["optional-dependencies"]["dev"]
    assert "-e ." in lines


@pytest.mark.parametrize("name", ["step1_download_labels", "step1b_download_zimbabwe2024_labels", "step2_audit_labels",
                                  "step3_build_labels", "step5_download_imagery"])
def test_step_scripts_that_moved_up_a_folder_find_the_repository_root(name):
    step_spec = importlib.util.spec_from_file_location(name, SCRIPT.parent / f"{name}.py")
    module = importlib.util.module_from_spec(step_spec)
    step_spec.loader.exec_module(module)
    assert module.ROOT == ROOT


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


def test_a_later_slice_does_not_rename_onto_a_finished_window_file(tmp_path, monkeypatch):
    path = tmp_path / "pilot.csv"
    rows = get_data.window_rows("pilot", get_data.scope_cohorts("pilot", None))
    get_data.write_windows(rows, path)
    monkeypatch.setattr(get_data, "replace_file", lambda *a: pytest.fail("the same bytes must not be written twice"))
    assert len(get_data.write_windows(rows, path)) == 48
    assert [item.name for item in tmp_path.iterdir()] == ["pilot.csv"]


def test_plan_runs_offline_and_slices_match_the_window_file(tmp_path):
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


def test_pilot_plan_slices_follow_the_window_file_order(tmp_path):
    # The pilot file is ordered by cohort as PILOT_SIZES lists them, not as the downloader lists datasets.
    assert get_data.main(["--plan", "--batch", "2/3", "--output-dir", str(tmp_path)]) == 0
    windows = pd.read_csv(ROOT / "configs" / "sentinel2_windows_pilot48.csv", dtype=str)
    (plan_file,) = tmp_path.glob("run-*/plan-*.jsonl")
    planned = [json.loads(line)["source_id"] for line in plan_file.read_text().splitlines()]
    assert planned == windows["source_id"].iloc[16:32].tolist()


def test_status_reads_the_disk_and_downloads_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(get_data.step5_download_imagery, "main", lambda argv: pytest.fail("--status must not download"))
    assert get_data.main(["--status", "--output-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "malawi_2023                      12 records: 12 not_on_disk" in out
    assert "zimbabwe_2024                    16 records: 16 not_on_disk" in out


def test_empty_batch_does_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(get_data.step5_download_imagery, "main", lambda argv: pytest.fail("no records, no downloader"))
    code = get_data.main(["--scope", "cohorts", "--cohorts", "malawi_2023", "--plan",
                          "--batch", "1/1000", "--output-dir", str(tmp_path)])
    assert code == 0
    assert "nothing to do" in capsys.readouterr().out


def test_plan_estimate_reflects_parallel_slices(tmp_path, capsys):
    assert get_data.main(["--scope", "all", "--plan", "--output-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "11,364 records: about 681.8 GB moved, about 22.7 GB kept, about 4 h 13 min with 32 parallel slices" in out
    assert "189" not in out.split("[4/4]")[1]


def test_plan_takes_the_slice_count_of_the_batch(tmp_path, capsys):
    assert get_data.main(["--scope", "all", "--plan", "--batch", "1/16", "--output-dir", str(tmp_path)]) == 0
    assert "about 8 h 25 min with 16 parallel slices" in capsys.readouterr().out


def pilot_table() -> pd.DataFrame:
    return get_data.window_table(get_data.window_rows("pilot", get_data.scope_cohorts("pilot", None)))


def write_record(imagery: Path, row, status: str = "complete", run: str = "run-a", megabytes: int = 1) -> Path:
    """A record folder as the downloader leaves it: the files first, record.json last."""
    folder = imagery / run / "records" / row.source_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "aoi_mask.tif").write_bytes(b"x" * (megabytes * 1_000_000))
    if status != "still_downloading":
        (folder / "record.json").write_text(json.dumps({"status": status, "record": {
            "dataset": row.dataset, "source_id": row.source_id, "start_date": row.start_date, "end_date": row.end_date}}))
    return folder


def test_progress_counts_finished_and_failed_records_of_the_scope_only(tmp_path):
    table = pilot_table()
    rows = list(table.itertuples())
    write_record(tmp_path, rows[0])
    write_record(tmp_path, rows[1], "no_scenes")
    write_record(tmp_path, rows[2], "error")
    write_record(tmp_path, rows[3], "partial_error")
    write_record(tmp_path, rows[4], "still_downloading")
    write_record(tmp_path, rows[5]._replace(start_date="2000-01-01"))  # another window does not count
    assert get_data.field_counts(table, RecordScan(tmp_path).statuses()) == (2, 2)


def test_the_newest_record_json_wins_in_the_progress_count(tmp_path):
    table = pilot_table()
    row = next(table.itertuples())
    write_record(tmp_path, row, "error", run="run-a")
    os.utime(tmp_path / "run-a" / "records" / row.source_id / "record.json", (1_000_000, 1_000_000))
    write_record(tmp_path, row, "complete", run="run-b")
    assert get_data.field_counts(table, get_data.record_status(tmp_path)) == (1, 0)


def test_a_repeat_scan_reads_only_the_record_json_that_changed(tmp_path, monkeypatch):
    rows = list(pilot_table().itertuples())
    write_record(tmp_path, rows[0], "error")
    write_record(tmp_path, rows[1])
    reads = []
    real_loads = json.loads
    monkeypatch.setattr(records.json, "loads", lambda text: reads.append(1) or real_loads(text))
    scan = RecordScan(tmp_path)
    scan.statuses()
    assert len(reads) == 2
    scan.statuses()
    assert len(reads) == 2
    folder = write_record(tmp_path, rows[0], "complete")
    os.utime(folder / "record.json", (2_000_000_000, 2_000_000_000))
    key = (rows[0].dataset, rows[0].source_id, rows[0].start_date, rows[0].end_date)
    assert scan.statuses()[key] == "complete"
    assert len(reads) == 3


def test_gigabytes_count_finished_records_and_the_catalogue_cache(tmp_path):
    rows = list(pilot_table().itertuples())
    write_record(tmp_path, rows[0], megabytes=2)
    write_record(tmp_path, rows[1], "still_downloading", megabytes=5)
    (tmp_path / "catalog_cache").mkdir()
    (tmp_path / "catalog_cache" / "one.json").write_bytes(b"x" * 500_000)
    scan = RecordScan(tmp_path)
    scan.statuses()
    assert scan.gigabytes() == pytest.approx(0.0025, abs=1e-5)
    assert RecordScan(tmp_path / "nothing_yet").gigabytes() == 0


def test_time_left_uses_the_speed_of_this_run_only():
    assert get_data.seconds_left(48, 10, 10, 60.0) is None  # a restart that has fetched nothing yet
    assert get_data.seconds_left(48, 18, 10, 80.0) == 300.0  # 8 new records in 80 s, 30 left
    assert get_data.seconds_left(48, 48, 0, 80.0) == 0


def test_loading_bar_states_fields_gigabytes_and_time():
    assert (get_data.bar_text(2, 48, 0, 0.0043, None)
            == "4.2% done | 2 of 48 fields | 0.00 GB on disk | time left not known yet")
    assert (get_data.bar_text(1200, 11364, 3, 2.5, 7380.0)
            == "10.6% done | 1,200 of 11,364 fields | 3 failed | 2.50 GB on disk | about 2 h 3 min left")
    assert '<progress value="2" max="48"' in get_data.bar_html(2, 48, 0, 0.0, None)


@pytest.mark.parametrize("left", [0.0, None])
def test_a_full_bar_says_finished_and_no_time_left(left):
    assert get_data.bar_text(48, 48, 0, 0.25, left) == "100.0% done | 48 of 48 fields | 0.25 GB on disk | finished"


@pytest.mark.parametrize("answer, expected", [("yes", True), (" YES\n", True), ("no", False), ("", False), ("yes please", False)])
def test_only_a_typed_yes_counts(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda question: answer)
    assert get_data.typed_yes("?") is expected


@pytest.mark.parametrize("error", [EOFError, NotImplementedError])
def test_a_run_with_no_keyboard_counts_as_no(monkeypatch, error):
    def no_keyboard(question):
        raise error
    monkeypatch.setattr("builtins.input", no_keyboard)
    assert get_data.typed_yes("?") is False


def test_start_slices_runs_each_slice_once_and_keeps_a_log(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(get_data.subprocess, "Popen", lambda command, **options: commands.append(command))
    assert len(get_data.start_slices("pilot", 3, tmp_path)) == 3
    assert [command[command.index("--batch") + 1] for command in commands] == ["1/3", "2/3", "3/3"]
    assert all(command[0] == sys.executable and "--stop-with-parent" in command for command in commands)
    assert sorted(item.name for item in (tmp_path / "logs").iterdir()) == [f"slice_{i}_of_3.log" for i in (1, 2, 3)]


def test_a_slice_ends_when_the_kernel_that_started_it_is_gone():
    code = (f"import sys, time; sys.path.insert(0, {str(SCRIPT.parent)!r}); import get_all_data; "
            "get_all_data.stop_with_parent(); time.sleep(120)")
    process = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE)
    process.stdin.close()  # what the end of a kernel does to the pipe
    assert process.wait(timeout=60) == 1


@pytest.fixture
def cell(tmp_path, monkeypatch):
    """notebook_download with the slices and the database build replaced by notes of what ran."""
    class Cell:
        def __init__(self):
            self.data_dir = tmp_path / "copy"
            self.imagery = tmp_path / "copy" / "imagery" / "sentinel2"
            self.started, self.built, self.stopped, self.answers = [], [], [], []

        def press(self, *answers):
            self.answers[:] = answers
            get_data.notebook_download("pilot", 32, self.data_dir)

    cell = Cell()
    monkeypatch.setattr("builtins.input", lambda question: cell.answers.pop(0))
    monkeypatch.setattr(get_data, "loading_bar", lambda: lambda html: None)
    monkeypatch.setattr(get_data, "start_slices", lambda *call: cell.started.append(call) or [])
    monkeypatch.setattr(get_data, "stop_slices", lambda processes: cell.stopped.append(processes))
    monkeypatch.setattr(get_data, "run_database_build", lambda *call: cell.built.append(call))
    return cell


def small_database(path: Path, presto_rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE downloads (obs_id VARCHAR)")
        con.execute("CREATE TABLE scenes (obs_id VARCHAR, month VARCHAR, item_id VARCHAR)")
        con.execute("CREATE TABLE presto_embeddings (obs_id VARCHAR)")
        con.execute("INSERT INTO presto_embeddings SELECT 'x' FROM range(?)", [presto_rows])


def test_any_answer_but_yes_starts_no_download_and_writes_nothing(cell, tmp_path, capsys):
    cell.press("no")
    assert cell.started == [] and cell.built == []
    assert not cell.data_dir.exists()
    assert "No download started." in capsys.readouterr().out


def test_a_step_of_the_notebook_runs_with_one_matrix_thread():
    assert get_data.background_options()["env"]["OPENBLAS_NUM_THREADS"] == "1"


def test_the_cell_says_when_a_slice_ended_with_an_error(cell, monkeypatch, capsys):
    ended = [SimpleNamespace(returncode=code, poll=lambda: 0) for code in (1, 0)]
    monkeypatch.setattr(get_data, "start_slices", lambda *call: ended)
    cell.press("yes")
    assert "1 of 32 slices ended with an error." in capsys.readouterr().out


def test_the_cell_states_the_cost_before_it_asks(cell, capsys):
    cell.press("no")
    assert "48 records: about 2.9 GB moved, about 0.1 GB kept, about 1 min with 32 parallel slices" in capsys.readouterr().out


def test_the_cell_says_what_is_on_disk_and_how_a_restart_works_before_it_asks(cell, monkeypatch, capsys):
    for row in list(pilot_table().itertuples())[:12]:
        write_record(cell.imagery, row)
    printed_before_the_question = []

    def question(text):
        printed_before_the_question.append(capsys.readouterr().out)
        return "no"
    monkeypatch.setattr("builtins.input", question)
    get_data.notebook_download("pilot", 32, cell.data_dir)
    out = printed_before_the_question[0]
    assert "On disk: 12 of 48 fields are done (25.0%). This run gets only the other 36." in out
    assert "Stop:    you can stop at any time. Every finished field stays on disk." in out
    assert "Restart: run this cell again. It checks the disk and downloads only the missing fields." in out


def test_the_cell_says_when_nothing_is_missing(cell, capsys):
    for row in pilot_table().itertuples():
        write_record(cell.imagery, row)
    cell.press("no")
    assert "On disk: 48 of 48 fields are done (100.0%). This run fetches nothing new." in capsys.readouterr().out


def test_a_yes_starts_the_slices_then_builds_and_reports_two_lines(cell, capsys):
    write_record(cell.imagery, next(pilot_table().itertuples()))
    cell.press("yes")
    assert cell.started == [("pilot", 32, cell.imagery)]
    assert cell.built == [(cell.data_dir, cell.imagery)]
    assert cell.stopped == [[]]
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "Complete: no, 1 of 48 records are complete. Run this cell again: it downloads only the missing fields.",
        "Same scenes: not checked, because there is no database."]


def test_the_last_lines_say_complete_and_count_the_same_scenes(cell, capsys):
    table = pilot_table()
    for row in table.itertuples():
        write_record(cell.imagery, row)
    database = cell.data_dir / "cropyield.duckdb"
    small_database(database, 0)
    cell.press("yes")
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "Complete: yes, all 48 records are complete.",
        "Same scenes: 0 of 0 records hold the same scenes as the frozen list."]


def test_nothing_done_builds_no_database(cell, capsys):
    cell.press("yes")
    assert cell.built == []
    assert "no record is done" in capsys.readouterr().out


def test_presto_rows_ask_a_second_time_and_a_no_keeps_the_database(cell, capsys):
    write_record(cell.imagery, next(pilot_table().itertuples()))
    small_database(cell.data_dir / "cropyield.duckdb", 3)
    cell.press("yes", "no")
    out = capsys.readouterr().out
    assert "The database holds 3 rows in presto_embeddings. The database build removes them." in out
    assert len(cell.started) == 1 and cell.built == []
    assert "Database not built" in out


def test_presto_rows_and_a_yes_build_the_database(cell, capsys):
    write_record(cell.imagery, next(pilot_table().itertuples()))
    small_database(cell.data_dir / "cropyield.duckdb", 3)
    cell.press("yes", "yes")
    assert len(cell.built) == 1


def test_the_stop_button_stops_the_slices_and_builds_nothing(cell, monkeypatch, capsys):
    def stopped_by_hand(*arguments):
        raise KeyboardInterrupt
    monkeypatch.setattr(get_data, "watch_slices", stopped_by_hand)
    for row in list(pilot_table().itertuples())[:12]:
        write_record(cell.imagery, row)
    cell.press("yes")
    assert cell.stopped == [[]] and cell.built == []
    assert capsys.readouterr().out.splitlines()[-1] == (
        "Stopped at 25.0%: 12 of 48 fields are on disk. Run this cell again: it downloads only the missing fields.")


def download_cells() -> list[dict]:
    guide = json.loads((ROOT / "notebooks" / "data_guide.ipynb").read_text(encoding="utf-8"))
    return [cell for cell in guide["cells"] if "notebook_download(" in "".join(cell["source"])]


def test_every_download_cell_of_the_guide_is_tagged_and_has_its_switch_and_slices_on_top():
    cells = download_cells()
    assert len(cells) == 2
    assert all(cell["metadata"]["tags"] == ["download"] for cell in cells)
    assert all(cell["source"][0].startswith("DOWNLOAD = True") for cell in cells)
    assert all(cell["source"][1].startswith("SLICES = 32") for cell in cells)


@pytest.mark.parametrize("index, scope", [(0, "pilot"), (1, "all")])
def test_download_true_presses_the_button_of_its_scope(monkeypatch, index, scope):
    calls = []
    monkeypatch.setitem(sys.modules, "get_all_data", SimpleNamespace(notebook_download=lambda *call: calls.append(call)))
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.chdir(ROOT)
    exec("".join(download_cells()[index]["source"]), {})
    assert [call[:2] for call in calls] == [(scope, 32)]


@pytest.mark.parametrize("index", [0, 1])
def test_download_false_skips_the_cell_and_asks_nothing(monkeypatch, capsys, index):
    monkeypatch.setitem(sys.modules, "get_all_data", None)  # an import would now fail
    monkeypatch.setattr("builtins.input", lambda question: pytest.fail("the switch is off, so the cell must not ask"))
    exec("".join(download_cells()[index]["source"]).replace("DOWNLOAD = True", "DOWNLOAD = False", 1), {})
    assert "Download is off" in capsys.readouterr().out
