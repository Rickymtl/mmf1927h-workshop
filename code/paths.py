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
