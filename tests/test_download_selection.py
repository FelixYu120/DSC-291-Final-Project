"""--only-listed: the downloader plans exactly the records named in --date-overrides (offline plan)."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "step5_download_imagery.py"
spec = importlib.util.spec_from_file_location("step5_download_imagery", SCRIPT)
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)

COLUMNS = ["dataset", "source_row", "source_id", "country", "year", "crop", "longitude", "latitude",
           "yield_kg_ha", "planting_date", "harvest_date", "observation_time",
           "passes_yield_and_known_location_checks"]


def write_audit(directory: Path) -> None:
    with (directory / "zimbabwe_screened_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for i, source_id in enumerate(["a", "b", "c"], 1):
            writer.writerow({"dataset": "zimbabwe", "source_row": i, "source_id": source_id, "country": "zimbabwe",
                             "year": 2023, "crop": "maize", "longitude": 31.0 + i / 100, "latitude": -18.0,
                             "yield_kg_ha": 2000, "planting_date": "", "harvest_date": "", "observation_time": "",
                             "passes_yield_and_known_location_checks": "True"})


def plan(tmp_path: Path, *extra: str) -> list[str]:
    out = tmp_path / "out"
    assert downloader.main(["plan", "--audit-dir", str(tmp_path), "--output-dir", str(out),
                            "--datasets", "zimbabwe", *extra]) == 0
    (plan_file,) = out.glob("run-*/plan-*.jsonl")
    return [json.loads(line)["source_id"] for line in plan_file.read_text().splitlines()]


def test_only_listed_plans_exactly_the_window_file(tmp_path):
    write_audit(tmp_path)
    windows = tmp_path / "windows.csv"
    windows.write_text("cohort,dataset,source_id,start_date,end_date\n"
                       "zimbabwe_lacuna_2022_2023,zimbabwe,b,2022-10-01,2023-06-30\n")
    assert plan(tmp_path, "--date-overrides", str(windows), "--only-listed") == ["b"]


def test_without_only_listed_every_eligible_record_is_planned(tmp_path):
    write_audit(tmp_path)
    assert plan(tmp_path) == ["a", "b", "c"]


def test_only_listed_needs_a_window_file():
    with pytest.raises(SystemExit):
        downloader.arguments(["plan", "--only-listed"])


def scene_folder(directory: Path, reflectance: bytes | None = None) -> Path:
    """A scene folder whose scene.json checksum matches its reflectance.tif."""
    from rasterio.transform import from_origin
    import numpy as np

    grid = {"crs": "EPSG:32736", "transform": from_origin(500000, 8500000, 10, 10), "width": 4, "height": 4}
    downloader.write_tif(directory / "reflectance.tif", np.ones((2, 4, 4), "float32"), grid, -9999.0, ["B02", "B03"])
    if reflectance is not None:
        (directory / "reflectance.tif").write_bytes(reflectance)
    (directory / "scene.json").write_text(json.dumps(
        {"files_sha256": {"reflectance.tif": downloader.sha256(directory / "reflectance.tif")}}))
    return directory


def test_verified_scene_accepts_a_whole_file(tmp_path):
    assert downloader.verified_scene(scene_folder(tmp_path)) is not None


def test_verified_scene_refuses_an_unreadable_file_with_a_matching_hash(tmp_path):
    # The header of the broken pilot file: TIFF magic, first-directory offset 0.
    assert downloader.verified_scene(scene_folder(tmp_path, b"II*\x00\x00\x00\x00\x00" + b"\x00" * 64)) is None


def test_a_restart_keeps_a_finished_record_and_fetches_only_the_rest(tmp_path):
    from types import SimpleNamespace

    import numpy as np
    from rasterio.transform import from_origin

    searched = []

    class Catalog:
        def search(self, record):
            searched.append(record["record_key"])
            return []

    args = SimpleNamespace(refresh_catalog=False, chip_size=8, resolution=10, max_scenes=12, candidates_per_month=3)
    place = {"start_date": "2023-01-01", "end_date": "2023-06-30", "longitude": 31.0, "latitude": -18.0,
             "geometry": {"type": "Point", "coordinates": [31.0, -18.0]}}
    finished = tmp_path / "records" / "finished"
    scene_folder(finished / "S2A_item")
    grid = {"crs": "EPSG:32736", "transform": from_origin(500000, 8500000, 10, 10), "width": 4, "height": 4}
    downloader.write_tif(finished / "aoi_mask.tif", np.ones((4, 4), "uint8"), grid, None, ["mask"])
    (finished / "record.json").write_text(json.dumps({
        "status": "complete", "accepted_item_ids": ["S2A_item"], "aoi_sha256": downloader.sha256(finished / "aoi_mask.tif")}))
    before = (finished / "record.json").stat().st_mtime_ns

    catalog = Catalog()
    kept = downloader.process_record({**place, "record_key": "finished"}, tmp_path, catalog, args)
    fetched = downloader.process_record({**place, "record_key": "stopped_halfway"}, tmp_path, catalog, args)

    assert kept == {"record_key": "finished", "status": "complete", "scenes": 1, "reused": True}
    assert fetched["status"] == "no_scenes"
    assert searched == ["stopped_halfway"]
    assert (finished / "record.json").stat().st_mtime_ns == before
