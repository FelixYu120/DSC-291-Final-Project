from datetime import date

import numpy as np
import pytest
from conftest import AOI_REFLECTANCE, BANDS, RECORD, add_scenes, make_record_dir, write_scene

from cropyield.satellite.chips import read_chip
from cropyield.satellite.monthly import month_range, monthly_series

WINDOW = (date(2023, 3, 1), date(2023, 6, 30))  # Mar, Apr, May, Jun


def test_read_chip_turns_nodata_into_nan_and_sorts_scenes(chip_dir):
    chip = read_chip(chip_dir)
    assert chip.bands == tuple(BANDS)
    assert chip.aoi.sum() == 9 and chip.aoi_interior.sum() == 4 and (chip.aoi_interior & ~chip.aoi).sum() == 0
    assert [s.date for s in chip.scenes] == [date(2023, 3, 12), date(2023, 5, 20)]
    may = chip.scenes[1]
    assert np.isnan(may.reflectance[:, ~may.valid]).all() and (~may.valid).sum() == 2


def test_point_record_keeps_its_single_pixel(tmp_path):
    point = {**RECORD, "geometry": {"type": "Point", "coordinates": [33.3837, -13.3171]}}
    record_dir, touched = make_record_dir(tmp_path, point, aoi_type="point_pixel")
    write_scene(record_dir, "S2A_T36LWL_20230312T080000_L2A", "2023-03-12", touched, touched)
    add_scenes(record_dir, ["S2A_T36LWL_20230312T080000_L2A"])
    chip = read_chip(record_dir)
    assert chip.aoi.sum() == chip.aoi_interior.sum() == 1
    series = monthly_series(chip, *WINDOW)
    assert series.pixel_rule == "interior" and series.n_pixels.tolist() == [1, 0, 0, 0]
    assert series.band("B08")[0] == pytest.approx(AOI_REFLECTANCE["B08"])


def test_monthly_series_uses_only_valid_aoi_pixels_and_nan_for_missing_months(chip_dir):
    series = monthly_series(read_chip(chip_dir), *WINDOW)
    assert series.months == month_range(*WINDOW) == ["2023-03", "2023-04", "2023-05", "2023-06"]
    assert series.values.shape == (4, len(BANDS))
    assert series.missing.tolist() == [False, True, False, True]
    assert series.pixel_rule == "interior"
    assert series.n_pixels.tolist() == [4, 0, 2, 0]           # May: two interior pixels were invalid
    for band, value in AOI_REFLECTANCE.items():                # boundary 0.5 and outside 0.9 never leak in
        assert series.band(band)[0] == pytest.approx(value) and series.band(band)[2] == pytest.approx(value)
    assert series.item_ids[0].startswith("S2A") and series.item_ids[1] is None


def test_monthly_series_refuses_a_failed_download(chip_dir):
    import json
    meta = json.loads((chip_dir / "record.json").read_text())
    meta["status"] = "partial_error"
    (chip_dir / "record.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="partial_error"):
        monthly_series(read_chip(chip_dir), *WINDOW)


def test_monthly_series_refuses_a_window_the_chip_was_not_downloaded_for(chip_dir):
    chip = read_chip(chip_dir)  # downloaded for 2023-03-01 .. 2023-06-30
    with pytest.raises(ValueError, match="does not cover"):
        monthly_series(chip, date(2022, 10, 1), date(2023, 6, 30))
