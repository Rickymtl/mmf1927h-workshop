"""Pull raw OHLCV price data from Yahoo Finance (yfinance).

One raw CSV per ticker under data/raw/prices/, plus a provenance log. No
cleaning or adjustment happens here — that is Session 2's job.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
import yfinance as yf

from paths import PRICES_DIR, rel, utc_now_iso, write_provenance
from universe import all_tickers


def pull_ticker(ticker: str, start: str, end: str | None, interval: str) -> pd.DataFrame:
    """Download one ticker's OHLCV history. Raises on empty result."""
    df = yf.download(
        ticker,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=False,  # keep raw Close and Adj Close; adjust in Session 2
        progress=False,
        threads=False,
    )
    if df.empty:
        raise ValueError(f"No data returned for {ticker!r} ({start} .. {end}).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "Date"
    return df


def pull_prices(tickers: list[str], start: str, end: str, interval: str) -> dict:
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    provenance = {
        "pulled_at_utc": utc_now_iso(),
        "source": "Yahoo Finance via yfinance",
        "yfinance_version": yf.__version__,
        "start": start,
        "end": end,
        "interval": interval,
        "tickers": {},
    }
    failures: list[str] = []
    for ticker in tickers:
        try:
            df = pull_ticker(ticker, start, end, interval)
        except Exception as exc:  # noqa: BLE001 — log and continue
            print(f"[prices FAIL] {ticker}: {exc}", file=sys.stderr)
            failures.append(ticker)
            continue
        csv_path = PRICES_DIR / f"{ticker}.csv"
        df.to_csv(csv_path)
        provenance["tickers"][ticker] = {
            "rows": int(len(df)),
            "first_date": str(df.index.min().date()),
            "last_date": str(df.index.max().date()),
            "file": rel(csv_path),
        }
        print(f"[prices OK]   {ticker}: {len(df)} rows -> {rel(csv_path)}")

    provenance["failures"] = failures
    write_provenance(PRICES_DIR, provenance)
    return provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", nargs="+", default=None,
                   help="Tickers to pull (default: full 88-name universe).")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default=None, help="Exclusive end date; default today.")
    p.add_argument("--interval", default="1d")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from datetime import datetime, timezone

    args = parse_args(argv)
    tickers = args.tickers or all_tickers()
    end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prov = pull_prices(tickers, args.start, end, args.interval)
    print(f"\n[prices] provenance -> {rel(PRICES_DIR / 'provenance.json')}")
    return 1 if prov["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
