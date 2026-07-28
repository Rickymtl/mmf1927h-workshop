"""Pull daily news tone + volume per ticker from GDELT DOC 2.0.

Why GDELT alongside Alpha Vantage
---------------------------------
Alpha Vantage NEWS_SENTIMENT returns *article-level* records and, without
time_from/time_to paging, only the most recent N articles — a day or two of
history per ticker. Rebuilding 5 years of history that way costs roughly one
request per ticker per month, which the free tier (~25 req/day) cannot fund
for an 88-name universe.

GDELT's DOC 2.0 API instead returns a **pre-aggregated daily timeline**, needs
no API key, and covers 2017-present. Two modes are pulled here:

    timelinetone     daily average tone of matching coverage  -> sentiment
    timelinevolraw   daily count of matching articles         -> attention

The volume series is a useful second signal: it is an attention measure built
from news rather than search, so it complements (and can be cross-checked
against) the Google Trends series.

Output: one CSV per ticker at data/raw/gdelt/<TICKER>.csv with columns
`date, tone, volume`, plus a provenance log.

Rate limiting
-------------
GDELT asks for **no more than one request every 5 seconds** and returns HTTP
429 with a plain-text message when you exceed it. Some shared/datacenter IPs
appear to be blocked outright regardless of pacing — if every request 429s even
at --sleep 10, try a residential connection.
"""

from __future__ import annotations

import argparse
import random
import sys
import time

import pandas as pd
import requests

from paths import HORIZON_START, RAW_DIR, rel, utc_now_iso, write_provenance
from universe import all_tickers, gdelt_query

GDELT_DIR = RAW_DIR / "gdelt"
ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
# GDELT DOC 2.0 coverage begins 2017-01-01 — a hard floor, clamped below.
# We default to HORIZON_START (later than this) to match the other sources.
EARLIEST = "2017-01-01"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

MODES = {"tone": "timelinetone", "volume": "timelinevolraw"}


def _fmt(ts: pd.Timestamp) -> str:
    """GDELT wants YYYYMMDDHHMMSS."""
    return ts.strftime("%Y%m%d%H%M%S")


def _request(query: str, mode: str, start: pd.Timestamp, end: pd.Timestamp,
             retries: int, sleep: float) -> list[dict] | None:
    """One GDELT timeline request, with backoff. Returns the data points."""
    params = {
        "query": query,
        "mode": mode,
        "format": "json",
        "startdatetime": _fmt(start),
        "enddatetime": _fmt(end),
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(ENDPOINT, params=params, timeout=90, headers=_HEADERS)
            # GDELT signals rate limiting with a 429 *and* sometimes with a
            # 200 carrying a plain-text body, so check the content type too.
            if resp.status_code == 429 or not resp.text.lstrip().startswith("{"):
                snippet = resp.text.strip()[:100]
                print(f"    attempt {attempt}/{retries}: throttled/non-JSON: {snippet}",
                      file=sys.stderr)
            else:
                payload = resp.json()
                timeline = payload.get("timeline") or []
                if not timeline:
                    # A valid response with no matching coverage.
                    return []
                return timeline[0].get("data", [])
        except Exception as exc:  # noqa: BLE001
            print(f"    attempt {attempt}/{retries}: {exc}", file=sys.stderr)

        if attempt < retries:
            wait = sleep * (2 ** (attempt - 1)) + random.uniform(0, sleep)
            print(f"    backing off {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
    return None


def _to_series(points: list[dict], name: str) -> pd.Series:
    """Convert GDELT timeline points into a daily-indexed Series."""
    if not points:
        return pd.Series(dtype="float64", name=name)
    df = pd.DataFrame(points)
    # GDELT date strings vary in shape across modes; let pandas infer.
    idx = pd.to_datetime(df["date"], format="mixed", utc=True).dt.tz_localize(None)
    series = pd.Series(df["value"].astype(float).values, index=idx.dt.normalize(), name=name)
    # Collapse any sub-daily buckets to one value per day.
    return series.groupby(level=0).mean()


def pull_gdelt(
    tickers: list[str],
    start: str = HORIZON_START,
    end: str | None = None,
    chunk_months: int = 12,
    sleep: float = 6.0,
    retries: int = 4,
    finance_filter: bool = True,
    resume: bool = True,
) -> dict:
    GDELT_DIR.mkdir(parents=True, exist_ok=True)
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.utcnow().normalize()
    start_ts = max(pd.Timestamp(start), pd.Timestamp(EARLIEST))

    if resume:
        pending = [t for t in tickers if not (GDELT_DIR / f"{t}.csv").exists()]
        if len(pending) < len(tickers):
            print(f"[gdelt] resume: skipping {len(tickers) - len(pending)} already downloaded")
        tickers = pending

    provenance = {
        "pulled_at_utc": utc_now_iso(),
        "source": "GDELT DOC 2.0 API (timelinetone + timelinevolraw)",
        "start": str(start_ts.date()),
        "end": str(end_ts.date()),
        "finance_filter": finance_filter,
        "note": ("tone = daily average tone of matching coverage; volume = daily "
                 "raw article count. Coverage starts 2017-01-01."),
        "tickers": {},
    }
    failures: list[str] = []

    # Split the range into chunks so each response stays a manageable size.
    bounds = list(pd.date_range(start_ts, end_ts, freq=f"{chunk_months}MS"))
    if not bounds or bounds[0] > start_ts:
        bounds.insert(0, start_ts)
    if bounds[-1] < end_ts:
        bounds.append(end_ts)

    for ti, ticker in enumerate(tickers, start=1):
        query = gdelt_query(ticker, finance_filter=finance_filter)
        print(f"[gdelt] {ti}/{len(tickers)} {ticker}: {query}")
        frames: dict[str, list[pd.Series]] = {"tone": [], "volume": []}
        ticker_failed = False

        for col, mode in MODES.items():
            for lo, hi in zip(bounds[:-1], bounds[1:]):
                points = _request(query, mode, lo, hi, retries, sleep)
                if points is None:
                    print(f"  [FAIL] {ticker} {col} {lo.date()}..{hi.date()}", file=sys.stderr)
                    ticker_failed = True
                    break
                frames[col].append(_to_series(points, col))
                time.sleep(sleep + random.uniform(0, sleep / 2))
            if ticker_failed:
                break

        if ticker_failed:
            failures.append(ticker)
            continue

        tone = pd.concat(frames["tone"]) if frames["tone"] else pd.Series(dtype="float64")
        vol = pd.concat(frames["volume"]) if frames["volume"] else pd.Series(dtype="float64")
        tone = tone[~tone.index.duplicated(keep="last")]
        vol = vol[~vol.index.duplicated(keep="last")]

        df = pd.DataFrame({"tone": tone, "volume": vol}).sort_index()
        df.index.name = "date"
        if df.empty:
            print(f"  [WARN] {ticker}: no coverage returned", file=sys.stderr)
            failures.append(ticker)
            continue

        csv_path = GDELT_DIR / f"{ticker}.csv"
        df.to_csv(csv_path)
        provenance["tickers"][ticker] = {
            "query": query,
            "rows": int(len(df)),
            "first_date": str(df.index.min().date()),
            "last_date": str(df.index.max().date()),
            "file": rel(csv_path),
        }
        print(f"  [OK] {ticker}: {len(df)} daily rows -> {rel(csv_path)}")

    provenance["failures"] = failures
    write_provenance(GDELT_DIR, provenance)
    print(f"\n[gdelt] {len(provenance['tickers'])} ok, {len(failures)} failed")
    return provenance


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", nargs="+", default=None)
    p.add_argument("--start", default=HORIZON_START,
                   help=f"History start (default: study horizon, {HORIZON_START}). "
                        f"Clamped to GDELT coverage floor {EARLIEST}.")
    p.add_argument("--end", default=None)
    p.add_argument("--chunk-months", type=int, default=12)
    p.add_argument("--sleep", type=float, default=6.0,
                   help="Seconds between requests; GDELT asks for >=5 (default 6).")
    p.add_argument("--retries", type=int, default=4)
    p.add_argument("--no-finance-filter", action="store_true",
                   help="Query the company name alone, without finance terms.")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--probe", action="store_true",
                   help="Make a single request and report the raw response, to "
                        "check whether this network is being throttled.")
    return p.parse_args(argv)


def _probe(sleep: float) -> int:
    """One request, verbose — for diagnosing 429 blocks."""
    q = gdelt_query("AAPL")
    print(f"Probing GDELT with query: {q}")
    params = {"query": q, "mode": "timelinetone", "format": "json",
              "startdatetime": "20240101000000", "enddatetime": "20240201000000"}
    resp = requests.get(ENDPOINT, params=params, timeout=90, headers=_HEADERS)
    print(f"HTTP {resp.status_code}, {len(resp.text)} bytes")
    print(resp.text[:400])
    ok = resp.status_code == 200 and resp.text.lstrip().startswith("{")
    print("\nRESULT:", "reachable" if ok else "throttled/blocked from this network")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.probe:
        return _probe(args.sleep)
    tickers = args.tickers or all_tickers()
    prov = pull_gdelt(
        tickers,
        start=args.start,
        end=args.end,
        chunk_months=args.chunk_months,
        sleep=args.sleep,
        retries=args.retries,
        finance_filter=not args.no_finance_filter,
        resume=not args.no_resume,
    )
    print(f"[gdelt] provenance -> {rel(GDELT_DIR / 'provenance.json')}")
    return 1 if prov["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
