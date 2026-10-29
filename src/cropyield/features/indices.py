"""Vegetation indices from one monthly Sentinel-2 series.

The five indices of Lobell et al. (2020), Table 2, computed month by month from the median
field reflectance in ``MonthlySeries``. Sentinel-2 bands: B03 green, B04 red, B05 red edge
(705 nm), B06 red edge (740 nm), B08 near infrared (NIR).

    NDVI    = (B08 - B04) / (B08 + B04)
    GCVI    =  B08 / B03 - 1
    MTCI    = (B08 - B05) / (B05 - B04)
    NDVI705 = (B08 - B05) / (B08 + B05)
    NDVI740 = (B08 - B06) / (B08 + B06)

Lobell, D. B., Azzari, G., Burke, M., Gourlay, S., Jin, Z., Kilic, T., Murray, S. (2020).
Eyes in the sky, boots on the ground: assessing satellite- and ground-based approaches to crop
yield measurement and analysis. American Journal of Agricultural Economics, 102(1), 202-219.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from cropyield.satellite.monthly import MonthlySeries

INDICES = ("ndvi", "gcvi", "mtci", "ndvi705", "ndvi740")


def vegetation_indices(series: MonthlySeries) -> pd.DataFrame:
    """Lobell et al. (2020) Table 2 indices per month: rows are the series' months, NaN where missing.

    A zero denominator (for example B05 == B04 in MTCI) gives NaN too, never infinity.
    """
    b = {code: series.band(code).astype("float64") for code in series.bands}
    with np.errstate(divide="ignore", invalid="ignore"):
        indices = pd.DataFrame({
            "ndvi": (b["B08"] - b["B04"]) / (b["B08"] + b["B04"]),
            "gcvi": b["B08"] / b["B03"] - 1,
            "mtci": (b["B08"] - b["B05"]) / (b["B05"] - b["B04"]),
            "ndvi705": (b["B08"] - b["B05"]) / (b["B08"] + b["B05"]),
            "ndvi740": (b["B08"] - b["B06"]) / (b["B08"] + b["B06"]),
        }, index=pd.Index(series.months, name="month"))
    return indices.replace([np.inf, -np.inf], np.nan)
