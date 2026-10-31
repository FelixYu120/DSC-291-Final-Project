# Landing: CROP-01-CLEAN

These are the commands the owner runs to apply the change. Run them in PowerShell from the repository root, on the
branch `plan/scope-reset`.

The moves and edits are staged. They are not committed. The local folders of step 2 have not moved.

## 1. Apply the change in Git

Do not run `git add` here. Later work stays unstaged, and it must stay out of this commit.

```powershell
git diff --cached -M --stat
git commit -m "Clean the data path: step names, parking folder, data guide"
```

## 2. Move the local files that Git does not see

Close every notebook first. `.gitignore` ignores `_parked/local/`, so these files stay on your machine.

| Local folder | New place |
|---|---|
| `data/models/presto/` | `_parked/local/data/models/presto/` |
| `data/runs/b0_seasonal_indices_ridge/` | `_parked/local/data/runs/b0_seasonal_indices_ridge/` |
| `data/runs/pilot48/` | `_parked/local/data/runs/pilot48/` |

```powershell
New-Item -ItemType Directory -Force _parked\local\data\models, _parked\local\data\runs
Move-Item data\models\presto _parked\local\data\models\presto
Move-Item data\runs\b0_seasonal_indices_ridge _parked\local\data\runs\b0_seasonal_indices_ridge
Move-Item data\runs\pilot48 _parked\local\data\runs\pilot48
```

## 3. Check it

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Use the `.venv` Python. On this machine the plain `python` imports `cropyield` from an old OneDrive folder.

## Before you rebuild the database

`scripts/step6_build_database.py` leaves `presto_embeddings` empty. The local `data/cropyield.duckdb` still holds the
embeddings, and a rebuild removes them. To keep them, copy the file before you rebuild:

```powershell
Copy-Item data\cropyield.duckdb _parked\local\cropyield_with_presto.duckdb
```

## Share it

The tag `splits-v1` and the branch `plan/scope-reset` are only on this machine. Push them when you want the team to
have them:

```powershell
git push origin plan/scope-reset
git push origin splits-v1
```

## Take a file back

The old path is the parked path without `_parked/`. For one file:

```powershell
git mv _parked/<old_path> <old_path>
```

Then delete its row in `_parked/MANIFEST.csv`. A parked script can still use old script names, so fix those before you
run it. Presto code also needs `torch>=2.5` and `einops>=0.8` back in `pyproject.toml`, the weights back in
`data/models/presto/`, and the Presto steps back in the database build.

A file in `_parked/` keeps the exact bytes of the commit `splits-v1`, and `.gitattributes` keeps it that way in every
checkout. `_parked/MANIFEST.csv` holds its SHA-256.
