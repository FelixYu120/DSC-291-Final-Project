# The full download on a cluster

The full data is every cohort: **11,364 field-seasons**, about **25 GB** of chips. On a laptop that takes
about 8–10 days, so split it into slices that run at the same time. Every command below runs from the
repository root.

## 1. Set up once

```bash
git clone https://github.com/FelixYu120/DSC-291-Final-Project.git
cd DSC-291-Final-Project
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev,presto]"
python scripts/get_data.py --scope all --plan     # offline check: 11,364 records, size and time estimate
```

Use a disk with at least 40 GB free (chips, the catalogue cache of about 3 GB, the features and the database).

## 2. Download

Pick the way that fits the machine. Both run **N slices**; more slices finish sooner, but Earth Search is a
free public service, so stay at or below 16.

| Machine | Command | Notes |
|---|---|---|
| Any Linux machine or a long-running cluster session | `bash scripts/cluster/run_batches.sh 10` | Runs 10 slices in parallel in the background of this shell. Use `tmux` or `screen` so a closed connection does not stop it. Logs: `data/runs/download/batch_<i>_of_10.log`. |
| Several machines | `bash scripts/cluster/run_batches.sh 10 1 5` on one, `... 10 6 10` on the other | Each machine takes its part of the same 10 slices. |
| A SLURM cluster | `python scripts/models/get_presto.py`, `mkdir -p data/runs/download`, then `sbatch scripts/cluster/download_all.sbatch` | 16 array tasks of about 700 records each. Add your `--account` / `--partition` lines to the file first. |

**Progress, at any time** (it only reads files, so it is safe while the download runs):

```bash
python scripts/get_data.py --scope all --status
```

**After a stop, a time limit or a failed slice:** run the same command again. Finished records are reused
(checked by SHA-256 and a read-back); records with a failed scene are tried again.

**Expected gaps, not errors:** Earth Search Collection 1 holds almost no scenes for Jan–Nov 2022, so most
Malawi 2022 and Lacuna 2022 records end with `no_scenes` or few months (`docs/DECISIONS.md`, 29 Oct).

## 3. Features and database

When `--status` shows no `not_on_disk` left:

```bash
bash scripts/cluster/after_download.sh --refit   # ONCE: MOSAIKS filters drawn from the full data, then the database
```

`--refit` replaces the MOSAIKS filters fitted on the 48 pilot records with filters from 64 random chips of
the full data. Do it **once**: new filters change every MOSAIKS feature. Every later run (for example after
re-downloading a few records) is `bash scripts/cluster/after_download.sh` without `--refit`.

## 4. Share the result with the team

Teammates do not need the 25 GB of chips to model. Share the two small outputs through the team drive or
a shared cluster folder, never through git (both are git-ignored):

| File | What | Who needs it |
|---|---|---|
| `data/cropyield.duckdb` | every table and view (`SELECT * FROM master`) | everyone: notebook 04, all models |
| `data/features/mosaiks/` | MOSAIKS filters and features | only who rebuilds the database |

Notebooks 00–03 read the chips themselves, so they need `data/imagery/` (or run them on the cluster).
