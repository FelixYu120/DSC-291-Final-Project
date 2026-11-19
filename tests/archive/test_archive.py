"""The pass archive: keys, survey rules, the pixel grid and the pixel reader. No network, no project data."""
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from cropyield.archive import catalog, ids, sampling, survey


def test_product_name_gives_scene_overflight_and_tile():
    name = ids.parse_product_name("S2B_MSIL2A_20190626T074619_N0212_R135_T36NXF_20190626T110744.SAFE")
    assert (name.platform, name.level, name.baseline, name.relative_orbit, name.tile) == ("S2B", "L2A", "02.12", 135, "36NXF")
    assert name.acquisition_id == "S2B_20190626T074619"
    assert name.scene_id == "S2B_MSIL2A_20190626T074619_N0212_R135_T36NXF_20190626T110744"
    # the Level-1C product and a reprocessing of the same granule share the overflight and the tile
    other = ids.parse_product_name("S2B_MSIL1C_20190626T074619_N0500_R135_T36NXF_20230723T034401")
    assert (other.acquisition_id, other.tile) == (name.acquisition_id, name.tile) and other.scene_id != name.scene_id
    with pytest.raises(ValueError):
        ids.parse_product_name("S2A_OPER_PRD_MSIL1C_PDMC_20151230T202002_R008_V20151230T105153_20151230T105153")


def test_keys_are_stable_and_keep_the_legacy_format():
    assert ids.source_observation_id("one_acre_fund_full", "ee151220") == "one_acre_fund_full:ee151220"
    assert ids.source_observation_id("one_acre_fund_curated", None, 7) == "one_acre_fund_curated:r000007"
    first = ids.field_season_id(["b:2", "a:1"])
    assert first == ids.field_season_id(["a:1"]) and first.startswith("fs_") and len(first) == 19
    assert ids.location_id("POINT (1 2)") != ids.location_id("POINT (1 3)")


def test_zero_blank_failure_and_not_measured_stay_apart():
    assert survey.label_status(1200.0) == "measured_positive"
    assert survey.label_status(0.0) == "recorded_zero"
    assert survey.label_status(0.0, zero_is_failure=True) == "verified_crop_failure"
    assert survey.label_status(None) == "not_answered"
    assert survey.label_status(float("nan")) == "not_answered"
    assert survey.label_status(None, not_measured=True) == "not_measured"


def test_only_a_field_point_inside_the_country_is_usable():
    good = survey.location_fields("KEN", 0.0864298, 34.7022612, "field_point")
    assert good["usable_at_field_scale"] and good["unusable_reason"] is None
    assert not survey.location_fields("KEN", None, None, "field_point")["usable_at_field_scale"]
    india = survey.location_fields("KEN", 29.22439, 76.141868, "field_point")       # one real workbook row
    assert india["location_quality"] == "outside_country" and not india["usable_at_field_scale"]
    assert not survey.location_fields("KEN", 0.227, 34.067, "rounded_point")["usable_at_field_scale"]


def test_curated_row_matches_the_full_row_by_yield_point_and_planting_date():
    per_acre = 1200.0
    common = {"country_iso3": "KEN", "harvest_year": 2019, "planting_date": pd.Timestamp("2019-04-15").date()}
    frame = pd.DataFrame([
        {**common, "source_observation_id": "full:a", "dataset": "one_acre_fund_full",
         "yield_raw": per_acre / survey.ACRE_HA, "latitude": 0.24712, "longitude": 34.08231},
        {**common, "source_observation_id": "full:b", "dataset": "one_acre_fund_full",      # same yield, far away
         "yield_raw": per_acre / survey.ACRE_HA, "latitude": 0.5, "longitude": 34.5},
        {**common, "source_observation_id": "cur:1", "dataset": "one_acre_fund_curated",
         "yield_raw": per_acre * survey.CURATED_FACTOR, "latitude": 0.248, "longitude": 34.081},
        {**common, "source_observation_id": "cur:2", "dataset": "one_acre_fund_curated",    # another yield
         "yield_raw": 999.0, "latitude": 0.248, "longitude": 34.081},
    ])
    links = survey.link_curated(frame).set_index("curated_id").candidates
    assert links["cur:1"] == ["full:a"] and links["cur:2"] == []


def test_offset_is_applied_once():
    assert catalog.dn_add_offset("sentinel-2-c1-l2a", "05.00", None) == -1000      # the file still holds +1000
    assert catalog.dn_add_offset("sentinel-2-l2a", "02.12", False) == 0            # no offset before 04.00
    assert catalog.dn_add_offset("sentinel-2-l2a", "05.00", True) == 0             # the provider removed it
    assert catalog.dn_add_offset("sentinel-2-l2a", "05.09", False) is None         # not measured: say so
    assert catalog.dn_add_offset(catalog.PLANETARY_COLLECTION, "02.12", None) == 0  # raw ESA numbers, old baseline
    assert catalog.dn_add_offset(catalog.PLANETARY_COLLECTION, "05.10", None) == -1000


def test_only_planetary_computer_addresses_get_a_token_and_it_is_reused(monkeypatch):
    calls = []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            calls.append(1)
            return {"token": "sig=abc", "msft:expiry": "2999-01-01T00:00:00Z"}
    monkeypatch.setattr(sampling.requests, "get", lambda url, timeout: Reply())
    monkeypatch.setitem(sampling._token, "expires", 0.0)
    aws = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/a/B04.tif"
    azure = "https://sentinel2l2a01.blob.core.windows.net/sentinel2-l2/a/B04_10m.tif"
    assert sampling.signed(aws) == aws and not calls
    assert sampling.signed(azure) == azure + "?sig=abc" and sampling.signed(azure).endswith("?sig=abc")
    assert len(calls) == 1                                                          # one token for many files


def test_a_point_falls_in_the_native_pixel_of_each_grid():
    tiles = pd.DataFrame([{"mgrs_tile": "36NXF", "epsg": 32636, "ulx": 600000.0, "uly": 100020.0, "size_m": 109800}])
    spots = pd.DataFrame({"location_id": ["inside", "outside"], "longitude": [34.7022612, 36.9],
                          "latitude": [0.0864298, 0.0864298]})
    placed = catalog.place_locations(spots, tiles)
    assert list(placed.location_id) == ["inside"]          # the second point is east of the tile square
    row = placed.iloc[0]
    # measured against the source file on 19 Nov 2026: B04 at (9046, 8944) and B05 at (4523, 4472)
    assert (row.row10, row.col10, row.row20, row.col20) == (9046, 8944, 4523, 4472)
    assert (row.row60, row.col60) == (9046 // 6, 8944 // 6)


def test_polygon_pixels_carry_centre_and_area(tmp_path):
    tiles = pd.DataFrame([{"mgrs_tile": "36LWL", "epsg": 32736, "ulx": 499980.0, "uly": 8600020.0, "size_m": 109800}])
    from pyproj import Transformer
    to_wgs84 = Transformer.from_crs(32736, 4326, always_xy=True).transform
    # a 30 m x 20 m field whose corner sits on the 10 m grid: 6 whole pixels
    x0, y1 = 499980.0 + 500 * 10, 8600020.0 - 700 * 10
    corners = [(x0, y1), (x0 + 30, y1), (x0 + 30, y1 - 20), (x0, y1 - 20), (x0, y1)]
    wkt = "POLYGON ((" + ", ".join("{:.9f} {:.9f}".format(*to_wgs84(x, y)) for x, y in corners) + "))"
    spots = pd.DataFrame({"location_id": ["field"], "geometry_type": ["polygon"], "geometry_wkt_wgs84": [wkt]})
    placed = pd.DataFrame({"location_id": ["field"], "mgrs_tile": ["36LWL"], "row10": [700], "col10": [500],
                           "row20": [350], "col20": [250], "row60": [116], "col60": [83]})
    pixels = sampling.footprint_pixels(spots, placed, tiles, tmp_path / "pixels.parquet")
    ten = pixels[pixels.res_m == 10]
    inside = ten[ten.center_inside]
    assert sorted(zip(inside.px_row, inside.px_col)) == [(700, 500), (700, 501), (700, 502), (701, 500), (701, 501), (701, 502)]
    assert ten.area_fraction.sum() == pytest.approx(6.0, abs=1e-3)      # 600 m2 of field in 100 m2 cells
    assert len(ten) > len(inside)                                       # the ring of edge pixels is kept
    assert pixels[pixels.res_m == 20].area_fraction.sum() == pytest.approx(1.5, abs=1e-3)


def test_reader_returns_the_stored_number_without_resampling(tmp_path):
    values = np.arange(64 * 64, dtype="uint16").reshape(64, 64)
    path = tmp_path / "band.tif"
    with rasterio.open(path, "w", driver="GTiff", height=64, width=64, count=1, dtype="uint16", crs="EPSG:32736",
                       transform=from_origin(499980, 8600020, 20, 20), tiled=True, blockxsize=16, blockysize=16) as file:
        file.write(values, 1)
    wanted = pd.DataFrame({"px_row": [0, 17, 63, 40], "px_col": [0, 33, 63, 5]})
    size, read = sampling.read_asset(str(path), {20: wanted})
    assert size == 20 and list(read) == [int(values[r, c]) for r, c in zip(wanted.px_row, wanted.px_col)]


def test_each_field_season_gets_its_country_year_step():
    rows = [   # dataset, country, harvest year, old cohort, measured -> step
        ("zimbabwe", "ZWE", 2023, "zimbabwe_lacuna_2022_2023", True, 1), ("zimbabwe", "ZWE", 2023, None, None, 1),
        ("one_acre_fund_full", "KEN", 2020, None, None, 2), ("one_acre_fund_full", "KEN", 2019, "kenya_oaf_2019_2020", True, 3),
        ("malawi_2023", "MWI", 2023, None, None, 4), ("malawi_2022", "MWI", 2022, "malawi_2022", True, 5),
        ("vision_guided_yield_estimation", "ZWE", 2024, "zimbabwe_2024", True, 6), ("zimbabwe", "ZWE", 2022, None, None, 7),
        ("one_acre_fund_full", "KEN", 2018, None, None, 8), ("one_acre_fund_full", "KEN", 2017, None, None, 9),
        ("one_acre_fund_full", "KEN", 2016, None, None, 10), ("one_acre_fund_full", "MWI", 2020, None, None, 11),
        ("vision_guided_yield_estimation", "ZWE", 2024, "zimbabwe_2024", False, 12),
        ("vision_guided_yield_estimation", "ZWE", 2024, None, None, 13), ("one_acre_fund_curated", "KEN", 2019, None, None, 14)]
    fields = pd.DataFrame(rows, columns=["dataset", "country_iso3", "harvest_year", "legacy_cohort",
                                         "legacy_include_primary", "expected"])
    assert list(sampling.step_of(fields)) == list(fields.expected)
    assert set(fields.expected) == set(sampling.STEPS)          # every step has a rule, every rule a name


def test_progress_counts_finished_units_per_step(tmp_path):
    plan = pd.DataFrame({"step": [1, 1, 2], "mgrs_tile": ["36NXF", "36NXF", "36KUE"], "block_row": [5, 5, 2],
                         "block_col": [4, 4, 12], "item_id": ["a", "b", "c"]})
    plan.to_parquet(tmp_path / "plan.parquet", index=False)
    for tile, block, item in (("36NXF", "b05_04", "a"), ("36NXF", "b05_04", "b")):
        folder = tmp_path / "shards" / tile / block
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{item}.parquet").write_bytes(b"x")
        (folder / "c.part_0").write_bytes(b"x")                 # an unfinished file is not a finished unit
    steps = {row["step"]: row for row in sampling.progress_by_step(tmp_path)}
    assert (steps[1]["units"], steps[1]["read"], steps[1]["complete"]) == (2, 2, True)
    assert (steps[2]["units"], steps[2]["read"], steps[2]["complete"]) == (1, 0, False)
    assert steps[1]["name"] == "Zimbabwe 2023 (Lacuna)"


def test_stop_time_is_today_at_that_clock_time():
    import time

    from cropyield.archive import download_all
    morning = time.mktime((2026, 11, 19, 5, 45, 0, 0, 0, -1))
    stop = download_all.stop_epoch("15:45", now=morning)
    assert stop - morning == 10 * 3600 and time.localtime(stop)[:5] == (2026, 11, 19, 15, 45)
    assert download_all.stop_epoch("05:00", now=morning) < morning     # a time that has passed: stop at once
    assert download_all.stop_epoch(None) is None


def test_safety_build_runs_once_at_its_time_and_not_after_the_reading_ended():
    import threading
    import time

    from cropyield.archive import download_all
    calls = []
    lock, finished = threading.Lock(), threading.Event()
    download_all.schedule_build(time.time(), lock, finished, build=lambda lock, label: calls.append(label)).join(5)
    assert calls == ["safety_build"]
    finished.set()                                              # the reading ended: the final build covers it
    download_all.schedule_build(time.time() + 60, lock, finished, build=lambda lock, label: calls.append(label)).join(5)
    assert calls == ["safety_build"]
