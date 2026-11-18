"""NASA POWER monthly weather enrichment with raw-response provenance and explicit grid matching."""
from __future__ import annotations

import calendar
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from cropyield import ROOT
from cropyield.data.handoff import csv_write, json_write, publish_release, require
from cropyield.data.labels import sha256
from cropyield.eval.splits import EARTH_RADIUS_KM

CONFIG = ROOT / "configs/zimbabwe_weather_v1.json"
CACHE = ROOT / "data/raw/nasa_power_zimbabwe_v1"
CATALOG = ROOT / "data/runs/zimbabwe_merge_v1/harmonized_labels.parquet"
OUTPUT = ROOT / "data/processed/zimbabwe_weather_v1"


def catalog_path(config: dict) -> Path:
    """Label catalog of the merge release named in the config (v1 by default)."""
    return ROOT / config.get("merge_run", "data/runs/zimbabwe_merge_v1") / "harmonized_labels.parquet"


def release_path(config: dict) -> Path:
    return ROOT / config.get("weather_release", "data/processed/zimbabwe_weather_v1")


def grid_mapping(labels, config):
    out = labels[["obs_id", "lat", "lon", "season_year"]].copy()
    lat_step, lon_step = config["latitude_spacing_degrees"], config["longitude_spacing_degrees"]
    require(np.isfinite(out[["lat", "lon"]]).all().all(), "Nonfinite coordinates")
    out["weather_grid_row"] = np.floor((out.lat+90)/lat_step+.5).astype(int)
    out["weather_grid_column"] = np.floor((out.lon+180)/lon_step+.5).astype(int)
    out["weather_grid_lat"] = out.weather_grid_row*lat_step-90
    out["weather_grid_lon"] = out.weather_grid_column*lon_step-180
    out["weather_grid_id"] = [f"merra2_r{r:03}_c{c:03}" for r,c in zip(out.weather_grid_row, out.weather_grid_column)]
    lat, lon, glat, glon = [np.radians(out[c].to_numpy()) for c in ["lat", "lon", "weather_grid_lat", "weather_grid_lon"]]
    h = np.sin((lat-glat)/2)**2 + np.cos(lat)*np.cos(glat)*np.sin((lon-glon)/2)**2
    out["weather_grid_distance_km"] = 2*EARTH_RADIUS_KM*np.arcsin(np.sqrt(np.clip(h,0,1)))
    require(out.obs_id.is_unique, "Nonunique catalog IDs")
    return out


def parse_response(content, grid_id, config):
    payload = json.loads(content)
    require(payload.get("type") == "Feature", f"Unexpected API type for {grid_id}")
    require(payload["header"]["sources"] == ["MERRA2"], f"Unexpected meteorological source for {grid_id}")
    require(payload["header"]["time_standard"] == "LST", "Unexpected provider time standard")
    require(payload["parameters"]["PRECTOTCORR"]["units"] == "mm/day", "Rainfall rate unit mismatch")
    require(payload["parameters"]["T2M"]["units"] == "C", "Temperature unit mismatch")
    parameters = payload["properties"]["parameter"]
    records = []
    for year in range(config["start_year"], config["end_year"]+1):
        for month in range(1,13):
            key = f"{year}{month:02}"
            require(all(key in parameters[name] for name in config["parameters"]), f"Missing month {grid_id}/{key}")
            rain, temp = (parameters[name][key] for name in ["PRECTOTCORR", "T2M"])
            require(np.isfinite([rain,temp]).all() and rain != payload["header"]["fill_value"]
                    and temp != payload["header"]["fill_value"], f"Missing source value {grid_id}/{key}")
            # Broad physical sanity bounds, not a yield-dependent outlier screen.
            require(0 <= rain <= 150 and -20 <= temp <= 50, f"Implausible monthly weather {grid_id}/{key}")
            days = calendar.monthrange(year,month)[1]
            records.append({"weather_grid_id":grid_id,"year":year,"calendar_month":month,"month":f"{year}-{month:02}",
                            "days_in_month":days,"rain_rate_mm_day":rain,"rain_total_mm":rain*days,"t2m_c":temp})
    return pd.DataFrame(records)


def request_parameters(grid, config):
    return {"parameters":",".join(config["parameters"]),"community":config["community"],
            "latitude":float(grid.weather_grid_lat),"longitude":float(grid.weather_grid_lon),
            "start":config["start_year"],"end":config["end_year"],"format":"JSON"}


def fetch_cell(grid, config, cache=CACHE, offline=False):
    destination = cache / grid.weather_grid_id
    raw_path, meta_path = destination / "response.json", destination / "request.json"
    params = request_parameters(grid, config)
    if destination.exists():
        require(raw_path.is_file() and meta_path.is_file(), f"Incomplete cache entry {destination}")
        metadata = json.loads(meta_path.read_text())
        require(metadata["parameters"] == params and metadata["endpoint"] == config["endpoint"], "Cache request differs")
        require(sha256(raw_path) == metadata["response_sha256"], f"Cached response hash mismatch: {grid.weather_grid_id}")
        parse_response(raw_path.read_bytes(), grid.weather_grid_id, config)
        return metadata
    require(not offline, f"Weather cache missing: {grid.weather_grid_id}; run --download-only with network access")
    cache.mkdir(parents=True,exist_ok=True)
    for attempt in range(4):
        try:
            response = requests.get(config["endpoint"],params=params,timeout=(15,90))
            if response.status_code in [429,500,502,503,504] and attempt < 3:
                time.sleep(min(30,2**(attempt+1)))
                continue
            response.raise_for_status()
            parse_response(response.content,grid.weather_grid_id,config)
            coordinates = response.json()["geometry"]["coordinates"]
            require(np.allclose(coordinates[:2],[grid.weather_grid_lon,grid.weather_grid_lat],atol=1e-8), "Response coordinates differ")
            with tempfile.TemporaryDirectory(prefix=".weather-stage-",dir=cache) as tmp:
                staged = Path(tmp) / "cell"
                staged.mkdir()
                (staged / "response.json").write_bytes(response.content)
                metadata = {"weather_grid_id":grid.weather_grid_id,"endpoint":config["endpoint"],"parameters":params,
                            "url":response.url,"retrieved_at_utc":datetime.now(UTC).isoformat(),
                            "response_sha256":sha256(staged / "response.json"),"response_bytes":len(response.content),
                            "http_headers":{k:v for k,v in response.headers.items() if k.lower() in
                                            ["content-type","date","etag","last-modified","server"]},
                            "provider_header":response.json()["header"],"parameter_metadata":response.json()["parameters"],
                            "provider_messages":response.json().get("messages",[]),"response_coordinates":coordinates}
                json_write(metadata,staged / "request.json")
                staged.rename(destination)
            return metadata
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(min(30,2**(attempt+1)))
    raise RuntimeError(f"Download failed: {grid.weather_grid_id}")


def download_weather(config, offline=False):
    catalog = catalog_path(config)
    pinned = json.loads((catalog.parent / "manifest.json").read_text())
    require(sha256(catalog) == pinned["outputs"][catalog.name]["sha256"], "Original label catalog changed")
    labels = pd.read_parquet(catalog)
    mapping = grid_mapping(labels,config)
    grids = mapping[["weather_grid_id","weather_grid_lat","weather_grid_lon"]].drop_duplicates().sort_values("weather_grid_id")
    finished = 0
    with ThreadPoolExecutor(max_workers=config["download_workers"]) as executor:
        futures = [executor.submit(fetch_cell,grid,config,CACHE,offline) for grid in grids.itertuples()]
        for future in as_completed(futures):
            future.result()
            finished += 1
            if finished % 10 == 0 or finished == len(grids):
                print(f"Weather cache verified {finished}/{len(grids)} cells",flush=True)
    return mapping,grids


def climate_normals(history, config):
    require(not history.duplicated(["weather_grid_id", "year", "calendar_month"]).any(), "Duplicate cell-month")
    reference = history[history.year.between(config["climatology_start"],config["climatology_end"])]
    normal = reference.groupby(["weather_grid_id","calendar_month"]).agg(
        reference_years=("year","nunique"),rain_normal_mm=("rain_total_mm","mean"),
        rain_normal_sd_mm=("rain_total_mm","std"),rain_normal_rate_mm_day=("rain_rate_mm_day","mean"),
        t2m_normal_c=("t2m_c","mean"),t2m_normal_sd_c=("t2m_c","std")).reset_index()
    require(normal.reference_years.eq(30).all(),"Incomplete 1991–2020 normal")
    return normal


def seasonal_weather(history,normal,config):
    actual = history[history.year.between(2021,2024)].merge(normal,on=["weather_grid_id","calendar_month"],validate="many_to_one")
    actual["season_year"] = actual.year + actual.calendar_month.ge(10).astype(int)
    actual = actual[actual.season_year.isin([2022,2023,2024]) & actual.calendar_month.isin(config["weather_months"])].copy()
    require(actual.groupby(["weather_grid_id","season_year"]).size().eq(9).all(),"Season does not have nine months")
    difference = actual.rain_total_mm-actual.rain_normal_mm
    zero_sd = actual.rain_normal_sd_mm.eq(0)
    require((~zero_sd | np.isclose(difference,0,atol=1e-10)).all(),"Undefined rainfall anomaly at zero normal variance")
    actual["rain_z"] = difference/actual.rain_normal_sd_mm.replace(0,1)
    actual["t2m_anomaly_c"] = actual.t2m_c-actual.t2m_normal_c
    actual["rain_expected_current_days_mm"] = actual.rain_normal_rate_mm_day*actual.days_in_month
    wide = actual.pivot(index=["weather_grid_id","season_year"],columns="calendar_month",
                        values=["rain_total_mm","t2m_c","rain_z","t2m_anomaly_c"])
    wide.columns = [f"wx_{variable}_m{month:02}" for variable,month in wide.columns]
    aggregates = []
    for (grid,season),part in actual.groupby(["weather_grid_id","season_year"]):
        values = {"weather_grid_id":grid,"season_year":season}
        for name,months in [("oct_jun",config["weather_months"]),("oct_mar",[10,11,12,1,2,3]),("jan_mar",[1,2,3])]:
            block = part[part.calendar_month.isin(months)]
            values[f"wx_rain_total_mm_{name}"] = block.rain_total_mm.sum()
            expected = block.rain_expected_current_days_mm.sum()
            require(expected>0,"Zero seasonal rain normal")
            values[f"wx_rain_percent_normal_{name}"] = 100*block.rain_total_mm.sum()/expected
            if name != "oct_mar":
                values[f"wx_t2m_c_{name}"] = np.average(block.t2m_c,weights=block.days_in_month)
                values[f"wx_t2m_anomaly_c_{name}"] = np.average(block.t2m_anomaly_c,weights=block.days_in_month)
        aggregates.append(values)
    wide = wide.reset_index().merge(pd.DataFrame(aggregates),on=["weather_grid_id","season_year"],validate="one_to_one")
    features = [c for c in wide if c.startswith("wx_")]
    require(len(features)==46 and np.isfinite(wide[features]).all().all(),"Invalid weather feature matrix")
    return actual.sort_values(["weather_grid_id","season_year","month"]),wide,features


def weather_dictionary(features):
    rows = []
    for name in features:
        if "percent_normal" in name:
            units,definition = "% of normal","100 × season rainfall / expected 1991–2020 rate for actual month lengths"
        elif "rain_z" in name:
            units,definition = "standard deviations","Monthly rainfall total minus historical mean, divided by historical sample standard deviation"
        elif "rain_total_mm" in name:
            units,definition = "mm","PRECTOTCORR mean daily rate × calendar days; sum for named season block"
        elif "anomaly" in name:
            units,definition = "degrees C","T2M minus 1991–2020 month normal; day-weighted mean for season blocks"
        else:
            units,definition = "degrees C","Monthly mean T2M; day-weighted mean for named season block"
        rows.append({"column":name,"units":units,"definition":definition,"provider":"NASA POWER / MERRA-2",
                     "window":"October through June","resolution":"0.5 degree latitude × 0.625 degree longitude"})
    return pd.DataFrame(rows)


def build_weather(output=OUTPUT,config_path=CONFIG,offline=True):
    config = json.loads(config_path.read_text())
    catalog = catalog_path(config)
    mapping,grids = download_weather(config,offline=offline)
    histories,ledger,inputs = [],[],{}
    for grid in grids.itertuples():
        raw,meta = CACHE/grid.weather_grid_id/"response.json",CACHE/grid.weather_grid_id/"request.json"
        history = parse_response(raw.read_bytes(),grid.weather_grid_id,config)
        metadata = json.loads(meta.read_text())
        history["response_sha256"] = metadata["response_sha256"]
        histories.append(history)
        ledger.append({"weather_grid_id":grid.weather_grid_id,"request_url":metadata["url"],
                       "retrieved_at_utc":metadata["retrieved_at_utc"],"response_sha256":metadata["response_sha256"],
                       "raw_path":str(raw.relative_to(ROOT)),"metadata_path":str(meta.relative_to(ROOT)),
                       "api_version":metadata["provider_header"]["api"]["version"],
                       "source":"MERRA2","time_standard":metadata["provider_header"]["time_standard"]})
        inputs[str(raw.relative_to(ROOT))] = sha256(raw)
        inputs[str(meta.relative_to(ROOT))] = sha256(meta)
    for path in [catalog,catalog.parent/"manifest.json",Path(__file__),
                 ROOT/"scripts/step11_add_zimbabwe_weather.py", ROOT/"src/cropyield/data/handoff.py",
                 ROOT/"src/cropyield/data/labels.py", ROOT/"src/cropyield/eval/splits.py",
                 ROOT/"docs/ZIMBABWE_WEATHER_PROTOCOL.md",config_path]:
        inputs[str(path.relative_to(ROOT))] = sha256(path)
    history = pd.concat(histories,ignore_index=True)
    normal = climate_normals(history,config)
    seasonal,wide,feature_names = seasonal_weather(history,normal,config)
    labels = pd.read_parquet(catalog)
    map_columns = [c for c in mapping if c.startswith("weather_")]
    enriched = labels.merge(mapping[["obs_id",*map_columns]],on="obs_id",validate="one_to_one")
    enriched = enriched.merge(wide,on=["weather_grid_id","season_year"],validate="many_to_one")
    require(set(enriched.obs_id)==set(labels.obs_id) and len(enriched)==6598,"Lost labels in weather join")
    enriched["weather_complete"] = np.isfinite(enriched[feature_names]).all(axis=1)
    require(enriched.weather_complete.all(),"Missing enriched weather")
    pd.testing.assert_frame_equal(labels.set_index("obs_id").sort_index(),
        enriched.set_index("obs_id")[labels.columns.drop("obs_id")].sort_index())
    field_months = mapping[["obs_id","weather_grid_id","season_year"]].merge(seasonal,on=["weather_grid_id","season_year"],validate="many_to_many")
    require(not field_months.duplicated(["obs_id","month"]).any() and len(field_months)==len(labels)*9,"Incorrect field-month expansion")
    # Fixed cells in both years distinguish temporal weather contrasts from changing sample geography.
    matched = wide[wide.season_year.isin([2023,2024])].merge(grids,on="weather_grid_id",validate="many_to_one")
    summary = {"labels":len(enriched),"weather_cells":len(grids),"field_months":len(field_months),
               "historical_cell_months":len(history),"weather_features":len(feature_names),
               "grid_distance_km_median":mapping.weather_grid_distance_km.median(),
               "grid_distance_km_max":mapping.weather_grid_distance_km.max(),"missing_weather_rows":int((~enriched.weather_complete).sum()),
               "api_versions":sorted({r["api_version"] for r in ledger}),"climatology":"1991–2020"}
    with tempfile.TemporaryDirectory(prefix="zimbabwe-weather-") as tmp:
        stage = Path(tmp)
        for name,table in {"weather_grid_mapping":mapping,"weather_retrieval_ledger":pd.DataFrame(ledger),
                           "weather_dictionary":weather_dictionary(feature_names),"weather_matched_cells":matched,
                           "climate_normals":normal}.items():
            csv_write(table,stage/f"{name}.csv")
        for name,table in {"harmonized_labels_weather":enriched,"weather_field_months":field_months,
                           "weather_cell_months":seasonal,"weather_history":history}.items():
            table.to_parquet(stage/f"{name}.parquet",index=False)
        csv_write(enriched,stage/"harmonized_labels_weather.csv")
        json_write(summary,stage/"summary.json")
        json_write(feature_names,stage/"weather_features.json")
        (stage/"README.md").write_text("# Zimbabwe labels with NASA POWER weather\n\n"
            "All 6,598 screened labels retain their original outcomes and metadata, with 46 weather predictors.\n"
            "Use the existing comparison eligibility and protected splits; the full catalog is not a training split.\n"
            "NASA POWER monthly PRECTOTCORR is mm/day, multiplied by actual month length; T2M is degrees C.\n"
            "A 0.5 × 0.625 degree grid centre is assigned to each point. These are regional reanalysis estimates.\n"
            "Normals are 1991–2020; each label uses October of the prior year through June of its year.\n"
            "See docs/ZIMBABWE_WEATHER_PROTOCOL.md for exact methods and source links, and the ledger for every URL.\n"
            "Raw response and request metadata paths/hashes are in the manifest. No target labels are imputed.\n",encoding="utf-8")
        require(all(sha256(ROOT/name)==digest for name,digest in inputs.items()), "Weather inputs changed while building")
        json_write({"config":config,"inputs":inputs,"outputs":{p.name:{"sha256":sha256(p),"bytes":p.stat().st_size}
                    for p in sorted(stage.iterdir())}},stage/"manifest.json")
        publish_release(stage,output)
    print(json.dumps(summary,indent=2),flush=True)
    return enriched,feature_names
