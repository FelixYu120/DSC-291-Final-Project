"""Protect historical inputs and avoid replaying into an existing result release."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("zimbabwe_reproduction", Path(__file__).parents[1] / "scripts/reproduce_zimbabwe.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "data/../../outside", "data\\outside"])
def test_manifest_paths_cannot_escape_snapshot(name):
    with pytest.raises(ValueError):
        runner.relative_path(name)


def test_recorded_hash_check_detects_mutated_data(tmp_path):
    data = tmp_path / "labels.csv"
    data.write_text("yield\n1\n")
    expected = {"labels.csv": runner.sha256(data)}
    assert runner.verify_paths(tmp_path, expected) == 1
    data.write_text("yield\n2\n")
    with pytest.raises(ValueError, match="Recorded hash differs"):
        runner.verify_paths(tmp_path, expected)


def test_replay_never_overwrites_an_existing_release(tmp_path):
    output = tmp_path / "release"
    output.mkdir()
    with pytest.raises(FileExistsError):
        runner.destination_for("compact", output)
    output.rmdir()
    Path(str(output) + ".reproduction.json").write_text("{}")
    with pytest.raises(FileExistsError):
        runner.destination_for("compact", output)


def test_command_preserves_output_as_one_literal_argument(tmp_path):
    output = tmp_path / "space;not-a-shell-command.json"
    command = runner.command_for("verify-compact", tmp_path, output)
    assert command[-2:] == ["--output", str(output)]
    assert command[1] == str(tmp_path / "scripts/verify_compact_weather.py")
