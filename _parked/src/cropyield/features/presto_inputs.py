"""Presto input tensors from one monthly Sentinel-2 series.

Mirrors ``presto.dataops.utils.construct_single_presto_input`` at the pinned commit
(see cropyield.models.presto) and adds handling for missing months:

* ``x`` holds Presto's 17 normalised bands in NORMED_BANDS order. Only the ten Sentinel-2
  bands and NDVI are filled; Sentinel-1, ERA5 and SRTM are zero and masked.
* Presto normalises Sentinel-2 by dividing digital numbers by 10 000 (S2_DIVIDE_BY). Our
  reflectance.tif already equals DN / 10 000 with the Collection 1 offset (-0.1) applied by
  the downloader, so the value Presto sees is the reflectance itself and is copied unchanged.
  The -1000 / -0.1 offset must not be applied a second time.
* NDVI is computed from the normalised B8 and B4 exactly as Presto does, 0 where B8 + B4 <= 0.
* A month without a value (NaN in the series) is masked for every band, so Presto drops all
  of that month's tokens. Dynamic World is set to 9 (unknown) and is therefore ignored.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cropyield.satellite.monthly import MonthlySeries

# presto/dataops/pipelines/s1_s2_era5_srtm.py NORMED_BANDS (B1, B9, B10 removed).
NORMED_BANDS = ["VV", "VH", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12",
                "temperature_2m", "total_precipitation", "elevation", "slope", "NDVI"]
# Same file: S2_DIV_VALUES. Presto divides Sentinel-2 digital numbers by this; reflectance.tif
# is DN / S2_DIVIDE_BY already (offset applied), so it enters ``x`` unchanged.
S2_DIVIDE_BY = 10_000.0
# Presto's Encoder default max_sequence_length: the positional table has this many rows.
# Pretraining used 12-step sequences; upstream evaluates on up to 24, our seasons use 8 or 9.
PRESTO_MAX_TIMESTEPS = 24
# Downloader band codes -> Presto band names.
SENTINEL2_TO_PRESTO = {"B02": "B2", "B03": "B3", "B04": "B4", "B05": "B5", "B06": "B6",
                       "B07": "B7", "B08": "B8", "B8A": "B8A", "B11": "B11", "B12": "B12"}
# presto DynamicWorld2020_2021.class_amount: the "no class" value Presto ignores.
MISSING_DYNAMIC_WORLD = 9
NDVI = NORMED_BANDS.index("NDVI")


@dataclass
class PrestoInputs:
    obs_id: str
    months: list[str]
    x: np.ndarray              # (1, T, 17) float32, normalised, 0 where masked
    mask: np.ndarray           # (1, T, 17) float32, 1 = masked (Presto ignores the value)
    dynamic_world: np.ndarray  # (1, T) int64, all MISSING_DYNAMIC_WORLD
    latlons: np.ndarray        # (1, 2) float32 [latitude, longitude]
    month: int                 # 0-based calendar month of the first timestep (Jan = 0)


def presto_inputs(series: MonthlySeries, latitude: float, longitude: float) -> PrestoInputs:
    """Build one record's Presto inputs (batch of one) from its monthly series."""
    timesteps = len(series.months)
    if not 1 <= timesteps <= PRESTO_MAX_TIMESTEPS:
        raise ValueError(f"{series.obs_id}: {timesteps} months; Presto takes 1 to {PRESTO_MAX_TIMESTEPS}")
    if series.missing.all():
        raise ValueError(f"{series.obs_id}: no month has a value, so there is no Presto input")
    x = np.zeros((timesteps, len(NORMED_BANDS)), dtype="float32")
    mask = np.ones((timesteps, len(NORMED_BANDS)), dtype="float32")
    for code, name in SENTINEL2_TO_PRESTO.items():
        if code not in series.bands:
            continue
        column = NORMED_BANDS.index(name)
        reflectance = series.band(code).astype("float32")
        present = np.isfinite(reflectance)
        x[present, column] = reflectance[present]  # already DN / S2_DIVIDE_BY
        mask[present, column] = 0.0
    nir, red = x[:, NORMED_BANDS.index("B8")], x[:, NORMED_BANDS.index("B4")]
    both = (mask[:, NORMED_BANDS.index("B8")] == 0) & (mask[:, NORMED_BANDS.index("B4")] == 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        x[:, NDVI] = np.where((nir + red) > 0, (nir - red) / (nir + red), 0.0)
    mask[both, NDVI] = 0.0
    x[mask == 1.0] = 0.0
    if not np.isfinite(x).all():
        raise ValueError(f"{series.obs_id}: non-finite Presto input")
    return PrestoInputs(
        obs_id=series.obs_id, months=list(series.months),
        x=x[np.newaxis], mask=mask[np.newaxis],
        dynamic_world=np.full((1, timesteps), MISSING_DYNAMIC_WORLD, dtype="int64"),
        latlons=np.array([[latitude, longitude]], dtype="float32"),
        month=int(series.months[0][5:7]) - 1,
    )
