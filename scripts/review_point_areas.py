"""Write explicitly unvalidated point-buffer candidates and validate proxy geometry on Malawi.

No point is moved, no field boundary inferred, no yield/imagery/split modified, no model fit.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cropyield.data.aoi_review import (
    candidate_features,
    summarize_validation,
    validate_proxies,
)
from cropyield.data.labels import sha256


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or ROOT / "data/runs/point_area_review" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if output.exists():
        parser.error("Use a new output directory; existing reviews are preserved.")
    labels_path = ROOT / "data/processed/labels_v1.parquet"
    before = sha256(labels_path)
    manifest = json.loads((ROOT / "data/splits/manifest.json").read_text())
    if before != manifest["labels_sha256"]:
        parser.error("Frozen labels checksum mismatch; investigate before generating candidates.")
    labels = pd.read_parquet(labels_path)
    features = {}
    for country, cohort, feature in candidate_features(labels):
        features.setdefault((country, cohort), []).append(feature)
    output.mkdir(parents=True)
    for (country, cohort), items in features.items():
        folder = output / country / cohort
        folder.mkdir(parents=True)
        (folder / "unvalidated_support_candidates.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": items}, separators=(",", ":")) + "\n")
    metrics = validate_proxies(labels)
    folder = output / "MWI/malawi_2023"
    folder.mkdir(parents=True)
    metrics.to_csv(folder / "proxy_geometry_validation.csv", index=False)
    summary = {"labels_sha256": before, "labels_unchanged": sha256(labels_path) == before,
               "models_trained_or_scored": False, "field_boundaries_inferred": 0, "coordinates_moved": 0,
               "candidate_counts": {cohort: len(items) for (_, cohort), items in features.items()},
               "validation_fields": int(metrics.obs_id.nunique()), "validation": summarize_validation(metrics),
               "limitations": [
                   "Candidate circles are extraction supports, not recovered field boundaries.",
                   "Kenya reported acreage can represent several fields; it is not used to size a boundary.",
                   "Malawi validation points come from the polygon itself; results are optimistic for homestead GPS.",
                   "10/20/30m offsets are sensitivity assumptions, not measured GPS errors.",
                   "Overlap measures are geometric only; they do not establish crop purity or spectral quality.",
                   "No candidate replaces the original point, polygon, spatial group or feature."],
               "source_code_sha256": {p: sha256(ROOT / p) for p in
                                      ("src/cropyield/data/aoi_review.py", "scripts/review_point_areas.py")}}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Outputs: {output}")
    return 0 if summary["labels_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
