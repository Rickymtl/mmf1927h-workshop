#!/bin/bash
# End-to-end pipeline: raw data -> panel -> features -> models -> portfolio -> diagnostics.
#
# Everything downstream of the raw pulls is reproducible from this one command.
#
#   ./code/run_pipeline.sh                # use best available Trends per ticker
#   ./code/run_pipeline.sh --source single    # only one-request-per-ticker data
#   ./code/run_pipeline.sh --source anchored  # only the legacy anchored pull
#
# Prerequisites: data/raw/prices/ and at least one of data/raw/trends_single/
# or data/raw/trends/ populated (see README "Pulling raw data").

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
SOURCE="best"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source) SOURCE="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$REPO"
echo "==================================================================="
echo " MMF1927H pipeline — Trends source: $SOURCE"
echo "==================================================================="

echo
echo ">>> 1/6  verify prices & compute daily returns"
"$PY" code/cleaning/verify_prices.py | tail -3

echo
echo ">>> 2/6  stage Trends"
"$PY" code/cleaning/prepare_trends.py --source "$SOURCE"

echo
echo ">>> 3/6  build weekly panel"
"$PY" code/build_panel.py | tail -3

echo
echo ">>> 4/6  construct features"
"$PY" code/features.py | tail -4

echo
echo ">>> 5/6  fit models (walk-forward, purged + embargoed)"
"$PY" code/model.py | tail -22

echo
echo ">>> 6/6  portfolio construction + diagnostics"
"$PY" code/portfolio.py | tail -16
"$PY" code/diagnostics.py | tail -12

echo
echo "==================================================================="
echo " done — results in data/processed/{models,portfolio,diagnostics}/"
echo "==================================================================="
