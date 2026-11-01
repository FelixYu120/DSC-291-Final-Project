# The parking folder

`_parked/` holds everything that left the data path on 31 October 2026. Nothing was deleted.
`_parked/MANIFEST.csv` lists each file with its reason and its SHA-256. A file here keeps the exact bytes of the
commit `splits-v1`, and `.gitattributes` keeps it that way in every checkout.

## Take a file back

The old path is the parked path without `_parked/`. New work should copy what it needs to a new path, because the
clean-up check fails when a parked file returns to its old path. To restore one file anyway:

```powershell
git mv _parked/<old_path> <old_path>
```

Then delete its row in `_parked/MANIFEST.csv`. A parked script can still use old script names, so fix those before you
run it. Presto code also needs `torch>=2.5` and `einops>=0.8` back in `pyproject.toml`, the weights back in
`data/models/presto/`, and the Presto steps back in the database build.

## Local files that Git does not see

These folders belong to parked work, and they exist only on the machine that made them. They may move to
`_parked/local/`, which `.gitignore` ignores. Nothing on the data path needs them.

| Local folder | New place |
|---|---|
| `data/models/presto/` | `_parked/local/data/models/presto/` |
| `data/runs/b0_seasonal_indices_ridge/` | `_parked/local/data/runs/b0_seasonal_indices_ridge/` |
| `data/runs/pilot48/` | `_parked/local/data/runs/pilot48/` |

## Before you rebuild a database

`scripts/step6_build_database.py` leaves `presto_embeddings` empty, so a rebuild of the team database removes the
embeddings. Do not rebuild it. If you must, copy the file first:

```powershell
Copy-Item data\cropyield.duckdb _parked\local\cropyield_with_presto.duckdb
```
