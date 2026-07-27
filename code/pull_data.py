"""Session 1 — Data Sourcing: pull raw OHLCV price data.

Downloads daily OHLCV bars for a configurable ticker universe from Yahoo
Finance and writes one raw CSV per ticker, plus a provenance log recording
exactly what was pulled and when.

Day 1 principle: respect point-in-time from the start and document provenance.
A sourcing mistake here propagates through every later stage of the pipeline,
so this script only *sources* raw data — no cleaning, alignment, or imputation.
That is Session 2's job.

Usage:
    python code/pull_data.py                      # default demo universe
    python code/pull_data.py --tickers AAPL MSFT  # custom tickers
    python code/pull_data.py --start 2015-01-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

# Project layout: this file lives in <repo>/code, raw data goes to <repo>/data/raw.
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"

# Default demo universe (the 11 SPDR sector ETFs — Option 2 in the Day 1 deck).
# Swap this for whatever universe your group's chosen project path needs.
DEFAULT_TICKERS = [
    "XLB", "XLC", "XLE", "XLF", "XLI",
    "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="Ticker symbols to download (default: 11 SPDR sector ETFs).",
    )
    parser.add_argument(
        "--start",
        default="2010-01-01",
        help="Start date, YYYY-MM-DD (inclusive).",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="End date, YYYY-MM-DD (exclusive). Default: today.",
    )
    parser.add_argument(
        "--interval",
        default="1d",
        help="Bar interval, e.g. 1d, 1wk, 1mo (default: 1d).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=RAW_DIR,
        help=f"Output directory for raw CSVs (default: {RAW_DIR}).",
    )
    return parser.parse_args(argv)


def pull_ticker(ticker: str, start: str, end: str | None, interval: str) -> pd.DataFrame:
    """Download one ticker's OHLCV history. Raises on empty result."""
    df = yf.download(
        ticker,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=False,  # keep raw Close and Adj Close both; adjust in Session 2
        progress=False,
        threads=False,
    )
    if df.empty:
        raise ValueError(f"No data returned for {ticker!r} ({start} .. {end}).")
    # yfinance returns a column MultiIndex for single tickers in recent versions;
    # flatten to plain OHLCV column names so the raw CSV is easy to read back.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "Date"
    return df


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    pulled_at = datetime.now(timezone.utc).isoformat()
    provenance: dict = {
        "pulled_at_utc": pulled_at,
        "source": "Yahoo Finance via yfinance",
        "yfinance_version": yf.__version__,
        "start": args.start,
        "end": end,
        "interval": args.interval,
        "tickers": {},
    }

    failures: list[str] = []
    for ticker in args.tickers:
        try:
            df = pull_ticker(ticker, args.start, end, args.interval)
        except Exception as exc:  # noqa: BLE001 — log and continue, don't abort the batch
            print(f"[FAIL] {ticker}: {exc}", file=sys.stderr)
            failures.append(ticker)
            continue

        csv_path = out_dir / f"{ticker}.csv"
        df.to_csv(csv_path)
        provenance["tickers"][ticker] = {
            "rows": int(len(df)),
            "first_date": str(df.index.min().date()),
            "last_date": str(df.index.max().date()),
            "file": str(csv_path.relative_to(REPO_ROOT)),
        }
        print(f"[OK]   {ticker}: {len(df)} rows -> {csv_path.relative_to(REPO_ROOT)}")

    prov_path = out_dir / "provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2))
    print(f"\nProvenance log written to {prov_path.relative_to(REPO_ROOT)}")

    if failures:
        print(f"\n{len(failures)} ticker(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
