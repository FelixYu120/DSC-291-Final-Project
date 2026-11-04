# Reviewed data variant: Kenya dates, locations and clouds

Read the [executed notebook walkthrough](../notebooks/data_quality_review.ipynb) for step-by-step
explanations, pixel-selection diagrams, recorded results, optional local checks and reproduction commands.
It runs without the database or image archive using committed aggregate evidence; detailed derivatives stay local.

This work on `felix-branch` prepares a separate dataset. The original database, provider files,
frozen labels and spatial splits remain unchanged. No model is trained or scored. The variant is a
documented sensitivity dataset; it has not replaced the team's frozen inputs.

## What was fixed, and what remains uncertain

### Kenya dates

Every Kenya record was linked back to its exact row in the provider workbook. All supplied dates were
typed Excel dates, and the audit agreed with them. The 89 missing harvest dates are genuinely blank
source cells, so no missing date could be recovered from a parsing correction.

For the derived date columns:

- Five planting years outside the declared season range become NULL. The valid harvest date stays.
- Eight records have ambiguous reversed planting/harvest order. Both dates become NULL for timing use.
- Original dates stay in the review evidence and in `original_*` columns of the assembled variant.
- All 3,977 yields and coordinates remain unchanged. Late harvests are retained and flagged, rather
  than moved into the fixed satellite window by guessing another date.

NULL means unknown. It does not mean that a true date was corrected or discovered. Other cohorts'
dates have not been corrected by this Kenya-specific review.

### Repeated Kenya coordinates

203 observations form 95 exact-coordinate groups, giving 133 pairs. Every pair has distinct source
IDs and different yields, but the same complete monthly satellite series. No identical source-record
payload was found after ignoring the identifier. These records cannot safely be deleted as duplicates
or assigned to different fields from the satellite values alone.

The review retains all observations and adds stable exact/near-coordinate group IDs. There are 560
records in 253 near-10 m groups and 450 nearby pairs. All pairs already share their frozen spatial
group and fold. Of the nearby pairs, 46 span years; no exact-coordinate pair spans years.

An especially important source clarification: Kenya's `plot_acres` can describe all land of a crop
and field type, rather than the individually sampled field. Coordinates may be homestead or nearby
locations. Therefore, `field_area_ha` in the frozen table must not be treated as a verified outline
area. Evidence: the OAF workbook's `Description!B2`, `Variables!C40:C41`, and `Variables!C75:C76`.

### Actual satellite cloud screening

The review inspected public SCL classification pixels for **all 1,307 frozen scene IDs and all
84,967 accepted field-months**, across active, excluded and parked observations. It fetched scene
metadata and small SCL windows, not the full reflectance archive. There were zero failed scene reads.
The SCL/mask cache is approximately 267 MB; the derived tables approximately 18 MB.

The declared strict policy keeps only vegetation/bare-land SCL classes 4/5, excludes cloud/shadow
classes 3/8/9/10 and adds a **60 m buffer**. Unknown classification/nodata near the field remains
unverified. Every touched field pixel must pass. This also excludes water and other non-land classes;
it is a conservative quality variant, not a cloud-only or universally optimal rule.

The mask is sampled onto the original chip grid with a context halo, and reconstructed field-pixel
counts are checked against the frozen metadata. Native SCL resolution remains 20 m; sampling at 10 m
does not improve it. [Copernicus documents the classification and its processing](https://sentiwiki.copernicus.eu/web/s2-processing),
and [provides examples of buffered SCL masking](https://documentation.dataspace.copernicus.eu/APIs/openEO/openeo-community-examples/python/30_openeo-processing/scl-dilation-mask/scl-dilation-mask.html).
The 60 m threshold is this project's conservative choice, not an assurance that all cloud is removed.

**82,381 field-months remain; 2,586 are withheld.** Of the withheld months, 1,288 have uncertain SCL
context. Direct cloud/shadow pixels touch 82 field-month AOIs; a buffered cloud/shadow area touches
1,703. These reasons overlap and must not be added. Not every withheld month is a confirmed cloud.

| Active cohort | Eligible labels retained | At least 4 original months | At least 4 strict months |
|---|---:|---:|---:|
| Kenya | 3,977 | 3,977 | 3,972 |
| Malawi 2023 | 260 | 251 | 206 |
| Lacuna 2023 | 1,880 | 1,880 | 1,873 |
| Total | 6,117 | 6,108 | 6,051 |

Rejected monthly bands become NULL, never zero. Retained numeric reflectance values exactly match
the originals. Seasonal indices are recomputed using the remaining months. Partly
cloudy polygon medians are not reconstructed: that would require the original reflectance pixels.
The old Presto/MOSAIKS embeddings are not included in the assembled variant because they still
represent the original imagery selection. SCL may miss thin cloud or haze; a passing mask is not a
visual certification. An independent [Cloud Score+ layer](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED)
is a useful follow-up where Earth Engine access is available.

## Matching a point to an area

Three candidate extraction supports were generated around each eligible Kenya/Lacuna point: circles
of radius 10, 20 and 30 m. They are explicitly named `unvalidated_support_candidates`, never field
boundaries. Kenya's reported acreage is not used to size them. No point is snapped or moved.

The geometry experiment uses all 260 Malawi walked polygons, their stored representative points, and
synthetic offsets of 0, 10, 20 and 30 m in four directions. Directions are averaged within a field
before field-level summaries. These offsets are assumptions for sensitivity analysis, not measured
GPS errors. The unshifted points come from the polygons, so this is optimistic compared with homestead
coordinates.

For a 20 m-radius support, the median fraction inside the known Malawi field is approximately 100%
without an offset, but it covers only 21% of the field. With a 30 m offset, the median inside fraction
falls to 72%. For a 30 m-radius support at a 30 m offset, it falls to 64%. A larger support can include
neighboring land; it does not repair a wrong location.

[FTW Global second-edition predictions](https://source.coop/ftw/global-data-2e) offer same-year candidate
boundaries for 2017–2025 under CC BY 4.0. They are model estimates, with weaker smallholder performance,
uncalibrated scores, early-year imagery gaps and a minimum polygon size of 900 m². The matching tool
retrieves candidate polygons, distinguishes ambiguity and measures overlap with Malawi outlines.
It never turns the nearest candidate into a confirmed field or chooses polygons using yield.
Annual predictions may contain post-harvest information; they do not establish forecast-time availability.

The actual same-year search was completed for all 203 repeated-coordinate Kenya records and 260
Malawi polygons. None of those Kenya records had a candidate within 30 m; Malawi had candidates for
only four records. Their best polygon-overlap scores (IoU) were 0.141, 0, 0.557 and 0.067. Regional
source coverage and the coordinate/geometry handling were independently checked. This does not
support replacing our field geometry with this product. An absent prediction does not establish
that a field is absent or its GPS is wrong.

Public GeoParquet files are read by HTTP byte ranges and filtered locally. The coordinates and SQL
predicates are not sent to a spatial-query service; see [DuckDB's HTTP documentation](https://www.duckdb.org/docs/1.5/core_extensions/httpfs/https).
Full-zone downloads are unnecessary. Source: Fields of The World / Taylor Geospatial, `global-data-2e`,
CC BY 4.0. Candidate geometries retain their source/year/score and remain separate from observed labels.

## The four opening problems in the data guide

| Problem | Current response | Further evidence needed |
|---|---|---|
| Yield measurements differ | Preserve source yields, units and each cohort's cut protocol; no guessed cross-cohort correction | Malawi's 75/100 m² ambiguity; Lacuna's grain/cob and moisture definitions |
| Points are not outlines | Source-coordinate audit, explicit duplicate-location groups, labelled proxy supports and same-year boundary candidates | Provider-linked outlines/GPS accuracy; validated candidate matching, especially at homesteads |
| Clouds leave gaps | Completed actual SCL screening; separate strict monthly tables; explicit unknowns and missing months | Independent cloud scores/visual checks; additional valid scenes or composites to recover coverage, especially Malawi |
| Nearby fields look alike | Preserve frozen groups and keep every near-coordinate pair together; identical imagery is recorded as dependence | Continue to evaluate new-location claims with spatial separation, not random rows; do not invent independent sample locations |

## Commands and output organization

Run from the repository root with the existing environment:

```bash
python scripts/review_kenya_records.py
python scripts/review_clouds.py plan
python scripts/review_clouds.py review --scope all-retained --workers 8
python scripts/review_point_areas.py
python scripts/review_boundary_candidates.py --per-cohort-limit 2 --max-seconds 180
```

Use `--per-cohort-limit 0` for all 260 Malawi records and 203 repeated-coordinate Kenya records.
The pilot default is two records per country/year. Query errors/time limits remain explicitly
unevaluated; an empty candidate result never proves that no field exists.

To assemble a complete local variant, use the exact directories printed by the completed reviews:

```bash
python scripts/assemble_quality_variant.py \
  --kenya <kenya-review-directory>/KEN \
  --clouds <completed-all-retained-cloud-directory> \
  --point-areas <point-area-review-directory> \
  --output data/runs/quality_variant/my-reviewed-copy
```

Optional `--boundaries <boundary-review-directory>` adds the candidate review summary. Every output
directory must be new. Existing data are not overwritten. Each country/cohort folder contains
`labels_reviewed.parquet`, `cleaned_monthly_bands.parquet`, `clean_season_indices.parquet` and
`field_coverage.parquet`. Kenya also includes the date and coordinate evidence CSVs. The root HTML
report explains the variant. Detailed results stay local under ignored `data/runs/`.

In reviewed labels, `plant_date`, `harvest_date` and `obs_date` use the derived Kenya decisions;
`original_*` columns preserve their source values. Old date flags are renamed `original_*` to avoid
presenting them as checks of the revised dates. `include_primary` remains the original eligibility
decision; `core_usable_under_strict_cloud_rule` separately records the new imagery support.

The full cloud run used source commit `2d8f2e3`. Subsequent formatting-only changes are documented
in its separate provenance note; the exact run source and every mask/output hash are retained.

The [recorded review summary](../results/quality_remediation/summary.json) contains aggregate evidence
and validation. The assembled local report is `data/runs/quality_variant/felix-reviewed-v1/report.html`.
