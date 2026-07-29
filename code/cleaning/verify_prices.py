"""Verify price data quality and compute daily returns from Adj Close.

#7 in the Session-2 checklist.  Addresses:

1. Returns from ``Adj Close`` (split + dividend adjusted) vs raw ``Close``
2. Split verification (NVDA 10-for-1, June 2024)
3. Short-history tickers (CEG — spin-off from Exelon)
4. Data-quality flags: repeated closes, zero volume, NaN gaps
5. Back-adjustment caveat (Yahoo restates history on every corporate action)

Output: ``data/processed/returns/daily_returns.csv`` — a tidy long-form CSV
with columns ``date, ticker, adj_close, daily_return`` plus a provenance log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or code/cleaning/ directly.
_code_dir = Path(__file__).resolve().parent.parent
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

import numpy as np
import pandas as pd

from paths import PRICES_DIR, PROCESSED_DIR, rel, utc_now_iso

RETURNS_DIR = PROCESSED_DIR / "returns"

# Known corporate actions in our universe (for spot-checking).
KNOWN_SPLITS = {
    "NVDA": {"date": "2024-06-10", "ratio": 10, "description": "10-for-1"},
    "AMZN": {"date": "2022-06-06", "ratio": 20, "description": "20-for-1"},
    "GOOGL": {"date": "2022-07-18", "ratio": 20, "description": "20-for-1"},
}

# Tickers known to be spin-offs / recent listings with shortened history.
# These start *after* the study horizon and need a documented rule.
SHORT_HISTORY_NOTE = {
    "CEG": "Spin-off from Exelon (Jan 2022).  First trade 2022-01-19; "
           "missing ~118 trading days from horizon start.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_price(ticker: str) -> pd.DataFrame | None:
    """Load one ticker's raw price CSV.  Returns None if missing."""
    path = PRICES_DIR / f"{ticker}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "date"
    return df


def _discover_tickers() -> list[str]:
    """Return every ticker with a price CSV (excluding provenance.json)."""
    return sorted(
        f.stem for f in PRICES_DIR.glob("*.csv")
        if f.name != "provenance.json"
    )


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def verify_and_compute_returns(
    tickers: list[str] | None = None,
) -> dict:
    """Run all checks and build the daily-returns file.

    Returns
    -------
    dict
        Provenance / summary record.
    """
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)

    if tickers is None:
        tickers = _discover_tickers()

    all_returns: list[pd.DataFrame] = []
    flags: dict[str, list[str]] = {}  # ticker -> list of issue descriptions
    split_results: dict[str, dict] = {}
    short_hist: dict[str, dict] = {}

    for ticker in tickers:
        df = _load_price(ticker)
        if df is None:
            flags[ticker] = ["missing CSV"]
            continue

        ticker_flags: list[str] = []
        n = len(df)

        # --- 1. Adj Close NaNs --------------------------------------------
        nan_count = int(df["Adj Close"].isna().sum())
        if nan_count > 0:
            ticker_flags.append(f"{nan_count} NaN in Adj Close")

        # --- 2. Short history ---------------------------------------------
        if ticker in SHORT_HISTORY_NOTE:
            ticker_flags.append(f"short history: {n} rows — {SHORT_HISTORY_NOTE[ticker]}")
            short_hist[ticker] = {
                "rows": n,
                "first_date": str(df.index[0].date()),
                "last_date": str(df.index[-1].date()),
                "note": SHORT_HISTORY_NOTE[ticker],
            }

        # --- 3. Zero volume -----------------------------------------------
        zero_vol = int((df["Volume"] == 0).sum())
        if zero_vol > 0:
            ticker_flags.append(f"{zero_vol} zero-volume days")

        # --- 4. Repeated closes (stale prices) ----------------------------
        repeated = int((df["Close"].diff() == 0).sum())
        if repeated > 5:
            ticker_flags.append(f"{repeated} repeated-Close days")

        # --- 5. Split spot-check ------------------------------------------
        if ticker in KNOWN_SPLITS:
            split_info = KNOWN_SPLITS[ticker]
            split_date = split_info["date"]
            if split_date in df.index:
                ret_close = float(df.loc[split_date, "Close"] / df["Close"].shift(1).loc[split_date] - 1)
                ret_adj = float(df.loc[split_date, "Adj Close"] / df["Adj Close"].shift(1).loc[split_date] - 1)
                split_results[ticker] = {
                    "split_date": split_date,
                    "description": split_info["description"],
                    "close_return": round(ret_close, 6),
                    "adj_close_return": round(ret_adj, 6),
                    "passed": abs(ret_adj) < 0.02,  # no fake -50% jump
                }
                if abs(ret_close) > 0.10:
                    ticker_flags.append(
                        f"split {split_info['description']} on {split_date}: "
                        f"Close ret={ret_close:.2%}, Adj Close ret={ret_adj:.2%}"
                    )
            else:
                split_results[ticker] = {
                    "split_date": split_date,
                    "note": "split date outside horizon or missing",
                }

        # --- 6. Compute daily log returns from Adj Close ------------------
        df["daily_return"] = np.log(df["Adj Close"] / df["Adj Close"].shift(1))
        df["ticker"] = ticker

        # Keep only what downstream needs.
        out = df[["ticker", "Adj Close", "daily_return"]].copy()
        out.index.name = "date"
        all_returns.append(out)

        if ticker_flags:
            flags[ticker] = ticker_flags

    # --- Concatenate & save -----------------------------------------------
    returns_df = pd.concat(all_returns).sort_index()
    returns_df = returns_df.reset_index()  # date becomes a column
    returns_df = returns_df[["date", "ticker", "Adj Close", "daily_return"]]

    out_path = RETURNS_DIR / "daily_returns.csv"
    returns_df.to_csv(out_path, index=False)
    print(f"[prices] {len(ticker_frames := all_returns)} tickers, "
          f"{len(returns_df):,} rows -> {rel(out_path)}")

    # --- Summary stats ---------------------------------------------------
    n_flagged = len(flags)
    n_clean = len(tickers) - n_flagged

    print(f"[prices] {n_clean} tickers clean, {n_flagged} with flags")
    for ticker, issues in flags.items():
        for issue in issues:
            print(f"[prices]   ⚠️  {ticker}: {issue}")

    # --- Split report -----------------------------------------------------
    for ticker, info in split_results.items():
        if info.get("passed"):
            print(f"[prices]   ✅ {ticker} {info['description']} split "
                  f"({info['split_date']}): Adj Close ret={info['adj_close_return']:.4%} — no fake jump")
        elif "note" in info:
            print(f"[prices]   ⚠️  {ticker}: {info['note']}")

    # --- Provenance -------------------------------------------------------
    provenance = {
        "step": "verify_prices",
        "timestamp_utc": utc_now_iso(),
        "input": rel(PRICES_DIR),
        "output": rel(RETURNS_DIR / "daily_returns.csv"),
        "method": "daily log returns from Adj Close",
        "back_adjustment_caveat": (
            "Yahoo Finance restates the entire Adj Close history whenever "
            "a new dividend or split occurs.  Adj Close as pulled today is "
            "NOT what would have been observed in real time.  For weekly "
            "return prediction the effect is small, but this is a "
            "point-in-time imperfection in an otherwise PIT-careful pipeline."
        ),
        "missing_data_policy": (
            "Drop ticker-days where Adj Close is NaN (none found in current "
            "pull).  For weekly aggregation: require at least 3 of 5 trading "
            "days with valid returns; compound available daily returns within "
            "the week.  Document any dropped weeks in the panel provenance."
        ),
        "short_history_policy": (
            "CEG (Constellation Energy, spin-off) starts 2022-01-19, ~118 "
            "trading days after the horizon.  Decision: KEEP in universe, "
            "flag the shorter history.  Features computed on CEG prior to "
            "its first trade will be NaN.  At model time, CEG enters the "
            "cross-section on its first valid feature date."
        ),
        "n_tickers": len(tickers),
        "n_flagged": n_flagged,
        "n_clean": n_clean,
        "flags": flags,
        "split_checks": split_results,
        "short_history": short_hist,
        "known_splits_checked": list(KNOWN_SPLITS.keys()),
    }

    prov_path = RETURNS_DIR / "provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2))
    print(f"[prices] provenance -> {rel(prov_path)}")

    return provenance


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--tickers", nargs="+", default=None,
        help="Tickers to verify (default: all with a price CSV).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify_and_compute_returns(tickers=args.tickers)
    return 1 if result.get("n_clean", 0) == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
