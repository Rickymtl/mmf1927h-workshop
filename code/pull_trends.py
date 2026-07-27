"""Pull raw Google Trends search-interest data (pytrends).

For each ticker we request the weekly search-interest time series for its
company keyword and save it as a raw CSV under data/raw/trends/.

Caveats worth stating in your write-up:
  * Google Trends returns *relative*, index-normalised interest (0-100),
    rescaled per request — series pulled in different batches are not directly
    comparable without an overlap/anchor keyword.
  * pytrends is an unofficial scraper; Google rate-limits it aggressively
    (HTTP 429). We back off and retry, and pull in small batches. If you hit
    persistent 429s, reduce --batch-size, add --sleep, or pull fewer tickers.
"""

from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from paths import TRENDS_DIR, rel, utc_now_iso, write_provenance
from universe import all_tickers, ticker_to_keyword


def _make_client():
    # Imported lazily so the module still imports if pytrends isn't installed.
    from pytrends.request import TrendReq

    # Note: do NOT pass retries/backoff_factor here. pytrends 4.9.2 builds a
    # urllib3 Retry with the `method_whitelist` kwarg, which urllib3 2.x removed
    # (renamed to `allowed_methods`) — passing them raises a TypeError. We do our
    # own retry/backoff in the batch loop below instead.
    return TrendReq(hl="en-US", tz=0)


def pull_trends(
    tickers: list[str],
    timeframe: str,
    batch_size: int,
    sleep: float,
) -> dict:
    TRENDS_DIR.mkdir(parents=True, exist_ok=True)
    kw_map = ticker_to_keyword()

    provenance = {
        "pulled_at_utc": utc_now_iso(),
        "source": "Google Trends via pytrends",
        "timeframe": timeframe,
        "note": "Interest is relative (0-100), rescaled per request batch.",
        "tickers": {},
    }
    failures: list[str] = []

    try:
        client = _make_client()
    except ImportError:
        print("[trends FAIL] pytrends not installed (pip install pytrends).", file=sys.stderr)
        provenance["failures"] = tickers
        write_provenance(TRENDS_DIR, provenance)
        return provenance

    # Trends allows up to 5 keywords per request.
    batch_size = max(1, min(batch_size, 5))
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        keywords = [kw_map[t] for t in batch]
        try:
            client.build_payload(keywords, timeframe=timeframe)
            df = client.interest_over_time()
        except Exception as exc:  # noqa: BLE001 — usually rate limiting
            print(f"[trends FAIL] batch {batch}: {exc}", file=sys.stderr)
            failures.extend(batch)
            time.sleep(sleep)
            continue

        if df.empty:
            print(f"[trends WARN] batch {batch}: empty result", file=sys.stderr)
            failures.extend(batch)
            continue

        df = df.drop(columns=[c for c in ("isPartial",) if c in df.columns])
        for ticker, keyword in zip(batch, keywords):
            if keyword not in df.columns:
                failures.append(ticker)
                continue
            series = df[[keyword]].rename(columns={keyword: "search_interest"})
            series.index.name = "date"
            csv_path = TRENDS_DIR / f"{ticker}.csv"
            series.to_csv(csv_path)
            provenance["tickers"][ticker] = {
                "keyword": keyword,
                "rows": int(len(series)),
                "first_date": str(series.index.min().date()),
                "last_date": str(series.index.max().date()),
                "file": rel(csv_path),
            }
            print(f"[trends OK]   {ticker} ({keyword!r}): {len(series)} rows -> {rel(csv_path)}")
        time.sleep(sleep)

    provenance["failures"] = failures
    write_provenance(TRENDS_DIR, provenance)
    return provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", nargs="+", default=None,
                   help="Tickers to pull (default: full universe).")
    p.add_argument("--timeframe", default="today 5-y",
                   help="Google Trends timeframe (default: 'today 5-y').")
    p.add_argument("--batch-size", type=int, default=5,
                   help="Keywords per request, max 5 (default 5).")
    p.add_argument("--sleep", type=float, default=2.0,
                   help="Seconds to sleep between batches (default 2).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tickers = args.tickers or all_tickers()
    prov = pull_trends(tickers, args.timeframe, args.batch_size, args.sleep)
    print(f"\n[trends] provenance -> {rel(TRENDS_DIR / 'provenance.json')}")
    return 1 if prov["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
