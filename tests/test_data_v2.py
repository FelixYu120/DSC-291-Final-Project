"""Data v2 (docs/DECISIONS.md, 5 Nov 2026): every new switch is off by default, and v1 stays as it is."""
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import numpy as np
import pandas as pd
import pytest

from cropyield.data.labels import LABELS_PATH, LABELS_V2_PATH, exclusion_reasons
from cropyield.eval.splits import check_split, temporal_rank

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def script(name: str, module: str):
    spec = importlib.util.spec_from_file_location(module, SCRIPTS / name)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[module] = loaded  # a script's dataclasses need their module importable
    spec.loader.exec_module(loaded)
    return loaded


step5 = script("step5_download_imagery.py", "step5_v2_test")
step6 = script("step6_build_database.py", "step6_v2_test")
step2 = script("step2_audit_labels.py", "step2_v2_test")


# --- downloader -------------------------------------------------------------------------------

def test_default_settings_still_name_the_v1_run():
    digest = lambda argv: step5.digest(step5.run_config(step5.arguments(["download", *argv])))[:16]  # noqa: E731
    assert digest([]) == "517bfcf0a69c6cac"
    assert digest(["--max-cloud-cover", "80"]) == "517bfcf0a69c6cac"   # 80 typed by hand was 80.0, another run
    assert digest(["--collection", "sentinel-2-l2a"]) != "517bfcf0a69c6cac"


def item(item_id: str, day: str, cloud: float) -> dict:
    return {"id": item_id, "properties": {"datetime": f"{day}T08:00:00Z", "eo:cloud_cover": cloud}}


def test_top_up_keeps_the_base_scenes_and_tries_only_what_the_base_did_not(tmp_path, monkeypatch):
    record = {"record_key": "zimbabwe__a__0123456789ab", "start_date": "2022-12-01", "end_date": "2023-02-28",
              "longitude": 31.0, "latitude": -18.0, "geometry": {"type": "Point", "coordinates": [31.0, -18.0]}}
    base = tmp_path / "run-base"
    base_record = base / "records" / record["record_key"]
    for scene in ("S2A_dec", "S2A_jan"):
        (base_record / scene).mkdir(parents=True)
        (base_record / scene / "reflectance.tif").write_bytes(b"pixels of " + scene.encode())
    attempts = ([{"month": "2022-12", "status": "accepted", "item_id": "S2A_dec"},
                 {"month": "2023-01", "status": "accepted", "item_id": "S2A_jan"}]
                + [{"month": "2023-02", "status": "rejected_cloud_or_nodata", "item_id": f"S2A_feb{i}"} for i in (1, 2, 3)])
    (base_record / "record.json").write_text(json.dumps({"status": "complete", "attempts": attempts,
                                                          "accepted_item_ids": ["S2A_dec", "S2A_jan"]}))
    base_bytes = (base_record / "record.json").read_bytes()
    # Today's catalogue: no December scene any more, another January scene first, February 3 old + 2 new.
    catalogue = [item("S2B_jan_new", "2023-01-05", 1), item("S2A_jan", "2023-01-20", 2)] + \
                [item(f"S2A_feb{i}", f"2023-02-0{i}", i) for i in (1, 2, 3)] + \
                [item("S2B_feb4", "2023-02-14", 50), item("S2B_feb5", "2023-02-20", 60)]
    tried = []

    def fake_download(scene, directory, record, grid, aoi, args):
        tried.append(scene["id"])
        return {"status": "accepted" if scene["id"] == "S2B_feb5" else "rejected_cloud_or_nodata",
                "item_id": scene["id"], "clear_fraction_aoi": 1.0}

    monkeypatch.setattr(step5, "download_scene", fake_download)
    args = SimpleNamespace(refresh_catalog=False, chip_size=8, resolution=10, max_scenes=12, candidates_per_month=24,
                           base_run=base, collection=step5.COLLECTION)
    result = step5.process_record(record, tmp_path / "run-new", SimpleNamespace(search=lambda r: catalogue), args)

    new_record = tmp_path / "run-new" / "records" / record["record_key"]
    written = json.loads((new_record / "record.json").read_text())
    assert tried == ["S2B_feb4", "S2B_feb5"]                     # only the two scenes the base never tried
    assert written["accepted_item_ids"] == ["S2A_dec", "S2A_jan", "S2B_feb5"]
    assert result["status"] == "complete" and result["scenes"] == 3
    for scene in ("S2A_dec", "S2A_jan"):                         # the base scenes, as hard links: the same files
        assert os.path.samefile(new_record / scene / "reflectance.tif", base_record / scene / "reflectance.tif")
    assert (base_record / "record.json").read_bytes() == base_bytes
    assert not (base_record / "S2B_feb5").exists()


def test_a_top_up_never_shares_a_run_folder_with_a_plain_run():
    plain = step5.run_config(step5.arguments(["download", "--candidates-per-month", "24"]))
    top_up = step5.run_config(step5.arguments(["download", "--candidates-per-month", "24", "--base-run", "x/run-517"]))
    assert step5.digest(plain) != step5.digest(top_up)


def test_a_cached_scene_of_an_unmeasured_item_is_not_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(step5, "verified_scene", lambda directory: {"clear_fraction_aoi": 1.0})
    scene = {"id": "S2A_z", "assets": {}, "properties": {"s2:processing_baseline": "05.10"}}
    attempt = step5.download_scene(scene, tmp_path, {"record_key": "k"}, None, None,
                                   SimpleNamespace(collection=step5.OLDER_COLLECTION))
    assert attempt["status"] == "rejected_unmeasured_offset"


def test_a_top_up_refuses_a_base_run_cut_with_other_settings(tmp_path):
    (tmp_path / "plan-x.json").write_text(json.dumps({"config": {"chip_size": 32}}))
    config = step5.run_config(step5.arguments(["download"]))
    with pytest.raises(ValueError, match="chip_size"):
        step5.check_base_run(tmp_path, config)


def test_older_collection_rejects_an_unmeasured_offset_before_reading_a_pixel(tmp_path, monkeypatch):
    def no_read(*args, **kwargs):
        raise AssertionError("a pixel was read")

    monkeypatch.setattr(step5, "read_asset", no_read)
    scene = {"id": "S2A_x", "assets": {}, "properties": {"s2:processing_baseline": "05.10"}}
    args = SimpleNamespace(collection=step5.OLDER_COLLECTION)
    attempt = step5.download_scene(scene, tmp_path / "S2A_x", {"record_key": "k"}, None, None, args)
    assert attempt["status"] == "rejected_unmeasured_offset"


def test_older_collection_reads_a_measured_item_with_offset_zero(tmp_path, monkeypatch):
    seen = {}

    class Stop(Exception):
        pass

    def fake_read(asset, grid, categorical=False):
        if categorical:
            return np.full((2, 2), 4, "uint8")                   # vegetation: clear
        seen["offset"] = asset["raster:bands"][0]["offset"]
        raise Stop

    monkeypatch.setattr(step5, "read_asset", fake_read)
    band = {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}
    scene = {"id": "S2A_y", "assets": {"scl": {}, **{name: band for name in step5.BANDS.values()}},
             "properties": {"s2:processing_baseline": "04.00"}}       # the unflagged case that read 0.1 too low
    args = SimpleNamespace(collection=step5.OLDER_COLLECTION, min_clear_fraction=0.8, bands=list(step5.BANDS))
    with pytest.raises(Stop):
        step5.download_scene(scene, tmp_path / "S2A_y", {"record_key": "k"}, None, np.ones((2, 2), bool), args)
    assert seen["offset"] == 0.0


# --- audit, labels, splits, database ------------------------------------------------------------

def test_the_datum_operations_are_the_named_ones():
    from pyproj import CRS
    assert "Arc 1950 to WGS 84 (1)" in step2.named_operation(CRS.from_epsg(20936), "EPSG:1113").description
    assert "Arc 1950 to WGS 84 (5)" in step2.named_operation(CRS.from_epsg(20936), "EPSG:1117").description


def test_labels_v2_refuse_an_audit_made_with_another_datum_operation(tmp_path, monkeypatch):
    import cropyield.data.labels as labels
    (tmp_path / "summary.json").write_text(json.dumps({"datum_operation": "EPSG:1117"}))
    monkeypatch.setattr(labels, "AUDIT_V2_DIR", tmp_path)
    with pytest.raises(ValueError, match="EPSG:1113"):
        labels.audit_dir("malawi_2022", 2)
    assert labels.audit_dir("malawi_2022", 1) == labels.AUDIT_DIR


def test_v2_includes_malawi_2022_and_v1_drops_it():
    frame = pd.DataFrame({"cohort": ["malawi_2022", "zimbabwe_lacuna_2022_2023"], "season_year": [2022, 2022],
                          "intercropped": [pd.NA, False], "irrigated": [pd.NA, False], "is_zero": [False, False],
                          "yield_kg_ha": [2000.0, 2000.0]})
    assert exclusion_reasons(frame, 1).tolist() == ["dropped_cohort_2022_imagery_gap", "dropped_year_2022_imagery_gap"]
    assert exclusion_reasons(frame, 2).tolist() == ["", "dropped_year_2022_imagery_gap"]


@pytest.mark.skipif(not LABELS_V2_PATH.exists(), reason="labels_v2 is not built on this copy")
def test_labels_v2_equals_labels_v1_outside_malawi_2022():
    v1, v2 = pd.read_parquet(LABELS_PATH), pd.read_parquet(LABELS_V2_PATH)
    other = v2["cohort"] != "malawi_2022"
    pd.testing.assert_frame_equal(v2[other].reset_index(drop=True), v1[other].reset_index(drop=True))
    malawi_2022 = v2[~other]
    assert len(malawi_2022) == 529 and malawi_2022["include_primary"].all()
    assert (malawi_2022["source_crs"] == "EPSG:20936 via EPSG:1113").all()


def test_temporal_rank_keeps_near_fields_of_the_first_season_and_every_field_of_the_second():
    def fields(cohort, year, lats):
        return pd.DataFrame({"obs_id": [f"{cohort}:{i}" for i in range(len(lats))], "cohort": cohort,
                             "season_year": year, "cluster_2km": range(len(lats)), "lat": lats, "lon": 33.0})
    first = fields("malawi_2022", 2022, [-13.0, -13.1, -15.0])       # the third field lies about 220 km away
    second = fields("malawi_2023", 2023, [-13.001, -13.05])
    split = temporal_rank(first, second)
    assert set(split["obs_id"]) == {"malawi_2022:0", "malawi_2022:1", "malawi_2023:0", "malawi_2023:1"}
    repeat0 = split[split["repeat"] == 0].set_index("obs_id")["fold"]
    assert repeat0["malawi_2022:0"] == "train" and repeat0["malawi_2023:0"] == "test"
    rows = pd.concat([first.iloc[:2], second])
    assert check_split(split, rows) == []


@pytest.mark.skipif(not LABELS_V2_PATH.exists(), reason="labels_v2 is not built on this copy")
def test_step4_v2_does_not_call_a_missing_frozen_file_unchanged(tmp_path, monkeypatch):
    import shutil
    step4 = script("step4_build_splits.py", "step4_v2_test")
    shutil.copytree(step4.SPLITS_V2_DIR, tmp_path / "splits")
    (tmp_path / "splits" / "malawi_2022__s1_cc2km.csv").unlink()
    monkeypatch.setattr(step4, "SPLITS_V2_DIR", tmp_path / "splits")
    assert step4.main(["--version", "2"]) == 1
    assert not (tmp_path / "splits" / "malawi_2022__s1_cc2km.csv").exists()


def test_the_v2_database_build_refuses_v1_paths(tmp_path):
    with pytest.raises(PermissionError, match="v1"):
        step6.build_database(tmp_path / "v2.duckdb", step6.DEFAULT_IMAGERY, tmp_path, version=2)


def test_the_database_build_refuses_a_file_that_holds_presto_rows(tmp_path):
    db = tmp_path / "team.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE presto_embeddings (obs_id VARCHAR, embedding FLOAT[2])")
        con.execute("INSERT INTO presto_embeddings VALUES ('a', [1.0, 2.0])")
    with pytest.raises(PermissionError, match="Presto"):
        step6.build_database(db, tmp_path)
    assert db.exists()


# --- step 9: the pre-registered v1 / v2 comparison ----------------------------------------------

step9 = script("step9_compare_data_v2.py", "step9_v2_test")


def paired_fields(n_clusters: int = 12, size: int = 5) -> pd.DataFrame:
    return pd.DataFrame({"group_id": np.repeat([str(g) for g in range(n_clusters)], size), "season_year": 2023})


def verdict(scores: list[dict]) -> dict:
    return {row["metric"]: row for row in scores}


def test_step9_identical_predictions_give_zero_and_no_win():
    fields = paired_fields()
    rng = np.random.default_rng(0)
    y = rng.normal(2.0, 1.0, len(fields))
    p = y + rng.normal(0, 1.0, len(fields))
    scores = verdict(step9.paired_scores(y, p, p.copy(), fields))
    assert scores["rank_v2_minus_v1"]["value"] == 0 and scores["rmse_v2_minus_v1"]["value"] == 0
    assert (scores["rank_v2_minus_v1"]["ci_low"], scores["rank_v2_minus_v1"]["ci_high"]) == (0, 0)
    assert scores["v2_wins"]["value"] == 0.0


def test_step9_a_better_v2_wins_and_a_worse_v2_does_not():
    fields = paired_fields()
    rng = np.random.default_rng(1)
    y = rng.normal(2.0, 1.0, len(fields))
    good, bad = y + rng.normal(0, 0.1, len(fields)), y + rng.normal(0, 2.0, len(fields))
    better = verdict(step9.paired_scores(y, bad, good, fields))          # (y, old, new)
    assert better["rmse_v2_minus_v1"]["value"] < 0 and better["rank_v2_minus_v1"]["ci_low"] > 0
    assert better["v2_wins"]["value"] == 1.0
    assert verdict(step9.paired_scores(y, good, bad, fields))["v2_wins"]["value"] == 0.0


def test_scripts_stop_on_a_database_that_differs_from_its_pin(tmp_path):
    (tmp_path / "cropyield.duckdb").write_bytes(b"team copy")
    pin = tmp_path / "pin.json"
    pin.write_text(json.dumps({"bytes": 9, "sha256": step9.sha256(tmp_path / "cropyield.duckdb")}))
    step9.check_database(tmp_path, pin)                                   # equal: passes
    (tmp_path / "cropyield.duckdb").write_bytes(b"team copx")
    with pytest.raises(SystemExit, match="differs from pin.json"):
        step9.check_database(tmp_path, pin)


@pytest.mark.skipif(not (step2.RAW / "malawi" / "mwi_mwi_lc_fo_202205_averageyield_v1.zip").exists(), reason="raw Malawi 2022 zip")
def test_step2_v2_note_names_the_datum_operation_it_used(tmp_path):
    step2.main(["--only", "malawi_2022", "--out-dir", str(tmp_path), "--datum-operation", "EPSG:1113"])
    notes = " ".join(json.loads((tmp_path / "summary.json").read_text())["datasets"][0]["notes"])
    assert "Arc 1950 to WGS 84 (1)" in notes and "44 m accuracy" in notes and "27 m" not in notes
