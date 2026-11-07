# Replaying the recorded Zimbabwe experiments after the merge

Main now includes both the Zimbabwe experiments and the earlier quality-review work. The quality review strengthens
`src/cropyield/data/labels.py` and improves the missing-database message in `xy.py`. Their hashes therefore differ from
the source files recorded by the historical Zimbabwe experiments, even though the frozen data and saved results have not changed.
The original experiment checks correctly reject that code mismatch. We preserve those checks and manifests.

Use the recorded-code runner for the published steps 9–13:

```bash
python scripts/reproduce_zimbabwe.py verify-compact
python scripts/reproduce_zimbabwe.py verify-weather
python scripts/reproduce_zimbabwe.py candidate
```

The runner extracts source, scripts, configurations and documentation from commit
`e1235944f092359e4ed29d3ef20cef1f17085d10` into a temporary directory. It reuses the current data files through a directory
link and verifies 329 recorded inputs/outputs against manifests read from Git history, before and after execution.
This requires the complete repository history and the existing team database. No branch checkout, worktree,
dependency installation or weather download is performed. The active checkout stays on main with its stronger validation code.

Each invocation writes to a new destination under `data/runs/reproductions/`, or a new path supplied with `--output`.
An adjacent `.reproduction.json` receipt records the historical commit, runner hash and verification count.
Existing destinations are refused. Verifier side files stay in the temporary directory, so the original validation receipts
and weather-support tables are not overwritten.

To repeat model training, choose the corresponding stage. These runs can take substantially longer than verification:

| Stage | Original entry point | Output type |
|---|---|---|
| `merge` | Step 9 | New experiment directory |
| `diagnosis` | Step 10 | New experiment directory |
| `weather` | Step 11, offline from saved cache | New weather-data directory |
| `weather-models` | Step 12 | New experiment directory |
| `compact` | Step 13 | New experiment directory |
| `verify-weather` | Independent full-weather verifier | JSON receipt |
| `verify-compact` | Independent compact-weather verifier | JSON receipt |
| `candidate` | Post-hoc benchmark comparison | CSV comparisons |

For example:

```bash
python scripts/reproduce_zimbabwe.py compact --output data/runs/zimbabwe_compact_replay
```

These stages replay the recorded version with its recorded upstream releases; they do not silently switch a later stage
to a newly generated upstream variant. A deliberately changed experiment needs its own configuration, inputs and release.
The old protocol files and their embedded commands describe the historical revision. Directly running them against
modified source on main is not a replay of that revision.

The step-8 midterm handoff is separate: its output hashes remain intact, and the guide checks them. Its recorded decision
and evaluation documents predate the consolidated experiment commit. To generate a new handoff using current source and
documentation, run step 8 with a new `--output` directory; do not replace the historical handoff manifest.

The default [Zimbabwe notebook](../notebooks/data_guide_2_zimbabwe.ipynb) needs no database or historical checkout:
it reads the saved outputs and recomputes the displayed checks and scores. The historical replay is for full provenance
verification or retraining, not a prerequisite for reading the notebook.

Integration verification receipts are in `results/integration/main_merge_20261107/`. They document verification of the
existing experiments, not new performance estimates or new use of the reserved target fold.
