"""Session 1 — Data Sourcing orchestrator.

Runs the raw-data pulls for the project's universe (8 largest names per GICS
sector):

    prices   Yahoo Finance OHLCV            daily   (code/pull_prices.py)
    trends   Google Trends interest         weekly  (code/pull_trends.py)
    gdelt    GDELT news tone + volume       daily   (code/pull_gdelt.py)
    news     Alpha Vantage article sentiment event  (code/pull_news.py)

`gdelt` is the primary news-sentiment source: it is pre-aggregated to daily and
covers 2017-present with no API key. `news` (Alpha Vantage) is article-level and
only reaches back a day or two per request on the free tier — useful as a
richer, headline-level cross-check on recent data, not as the history.

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

from paths import HORIZON_START
from universe import all_tickers, SECTORS
import pull_prices
import pull_trends
import pull_gdelt
import pull_news

ALL_SOURCES = ("prices", "trends", "gdelt", "news")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sources", nargs="+", choices=ALL_SOURCES, default=list(ALL_SOURCES),
                   help="Which sources to pull (default: all).")
    p.add_argument("--sample", type=int, default=None,
                   help="Pull only the first N tickers of the universe (quick test).")
    p.add_argument("--start", default=HORIZON_START,
                   help=f"Price history start (default: study horizon, {HORIZON_START}).")
    p.add_argument("--trends-timeframe", default="today 5-y")
    p.add_argument("--gdelt-start", default=HORIZON_START,
                   help=f"GDELT history start (default: study horizon, {HORIZON_START}).")
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
    if "gdelt" in args.sources:
        prov = pull_gdelt.pull_gdelt(tickers, start=args.gdelt_start)
        rc |= 1 if prov["failures"] else 0
    if "news" in args.sources:
        prov = pull_news.pull_news(tickers, limit=args.news_limit, sleep=1.0)
        rc |= 0 if prov.get("skipped") else (1 if prov["failures"] else 0)

    print("\nDone. Raw data under data/raw/ (gitignored).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
