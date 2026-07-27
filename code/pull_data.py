"""Session 1 — Data Sourcing orchestrator.

Runs all three raw-data pulls for the project's universe (8 largest names per
GICS sector):

    prices   Yahoo Finance OHLCV        (code/pull_prices.py)
    trends   Google Trends interest     (code/pull_trends.py)
    news     Alpha Vantage sentiment    (code/pull_news.py)

Each source writes raw files + a provenance.json under data/raw/<source>/.
Everything under data/raw/ is gitignored.

Usage:
    python code/pull_data.py                       # all sources, full universe
    python code/pull_data.py --sources prices      # just prices
    python code/pull_data.py --sample 8            # first 8 tickers only (a quick test)
    python code/pull_data.py --sources trends news --sample 5
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from universe import all_tickers, SECTORS
import pull_prices
import pull_trends
import pull_news

ALL_SOURCES = ("prices", "trends", "news")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sources", nargs="+", choices=ALL_SOURCES, default=list(ALL_SOURCES),
                   help="Which sources to pull (default: all).")
    p.add_argument("--sample", type=int, default=None,
                   help="Pull only the first N tickers of the universe (quick test).")
    p.add_argument("--start", default="2015-01-01", help="Price history start date.")
    p.add_argument("--trends-timeframe", default="today 5-y")
    p.add_argument("--news-limit", type=int, default=50)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tickers = all_tickers()
    if args.sample:
        tickers = tickers[: args.sample]

    print(f"Universe: {len(SECTORS)} sectors, pulling {len(tickers)} tickers.")
    print(f"Sources: {', '.join(args.sources)}\n")

    rc = 0
    if "prices" in args.sources:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rc |= pull_prices.pull_prices(tickers, args.start, end, "1d").get("failures") and 1 or 0
    if "trends" in args.sources:
        prov = pull_trends.pull_trends(tickers, args.trends_timeframe)
        rc |= 1 if prov["failures"] else 0
    if "news" in args.sources:
        prov = pull_news.pull_news(tickers, limit=args.news_limit, sleep=1.0)
        rc |= 0 if prov.get("skipped") else (1 if prov["failures"] else 0)

    print("\nDone. Raw data under data/raw/ (gitignored).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
