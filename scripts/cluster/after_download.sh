#!/usr/bin/env bash
# Steps 2 and 3 after a download: MOSAIKS features, then the database.
#
#   bash scripts/cluster/after_download.sh --refit   # ONCE, after the full download: new MOSAIKS filters
#                                                   # drawn from the full data instead of the 48-record pilot
#   bash scripts/cluster/after_download.sh           # every later run: reuse those filters
#
# Extra arguments go to scripts/features/mosaiks_features.py. Close every notebook connection to
# data/cropyield.duckdb first: the database file is rebuilt from scratch.
set -euo pipefail
cd "$(dirname "$0")/../.."                      # the repository root
PYTHON=${PYTHON:-python}
SCOPE=${SCOPE:-all}

"$PYTHON" scripts/get_data.py --scope "$SCOPE" --status
"$PYTHON" scripts/features/mosaiks_features.py "$@"
"$PYTHON" scripts/build_database.py
