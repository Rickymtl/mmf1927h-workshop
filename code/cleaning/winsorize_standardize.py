"""Outlier treatment & cross-sectional standardization — #13.

Day 2 (slides 19–20, 27) requires:

1. **Per-date cross-sectional winsorization** at p1/p99 on every continuous
   feature before Day 3 touches them.  Winsorize, don't trim — extreme values
   are capped, not dropped (slide 20: "reach for trimming only when values are
   known data errors").

2. **Cross-sectional standardization** — percentile-rank (0–1) within each
   Friday's cross-section.  Rank-based is the natural fit for this project's
   Rank-IC evaluation (slide 27: "rank-based for anything feeding a rank/IC-
   based evaluation").

3. **Sector neutralization** (optional) — demean within GICS sector on each
   date so a feature isn't just reflecting "which sector was hot that day."

This module is imported by ``build_panel.py`` (#4) during the final stage
before the analysis-ready panel is written.

-----
Usage
-----

::

    from cleaning.winsorize_standardize import apply_all

    panel = apply_all(
        panel,
        value_columns=["weekly_return", "trends_interest", "gdelt_tone", "gdelt_volume"],
        sector_column="sector",
        lower=0.01,
        upper=0.99,
        sector_neutralize=True,
    )
"""

from __future__ import annotations

import pandas as pd


def winsorize_cross_section(
    df: pd.DataFrame,
    columns: list[str],
    date_column: str = "date",
    lower: float = 0.01,
    upper: float = 0.99,
) -> pd.DataFrame:
    """Per-date cross-sectional winsorization.

    For each *date* independently, cap values in *columns* at the *lower*-th
    and *upper*-th percentiles of that day's cross-section.

    Parameters
    ----------
    df : pd.DataFrame
        Long-form panel with *date_column* and *columns*.
    columns : list[str]
        Column names to winsorize.
    date_column : str
        Name of the date column (default ``"date"``).
    lower : float
        Lower percentile (default 0.01 → 1st percentile).
    upper : float
        Upper percentile (default 0.99 → 99th percentile).

    Returns
    -------
    pd.DataFrame
        Copy of *df* with winsorized columns added as ``{col}_wins``.
    """
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        wins_col = f"{col}_wins"
        out[wins_col] = out.groupby(date_column)[col].transform(
            lambda x: x.clip(
                lower=x.quantile(lower),
                upper=x.quantile(upper),
            )
        )
    return out


def rank_standardize(
    df: pd.DataFrame,
    columns: list[str],
    date_column: str = "date",
) -> pd.DataFrame:
    """Cross-sectional percentile-rank standardization.

    For each date, rank every value in *columns* and scale to [0, 1].
    Ties get the average rank (pandas default).

    Parameters
    ----------
    df : pd.DataFrame
    columns : list[str]
        Column names to rank-standardize.  These should be the winsorized
        columns (``{col}_wins``) when called after ``winsorize_cross_section``.
    date_column : str

    Returns
    -------
    pd.DataFrame
        Copy with new columns ``{col}_rank`` in [0, 1].
    """
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        rank_col = f"{col}_rank"
        # rank(pct=True) gives [0, 1] percentile ranks per group
        out[rank_col] = out.groupby(date_column)[col].rank(pct=True)
    return out


def sector_neutralize(
    df: pd.DataFrame,
    columns: list[str],
    sector_column: str = "sector",
    date_column: str = "date",
) -> pd.DataFrame:
    """Sector-neutralize features by demeaning within sector×date.

    For each date, subtract the sector-mean of each column so that the
    resulting value captures *within-sector* relative strength rather
    than which sector happened to be hot that day.

    Parameters
    ----------
    df : pd.DataFrame
    columns : list[str]
        Column names to sector-neutralize (typically the rank columns).
    sector_column : str
    date_column : str

    Returns
    -------
    pd.DataFrame
        Copy with new columns ``{col}_sector_neutral``.
    """
    out = df.copy()
    for col in columns:
        if col not in out.columns or sector_column not in out.columns:
            continue
        neutral_col = f"{col}_sector_neutral"
        sector_mean = out.groupby([date_column, sector_column])[col].transform("mean")
        out[neutral_col] = out[col] - sector_mean
    return out


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def apply_all(
    df: pd.DataFrame,
    value_columns: list[str] | None = None,
    sector_column: str = "sector",
    date_column: str = "date",
    lower: float = 0.01,
    upper: float = 0.99,
    sector_neutralize_flag: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Run the full winsorize → rank → sector-neutralize pipeline.

    This is the function ``build_panel.py`` (#4) calls as its final step
    before writing the analysis-ready panel.

    Parameters
    ----------
    df : pd.DataFrame
        Long-form weekly panel with *date_column*, *value_columns*, and
        (if *sector_neutralize_flag*) *sector_column*.
    value_columns : list[str] or None
        Columns to process.  Defaults to the four standard panel columns:
        ``weekly_return``, ``trends_interest``, ``gdelt_tone``, ``gdelt_volume``.
    sector_column : str
    date_column : str
    lower : float
        Winsorization lower bound.
    upper : float
        Winsorization upper bound.
    sector_neutralize_flag : bool
        Whether to produce sector-neutral variants.

    Returns
    -------
    df : pd.DataFrame
        Enriched panel with ``_wins``, ``_rank``, and optionally
        ``_sector_neutral`` columns.
    report : dict
        Summary for the data-quality memo (#14).
    """
    if value_columns is None:
        value_columns = [
            "weekly_return",
            "trends_interest",
            "gdelt_tone",
            "gdelt_volume",
        ]

    # Keep only columns that actually exist in the frame.
    present = [c for c in value_columns if c in df.columns]
    if not present:
        return df.copy(), {
            "step": "winsorize_standardize",
            "error": "no value columns found in panel",
        }

    original_cols = set(df.columns)

    # --- 1. Winsorize ----------------------------------------------------
    df = winsorize_cross_section(
        df, columns=present, date_column=date_column, lower=lower, upper=upper
    )
    wins_cols = [f"{c}_wins" for c in present]

    # --- 2. Rank-standardize ---------------------------------------------
    df = rank_standardize(df, columns=wins_cols, date_column=date_column)
    rank_cols = [f"{c}_rank" for c in wins_cols]

    # --- 3. Sector-neutralize (optional) ---------------------------------
    if sector_neutralize_flag and sector_column in df.columns:
        df = sector_neutralize(
            df, columns=rank_cols,
            sector_column=sector_column, date_column=date_column,
        )

    # --- Report ----------------------------------------------------------
    n_dates = df[date_column].nunique()
    n_tickers = df["ticker"].nunique() if "ticker" in df.columns else 0

    original_cols = set(df.columns)

    report = {
        "step": "winsorize_standardize",
        "method": (
            f"per-date winsorization at p{lower}-p{upper}, "
            "percentile-rank standardization, "
            + ("sector-neutralized" if sector_neutralize_flag else "not sector-neutralized")
        ),
        "winsorization": {
            "lower": lower,
            "upper": upper,
            "columns_processed": present,
        },
        "standardization": "percentile-rank (rank-based → natural fit for Rank IC)",
        "sector_neutralization": (
            "applied — demean within sector×date"
            if sector_neutralize_flag
            else "not applied"
        ),
        "n_dates": n_dates,
        "n_tickers": n_tickers,
        "output_columns": sorted(set(df.columns) - original_cols),
    }
    return df, report
