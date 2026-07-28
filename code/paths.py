"""Shared filesystem paths and helpers for the data-sourcing scripts.

Everything under data/raw/ is gitignored — raw pulls are regenerable and must
never be committed (they can also be large and, for licensed feeds, non-
redistributable). See .gitignore.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PRICES_DIR = RAW_DIR / "prices"
TRENDS_DIR = RAW_DIR / "trends"
NEWS_DIR = RAW_DIR / "news"

# --- Study horizon -----------------------------------------------------------
# Every source is pulled over the same 5-year window so the panel is balanced
# and no source silently contributes extra history.
#
# Why 2021-08-01 → 2026-07-27: Google Trends is the binding constraint. A
# fixed, absolute window so re-pulls are deterministic — no rolling "today 5-y"
# drift. 2021-08-01 is the nearest clean month boundary inside the 5-year
# lookback from mid-2026.
#
# Deliberately FIXED dates, not "today minus 5 years": a moving window would
# make the dataset non-reproducible, which defeats the point-in-time discipline
# the rest of the pipeline is built around. Bump explicitly if the study window
# should move.
HORIZON_START = "2021-08-01"
HORIZON_END = "2026-07-27"
HORIZON_TIMEFRAME = f"{HORIZON_START} {HORIZON_END}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    """Path relative to the repo root, for logging."""
    return str(path.relative_to(REPO_ROOT))


def write_provenance(directory: Path, record: dict) -> Path:
    """Write a provenance.json log into `directory` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    prov_path = directory / "provenance.json"
    prov_path.write_text(json.dumps(record, indent=2))
    return prov_path
