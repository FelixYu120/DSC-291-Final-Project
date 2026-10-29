"""MOSAIKS features for every accepted Sentinel-2 scene of every labelled observation with a chip folder.

Filters are fitted once from a fixed set of scenes (seeded) and saved; later runs reuse them,
because new filters would change every feature. Pass --refit to draw new ones.

Writes to --out-dir (default data/features/mosaiks):
    filters.npz      the P filters (P, 10, s, s) and the per-band mean and std they expect
    params.json      how the filters were made (K, P, s, bias, seed, bands, ...)
    monthly.parquet  obs_id, month 'YYYY-MM', chip (K floats or null), field (K floats or null)
    season.parquet   obs_id, months_used, chip, field: the mean over the non-null monthly vectors

Usage:
    python scripts/features/mosaiks_features.py
    python scripts/features/mosaiks_features.py --patches 512 --patch-size 3 --bias 1.0 --seed 291
    python scripts/features/mosaiks_features.py --refit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.cohorts import COHORTS, load_cohort  # noqa: E402
from cropyield.features import mosaiks  # noqa: E402
from cropyield.satellite.chips import FAILED_DOWNLOAD, Chip, read_chip  # noqa: E402
from cropyield.satellite.records import Download, field_mask, match_downloads  # noqa: E402

N_FIT_CHIPS = 64        # chips whose scenes supply the random patches
VECTOR = pa.list_(pa.float32())
NOTES = ("Paper/code: 3x3 patches cut from the images, centred + unit norm + ZCA (eps 1e-3), "
         "ReLU(+conv - b) and ReLU(-conv - b), mean over the image, b = 1 (paper text). "
         "Ours: per-band standardisation with NaN -> 0, 'same' padding with a response counted only "
         "over fully valid windows, 'chip' and 'field' poolings.")


def usable(downloads: list[Download]) -> list[Download]:
    """Downloads that finished without error and hold at least one accepted scene."""
    return [d for d in downloads if d.meta["status"] not in FAILED_DOWNLOAD and d.meta["accepted_item_ids"]]


def fit_chips(downloads: list[Download], seed: int) -> list[Chip]:
    """A fixed random subset of the downloads, chosen from the sorted obs_ids, read as chips."""
    ordered = sorted(downloads, key=lambda d: d.obs_id)
    picked = np.random.default_rng(seed).choice(len(ordered), size=min(N_FIT_CHIPS, len(ordered)), replace=False)
    return [read_chip(ordered[i].record_dir) for i in sorted(picked)]


def fit(downloads: list[Download], args: argparse.Namespace) -> tuple[mosaiks.Filters, dict]:
    """New filters and their params. Nothing is written yet: see save()."""
    chips = fit_chips(downloads, args.seed)
    images = [scene.reflectance for chip in chips for scene in chip.scenes]
    print(f"fitting {args.patches} filters of {args.patch_size} x {args.patch_size} from "
          f"{len(images)} scenes of {len(chips)} chips (seed {args.seed})")
    filters = mosaiks.fit_filters(images, args.patches, args.patch_size, args.seed)
    params = {
        "k_features": filters.k_features, "n_patches": args.patches, "patch_size": args.patch_size,
        "bias": args.bias, "seed": args.seed, "bands": list(chips[0].bands), "poolings": ["chip", "field"],
        "n_fit_scenes": len(images), "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes": NOTES,
    }
    return filters, params


def load_saved(args: argparse.Namespace, out_dir: Path) -> tuple[mosaiks.Filters, dict]:
    """Reuse saved filters; refuse silently different settings, because they would change every feature."""
    params = json.loads((out_dir / "params.json").read_text())
    same = {"n_patches": args.patches, "patch_size": args.patch_size, "bias": args.bias, "seed": args.seed}
    changed = {k: (params[k], v) for k, v in same.items() if params[k] != v}
    if changed:
        raise SystemExit(f"saved filters differ in {changed} (saved, asked); pass --refit to draw new filters")
    print(f"reusing {out_dir / 'filters.npz'} (K = {params['k_features']}, created {params['created_at']})")
    return mosaiks.load_filters(out_dir / "filters.npz"), params


def save(filters: mosaiks.Filters, params: dict, out_dir: Path) -> None:
    """Write filters.npz, then params.json LAST, after the feature files.

    params.json therefore always describes the files beside it: a run that stops half-way leaves
    the previous filters, params and features together, and a missing params.json forces a refit.
    """
    mosaiks.save_filters(filters, out_dir / "filters.npz")
    params = {**params, "filters_sha256": hashlib.sha256((out_dir / "filters.npz").read_bytes()).hexdigest()}
    (out_dir / "params.json").write_text(json.dumps(params, indent=2))


def vector_column(vectors: list[np.ndarray | None]) -> pa.Array:
    """list<float32> column; a None vector becomes a null row."""
    return pa.array(vectors, type=VECTOR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--patches", type=int, default=512, help="number of random patches P; K = 2P")
    parser.add_argument("--patch-size", type=int, default=3, help="patch width s in pixels")
    parser.add_argument("--bias", type=float, default=1.0, help="ReLU bias b")
    parser.add_argument("--seed", type=int, default=291)
    parser.add_argument("--refit", action="store_true", help="draw new filters even when saved ones exist")
    parser.add_argument("--imagery-dir", type=Path, default=ROOT / "data" / "imagery" / "sentinel2")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "features" / "mosaiks")
    args = parser.parse_args(argv)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = pd.concat([load_cohort(name) for name in COHORTS], ignore_index=True)
    downloads = usable(match_downloads(labels, args.imagery_dir))
    print(f"{len(labels)} labelled observations, {len(downloads)} with a usable chip folder")
    if not downloads:
        print("nothing to featurise")
        return 1
    refit = args.refit or not ((out_dir / "filters.npz").exists() and (out_dir / "params.json").exists())
    filters, params = fit(downloads, args) if refit else load_saved(args, out_dir)
    bands = tuple(params["bands"])

    started = time.perf_counter()
    monthly: list[dict] = []
    season: list[dict] = []
    for download in downloads:
        chip = read_chip(download.record_dir)
        if chip.bands != bands:
            raise ValueError(f"{chip.obs_id}: bands {chip.bands} differ from the filters' {bands}")
        field = field_mask(chip)
        rows = [{"obs_id": chip.obs_id, "month": scene.date.strftime("%Y-%m"),
                 **dict(zip(("chip", "field"), mosaiks.featurize(scene, field, filters, args.bias)))}
                for scene in chip.scenes]
        monthly.extend(rows)
        season.append({"obs_id": chip.obs_id,
                       "months_used": sum(row["chip"] is not None for row in rows),
                       "chip": mosaiks.season_mean([row["chip"] for row in rows]),
                       "field": mosaiks.season_mean([row["field"] for row in rows])})
    seconds = time.perf_counter() - started

    pq.write_table(pa.table({
        "obs_id": pa.array([r["obs_id"] for r in monthly], pa.string()),
        "month": pa.array([r["month"] for r in monthly], pa.string()),
        "chip": vector_column([r["chip"] for r in monthly]),
        "field": vector_column([r["field"] for r in monthly]),
    }), out_dir / "monthly.parquet")
    pq.write_table(pa.table({
        "obs_id": pa.array([r["obs_id"] for r in season], pa.string()),
        "months_used": pa.array([r["months_used"] for r in season], pa.int64()),
        "chip": vector_column([r["chip"] for r in season]),
        "field": vector_column([r["field"] for r in season]),
    }), out_dir / "season.parquet")
    if refit:
        save(filters, params, out_dir)

    null_field = sum(r["field"] is None for r in monthly)
    print(f"monthly.parquet: {len(monthly)} scenes, K = {filters.k_features}, {null_field} null field vectors "
          f"({seconds / max(len(monthly), 1) * 1000:.1f} ms per scene incl. reading)")
    print(f"season.parquet: {len(season)} observations, "
          f"{sum(r['chip'] is None for r in season)} without any usable scene")
    return 0


if __name__ == "__main__":
    sys.exit(main())
