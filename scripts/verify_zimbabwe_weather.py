"""Independently check weather units, joins, frozen splits, scores and one selected model."""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from cropyield.data.labels import sha256
from cropyield.eval.splits import EARTH_RADIUS_KM, unit_xyz
from cropyield.experiments.zimbabwe_merge import default_output, training_rows
from cropyield.experiments.zimbabwe_weather import (
    CONFIG,
    CONTROLS,
    load_weather_experiment,
    make_context,
    predict,
    release_paths,
    verify_release,
)


def verify(config_path=CONFIG):
    config = json.loads(Path(config_path).read_text())
    paths = release_paths(config)
    prior, diagnosis, weather, output = paths["merge"], paths["diagnosis"], paths["weather"], default_output(config)
    for directory in [prior,diagnosis,weather,output]:
        verify_release(directory)
    catalog = pd.read_parquet(prior/"harmonized_labels.parquet").set_index("obs_id").sort_index()
    enriched = pd.read_parquet(weather/"harmonized_labels_weather.parquet").set_index("obs_id").sort_index()
    pd.testing.assert_frame_equal(catalog,enriched[catalog.columns])
    assert len(enriched)==6598 and enriched.weather_complete.all()
    mapping = pd.read_csv(weather/"weather_grid_mapping.csv")
    assert mapping.obs_id.is_unique and set(mapping.obs_id)==set(enriched.index)
    history = pd.read_parquet(weather/"weather_history.parquet").set_index(["weather_grid_id","year","calendar_month"])
    ledger = pd.read_csv(weather/"weather_retrieval_ledger.csv")
    assert len(ledger)==97 and len(history)==97*34*12
    for record in ledger.itertuples():
        raw = ROOT/record.raw_path
        assert sha256(raw)==record.response_sha256
        data = json.loads(raw.read_text())["properties"]["parameter"]
        for year in range(1991,2025):
            for month in range(1,13):
                key = f"{year}{month:02}"
                actual = history.loc[(record.weather_grid_id,year,month)]
                assert actual.rain_total_mm==data["PRECTOTCORR"][key]*calendar.monthrange(year,month)[1]
                assert actual.t2m_c==data["T2M"][key]
    monthly = pd.read_parquet(weather/"weather_field_months.parquet")
    assert len(monthly)==6598*9 and not monthly.duplicated(["obs_id","month"]).any()
    actual = history.reset_index()
    normals = actual[actual.year.between(1991,2020)].groupby(["weather_grid_id","calendar_month"])
    lookup = {"rain":normals.rain_total_mm.mean(),"rain_sd":normals.rain_total_mm.std(),
              "rain_rate":normals.rain_rate_mm_day.mean(),"temperature":normals.t2m_c.mean()}
    # Independently reconstruct every field's 9-month window and 46 derived values.
    for row in enriched.itertuples():
        parts = []
        for month in [10,11,12,1,2,3,4,5,6]:
            year = row.season_year-1 if month>=10 else row.season_year
            h = history.loc[(row.weather_grid_id,year,month)]
            key = (row.weather_grid_id,month)
            expected = {f"wx_rain_total_mm_m{month:02}":h.rain_total_mm,
                        f"wx_t2m_c_m{month:02}":h.t2m_c,
                        f"wx_rain_z_m{month:02}":(h.rain_total_mm-lookup['rain'][key])/lookup['rain_sd'][key],
                        f"wx_t2m_anomaly_c_m{month:02}":h.t2m_c-lookup['temperature'][key]}
            for name,value in expected.items():
                assert np.isclose(getattr(row,name),value,rtol=0,atol=1e-10)
            parts.append([month,h.rain_total_mm,h.t2m_c,h.days_in_month,
                          lookup["rain_rate"][key]*h.days_in_month,h.t2m_c-lookup["temperature"][key]])
        frame = np.array(parts)
        for label,months in [("oct_jun",[10,11,12,1,2,3,4,5,6]),("oct_mar",[10,11,12,1,2,3]),("jan_mar",[1,2,3])]:
            block = frame[np.isin(frame[:,0],months)]
            assert np.isclose(getattr(row,f"wx_rain_total_mm_{label}"),block[:,1].sum())
            assert np.isclose(getattr(row,f"wx_rain_percent_normal_{label}"),100*block[:,1].sum()/block[:,4].sum())
            if label!="oct_mar":
                assert np.isclose(getattr(row,f"wx_t2m_c_{label}"),np.average(block[:,2],weights=block[:,3]))
                assert np.isclose(getattr(row,f"wx_t2m_anomaly_c_{label}"),np.average(block[:,5],weights=block[:,3]))

    rows,features,membership,permission,controls = load_weather_experiment(config)
    # Training-row rule, checked against labels_v1 itself rather than the merged table.
    labels = pd.read_parquet(ROOT/"data/processed/labels_v1.parquet").set_index("obs_id")
    pool = sorted(set(permission.loc[permission.allowed_by_spatial_rule,"obs_id"]) | set(membership.loc[membership.role.eq("fit"),"obs_id"]))
    if training_rows(config)=="include_primary":
        assert labels.loc[pool,"include_primary"].all(), "A fit pool holds a row outside labels_v1.include_primary"
    for name in ["target_memberships.csv","source_spatial_permissions.csv"]:
        assert (output/name).read_bytes()==(prior/name).read_bytes()
    reserved = set(rows[rows.domain.eq("lacuna")&rows.fold.eq(0)].index)
    all_source = rows[rows.domain.eq("zimbabwe_2024")&rows.feature_eligible]
    minimum = np.inf
    for (outer,inner),one in permission.groupby(["outer_fold","inner_fold"]):
        m = membership[membership.outer_fold.eq(outer)]
        protected = reserved | set(m[m.inner_fold.eq(0)&m.role.eq("evaluation")].obs_id)
        if inner:
            protected |= set(m[m.inner_fold.eq(inner)&m.role.eq("validation")].obs_id)
        p = rows.loc[sorted(protected)]
        s = all_source.loc[one.obs_id]
        chord = cKDTree(unit_xyz(p.lat.to_numpy(),p.lon.to_numpy())).query(unit_xyz(s.lat.to_numpy(),s.lon.to_numpy()))[0]
        distances = 2*EARTH_RADIUS_KM*np.arcsin(np.clip(chord/(2*EARTH_RADIUS_KM),0,1))
        np.testing.assert_array_equal(distances>=2,one.allowed_by_spatial_rule)
        minimum = min(minimum,distances[one.allowed_by_spatial_rule].min())

    pred = pd.read_csv(output/"predictions.csv",dtype={"group_id":str})
    expected_ids = set(rows[rows.domain.eq("lacuna")&rows.fold.isin([1,2,3,4])].index)
    assert len(pred.method.unique())==13 and len(expected_ids)==1504
    metrics = pd.read_csv(output/"metrics.csv").set_index("method")
    for method,part in pred.groupby("method"):
        assert part.obs_id.is_unique and set(part.obs_id)==expected_ids and reserved.isdisjoint(part.obs_id)
        np.testing.assert_array_equal(part.yield_t_ha,rows.loc[part.obs_id].yield_t_ha)
        np.testing.assert_array_equal(part.outer_fold,rows.loc[part.obs_id].fold)
        e = part.prediction_t_ha-part.yield_t_ha
        assert np.isclose(np.sqrt(np.mean(e**2)),metrics.loc[method,"rmse_t_ha"],atol=1e-10)
        assert np.isclose(abs(e).mean(),metrics.loc[method,"mae_t_ha"],atol=1e-10)
    for method in CONTROLS:
        a = pred[pred.method.eq(method)].set_index("obs_id").sort_index()
        b = controls[controls.method.eq(method)].set_index("obs_id").sort_index()
        np.testing.assert_array_equal(a.prediction_t_ha,b.prediction_t_ha)
    tuning = pd.read_csv(output/"tuning.csv")
    selected = pd.read_csv(output/"selected_parameters.csv")
    accounting = pd.read_csv(output/"fit_accounting.csv")
    for pick in selected.itertuples():
        options = tuning[tuning.outer_fold.eq(pick.outer_fold)&tuning.method.eq(pick.method)]
        best = options.iloc[np.argmin(options.inner_rmse_t_ha.to_numpy())]
        assert pick.ratio==best.ratio and np.isclose(pick.inner_rmse_t_ha,best.inner_rmse_t_ha)
        key = "leaves" if "tree" in pick.method else "alpha"
        assert getattr(pick,key)==best[key]
        assert pick.n_target_train==1128 and (pick.source_used==0)==(pick.ratio==0)
    for record in accounting.itertuples():
        m = membership[membership.outer_fold.eq(record.outer_fold)&membership.inner_fold.eq(record.inner_fold)]
        fit_ids = m[m.role.eq("fit")].obs_id.tolist()
        p = permission[permission.outer_fold.eq(record.outer_fold)&permission.inner_fold.eq(record.inner_fold)&permission.allowed_by_spatial_rule]
        assert record.target_ids_sha256==hashlib.sha256("|".join(fit_ids).encode()).hexdigest()
        assert record.source_ids_sha256==hashlib.sha256("|".join(p.obs_id).encode()).hexdigest()
        assert reserved.isdisjoint(fit_ids)

    # Replay the primary paired interval with direct group resampling, not group SSE aggregation.
    wide = pred.pivot(index="obs_id",columns="method",values="prediction_t_ha").sort_index()
    truth = pred[pred.method.eq("monthly_tree_target")].set_index("obs_id").loc[wide.index]
    groups = truth.group_id.to_numpy()
    members = [np.flatnonzero(groups==g) for g in np.unique(groups)]
    rng = np.random.default_rng(config["seed"])
    e = (wide-truth.yield_t_ha.to_numpy()[:,None])**2
    differences,interactions = [],[]
    for _ in range(config["bootstrap_draws"]):
        index = np.concatenate([members[i] for i in rng.integers(len(members),size=len(members))])
        score = np.sqrt(e.iloc[index].mean())
        d = score.weather_tree_transfer-score.weather_tree_target
        differences.append(d)
        interactions.append(d-score.monthly_tree_transfer+score.monthly_tree_target)
    pair = pd.read_csv(output/"paired_differences.csv")
    primary = pair[pair.primary_comparison].iloc[0]
    np.testing.assert_allclose(np.quantile(differences,[.025,.975]),[primary.ci_low,primary.ci_high],atol=1e-10)
    interaction = json.loads((output/"transfer_benefit_interaction.json").read_text())
    np.testing.assert_allclose(np.quantile(interactions,[.025,.975]),[interaction["ci_low"],interaction["ci_high"]],atol=1e-10)

    # Replay a selected shared-label fit, verifying that weather/source training reconstructs saved predictions.
    pick = selected[selected.outer_fold.eq(1)&selected.method.eq("weather_shared")].iloc[0]
    m = membership[membership.outer_fold.eq(1)&membership.inner_fold.eq(0)]
    p = permission[permission.outer_fold.eq(1)&permission.inner_fold.eq(0)&permission.allowed_by_spatial_rule]
    ids = m[m.role.eq("evaluation")].obs_id.tolist()
    data = make_context(rows,features["weather"],m[m.role.eq("fit")].obs_id.tolist(),p.obs_id.tolist(),ids)
    with threadpool_limits(limits=1):
        replay = predict(data,"shared",{"alpha":pick.alpha,"ratio":pick.ratio},config)
    saved = pred[pred.method.eq("weather_shared")].set_index("obs_id").loc[ids].prediction_t_ha
    np.testing.assert_allclose(replay,saved,rtol=0,atol=1e-9)
    return {"status":"passed","training_rows":training_rows(config),"training_pool_rows_checked":len(pool),"labels":6598,"weather_cells":97,"field_months":len(monthly),
            "historical_cell_months":len(history),"weather_values_reconstructed":6598*46,
            "evaluation_fields_per_arm":1504,"arms":13,"reserved_fold_scored":False,
            "minimum_source_distance_to_protected_km":float(minimum),"bootstrap_draws_replayed":2000,
            "controls_identical":True,"selected_model_replay":"fold 1 weather_shared",
            "verifier_sha256":sha256(Path(__file__))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path)
    parser.add_argument("--config",type=Path,default=CONFIG)
    args = parser.parse_args()
    report = verify(args.config.resolve())
    text = json.dumps(report,indent=2)+"\n"
    print(text)
    if args.report:
        args.report.write_text(text,encoding="utf-8")


if __name__=="__main__":
    main()
