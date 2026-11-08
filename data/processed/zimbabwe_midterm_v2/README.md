# Zimbabwe data handoff for the midterm

Scope agreed at the November 4 meeting: Zimbabwe Lacuna. This handoff covers Felix and Florian's data structure,
cleaning, quality assessment, splits, and reproducibility responsibilities. It builds on the team's existing frozen
data. It does not train a model, alter the shared database, replace frozen folds, or add other countries to training.

## Start here

From the repository root, using the project's Python environment:

```bash
python scripts/step8_build_zimbabwe_handoff.py
python -m pytest -q
```

The builder needs the original provider files, committed labels/splits, and **the pinned team database** at
`data/cropyield.duckdb`. Use the team's shared file; do not run step 6 on it. The builder verifies its complete
SHA-256 before opening it read-only. It needs no network and downloads no imagery.

Output: [`data/processed/zimbabwe_midterm_v2/`](./).
Read the generated [audit report](./audit_report.md) first.
Release v2 has the same rows and folds as release v1 (`data/processed/zimbabwe_midterm_v1/`). Only the fold
roles differ: v1 named fold 1 "validation" and folds 2–4 "train", which is not the team protocol; v2 names
folds 1–4 "cv" and fold 0 "holdout". v1 stays published unchanged for the experiments that cite it.

To verify reproduction independently without changing the release:

```bash
python scripts/step8_build_zimbabwe_handoff.py --output /tmp/zimbabwe-rebuild
```

Every output file is hashed in `manifest.json`. Same inputs/code/environment produce the same release bytes.
Re-running into the existing output directory succeeds only if every file is identical. A changed input or
implementation requires a new output directory; there is no force-overwrite option. The manifest records the base
Git commit **and actual generator/input hashes**, so uncommitted code is not misrepresented as committed code.

## What is delivered

| File | Rows | Meaning |
|---|---:|---|
| `row_audit.csv` | 2,269 | All raw maize records, original measurements, independently derived screening/eligibility, multiple exclusion reasons and imagery timing flags |
| `cleaned_labels.parquet` / `.csv` | 2,266 | Screened 2022 and 2023 labels, with the exact 44-column frozen schema; 2022 retained and explicitly excluded from primary modeling |
| `model_table.parquet` / `.csv` | 1,880 | Primary 2023 observations, `obs_id`, target `yield_t_ha`, and exactly 10 seasonal satellite predictors |
| `monthly_features.parquet` / `.csv` | 16,920 | Nine months per primary field, including missing months; ten bands, five indices, missingness and acquisition date |
| `split_s1_cc2km.csv` | 1,880 | Primary spatial split: original `fold`, and `partition` = cv (folds 1–4) or holdout (fold 0) |
| `split_s2_region.csv` | 1,880 | Separate Admin1-holdout sensitivity analysis with explicit roles |
| `monthly_coverage.csv` | Calculated | Counts by month and coverage state |
| `label_summary.csv`, `feature_quality.csv` | Calculated | Descriptive label statistics and feature missingness/ranges; no transformations fitted |
| `data_dictionary.csv` | One entry per table column | Type, observed null count and meaning, including units and unsafe predictors |
| `audit_report.md`, `audit_summary.json` | — | Human-readable findings and machine-readable counts/check results |
| `data_overview.png` | — | Inclusion counts, monthly coverage and primary split coordinates |
| `manifest.json` | — | Release config, source/code hashes, database hash, versions and output hashes |
| `README.md` | — | Copy of this guide inside the release |

Parquet preserves numeric, Boolean and date types. CSV is an inspection/interchange copy; an empty cell means missing,
not zero. Join by `obs_id`; monthly tables additionally require `month`. A monthly row is not an independent label.

## Data structure and origin

Provider: PULA Advisors, Lacuna release 1.1.1, DOI [10.5281/zenodo.10060610](https://doi.org/10.5281/zenodo.10060610),
CC BY 4.0 according to the saved provider metadata. Preserve that attribution when sharing derivatives.

The GeoJSON has 3,002 point features: 2,269 maize, 304 wheat, 217 sorghum and 212 soybean records. `Case_ID` identifies
a source observation. There is no verified farm identifier linking the same farm across years. `source_row` is the
1-based position in the GeoJSON features array; it is not a CSV line number. The GeoJSON uses longitude, latitude.

Each screened record represents one recorded maize field-season. All Zimbabwe locations are points; there are no
walked field polygons or whole-field areas. The 40 m² crop-cut area is a sampling area, not farm size.

The original source fields retained in `row_audit.csv` include planting and harvest dates, `Admin1`, intercropping,
irrigation, wet/dry crop-cut weights, yield and crop condition. Unknown management values make the new builder fail
instead of silently interpreting them as pure stand or rainfed. Original source files are never changed.

`cleaned_labels.role` still reads `second`: this is historical metadata from the frozen cross-country plan. The
November 4 meeting makes Zimbabwe the midterm focus; use the handoff configuration for that scope.

## Cleaning and harmonization rules

1. Select `Crop_Type == Maize/Corn`; preserve provider IDs and raw feature positions.
2. Parse dates without inferring missing dates. Normalize Admin1 by trimming and lowercasing; do not invent district
   equivalences for town/province names. Convert explicit yes/no management flags to Boolean values.
3. Interpret `Yield(Mt/H` as metric tonnes per hectare and multiply by 1,000 once. The provider Python manual calls
   the quantity Mg/ha. Independently verify `yield_t_ha = dry_weight_kg × 0.25`, appropriate to the declared 40 m² cut.
   Comparison tolerance is 0.001 relative / 0.001 t/ha absolute. Preserve the provisional-unit flag and missing
   moisture percentage; do not perform an unsupported moisture adjustment.
4. Screen nonfinite/negative/extreme yield, invalid weights, dry mass above wet mass, coordinates outside the legacy
   coarse envelope and inconsistent crop-cut conversion. Three maize records have `yield = dry kg × 0.5`, twice the
   expected conversion. They remain in the raw audit, excluded from cleaned labels. Their actual cut area is unknown.
5. Retain both years in cleaned labels. For the existing primary population, exclude 169 screened 2022 observations,
   then 212 intercropped 2023 rows, then 5 irrigated rows. These **sequential** counts reconcile 2,266 to 1,880.
   The raw dataset has 225 intercropped rows across both years, so 225 is not the 2023 reduction.
6. Keep the 28 primary zero yields. Keep repeated coordinates/nearby observations with their original yield; group
   them for evaluation. A location match alone does not establish a duplicate farmer or justify averaging labels.
7. Require at least four observed months and finite seasonal model features. All 1,880 current primary rows pass.
   Missing months remain explicit missing values with masks. No clipping, imputation, standardization or learned
   outlier rejection is fitted on the full dataset.

The independent reconstruction must agree with the frozen labels on IDs, yields, both coordinates, raw row positions,
dates, management, Admin1 and inclusion flags. Any disagreement stops the release rather than updating a frozen file.

## Cross-validation and the held-back fold

The release labels the existing folds, without shuffling. This is the team protocol of `docs/EVALUATION.md`:

| Existing fold | Partition | Use | Primary split rows |
|---|---|---|---:|
| 1, 2, 3, 4 | cv | Cross-validation: fit on three folds, predict the fourth, score the pooled out-of-fold predictions | 1,504 |
| 0 | holdout | Held back; only one pre-registered final test may score it | 376 |

Release v1 labelled the same folds train (2–4, 1,128 rows), validation (1, 376) and test (0, 376). A model tuned on
fold 1 alone and scored there is not comparable with the team's pooled scores over folds 1–4, so use v2.

The primary `s1_cc2km` split uses connected components at 2 km. Every pair of folds is checked to
have at least 2 km separation. This is a distance-based new-location test; components are not surveyed villages.
Use the split's **`group_id`**, not `cleaned_labels.cluster_2km`: the latter was formed using excluded observations
as well, which can connect otherwise separate retained groups.

For `s2_region`, whole normalized Admin1 groups remain together. This tests transfer across the supplied regional
labels. Admin1 mixes administrative levels and does not guarantee a distance buffer. The report gives actual minimum
separations; do not claim all cross-partition distances exceed 2 km for this family.

**Prior evaluation matters.** Historical baseline runs have already evaluated these observations. Fold 0 is not a
fresh blind test. The November 1 decision forbids scoring new model arms on fold 0 in any family. The builder labels
the partitions while retaining that restriction; it does not reset history by changing a seed.
Develop new models by cross-validation over folds 1–4, and label results appropriately. A fresh confirmatory
test needs genuinely unexamined observations or an explicitly revised team protocol, not a renamed old fold.

Fit preprocessing on the training folds of each outer fold, apply it unchanged to the predicted fold, and fit any
tuning CV preprocessing inside each inner training fold. Group inner CV by the returned `group_id`. Compare models on identical observations
and split families. Report RMSE/MAE in t/ha, bias and R², with ranking metrics as secondary results and uncertainty
resampled by spatial group. Never randomly split months of the same field across partitions.

## Model handoff example

```python
from cropyield.data.handoff import load_handoff

from pathlib import Path
import pandas as pd

release = Path("data/processed/zimbabwe_midterm_v2")
X, y, groups = load_handoff(release, partition="cv")          # folds 1-4
folds = pd.read_csv(release / "split_s1_cc2km.csv", dtype={"fold": str}).set_index("obs_id").fold.loc[X.index]
for fold in ["1", "2", "3", "4"]:
    train, test = folds.ne(fold), folds.eq(fold)
    # Fit preprocessing and model on X[train] only (grouped inner CV on groups[train]); predict X[test].
# Score the pooled out-of-fold predictions of the 1,504 fields.
```

The loader verifies output hashes and returns only the explicit predictor allowlist. Holdout (fold 0) access raises an
error by default. `allow_historical_test=True` exists solely to reproduce already permitted historical baselines; it does not
authorize scoring new arms. The files are visible research data, not an access-control system.

For Pamely's monthly sequence work:

```python
from pathlib import Path
import pandas as pd

release = Path("data/processed/zimbabwe_midterm_v2")
monthly = pd.read_parquet(release / "monthly_features.parquet")
assignment = pd.read_csv(release / "split_s1_cc2km.csv", dtype={"fold": str})
monthly = monthly.merge(assignment[["obs_id", "fold", "partition"]], on="obs_id", validate="many_to_one")
cv_monthly = monthly[monthly.partition.eq("cv")].sort_values(["obs_id", "time_index"])
# Cross-validate over cv_monthly.fold (1-4); fold 0 (holdout) stays out.
# time_index: 0=October, ..., 8=June. Retain missing masks.
# Derive per-feature finite masks as well: an index denominator can make an index missing.
# Any imputation parameters are fitted on the training folds only.
```

Yield appears once per field in `model_table`, not repeated in the exported monthly predictors. A dense sequence
representation has 9 time steps and 15 possible inputs (10 bands + 5 indices); metadata such as harvest date is not
part of that feature list. Presto requires its own band order, normalization and modality masks; do not send this
15-channel array directly to Presto.

## Methodological weaknesses to report

- **Measurement:** the numeric yield conversion is supported, but moisture percentage, grain-versus-cob basis and
  details of drying remain uncertain. A consistency check does not prove the source measurements are accurate.
- **Time:** 1,810 of 1,880 primary fields have at least one accepted scene after the recorded harvest. Full-season
  features support retrospective yield estimation. Forecasting requires a prediction cutoff and a separate feature
  build excluding information unavailable at that cutoff. Future actual harvest dates cannot define a deployed cutoff.
- **Missing imagery:** October/November 2022 are absent in this extraction. The 2022 harvest cohort has limited data
  rather than literally no imagery. Its exclusion is the frozen policy, not a claim that every archive lacks imagery.
- **Spatial support:** one GPS pixel may be displaced or contain non-maize land; no field boundaries or GPS accuracy
  estimates are available. Coarse country-envelope checks cannot verify location on a specific farm.
- **Administrative grouping:** Admin1 includes towns/province labels as well as districts. Describe grouping honestly.
- **Repeated coordinates:** preserve and group; unresolved farmer identities prevent definitive deduplication or claims
  of independent repeated-year farms. Do not count fields inside a nearby cluster as statistically independent.
- **Small regional holdout:** in `s2_region`, fold 0 contains only two Admin1 groups, and fold 1 only three.
  Group-level uncertainty is poorly determined from so few groups. Treat this single partition as a sensitivity
  check, not a precise national generalization estimate; the primary split has substantially more spatial groups.
- **Population:** the primary sample is pure-stand rainfed maize from one harvest year and selected collection sites.
  It does not establish accuracy for all Zimbabwe farms, irrigated/intercropped maize or future seasons.
- **Yield-derived fields:** dry/wet weights, source yield, crop-condition assessments and transformations of these are
  not satellite predictors. Their use would change the task and can create target or availability leakage.
- **Historical test exposure:** no fresh blind test is claimed. Keep a record of which models have used which folds.
- **Pretrained/random features:** the team database also contains Presto and MOSAIKS. The latter's filter bank was
  fitted using chips across the available population, so a strict inductive comparison must address that preprocessing
  exposure. This handoff exports deterministic spectral indices, not those embeddings.

## Existing code and data-processing pipeline

| Stage | Code | Reads → writes | Main caution |
|---|---|---|---|
| Provider retrieval | `scripts/step1_download_labels.py` | Provider URLs → `data/raw/`, `data/metadata/` | Preserve originals and checksums |
| Row audit | `scripts/step2_audit_labels.py` | Raw provider files → all-maize audit and screened CSVs | Screening is not proof of label accuracy |
| Cohort definition | `src/cropyield/data/cohorts.py` | Screened rows → fixed year/country/season selections | Cohort name includes years outside primary modeling |
| Label build | `scripts/step3_build_labels.py`, `src/cropyield/data/labels.py` | Audits + raw grouping metadata → 44-column `labels_v1.parquet` | Frozen artifact; avoid incidental rebuilds |
| Spatial splits | `scripts/step4_build_splits.py`, `src/cropyield/eval/splits.py` | Primary labels → frozen folds + manifest | Original split files never change |
| Satellite retrieval | `scripts/get_all_data.py`, `scripts/step5_download_imagery.py` | Label locations + fixed windows → Sentinel-2 chips and scene metadata | Default is a pilot; full imagery is large and stays off Git |
| Pixel/time processing | `src/cropyield/satellite/chips.py`, `monthly.py`, `records.py` | Chips + masks → field-month values | Point vs polygon support; missingness and scale/offset |
| Spectral indices | `src/cropyield/features/indices.py` | Band values → NDVI, GCVI, MTCI, NDVI705, NDVI740 | Unstable denominators; train-only clipping for learned models |
| Database build | `scripts/step6_build_database.py`, `sql/schema.sql`, `sql/views.sql` | Local artifacts → DuckDB tables/views | Do not run on shared team DB; it removes its Presto contents |
| Database access | `src/cropyield/data/database.py`, `xy.py` | Read-only DB → indexed matrices | `master` includes excluded rows unless filtered |
| Existing diagnostics | `scripts/step7_check_data.py` | DB → console summaries | Diagnostics do not authorize changing frozen inclusion |
| This handoff | `scripts/step8_build_zimbabwe_handoff.py`, `src/cropyield/data/handoff.py` | Raw + frozen labels/splits + pinned DB → verified release | Fail on mismatch, preserve evaluation history |

Database table keys: `labels`, `downloads`, `presto_embeddings`, `mosaiks_season` are observation-level;
`coverage`, `monthly_bands`, `vegetation_indices`, `mosaiks_monthly` are observation-month-level. `scenes` has one
accepted scene per observation-month in this extraction. `master` and `monthly` are SQL views. Join monthly tables
using **both** `obs_id` and `month` to avoid multiplication of rows. Modeling code under `_parked/` is historical and
is not the active data pipeline.

## Verification boundary

The release verifies file provenance, deterministic transformations, source reconciliation, partition integrity,
coverage and feature eligibility. Automated tests additionally inject corrupted values, missing IDs, unknown
management flags, spatial leakage, tampered outputs and overwrite attempts. They do not certify field measurements,
resolve provider ambiguities, confirm GPS accuracy, or prove a model generalizes. No raw observations are fabricated
and no unavailable months are interpolated by this package.
