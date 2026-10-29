#!/usr/bin/env bash
# Run slices FIRST..LAST of N of the Sentinel-2 download in parallel on this machine.
#
#   bash scripts/cluster/run_batches.sh 10          # all 10 slices at once on this machine
#   bash scripts/cluster/run_batches.sh 10 1 5      # slices 1-5 of 10 here, 6-10 on a second machine
#   SCOPE=pilot bash scripts/cluster/run_batches.sh 4   # a quick test on the 48 pilot records
#
# Every slice writes its log to data/runs/download/batch_<i>_of_<N>.log. After a stop, run the
# same command again: finished records are reused, failed ones are tried again.
set -euo pipefail
cd "$(dirname "$0")/../.."                      # the repository root

N=${1:?usage: run_batches.sh N [FIRST LAST]}
FIRST=${2:-1}
LAST=${3:-$N}
SCOPE=${SCOPE:-all}
PYTHON=${PYTHON:-python}
LOGS=data/runs/download
mkdir -p "$LOGS"

# The slices must not download the Presto weights at the same time, so it happens once, here.
"$PYTHON" scripts/models/get_presto.py

for i in $(seq "$FIRST" "$LAST"); do
    echo "slice $i of $N started, log: $LOGS/batch_${i}_of_${N}.log"
    "$PYTHON" scripts/get_data.py --scope "$SCOPE" --batch "$i/$N" --skip-presto > "$LOGS/batch_${i}_of_${N}.log" 2>&1 &
done
wait                                            # until every slice has stopped
"$PYTHON" scripts/get_data.py --scope "$SCOPE" --status
