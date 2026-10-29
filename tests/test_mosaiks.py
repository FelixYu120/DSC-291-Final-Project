"""MOSAIKS features on the synthetic 6 x 6 chip (conftest): K = 2P, determinism, poolings, nulls."""
import numpy as np
import pytest
from conftest import RECORD, add_scenes, make_record_dir, write_scene

from cropyield.features import mosaiks
from cropyield.satellite.chips import read_chip
from cropyield.satellite.records import field_mask

P = 8


def fit(chip, seed=291):
    return mosaiks.fit_filters([s.reflectance for s in chip.scenes], n_patches=P, patch_size=3, seed=seed)


def test_k_features_is_two_per_patch(chip_dir):
    chip = read_chip(chip_dir)
    filters = fit(chip)
    assert filters.filters.shape == (P, 10, 3, 3) and filters.k_features == 2 * P
    chip_vec, field_vec = mosaiks.featurize(chip.scenes[0], field_mask(chip), filters)
    assert chip_vec.shape == field_vec.shape == (2 * P,)
    assert chip_vec.dtype == np.float32


def test_same_seed_gives_identical_filters_and_features(chip_dir):
    chip = read_chip(chip_dir)
    first, second = fit(chip), fit(chip)
    np.testing.assert_array_equal(first.filters, second.filters)
    np.testing.assert_array_equal(first.band_mean, second.band_mean)
    a = mosaiks.featurize(chip.scenes[0], field_mask(chip), first)
    b = mosaiks.featurize(chip.scenes[0], field_mask(chip), second)
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])
    assert not np.array_equal(first.filters, fit(chip, seed=7).filters)


def test_chip_and_field_pooling_differ(chip_dir):
    chip = read_chip(chip_dir)
    chip_vec, field_vec = mosaiks.featurize(chip.scenes[0], field_mask(chip), fit(chip))
    assert not np.allclose(chip_vec, field_vec)


def test_only_fully_valid_windows_count(chip_dir):
    chip = read_chip(chip_dir)
    march, may = chip.scenes
    assert mosaiks.complete_windows(march.valid, 3).sum() == 16        # inner 4 x 4 of a 6 x 6 chip
    assert mosaiks.complete_windows(may.valid, 3).sum() == 2           # two invalid interior pixels
    _, field_may = mosaiks.featurize(may, field_mask(chip), fit(chip))
    assert field_may is None                                            # every field window touches a NaN


def test_invalid_field_pixel_gives_null_field_but_a_chip_vector(tmp_path):
    point = {**RECORD, "geometry": {"type": "Point", "coordinates": [33.3837, -13.3171]}}
    record_dir, touched = make_record_dir(tmp_path, point, aoi_type="point_pixel")
    write_scene(record_dir, "S2A_T36LWL_20230312T080000_L2A", "2023-03-12", touched, touched, invalid=[(2, 2)])
    add_scenes(record_dir, ["S2A_T36LWL_20230312T080000_L2A"])
    chip = read_chip(record_dir)
    assert field_mask(chip).sum() == 1
    chip_vec, field_vec = mosaiks.featurize(chip.scenes[0], field_mask(chip), fit(chip))
    assert field_vec is None
    assert chip_vec is not None and np.isfinite(chip_vec).all()


def test_vectors_never_hold_nan(chip_dir):
    chip = read_chip(chip_dir)
    filters = fit(chip)
    assert np.isfinite(filters.filters).all()
    for scene in chip.scenes:
        for vector in mosaiks.featurize(scene, field_mask(chip), filters):
            assert vector is None or np.isfinite(vector).all()


def test_season_vector_is_the_mean_of_the_monthly_ones():
    a = np.array([1.0, 2.0, 3.0], dtype="float32")
    b = np.array([3.0, 2.0, 7.0], dtype="float32")
    np.testing.assert_allclose(mosaiks.season_mean([a, None, b]), [2.0, 2.0, 5.0])
    assert mosaiks.season_mean([None, None]) is None


def test_filters_survive_save_and_load(chip_dir, tmp_path):
    chip = read_chip(chip_dir)
    filters = fit(chip)
    mosaiks.save_filters(filters, tmp_path / "filters.npz")
    loaded = mosaiks.load_filters(tmp_path / "filters.npz")
    np.testing.assert_array_equal(loaded.filters, filters.filters)
    np.testing.assert_array_equal(loaded.band_std, filters.band_std)
    assert loaded.patch_size == 3


def test_whitening_gives_every_direction_the_same_variance():
    rng = np.random.default_rng(0)
    scales = np.linspace(0.05, 3.0, 90)                     # very unequal variance per direction
    patches = (rng.normal(size=(5000, 90)) * scales).reshape(5000, 10, 3, 3)
    flat = mosaiks.whiten_patches(patches, epsilon=1e-9).reshape(5000, -1).astype("float64")
    eigenvalues = np.linalg.eigvalsh(flat.T @ flat / len(flat))
    kept = eigenvalues[eigenvalues > 1e-3]                  # centring each patch removes one direction
    assert len(kept) == 89 and np.allclose(kept, 1.0, atol=1e-3)


def test_standardise_sets_nan_to_the_band_mean():
    image = np.full((2, 3, 3), np.nan, dtype="float32")
    image[0, 0, 0], image[1, 1, 1] = 5.0, 1.0
    z = mosaiks.standardise(image, np.array([3.0, 1.0], dtype="float32"), np.array([2.0, 1.0], dtype="float32"))
    assert z[0, 0, 0] == pytest.approx(1.0) and z[1, 1, 1] == pytest.approx(0.0)
    assert np.isfinite(z).all() and (z[0, 1:] == 0).all()
