"""The database builder on a tiny hand-made staging set: windows, pass counting, statuses and the offset."""
import json

import duckdb
import pandas as pd
import pytest

from cropyield.archive import paths, release


def stamp(text):
    return pd.Timestamp(text, tz="UTC")


@pytest.fixture
def staged(tmp_path, monkeypatch):
    monkeypatch.setenv("CROPYIELD_DATA_DIR", str(tmp_path / "data"))        # no old database there: nothing reused
    monkeypatch.setenv("PASSARCHIVE_DIR", str(tmp_path / "archive"))
    survey, catalog, samples = (paths.staging_dir(part) for part in ("survey", "catalog", "samples"))
    for folder in (survey, catalog, samples / "shards" / "T1" / "b00_00", samples / "shards" / "T2" / "b00_00"):
        folder.mkdir(parents=True)

    def save(folder, name, rows):
        pd.DataFrame(rows).to_parquet(folder / f"{name}.parquet", index=False)

    save(survey, "source_files", [{"source_file_id": "abc", "dataset": "demo", "title": "Demo", "licence": "CC BY",
                                   "path": "raw/demo.csv", "bytes": 1, "rows_in_scope": 3, "rows_other_countries": 0}])
    save(survey, "locations", [{"location_id": "loc_a", "geometry_type": "point"},
                               {"location_id": "loc_b", "geometry_type": "point"}])
    common = {"dataset": "demo", "country_iso3": "ZWE", "crop": "maize", "legacy_cohort": None}
    place = {"planting_date": None, "harvest_date": None, "survey_date": None, "admin_unit": "Chivi", "site_unit": None,
             "intercropped": False, "irrigated": False, "geometry_type": "point", "latitude": -20.0, "longitude": 30.5,
             "location_quality": "field_point", "fold0_reserved": False}
    save(survey, "fields", [
        {**common, **place, "field_season_id": "fs_1", "primary_source_observation_id": "demo:1", "location_id": "loc_a",
         "harvest_year": 2023, "usable_at_field_scale": True},
        {**common, **place, "field_season_id": "fs_2", "primary_source_observation_id": "demo:2", "location_id": None,
         "harvest_year": 2016, "usable_at_field_scale": False},
        {**common, **place, "field_season_id": "fs_3", "primary_source_observation_id": "demo:3", "location_id": "loc_b",
         "harvest_year": 2015, "usable_at_field_scale": True}])
    save(survey, "source_records", [{**common, "source_observation_id": f"demo:{n}", "field_season_id": f"fs_{n}",
                                     "harvest_year": year, "payload_json": '{"Yield": 2.5}'}
                                    for n, year in ((1, 2023), (2, 2016), (3, 2015))])
    save(survey, "field_source_crosswalk", [{"field_season_id": f"fs_{n}", "source_observation_id": f"demo:{n}"}
                                            for n in (1, 2, 3)])
    raw = {"yield_raw_unit": "t/ha", "zero_evidence": None}
    save(survey, "labels", [
        {**raw, "field_season_id": "fs_1", "label_status": "measured_positive", "yield_raw": 2.5, "yield_kg_ha": 2500.0},
        {**raw, "field_season_id": "fs_2", "label_status": "recorded_zero", "yield_raw": 0.0, "yield_kg_ha": 0.0},
        {**raw, "field_season_id": "fs_3", "label_status": "not_answered", "yield_raw": None, "yield_kg_ha": None}])
    save(survey, "label_measurements", [{"field_season_id": "fs_1", "measurement": "yield", "value": 2.5, "unit": "t/ha"}])
    save(survey, "splits", [{"field_season_id": "fs_1", "split_name": "frozen/v1/demo/s1_cc2km", "fold": 0, "repeat": 0}])
    save(survey, "split_specs", [{"split_name": "frozen/v1/demo/s1_cc2km", "frozen": True, "version": "v1",
                                  "source_file": "splits/demo.csv", "sha256": "x", "rows": 1}])

    save(catalog, "tiles", [{"mgrs_tile": tile, "epsg": 32736, "ulx": 0.0, "uly": 0.0, "size_m": 109800}
                            for tile in ("T1", "T2")])
    save(catalog, "location_tiles", [{"location_id": "loc_a", "mgrs_tile": tile, "row10": 5, "col10": 7}
                                     for tile in ("T1", "T2")]
         + [{"location_id": "loc_b", "mgrs_tile": "T1", "row10": 9, "col10": 9}])
    granules = [   # id, tile, overflight, sensing time
        ("g_last_second_2022", "T1", "S2A_20221231T235950", "2022-12-31T23:59:59Z"),
        ("g_first_second_2023", "T1", "S2A_20230101T000000", "2023-01-01T00:00:00Z"),
        ("g_same_overflight_other_tile", "T2", "S2A_20230101T000000", "2023-01-01T00:00:05Z"),
        ("g_outside_swath", "T1", "S2B_20230315T080000", "2023-03-15T08:00:00Z"),
        ("g_no_public_file", "T1", "S2B_20230610T080000", "2023-06-10T08:00:00Z"),
        ("g_first_second_2024", "T1", "S2B_20240101T000000", "2024-01-01T00:00:00Z")]
    save(catalog, "granules", [{"granule_id": name, "mgrs_tile": tile, "acquisition_id": flight, "platform": flight[:3],
                                "relative_orbit": 78, "sensing_time": stamp(when), "year": stamp(when).year,
                                "month": stamp(when).month, "footprint_wkt": None}
                               for name, tile, flight, when in granules])
    scenes = [(f"scene_{name}", name, "L2A") for name, *_ in granules] + [("scene_l1c", "g_first_second_2023", "L1C")]
    tile_of = {name: tile for name, tile, *_ in granules}
    when_of = {name: stamp(when) for name, _, _, when in granules}
    save(catalog, "scenes", [{"scene_id": scene, "granule_id": name, "level": level, "mgrs_tile": tile_of[name],
                              "processing_baseline": "05.10", "cloud_cover_percent": 99.0, "in_cdse": True,
                              "sensing_time": when_of[name]} for scene, name, level in scenes])
    readable = [name for name, *_ in granules if name != "g_no_public_file"]
    save(catalog, "scene_items", [{"scene_id": f"scene_{name}", "provider": "earth-search",
                                   "collection": "sentinel-2-c1-l2a", "item_id": f"item_{name}",
                                   "dn_add_offset": -1000.0, "assets_json": '{"B04": {"href": "x"}}'} for name in readable])
    save(catalog, "catalog_queries", [{"provider": "cdse", "mgrs_tile": tile, "year": year, "status": "ok", "items": 1}
                                      for tile in ("T1", "T2") for year in (2022, 2023)])
    save(catalog, "location_granules", [{"location_id": "loc_a", "granule_id": name,
                                         "in_catalogue_footprint": name != "g_outside_swath"} for name, *_ in granules])
    pd.DataFrame([{"location_id": "loc_a", "mgrs_tile": tile, "res_m": 10, "px_row": 5, "px_col": 7,
                   "center_inside": True, "area_fraction": None, "is_point_pixel": True} for tile in ("T1", "T2")]
                 ).to_parquet(samples / "footprint_pixels.parquet", index=False)

    def shard(tile, name, numbers):
        pd.DataFrame([{"location_id": "loc_a", "res_m": 10, "px_row": 5, "px_col": 7, "band": band, "dn": dn,
                       "item_id": f"item_{name}", "scene_id": f"scene_{name}"} for band, dn in numbers.items()]
                     ).to_parquet(samples / "shards" / tile / "b00_00" / f"item_{name}.parquet", index=False)
    shard("T1", "g_first_second_2023", {"B03": 1400, "B04": 1500, "B08": 4000, "B02": 1300})   # 99 % cloud scene, kept
    shard("T2", "g_same_overflight_other_tile", {"B03": 0, "B04": 0, "B08": 0, "B02": 0})      # tile edge: no data
    return tmp_path


def test_windows_statuses_overflights_and_offset(staged):
    database = release.build()
    assert database.exists() and not database.with_suffix(".building").exists()
    con = duckdb.connect(str(database), read_only=True, config={"enable_external_access": "false"})
    passes = con.execute("""select g.granule_id, p.window_kind, p.year, p.month, p.sample_status, p.n_l1c_products
                            from passes p join granules g using (granule_key) join fields f using (fs_key)
                            where f.field_season_id = 'fs_1'""").df().set_index("granule_id")
    # 1 January 00:00:00 UTC opens the harvest year; one second earlier is the year before; the next year is out
    assert passes.loc["g_last_second_2022", ["window_kind", "year", "month"]].tolist() == ["previous", 2022, 12]
    assert passes.loc["g_first_second_2023", ["window_kind", "year", "month"]].tolist() == ["current", 2023, 1]
    assert "g_first_second_2024" not in passes.index and len(passes) == 5
    assert passes.sample_status.to_dict() == {
        "g_last_second_2022": "not_sampled_yet", "g_first_second_2023": "sampled_all_bands",
        "g_same_overflight_other_tile": "sampled_nodata", "g_outside_swath": "outside_swath_per_catalogue",
        "g_no_public_file": "not_sampled_no_public_file"}
    # Level-1C and Level-2A of one granule are one pass; two tiles of one overflight are one overflight
    assert passes.loc["g_first_second_2023", "n_l1c_products"] == 1
    assert con.execute("""select n_tiles from v_overflights where field_season_id = 'fs_1'
                          and acquisition_id = 'S2A_20230101T000000'""").fetchall() == [(2,)]
    january = con.execute("""select n_passes, n_overflights, month_status from coverage_months c
                             join fields f using (fs_key)
                             where f.field_season_id = 'fs_1' and year = 2023 and month = 1""").fetchone()
    assert january == (2, 1, "complete")
    # every dated field-season has 24 month rows, with the reason when a month is empty
    assert con.execute("select count(*) from coverage_months group by fs_key").fetchall() == [(24,)] * 3
    status = dict(con.execute("""select f.field_season_id || ' ' || year || '-' || month, month_status
                                 from coverage_months c join fields f using (fs_key)""").fetchall())
    assert status["fs_2 2016-3"] == "unusable_location"
    assert status["fs_3 2015-5"] == "pre_mission" and status["fs_3 2015-6"] == "catalogue_zero"
    assert status["fs_1 2023-2"] == "catalogue_zero" and status["fs_1 2022-12"] == "listed_not_sampled"
    # the +1000 of the file is removed once: (1500 - 1000) / 10000 and (4000 - 1000) / 10000
    red, nir = con.execute("select b04, b08 from v_reflectance where granule_id = 'g_first_second_2023'").fetchone()
    assert (red, nir) == (pytest.approx(0.05), pytest.approx(0.30))
    assert con.execute("select ndvi from v_ndvi_v1").fetchall() == [(pytest.approx(0.25 / 0.35),)]   # nodata: no row
    assert con.execute("select count(*) from pass_bands_long where band = 'B04'").fetchone()[0] == 2
    # one table with everything: a row per pass, plus one row for each field-season that has no pass
    master = con.execute("select field_season_id, granule_id, yield_kg_ha, b04, sample_status, source_row_json from master").df()
    assert len(master) == 5 + 2 and master.groupby("field_season_id").size().to_dict() == {"fs_1": 5, "fs_2": 1, "fs_3": 1}
    cloudy = master[master.granule_id == "g_first_second_2023"].iloc[0]
    assert (cloudy.yield_kg_ha, cloudy.b04, cloudy.sample_status) == (2500.0, 1500.0, "sampled_all_bands")
    assert master[master.field_season_id == "fs_2"].granule_id.isna().all()         # kept, with empty pass columns
    # X and y: one row per field-season, the passes as one list in time order
    xy = con.execute("select field_season_id, yield_kg_ha, n_passes, n_passes_all_bands, passes from field_xy").df()
    xy = xy.set_index("field_season_id")
    assert len(xy) == 3 and xy.n_passes.to_dict() == {"fs_1": 5, "fs_2": 0, "fs_3": 0}
    first = xy.loc["fs_1"]
    assert (first.yield_kg_ha, first.n_passes_all_bands, len(first.passes)) == (2500.0, 1, 5)
    assert [entry["month"] for entry in first.passes] == [12, 1, 1, 3, 6] and first.passes[1]["b04"] == 1500.0
    assert con.execute("select passes is null from field_xy where field_season_id = 'fs_2'").fetchone()[0]   # kept, no list
    info = json.loads((database.parent / "manifest.json").read_text(encoding="utf-8"))
    assert info["sha256"] == release.sha256(database) and info["row_counts"]["passes"] == 5
    con.close()


def test_second_image_source_makes_a_pass_readable(staged):
    catalog = paths.staging_dir("catalog")
    pd.DataFrame([{"scene_id": "scene_pc", "granule_id": "g_no_public_file", "level": "L2A", "mgrs_tile": "T1",
                   "processing_baseline": "02.12", "cloud_cover_percent": 10.0, "in_cdse": False,
                   "sensing_time": stamp("2023-06-10T08:00:00Z")}]).to_parquet(catalog / "scenes_pc.parquet", index=False)
    pd.DataFrame([{"scene_id": "scene_pc", "provider": "planetary-computer", "collection": "planetary-computer/sentinel-2-l2a",
                   "item_id": "item_pc", "dn_add_offset": 0.0, "assets_json": '{"B04": {"href": "x"}}'}]
                 ).to_parquet(catalog / "scene_items_pc.parquet", index=False)
    con = duckdb.connect(str(release.build()), read_only=True)
    assert con.execute("""select p.sample_status, p.n_l2a_products from passes p join granules g using (granule_key)
                          where g.granule_id = 'g_no_public_file'""").fetchall() == [("not_sampled_yet", 2)]
    assert con.execute("select count(*) from scene_items where provider = 'planetary-computer'").fetchone()[0] == 1
    con.close()


def test_new_split_is_added_and_frozen_names_are_protected(staged, tmp_path):
    database = release.build()
    csv = tmp_path / "mine.csv"
    pd.DataFrame({"field_season_id": ["fs_1", "fs_3"], "fold": [0, 1]}).to_csv(csv, index=False)
    assert release.register_split(database, "team/me/v1", csv) == 2
    for name in ("team/me/v1", "frozen/v1/demo/s1_cc2km", "frozen/new"):
        with pytest.raises(SystemExit):
            release.register_split(database, name, csv)
    con = duckdb.connect(str(database), read_only=True)
    assert con.execute("select fold from splits where split_name like 'frozen/%'").fetchall() == [(0,)]
    assert con.execute("select count(*) from split_membership_full where not assigned").fetchone()[0] == 3
    con.close()
