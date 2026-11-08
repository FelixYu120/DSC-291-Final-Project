"""Audit the shared database and source labels without changing them or running models.

    python scripts/audit_data_quality.py

Outputs report.html, summary.json, monthly_coverage.csv and country-specific review tables
under data/runs/data_quality/<UTC timestamp>/. Exit 1 means a deterministic check failed;
exit 0 means those checks passed, NOT that all scientific uncertainties are resolved.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cropyield.data.labels import (
    LACUNA_GEOJSON,
    MALAWI_2023_ZIP,
    OAF_WORKBOOK,
    check_against_raw,
    check_labels,
    lacuna_groups,
    oaf_groups,
    sha256,
)
from cropyield.data.quality import (
    CORE,
    REVIEW_RULES,
    Checks,
    check_database,
    check_geometries,
    review_records,
    summarize_reviews,
)

OPEN_QUESTIONS = [
    {"cohort": "malawi_2023", "status": "provider_confirmation_needed",
     "question": "Did the main crop-cut weight cover 100 m², or 75 m² after removing the nested 5×5 m cut?",
     "action": "Keep provider yield unchanged until harvest-area documentation resolves this."},
    {"cohort": "kenya_oaf_2019_2020", "status": "provider_confirmation_needed",
     "question": "Which GPS points mark fields versus homes; which repeats are the same field; can invalid/missing dates be corrected?",
     "action": "Review flagged IDs with original survey records. Ask for explicit 2020 crop-cut protocol confirmation."},
    {"cohort": "zimbabwe_lacuna_2022_2023", "status": "provider_confirmation_needed",
     "question": "What are the grain/cob basis, drying or moisture convention, and yield unit definition?",
     "action": "Retain provisional-unit flag; do not infer cross-country measurement equivalence."},
]
LIMITATIONS = [
    "This audit checks stored data, conversions and internal consistency; it cannot establish ground truth.",
    "No pixel-level image, cloud-mask or GPS-on-field visual inspection is performed. Stored metadata passing is not a visual pass.",
    "The numerical validity of embeddings is checked; their semantic correctness is not established by finite values.",
    "Review thresholds are fixed descriptive heuristics from the data guide, not learned cutoffs or automatic exclusions.",
    "Country membership is not independently checked against an administrative-boundary dataset.",
    "Uncertain crop-cut methods, moisture conventions and missing dates need provider evidence, not guessed corrections.",
    "Fields may have multiple review flags; counts must not be added to obtain a number of bad fields.",
    "Only Kenya, Malawi 2023 and Lacuna primary rows receive detailed review tables; integrity checks cover all retained cohorts.",
]
COUNTRY_FOLDERS = {"kenya_oaf_2019_2020": "KEN", "malawi_2023": "MWI", "zimbabwe_lacuna_2022_2023": "ZWE"}


def html_report(report: dict) -> str:
    """Self-contained human-readable report; no network, JavaScript or personal identifiers."""
    def table(headers, rows):
        return ("<table><thead><tr>" + "".join(f"<th>{escape(str(h))}</th>" for h in headers)
                + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{escape(str(x))}</td>" for x in row)
                                                  + "</tr>" for row in rows) + "</tbody></table>")

    cohorts = report["cohorts"]
    passed = sum(c["status"] == "pass" for c in report["checks"])
    retained = (f"The database retains {report['tables']['labels']:,} labels including excluded and parked cohorts. "
                if "labels" in report["tables"] else "The database label count is unavailable because the audit could not complete. ")
    parts = ["<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>",
             "<title>Maize data quality</title><style>body{max-width:1100px;margin:40px auto;padding:0 24px;",
             "font:16px/1.55 system-ui;color:#172b34;background:#fafafa}h1,h2{line-height:1.2}",
             "table{border-collapse:collapse;width:100%;margin:18px 0;background:white}",
             "td,th{padding:9px 12px;border:1px solid #dce3e5;text-align:left;vertical-align:top}",
             "th{background:#eaf2f4}li{margin:8px 0}.status{border-left:5px solid #b47b19;padding:15px;background:#fff4d9}",
             "small{color:#53636b}a{color:#075b86}</style><main><h1>Maize data quality</h1>",
             f"<p><small>Generated {escape(report['created_at'])} · branch {escape(report['branch'])}</small></p>",
             f"<p class='status'><strong>{passed}/{len(report['checks'])} integrity checks passed.</strong> ",
             "Scientific review remains open. No labels, imagery, eligibility or splits were changed. No models were run.</p>",
             "<h2>Which observations this covers</h2>",
             table(["Cohort", "Eligible fields", "At least four clear months"],
                   [(c["cohort"], c["eligible_fields"], c["usable_fields"]) for c in cohorts]),
             f"<p>{retained}",
             "The table above is the active three-cohort selection. A usable row is not a quality-certified row.</p>",
             "<h2>Fields needing review</h2><p>Numbers are flagged / assessed fields. Flags can overlap. ",
             "Unknown dates and rules that do not apply are excluded from assessed denominators.</p>"]
    review_rows = []
    for rule, description in REVIEW_RULES.items():
        counts = []
        for cohort in cohorts:
            item = cohort["flags"][rule]
            counts.append(f"{item['flagged']} / {item['assessed']}" if item["assessed"] else "Not assessed")
        review_rows.append([rule.replace("_", " "), *counts, description])
    parts.append(table(["Review flag", *[c["cohort"] for c in cohorts], "Meaning"], review_rows))
    if not cohorts:
        parts.append("<p><strong>Detailed reviews unavailable: integrity prerequisites failed. See the failed checks below.</strong></p>")
    parts.append("<h2>Monthly feature availability</h2><p>MOSAIKS needs complete pixel neighborhoods. ")
    parts.append("NULL monthly vectors are unavailable features, not zero-valued measurements; seasonal means skip them.</p>")
    parts.append(table(["Cohort (all retained rows)", "Scene-months", "Missing chip vectors", "Missing field vectors"],
                       [(r["cohort"], r["scene_months"], r["missing_chip_vectors"], r["missing_field_vectors"])
                        for r in report["monthly_feature_availability"]]))
    parts.append("<h2>Review individual records</h2><p>These tables retain original values and mark uncertainty. ")
    parts.append("They are not a cleaned replacement dataset.</p><ul>")
    for cohort in cohorts:
        iso = report["country_folders"][cohort["cohort"]]
        link = f"{iso}/{cohort['cohort']}/record_review.csv"
        parts.append(f"<li><a href='{escape(link)}'>{escape(cohort['cohort'])} record review</a></li>")
    parts.append("</ul><p><a href='monthly_coverage.csv'>Monthly coverage by cohort and year</a> · ")
    parts.append("<a href='summary.json'>Full machine-readable results and file fingerprints</a></p>")
    parts.append("<h2>Questions the data cannot settle</h2>")
    parts.append(table(["Cohort", "Question", "Next action"],
                       [(q["cohort"], q["question"], q["action"]) for q in OPEN_QUESTIONS]))
    parts.append("<h2>What has not been verified</h2><ul>" + "".join(f"<li>{escape(x)}</li>" for x in LIMITATIONS) + "</ul>")
    parts.append("<h2>Integrity checks</h2>")
    parts.append(table(["Rule", "Status", "Violations", "Detail"],
                       [(c["rule"], c["status"], c["failed_rows"] if c["failed_rows"] is not None else "—", c["detail"])
                        for c in report["checks"]]))
    return "".join(parts) + "</main></html>\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=ROOT / "data/cropyield.duckdb")
    parser.add_argument("--output", type=Path, help="New output directory; refuses to overwrite an existing report.")
    args = parser.parse_args(argv)
    stamp = datetime.now(UTC)
    output = args.output or ROOT / "data/runs/data_quality" / stamp.strftime("%Y%m%dT%H%M%S%fZ")
    if not args.db.is_file():
        parser.error("Download the shared team cropyield.duckdb to data/; do not rebuild the team database.")
    if output.exists():
        parser.error(f"Output already exists: {output}; choose a new directory.")
    checks = Checks()
    labels_path = ROOT / "data/processed/labels_v1.parquet"
    labels = pd.read_parquet(labels_path)
    manifest = json.loads((ROOT / "data/splits/manifest.json").read_text())
    spec = json.loads((ROOT / "configs/team_database_v1.json").read_text())
    scene_path = ROOT / "configs/sentinel2_scenes_v1.parquet"
    protected = {args.db.resolve(), labels_path, scene_path, OAF_WORKBOOK, LACUNA_GEOJSON, MALAWI_2023_ZIP,
                 ROOT / "configs/team_database_v1.json", ROOT / "data/splits/manifest.json",
                 ROOT / "data/metadata/download_manifest.json"}
    protected.update(ROOT / "data/splits" / name for name in manifest["files"])
    audit_paths = {}
    for dataset, rows in labels.groupby("dataset"):
        path = ROOT / "data/audit" / f"{dataset}_screened_candidates.csv"
        protected.add(path)
        audit_paths[path] = rows.source_sha256.unique().tolist()
    print("Checking file fingerprints and frozen labels...", flush=True)
    before = {str(p): sha256(p) if p.exists() else None for p in sorted(protected)}
    checks.add("team_database_fingerprint", before[str(args.db.resolve())] == spec["sha256"]
               and args.db.stat().st_size == spec["bytes"])
    checks.add("frozen_labels_fingerprint", before[str(labels_path)] == manifest["labels_sha256"])
    for name, item in manifest["files"].items():
        checks.add(f"frozen_split_{name}", before[str(ROOT / 'data/splits' / name)] == item["sha256"])
    for path, digests in audit_paths.items():
        checks.add(f"source_audit_{path.stem}", len(digests) == 1 and before[str(path)] == digests[0])
    problems = check_labels(labels)
    checks.add("label_contract", not problems, "; ".join(problems))
    check_geometries(labels, checks)
    print("Comparing yields and coordinates with provider files...", flush=True)
    try:
        raw_problems = check_against_raw(labels, oaf_groups(), lacuna_groups())
        checks.add("source_measurement_and_location_checks", not raw_problems, "; ".join(raw_problems))
    except (OSError, KeyError, ValueError) as error:
        checks.add("source_measurement_and_location_checks", False, f"Could not complete: {error}")
    print("Checking database keys, monthly observations, arithmetic and feature arrays...", flush=True)
    tables, availability = {}, []
    records, coverage = pd.DataFrame(), pd.DataFrame()
    try:
        with duckdb.connect(str(args.db), read_only=True) as con:
            tables = check_database(con, labels, checks)
            keys = ["obs_id", "month", "item_id"]
            actual = con.execute("SELECT obs_id, month, item_id FROM scenes").df()
            expected = pd.read_parquet(scene_path)[keys]
            checks.add("frozen_scene_selection", actual.sort_values(keys).reset_index(drop=True).equals(
                expected.sort_values(keys).reset_index(drop=True)))
            availability = con.execute("""SELECT cohort, count(*) AS scene_months,
                count(*) FILTER(WHERE chip IS NULL) AS missing_chip_vectors,
                count(*) FILTER(WHERE field IS NULL) AS missing_field_vectors
                FROM mosaiks_monthly JOIN labels USING(obs_id) GROUP BY cohort ORDER BY cohort""").df().to_dict("records")
            unsafe = any(c["status"] == "fail" and (c["rule"].endswith(("unique_keys", "nonnull_keys"))
                         or c["rule"] in ("database_labels_same_ids", "master_row_count", "label_contract"))
                         for c in checks.rows)
            if unsafe:
                checks.add("detailed_review_available", False, "Skipped: invalid keys/label contract make row joins unsafe.")
            else:
                records = review_records(con, labels)
                checks.add("all_core_cohorts_present", set(records.cohort) == set(CORE))
                con.register("quality_core", records[["obs_id", "cohort", "season_year", "season_start", "season_end"]])
                coverage = con.execute("""WITH expected AS (
                    SELECT q.obs_id, cohort, season_year, strftime(t.month, '%Y-%m') AS month
                    FROM quality_core q, LATERAL generate_series(date_trunc('month', season_start),
                        date_trunc('month', season_end), INTERVAL '1 month') t(month)
                  ) SELECT cohort, season_year, e.month, count(*) AS eligible_fields,
                    count(c.obs_id) AS observed_coverage_rows,
                    count(*) FILTER(WHERE c.obs_id IS NULL) AS missing_coverage_rows,
                    count(*) FILTER(WHERE state='clear') AS clear_fields,
                    count(*) FILTER(WHERE state='cloudy') AS cloudy_fields,
                    count(*) FILTER(WHERE state='no_scene') AS no_scene_fields,
                    count(*) FILTER(WHERE state='download_error') AS download_error_fields
                    FROM expected e LEFT JOIN coverage c USING(obs_id, month)
                    GROUP BY ALL ORDER BY cohort, season_year, e.month""").df()
    except (duckdb.Error, ValueError, KeyError, TypeError) as error:
        checks.add("database_audit_completed", False, f"Could not complete: {error}")
        records, coverage = pd.DataFrame(), pd.DataFrame()
    after = {str(p): sha256(p) if p.exists() else None for p in sorted(protected)}
    checks.add("all_protected_inputs_unchanged", before == after)
    git = lambda *a: subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()
    report = {
        "created_at": stamp.isoformat(), "branch": git("branch", "--show-current"), "git_commit": git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(git("status", "--porcelain")),
        "integrity_passed": checks.passed, "scientific_review_status": "open",
        "models_trained_or_scored": False, "observations_modified_or_removed": 0,
        "tables": tables, "cohorts": summarize_reviews(records) if not records.empty else [], "checks": checks.rows,
        "monthly_feature_availability": availability,
        "review_rule_definitions": REVIEW_RULES, "open_questions": OPEN_QUESTIONS, "limitations": LIMITATIONS,
        "country_folders": COUNTRY_FOLDERS,
        "input_sha256_before": before, "input_sha256_after": after,
        "source_code_sha256": {p: sha256(ROOT / p) for p in
                               ("scripts/audit_data_quality.py", "src/cropyield/data/quality.py", "src/cropyield/data/labels.py")},
        "package_versions": {p: importlib.metadata.version(p) for p in ("duckdb", "pandas", "numpy", "shapely", "pyarrow")},
    }
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "report.html").write_text(html_report(report), encoding="utf-8")
    coverage.to_csv(output / "monthly_coverage.csv", index=False)
    for (country, cohort), rows in records.groupby(["country_iso3", "cohort"]) if not records.empty else []:
        folder = output / country / cohort
        folder.mkdir(parents=True)
        # Keep a compact review table, with original values and explicit flags; no new target.
        columns = ["obs_id", "source_id", "source_row", "country_iso3", "cohort", "season_year", "lat", "lon",
                   "yield_kg_ha", "plant_date", "harvest_date", "obs_date", "season_start", "season_end",
                   "months_with_data", "ndvi_season_max", "post_observation_scene_months",
                   "usable_under_existing_rule", *REVIEW_RULES]
        rows[columns].sort_values("obs_id").to_csv(folder / "record_review.csv", index=False)
    print(f"{sum(c['status']=='pass' for c in checks.rows)}/{len(checks.rows)} integrity checks passed.")
    print(f"Report: {output / 'report.html'}")
    print("Scientific review remains open. No models run; source data unchanged.")
    return 0 if checks.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
