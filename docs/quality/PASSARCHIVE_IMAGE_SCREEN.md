# Passarchive image quality screen (experimental)

Run from the repository root:

```powershell
python scripts/quality/select_passarchive_imagery.py `
  --database 'D:\存储\UCSD\课程\DSC-190\Final project\passarchive_v1.duckdb' `
  --output 'D:\存储\UCSD\课程\DSC-190\Final project\image_quality_screen'
```

The output must be a new directory. `--limit-fields 100` runs a small pilot.
For Allen's maize comparison across growing seasons that cross calendar years,
add `--window-kind both --crop maize`; see the executed
[`allen_median3_cleaning.ipynb`](../../notebooks/allen_median3_cleaning.ipynb).
The source DuckDB is read-only. Three files are produced:

- `scene_decisions.parquet`: one sampled L2A candidate per field and scene,
  with `keep`, `review`, or `reject`, a reason, local clear fraction, crop
  timing flag, and point/polygon support flag.
- `monthly_top15.parquet`: up to 15 eligible scenes per field and calendar
  month, with `quality_rank` (1 is best), `quality_score`, spectral bands,
  provenance, `eligible_scenes_in_month`, `unique_overflights_in_month`, and
  `same_overflight_rank`. Independent overflights rank first; additional
  clear scenes from the same overflight may fill the remaining slots.
- `monthly_coverage.parquet`: every current-window field-month, including
  those with zero selected scenes; counts and `shortfall_to_target` are shown.
- `summary.json`: scope, counts, parameters, and limitations.

The screen uses no yield values. It rejects invalid/missing model bands and
locally obstructed point observations. Polygon clarity is measured with
individual 20 m SCL pixels inside the stored field footprint; a summary SCL
class is insufficient. A polygon needs at least 80% clear SCL pixels by
default. Water and unclassified point pixels, high local cloud probability,
and low sun elevation are sent for review. Scene-wide cloud cover is only a
tie-breaker. SCL vegetation and bare soil are both valid optical classes.

The top-15 table contains only `keep` observations within recorded crop
dates or with incomplete dates. It never fills a shortage with rejected or
review observations. The provisional score (maximum 100) weights local clear
fraction 50, local cloud probability 25, whole-scene cloud cover 10,
recorded timing 10, and sun elevation 5. Missing cloud/sun metadata gets
a neutral half-credit, not a perfect score. The best scene from each
overflight ranks ahead of extra same-overflight scenes. Those extra scenes
remain distinguishable with `same_overflight_rank > 1`. The score weights
are a starting policy, not fitted to yield labels. Use `--top-k` to change
the cap.

Because source dates are not all independently verified, the timing rule
must be reviewed per dataset before final modeling. The current run includes
all crops; for the maize task filter `crop = 'maize'` after reading the output.

This screen does **not** verify that a GPS point is centered in its field,
classify other crops/trees/roads in a pixel, examine neighboring cloud
shadows, or validate the entire season's phenological coverage. These need
field boundaries, additional imagery or a separate sequence-level audit.
It scores sampled current-window scenes only; use `coverage_months` in the
source database to examine months without a sampled scene. Do not use its
output as a final cleaned training set without those checks and a fixed,
label-free policy. It does not modify source labels, splits or imagery.
