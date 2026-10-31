"""Frozen train/test splits: new village, new region, new season, and a random diagnostic.

Rules and evidence: docs/EVALUATION.md. A split is a table with one row per observation, per
repeat; it is written once by scripts/build_splits.py and never edited. Everything is seeded,
so the same labels give byte-identical split files.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

SEED = 20261029
FOLDS = 5
EARTH_RADIUS_KM = 6371.0088
SPLIT_COLUMNS = ["obs_id", "cohort", "season_year", "cluster_id", "group_id", "fold", "repeat", "family"]


def unit_xyz(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Points on the sphere in km, so straight-line distances in a KD-tree are chords."""
    lat, lon = np.radians(lat), np.radians(lon)
    return np.c_[np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)] * EARTH_RADIUS_KM


def chord_km(distance_km: float) -> float:
    """Chord length of a great-circle distance."""
    return 2 * EARTH_RADIUS_KM * np.sin(distance_km / (2 * EARTH_RADIUS_KM))


def connected_clusters(lat: np.ndarray, lon: np.ndarray, km: float) -> np.ndarray:
    """Single-linkage clusters: two points within `km` of each other are always in the same cluster."""
    points = unit_xyz(lat, lon)
    pairs = cKDTree(points).query_pairs(r=chord_km(km), output_type="ndarray")
    n = len(points)
    if len(pairs) == 0:
        return np.arange(n)
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(graph, directed=False)[1]


def has_neighbour(lat: np.ndarray, lon: np.ndarray, km: float) -> np.ndarray:
    """True for points with at least one other point within `km`."""
    points = unit_xyz(lat, lon)
    tree = cKDTree(points)
    return np.array([len(found) > 1 for found in tree.query_ball_point(points, r=chord_km(km))])


def nearest_km(lat: np.ndarray, lon: np.ndarray, target: np.ndarray, source: np.ndarray) -> np.ndarray:
    """For each `target` point, the chord distance in km to its nearest `source` point."""
    points = unit_xyz(lat, lon)
    return cKDTree(points[source]).query(points[target])[0]


def assign_folds(groups: np.ndarray, k: int = FOLDS, seed: int = SEED) -> np.ndarray:
    """Fold of each row. Seeded shuffle of the groups, then largest group first into the smallest fold."""
    sizes = pd.Series(groups).value_counts()
    order = np.array(sizes.index, dtype=object)
    np.random.default_rng(seed).shuffle(order)
    fold_of, filled = {}, np.zeros(k)
    for group in sorted(order, key=lambda g: -sizes[g]):  # sorted is stable: ties stay shuffled
        fold_of[group] = int(np.argmin(filled))
        filled[fold_of[group]] += sizes[group]
    return np.array([fold_of[group] for group in groups])


def _table(rows: pd.DataFrame, group_id, fold, family: str, repeat=0) -> pd.DataFrame:
    return pd.DataFrame({"obs_id": rows["obs_id"].to_numpy(), "cohort": rows["cohort"].to_numpy(),
                         "season_year": rows["season_year"].to_numpy(), "cluster_id": rows["cluster_2km"].to_numpy(),
                         "group_id": np.asarray(group_id).astype(str), "fold": np.asarray(fold).astype(str),
                         "repeat": repeat, "family": family})[SPLIT_COLUMNS]


def new_village(rows: pd.DataFrame) -> pd.DataFrame:
    """s1_cc2km: 5 folds over 2 km clusters, so no test field lies within 2 km of a training field."""
    groups = connected_clusters(rows["lat"].to_numpy(), rows["lon"].to_numpy(), 2.0)
    return _table(rows, groups, assign_folds(groups), "s1_cc2km")


def new_region(rows: pd.DataFrame, unit: str | int) -> pd.DataFrame:
    """s2_region: whole regions held out, grouped into 5 folds.

    `unit` is a column name (district), a distance in km (connected clusters) or "kmeans<k>" blocks.
    """
    if isinstance(unit, (int, float)):
        groups = connected_clusters(rows["lat"].to_numpy(), rows["lon"].to_numpy(), float(unit))
    elif unit.startswith("kmeans"):
        model = KMeans(int(unit.removeprefix("kmeans")), n_init=10, random_state=SEED)
        groups = model.fit_predict(np.c_[rows["lat"].to_numpy(), rows["lon"].to_numpy()])
    else:
        groups = rows[unit].to_numpy()
    return _table(rows, groups, assign_folds(groups), "s2_region")


def new_season(rows: pd.DataFrame, first: int, second: int) -> pd.DataFrame:
    """temporal: repeat 0 trains on `first` and tests on `second`, repeat 1 the reverse.

    `test_subset` separates test fields whose district was in the training year from new ones.
    """
    tables = []
    for repeat, (train_year, test_year) in enumerate(((first, second), (second, first))):
        fold = np.where(rows["season_year"] == train_year, "train", "test")
        table = _table(rows, rows["admin_unit"], fold, "temporal", repeat)
        seen = set(rows.loc[rows["season_year"] == train_year, "admin_unit"])
        table["test_subset"] = np.where(fold == "train", "", np.where(rows["admin_unit"].isin(seen), "seen_region", "new_region"))
        tables.append(table)
    return pd.concat(tables, ignore_index=True)


def random_diagnostic(rows: pd.DataFrame) -> pd.DataFrame:
    """random_diag: a plain random 5-fold; optimistic on purpose, reported only as a diagnostic."""
    fold = np.random.default_rng(SEED).permutation(len(rows)) % FOLDS
    return _table(rows, np.arange(len(rows)), fold, "random_diag")


def check_split(split: pd.DataFrame, rows: pd.DataFrame) -> list[str]:
    """Problems of one split table; empty when it is sound. The tests of docs/EVALUATION.md, section 4."""
    problems = []
    family = split["family"].iloc[0]
    for repeat, table in split.groupby("repeat"):
        if set(table["obs_id"]) != set(rows["obs_id"]) or table["obs_id"].duplicated().any():
            problems.append(f"{family} repeat {repeat}: rows are not exactly the eligible observations, once each")
        if family != "temporal" and (table.groupby("group_id")["fold"].nunique() > 1).any():
            problems.append(f"{family} repeat {repeat}: a group is in two folds")
    if family == "s1_cc2km":
        where = rows.set_index("obs_id").loc[split["obs_id"]]
        lat, lon = where["lat"].to_numpy(), where["lon"].to_numpy()
        for fold in split["fold"].unique():
            test = (split["fold"] == fold).to_numpy()
            if nearest_km(lat, lon, test, ~test).min() < 2.0:
                problems.append(f"s1_cc2km fold {fold}: a test field is within 2 km of a training field")
    return problems
