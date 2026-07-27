"""Pull raw news-sentiment data from Alpha Vantage's NEWS_SENTIMENT endpoint.

Saves the raw JSON response per ticker under data/raw/news/. Sentiment scoring
is left as-is (raw) here; feature construction is Session 3.

API KEY HANDLING
----------------
The key is read from the ALPHAVANTAGE_API_KEY environment variable (loaded
from a local, gitignored .env file if present). It is NEVER written to disk,
logged, or committed. Get a free key at:
    https://www.alphavantage.co/support/#api-key
Then create a .env file (copy .env.example) containing:
    ALPHAVANTAGE_API_KEY=your_key_here

Free tier is ~25 requests/day, so pull a small sample of tickers at a time.
The deck flags newsapi.org as the thing NOT to default to — this uses Alpha
Vantage instead.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

from paths import NEWS_DIR, rel, utc_now_iso, write_provenance
from universe import all_tickers

ENDPOINT = "https://www.alphavantage.co/query"


def _load_api_key() -> str | None:
    # Load .env if python-dotenv is available; ignore if not.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return os.environ.get("ALPHAVANTAGE_API_KEY")


def pull_news(tickers: list[str], limit: int, sleep: float) -> dict:
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    api_key = _load_api_key()

    provenance = {
        "pulled_at_utc": utc_now_iso(),
        "source": "Alpha Vantage NEWS_SENTIMENT",
        "articles_limit_per_ticker": limit,
        "note": "API key read from env; not stored in this log.",
        "tickers": {},
    }

    if not api_key:
        msg = ("ALPHAVANTAGE_API_KEY not set. Copy .env.example to .env and add "
               "your free key (https://www.alphavantage.co/support/#api-key). "
               "Skipping news pull.")
        print(f"[news SKIP] {msg}", file=sys.stderr)
        provenance["skipped"] = True
        provenance["reason"] = "no ALPHAVANTAGE_API_KEY in environment"
        write_provenance(NEWS_DIR, provenance)
        return provenance

    failures: list[str] = []
    for ticker in tickers:
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "limit": str(limit),
            "apikey": api_key,
        }
        try:
            resp = requests.get(ENDPOINT, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[news FAIL] {ticker}: {exc}", file=sys.stderr)
            failures.append(ticker)
            time.sleep(sleep)
            continue

        # Alpha Vantage returns {"Note": ...} or {"Information": ...} on
        # rate-limit / bad key instead of a "feed" list.
        if "feed" not in data:
            info = data.get("Note") or data.get("Information") or data.get("Error Message") or data
            print(f"[news WARN] {ticker}: no feed returned ({info})", file=sys.stderr)
            failures.append(ticker)
            time.sleep(sleep)
            continue

        json_path = NEWS_DIR / f"{ticker}.json"
        # Strip nothing sensitive is in the response; safe to dump verbatim.
        json_path.write_text(json.dumps(data, indent=2))
        n_articles = len(data.get("feed", []))
        provenance["tickers"][ticker] = {
            "articles": n_articles,
            "file": rel(json_path),
        }
        print(f"[news OK]   {ticker}: {n_articles} articles -> {rel(json_path)}")
        time.sleep(sleep)

    provenance["failures"] = failures
    write_provenance(NEWS_DIR, provenance)
    return provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", nargs="+", default=None,
                   help="Tickers to pull (default: full universe — but mind the "
                        "free-tier ~25 req/day limit).")
    p.add_argument("--limit", type=int, default=50,
                   help="Max articles per ticker (default 50).")
    p.add_argument("--sleep", type=float, default=1.0,
                   help="Seconds between requests (default 1).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tickers = args.tickers or all_tickers()
    prov = pull_news(tickers, args.limit, args.sleep)
    print(f"\n[news] provenance -> {rel(NEWS_DIR / 'provenance.json')}")
    if prov.get("skipped"):
        return 0
    return 1 if prov["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
