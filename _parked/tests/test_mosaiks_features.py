"""scripts/features/mosaiks_features.py: the files it writes, reuse of saved filters, and params.json written last."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
from conftest import RECORD, SIZE, add_scenes, make_record_dir, write_scene

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mosaiks_features = load_script("mosaiks_features", SCRIPTS / "features" / "mosaiks_features.py")
build_database = load_script("build_database_for_mosaiks", SCRIPTS / "build_database.py")

OBS_ID = f"{RECORD['dataset']}:{RECORD['source_id']}"
SEASON = {"start_date": "2022-10-01", "end_date": "2023-06-30"}   # the Malawi 2023 window of cohorts.py
P = 4


@pytest.fixture
def imagery(tmp_path):
    """One labelled synthetic record (audit row 1 of Malawi 2023) with scenes in March and May."""
    records = tmp_path / "imagery" / "run-synthetic" / "records"
    record_dir, touched = make_record_dir(records, {**RECORD, **SEASON})
    interior = np.zeros((SIZE, SIZE), dtype=bool)
    interior[2:4, 2:4] = True
    write_scene(record_dir, "S2A_T36LWL_20230312T080000_L2A", "2023-03-12", touched, interior)
    write_scene(record_dir, "S2B_T36LWL_20230520T080000_L2A", "2023-05-20", touched, interior, invalid=[(2, 2)])
    add_scenes(record_dir, ["S2A_T36LWL_20230312T080000_L2A", "S2B_T36LWL_20230520T080000_L2A"])
    return tmp_path / "imagery"


def run(imagery: Path, out: Path, *extra: str) -> int:
    return mosaiks_features.main(["--imagery-dir", str(imagery), "--out-dir", str(out), "--patches", str(P), *extra])


def test_the_files_have_the_columns_the_database_expects(imagery, tmp_path):
    out = tmp_path / "mosaiks"
    assert run(imagery, out) == 0
    for _, (file, columns) in build_database.MOSAIKS_FILES.items():
        assert pq.read_table(out / file).column_names == columns
    monthly = pq.read_table(out / "monthly.parquet").to_pandas()
    assert monthly["obs_id"].tolist() == [OBS_ID, OBS_ID] and monthly["month"].tolist() == ["2023-03", "2023-05"]
    assert all(len(vector) == 2 * P for vector in monthly["chip"])
    params = json.loads((out / "params.json").read_text())
    assert params["k_features"] == 2 * P and params["n_patches"] == P


def test_a_second_run_reuses_the_saved_filters_and_gives_the_same_features(imagery, tmp_path):
    out = tmp_path / "mosaiks"
    assert run(imagery, out) == 0
    filters_bytes = (out / "filters.npz").read_bytes()
    first = pq.read_table(out / "season.parquet").to_pandas()
    assert run(imagery, out) == 0
    assert (out / "filters.npz").read_bytes() == filters_bytes
    second = pq.read_table(out / "season.parquet").to_pandas()
    np.testing.assert_array_equal(np.stack(first["chip"]), np.stack(second["chip"]))


def test_other_settings_are_refused_without_refit(imagery, tmp_path):
    out = tmp_path / "mosaiks"
    assert run(imagery, out) == 0
    with pytest.raises(SystemExit, match="--refit"):
        mosaiks_features.main(["--imagery-dir", str(imagery), "--out-dir", str(out), "--patches", str(P + 2)])


def test_params_json_is_written_last(imagery, tmp_path, monkeypatch):
    out = tmp_path / "mosaiks"

    def fail(*args, **kwargs):
        raise RuntimeError("stopped half-way")
    monkeypatch.setattr(mosaiks_features.mosaiks, "featurize", fail)
    with pytest.raises(RuntimeError):
        run(imagery, out)
    assert not (out / "params.json").exists() and not (out / "filters.npz").exists()  # the next run refits
