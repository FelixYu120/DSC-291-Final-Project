from datetime import date

import numpy as np
import pytest
from conftest import AOI_REFLECTANCE, BANDS, RECORD, add_scenes, make_record_dir, write_scene

from cropyield.features.presto_inputs import MISSING_DYNAMIC_WORLD, NORMED_BANDS, PRESTO_MAX_TIMESTEPS, presto_inputs
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


def test_monthly_series_refuses_a_window_the_chip_was_not_downloaded_for(chip_dir):
    chip = read_chip(chip_dir)  # downloaded for 2023-03-01 .. 2023-06-30
    with pytest.raises(ValueError, match="does not cover"):
        monthly_series(chip, date(2022, 10, 1), date(2023, 6, 30))


def test_presto_inputs_scaling_masks_and_shapes(chip_dir):
    series = monthly_series(read_chip(chip_dir), *WINDOW)
    inputs = presto_inputs(series, latitude=-13.3171, longitude=33.3837)
    assert inputs.x.shape == inputs.mask.shape == (1, 4, 17) and len(NORMED_BANDS) == 17
    assert inputs.dynamic_world.shape == (1, 4) and (inputs.dynamic_world == MISSING_DYNAMIC_WORLD).all()
    assert inputs.latlons.tolist() == [[pytest.approx(-13.3171), pytest.approx(33.3837)]]
    assert inputs.month == 2  # March, 0-based
    x, mask = inputs.x[0], inputs.mask[0]
    # Scaling: Presto divides digital numbers by 10 000; our reflectance is already on that
    # scale with the Collection 1 offset applied, so the value passes through unchanged.
    assert x[0, NORMED_BANDS.index("B8")] == pytest.approx(0.25)
    assert x[0, NORMED_BANDS.index("B4")] == pytest.approx(0.05)
    assert x[0, NORMED_BANDS.index("NDVI")] == pytest.approx((0.25 - 0.05) / (0.25 + 0.05))
    # Masks: bands we do not have are masked everywhere; missing months are masked for every band.
    for name in ("VV", "VH", "temperature_2m", "total_precipitation", "elevation", "slope"):
        assert (mask[:, NORMED_BANDS.index(name)] == 1).all()
    assert (mask[[1, 3]] == 1).all() and (x[[1, 3]] == 0).all()
    s2_and_ndvi = [NORMED_BANDS.index(b) for b in ("B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12", "NDVI")]
    assert (mask[[0, 2]][:, s2_and_ndvi] == 0).all()
    assert np.isfinite(x).all()


def test_presto_inputs_refuse_empty_or_too_long_series(chip_dir):
    chip = read_chip(chip_dir)
    empty = monthly_series(chip, date(2023, 4, 1), date(2023, 4, 30))  # April has no scene
    assert empty.missing.all()
    with pytest.raises(ValueError, match="no month has a value"):
        presto_inputs(empty, latitude=-13.3, longitude=33.4)
    chip.end_date = date(2025, 12, 31)
    too_long = monthly_series(chip, date(2023, 3, 1), date(2025, 12, 31))
    assert len(too_long.months) > PRESTO_MAX_TIMESTEPS
    with pytest.raises(ValueError, match="Presto takes 1 to"):
        presto_inputs(too_long, latitude=-13.3, longitude=33.4)
