#!/usr/bin/env bash
# The full Sentinel-2 download as a SLURM job array: array task i runs slice i of N.
#
# Once, before submitting (from the repository root):
#     python scripts/models/get_presto.py      # the tasks skip it, so they never download it together
#     mkdir -p data/runs/download              # SLURM writes the logs there
# Then:
#     sbatch scripts/cluster/download_all.sbatch
#     python scripts/get_data.py --scope all --status      # progress, any time
# After a stop or a failed task, submit again: finished records are reused.
#
# Add the lines your cluster needs, for example #SBATCH --account=... or #SBATCH --partition=...
#SBATCH --job-name=s2-download
#SBATCH --array=1-16
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=24:00:00
#SBATCH --output=data/runs/download/slurm_%A_%a.log
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi

N=${SLURM_ARRAY_TASK_COUNT:-16}                  # the size of --array above
python scripts/get_data.py --scope all --batch "${SLURM_ARRAY_TASK_ID}/${N}" --skip-presto
