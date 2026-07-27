"""Pull raw Google Trends search-interest data (pytrends).

For each ticker we request the search-interest time series for its company
keyword and save it as a raw CSV under data/raw/trends/.

BATCHING & COMPARABILITY
------------------------
Google Trends allows up to 5 keywords per request and normalises the returned
0-100 index *within each request*. That means series pulled in different
batches are NOT directly comparable out of the box.

To fix this we reserve one slot in every batch for a shared **anchor keyword**
(default "stock market"), so each batch carries a common yardstick. The anchor
series is saved per batch as `_anchor_batch<N>.csv`; Session 2 can rescale each
ticker by its batch anchor to put all 88 names on one comparable scale.

RATE LIMITING
-------------
pytrends is an unofficial scraper and Google rate-limits it hard (HTTP 429),
especially from datacenter/VPN IPs. This script:
  * retries each batch with exponential backoff + jitter,
  * sleeps between batches,
  * supports --resume so a partial run is never wasted.
If you still get persistent 429s, try a residential connection, raise --sleep,
or pull in a few sittings with --resume.
"""

from __future__ import annotations

import argparse
import random
import sys
import time

import pandas as pd

from paths import TRENDS_DIR, rel, utc_now_iso, write_provenance
from universe import all_tickers, ticker_to_keyword

# A browser-like UA makes the scraper marginally less likely to be blocked.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _make_client():
    """Build a fresh pytrends client.

    Note: do NOT pass retries/backoff_factor. pytrends 4.9.2 builds a urllib3
    Retry with the `method_whitelist` kwarg, which urllib3 2.x removed (renamed
    to `allowed_methods`) — passing them raises a TypeError. We do our own
    retry/backoff below instead.
    """
    from pytrends.request import TrendReq

    return TrendReq(hl="en-US", tz=0, requests_args={"headers": _HEADERS})


def _fetch_batch(keywords: list[str], timeframe: str, retries: int,
                 base_sleep: float) -> pd.DataFrame | None:
    """Fetch one batch of <=5 keywords, retrying with exponential backoff.

    Returns the interest-over-time frame, or None if every attempt failed.
    """
    for attempt in range(1, retries + 1):
        try:
            # A fresh client per attempt re-negotiates Google's cookie, which
            # sometimes clears a soft block.
            client = _make_client()
            client.build_payload(keywords, timeframe=timeframe)
            df = client.interest_over_time()
            if not df.empty:
                return df
            print(f"  attempt {attempt}/{retries}: empty result", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — nearly always a 429
            print(f"  attempt {attempt}/{retries}: {exc}", file=sys.stderr)

        if attempt < retries:
            # Exponential backoff with jitter: 1x, 2x, 4x, 8x ... of base_sleep.
            wait = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, base_sleep)
            print(f"  backing off {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
    return None


def pull_trends(
    tickers: list[str],
    timeframe: str,
    batch_size: int = 4,
    sleep: float = 8.0,
    retries: int = 4,
    anchor: str | None = "stock market",
    resume: bool = True,
) -> dict:
    TRENDS_DIR.mkdir(parents=True, exist_ok=True)
    kw_map = ticker_to_keyword()

    if resume:
        pending = [t for t in tickers if not (TRENDS_DIR / f"{t}.csv").exists()]
        skipped = len(tickers) - len(pending)
        if skipped:
            print(f"[trends] resume: skipping {skipped} already-downloaded ticker(s)")
        tickers = pending

    provenance = {
        "pulled_at_utc": utc_now_iso(),
        "source": "Google Trends via pytrends",
        "timeframe": timeframe,
        "anchor_keyword": anchor,
        "note": ("Interest is relative (0-100), normalised within each request. "
                 "Each batch includes the anchor keyword; rescale by the batch "
                 "anchor (_anchor_batch<N>.csv) to compare across batches."),
        "tickers": {},
    }
    failures: list[str] = []

    try:
        _make_client()
    except ImportError:
        print("[trends FAIL] pytrends not installed (pip install pytrends).", file=sys.stderr)
        provenance["failures"] = tickers
        write_provenance(TRENDS_DIR, provenance)
        return provenance

    # Reserve one of the 5 keyword slots for the anchor.
    max_tickers = 4 if anchor else 5
    batch_size = max(1, min(batch_size, max_tickers))

    n_batches = (len(tickers) + batch_size - 1) // batch_size
    for bi, i in enumerate(range(0, len(tickers), batch_size), start=1):
        batch = tickers[i : i + batch_size]
        keywords = [kw_map[t] for t in batch]
        payload = keywords + [anchor] if anchor else keywords

        print(f"[trends] batch {bi}/{n_batches}: {', '.join(batch)}")
        df = _fetch_batch(payload, timeframe, retries, sleep)

        if df is None:
            print(f"[trends FAIL] batch {bi} gave up after {retries} attempts", file=sys.stderr)
            failures.extend(batch)
            continue

        df = df.drop(columns=[c for c in ("isPartial",) if c in df.columns])

        if anchor and anchor in df.columns:
            anchor_series = df[[anchor]].rename(columns={anchor: "search_interest"})
            anchor_series.index.name = "date"
            anchor_series.to_csv(TRENDS_DIR / f"_anchor_batch{bi}.csv")

        for ticker, keyword in zip(batch, keywords):
            if keyword not in df.columns:
                print(f"[trends WARN] {ticker}: {keyword!r} missing from response", file=sys.stderr)
                failures.append(ticker)
                continue
            series = df[[keyword]].rename(columns={keyword: "search_interest"})
            series.index.name = "date"
            csv_path = TRENDS_DIR / f"{ticker}.csv"
            series.to_csv(csv_path)
            provenance["tickers"][ticker] = {
                "keyword": keyword,
                "batch": bi,
                "anchor_file": f"_anchor_batch{bi}.csv" if anchor else None,
                "rows": int(len(series)),
                "first_date": str(series.index.min().date()),
                "last_date": str(series.index.max().date()),
                "file": rel(csv_path),
            }
            print(f"[trends OK]   {ticker} ({keyword!r}): {len(series)} rows")

        if bi < n_batches:
            time.sleep(sleep + random.uniform(0, sleep / 2))

    provenance["failures"] = failures
    write_provenance(TRENDS_DIR, provenance)
    print(f"\n[trends] {len(provenance['tickers'])} ok, {len(failures)} failed")
    return provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", nargs="+", default=None,
                   help="Tickers to pull (default: full universe).")
    p.add_argument("--timeframe", default="today 5-y",
                   help="Google Trends timeframe (default: 'today 5-y').")
    p.add_argument("--batch-size", type=int, default=4,
                   help="Tickers per request; max 4 with an anchor, 5 without (default 4).")
    p.add_argument("--sleep", type=float, default=8.0,
                   help="Base seconds between batches / backoff unit (default 8).")
    p.add_argument("--retries", type=int, default=4,
                   help="Attempts per batch before giving up (default 4).")
    p.add_argument("--anchor", default="stock market",
                   help="Shared anchor keyword for cross-batch comparability. "
                        "Pass --anchor '' to disable.")
    p.add_argument("--no-resume", action="store_true",
                   help="Re-download tickers even if a CSV already exists.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tickers = args.tickers or all_tickers()
    prov = pull_trends(
        tickers,
        timeframe=args.timeframe,
        batch_size=args.batch_size,
        sleep=args.sleep,
        retries=args.retries,
        anchor=args.anchor or None,
        resume=not args.no_resume,
    )
    print(f"[trends] provenance -> {rel(TRENDS_DIR / 'provenance.json')}")
    return 1 if prov["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
