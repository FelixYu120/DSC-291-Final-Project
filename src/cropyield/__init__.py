"""Smallholder maize-yield estimation from Sentinel-2 (DSC 291).

One subpackage per pipeline stage:
    data       cohorts, season windows, the labels table
    satellite  Sentinel-2 search, pixel reads, cloud masks, monthly composites
    features   seasonal indices
    eval       frozen splits
See docs/STRUCTURE.md and docs/ROADMAP.md.
"""
from pathlib import Path

# Repository root. The package is installed in editable mode from src/, so the
# data, configs and scripts folders are two levels above this file.
ROOT = Path(__file__).resolve().parents[2]
