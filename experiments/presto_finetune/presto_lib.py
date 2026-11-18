"""Shared code of the Presto fine-tune experiment. The rules are in experiments/presto_finetune/PLAN.md.

The parked Presto files under _parked/ are imported in place, under their old module names, after a SHA-256
check against _parked/MANIFEST.csv. Nothing is copied and nothing under _parked/, data/ or scripts/ is changed.
Every DuckDB file opens read-only.

Needs torch>=2.5 and einops>=0.8. The shared .venv has neither; this experiment runs with a Python that has them
(on the owner's machine: the global Python 3.12, which has the same numpy, pandas, scikit-learn and duckdb).
"""
from __future__ import annotations

import copy
import csv
import hashlib
import sys
import types
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (ROOT / "src", ROOT / "scripts" / "baselines"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import torch  # noqa: E402

import cropyield  # noqa: E402
import cropyield.features  # noqa: E402
import baseline_table as step8  # noqa: E402
from cropyield.satellite.monthly import MonthlySeries, month_range  # noqa: E402

PARKED = ROOT / "_parked"
DATA = ROOT / "data" / "v2"
DATABASE = DATA / "cropyield.duckdb"
DATABASE_PIN = ROOT / "configs" / "team_database_v2.json"
LABELS_FILE = "labels_v2.parquet"
RUNS = HERE / "runs"

SEED = step8.SEED                    # 20261029
SCORED_FOLDS = ("1", "2", "3", "4")  # fold 0 trains, never scored
BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
BAND_COLUMNS = tuple(band.lower() for band in BANDS)
# The fixed, label-free cohort windows (PLAN.md, Inputs). Same for every field of a cohort.
WINDOWS = {"zimbabwe_lacuna_2022_2023": ("2022-10", "2023-06"),
           "malawi_2023": ("2022-10", "2023-06"),
           "malawi_2022": ("2021-10", "2022-06")}

# Training rules (PLAN.md, Training rules).
LEARNING_RATES = (3e-5, 1e-4, 3e-4, 1e-3)
HEAD_LR_FACTOR = 10.0
WEIGHT_DECAY = 0.01
BATCH_SIZE = 32
GRAD_CLIP = 1.0
MAX_EPOCHS = 40
PATIENCE = 6
INNER_FOLDS = 5
NN_ARMS = ("P1", "P1_noloc", "P2")


# --- parked Presto code ------------------------------------------------------------------------------------------

PARKED_MODULES = {
    "cropyield.features.presto_inputs": "_parked/src/cropyield/features/presto_inputs.py",
    "cropyield.models.presto_weights": "_parked/src/cropyield/models/presto_weights.py",
    "cropyield.models.presto_single_file": "_parked/src/cropyield/models/presto_single_file.py",
    "cropyield.models.presto": "_parked/src/cropyield/models/presto.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_parked() -> dict[str, str]:
    """SHA-256 of each parked Presto file; stops if one differs from _parked/MANIFEST.csv."""
    with (PARKED / "MANIFEST.csv").open(encoding="utf-8", newline="") as handle:
        manifest = {row["new_path"]: row["sha256"] for row in csv.DictReader(handle)}
    hashes = {}
    for relative in PARKED_MODULES.values():
        actual = sha256(ROOT / relative)
        if manifest.get(relative) != actual:
            raise RuntimeError(f"{relative} differs from _parked/MANIFEST.csv; stopping.")
        hashes[relative] = actual
    return hashes


def _mount_parked() -> None:
    """Make the parked modules importable under their old names, without moving or copying them."""
    check_parked()
    features = str(PARKED / "src" / "cropyield" / "features")
    if features not in cropyield.features.__path__:
        cropyield.features.__path__.append(features)
    if "cropyield.models" not in sys.modules:  # a bare package: the parked __init__ only holds a docstring
        package = types.ModuleType("cropyield.models")
        package.__path__ = [str(PARKED / "src" / "cropyield" / "models")]
        sys.modules["cropyield.models"] = package
        cropyield.models = package


_mount_parked()
from cropyield.features.presto_inputs import PrestoInputs, presto_inputs  # noqa: E402
from cropyield.models.presto import encode, load_presto  # noqa: E402
from cropyield.models.presto_single_file import BANDS_GROUPS_IDX, NUM_DYNAMIC_WORLD_CLASSES, Presto  # noqa: E402
from cropyield.models.presto_weights import PRESTO_COMMIT, PRESTO_WEIGHTS_SHA256  # noqa: E402


# --- data --------------------------------------------------------------------------------------------------------

def cohort_rows(cohort: str):
    """X (season indices), y (t/ha) and fields (fold, group_id, season_year, lat, lon) from the step 8 code,
    after the v2 database, labels and split checks."""
    step8.check_database(DATA, DATABASE_PIN)
    step8.check_frozen(DATA, LABELS_FILE, {cohort: step8.COHORTS_V2[cohort]})
    labels = pd.read_parquet(DATA / "processed" / LABELS_FILE,
                             columns=["obs_id", "yield_kg_ha", "lat", "lon"]).set_index("obs_id")
    return step8.cohort_rows(cohort, DATA, labels, step8.COHORTS_V2[cohort], LABELS_FILE.removesuffix(".parquet"))


def monthly_series(cohort: str, obs_ids, database: Path = DATABASE,
                   window: tuple[str, str] | None = None) -> dict[str, MonthlySeries]:
    """One MonthlySeries per field over the fixed cohort window, from the view ``monthly``.

    A month carries values only when its state is ``clear``; cloudy and no_scene months are NaN, so the parked
    ``presto_inputs`` masks them. Every field must have every month of the window.
    """
    start, end = window or WINDOWS[cohort]
    months = month_range(pd.Timestamp(start + "-01").date(), pd.Timestamp(end + "-01").date())
    with duckdb.connect(str(database), read_only=True) as con:
        rows = con.execute(f"""SELECT obs_id, month, coverage_state, {", ".join(BAND_COLUMNS)}
                               FROM monthly WHERE cohort = ? AND month BETWEEN ? AND ?
                               ORDER BY obs_id, month""", [cohort, start, end]).df()
    rows = rows[rows["obs_id"].isin(set(obs_ids))]
    clear = (rows["coverage_state"] == "clear").to_numpy()
    values = rows[list(BAND_COLUMNS)].to_numpy(dtype="float32", copy=True)
    values[~clear] = np.nan
    series = {}
    for obs_id, index in rows.groupby("obs_id", sort=False).indices.items():
        if rows["month"].iloc[index].tolist() != months:
            raise ValueError(f"{obs_id}: months differ from the window {start}..{end}")
        block = values[index]
        series[obs_id] = MonthlySeries(obs_id=obs_id, months=list(months), bands=BANDS, values=block,
                                       n_pixels=np.where(np.isnan(block).all(axis=1), 0, 1),
                                       item_ids=[None] * len(months), pixel_rule="database")
    missing = set(obs_ids) - set(series)
    if missing:
        raise ValueError(f"{len(missing)} fields have no monthly rows, for example {sorted(missing)[0]}")
    return series


def kept_tokens(mask: np.ndarray, dynamic_world: np.ndarray) -> np.ndarray:
    """Number of tokens Presto keeps per record, computed as Encoder.forward does (SRTM: one token)."""
    kept = np.zeros(mask.shape[0], dtype=int)
    for group, channels in BANDS_GROUPS_IDX.items():
        group_mask = mask[:, :, channels].max(axis=-1)
        if group == "SRTM":
            group_mask = group_mask[:, :1]
        kept += (group_mask == 0).sum(axis=1)
    return kept + (dynamic_world != NUM_DYNAMIC_WORLD_CLASSES).sum(axis=1)


class Arrays:
    """Presto inputs of every field of a cohort, stacked, in the order of ``obs_ids``."""

    def __init__(self, inputs: list[PrestoInputs]):
        months = {item.month for item in inputs}
        if len(months) != 1:
            raise ValueError(f"start months differ: {sorted(months)}")
        self.obs_ids = [item.obs_id for item in inputs]
        self.x = torch.from_numpy(np.concatenate([item.x for item in inputs]))
        self.mask = torch.from_numpy(np.concatenate([item.mask for item in inputs]))
        self.dynamic_world = torch.from_numpy(np.concatenate([item.dynamic_world for item in inputs]))
        self.latlons = torch.from_numpy(np.concatenate([item.latlons for item in inputs]))
        self.month = months.pop()
        self.kept = kept_tokens(self.mask.numpy(), self.dynamic_world.numpy())

    def to_numpy(self) -> dict:
        """Plain numpy arrays, to send to worker processes once."""
        return {"obs_ids": self.obs_ids, "month": self.month, "x": self.x.numpy(), "mask": self.mask.numpy(),
                "dynamic_world": self.dynamic_world.numpy(), "latlons": self.latlons.numpy()}

    @classmethod
    def from_numpy(cls, payload: dict) -> "Arrays":
        arrays = cls.__new__(cls)
        arrays.obs_ids, arrays.month = list(payload["obs_ids"]), int(payload["month"])
        for name in ("x", "mask", "dynamic_world", "latlons"):
            setattr(arrays, name, torch.from_numpy(np.ascontiguousarray(payload[name])))
        arrays.kept = kept_tokens(payload["mask"], payload["dynamic_world"])
        return arrays

    def batch(self, index: np.ndarray, no_location: bool = False) -> dict:
        latlons = self.latlons[index]
        return {"x": self.x[index], "mask": self.mask[index], "dynamic_world": self.dynamic_world[index],
                "latlons": torch.zeros_like(latlons) if no_location else latlons, "month": self.month}

    def batches(self, index: np.ndarray, size: int, rng: np.random.Generator | None = None):
        """Index blocks of at most ``size`` fields with the same kept-token count (Presto needs this).
        With ``rng``: shuffled inside each count and in block order; without: a fixed order."""
        index = np.asarray(index)
        blocks = []
        for count in np.unique(self.kept[index]):
            members = index[self.kept[index] == count]
            if rng is not None:
                members = rng.permutation(members)
            blocks += [members[i:i + size] for i in range(0, len(members), size)]
        if rng is not None:
            blocks = [blocks[i] for i in rng.permutation(len(blocks))]
        return blocks


def build_arrays(cohort: str, fields: pd.DataFrame, database: Path = DATABASE) -> Arrays:
    """Parked ``presto_inputs`` for every field, with the lat and lon of the labels (the same as R1)."""
    series = monthly_series(cohort, fields.index, database)
    return Arrays([presto_inputs(series[obs_id], float(row.lat), float(row.lon))
                   for obs_id, row in fields[["lat", "lon"]].iterrows()])


# --- models ------------------------------------------------------------------------------------------------------

def embed(encoder: torch.nn.Module, arrays: Arrays, index: np.ndarray, no_location: bool = False,
          size: int = 256) -> np.ndarray:
    """Frozen ``eval_task`` embeddings (n, 128) in the order of ``index``."""
    out = np.zeros((len(index), encoder.embedding_size), dtype="float32")
    position = {int(i): k for k, i in enumerate(index)}
    with torch.no_grad():
        for block in arrays.batches(index, size):
            values = encoder(**arrays.batch(block, no_location), eval_task=True).numpy()
            out[[position[int(i)] for i in block]] = values
    return out


def predict(model: torch.nn.Module, arrays: Arrays, index: np.ndarray, no_location: bool,
            size: int = 256) -> np.ndarray:
    """Model output (standardised units) for ``index``, in that order."""
    model.eval()
    out = np.zeros(len(index), dtype="float64")
    position = {int(i): k for k, i in enumerate(index)}
    with torch.no_grad():
        for block in arrays.batches(index, size):
            out[[position[int(i)] for i in block]] = model(**arrays.batch(block, no_location))[:, 0].double().numpy()
    return out


def new_model(arm: str, seed: int) -> torch.nn.Module:
    """P1 and P1_noloc: the pinned pretrained weights. P2: the same architecture with random weights."""
    torch.manual_seed(seed)
    base = load_presto() if arm in ("P1", "P1_noloc") else Presto.construct()
    model = base.construct_finetuning_model(num_outputs=1, regression=True)
    torch.nn.init.zeros_(model.head.linear.bias)  # targets are standardised, so the start prediction is the mean
    return model


def train_one(job: dict) -> dict:
    """One inner model: train on the inner training rows, early-stop on the inner validation rows, and predict
    the outer test fold at the best epoch. The test rows are never used for a choice here."""
    torch.set_num_threads(1)
    arrays: Arrays = job["arrays"]
    y = job["y"]
    train, val, test = job["train"], job["val"], job["test"]
    no_location = job["arm"] == "P1_noloc"
    mean, sd = float(y[train].mean()), float(y[train].std())
    target = torch.from_numpy(((y - mean) / sd).astype("float32"))
    model = new_model(job["arm"], job["seed"])
    head = list(model.head.parameters())
    body = [p for name, p in model.named_parameters() if p.requires_grad and not name.startswith("head.")]
    optimiser = torch.optim.AdamW([{"params": body, "lr": job["lr"]},
                                   {"params": head, "lr": job["lr"] * HEAD_LR_FACTOR}], weight_decay=WEIGHT_DECAY)
    rng = np.random.default_rng(job["seed"])
    # Epoch 0 (the start weights) is the fallback, so a run whose validation MSE is never finite still predicts.
    best, best_epoch, best_state, curve = np.inf, 0, copy.deepcopy(model.state_dict()), []
    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        for block in arrays.batches(train, BATCH_SIZE, rng):
            optimiser.zero_grad()
            output = model(**arrays.batch(block, no_location))[:, 0]
            loss = torch.nn.functional.mse_loss(output, target[block])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            optimiser.step()
        val_mse = float(np.mean((predict(model, arrays, val, no_location) * sd + mean - y[val]) ** 2))
        curve.append(val_mse)
        if val_mse < best:
            best, best_epoch, best_state = val_mse, epoch, copy.deepcopy(model.state_dict())
        elif epoch - best_epoch >= PATIENCE:
            break
    model.load_state_dict(best_state)
    return {key: job[key] for key in ("arm", "fold", "lr", "inner")} | {
        "best_val_mse": best, "best_epoch": best_epoch, "epochs_run": len(curve), "curve": curve,
        "test_pred": predict(model, arrays, test, no_location) * sd + mean}


def inner_splits(train: np.ndarray, groups: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """GroupKFold(INNER_FOLDS) on group_id inside the outer training rows, as absolute row positions."""
    from sklearn.model_selection import GroupKFold
    return [(train[a], train[b]) for a, b in GroupKFold(n_splits=INNER_FOLDS).split(train, groups=groups[train])]


_WORKER: dict = {}


def init_worker(payload: dict, y: np.ndarray) -> None:
    """Pool initializer: one torch thread, and the cohort arrays sent once per process."""
    torch.set_num_threads(1)
    _WORKER["arrays"], _WORKER["y"] = Arrays.from_numpy(payload), y


def run_job(job: dict) -> dict:
    return train_one(job | {"arrays": _WORKER["arrays"], "y": _WORKER["y"]})


def job_seed(fold: str, lr_index: int, inner: int) -> int:
    """The same seed for every arm on the same fold, learning rate and inner fold: paired batch orders."""
    return SEED + 1000 * int(fold) + 100 * lr_index + inner
