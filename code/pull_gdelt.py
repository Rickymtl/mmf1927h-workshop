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
from collections.abc import Iterator

import pandas as pd
import requests

from paths import HORIZON_END, HORIZON_START, RAW_DIR, rel, utc_now_iso, write_provenance
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
MIN_THROTTLE_COOLDOWN = 60.0


def _fmt(ts: pd.Timestamp) -> str:
    """GDELT wants YYYYMMDDHHMMSS."""
    return ts.strftime("%Y%m%d%H%M%S")


def _timeline_points(payload: dict, mode: str) -> list[dict]:
    """Extract timeline points while rejecting unexpected response shapes."""
    timeline = payload.get("timeline")
    if timeline is None:
        raise ValueError(f"{mode}: response has no 'timeline' field")
    if not isinstance(timeline, list):
        raise ValueError(f"{mode}: 'timeline' is not a list")
    if not timeline:
        return []

    for series in timeline:
        if isinstance(series, dict) and isinstance(series.get("data"), list):
            return series["data"]
    raise ValueError(f"{mode}: no timeline series contains a data list")


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
        throttled = False
        try:
            resp = requests.get(ENDPOINT, params=params, timeout=90, headers=_HEADERS)
            # GDELT signals rate limiting with a 429 *and* sometimes with a
            # 200 carrying a plain-text body, so check the content type too.
            if resp.status_code == 429 or not resp.text.lstrip().startswith("{"):
                snippet = resp.text.strip()[:100]
                throttled = (
                    resp.status_code == 429
                    or "limit requests" in snippet.lower()
                    or "rate limit" in snippet.lower()
                )
                print(f"    attempt {attempt}/{retries}: throttled/non-JSON: {snippet}",
                      file=sys.stderr)
            else:
                payload = resp.json()
                return _timeline_points(payload, mode)
        except Exception as exc:  # noqa: BLE001
            print(f"    attempt {attempt}/{retries}: {exc}", file=sys.stderr)

        if attempt < retries:
            wait = sleep * (2 ** (attempt - 1)) + random.uniform(0, sleep)
            if throttled:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = max(wait, float(retry_after))
                except (TypeError, ValueError):
                    wait = max(wait, MIN_THROTTLE_COOLDOWN)
            print(f"    backing off {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
    return None


def _to_series(points: list[dict], name: str) -> pd.Series:
    """Convert GDELT timeline points into a daily-indexed Series."""
    if name not in MODES:
        raise ValueError(f"unknown GDELT series: {name}")
    if not points:
        return pd.Series(dtype="float64", name=name)

    df = pd.DataFrame(points)
    missing = {"date", "value"} - set(df.columns)
    if missing:
        raise ValueError(f"{name}: timeline points missing field(s): {', '.join(sorted(missing))}")

    # GDELT currently returns values such as 20240101T000000Z. Keep mixed
    # parsing because the API has historically varied the timestamp shape.
    idx = pd.to_datetime(df["date"], format="mixed", utc=True, errors="coerce")
    values = pd.to_numeric(df["value"], errors="coerce")
    invalid = idx.isna() | values.isna()
    if invalid.any():
        examples = df.loc[invalid, ["date", "value"]].head(3).to_dict("records")
        raise ValueError(f"{name}: invalid date/value point(s): {examples}")
    if name == "volume" and (values < 0).any():
        raise ValueError("volume: negative article count returned")

    daily_index = pd.DatetimeIndex(idx).tz_localize(None).normalize()
    series = pd.Series(values.to_numpy(dtype=float), index=daily_index, name=name)
    # Tone is an average; volume is a count. This matters if GDELT ever returns
    # sub-daily buckets or duplicate points inside one response.
    aggregation = "mean" if name == "tone" else "sum"
    return series.groupby(level=0).agg(aggregation)


def _chunk_ranges(
    start: pd.Timestamp, end: pd.Timestamp, chunk_months: int
) -> Iterator[tuple[pd.Timestamp, pd.Timestamp]]:
    """Yield inclusive, non-overlapping calendar ranges."""
    if chunk_months < 1:
        raise ValueError("chunk_months must be at least 1")
    if start > end:
        raise ValueError("start must be on or before end")

    lo = start
    while lo <= end:
        hi = min(lo + pd.DateOffset(months=chunk_months) - pd.Timedelta(days=1), end)
        yield lo, hi
        lo = hi + pd.Timedelta(days=1)


def pull_gdelt(
    tickers: list[str],
    start: str = HORIZON_START,
    end: str = HORIZON_END,
    chunk_months: int = 12,
    sleep: float = 6.0,
    retries: int = 4,
    finance_filter: bool = True,
    resume: bool = True,
) -> dict:
    GDELT_DIR.mkdir(parents=True, exist_ok=True)
    if retries < 1:
        raise ValueError("retries must be at least 1")
    if sleep < 0:
        raise ValueError("sleep must be non-negative")

    end_ts = pd.Timestamp(end)
    start_ts = max(pd.Timestamp(start), pd.Timestamp(EARLIEST))
    chunks = list(_chunk_ranges(start_ts, end_ts, chunk_months))

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
        "chunk_months": chunk_months,
        "sleep_seconds": sleep,
        "finance_filter": finance_filter,
        "note": ("tone = daily average tone of matching coverage; volume = daily "
                 "raw article count. Coverage starts 2017-01-01."),
        "tickers": {},
    }
    failures: list[str] = []

    for ti, ticker in enumerate(tickers, start=1):
        query = gdelt_query(ticker, finance_filter=finance_filter)
        print(f"[gdelt] {ti}/{len(tickers)} {ticker}: {query}")
        frames: dict[str, list[pd.Series]] = {"tone": [], "volume": []}
        ticker_failed = False

        for col, mode in MODES.items():
            for lo, hi in chunks:
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
    p.add_argument("--end", default=HORIZON_END,
                   help=f"History end (default: fixed study horizon, {HORIZON_END}).")
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
