"""Build data/cropyield.duckdb: every piece of project data as its own table, plus the views.

The database is rebuilt from scratch on every run. Labels come from the committed audit CSVs
(cropyield.data.cohorts), imagery tables from the chip folders the downloader wrote under
data/imagery/sentinel2, Presto embeddings from the frozen encoder, and the MOSAIKS tables from
the parquet files scripts/features/mosaiks_features.py writes under data/features/mosaiks.
One observation is one field in one season, keyed everywhere by ``obs_id = "<dataset>:<source_id>"``.

The SQL lives in sql/ (read sql/README.md): schema.sql creates the tables, views.sql the views.
This script runs the two files and fills the tables by column name.

Tables, all keyed by obs_id (every column is commented in sql/schema.sql):
    labels               one row per observation of every cohort, with or without imagery
    downloads            one row per observation that has a chip folder
    scenes               one row per accepted Sentinel-2 scene
    coverage             one row per observation x month: no_scene / cloudy / clear / download_error
    monthly_bands        one row per observation x month: median field reflectance per band
    vegetation_indices   one row per observation x month: NDVI, GCVI, MTCI, NDVI705, NDVI740
    presto_embeddings    one row per observation with data: the frozen Presto embedding, FLOAT[128]
    mosaiks_monthly      one row per observation x month: MOSAIKS chip and field vectors, FLOAT[K]
    mosaiks_season       one row per observation: the season mean of the MOSAIKS vectors
    build_info           one row: when, from which commit and from which folders this was built
Views (sql/views.sql): season_indices, master (one row per labelled observation, NULLs where
imagery is missing) and monthly (one row per observation x month, for sequence models).

Usage:
    python scripts/build_database.py                 # data/cropyield.duckdb, with Presto embeddings
    python scripts/build_database.py --no-presto     # skip the embeddings (torch is not imported)
    python scripts/build_database.py --mosaiks-dir data/features/mosaiks   # where the MOSAIKS files are
Then, for example:
    from cropyield.data.database import connect
    connect().sql("SELECT * FROM master LIMIT 5")
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.cohorts import AUDIT_DIR, COHORTS, load_cohort  # noqa: E402
from cropyield.features.indices import vegetation_indices  # noqa: E402
from cropyield.features.presto_inputs import PrestoInputs, presto_inputs  # noqa: E402
from cropyield.models.presto_weights import PRESTO_COMMIT, PRESTO_WEIGHTS_SHA256, weights_verified  # noqa: E402
from cropyield.satellite.chips import FAILED_DOWNLOAD, Chip, read_chip  # noqa: E402
from cropyield.satellite.monthly import MonthlySeries, month_range, monthly_series  # noqa: E402
from cropyield.satellite.records import Download, field_mask, match_downloads  # noqa: E402

DEFAULT_DB = ROOT / "data" / "cropyield.duckdb"
DEFAULT_IMAGERY = ROOT / "data" / "imagery" / "sentinel2"
DEFAULT_MOSAIKS = ROOT / "data" / "features" / "mosaiks"
SCHEMA_FILE = ROOT / "sql" / "schema.sql"
VIEWS_FILE = ROOT / "sql" / "views.sql"
BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
BAND_COLUMNS = [band.lower() for band in BANDS]          # b02 ... b12
# The tables, in the order of sql/schema.sql. Frames are inserted BY NAME, so column order is free.
TABLES = ("labels", "downloads", "scenes", "coverage", "monthly_bands", "vegetation_indices",
          "presto_embeddings", "mosaiks_monthly", "mosaiks_season", "build_info")
# The MOSAIKS parquet files (scripts/features/mosaiks_features.py) and the columns each table takes.
MOSAIKS_FILES = {"mosaiks_monthly": ("monthly.parquet", ["obs_id", "month", "chip", "field"]),
                 "mosaiks_season": ("season.parquet", ["obs_id", "months_used", "chip", "field"])}
MOSAIKS_HINT = ("MOSAIKS features not found: mosaiks_monthly and mosaiks_season stay empty. "
                "Make them with: python scripts/features/mosaiks_features.py")


# --- labels: the audit rows of every cohort -------------------------------------------------

def blank_to_null(text: pd.Series) -> pd.Series:
    """Audit columns are text; an empty string, or a column a dataset lacks, means no value."""
    text = text.fillna("").astype(str).str.strip()
    return text.where(text != "", None)


def label_dates(rows: pd.DataFrame) -> pd.Series:
    """Harvest date where the provider gives one, else the crop-cut observation time; NaT if neither."""
    text = blank_to_null(rows["harvest_date"]).fillna(blank_to_null(rows["observation_time"]))
    return pd.to_datetime(text, format="mixed")  # providers mix ISO, "2023/05/17 08:55" and "3/15/2022 9:30"


def field_polygons(datasets) -> dict[tuple[str, str], str]:
    """GeoJSON geometry text per (dataset, source_id) from data/audit/<dataset>_candidates_wgs84.geojson."""
    polygons = {}
    for dataset in datasets:
        path = AUDIT_DIR / f"{dataset}_candidates_wgs84.geojson"
        if not path.exists():
            continue  # point datasets have no polygon file
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            polygons[(dataset, str(feature["properties"]["source_id"]))] = json.dumps(feature["geometry"])
    return polygons


def labels_frame() -> pd.DataFrame:
    """One row per observation of every cohort, with the columns of the labels table."""
    rows = pd.concat([load_cohort(name) for name in COHORTS], ignore_index=True)
    polygons = field_polygons(rows["dataset"].unique())
    return pd.DataFrame({
        "obs_id": rows["obs_id"],
        "cohort": rows["cohort"],
        "dataset": rows["dataset"],
        "source_id": rows["source_id"],
        "source_row": rows["source_row"],
        "country": rows["country"],
        "year": rows["year"],
        "yield_kg_ha": rows["yield_kg_ha"],
        "source_yield": pd.to_numeric(blank_to_null(rows["source_yield"])),
        "source_yield_units": blank_to_null(rows["source_yield_units"]),
        "yield_field": blank_to_null(rows["yield_field"]),
        "latitude": rows["latitude"],
        "longitude": rows["longitude"],
        "geometry_type": blank_to_null(rows["geometry_type"]),
        "field_area_ha": pd.to_numeric(blank_to_null(rows["field_area_ha"])),
        "label_date": label_dates(rows),
        "season_start": rows["season_start"],
        "season_end": rows["season_end"],
        "intercropping": blank_to_null(rows["intercropping"]),
        "field_polygon": [polygons.get(key) for key in zip(rows["dataset"], rows["source_id"])],
    })


# --- downloads: which chip folder belongs to which observation (cropyield.satellite.records) ----

def relative_dir(path: Path) -> str:
    """Folder path relative to the repository root; absolute when it lies elsewhere (tests)."""
    path = path.resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


# --- one row (or a few rows) per observation for each imagery table ---------------------------

def download_row(item: Download, chip: Chip) -> dict:
    return {
        "obs_id": item.obs_id,
        "record_dir": relative_dir(item.record_dir),
        "status": chip.status,
        "aoi_type": chip.aoi_type,
        "aoi_pixels": int(chip.aoi.sum()),
        "field_pixels": int(field_mask(chip).sum()),
        "aoi_inside_chip": chip.entire_aoi_inside_chip,
        "catalog_scenes": item.meta.get("catalog_matches"),
        "accepted_months": len(item.meta["accepted_item_ids"]),
        "crs": chip.crs,
        "search_start": chip.start_date,
        "search_end": chip.end_date,
    }


def scene_rows(item: Download, chip: Chip) -> list[dict]:
    """One row per accepted scene; satellite and tile are read off the item id S2B_T36LWL_2023...."""
    field = field_mask(chip)
    return [{
        "obs_id": item.obs_id,
        "item_id": scene.item_id,
        "acquired": scene.date,
        "month": scene.date.strftime("%Y-%m"),
        "satellite": scene.item_id.split("_")[0],
        "tile": scene.item_id.split("_")[1].removeprefix("T"),
        "tile_cloud_cover": scene.tile_cloud_cover,
        "clear_fraction_aoi": scene.clear_fraction_aoi,
        "field_valid_pixels": int((field & scene.valid).sum()),
    } for scene in chip.scenes]


def coverage_rows(item: Download, chip: Chip) -> list[dict]:
    """What the downloader found for each month of the season window.

    clear: a scene was accepted. cloudy: every scene tried (at most --candidates-per-month) was
    rejected for clouds or missing pixels over the field. no_scene: the catalogue offered no scene
    under the downloader's tile cloud limit (--max-cloud-cover). download_error: the download failed
    part-way (status error or partial_error), so every month of it is unknown, even an accepted one:
    no band values are read from such a folder.
    """
    accepted = {scene.date.strftime("%Y-%m"): scene.item_id for scene in chip.scenes}
    attempts = item.meta.get("attempts", [])
    rows = []
    for month in month_range(item.season_start, item.season_end):
        tried = [attempt["status"] for attempt in attempts if attempt["month"] == month]
        if chip.status in FAILED_DOWNLOAD:
            state = "download_error"
        elif month in accepted:
            state = "clear"
        elif tried:
            state = "cloudy"
        else:
            state = "no_scene"
        item_id = accepted.get(month) if state == "clear" else None
        rows.append({"obs_id": item.obs_id, "month": month, "state": state, "item_id": item_id})
    return rows


def band_rows(series: MonthlySeries) -> list[dict]:
    """One row per month: the median field reflectance of each band (NaN becomes NULL)."""
    return [{
        "obs_id": series.obs_id,
        "month": month,
        **{column: float(series.band(band)[i]) for band, column in zip(BANDS, BAND_COLUMNS)},
        "field_pixels": int(series.n_pixels[i]),
        "missing": bool(series.missing[i]),
    } for i, month in enumerate(series.months)]


def index_rows(series: MonthlySeries) -> list[dict]:
    """One row per month with the five Lobell et al. (2020) indices."""
    indices = vegetation_indices(series)
    return [{"obs_id": series.obs_id, "month": month, **values.to_dict()} for month, values in indices.iterrows()]


def embedding_row(series: MonthlySeries, chip: Chip, encoder: Callable[[PrestoInputs], np.ndarray]) -> dict:
    """The frozen Presto embedding as one list of 128 numbers (stored as FLOAT[128])."""
    embedding = encoder(presto_inputs(series, chip.latitude, chip.longitude))
    return {"obs_id": series.obs_id, "embedding": embedding.astype("float32").tolist()}


def presto_encoder() -> Callable[[PrestoInputs], np.ndarray]:
    """Pretrained Presto as a function inputs -> embedding. Imports torch, so only called with Presto on."""
    from cropyield.models.presto import encode, load_presto

    model = load_presto()
    return lambda inputs: encode(model, inputs)


def imagery_frames(downloads: list[Download], encoder: Callable | None) -> dict[str, pd.DataFrame]:
    """Read every chip once and collect the rows of each imagery table."""
    rows: dict[str, list[dict]] = {name: [] for name in ("downloads", "scenes", "coverage", "monthly_bands",
                                                         "vegetation_indices", "presto_embeddings")}
    for item in downloads:
        chip = read_chip(item.record_dir)
        rows["downloads"].append(download_row(item, chip))
        rows["scenes"] += scene_rows(item, chip)
        rows["coverage"] += coverage_rows(item, chip)
        if chip.status in FAILED_DOWNLOAD or not chip.scenes:
            continue  # no band values to read; the coverage rows already say why every month is empty
        series = monthly_series(chip, item.season_start, item.season_end)
        rows["monthly_bands"] += band_rows(series)
        rows["vegetation_indices"] += index_rows(series)
        if encoder is not None and not series.missing.all():
            rows["presto_embeddings"].append(embedding_row(series, chip, encoder))
    return {name: pd.DataFrame(table) for name, table in rows.items()}


# --- MOSAIKS: parquet files written by scripts/features/mosaiks_features.py ----------------------

def mosaiks_present(mosaiks_dir: Path) -> bool:
    """True when both parquet files exist; otherwise the MOSAIKS tables stay empty."""
    return all((mosaiks_dir / file).exists() for file, _ in MOSAIKS_FILES.values())


def mosaiks_tables(mosaiks_dir: Path) -> dict[str, pa.Table]:
    """The two MOSAIKS parquet files as Arrow tables with exactly the columns of their database table.

    Arrow keeps list<float32> as FLOAT[] and a NULL vector as NULL, so nothing is converted in
    Python. A parquet file without one of the expected columns stops the build with a KeyError.
    """
    if not mosaiks_present(mosaiks_dir):
        return {table: pa.table({column: [] for column in columns}) for table, (_, columns) in MOSAIKS_FILES.items()}
    return {table: pq.read_table(mosaiks_dir / file).select(columns) for table, (file, columns) in MOSAIKS_FILES.items()}


def mosaiks_params(mosaiks_dir: Path) -> tuple[int | None, str | None]:
    """(K, text of params.json) from the MOSAIKS folder; (None, None) when MOSAIKS is not built."""
    path = mosaiks_dir / "params.json"
    if not mosaiks_present(mosaiks_dir) or not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    return int(json.loads(text)["k_features"]), text


# --- build_info and the database file -----------------------------------------------------------

def git_commit() -> str | None:
    """Commit the repository checkout is at; None when git is unavailable."""
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    except FileNotFoundError:  # git is not installed
        return None
    return result.stdout.strip() or None


def build_info_frame(frames: dict, imagery_dir: Path, with_presto: bool, mosaiks_dir: Path) -> pd.DataFrame:
    k_features, params = mosaiks_params(mosaiks_dir)
    return pd.DataFrame([{
        "built_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "git_commit": git_commit(),
        "presto_commit": PRESTO_COMMIT,
        "presto_weights_sha256": PRESTO_WEIGHTS_SHA256 if with_presto else None,
        "presto_embeddings_built": with_presto,
        "imagery_dir": relative_dir(imagery_dir),
        "n_labels": len(frames["labels"]),
        "n_downloads": len(frames["downloads"]),
        "n_embeddings": len(frames["presto_embeddings"]),
        "mosaiks_features": k_features,
        "mosaiks_params": params,
    }])


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    """Run every statement of one SQL file, in order.

    DuckDB's own parser splits the file (``extract_statements``), so semicolons inside comments or
    strings are safe, and a failing statement is reported with its number in the file.
    """
    statements = con.extract_statements(path.read_text(encoding="utf-8"))
    for number, statement in enumerate(statements, start=1):
        try:
            con.execute(statement)
        except duckdb.Error as error:
            raise RuntimeError(f"{path.name}, statement {number}: {error}") from error


def insert(con: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame | pa.Table) -> int:
    """Insert a pandas or Arrow table into its database table by column name and return the row count.

    DuckDB casts a Python list or an Arrow list column to the table's array type (FLOAT[128],
    FLOAT[]) on insert, and stops with an error when a vector has the wrong length.
    """
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}")
    if len(frame):
        con.register("df", frame)
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
        con.unregister("df")
    return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def build_database(db: Path, imagery_dir: Path, with_presto: bool, mosaiks_dir: Path = DEFAULT_MOSAIKS) -> dict[str, int]:
    """Create ``db`` from scratch and return the row count of every table."""
    frames: dict = {"labels": labels_frame()}
    downloads = match_downloads(frames["labels"], imagery_dir)
    frames.update(imagery_frames(downloads, presto_encoder() if with_presto else None))
    frames.update(mosaiks_tables(mosaiks_dir))
    if not mosaiks_present(mosaiks_dir):
        print(MOSAIKS_HINT)
    frames["build_info"] = build_info_frame(frames, imagery_dir, with_presto, mosaiks_dir)

    db.parent.mkdir(parents=True, exist_ok=True)
    for stale in (db, db.with_name(db.name + ".wal")):
        try:
            stale.unlink(missing_ok=True)
        except PermissionError:  # Windows: another program still holds the file open
            raise PermissionError(f"{stale} is in use. Close every connection to it (con.close() in "
                                  "04_database.ipynb) and run again.") from None
    with duckdb.connect(str(db)) as con:
        run_sql_file(con, SCHEMA_FILE)
        counts = {table: insert(con, table, frames[table]) for table in TABLES}
        run_sql_file(con, VIEWS_FILE)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="database file to (re)create")
    parser.add_argument("--imagery-dir", type=Path, default=DEFAULT_IMAGERY, help="folder holding run-*/records/")
    parser.add_argument("--mosaiks-dir", type=Path, default=DEFAULT_MOSAIKS,
                        help="folder holding monthly.parquet, season.parquet and params.json")
    parser.add_argument("--no-presto", action="store_true", help="skip the Presto embeddings (no torch import)")
    args = parser.parse_args(argv)
    if not args.no_presto and not weights_verified():
        print("Presto weights are missing; run scripts/models/get_presto.py or pass --no-presto", file=sys.stderr)
        return 1
    started = time.perf_counter()
    try:
        counts = build_database(args.db, args.imagery_dir, with_presto=not args.no_presto, mosaiks_dir=args.mosaiks_dir)
    except PermissionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    for table, count in counts.items():
        print(f"{table:<20} {count:>8} rows")
    print(f"{args.db} built in {time.perf_counter() - started:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
