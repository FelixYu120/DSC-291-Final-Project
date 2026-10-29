"""Windows chip paths in this checkout are 260 characters or longer."""
import os
from pathlib import Path

import numpy as np
import pytest

from cropyield import longpath
from cropyield.longpath import filesystem_path, replace_file
from cropyield.satellite.chips import read_chip
from conftest import RECORD, make_record_dir, write_scene, add_scenes


def test_filesystem_path_leaves_short_paths_unchanged():
    text = filesystem_path(Path("data") / "imagery" / "sentinel2")
    assert not text.startswith("\\\\?\\")
    assert text.endswith(os.path.join("data", "imagery", "sentinel2"))


@pytest.mark.skipif(os.name != "nt", reason="MAX_PATH is a Windows limit")
def test_read_chip_opens_a_path_past_max_path(tmp_path):
    parent = tmp_path
    leaf = Path("malawi_2023__506ae8b2__synthetic") / "S2A_T36LWL_20230312T080000_L2A" / "reflectance.tif"
    while len(os.path.abspath(parent / leaf)) < 261:
        parent = parent / ("d" * 20)
    Path(filesystem_path(parent)).mkdir(parents=True, exist_ok=True)
    record_dir, touched = make_record_dir(parent, RECORD)
    interior = np.zeros(touched.shape, dtype=bool)
    interior[2:4, 2:4] = True
    item_id = "S2A_T36LWL_20230312T080000_L2A"
    reflectance = record_dir / item_id / "reflectance.tif"
    assert len(os.path.abspath(reflectance)) >= 260
    write_scene(record_dir, item_id, "2023-03-12", touched, interior)
    add_scenes(record_dir, [item_id])
    chip = read_chip(record_dir)
    assert chip.status == "complete" and len(chip.scenes) == 1
    assert chip.scenes[0].reflectance.shape[0] == 10


def flaky_replace(monkeypatch, failures):
    """os.replace that raises a sharing violation ``failures`` times, then renames."""
    real, calls = os.replace, []

    def replace(source, target):
        calls.append(source)
        if len(calls) <= failures:
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        real(source, target)
    monkeypatch.setattr(longpath.os, "replace", replace)
    return calls


def test_replace_file_retries_a_locked_file(tmp_path, monkeypatch):
    source, target = tmp_path / "x.json.part", tmp_path / "x.json"
    source.write_text("{}")
    calls = flaky_replace(monkeypatch, failures=2)
    replace_file(source, target, attempts=5, wait=0)
    assert len(calls) == 3 and target.read_text() == "{}" and not source.exists()


def test_replace_file_gives_up_after_the_last_attempt(tmp_path, monkeypatch):
    source, target = tmp_path / "x.json.part", tmp_path / "x.json"
    source.write_text("{}")
    calls = flaky_replace(monkeypatch, failures=5)
    with pytest.raises(PermissionError):
        replace_file(source, target, attempts=3, wait=0)
    assert len(calls) == 3 and source.exists() and not target.exists()
