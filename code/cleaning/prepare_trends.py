"""Stage raw Trends CSVs into the form ``build_panel.py`` consumes.

Replaces the anchor-rescaling step (``rescale_trends.py``).

Why no rescaling any more
-------------------------
Trends were originally pulled in batches sharing the anchor keyword
``"stock market"``, which peaks at 100 in every request.  Google normalises
the 0-100 index *within* each request, so company names with far less search
volume were quantised into {0,1,2} — 7 tickers became perfectly constant and
a third of the cross-section was tied at zero every week.  The anchor was
added to make batches comparable and instead destroyed the signal.

The fix is to pull **one ticker per request**, so each series is normalised
to its own peak and keeps full resolution.  That leaves levels incomparable
across tickers — but they were never comparable anyway (keywords differ in
ambiguity: "Apple" catches the fruit, "Welltower" does not), and every Trends
feature we build is a *within-ticker* anomaly, which cancels the scale factor
exactly.  So no rescaling step is needed at all.

Source preference per ticker (``--source best``, the default):
    1. ``data/raw/trends_single/``  — one-request-per-ticker (preferred)
    2. ``data/raw/trends/``         — legacy anchored batch pull (fallback)

Writes ``data/processed/trends_rescaled/<TICKER>.csv`` with the column name
``build_panel.py`` expects, plus ``trends_source.json`` recording which pull
each ticker came from.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_code_dir = Path(__file__).resolve().parent.parent
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

from paths import PROCESSED_DIR, RAW_DIR, rel, utc_now_iso

SINGLE_DIR = RAW_DIR / "trends_single"
ANCHORED_DIR = RAW_DIR / "trends"
OUT_DIR = PROCESSED_DIR / "trends_rescaled"

_SKIP = {"provenance", "cross_sectional_summary", "manifest"}


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    return df[["date", "search_interest"]].sort_values("date")


def _available(directory: Path) -> dict[str, Path]:
    if not directory.exists():
        return {}
    return {
        f.stem: f
        for f in directory.glob("*.csv")
        if f.stem not in _SKIP and not f.stem.startswith("_")
    }


def prepare(source: str = "best") -> dict:
    single, anchored = _available(SINGLE_DIR), _available(ANCHORED_DIR)
    if source == "single":
        chosen = {t: ("single", p) for t, p in single.items()}
    elif source == "anchored":
        chosen = {t: ("anchored", p) for t, p in anchored.items()}
    else:
        chosen = {t: ("anchored", p) for t, p in anchored.items()}
        chosen.update({t: ("single", p) for t, p in single.items()})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.csv"):
        stale.unlink()

    manifest: dict[str, dict] = {}
    for ticker, (src, path) in sorted(chosen.items()):
        df = _load(path)
        # No transformation — the column is renamed only because build_panel
        # still expects the historical name from the rescaling era.
        out = df.rename(columns={"search_interest": "search_interest_rescaled"})
        out.to_csv(OUT_DIR / f"{ticker}.csv", index=False)
        s = df["search_interest"]
        manifest[ticker] = {
            "source": src,
            "rows": int(len(df)),
            "distinct": int(s.nunique()),
            "zero_pct": round(100 * (s == 0).mean(), 1),
            "constant": bool(s.nunique() == 1),
        }

    n_single = sum(1 for m in manifest.values() if m["source"] == "single")
    record = {
        "prepared_at_utc": utc_now_iso(),
        "source_mode": source,
        "note": "No rescaling applied; see module docstring.",
        "n_tickers": len(manifest),
        "n_from_single_request": n_single,
        "n_from_anchored_legacy": len(manifest) - n_single,
        "n_constant_columns": sum(1 for m in manifest.values() if m["constant"]),
        "tickers": manifest,
    }
    (OUT_DIR / "trends_source.json").write_text(json.dumps(record, indent=2))

    print(f"[trends] staged {len(manifest)} tickers -> {rel(OUT_DIR)}")
    print(f"  single-request: {n_single}   legacy anchored: {len(manifest) - n_single}")
    print(f"  constant (zero-information) columns: {record['n_constant_columns']}")
    med = pd.Series([m["distinct"] for m in manifest.values()]).median()
    print(f"  median distinct values: {med:.0f}")
    return record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=["best", "single", "anchored"], default="best",
                   help="Which raw pull to stage (default: best available per ticker).")
    args = p.parse_args(argv)
    prepare(args.source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
