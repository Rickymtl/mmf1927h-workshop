#!/bin/bash
# pull_trends_until_done.sh — keep resuming the Google Trends pull until all
# 88 tickers are downloaded, with cooldown sleeps between rate-limit hits.
#
# Usage:
#   bash code/pull_trends_until_done.sh
#
# Log output goes to data/raw/trends/pull.log so you can tail it or check
# later.  Exit code 0 when complete, 1 if something breaks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG="$PROJECT_DIR/data/raw/trends/pull.log"
TOTAL=88

mkdir -p "$(dirname "$LOG")"

log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
count() {
  find "$PROJECT_DIR/data/raw/trends" -maxdepth 1 -name '*.csv' ! -name '_anchor*' 2>/dev/null | wc -l | tr -d ' '
}

PYTHON="$PROJECT_DIR/.venv/bin/python3"
PULL="$PROJECT_DIR/code/pull_trends.py"

cd "$PROJECT_DIR"

log "=== starting unattended trends pull (target: $TOTAL tickers) ==="

downloaded=$(count)
log "already downloaded: $downloaded"

while [ "$downloaded" -lt "$TOTAL" ]; do
  missing=$((TOTAL - downloaded))
  log "--- $missing remaining, running batch ---"

  set +e
  "$PYTHON" "$PULL" \
    --max-batches 5 \
    --sleep 60 \
    --retries 3 \
    >> "$LOG" 2>&1
  rc=$?
  set -e

  new_count=$(count)
  gained=$((new_count - downloaded))
  downloaded=$new_count
  log "batch result: exit=$rc, gained=$gained, total=$downloaded/$TOTAL"

  if [ "$downloaded" -ge "$TOTAL" ]; then
    log "=== DONE: all $TOTAL tickers downloaded ==="
    exit 0
  fi

  if [ "$gained" -eq 0 ]; then
    cooldown=$((40 * 60))
    log "no progress (rate-limited), cooling down ${cooldown}s"
  else
    cooldown=$((15 * 60))
    log "made progress, cooling down ${cooldown}s"
  fi

  sleep "$cooldown"
done

log "=== DONE: all $TOTAL tickers downloaded ==="
exit 0
