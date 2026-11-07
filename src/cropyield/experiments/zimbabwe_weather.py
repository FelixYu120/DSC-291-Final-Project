"""Same-split weather augmentation; immutable no-weather controls and paired transfer contrasts."""
from __future__ import annotations

import hashlib
import importlib.metadata
import itertools
import json
import platform
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

from cropyield import ROOT
from cropyield.data.handoff import csv_write, json_write, publish_release, require
from cropyield.data.labels import sha256
from cropyield.data.weather import CONFIG
from cropyield.data.weather import OUTPUT as WEATHER
from cropyield.experiments.zimbabwe_diagnosis import TrainingTransform
from cropyield.experiments.zimbabwe_diagnosis import predict as previous_predict
from cropyield.experiments.zimbabwe_merge import score_predictions

PRIOR = ROOT / "data/runs/zimbabwe_merge_v1"
DIAGNOSIS = ROOT / "data/runs/zimbabwe_transfer_diagnosis_v1"
OUTPUT = ROOT / "data/runs/zimbabwe_weather_v1"
CONTROLS = ["monthly_target", "monthly_adaptive", "monthly_tree_target", "monthly_tree_transfer"]


class WeatherTransform:
    """Preserve weather extremes: training-only median imputation and scaling, without clipping."""
    def fit(self, x):
        x = np.asarray(x, float).copy()
        x[~np.isfinite(x)] = np.nan
        x[:, np.isnan(x).all(axis=0)] = 0.
        self.median = np.nanmedian(x, axis=0)
        filled = np.where(np.isnan(x), self.median, x)
        self.mean, self.scale = filled.mean(axis=0), filled.std(axis=0)
        self.scale[self.scale < 1e-12] = 1.
        return self

    def transform(self, x):
        x = np.asarray(x, float)
        return (np.where(np.isfinite(x), x, self.median)-self.mean)/self.scale


def verify_release(directory):
    manifest = json.loads((directory/"manifest.json").read_text())
    for name, record in manifest["outputs"].items():
        require(sha256(directory/name)==record["sha256"], f"Changed output: {directory.name}/{name}")
    for name, digest in manifest["inputs"].items():
        require(sha256(ROOT/name)==digest, f"Changed input: {name}")


def load_weather_experiment():
    for directory in [PRIOR, DIAGNOSIS, WEATHER]:
        verify_release(directory)
    rows = pd.read_parquet(PRIOR/"combined_data.parquet").set_index("obs_id").sort_index()
    rows["group_id"] = rows.group_id.astype(str)
    enriched = pd.read_parquet(WEATHER/"harmonized_labels_weather.parquet").set_index("obs_id")
    names = json.loads((WEATHER/"weather_features.json").read_text())
    imagery = pd.read_parquet(DIAGNOSIS/"features_monthly.parquet").reindex(rows.index)
    require(len(imagery.columns)==122, "Monthly imagery feature schema changed")
    wx = enriched.loc[rows.index,names]
    require(np.isfinite(wx).all().all(), "Weather missing on comparison rows")
    pd.testing.assert_series_equal(rows.yield_t_ha, enriched.loc[rows.index,"yield_t_ha"], check_names=False)
    rows = rows.join(enriched[[c for c in enriched if c.startswith("weather_") or c in names]],validate="one_to_one")
    features = {"weather_only": wx, "weather": pd.concat([imagery,wx],axis=1)}
    terms = {}
    for month in [12,1,2,3,4,5,6]:
        for variable in ["rain_z","t2m_anomaly_c"]:
            terms[f"interaction_ndvi_{variable}_m{month:02}"] = imagery[f"ndvi_month_{month:02}"]*wx[f"wx_{variable}_m{month:02}"]
    features["interactions"] = pd.concat([features["weather"],pd.DataFrame(terms,index=rows.index)],axis=1)
    membership = pd.read_csv(PRIOR/"target_memberships.csv",dtype={"group_id":str})
    permission = pd.read_csv(PRIOR/"source_spatial_permissions.csv")
    controls = pd.read_csv(DIAGNOSIS/"predictions.csv",dtype={"group_id":str})
    controls = controls[controls.method.isin(CONTROLS)].copy()
    require(controls.groupby("method").size().eq(1504).all() and controls.outer_fold.ne(0).all(), "Invalid controls")
    return rows,features,membership,permission,controls


def make_context(rows, x, fit_ids, source_ids, query_ids):
    imagery_columns = [c for c in x if not c.startswith(("wx_","interaction_"))]
    weather_columns = [c for c in x if c not in imagery_columns]
    blocks = []
    for columns, cls in [(imagery_columns,TrainingTransform),(weather_columns,WeatherTransform)]:
        if columns:
            fitted = cls().fit(x.loc[fit_ids,columns])
            blocks.append([fitted.transform(x.loc[ids,columns]) for ids in [fit_ids,source_ids,query_ids]])
    transformed = [np.concatenate([block[i] for block in blocks],axis=1) for i in range(3)]
    return dict(zip(["xt","xs","xq"],transformed)) | {
        "yt":rows.loc[fit_ids].yield_t_ha.to_numpy(float),"ys":rows.loc[source_ids].yield_t_ha.to_numpy(float),
        "weights":np.ones(len(source_ids)),"fit_ids":fit_ids,"source_ids":source_ids}


def predict(data, kind, params, config):
    if kind != "shared" or params["ratio"]==0:
        return previous_predict(data,"ridge" if kind=="shared" else kind,params,config)
    xt,xs,xq,yt,ys,sw = (data[k] for k in ["xt","xs","xq","yt","ys","weights"])
    require(len(ys)>0,"Shared-label fit requires source rows")
    weights = np.r_[np.ones(len(yt)),sw/sw.sum()*len(yt)*params["ratio"]]
    model = Ridge(alpha=params["alpha"]).fit(np.r_[xt,xs],np.r_[yt,ys],sample_weight=weights)
    return np.maximum(model.predict(xq),0)


def specifications():
    specs = [{"name":"weather_only_target","family":"weather_only","kind":"ridge","transfer":False}]
    for family in ["weather","interactions"]:
        for kind, suffix, transfer in [("ridge","target",False),("adaptive","adaptive",True),("shared","shared",True)]:
            specs.append({"name":f"{family}_{suffix}","family":family,"kind":kind,"transfer":transfer})
    for transfer,suffix in [(False,"target"),(True,"transfer")]:
        specs.append({"name":f"weather_tree_{suffix}","family":"weather","kind":"tree","transfer":transfer})
    return specs


def parameter_grid(spec,config):
    ratios = config["source_ratios"] if spec["transfer"] else [0]
    key,grid = ("leaves",config["tree_leaf_nodes"]) if spec["kind"]=="tree" else ("alpha",config["alphas"])
    return [{key:value,"ratio":ratio} for ratio,value in itertools.product(ratios,grid)]


def run_models(rows, features, membership, permission, config):
    predictions,tuning,selected,accounting,overlap = [],[],[],[],[]
    for outer in config["target_folds"]:
        part = membership[membership.outer_fold.eq(outer)]
        query_ids = part[part.inner_fold.eq(0)&part.role.eq("evaluation")].obs_id.tolist()
        index,truths = [],[]
        for inner in range(4):
            m = part[part.inner_fold.eq(inner)]
            fit_ids = m[m.role.eq("fit")].obs_id.tolist()
            val_ids = query_ids if inner==0 else m[m.role.eq("validation")].obs_id.tolist()
            allowed = permission[permission.outer_fold.eq(outer)&permission.inner_fold.eq(inner)&permission.allowed_by_spatial_rule]
            source_ids = allowed.obs_id.tolist()
            require(rows.loc[fit_ids+val_ids].fold.ne(0).all(),"Fold-zero exposure")
            require(set(rows.loc[fit_ids].group_id).isdisjoint(rows.loc[val_ids].group_id),"Target group leakage")
            require(allowed.minimum_distance_to_protected_km.ge(config["buffer_km"]).all(),"Source buffer violation")
            require(rows.loc[source_ids].domain.eq("zimbabwe_2024").all() and rows.loc[source_ids].feature_eligible.all(),"Invalid source population")
            fit_cells = set(rows.loc[fit_ids].weather_grid_id)
            overlap.append({"outer_fold":outer,"inner_fold":inner,"query_rows":len(val_ids),
                            "query_cells":rows.loc[val_ids].weather_grid_id.nunique(),
                            "query_rows_in_training_weather_cell":int(rows.loc[val_ids].weather_grid_id.isin(fit_cells).sum()),
                            "query_cells_in_training":len(set(rows.loc[val_ids].weather_grid_id)&fit_cells)})
            index.append((fit_ids,source_ids,val_ids))
            if inner:
                truths.append(rows.loc[val_ids].yield_t_ha.to_numpy())
        truth = np.concatenate(truths)
        context_cache,prediction_cache = {},{}
        for spec in specifications():
            family = spec["family"]
            if family not in context_cache:
                context_cache[family] = [make_context(rows,features[family],*ids) for ids in index]
            contexts = context_cache[family]

            def get_prediction(inner, params, spec=spec, family=family, contexts=contexts, prediction_cache=prediction_cache):
                # Ratio zero has exactly the same target-only estimator for all Ridge variants.
                kind = "ridge" if params["ratio"]==0 and spec["kind"]!="tree" else spec["kind"]
                key = (family,kind,inner,tuple(sorted(params.items())))
                if key not in prediction_cache:
                    prediction_cache[key] = predict(contexts[inner],kind,params,config)
                return prediction_cache[key]

            trials = []
            for params in parameter_grid(spec,config):
                pred = np.concatenate([get_prediction(inner,params) for inner in [1,2,3]])
                loss = float(np.mean((truth-pred)**2))
                trials.append((loss,params))
                tuning.append({"outer_fold":outer,"method":spec["name"],**params,"inner_rmse_t_ha":np.sqrt(loss)})
            loss,best = min(trials,key=lambda trial:trial[0])
            prediction = get_prediction(0,best)
            selected.append({"outer_fold":outer,"method":spec["name"],**best,"inner_rmse_t_ha":np.sqrt(loss),
                             "n_target_train":len(contexts[0]["yt"]),"source_available":len(contexts[0]["ys"]),
                             "source_used":len(contexts[0]["ys"]) if best["ratio"]>0 else 0})
            predictions.append(pd.DataFrame({"obs_id":query_ids,"group_id":rows.loc[query_ids].group_id.to_numpy(),
                "outer_fold":outer,"method":spec["name"],"yield_t_ha":rows.loc[query_ids].yield_t_ha.to_numpy(),"prediction_t_ha":prediction}))
            for inner,data in enumerate(contexts):
                accounting.append({"outer_fold":outer,"inner_fold":inner,"method":spec["name"],
                                   "n_target":len(data["yt"]),"n_source":len(data["ys"]),
                                   "target_ids_sha256":hashlib.sha256("|".join(data["fit_ids"]).encode()).hexdigest(),
                                   "source_ids_sha256":hashlib.sha256("|".join(data["source_ids"]).encode()).hexdigest()})
            print(f"weather fold {outer} {spec['name']}: inner RMSE {np.sqrt(loss):.4f}; {best}",flush=True)
    return (pd.concat(predictions,ignore_index=True),pd.DataFrame(tuning),pd.DataFrame(selected),
            pd.DataFrame(accounting),pd.DataFrame(overlap))


def paired_metrics(predictions, config):
    metrics,folds = [],[]
    for name,part in predictions.groupby("method",sort=False):
        require(part.obs_id.is_unique and len(part)==1504 and part.outer_fold.ne(0).all(),"Unequal evaluation population")
        metrics.append({"method":name,"n":len(part),**score_predictions(part.yield_t_ha.to_numpy(),part.prediction_t_ha.to_numpy())})
        for fold,one in part.groupby("outer_fold"):
            folds.append({"method":name,"fold":fold,**score_predictions(one.yield_t_ha.to_numpy(),one.prediction_t_ha.to_numpy())})
    wide = predictions.pivot(index="obs_id",columns="method",values="prediction_t_ha").sort_index()
    require(wide.notna().all().all(),"Missing paired predictions")
    truth = predictions[predictions.method.eq("monthly_tree_target")].set_index("obs_id").loc[wide.index]
    errors = (wide-truth.yield_t_ha.to_numpy()[:,None])**2
    groups = truth.group_id.astype(str)
    counts = groups.groupby(groups,sort=True).size().to_numpy()
    sums = errors.groupby(groups,sort=True).sum().to_numpy()
    rng = np.random.default_rng(config["seed"])
    draws = rng.integers(len(counts),size=(config["bootstrap_draws"],len(counts)))
    boot = np.sqrt(sums[draws].sum(axis=1)/counts[draws].sum(axis=1)[:,None])
    boot = pd.DataFrame(boot,columns=wide.columns)
    point = np.sqrt(errors.mean())
    comparisons = [("weather_tree_transfer","weather_tree_target"),
                   ("monthly_tree_transfer","monthly_tree_target"),
                   ("weather_tree_target","monthly_tree_target"),
                   ("weather_tree_transfer","monthly_tree_transfer"),
                   ("weather_target","monthly_target"),("weather_adaptive","monthly_adaptive"),
                   ("weather_only_target","monthly_target")]
    for family in ["weather","interactions"]:
        comparisons += [(f"{family}_adaptive",f"{family}_target"),(f"{family}_shared",f"{family}_target")]
    comparisons += [("interactions_target","weather_target"),("interactions_adaptive","weather_adaptive"),
                    ("interactions_shared","weather_shared")]
    differences = []
    for method,reference in comparisons:
        low,high = np.quantile(boot[method]-boot[reference],[.025,.975])
        differences.append({"method":method,"reference":reference,"delta_rmse_t_ha":point[method]-point[reference],
                            "ci_low":low,"ci_high":high,"primary_comparison":(method,reference)==comparisons[0]})
    values = boot.weather_tree_transfer-boot.weather_tree_target-boot.monthly_tree_transfer+boot.monthly_tree_target
    low,high = np.quantile(values,[.025,.975])
    interaction = {"definition":"(pooled weather - target weather) - (pooled no weather - target no weather)",
                   "delta_rmse_t_ha":point.weather_tree_transfer-point.weather_tree_target-point.monthly_tree_transfer+point.monthly_tree_target,
                   "ci_low":low,"ci_high":high,"negative_means":"weather increased the benefit of merging",
                   "bootstrap_draws":config["bootstrap_draws"],"spatial_groups":len(counts)}
    return pd.DataFrame(metrics),pd.DataFrame(folds),pd.DataFrame(differences),interaction


def weather_summaries(rows):
    selected = rows[(rows.domain.eq("lacuna")&rows.fold.ne(0))|rows.domain.eq("zimbabwe_2024")]
    columns = ["wx_rain_total_mm_oct_mar","wx_rain_percent_normal_oct_mar","wx_rain_total_mm_jan_mar",
               "wx_rain_percent_normal_jan_mar","wx_t2m_c_jan_mar","wx_t2m_anomaly_c_jan_mar"]
    cohorts = selected.groupby("domain")[columns].mean().reset_index()
    cohorts["n_fields"] = cohorts.domain.map(selected.groupby("domain").size())
    cohorts["n_weather_cells"] = cohorts.domain.map(selected.groupby("domain").weather_grid_id.nunique())
    cells = pd.read_csv(WEATHER/"weather_matched_cells.csv")
    matched = cells.groupby("season_year")[columns].mean().reset_index()
    matched["n_weather_cells"] = cells.groupby("season_year").weather_grid_id.nunique().to_numpy()
    return cohorts,matched


def plot_results(path,metrics,differences,matched):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes = plt.subplots(1,3,figsize=(15,4.8),layout="constrained")
    names = ["monthly_tree_target","monthly_tree_transfer","weather_tree_target","weather_tree_transfer"]
    labels = ["Lacuna · imagery","Merged · imagery","Lacuna · imagery + weather","Merged · imagery + weather"]
    values = metrics.set_index("method").loc[names,"rmse_t_ha"].to_numpy()
    axes[0].barh(labels,values,color=["#65889b","#d9a361","#32617b","#ae6825"])
    for y,value in enumerate(values):
        axes[0].text(value+.012,y,f"{value:.4f}",va="center")
    axes[0].invert_yaxis()
    axes[0].set(xlabel="RMSE (t/ha), lower is better",xlim=(0,max(values)*1.16),title="Same 1,504 Lacuna fields")
    for ax,column,title,ylabel in [(axes[1],"wx_rain_percent_normal_jan_mar","January–March rainfall","% of 1991–2020 normal"),
                                    (axes[2],"wx_t2m_anomaly_c_jan_mar","January–March temperature","°C above 1991–2020 normal")]:
        ax.bar(matched.season_year.astype(str),matched[column],color=["#32617b","#ae6825"],width=.6)
        ax.set(title=title,ylabel=ylabel,xlabel="Same 97 cells in both years")
        if "rain" in column:
            ax.axhline(100,color="#666666",linestyle="--",linewidth=1)
        for x,value in enumerate(matched[column]):
            ax.text(x,value,f"{value:.1f}",ha="center",va="bottom")
    fig.suptitle("Zimbabwe weather augmentation · exploratory spatial cross-validation",fontsize=14)
    fig.savefig(path,dpi=170,bbox_inches="tight")
    plt.close(fig)


def input_hashes(config_path):
    paths = [Path(__file__),config_path,ROOT/"scripts/step12_compare_zimbabwe_weather.py",
             ROOT/"docs/ZIMBABWE_WEATHER_PROTOCOL.md",ROOT/"requirements.txt"]
    for directory in [PRIOR,DIAGNOSIS,WEATHER]:
        paths.extend(p for p in directory.iterdir() if p.is_file())
        manifest = json.loads((directory/"manifest.json").read_text())
        paths.extend(ROOT/name for name in manifest["inputs"])
    return {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha256(p) for p in set(paths)}


def write_results(path,metrics,differences,interaction,selected,overlap,matched):
    lines = ["# Zimbabwe weather experiment", "", ("Exploratory results; every arm predicts the same 1,504 Lacuna 2023 fields. "
             "Fold 0 remains reserved. RMSE/MAE/bias are t/ha. No-weather predictions are unchanged saved controls."), "",
             "| Method | RMSE | MAE | Bias | R² |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {r.method} | {r.rmse_t_ha:.6f} | {r.mae_t_ha:.6f} | {r.bias_t_ha:+.6f} | {r.r2:.6f} |" for r in metrics.itertuples()]
    primary = differences[differences.primary_comparison].iloc[0]
    lines += ["", (f"Primary: merged weather minus Lacuna-only weather RMSE = {primary.delta_rmse_t_ha:+.6f}; "
              f"95% spatial-group bootstrap interval [{primary.ci_low:+.6f}, {primary.ci_high:+.6f}]."), "",
              (f"Weather × merging interaction = {interaction['delta_rmse_t_ha']:+.6f}; "
              f"95% interval [{interaction['ci_low']:+.6f}, {interaction['ci_high']:+.6f}]. Negative means weather increased the merging benefit."), "",
              "## Selected source contributions", "", "| Method | Fold | Source/target weight ratio | Source rows used |", "|---|---:|---:|---:|"]
    lines += [f"| {r.method} | {r.outer_fold} | {r.ratio:g} | {r.source_used} |" for r in selected.itertuples()]
    outer = overlap[overlap.inner_fold.eq(0)]
    lines += ["", (f"Weather-cell overlap: {outer.query_rows_in_training_weather_cell.sum()}/{outer.query_rows.sum()} "
              "evaluation fields share a weather cell with target-training fields. The required 2 km splits do not test entirely new weather cells."), "",
              "## Weather contrast on the same 97 cells", "", "| Harvest year | Jan–Mar rainfall % normal | Jan–Mar temperature anomaly °C |", "|---|---:|---:|"]
    lines += [f"| {r.season_year} | {r.wx_rain_percent_normal_jan_mar:.3f} | {r.wx_t2m_anomaly_c_jan_mar:.3f} |" for r in matched.itertuples()]
    lines += ["", ("The weather contrast is descriptive, not causal attribution of yield differences. Year, provider, management, "
              "and measurement protocol remain confounded. Monthly regional weather cannot establish field drought damage or dry-spell duration."), "",
              ("Run step11 with the cached NASA responses, then step12. PROTOCOL.md describes source matching, unit conversion, "
              "baseline construction, training-only preprocessing and all parameter grids. The full input/output hash chain is in manifest.json."), "",
              "![Weather experiment](weather_comparison.png)", ""]
    path.write_text("\n".join(lines),encoding="utf-8")


def run_experiment(output=OUTPUT,config_path=CONFIG):
    config = json.loads(config_path.read_text())
    require(config["target_folds"]==[1,2,3,4] and config["reserved_fold"]==0,"Reserved splits cannot change")
    before = input_hashes(config_path)
    rows,features,membership,permission,controls = load_weather_experiment()
    with threadpool_limits(limits=1):
        new,tuning,selected,accounting,overlap = run_models(rows,features,membership,permission,config)
    predictions = pd.concat([controls,new],ignore_index=True)
    metrics,folds,differences,interaction = paired_metrics(predictions,config)
    cohorts,matched = weather_summaries(rows)
    with tempfile.TemporaryDirectory(prefix="zimbabwe-weather-models-") as tmp:
        stage = Path(tmp)
        for name,table in {"predictions":predictions,"metrics":metrics,"fold_metrics":folds,"paired_differences":differences,
                           "selected_parameters":selected,"tuning":tuning,"fit_accounting":accounting,"weather_cell_overlap":overlap,
                           "weather_cohort_summary":cohorts,"weather_matched_cell_summary":matched}.items():
            csv_write(table,stage/f"{name}.csv")
        # Keep exact split/permitted-source bytes, not a reserialized approximation.
        for name in ["target_memberships.csv","source_spatial_permissions.csv"]:
            (stage/name).write_bytes((PRIOR/name).read_bytes())
        enriched = rows.join(features["weather"].drop(columns=[c for c in features["weather"] if c in rows]),validate="one_to_one")
        enriched.to_parquet(stage/"combined_data_weather.parquet",index=True)
        csv_write(enriched.reset_index(),stage/"combined_data_weather.csv")
        for family,x in features.items():
            x.to_parquet(stage/f"features_{family}.parquet",index=True)
        json_write({name:list(x.columns) for name,x in features.items()},stage/"feature_dictionary.json")
        json_write(interaction,stage/"transfer_benefit_interaction.json")
        (stage/"PROTOCOL.md").write_text((ROOT/"docs/ZIMBABWE_WEATHER_PROTOCOL.md").read_text(),encoding="utf-8")
        write_results(stage/"RESULTS.md",metrics,differences,interaction,selected,overlap,matched)
        plot_results(stage/"weather_comparison.png",metrics,differences,matched)
        require(before==input_hashes(config_path),"Inputs changed during weather experiment")
        json_write({"config":config,"inputs":before,"python":platform.python_version(),
                    "versions":{name:importlib.metadata.version(name) for name in ["numpy","pandas","scipy","scikit-learn","pyarrow","matplotlib"]},
                    "outputs":{p.name:{"sha256":sha256(p),"bytes":p.stat().st_size} for p in sorted(stage.iterdir())}},stage/"manifest.json")
        publish_release(stage,output)
    print(metrics.round(6).to_string(index=False),flush=True)
    print(differences[differences.primary_comparison].to_string(index=False),flush=True)
    print(json.dumps(interaction,indent=2),flush=True)
    return metrics
