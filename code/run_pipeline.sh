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

# --- preconditions, with actionable errors -------------------------------
fail() { echo; echo "ERROR: $1" >&2; echo; exit 1; }

[ -x "$PY" ] || fail "No virtualenv at .venv/
  Create it:
    python3.11 -m venv .venv
    ./.venv/bin/pip install -r requirements.txt
  On macOS LightGBM also needs the OpenMP runtime:  brew install libomp"

"$PY" -c "import pandas, sklearn, lightgbm, scipy, statsmodels, pyarrow" 2>/dev/null \
  || fail "Missing Python dependencies.
    ./.venv/bin/pip install -r requirements.txt
  If lightgbm fails to import on macOS:  brew install libomp"

if [ -z "$(ls -A "$REPO/data/raw/prices" 2>/dev/null)" ]; then
    fail "No price data in data/raw/prices/ (not committed — 26 MB, regenerable).
  Pull it (~2 minutes, no rate limit):
    ./.venv/bin/python code/pull_prices.py"
fi

if [ -z "$(ls -A "$REPO/data/raw/trends_single" 2>/dev/null)" ] \
   && [ -z "$(ls -A "$REPO/data/raw/trends" 2>/dev/null)" ]; then
    fail "No Trends data found.
  data/raw/trends_single/ ships with the repo — if it is missing, re-clone.
  To re-pull from scratch (slow: Google caps ~19 requests per ~2.5h per IP):
    ./.venv/bin/python code/pull_trends.py"
fi

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
