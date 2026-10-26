"""Cohorts: which screened audit rows form one labelled cohort, and its fixed season window.

A cohort is one audit dataset restricted to the years, country and management filter in
docs/STRUCTURE.md. Rows keep every source column so each observation can be traced back to
the provider file through ``dataset``, ``source_id`` and ``source_row``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from cropyield import ROOT

AUDIT_DIR = ROOT / "data" / "audit"


@dataclass(frozen=True)
class Cohort:
    name: str
    dataset: str                      # audit dataset: data/audit/<dataset>_screened_candidates.csv
    years: tuple[int, ...]            # audit ``year`` column (harvest year)
    country: str
    season_start: tuple[int, int]     # (month, day) of the fixed window start
    season_end: tuple[int, int]       # (month, day) of the fixed window end, in the harvest year
    start_year_offset: int            # -1 when the window starts in the previous calendar year
    intercropping: str | None = None  # audit ``intercropping`` value to keep, None keeps all


# Windows are fixed per agro-zone (docs/DECISIONS.md 2026-10-25) and never anchored on a
# row's crop-cut date. Kenya: 1 Feb - 30 Sep of the year. Malawi, Zimbabwe: 1 Oct - 30 Jun.
COHORTS: dict[str, Cohort] = {
    "malawi_2022": Cohort("malawi_2022", "malawi_2022", (2022,), "malawi", (10, 1), (6, 30), -1),
    "malawi_2023": Cohort("malawi_2023", "malawi_2023", (2023,), "malawi", (10, 1), (6, 30), -1),
    "kenya_oaf_2019_2020": Cohort("kenya_oaf_2019_2020", "one_acre_fund_full", (2019, 2020),
                                  "kenya", (2, 1), (9, 30), 0, intercropping="0"),
    "zimbabwe_lacuna_2022_2023": Cohort("zimbabwe_lacuna_2022_2023", "zimbabwe", (2022, 2023),
                                        "zimbabwe", (10, 1), (6, 30), -1),
    "zimbabwe_2024": Cohort("zimbabwe_2024", "vision_guided_yield_estimation", (2024,),
                            "zimbabwe", (10, 1), (6, 30), -1),
}


def season_window(cohort: Cohort, year: int) -> tuple[date, date]:
    """Fixed season window (inclusive dates) for one harvest year of a cohort."""
    start = date(year + cohort.start_year_offset, *cohort.season_start)
    end = date(year, *cohort.season_end)
    if start >= end:
        raise ValueError(f"{cohort.name}: window start {start} is not before end {end}")
    return start, end


def obs_id(dataset: str, source_id: str) -> str:
    """Stable observation id: the audit's unique (dataset, source_id) pair, joined by ':'."""
    return f"{dataset}:{source_id}"


def load_cohort(name: str, audit_dir: Path = AUDIT_DIR) -> pd.DataFrame:
    """Load one cohort from its screened audit CSV, in file order, one row per observation.

    Adds ``obs_id`` (first column), ``cohort``, ``season_start`` and ``season_end``; converts
    ``year``, ``source_row``, ``longitude``, ``latitude`` and ``yield_kg_ha`` to numbers and
    leaves every other source column as text so nothing from the audit row is lost.
    """
    cohort = COHORTS[name]
    path = audit_dir / f"{cohort.dataset}_screened_candidates.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    keep = (
        (df["dataset"] == cohort.dataset)
        & df["year"].astype(int).isin(cohort.years)
        & (df["country"].str.lower() == cohort.country)
        & (df["crop"].str.lower() == "maize")
        & (df["passes_yield_and_known_location_checks"].str.lower() == "true")
    )
    if cohort.intercropping is not None:
        keep &= df["intercropping"] == cohort.intercropping
    df = df.loc[keep].copy()
    df.insert(0, "obs_id", [obs_id(d, s) for d, s in zip(df["dataset"], df["source_id"])])
    if df["obs_id"].duplicated().any() or (df["source_id"] == "").any():
        raise ValueError(f"{name}: missing or duplicate source_id in {path.name}")
    df["year"] = df["year"].astype(int)
    df["source_row"] = df["source_row"].astype(int)
    for column in ("longitude", "latitude", "yield_kg_ha"):
        df[column] = df[column].astype(float)
    df["cohort"] = name
    windows = [season_window(cohort, int(y)) for y in df["year"]]
    df["season_start"] = [w[0].isoformat() for w in windows]
    df["season_end"] = [w[1].isoformat() for w in windows]
    return df.reset_index(drop=True)


def date_overrides(cohort_rows: pd.DataFrame) -> pd.DataFrame:
    """Rows for ``download_sentinel2.py --date-overrides``: the fixed cohort window per record."""
    out = cohort_rows[["dataset", "source_id", "season_start", "season_end"]].copy()
    return out.rename(columns={"season_start": "start_date", "season_end": "end_date"}).reset_index(drop=True)
