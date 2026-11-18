"""Input check of PLAN.md: the experiment's input path must give back the v1 Presto embeddings.

    python experiments/presto_finetune/check_inputs.py [--cohort zimbabwe_lacuna_2022_2023] [--n 300]

Builds the Presto inputs of v1 fields from the v1 view ``monthly`` (data/cropyield.duckdb, read-only) with the
same code as the experiment, encodes them one by one with the parked ``encode`` and in batches with ``embed``,
and compares both with the stored v1 ``presto_embeddings``. Writes nothing. Exit code 1 on a mismatch.
"""
from __future__ import annotations

import argparse
import sys

import duckdb
import numpy as np

import presto_lib as lib

TOLERANCE = 1e-4


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cohort", default="zimbabwe_lacuna_2022_2023")
    parser.add_argument("--n", type=int, default=300, help="fields to check (seeded sample)")
    args = parser.parse_args(argv)
    v1 = lib.ROOT / "data" / "cropyield.duckdb"
    with duckdb.connect(str(v1), read_only=True) as con:
        rows = con.execute("""SELECT m.obs_id, m.latitude, m.longitude, e.embedding
                              FROM master m JOIN presto_embeddings e USING (obs_id)
                              WHERE m.cohort = ? AND m.include_primary AND m.months_with_data >= 4
                              ORDER BY m.obs_id""", [args.cohort]).df()
    rows = rows.iloc[np.sort(np.random.default_rng(lib.SEED).choice(len(rows), min(args.n, len(rows)), replace=False))]
    series = lib.monthly_series(args.cohort, rows["obs_id"], database=v1)
    inputs = [lib.presto_inputs(series[r.obs_id], float(r.latitude), float(r.longitude)) for r in rows.itertuples()]
    stored = np.stack(rows["embedding"].map(np.asarray).to_list()).astype("float32")
    model = lib.load_presto()
    one_by_one = np.stack([lib.encode(model, item) for item in inputs])
    arrays = lib.Arrays(inputs)
    batched = lib.embed(model.encoder, arrays, np.arange(len(inputs)))
    gaps = {"parked encode vs stored v1": np.abs(one_by_one - stored).max(),
            "batched embed vs stored v1": np.abs(batched - stored).max(),
            "batched embed vs parked encode": np.abs(batched - one_by_one).max()}
    print(f"{args.cohort}: {len(rows)} v1 fields, kept-token counts {sorted(set(arrays.kept.tolist()))}, "
          f"start month {arrays.month}")
    for name, gap in gaps.items():
        print(f"  largest absolute difference, {name}: {gap:.2e}")
    ok = all(gap < TOLERANCE for gap in gaps.values())
    print("OK" if ok else f"MISMATCH (tolerance {TOLERANCE})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
