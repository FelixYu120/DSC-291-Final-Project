"""Assemble a separate reviewed dataset and readable report; never modify the source database.

Inputs are completed Kenya, cloud and point-area review directories printed by their scripts.
All source observations survive. Only derived Kenya dates and monthly imagery availability change.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cropyield.data.kenya_review import date_proposal
from cropyield.data.labels import LABELS_PATH, sha256
from cropyield.data.quality import CORE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kenya", type=Path, required=True, help="KEN folder containing record_review.parquet")
    parser.add_argument("--clouds", type=Path, required=True, help="Completed all-retained cloud review folder")
    parser.add_argument("--point-areas", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, help="Optional completed FTW candidate review folder")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output must be a new directory; no previous variant is overwritten.")
    cloud_run = json.loads((args.clouds / "run.json").read_text())
    if not cloud_run["scope_complete"] or cloud_run["scope"] != "all-retained":
        parser.error("A completed all-retained cloud review is required; unreviewed scenes cannot be declared clear.")
    kenya_summary = json.loads((args.kenya / "summary.json").read_text())
    kenya_provenance = json.loads((args.kenya / "provenance.json").read_text())
    point_summary = json.loads((args.point_areas / "summary.json").read_text())
    original_hash = sha256(LABELS_PATH)
    if (original_hash != kenya_provenance["protected_sha256_before"]["data/processed/labels_v1.parquet"]
            or original_hash != point_summary["labels_sha256"]):
        raise ValueError("Review inputs do not refer to the current frozen labels")
    cloud_label_hashes = [value for name, value in cloud_run["input_sha256"].items()
                         if Path(name).name == "labels_v1.parquet"]
    if cloud_label_hashes != [original_hash]:
        raise ValueError("Cloud review does not refer to the current frozen labels")
    for name in ("record_review.parquet", "date_review.csv", "coordinate_pairs.csv", "summary.json"):
        if sha256(args.kenya / name) != kenya_provenance["derived_output_sha256"].get(name):
            raise ValueError(f"Kenya review fingerprint mismatch: {name}")
    for name, digest in cloud_run["output_sha256"].items():
        if sha256(args.clouds / name) != digest:
            raise ValueError(f"Cloud derivative fingerprint mismatch: {name}")
    labels = pd.read_parquet(LABELS_PATH)
    original = labels.set_index("obs_id")
    reviewed = labels.copy().set_index("obs_id")
    for column in ("plant_date", "harvest_date", "obs_date"):
        reviewed["original_" + column] = reviewed[column]
    reviewed["date_review_decision"] = "not_reviewed_for_this_cohort"
    reviewed["exact_coordinate_group_id"] = ""
    reviewed["coordinate_review_group_id"] = ""
    reviewed["location_scope_review"] = "source_location_unchanged"
    reviewed["area_scope_review"] = "source_area_unchanged"
    kenya = pd.read_parquet(args.kenya / "record_review.parquet").set_index("obs_id")
    expected_kenya = set(original.index[original.cohort.eq("kenya_oaf_2019_2020")])
    if not kenya.index.is_unique or set(kenya.index) != expected_kenya:
        raise ValueError("Kenya review keys do not match frozen cohort")
    for field in ("yield_kg_ha", "lat", "lon"):
        if not np.array_equal(original.loc[kenya.index, field], kenya[field]):
            raise ValueError(f"Kenya review changed original {field}")
    for field in ("plant_date", "harvest_date"):
        same = original.loc[kenya.index, field].eq(kenya[field]) | (original.loc[kenya.index, field].isna() & kenya[field].isna())
        if not same.all():
            raise ValueError(f"Kenya review changed original {field}")
    for row in kenya.itertuples():
        source = original.loc[row.Index]
        plant, harvest, decision = date_proposal(source.plant_date, source.harvest_date, int(source.season_year))
        for actual, expected in ((row.proposed_plant_date, plant), (row.proposed_harvest_date, harvest),
                                 (row.proposed_obs_date, harvest)):
            if not ((pd.isna(actual) and pd.isna(expected)) or actual == expected):
                raise ValueError("Kenya proposed dates do not match the source-backed quarantine rules")
        if row.date_decision != decision:
            raise ValueError("Kenya date decision does not match the source-backed quarantine rules")
    for destination, source in (("plant_date", "proposed_plant_date"), ("harvest_date", "proposed_harvest_date"),
                                 ("obs_date", "proposed_obs_date"), ("date_review_decision", "date_decision"),
                                 ("exact_coordinate_group_id", "exact_coordinate_group_id"),
                                 ("coordinate_review_group_id", "coordinate_group_id"),
                                 ("location_scope_review", "location_scope"), ("area_scope_review", "area_scope")):
        reviewed.loc[kenya.index, destination] = kenya[source]
    fields = pd.read_parquet(args.clouds / "field_coverage.parquet").set_index("obs_id")
    if not fields.index.is_unique or set(fields.index) != set(original.index):
        raise ValueError("Cloud coverage does not retain every source observation")
    reviewed = reviewed.join(fields[["original_months_with_data", "retained_months", "retains_four_months"]],
                             validate="one_to_one")
    reviewed["core_usable_under_strict_cloud_rule"] = (reviewed.cohort.isin(CORE)
        & reviewed.include_primary & reviewed.retains_four_months)
    # Existing flags remain source flags; new date columns do not silently rewrite their evidence.
    reviewed = reviewed.rename(columns={"impossible_date": "original_impossible_date",
                                       "date_outside_window": "original_date_outside_window"})
    unchanged = ["yield_kg_ha", "lat", "lon", "geometry_wkt", "include_primary", "exclusion_reason", "cluster_2km"]
    pd.testing.assert_frame_equal(reviewed[unchanged], original[unchanged])
    if sha256(LABELS_PATH) != original_hash:
        raise ValueError("Protected labels changed during assembly")
    args.output.mkdir(parents=True)
    reviewed.reset_index().to_parquet(args.output / "labels_reviewed.parquet", index=False)
    for (country, cohort), rows in reviewed.groupby(["country_iso3", "cohort"]):
        destination = args.output / country / cohort
        destination.mkdir(parents=True)
        rows.reset_index().to_parquet(destination / "labels_reviewed.parquet", index=False)
        for filename in ("cleaned_monthly_bands.parquet", "clean_season_indices.parquet", "field_coverage.parquet"):
            shutil.copy2(args.clouds / country / cohort / filename, destination / filename)
    for name in ("date_review.csv", "coordinate_pairs.csv"):
        shutil.copy2(args.kenya / name, args.output / "KEN/kenya_oaf_2019_2020" / name)
    core = reviewed[reviewed.cohort.isin(CORE) & reviewed.include_primary]
    counts = core.groupby("cohort").agg(eligible=("cohort", "size"),
        before=("original_months_with_data", lambda x: int(x.ge(4).sum())), after=("retains_four_months", "sum"))
    buffer_m = cloud_run["policy"]["buffer_metres"]
    summary = {"variant": f"kenya_date_review_and_strict_scl{buffer_m:g}m_v1", "original_labels_sha256": original_hash,
               "source_observations": len(original), "retained_observations": len(reviewed),
               "original_measurements_coordinates_and_eligibility_unchanged": True,
               "no_models_trained_or_scored": True, "core_coverage": counts.reset_index().to_dict("records"),
               "assembly_source_sha256": sha256(Path(__file__)),
               "cloud_run_manifest_sha256": sha256(args.clouds / "run.json"),
               "kenya_provenance_sha256": sha256(args.kenya / "provenance.json"),
               "kenya": kenya_summary, "cloud_policy": cloud_run["policy"],
               "cloud_totals": {k: cloud_run[k] for k in ("unique_scenes", "reviewed_field_months", "kept_field_months",
                                                          "unverified_field_months", "unreviewed_field_months")},
               "point_area_validation": point_summary["validation"],
               "inputs": {"kenya": str(args.kenya), "clouds": str(args.clouds), "point_areas": str(args.point_areas)},
               "notes": ["Derived Kenya date columns use reviewed values; original_* columns retain source dates.",
                         "Quarantined dates are unknown; no true replacement dates were recovered.",
                         "Other cohorts' dates were not corrected by the Kenya review.",
                         "NULL monthly bands mean withheld or missing; no values are imputed.",
                         "Old Presto/MOSAIKS embeddings are not included because their cloud masks have not been rebuilt.",
                         "Point buffers and FTW polygons remain separate unvalidated candidates.",
                         "Frozen labels, database, source measurements and spatial splits are unchanged."]}
    boundary_text = ""
    if args.boundaries:
        summary["boundary_review"] = json.loads((args.boundaries / "summary.json").read_text())
        evidence_counts = []
        for country, cohort in (("KEN", "kenya_oaf_2019_2020"), ("MWI", "malawi_2023")):
            source = args.boundaries / country
            matches = pd.read_csv(source / "observation_review.csv")
            count = int(matches.candidate_count.fillna(0).gt(0).sum())
            evidence_counts.append({"country": country, "observations": len(matches), "with_candidate": count})
            destination = args.output / country / cohort
            shutil.copy2(source / "observation_review.csv", destination / "boundary_candidate_review.csv")
            for name in ("candidate_matches.csv", "predicted_boundaries.parquet"):
                if (source / name).exists():
                    shutil.copy2(source / name, destination / name)
        summary["boundary_match_coverage"] = evidence_counts
        boundary_text = '<p>Same-year FTW lookup within 30 m: ' + '; '.join(
            f"{r['country']}: {r['with_candidate']} of {r['observations']} observations with a candidate"
            for r in evidence_counts) + '. These are predicted candidates, not confirmed field matches. No coordinates or outlines were replaced.</p>'
    summary["output_sha256"] = {p.relative_to(args.output).as_posix(): sha256(p) for p in args.output.rglob("*.parquet")}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    table = "".join(f"<tr><td>{escape(name)}</td><td>{r.eligible}</td><td>{r.before}</td><td>{r.after}</td></tr>"
                    for name, r in counts.iterrows())
    decisions = kenya_summary["date_decisions"]
    rejected_months = cloud_run["reviewed_field_months"] - cloud_run["kept_field_months"]
    example_image = ""
    if (args.point_areas / "proxy_overlap_examples.png").exists():
        shutil.copy2(args.point_areas / "proxy_overlap_examples.png", args.output / "point_area_example.png")
        example_image = '<img src="point_area_example.png" alt="Observed field and candidate supports under synthetic location offsets" style="width:100%">'
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>Data quality review</title><style>body{{font:16px/1.6 system-ui;max-width:1050px;margin:40px auto;padding:0 24px;color:#203038}}
    table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:10px;text-align:left}}th{{background:#eaf3ef}}
    .note{{padding:18px;background:#fff4d9;border-left:4px solid #b57b13}}a{{color:#176346}}</style><main>
    <h1>Data quality review</h1><p class="note">Separate reviewed variant on felix-branch. All {len(reviewed):,} observations remain.
    Original yields, coordinates, source files and spatial splits are unchanged. No training was run.</p>
    <h2>Kenya dates and repeated coordinates</h2><p>{decisions.get('quarantine_plant_year_outside_season_range', 0)} planting dates
    with impossible years are now unknown in the derived date columns;
    {decisions.get('quarantine_both_ambiguous_date_order', 0)} ambiguous reversed pairs have both dates marked unknown.
    The original dates remain alongside them. {kenya_summary['original_missing_harvest_dates']} harvest dates were missing;
    {kenya_summary['dates_recovered_from_source']} records had a date recoverable from the original workbook.</p>
    <p>{kenya_summary['exact_coordinate_observations']} records form {kenya_summary['exact_coordinate_groups']} repeated-coordinate groups.
    All {kenya_summary['exact_pairs']} exact-coordinate pairs have different yields and IDs, but identical monthly
    imagery. They remain separate records with explicit grouping and review evidence. No point was moved.</p>
    <p><a href="KEN/kenya_oaf_2019_2020/date_review.csv">Inspect Kenya date evidence</a> ·
    <a href="KEN/kenya_oaf_2019_2020/coordinate_pairs.csv">Inspect coordinate pairs</a></p>
    <h2>Satellite cloud screening</h2><p>All {cloud_run['unique_scenes']:,} frozen scenes and
    {cloud_run['reviewed_field_months']:,} accepted field-months were checked using actual SCL pixels.
    The strict land-only rule with a {buffer_m:g} m cloud/shadow/context buffer retains {cloud_run['kept_field_months']:,} months
    and withholds {rejected_months:,}. Of these, {cloud_run['unverified_field_months']:,} have uncertain classification context.
    These are not all confirmed clouds.
    Rejected monthly bands become NULL; seasonal summaries are recomputed. SCL can miss thin clouds, so passing is not
    a guarantee of cloud-free imagery. Old embeddings are not part of this cleaned variant.</p>
    <table><tr><th>Cohort</th><th>Eligible labels</th><th>≥4 months before</th><th>≥4 strict months</th></tr>{table}</table>
    <h2>Point to area</h2><p>Kenya source coordinates may be homesteads or nearby locations. Its acreage can cover several fields
    of one crop/type, so it cannot establish an individual field outline. Fixed 10/20/30 m circles were created only as
    extraction-support candidates. Validation against 260 Malawi polygons tests their geometric contamination under declared
    offsets; it does not establish Kenya GPS accuracy or identify a true field. FTW predictions require separate review.</p>
    {boundary_text}
    {example_image}
    <h2>The four problems in the guide</h2><table><tr><th>Problem</th><th>Action and remaining limitation</th></tr>
    <tr><td>Different yield measurements</td><td>Keep each cohort's original definition and units/protocol metadata.
    Obtain provider clarification for Malawi cut area and Lacuna product/moisture conventions; no guessed conversion.</td></tr>
    <tr><td>Points instead of boundaries</td><td>Use observed polygons where available. Keep proxy areas and same-year predicted
    boundaries as labelled candidates; validate them before changing extraction areas.</td></tr>
    <tr><td>Clouds and missing months</td><td>Actual pixel-based cloud screening now produces a separate strict dataset.
    Missing months stay missing. More scene dates or independent cloud scoring can recover or validate coverage later.</td></tr>
    <tr><td>Nearby fields share information</td><td>All {kenya_summary['near_10m_pairs']} Kenya near-coordinate pairs already share their frozen spatial group/fold.
    Preserve those assignments and flag co-located observations; do not count them as independent locations.</td></tr></table>
    <h2>Files</h2><p>Each country/cohort folder holds reviewed labels, cleaned monthly bands, seasonal indices and coverage.
    <a href="summary.json">Summary and output fingerprints</a> · <a href="labels_reviewed.parquet">All reviewed labels</a></p>
    <p>Data preparation only. This variant has not replaced the team's frozen dataset.</p></main></html>"""
    (args.output / "report.html").write_text(html, encoding="utf-8")
    print(f"Reviewed data and report: {args.output}")
    print(counts.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
