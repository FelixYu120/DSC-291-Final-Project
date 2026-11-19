# Where to put the data

The databases are too large for Git. Get them from the team's shared Drive folder (the link is in the team chat) and
put each file at the path below, inside your clone. Nothing else is needed to open the notebooks.

| File | Size | Put it at | Check it against |
|---|---|---|---|
| `passarchive_v1.duckdb` | 2.68 GB | `data/passarchive_v1/release/passarchive_v1.duckdb` | `data/passarchive_v1/release/SHA256SUMS` |
| `cropyield.duckdb` (data v1, with Presto and MOSAIKS) | 0.87 GB | `data/cropyield.duckdb` | `configs/team_database_v1.json` |
| `cropyield.duckdb` (data v2) | 23 MB | `data/v2/cropyield.duckdb` | `configs/team_database_v2.json` |
| `sentinel2.zip` (old image chips, optional) | 19.9 GB | unpack into `data/imagery/` | only some older notebooks need it |

The two files named `cropyield.duckdb` are different files: keep both, each in its own folder.

## Which one do I need?

- **New work: `passarchive_v1.duckdb`.** Every survey row for Kenya, Malawi and Zimbabwe, every Sentinel-2 pass of
  the harvest year and the year before, all Level-2A bands at the field, nothing filtered. Start with
  [notebooks/pass_archive_overview.ipynb](../notebooks/pass_archive_overview.ipynb) (what is inside) and
  [notebooks/pass_archive_query.ipynb](../notebooks/pass_archive_query.ipynb) (query it yourself). Columns:
  `data/passarchive_v1/release/DICTIONARY.md`.
- **To rerun the earlier results:** the two `cropyield.duckdb` files (one clear scene per month, 11,364 labels).
  They are unchanged. See the [dataset guide](DATASET.md).

## Check a download

```bash
# macOS / Linux, from the repository folder
cd data/passarchive_v1/release && shasum -a 256 -c SHA256SUMS
```

```powershell
# Windows PowerShell, from the repository folder
(Get-FileHash data\passarchive_v1\release\passarchive_v1.duckdb -Algorithm SHA256).Hash.ToLower()
Get-Content data\passarchive_v1\release\SHA256SUMS
```

The two values must be equal.

## Open it

```python
import duckdb
con = duckdb.connect("data/passarchive_v1/release/passarchive_v1.duckdb", read_only=True)
con.execute("select * from field_xy limit 5").df()
```

The file opens with DuckDB alone: no other file, no Internet, no account.
