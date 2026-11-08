"""Fixed two/four-variable weather ablation on the original Zimbabwe spatial splits."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from cropyield import ROOT
from cropyield.data.handoff import csv_write, json_write, publish_release, require
from cropyield.data.labels import sha256
from cropyield.experiments.zimbabwe_merge import score_predictions
from cropyield.experiments.zimbabwe_weather import (
    DIAGNOSIS,
    PRIOR,
    WEATHER,
    load_weather_experiment,
    make_context,
    parameter_grid,
    predict,
    verify_release,
)
from cropyield.experiments.zimbabwe_weather import OUTPUT as FULL_WEATHER

CONFIG = ROOT / "configs/zimbabwe_weather_compact_v1.json"
PROTOCOL = ROOT / "docs/ZIMBABWE_COMPACT_WEATHER_PROTOCOL.md"
OUTPUT = ROOT / "data/runs/zimbabwe_weather_compact_v1"
CONTROL_NAMES = ["monthly_target","monthly_adaptive","monthly_tree_target","monthly_tree_transfer",
                 "weather_target","weather_adaptive","weather_shared","weather_tree_target","weather_tree_transfer"]


def early_weather(cell_months):
    """Pure weather calculation: no label column or fitted/yield-dependent feature choice."""
    keys = ["weather_grid_id","season_year"]
    early = cell_months[cell_months.calendar_month.isin([10,11,12])].copy()
    require(not early.duplicated([*keys,"calendar_month"]).any(),"Duplicate early-season month")
    require(early.groupby(keys).size().eq(3).all(),"Incomplete October–December window")
    require((early.year==early.season_year-1).all(),"Early months assigned to wrong season")
    early["temperature_day_sum"] = early.t2m_anomaly_c*early.days_in_month
    total = early.groupby(keys)[["rain_total_mm","rain_expected_current_days_mm","temperature_day_sum","days_in_month"]].sum()
    require(total.rain_expected_current_days_mm.gt(0).all(),"Undefined rain normal")
    return pd.DataFrame({"wx_rain_percent_normal_oct_dec":100*total.rain_total_mm/total.rain_expected_current_days_mm,
                         "wx_t2m_anomaly_c_oct_dec":total.temperature_day_sum/total.days_in_month}).reset_index()


def load_compact(config):
    verify_release(FULL_WEATHER)
    rows,old_features,membership,permission,_ = load_weather_experiment()
    extra = early_weather(pd.read_parquet(WEATHER/"weather_cell_months.parquet"))
    keys = ["weather_grid_id","season_year"]
    compact = rows.reset_index().merge(extra,on=keys,validate="many_to_one").set_index("obs_id").reindex(rows.index)
    imagery = old_features["weather"].loc[:,~old_features["weather"].columns.str.startswith("wx_")]
    features = {name:pd.concat([imagery,compact[columns]],axis=1) for name,columns in config["feature_sets"].items()}
    require(all(len(x.columns)==122+len(config["feature_sets"][name]) for name,x in features.items()),"Wrong feature count")
    require(np.isfinite(compact[config["feature_sets"]["compact4"]]).all().all(),"Missing compact weather")
    controls = pd.read_csv(FULL_WEATHER/"predictions.csv",dtype={"group_id":str})
    controls = controls[controls.method.isin(CONTROL_NAMES)].copy()
    return compact,features,{"monthly":imagery,"weather":old_features["weather"]},membership,permission,controls


def specifications(config):
    return [{"name":f"{family}_{suffix}","family":family,"kind":kind,"transfer":transfer}
            for family in config["feature_sets"]
            for kind,suffix,transfer in [("ridge","target",False),("adaptive","adaptive",True),
                                        ("shared","shared",True),("tree","tree_target",False),("tree","tree_transfer",True)]]


def select_inner(trials):
    """The choice has no outer-error argument; stable ordering breaks exact ties."""
    return min(trials,key=lambda item:item[0])


def fit_indices(rows,membership,permission,outer,config):
    part = membership[membership.outer_fold.eq(outer)]
    query = part[part.inner_fold.eq(0)&part.role.eq("evaluation")].obs_id.tolist()
    index = []
    for inner in range(4):
        m = part[part.inner_fold.eq(inner)]
        fit = m[m.role.eq("fit")].obs_id.tolist()
        val = query if inner==0 else m[m.role.eq("validation")].obs_id.tolist()
        allowed = permission[permission.outer_fold.eq(outer)&permission.inner_fold.eq(inner)&permission.allowed_by_spatial_rule]
        require(rows.loc[fit+val].fold.ne(0).all(),"Reserved target exposure")
        require(set(rows.loc[fit].group_id).isdisjoint(rows.loc[val].group_id),"Target spatial group overlap")
        require(allowed.minimum_distance_to_protected_km.ge(config["buffer_km"]).all(),"Source buffer violation")
        require(rows.loc[allowed.obs_id].feature_eligible.all(),"Imagery-ineligible source")
        index.append((fit,allowed.obs_id.tolist(),val))
    return index


def run_models(rows,features,old_features,membership,permission,controls,config):
    predictions,tuning,selected,accounting,gaps = [],[],[],[],[]
    for outer in config["target_folds"]:
        index = fit_indices(rows,membership,permission,outer,config)
        query = index[0][2]
        truth = np.concatenate([rows.loc[ids[2]].yield_t_ha.to_numpy() for ids in index[1:]])
        contexts,cache = {},{}
        for spec in specifications(config):
            family = spec["family"]
            if family not in contexts:
                contexts[family] = [make_context(rows,features[family],fit,source,val+(fit if i==0 else []))
                                    for i,(fit,source,val) in enumerate(index)]
            data = contexts[family]

            def get_prediction(inner,params,spec=spec,family=family,data=data,cache=cache):
                kind = "ridge" if params["ratio"]==0 and spec["kind"]!="tree" else spec["kind"]
                key = (family,kind,inner,tuple(sorted(params.items())))
                if key not in cache:
                    cache[key] = predict(data[inner],kind,params,config)
                return cache[key]

            trials = []
            for params in parameter_grid(spec,config):
                val_pred = np.concatenate([get_prediction(inner,params) for inner in [1,2,3]])
                loss = float(np.mean((truth-val_pred)**2))
                trials.append((loss,params))
                tuning.append({"outer_fold":outer,"method":spec["name"],**params,"inner_rmse_t_ha":np.sqrt(loss)})
            loss,best = select_inner(trials)
            outer_prediction = get_prediction(0,best)
            pred,train_pred = outer_prediction[:len(query)],outer_prediction[len(query):]
            train_rmse = float(np.sqrt(np.mean((train_pred-data[0]["yt"])**2)))
            outer_rmse = float(np.sqrt(np.mean((pred-rows.loc[query].yield_t_ha.to_numpy())**2)))
            selected.append({"outer_fold":outer,"method":spec["name"],**best,"inner_rmse_t_ha":np.sqrt(loss),
                             "n_target_train":len(data[0]["yt"]),"source_available":len(data[0]["ys"]),
                             "source_used":len(data[0]["ys"]) if best["ratio"]>0 else 0})
            gaps.append({"outer_fold":outer,"method":spec["name"],"training_rmse_t_ha":train_rmse,
                         "outer_rmse_t_ha":outer_rmse,"gap_t_ha":outer_rmse-train_rmse})
            predictions.append(pd.DataFrame({"obs_id":query,"group_id":rows.loc[query].group_id.to_numpy(),
                "outer_fold":outer,"method":spec["name"],"yield_t_ha":rows.loc[query].yield_t_ha.to_numpy(),"prediction_t_ha":pred}))
            for inner,context in enumerate(data):
                accounting.append({"outer_fold":outer,"inner_fold":inner,"method":spec["name"],
                                   "n_target":len(context["yt"]),"n_source":len(context["ys"]),
                                   "target_ids_sha256":hashlib.sha256("|".join(context["fit_ids"]).encode()).hexdigest(),
                                   "source_ids_sha256":hashlib.sha256("|".join(context["source_ids"]).encode()).hexdigest()})
            print(f"compact fold {outer} {spec['name']}: inner RMSE {np.sqrt(loss):.4f}; {best}",flush=True)
        # Replay old selected trees only for training-error diagnostics. Original saved OOF predictions remain controls.
        for family,directory in [("monthly",DIAGNOSIS),("weather",FULL_WEATHER)]:
            choices = pd.read_csv(directory/"selected_parameters.csv")
            fit,source,val = index[0]
            data = make_context(rows,old_features[family],fit,source,val+fit)
            for suffix in ["target","transfer"]:
                method = f"{family}_tree_{suffix}"
                choice = choices[choices.outer_fold.eq(outer)&choices.method.eq(method)].iloc[0]
                values = predict(data,"tree",{"leaves":int(choice.leaves),"ratio":float(choice.ratio)},config)
                saved = controls[controls.method.eq(method)].set_index("obs_id").loc[val].prediction_t_ha.to_numpy()
                require(np.allclose(values[:len(val)],saved,rtol=0,atol=1e-9),f"Control replay differs: {method}/{outer}")
                train_rmse = float(np.sqrt(np.mean((values[len(val):]-data["yt"])**2)))
                outer_rmse = float(np.sqrt(np.mean((saved-rows.loc[val].yield_t_ha.to_numpy())**2)))
                gaps.append({"outer_fold":outer,"method":method,"training_rmse_t_ha":train_rmse,
                             "outer_rmse_t_ha":outer_rmse,"gap_t_ha":outer_rmse-train_rmse})
        print(f"fold {outer}: no-weather and 46-weather tree replays match",flush=True)
    return pd.concat(predictions,ignore_index=True),pd.DataFrame(tuning),pd.DataFrame(selected),pd.DataFrame(accounting),pd.DataFrame(gaps)


def feature_structure(rows,old_features,config):
    ids = rows[rows.domain.eq("lacuna")&rows.fold.isin(config["target_folds"])].drop_duplicates("weather_grid_id").index
    families = {**{k:rows.loc[ids,v] for k,v in config["feature_sets"].items()},
                "full46":old_features["weather"].loc[ids].filter(regex="^wx_")}
    summaries,pairs = [],[]
    for family,x in families.items():
        sd = x.std(ddof=0)
        varying = sd.gt(1e-12)
        z = ((x.loc[:,varying]-x.loc[:,varying].mean())/sd[varying]).to_numpy()
        corr = np.corrcoef(z,rowvar=False)
        columns = x.columns[varying]
        for i in range(len(columns)):
            for j in range(i):
                if abs(corr[i,j])>=.95:
                    pairs.append({"family":family,"feature_a":columns[i],"feature_b":columns[j],"correlation":corr[i,j]})
        summaries.append({"family":family,"weather_features":len(x.columns),"target_cells":len(x),
                          "unique_profiles":len(x.drop_duplicates()),"constant_columns":int((~varying).sum()),
                          "centered_numerical_rank":int(np.linalg.matrix_rank(z)),
                          "high_correlation_pairs":sum(r["family"]==family for r in pairs)})
    return pd.DataFrame(summaries),pd.DataFrame(pairs)


def comparison_pairs(config):
    pairs = [(config["primary_method"],config["primary_reference"])]
    for family in config["feature_sets"]:
        for suffix,reference in [("target","monthly_target"),("adaptive","monthly_adaptive"),
                                 ("tree_target","monthly_tree_target"),("tree_transfer","monthly_tree_transfer")]:
            pairs.append((f"{family}_{suffix}",reference))
        for suffix in ["target","adaptive","shared","tree_target","tree_transfer"]:
            pairs.append((f"{family}_{suffix}",f"weather_{suffix}"))
        pairs += [(f"{family}_adaptive",f"{family}_target"),(f"{family}_shared",f"{family}_target"),
                  (f"{family}_tree_transfer",f"{family}_tree_target")]
    pairs += [("monthly_tree_transfer","monthly_tree_target"),("weather_tree_transfer","weather_tree_target")]
    return list(dict.fromkeys(pairs))


def evaluate(predictions,rows,config):
    metrics,folds,decomposition = [],[],[]
    for name,part in predictions.groupby("method",sort=False):
        require(len(part)==1504 and part.obs_id.is_unique and part.outer_fold.ne(0).all(),"Wrong evaluation sample")
        metrics.append({"method":name,"n":len(part),**score_predictions(part.yield_t_ha.to_numpy(),part.prediction_t_ha.to_numpy())})
        error = part.prediction_t_ha-part.yield_t_ha
        decomposition.append({"method":name,"mse":np.mean(error**2),"squared_bias":error.mean()**2,"centered_error_variance":error.var(ddof=0)})
        for fold,one in part.groupby("outer_fold"):
            folds.append({"method":name,"fold":fold,**score_predictions(one.yield_t_ha.to_numpy(),one.prediction_t_ha.to_numpy())})
    wide = predictions.pivot(index="obs_id",columns="method",values="prediction_t_ha").sort_index()
    require(wide.notna().all().all(),"Unequal paired IDs")
    truth = predictions[predictions.method.eq("monthly_tree_target")].set_index("obs_id").loc[wide.index]
    errors = (wide-truth.yield_t_ha.to_numpy()[:,None])**2
    point = np.sqrt(errors.mean())
    differences,interactions = [],[]
    for grouping,groups in [("spatial_group",truth.group_id.astype(str)),("weather_cell",rows.loc[wide.index].weather_grid_id)]:
        counts = groups.groupby(groups,sort=True).size().to_numpy()
        sums = errors.groupby(groups,sort=True).sum().to_numpy()
        draws = np.random.default_rng(config["seed"]).integers(len(counts),size=(config["bootstrap_draws"],len(counts)))
        boot = pd.DataFrame(np.sqrt(sums[draws].sum(axis=1)/counts[draws].sum(axis=1)[:,None]),columns=wide.columns)
        for method,reference in comparison_pairs(config):
            low,high = np.quantile(boot[method]-boot[reference],[.025,.975])
            differences.append({"method":method,"reference":reference,"bootstrap_unit":grouping,"clusters":len(counts),
                                "delta_rmse_t_ha":point[method]-point[reference],"ci_low":low,"ci_high":high,
                                "primary_comparison":method==config["primary_method"] and reference==config["primary_reference"] and grouping=="spatial_group"})
        values = boot.compact4_tree_transfer-boot.compact4_tree_target-boot.monthly_tree_transfer+boot.monthly_tree_target
        low,high = np.quantile(values,[.025,.975])
        interactions.append({"bootstrap_unit":grouping,"clusters":len(counts),"delta_rmse_t_ha":
            point.compact4_tree_transfer-point.compact4_tree_target-point.monthly_tree_transfer+point.monthly_tree_target,
            "ci_low":low,"ci_high":high,"negative_means":"four weather features increased the benefit of merging vs no weather"})
    return pd.DataFrame(metrics),pd.DataFrame(folds),pd.DataFrame(differences),pd.DataFrame(interactions),pd.DataFrame(decomposition)


def input_hashes():
    paths = {CONFIG,PROTOCOL,Path(__file__),ROOT/"scripts/step13_compare_compact_weather.py",ROOT/"requirements.txt"}
    for directory in [PRIOR,DIAGNOSIS,WEATHER,FULL_WEATHER]:
        paths.update(p for p in directory.iterdir() if p.is_file())
        paths.update(ROOT/name for name in json.loads((directory/"manifest.json").read_text())["inputs"])
    return {str(p.relative_to(ROOT)):sha256(p) for p in paths}


def plot_results(path,metrics):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes = plt.subplots(1,2,figsize=(11,4.2),layout="constrained")
    m = metrics.set_index("method")
    for ax,suffix,title in [(axes[0],"target","Lacuna only"),(axes[1],"transfer","Lacuna + 2024 allowed")]:
        names = [f"monthly_tree_{suffix}",f"weather_tree_{suffix}",f"compact2_tree_{suffix}",f"compact4_tree_{suffix}"]
        values = m.loc[names,"rmse_t_ha"].to_numpy()
        ax.barh(["Imagery only","+ 46 weather features","+ 2 weather features","+ 4 weather features"],values,
                color=["#657d90","#b97045","#4e8c80","#267569"])
        for i,value in enumerate(values):
            ax.text(value+.006,i,f"{value:.4f}",va="center",fontsize=10)
        ax.set(title=title,xlabel="RMSE t/ha · lower is better",xlim=(0,max(values)+.14))
        ax.invert_yaxis()
        ax.spines[["top","right"]].set_visible(False)
    fig.suptitle("Compact weather test · same 1,504 fields and frozen splits",fontsize=13)
    fig.savefig(path,dpi=170,bbox_inches="tight")
    plt.close(fig)


def run_experiment(output=OUTPUT):
    config = json.loads(CONFIG.read_text())
    require(config["target_folds"]==[1,2,3,4] and config["reserved_fold"]==0,"Reserved folds cannot change")
    before = input_hashes()
    rows,features,old_features,membership,permission,controls = load_compact(config)
    structure,correlations = feature_structure(rows,old_features,config)
    print(structure.to_string(index=False),flush=True)
    with threadpool_limits(limits=1):
        new,tuning,selected,accounting,gaps = run_models(rows,features,old_features,membership,permission,controls,config)
    predictions = pd.concat([controls,new],ignore_index=True)
    metrics,folds,differences,interactions,decomposition = evaluate(predictions,rows,config)
    with tempfile.TemporaryDirectory(prefix="zimbabwe-compact-weather-") as tmp:
        stage = Path(tmp)
        tables = {"predictions":predictions,"tuning":tuning,"selected_parameters":selected,"fit_accounting":accounting,
                  "training_outer_diagnostics":gaps,"feature_structure":structure,"weather_correlations":correlations,
                  "metrics":metrics,"fold_metrics":folds,"paired_differences":differences,"transfer_benefit_interaction":interactions,
                  "error_decomposition":decomposition}
        for name,table in tables.items():
            csv_write(table,stage/f"{name}.csv")
        for name in ["target_memberships.csv","source_spatial_permissions.csv"]:
            (stage/name).write_bytes((PRIOR/name).read_bytes())
        compact = rows[["domain","season_year","weather_grid_id","fold","feature_eligible",*config["feature_sets"]["compact4"]]]
        compact.to_parquet(stage/"compact_weather.parquet",index=True)
        csv_write(compact.reset_index(),stage/"compact_weather.csv")
        for name,x in features.items():
            x.to_parquet(stage/f"features_{name}.parquet",index=True)
        json_write({name:list(x.columns) for name,x in features.items()},stage/"feature_dictionary.json")
        (stage/"PROTOCOL.md").write_text(PROTOCOL.read_text())
        text = ["# Compact weather results","","Same 1,504 evaluation fields; exploratory. Lower RMSE is better.","",
                "| Method | RMSE t/ha | MAE t/ha | R² |","|---|---:|---:|---:|"]
        text += [f"| {r.method} | {r.rmse_t_ha:.6f} | {r.mae_t_ha:.6f} | {r.r2:.6f} |" for r in metrics.itertuples()]
        main = differences[differences.primary_comparison].iloc[0]
        text += ["",f"Primary compact4 merging difference {main.delta_rmse_t_ha:+.6f}; 95% group interval [{main.ci_low:+.6f}, {main.ci_high:+.6f}].",
                 "","See paired_differences.csv for all contrasts and the weather-cell bootstrap sensitivity, and training_outer_diagnostics.csv for fit gaps.",
                 "","![Compact weather comparison](compact_weather_comparison.png)",""]
        (stage/"RESULTS.md").write_text("\n".join(text))
        plot_results(stage/"compact_weather_comparison.png",metrics)
        require(before==input_hashes(),"Inputs changed during compact experiment")
        json_write({"config":config,"inputs":before,"python":platform.python_version(),
                    "versions":{name:importlib.metadata.version(name) for name in ["numpy","pandas","scipy","scikit-learn","pyarrow","matplotlib"]},
                    "outputs":{p.name:{"sha256":sha256(p),"bytes":p.stat().st_size} for p in sorted(stage.iterdir())}},stage/"manifest.json")
        publish_release(stage,output)
    print(metrics.round(6).to_string(index=False),flush=True)
    print(differences[differences.primary_comparison].to_string(index=False),flush=True)
    return metrics
