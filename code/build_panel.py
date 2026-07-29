"""Build the weekly Friday-to-Friday analysis-ready panel — #4.

The core Session 2 deliverable: **Validate → Align → Impute/Winsorize →
Analysis-ready** across all three sources, producing a single
``panel_weekly.parquet`` that Day 3 reads directly.

Alignment rules (from the README)
---------------------------------
.. list-table::
   :header-rows: 1

   * - Series
     - Native
     - Aligned to weekly by
   * - Prices
     - daily
     - compound daily log returns within the week (require ≥3 of 5 days)
   * - Trends
     - weekly (Sun→Sun)
     - already weekly — map week-start Sunday to week-ending Friday
   * - GDELT tone
     - daily
     - mean over the week
   * - GDELT volume
     - daily
     - sum over the week

No lookahead: features for week ``t`` use only information up to that Friday's
close.  The target is the **following** week's return (``t+1``), never
contemporaneous.

.. note::

   GDELT is **not yet integrated** — the pull (#2) is still blocked on a
   stable residential connection.  This script produces a prices+trends panel
   now; the GDELT join is a ``# TODO(#2)`` block that uncomments when the
   raw CSVs land in ``data/raw/gdelt/``.

Output
------
``data/processed/panel_weekly.parquet`` — tidy long-form with columns:

- ``week_ending_friday`` — the Friday that closes the observation week
- ``ticker``
- ``sector`` — GICS sector name
- ``weekly_return`` — compound daily log return over Mon–Fri
- ``trends_interest`` — rescaled Google Trends search interest (ratio units)
- ``gdelt_tone`` — mean daily tone over the week *(future)*
- ``gdelt_volume`` — total article count over the week *(future)*
- ``_wins``, ``_rank``, ``_sector_neutral`` variants (from #13)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Allow running from repo root or code/ directly.
_code_dir = Path(__file__).resolve().parent
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

import numpy as np
import pandas as pd

from paths import (
    HORIZON_START,
    HORIZON_END,
    PRICES_DIR,
    TRENDS_DIR,
    GDELT_DIR,
    PROCESSED_DIR,
    rel,
    utc_now_iso,
)
from universe import all_tickers, ticker_to_sector
from cleaning.impute import (
    apply_price_policy,
    apply_trends_policy,
    apply_gdelt_policy,
    build_imputation_report,
)
from cleaning.winsorize_standardize import apply_all as apply_winsorize_standardize

PANEL_DIR = PROCESSED_DIR / "panel"
RETURNS_CSV = PROCESSED_DIR / "returns" / "daily_returns.csv"
TRENDS_RESCALED_DIR = PROCESSED_DIR / "trends_rescaled"

# Minimum fraction of trading days required to keep a week.
MIN_DAYS_FRACTION = 0.6  # → 3 of 5 days
MIN_HISTORY_DAYS = 252  # ≈ 1 year — tickers with less are flagged, not dropped


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_commit_hash() -> str:
    """Return the current HEAD commit hash (short form)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _week_ending_friday(date: pd.Timestamp) -> pd.Timestamp:
    """Map any date to its week-ending Friday.

    Monday→Thursday map forward to the same week's Friday.
    Friday maps to itself.  Saturday/Sunday map to the *next* Friday.
    """
    # pandas: Monday=0, Friday=4, Saturday=5, Sunday=6
    dow = date.dayofweek
    if dow <= 4:  # Mon–Fri
        return date + pd.Timedelta(days=4 - dow)
    else:  # Sat–Sun → next Friday
        return date + pd.Timedelta(days=(11 - dow))


# ---------------------------------------------------------------------------
# Validation (lightweight — detailed validation is in dedicated scripts)
# ---------------------------------------------------------------------------


def _validate_inputs() -> dict:
    """Check that required raw/processed files exist.  Returns a coverage dict."""
    issues: list[str] = []
    tickers = all_tickers()

    # Prices
    price_tickers = {
        f.stem for f in PRICES_DIR.glob("*.csv")
        if f.name != "provenance.json"
    }
    missing_prices = set(tickers) - price_tickers
    if missing_prices:
        issues.append(f"{len(missing_prices)} tickers missing price CSV")

    # Trends
    trend_tickers = {
        f.stem for f in TRENDS_RESCALED_DIR.glob("*.csv")
        if f.name not in ("provenance.json", "cross_sectional_summary.csv")
    }
    missing_trends = set(tickers) - trend_tickers
    if missing_trends:
        issues.append(f"{len(missing_trends)} tickers missing rescaled Trends CSV")

    # GDELT
    gdelt_tickers = {
        f.stem for f in GDELT_DIR.glob("*.csv")
        if f.name != "provenance.json"
    }
    gdelt_available = len(gdelt_tickers) > 0
    missing_gdelt = set(tickers) - gdelt_tickers if gdelt_available else set(tickers)

    return {
        "n_tickers": len(tickers),
        "n_price_tickers": len(price_tickers),
        "n_trends_tickers": len(trend_tickers),
        "n_gdelt_tickers": len(gdelt_tickers),
        "gdelt_available": gdelt_available,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Build — prices
# ---------------------------------------------------------------------------


def _build_price_weekly(returns_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily log returns to weekly, Friday-to-Friday.

    Requires ≥3 of 5 trading days per ticker-week.  Weeks with fewer valid
    days are dropped.
    """
    df = returns_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].apply(_week_ending_friday)

    # Count valid trading days per ticker-week.
    valid = df.dropna(subset=["daily_return"])
    day_counts = valid.groupby(["ticker", "week"]).size()
    min_days = day_counts.groupby("week").transform(
        lambda x: max(3, np.ceil(x.max() * MIN_DAYS_FRACTION))
    )
    keep_mask = day_counts >= min_days
    valid_weeks = day_counts[keep_mask].reset_index()[["ticker", "week"]]

    # Compound daily log returns within each valid week.
    weekly = (
        valid.merge(valid_weeks, on=["ticker", "week"])
        .groupby(["ticker", "week"])["daily_return"]
        .sum()
        .reset_index()
        .rename(columns={"daily_return": "weekly_return"})
    )

    return weekly


# ---------------------------------------------------------------------------
# Build — trends
# ---------------------------------------------------------------------------


def _build_trends_weekly() -> pd.DataFrame:
    """Load rescaled Trends CSVs and map week-start Sunday → week-ending Friday.

    Trends dates are Sundays (the start of the 7-day bucket).  The Friday that
    *ends* that bucket is Sunday + 5 days.
    """
    frames: list[pd.DataFrame] = []
    for f in TRENDS_RESCALED_DIR.glob("*.csv"):
        ticker = f.stem
        if ticker in ("provenance", "cross_sectional_summary"):
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        df["ticker"] = ticker
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    trends = pd.concat(frames, ignore_index=True)
    trends = trends.rename(columns={"search_interest_rescaled": "trends_interest"})

    # Map Sunday week-start → Friday week-end.
    # Sunday is dayofweek=6.  Friday is 4.  Sunday + 5 = Friday.
    trends["week"] = trends["date"].apply(
        lambda d: d + pd.Timedelta(days=5)
    )

    return trends[["ticker", "week", "trends_interest"]]


# ---------------------------------------------------------------------------
# Build — GDELT (future, placeholder)
# ---------------------------------------------------------------------------


def _build_gdelt_weekly() -> pd.DataFrame | None:
    """Aggregate GDELT daily tone/volume to weekly.

    Returns None if no GDELT CSVs are on disk (the current state until #2
    resolves).
    """
    csvs = list(GDELT_DIR.glob("*.csv"))
    if not csvs:
        return None

    frames: list[pd.DataFrame] = []
    for f in csvs:
        ticker = f.stem
        if ticker == "provenance":
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        df["ticker"] = ticker
        frames.append(df)

    if not frames:
        return None

    gdelt = pd.concat(frames, ignore_index=True)
    gdelt["week"] = gdelt["date"].apply(_week_ending_friday)

    weekly = (
        gdelt.groupby(["ticker", "week"])
        .agg(gdelt_tone=("tone", "mean"), gdelt_volume=("volume", "sum"))
        .reset_index()
    )
    return weekly


# ---------------------------------------------------------------------------
# Master build
# ---------------------------------------------------------------------------


def build_panel(
    min_history_days: int = MIN_HISTORY_DAYS,
) -> tuple[pd.DataFrame, dict]:
    """Build the full analysis-ready weekly panel.

    Parameters
    ----------
    min_history_days : int
        Minimum number of trading days of price history before a ticker enters
        the modeling cross-section.  Default 252 (≈1 year).

    Returns
    -------
    panel : pd.DataFrame
    provenance : dict
    """
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    commit = _git_commit_hash()

    # --- Validate -----------------------------------------------------------
    coverage = _validate_inputs()
    if coverage["issues"]:
        print("[panel] ⚠️  validation issues:")
        for issue in coverage["issues"]:
            print(f"[panel]    {issue}")

    # --- Load & align prices ------------------------------------------------
    print("[panel] loading daily returns …")
    returns_df = pd.read_csv(RETURNS_CSV, parse_dates=["date"])

    # Filter to study horizon.
    returns_df = returns_df[
        (returns_df["date"] >= HORIZON_START)
        & (returns_df["date"] <= HORIZON_END)
    ]

    # Impute: apply price missing-data policy (#12).
    returns_df, price_impute_report = apply_price_policy(returns_df)

    # Aggregate to weekly.
    price_weekly = _build_price_weekly(returns_df)
    print(f"[panel]   price weekly: {len(price_weekly)} rows, "
          f"{price_weekly['ticker'].nunique()} tickers")

    # --- Load & align trends ------------------------------------------------
    print("[panel] loading rescaled Trends …")
    trends_weekly = _build_trends_weekly()

    # Filter to study horizon (Trends weeks may slightly exceed).
    trends_weekly = trends_weekly[
        (trends_weekly["week"] >= HORIZON_START)
        & (trends_weekly["week"] <= HORIZON_END)
    ]

    # Impute: apply trends missing-data policy (#12).
    trends_weekly, trends_impute_report = apply_trends_policy(
        trends_weekly, value_col="trends_interest", date_col="week"
    )
    print(f"[panel]   trends weekly: {len(trends_weekly)} rows, "
          f"{trends_weekly['ticker'].nunique()} tickers")

    # --- Load & align GDELT (future) ----------------------------------------
    gdelt_weekly = _build_gdelt_weekly()
    gdelt_impute_report: dict = {"source": "gdelt", "status": "not_available"}
    if gdelt_weekly is not None:
        gdelt_weekly, gdelt_impute_report = apply_gdelt_policy(
            gdelt_weekly, method="zero"
        )
        print(f"[panel]   gdelt weekly: {len(gdelt_weekly)} rows")
    else:
        print("[panel]   ⚠️  GDELT not available — panel built without news features")

    # --- Join ---------------------------------------------------------------
    print("[panel] joining sources …")
    sector_map = ticker_to_sector()

    # Start with prices (the most reliable source).
    panel = price_weekly.copy()

    # Add sector.
    panel["sector"] = panel["ticker"].map(sector_map)

    # Merge Trends (left join — keep every price row).
    panel = panel.merge(trends_weekly, on=["ticker", "week"], how="left")

    # Merge GDELT if available.
    if gdelt_weekly is not None:
        panel = panel.merge(gdelt_weekly, on=["ticker", "week"], how="left")
    else:
        panel["gdelt_tone"] = np.nan
        panel["gdelt_volume"] = np.nan

    # --- Minimum-history threshold ------------------------------------------
    # Count trading days per ticker BEFORE the first week.
    history_days = (
        returns_df.dropna(subset=["daily_return"])
        .groupby("ticker")
        .size()
    )
    short_tickers = set(history_days[history_days < min_history_days].index)
    if short_tickers:
        print(f"[panel]   ⚠️  {len(short_tickers)} ticker(s) below "
              f"{min_history_days}-day threshold: {sorted(short_tickers)}")
        # We flag them but do NOT drop — that's a Day 3 modeling decision.

    # --- Imputation report --------------------------------------------------
    imputation_report = build_imputation_report(
        price_impute_report, trends_impute_report, gdelt_impute_report
    )

    # --- Winsorize & standardize (#13) --------------------------------------
    value_cols = ["weekly_return", "trends_interest"]
    if gdelt_weekly is not None:
        value_cols += ["gdelt_tone", "gdelt_volume"]

    panel, ws_report = apply_winsorize_standardize(
        panel,
        value_columns=value_cols,
        sector_column="sector",
        date_column="week",
        lower=0.01,
        upper=0.99,
        sector_neutralize_flag=True,
    )

    # --- Provenance ---------------------------------------------------------
    provenance = {
        "step": "build_panel",
        "git_commit": commit,
        "timestamp_utc": utc_now_iso(),
        "horizon_start": HORIZON_START,
        "horizon_end": HORIZON_END,
        "min_days_per_week": MIN_DAYS_FRACTION,
        "min_history_days": min_history_days,
        "alignment": "weekly Friday-to-Friday, no lookahead",
        "target_definition": (
            "raw weekly log return (continuous).  Chosen over classification "
            "or ordinal because: (a) preserves magnitude information for "
            "Day 4 portfolio construction, (b) natural fit for Rank IC "
            "evaluation (we rank predictions, not binarize them), "
            "(c) simpler — fewer moving parts than triple-barrier labels."
        ),
        "coverage": coverage,
        "tickers_below_history_threshold": sorted(short_tickers),
        "n_rows": len(panel),
        "n_tickers": int(panel["ticker"].nunique()),
        "n_weeks": int(panel["week"].nunique()),
        "date_range": [
            str(panel["week"].min().date()),
            str(panel["week"].max().date()),
        ],
        "sources": {
            "prices": "daily_returns.csv → compounded weekly",
            "trends": "trends_rescaled/ → Sun→Fri mapping",
            "gdelt": (
                "daily tone/volume → mean/sum weekly"
                if gdelt_weekly is not None
                else "NOT AVAILABLE — pending #2"
            ),
        },
        "imputation": imputation_report,
        "winsorize_standardize": ws_report,
    }

    # --- Save ---------------------------------------------------------------
    panel = panel.sort_values(["week", "ticker"]).reset_index(drop=True)
    panel = panel.rename(columns={"week": "week_ending_friday"})

    parquet_path = PANEL_DIR / "panel_weekly.parquet"
    panel.to_parquet(parquet_path, index=False)
    print(f"[panel] saved → {rel(parquet_path)}")

    # Lineage manifest alongside the panel.
    manifest_path = PANEL_DIR / "panel_weekly_manifest.json"
    manifest_path.write_text(json.dumps(provenance, indent=2))
    print(f"[panel] manifest → {rel(manifest_path)}")

    # Quick summary.
    print(
        f"[panel] done: {len(panel):,} rows × {len(panel.columns)} cols, "
        f"{panel['ticker'].nunique()} tickers, "
        f"{panel['week_ending_friday'].nunique()} weeks"
    )
    return panel, provenance


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--min-history", type=int, default=MIN_HISTORY_DAYS,
        help=f"Minimum price-history days before a ticker enters (default {MIN_HISTORY_DAYS}).",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Print the provenance record as JSON and exit.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    panel, provenance = build_panel(min_history_days=args.min_history)

    if args.json:
        print(json.dumps(provenance, indent=2))

    # Non-zero exit if there are validation issues worth investigating.
    issues = provenance["coverage"].get("issues", [])
    if issues:
        print(f"\n[panel] ⚠️  {len(issues)} validation issue(s) — see above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
