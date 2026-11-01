"""MOSAIKS random convolutional features of one Sentinel-2 scene.

MOSAIKS (Rolf et al. 2021, Nature Communications 12:4392, Methods "Implementation of MOSAIKS")
turns an image into K numbers with random filters: the filters are small patches cut from the
images themselves, and each number is the average response of the image to one filter. Code of
the paper: github.com/Global-Policy-Lab/mosaiks-paper, code/mosaiks/featurization.py
(grab_patches, normalize_patches, BasicCoatesNgNet) and config.py (features["random"]).

Kept from the paper and its code
    * filters are random 3 x 3 patches cut from random places of random images
      (paper: M = 3; grab_patches)
    * each patch is centred, scaled to unit length, and the set is ZCA-whitened with 1e-3
      added to the eigenvalues (normalize_patches; config filter_scale); the paper's code
      whitens the patches only, not the images
    * for each filter w: ReLU(x * w - b) and ReLU(-(x * w) - b), so K = 2P features
      (BasicCoatesNgNet); b = 1 as in the paper text (the config file sets 0)
    * one feature = the mean response over the whole image (paper; pool_size = image size)

Ours, for 10-band reflectance chips with cloudy pixels
    * per-band standardisation of the images with the mean and std of the fit scenes, so the
      10 bands share one scale; a NaN pixel (cloudy or invalid) becomes 0, the band mean
    * 'same' padding, so every response sits on its own pixel, and a response counts only
      when all s x s pixels under it are valid (a convolution of the valid mask counts them)
    * two poolings: "chip" = mean over the counted responses of the whole 64 x 64 chip,
      "field" = mean over the counted responses on the labelled field pixels only;
      no counted response gives None
    * the ZCA matrix is applied once; normalize_patches multiplies by it twice
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from cropyield.longpath import filesystem_path
from cropyield.satellite.chips import Scene

ZCA_EPSILON = 1e-3  # mosaiks-paper config.py: filter_scale


@dataclass
class Filters:
    filters: np.ndarray    # (P, n_bands, s, s) float32 whitened patches
    band_mean: np.ndarray  # (n_bands,) float32, from the fit scenes
    band_std: np.ndarray   # (n_bands,) float32

    @property
    def patch_size(self) -> int:
        return int(self.filters.shape[-1])

    @property
    def k_features(self) -> int:
        return 2 * len(self.filters)


def band_statistics(images: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Mean and std of every band over all valid pixels of the images (each (n_bands, h, w))."""
    stack = np.stack(images)
    mean = np.nanmean(stack, axis=(0, 2, 3)).astype("float32")
    std = np.nanstd(stack, axis=(0, 2, 3)).astype("float32")
    return mean, np.where(std > 0, std, 1.0).astype("float32")  # a constant band must not divide by 0


def standardise(reflectance: np.ndarray, band_mean: np.ndarray, band_std: np.ndarray) -> np.ndarray:
    """Per-band z-scores of (..., n_bands, h, w); NaN becomes 0, the band mean."""
    z = (reflectance - band_mean[:, None, None]) / band_std[:, None, None]
    return np.nan_to_num(z, nan=0.0).astype("float32")


def sample_patches(images: list[np.ndarray], n_patches: int, patch_size: int, seed: int) -> np.ndarray:
    """n_patches random s x s windows, cut from random images, whose pixels are all valid."""
    rng = np.random.default_rng(seed)
    patches: list[np.ndarray] = []
    for _ in range(1000 * n_patches):  # bounded, so a set of all-cloudy images cannot loop forever
        image = images[rng.integers(len(images))]
        row = rng.integers(image.shape[1] - patch_size + 1)
        col = rng.integers(image.shape[2] - patch_size + 1)
        patch = image[:, row:row + patch_size, col:col + patch_size]
        if np.isfinite(patch).all():
            patches.append(patch)
        if len(patches) == n_patches:
            return np.stack(patches)
    raise ValueError(f"found only {len(patches)} of {n_patches} fully valid {patch_size} x {patch_size} patches")


def whiten_patches(patches: np.ndarray, epsilon: float = ZCA_EPSILON) -> np.ndarray:
    """Centre each patch, scale it to unit length, then ZCA-whiten the set (normalize_patches)."""
    flat = patches.reshape(len(patches), -1).astype("float64")
    flat -= flat.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(flat, axis=1, keepdims=True)
    flat /= np.where(norms < 1e-8, 1.0, norms)
    covariance = flat.T @ flat / len(flat)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    zca = eigenvectors @ np.diag(1.0 / np.sqrt(eigenvalues + epsilon)) @ eigenvectors.T
    return (flat @ zca).reshape(patches.shape).astype("float32")


def fit_filters(images: list[np.ndarray], n_patches: int = 512, patch_size: int = 3, seed: int = 291) -> Filters:
    """Band statistics of the images, and n_patches whitened random patches of them as filters."""
    band_mean, band_std = band_statistics(images)
    patches = standardise(sample_patches(images, n_patches, patch_size, seed), band_mean, band_std)
    return Filters(whiten_patches(patches), band_mean, band_std)


def complete_windows(valid: np.ndarray, patch_size: int) -> torch.Tensor:
    """True where all s x s pixels under a response are valid: a convolution of the mask counts them."""
    mask = torch.from_numpy(valid.astype("float32"))[None, None]
    count = F.conv2d(mask, torch.ones(1, 1, patch_size, patch_size), padding="same")[0, 0]
    return count == patch_size ** 2


def pooled(response: torch.Tensor, counted: torch.Tensor) -> np.ndarray | None:
    """Mean of the (K, h, w) responses over the counted pixels; None when none counts."""
    if not counted.any():
        return None
    return response[:, counted].mean(dim=1).numpy()


def featurize(scene: Scene, field: np.ndarray, filters: Filters,
              bias: float = 1.0) -> tuple[np.ndarray | None, np.ndarray | None]:
    """The K features of one scene pooled over the chip and over the field pixels (None when empty)."""
    x = torch.from_numpy(standardise(scene.reflectance, filters.band_mean, filters.band_std))[None]
    conv = F.conv2d(x, torch.from_numpy(filters.filters), padding="same")[0]       # (P, h, w)
    response = torch.cat([F.relu(conv - bias), F.relu(-conv - bias)])             # (K, h, w)
    counted = complete_windows(scene.valid, filters.patch_size)
    return pooled(response, counted), pooled(response, counted & torch.from_numpy(field))


def season_mean(vectors: list[np.ndarray | None]) -> np.ndarray | None:
    """Element-wise mean of the non-null monthly vectors; None when every month is null."""
    present = [v for v in vectors if v is not None]
    return np.mean(present, axis=0).astype("float32") if present else None


def save_filters(filters: Filters, path: Path) -> None:
    np.savez(filesystem_path(path), filters=filters.filters, band_mean=filters.band_mean, band_std=filters.band_std)


def load_filters(path: Path) -> Filters:
    with np.load(filesystem_path(path)) as saved:
        return Filters(saved["filters"], saved["band_mean"], saved["band_std"])
