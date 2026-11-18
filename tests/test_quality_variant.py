"""A reviewed variant preserves observations and rejects incompatible review inputs."""

import importlib.util
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from cropyield import ROOT
from cropyield.data.labels import sha256


def write_json(path, payload):
    path.write_text(json.dumps(payload) + "\n")


def refresh_kenya_fingerprint(directory):
    path = directory / "provenance.json"
    provenance = json.loads(path.read_text())
    provenance["derived_output_sha256"] = {
        name: sha256(directory / name)
        for name in ("record_review.parquet", "date_review.csv", "coordinate_pairs.csv", "summary.json")
    }
    write_json(path, provenance)


@pytest.fixture
def completed_reviews(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("assemble_quality_variant", ROOT / "scripts/quality/assemble_quality_variant.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kenya_dir, clouds, areas = (tmp_path / name for name in ("kenya", "clouds", "areas"))
    for directory in (kenya_dir, clouds, areas):
        directory.mkdir()
    labels_path = tmp_path / "labels_v1.parquet"
    labels = pd.DataFrame({
        "obs_id": ["k:year", "k:order", "k:valid", "k:missing", "m:1", "z:1", "parked:1"],
        "cohort": ["kenya_oaf_2019_2020"] * 4 + ["malawi_2023", "zimbabwe_lacuna_2022_2023", "zimbabwe_2024"],
        "country_iso3": ["KEN"] * 4 + ["MWI", "ZWE", "ZWE"],
        "season_year": [2019, 2020, 2019, 2020, 2023, 2023, 2024],
        "yield_kg_ha": [1234., 0., 2234., 3234., 4234., 5234., 0.],
        "lat": [0.1, 0.2, 0.3, 0.4, -13., -18., -18.1],
        "lon": [34., 34.1, 34.2, 34.3, 33., 30., 30.1],
        "geometry_wkt": [None] * 4 + ["POLYGON ((33 -13, 33.01 -13, 33.01 -12.99, 33 -13))", None, None],
        "include_primary": [True] * 6 + [False],
        "exclusion_reason": [""] * 6 + ["source_zero_requires_review"],
        "cluster_2km": ["g1", "g2", "g3", "g4", "g5", "g6", "g7"],
        "field_area_ha": [.2, .4, .1, .3, .6, np.nan, np.nan],
        "provider_note": ["preserve this source text"] * 7,
        "impossible_date": [True, True, False, False, False, False, False],
        "date_outside_window": [False] * 7,
    })
    labels["plant_date"] = pd.to_datetime([
        "2100-03-01", "2020-06-25", "2019-03-01", None, None, "2022-11-15", None])
    labels["harvest_date"] = pd.to_datetime([
        "2019-08-01", "2020-06-23", "2019-09-01", None, None, "2023-05-01", None])
    labels["obs_date"] = pd.to_datetime([
        "2019-08-01", "2020-06-23", "2019-09-01", None, "2023-05-20", "2023-05-01", "2024-04-15"])
    labels.to_parquet(labels_path, index=False)
    monkeypatch.setattr(module, "LABELS_PATH", labels_path)
    label_hash = sha256(labels_path)

    kenya = labels.iloc[:4].copy()
    kenya["proposed_plant_date"] = kenya.plant_date
    kenya["proposed_harvest_date"] = kenya.harvest_date
    kenya.loc[0, "proposed_plant_date"] = pd.NaT
    kenya.loc[1, ["proposed_plant_date", "proposed_harvest_date"]] = pd.NaT
    kenya["proposed_obs_date"] = kenya.proposed_harvest_date
    kenya["date_decision"] = ["quarantine_plant_year_outside_season_range",
                              "quarantine_both_ambiguous_date_order", "retain_source_dates", "retain_source_dates"]
    kenya["exact_coordinate_group_id"] = ""
    kenya["coordinate_group_id"] = ""
    kenya["location_scope"] = "field_or_homestead_or_nearby_per_provider"
    kenya["area_scope"] = "crop_and_field_type_land_not_verified_individual_field"
    kenya.to_parquet(kenya_dir / "record_review.parquet", index=False)
    kenya[kenya.date_decision.ne("retain_source_dates")].to_csv(kenya_dir / "date_review.csv", index=False)
    pd.DataFrame(columns=["left_obs_id", "right_obs_id"]).to_csv(kenya_dir / "coordinate_pairs.csv", index=False)
    write_json(kenya_dir / "summary.json", {
        "date_decisions": kenya.date_decision.value_counts().to_dict(), "original_missing_harvest_dates": 1,
        "dates_recovered_from_source": 0, "exact_coordinate_observations": 0, "exact_coordinate_groups": 0,
        "exact_pairs": 0, "near_10m_pairs": 0,
    })
    write_json(kenya_dir / "provenance.json", {
        "protected_sha256_before": {"data/processed/labels_v1.parquet": label_hash},
        "protected_sha256_after": {"data/processed/labels_v1.parquet": label_hash}, "inputs_unchanged": True,
    })
    refresh_kenya_fingerprint(kenya_dir)
    write_json(areas / "summary.json", {"labels_sha256": label_hash, "labels_unchanged": True, "validation": []})

    fields = labels[["obs_id", "cohort", "country_iso3", "include_primary"]].copy()
    fields["original_months_with_data"] = 4
    fields["retained_months"] = [4, 2, 4, 4, 4, 3, 0]
    fields["retains_four_months"] = fields.retained_months.ge(4)
    monthly = pd.DataFrame([
        {"obs_id": row.obs_id, "month": f"{row.season_year}-0{month}",
         "b04": .2 if month <= fields.retained_months.iloc[i] else np.nan,
         "b08": .6 if month <= fields.retained_months.iloc[i] else np.nan,
         "missing": month > fields.retained_months.iloc[i]}
        for i, row in enumerate(labels.itertuples()) for month in range(1, 5)
    ])
    season = fields[["obs_id"]].copy()
    season["ndvi_season_mean"] = np.where(fields.retained_months.gt(0), .5, np.nan)
    tables = {"field_coverage.parquet": fields, "cleaned_monthly_bands.parquet": monthly,
              "clean_season_indices.parquet": season}
    for name, frame in tables.items():
        frame.to_parquet(clouds / name, index=False)
    for (country, cohort), group in fields.groupby(["country_iso3", "cohort"]):
        folder = clouds / country / cohort
        folder.mkdir(parents=True)
        for name, frame in tables.items():
            frame[frame.obs_id.isin(group.obs_id)].to_parquet(folder / name, index=False)
    write_json(clouds / "run.json", {
        "scope_complete": True, "scope": "all-retained", "source_inputs_unchanged": True,
        "input_sha256": {str(labels_path.resolve()): label_hash},
        "output_sha256": {p.relative_to(clouds).as_posix(): sha256(p) for p in clouds.rglob("*.parquet")},
        "policy": {"buffer_metres": 60}, "unique_scenes": 12, "reviewed_field_months": len(monthly),
        "kept_field_months": int(fields.retained_months.sum()), "unverified_field_months": 0,
        "unreviewed_field_months": 0,
    })
    output = tmp_path / "assembled"
    return SimpleNamespace(module=module, labels=labels, labels_path=labels_path, kenya=kenya_dir,
                           clouds=clouds, areas=areas, output=output,
                           argv=["--kenya", str(kenya_dir), "--clouds", str(clouds),
                                 "--point-areas", str(areas), "--output", str(output)])


def test_assembled_variant_retains_every_source_value_and_quarantines_only_reviewed_dates(completed_reviews):
    case = completed_reviews
    # Sidecar order is incidental: observation identifiers must control alignment.
    kenya_path = case.kenya / "record_review.parquet"
    pd.read_parquet(kenya_path).iloc[::-1].to_parquet(kenya_path, index=False)
    refresh_kenya_fingerprint(case.kenya)
    protected = {p: sha256(p) for p in case.labels_path.parent.rglob("*") if p.is_file()}
    assert case.module.main(case.argv) == 0
    original = case.labels.set_index("obs_id")
    result = pd.read_parquet(case.output / "labels_reviewed.parquet").set_index("obs_id")
    assert result.index.equals(original.index)
    assert result.index.is_unique
    for name in original.columns:
        saved_name = "original_" + name if name in {
            "plant_date", "harvest_date", "obs_date", "impossible_date", "date_outside_window"} else name
        pd.testing.assert_series_equal(result[saved_name], original[name], check_names=False)
    expected_dates = original[["plant_date", "harvest_date", "obs_date"]].copy()
    expected_dates.loc["k:year", "plant_date"] = pd.NaT
    expected_dates.loc["k:order"] = pd.NaT
    pd.testing.assert_frame_equal(result[expected_dates.columns], expected_dates)
    assert result.loc["k:order", "yield_kg_ha"] == 0  # A legitimate zero is not deleted.
    assert not result.loc["k:order", "core_usable_under_strict_cloud_rule"]
    assert not result.loc["parked:1", "include_primary"]
    assert not result.loc["parked:1", "core_usable_under_strict_cloud_rule"]
    assert all(sha256(path) == digest for path, digest in protected.items())
    country_ids = []
    for path in case.output.glob("*/*/labels_reviewed.parquet"):
        country_ids.extend(pd.read_parquet(path).obs_id)
    assert sorted(country_ids) == sorted(original.index)
    for source in case.clouds.glob("*/*/cleaned_monthly_bands.parquet"):
        copied = case.output / source.relative_to(case.clouds)
        pd.testing.assert_frame_equal(pd.read_parquet(copied), pd.read_parquet(source))
    summary = json.loads((case.output / "summary.json").read_text())
    assert summary["source_observations"] == summary["retained_observations"] == 7
    assert summary["no_models_trained_or_scored"]
    assert (case.output / "report.html").is_file()


@pytest.mark.parametrize("scope,complete", [("all-retained", False), ("core", True)])
def test_partial_cloud_review_is_not_assembled_as_a_complete_dataset(completed_reviews, scope, complete):
    case = completed_reviews
    path = case.clouds / "run.json"
    run = json.loads(path.read_text())
    run.update(scope=scope, scope_complete=complete)
    write_json(path, run)
    with pytest.raises(SystemExit) as error:
        case.module.main(case.argv)
    assert error.value.code == 2
    assert not case.output.exists()


@pytest.mark.parametrize("corruption", ["missing", "duplicate"])
def test_kenya_review_requires_each_source_observation_exactly_once(completed_reviews, corruption):
    case = completed_reviews
    path = case.kenya / "record_review.parquet"
    records = pd.read_parquet(path)
    records = records.iloc[:-1] if corruption == "missing" else pd.concat([records, records.iloc[:1]], ignore_index=True)
    records.to_parquet(path, index=False)
    refresh_kenya_fingerprint(case.kenya)
    with pytest.raises(ValueError, match="Kenya review keys"):
        case.module.main(case.argv)
    assert not case.output.exists()


@pytest.mark.parametrize("field", ["yield_kg_ha", "lat", "lon"])
def test_kenya_review_cannot_replace_yields_or_coordinates(completed_reviews, field):
    case = completed_reviews
    path = case.kenya / "record_review.parquet"
    records = pd.read_parquet(path)
    records.loc[0, field] += 1
    records.to_parquet(path, index=False)
    refresh_kenya_fingerprint(case.kenya)
    with pytest.raises(ValueError, match=f"changed original {field}"):
        case.module.main(case.argv)
    assert not case.output.exists()


@pytest.mark.parametrize("field", ["proposed_plant_date", "proposed_harvest_date", "proposed_obs_date",
                                  "plant_date", "harvest_date"])
def test_even_fingerprinted_kenya_dates_cannot_invent_or_rewrite_source_evidence(completed_reviews, field):
    case = completed_reviews
    path = case.kenya / "record_review.parquet"
    records = pd.read_parquet(path)
    # The valid source row must not acquire a new plausible date merely because a
    # replacement review file has its own valid fingerprint.
    records.loc[2, field] += pd.Timedelta(days=1)
    records.to_parquet(path, index=False)
    refresh_kenya_fingerprint(case.kenya)
    with pytest.raises(ValueError):
        case.module.main(case.argv)
    assert not case.output.exists()


def test_missing_harvest_cannot_be_filled_with_a_plausible_but_unsupported_date(completed_reviews):
    case = completed_reviews
    path = case.kenya / "record_review.parquet"
    records = pd.read_parquet(path)
    records.loc[records.obs_id.eq("k:missing"), ["proposed_harvest_date", "proposed_obs_date"]] = pd.Timestamp("2020-09-01")
    records.to_parquet(path, index=False)
    refresh_kenya_fingerprint(case.kenya)
    with pytest.raises(ValueError, match="proposed dates"):
        case.module.main(case.argv)
    assert not case.output.exists()


def test_completed_cloud_review_from_different_labels_is_rejected(completed_reviews):
    case = completed_reviews
    path = case.clouds / "run.json"
    run = json.loads(path.read_text())
    run["input_sha256"][str(case.labels_path.resolve())] = "0" * 64
    write_json(path, run)
    with pytest.raises(ValueError):
        case.module.main(case.argv)
    assert not case.output.exists()


def test_cloud_derivative_modified_after_review_is_rejected(completed_reviews):
    case = completed_reviews
    path = case.clouds / "cleaned_monthly_bands.parquet"
    monthly = pd.read_parquet(path)
    monthly.loc[0, "b08"] = .9
    monthly.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="Cloud derivative fingerprint mismatch"):
        case.module.main(case.argv)
    assert not case.output.exists()
