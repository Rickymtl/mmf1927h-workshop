"""Missing-data policy & imputation — #12 in the Session-2 checklist.

Day 2 (slides 15–18) requires every missing value classified under Rubin's
taxonomy (MCAR / MAR / MNAR) **before** choosing an imputation method.  This
module documents the classification and provides the functions that
``build_panel.py`` (#4) calls during the Impute/Winsorize stage.

-----
Policy (per source)
-----

.. list-table::
   :header-rows: 1

   * - Source
     - Pattern
     - Mechanism
     - Method
     - Max gap
   * - Prices (Adj Close / daily returns)
     - CEG: no data before 2022-01-19 (spin-off).  No other ticker has gaps.
     - Structural (not random — firm didn't exist)
     - Leave NaN.  CEG enters on first valid date per min-history rule (#4).
     - ∞ (never forward-fill prices)
   * - Trends (search_interest_rescaled)
     - CEG: zeros before 2022-01-19 (no search interest for a firm that didn't
       exist).  All other zeros (rare) are genuine low-interest weeks.
     - MNAR-adjacent (zero = genuinely low interest, not a feed outage)
     - Treat zero as real signal.  CEG pre-listing zeros are structural —
       recode to NaN so they don't get treated as "zero interest."
     - N/A (zeros are signal, not missingness)
   * - GDELT (tone, volume)
     - Days where no articles match the query → tone=NaN, volume=NaN.
       Scope unknown until #2 completes.
     - Likely MAR or MNAR — depends whether no-article days correlate with
       the return being predicted.
     - Two defensible paths, configurable via ``gdelt_method=``:
       (a) ``"zero"`` — tone=0, volume=0 ("no news is neutral")
       (b) ``"nan"`` — leave NaN, handle at model time
     - 5 business days (one week) if forward-filling

-----
Leakage prevention
-----

All imputation statistics are computed using only data available **on or
before the date being filled**.  For the weekly Friday-to-Friday panel this
is naturally enforced by the alignment step — no imputation routine looks
past the current Friday.  Stated here for the record; the implementation
is in ``build_panel.py``.

-----
Usage
-----

This module is **not** a standalone script.  It is imported by
``build_panel.py`` (#4) during the Impute stage::

    from cleaning.impute import (
        apply_price_policy,
        apply_trends_policy,
        apply_gdelt_policy,
    )
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Structural-zero tickers — firms that did not exist / were not listed for
# part of the study horizon.  These are NOT "missing data" in the Rubin sense;
# the firm had no price / no search interest because it didn't exist.
# ---------------------------------------------------------------------------

# (ticker, first_valid_date, reason)
_STRUCTURAL_STARTS: list[tuple[str, str, str]] = [
    (
        "CEG",
        "2022-01-19",
        "Spin-off from Exelon.  No price or Trends data before this date.",
    ),
]


def _is_structural_zero(ticker: str, date: pd.Timestamp) -> bool:
    """Return True if *date* predates *ticker*'s known first trading day."""
    for sym, first_str, _reason in _STRUCTURAL_STARTS:
        if ticker == sym and date < pd.Timestamp(first_str):
            return True
    return False


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------


def apply_price_policy(returns_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Handle missing price/return data.

    Current state (verified by ``verify_prices.py``):
    - 88 NaN rows total — all are the first row per ticker (no prior day).
    - CEG: first row 2022-01-19, ~118 trading days missing from horizon start.
    - No other tickers have NaN Adj Close or gaps.

    Policy
    ------
    - First-row NaN per ticker: left as NaN (downstream, ``build_panel.py``
      requires ≥3 of 5 valid trading days per week, so week 1 of each ticker
      drops naturally).
    - CEG pre-2022: left as NaN.  CEG enters the cross-section on its first
      valid date per the minimum-history threshold (#4).

    Parameters
    ----------
    returns_df : pd.DataFrame
        Long-form daily returns with columns ``[date, ticker, daily_return]``.

    Returns
    -------
    df : pd.DataFrame
        Same shape, with structural zeros explicitly NaN'd (already are).
    report : dict
        Summary for the data-quality memo (#14).
    """
    df = returns_df.copy()
    n_before = int(df["daily_return"].isna().sum())

    # Structural zeros: ensure they are NaN (they already are in practice,
    # but make it explicit).
    for sym, first_str, _reason in _STRUCTURAL_STARTS:
        first_date = pd.Timestamp(first_str)
        mask = (df["ticker"] == sym) & (pd.to_datetime(df["date"]) < first_date)
        df.loc[mask, "daily_return"] = pd.NA

    n_after = int(df["daily_return"].isna().sum())
    n_added = n_after - n_before

    report = {
        "source": "prices",
        "mechanism": "structural (spin-off / not-yet-listed)",
        "method": "leave NaN — ticker enters cross-section on first valid date",
        "max_gap": "∞ (never forward-fill prices)",
        "n_nan_before": n_before,
        "n_nan_after": n_after,
        "n_structural_nan_added": n_added,
        "structural_tickers": [s for s, _, _ in _STRUCTURAL_STARTS],
    }
    return df, report


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


def apply_trends_policy(
    trends_df: pd.DataFrame,
    recode_structural_zeros: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Handle Trends missingness.

    Patterns found (empirically verified):
    - CEG: ``search_interest_rescaled == 0`` for every week before 2022-01-19.
      These are structural zeros — no search interest for a firm that didn't
      exist yet.  They are NOT the same as "nobody searched for GE this week."
    - All other tickers: no zero-weeks found in current pull.  If a future
      ticker has a genuine zero week it is treated as real signal.

    Policy
    ------
    - **Structural zeros** (CEG pre-listing): recode to NaN so they are not
      confused with genuine zero-interest weeks.
    - **Genuine zeros**: treated as real signal — "nobody searched" is
      information, not missingness.  This is a modeling assumption documented
      here and in the data-quality memo (#14).

    Parameters
    ----------
    trends_df : pd.DataFrame
        Long-form with columns ``[date, ticker, search_interest_rescaled]``.
    recode_structural_zeros : bool
        If True (default), replace CEG pre-listing zeros with NaN.

    Returns
    -------
    df : pd.DataFrame
    report : dict
    """
    df = trends_df.copy()
    value_col = "search_interest_rescaled"

    n_zero_before = int((df[value_col] == 0).sum())
    n_structural_replaced = 0

    if recode_structural_zeros:
        for sym, first_str, _reason in _STRUCTURAL_STARTS:
            first_date = pd.Timestamp(first_str)
            mask = (
                (df["ticker"] == sym)
                & (pd.to_datetime(df["date"]) < first_date)
                & (df[value_col] == 0)
            )
            n_structural_replaced = int(mask.sum())
            df.loc[mask, value_col] = pd.NA

    n_zero_after = int((df[value_col] == 0).sum())

    report = {
        "source": "trends",
        "mechanism": "MNAR-adjacent (zeros = genuinely low interest, structural zeros recoded)",
        "method": (
            "zeros treated as real signal; structural pre-listing zeros "
            "replaced with NaN"
        ),
        "max_gap": "N/A (zeros are signal, not missingness)",
        "n_zero_before": n_zero_before,
        "n_zero_after": n_zero_after,
        "n_structural_replaced": n_structural_replaced,
        "structural_tickers": [s for s, _, _ in _STRUCTURAL_STARTS],
        "caveat": (
            "Treating genuine search-interest zeros as signal is a modeling "
            "assumption — there is no way to distinguish 'nobody searched' "
            "from 'data not collected' in the raw Trends index."
        ),
    }
    return df, report


# ---------------------------------------------------------------------------
# GDELT
# ---------------------------------------------------------------------------


def apply_gdelt_policy(
    gdelt_df: pd.DataFrame,
    method: str = "zero",
) -> tuple[pd.DataFrame, dict]:
    """Handle GDELT no-article days.

    GDELT returns daily tone + volume.  Days where the query matched zero
    articles have no row in the API response (or NaN values after alignment).
    These are NOT random feed outages — they mean the company was not in the
    news that day.

    Policy (two options)
    --------------------
    ``method="zero"`` (default)
        ``tone=0, volume=0`` — "no news" is treated as neutral sentiment with
        zero attention.  This keeps the panel dense and avoids dropping weeks
        where the company was simply not in the news cycle.

    ``method="nan"``
        Leave NaN.  Downstream code handles missingness at model time (e.g.,
        by skipping the ticker-week or using a missing indicator).  This is
        more conservative but creates sparse panels for low-coverage tickers.

    Parameters
    ----------
    gdelt_df : pd.DataFrame
        Long-form with columns ``[date, ticker, tone, volume]``.
    method : str
        ``"zero"`` or ``"nan"``.

    Returns
    -------
    df : pd.DataFrame
    report : dict
    """
    if method not in ("zero", "nan"):
        raise ValueError(f"method must be 'zero' or 'nan', got {method!r}")

    df = gdelt_df.copy()
    n_tone_nan = int(df["tone"].isna().sum())
    n_volume_nan = int(df["volume"].isna().sum())

    if method == "zero":
        df["tone"] = df["tone"].fillna(0.0)
        df["volume"] = df["volume"].fillna(0)
    # else "nan": leave as-is

    report = {
        "source": "gdelt",
        "mechanism": (
            "Likely MAR or MNAR — no-article days may correlate with "
            "low-volatility / low-attention periods"
        ),
        "method": (
            "fill tone=0, volume=0 (no news = neutral)"
            if method == "zero"
            else "leave NaN — handle at model time"
        ),
        "max_gap": "5 business days if forward-filling (not applied by default)",
        "n_tone_nan_before": n_tone_nan,
        "n_volume_nan_before": n_volume_nan,
        "n_tone_nan_after": int(df["tone"].isna().sum()),
        "n_volume_nan_after": int(df["volume"].isna().sum()),
        "caveat": (
            "GDELT coverage unknown until #2 completes.  Policy designed; "
            "actual NaN counts are TBD."
        ),
    }
    return df, report


# ---------------------------------------------------------------------------
# Master
# ---------------------------------------------------------------------------


def build_imputation_report(
    price_report: dict,
    trends_report: dict,
    gdelt_report: dict,
) -> dict:
    """Combine per-source reports into one provenance record.

    Written alongside the panel by ``build_panel.py`` (#4) and referenced
    by the data-quality memo (#14).
    """
    return {
        "step": "impute",
        "rubin_taxonomy_applied": True,
        "leakage_prevention": (
            "all imputation uses only data on or before the date being "
            "filled — naturally enforced by Friday-to-Friday alignment"
        ),
        "sources": {
            "prices": price_report,
            "trends": trends_report,
            "gdelt": gdelt_report,
        },
    }
