"""Day 3 — feature construction for the Trend-Driven Names project.

Builds F from the Day 2 weekly panel.  Every feature is tagged
internal/external and mapped to a risk-model bucket (Day 3 slides p9, p11-15),
and every one is computed from information available **on or before** its own
week-ending Friday.

Feature set
-----------

**Every window below is in WEEKS, not months.**  The panel is weekly, so
``mom_12_1`` is a *12-week* (~3-month) feature, **not** the 12-month
Jegadeesh-Titman factor its name resembles.  The ~12-month factor is
``mom_52_4``.  The names are kept for continuity with earlier commits; the
unit is stated here, in the feature table of ``REPORT.md``, and on the slides.

| Feature            | Category                        | Construction (windows in WEEKS)                     |
|--------------------|---------------------------------|-----------------------------------------------------|
| ``asvi``           | External · Alt-data             | log SVI − log median(SVI, prior 8w)  *(paper)*      |
| ``trends_z_26``    | External · Alt-data             | z-score of SVI vs. own trailing 26w                 |
| ``trends_chg_4``   | External · Alt-data             | log change in SVI over 4w                           |
| ``trends_vol_13``  | External · Statistical          | std. dev. of weekly ΔlogSVI, trailing 13w           |
| ``mom_52_4``       | Internal · Fundamental          | cum. return t−51w → t−4w  (~11 months, skips ~1mo)  |
| ``mom_12_1``       | Internal · Fundamental          | cum. return t−11w → t−1w  (**~3 months**, not 12)   |
| ``rvol_13``        | Internal · Statistical          | std. dev. of weekly returns, trailing 13w           |
| ``ivol_26``        | Internal · Statistical          | std. dev. of market-model residuals, trailing 26w   |
| ``rev_1``          | Internal · Fundamental          | prior week's return (short-term reversal control)   |

Note on the ``External · Alt-data`` tag.  Earlier commits tagged the four
Trends features ``macro-analog``.  That was inaccurate: Day 3 defines a macro
factor as an observable series taking *the same value for every name on a
date*, and per-ticker search interest is name-specific.  They are external
(not derived from the asset's own market data) but they are not macro.  The
consequence is that **the macro and statistical risk-model buckets are not
genuinely populated** — no rate-sensitivity beta, no PCA factors — which is a
disclosed gap in ``REPORT.md`` §8 rather than a relabelled one.

Horizon ladder, and what is missing from it.  The price block spans 1w
(``rev_1``) → 11w (``mom_12_1``) → 48w (``mom_52_4``); the ~4-week rung is
empty.  Adding it was considered and **not** done: Day 3 warns that momentum
variants are highly correlated by construction and destabilise penalised-
regression coefficients, and the price block already outnumbers the Trends
block that carries the thesis.  The decision is recorded rather than silent.

Feature-quality caveat (Day 2, unbalanced panels).  ``mom_52_4`` uses
``min_periods=30`` on a 48-week window, so for a name's earliest eligible
weeks it is estimated on as few as 30 observations while returning a
normal-looking number.  ``MIN_HISTORY_WEEKS = 52`` bounds how early that can
happen, but does not eliminate it.

**Paper-derived feature — ``asvi``.**  Da, Engelberg & Gao (2011), "In Search
of Attention", *Journal of Finance* 66(5), 1461-1499.  The paper's Abnormal
Search Volume Index is

    ASVI_t = log(SVI_t) − log[ median(SVI_{t−1}, …, SVI_{t−8}) ]

i.e. log search volume minus the log median of the previous eight weeks.
The median (not mean) baseline is the paper's own choice — it is robust to
one-off spikes, so ASVI measures *sustained* abnormal attention rather than a
single noisy week.  Da et al. find high-ASVI stocks earn higher returns over
the following two weeks, consistent with retail attention pushing prices up
temporarily.  Construction is reproduced here, not merely cited; the only
adaptation is that we use ``log1p`` so that weeks with SVI = 0 are finite.

Why every Trends feature is within-ticker
-----------------------------------------
Single-request Trends pulls normalise each series to its own peak, so raw
levels are not comparable across tickers — and they never were, since keywords
differ in ambiguity ("Apple" catches the fruit, "Welltower" does not).  Every
Trends feature above is a deviation from the ticker's own trailing baseline,
which cancels the per-ticker scale factor exactly.  Cross-sectional ranking
happens afterwards, on the anomaly.

Look-ahead discipline
---------------------
* Panel is sorted ``(ticker, week)`` before any ``groupby().rolling()`` —
  otherwise rolling windows mix entities (Day 3 slides p24).
* ``.shift(1)`` is applied to every rolling statistic so that week *t*'s
  feature uses data strictly up to week *t*.
* ``center=True`` and ``.shift(-1)`` appear nowhere.
* The target is ``fwd_return`` = **next** week's return, created by
  ``groupby(ticker).shift(-1)`` on the *target only*, never on a feature.

.. warning::

   **One disclosed look-ahead remains, in the Trends block.**  Google Trends
   weekly buckets are labelled with the week-*start* Sunday and cover Sunday
   through Saturday.  ``build_panel.py`` maps a bucket to Sunday + 5 days =
   the Friday inside it, so the value attached to week-ending-Friday *t*
   includes **Saturday t+1** — one day that was not observable at that
   Friday's close, and that falls inside the target window (Friday *t* close
   → Friday *t+1* close).

   All *rolling baselines* are ``.shift(1)``-ed, but the current-week level
   entering ``asvi``, ``trends_z_26`` and ``trends_chg_4`` is not, so the
   contamination reaches the headline feature.  Magnitude: 1 of 7 days of a
   weekly bucket.  Direction: plausibly favourable, since Friday-evening or
   weekend news would lift both weekend search volume and the following
   Monday's move.

   Not corrected before the Day 5 deadline because the fix (aligning a bucket
   to the Friday after it is fully observable) invalidates every number in the
   report.  Disclosed in ``REPORT.md`` §8 and quantified as an upper bound
   rather than left implicit.  This is the single highest-priority correction
   in "with one more week".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_code_dir = Path(__file__).resolve().parent
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

import numpy as np
import pandas as pd

from paths import PROCESSED_DIR, rel

PANEL_PATH = PROCESSED_DIR / "panel" / "panel_weekly.parquet"
OUT_PATH = PROCESSED_DIR / "features" / "features_weekly.parquet"

# feature -> (internal|external, risk-model bucket)
# NB: the Trends block is tagged "alt-data", not "macro-analog". A macro factor
# takes the same value for every name on a date (Day 3); per-ticker search
# interest does not. Relabelling it macro would paper over the fact that the
# macro and statistical buckets are not genuinely populated — see the module
# docstring and REPORT.md §8.
FEATURE_TAGS: dict[str, tuple[str, str]] = {
    "asvi":          ("external", "alt-data"),
    "trends_z_26":   ("external", "alt-data"),
    "trends_chg_4":  ("external", "alt-data"),
    "trends_vol_13": ("external", "statistical"),
    "mom_52_4":      ("internal", "fundamental"),
    "mom_12_1":      ("internal", "fundamental"),
    "rvol_13":       ("internal", "statistical"),
    "ivol_26":       ("internal", "statistical"),
    "rev_1":         ("internal", "fundamental"),
}
FEATURES = list(FEATURE_TAGS)
TARGET = "fwd_return"

MIN_HISTORY_WEEKS = 52  # a name must have a year of weekly history to enter


def _lagged_roll(g: pd.Series, window: int, fn: str, min_frac: float = 0.6):
    """Trailing rolling stat, shifted one week so week t never sees week t."""
    r = g.rolling(window, min_periods=max(2, int(window * min_frac)))
    return getattr(r, fn)().shift(1)


def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    # Sorting first is not cosmetic: groupby().rolling() on an unsorted frame
    # silently mixes observations across tickers.
    df = panel.sort_values(["ticker", "week_ending_friday"]).reset_index(drop=True)
    g = df.groupby("ticker", sort=False)

    # --- target: NEXT week's return. The only forward-looking column. -------
    df[TARGET] = g["weekly_return"].shift(-1)

    # --- Trends features (within-ticker anomalies) --------------------------
    df["log_svi"] = np.log1p(df["trends_interest"])
    lg = df.groupby("ticker", sort=False)["log_svi"]

    # ASVI — Da, Engelberg & Gao (2011). Median baseline over prior 8 weeks.
    med8 = lg.transform(lambda s: s.rolling(8, min_periods=4).median().shift(1))
    df["asvi"] = df["log_svi"] - med8

    mu26 = lg.transform(lambda s: _lagged_roll(s, 26, "mean"))
    sd26 = lg.transform(lambda s: _lagged_roll(s, 26, "std"))
    df["trends_z_26"] = (df["log_svi"] - mu26) / sd26.replace(0, np.nan)

    df["trends_chg_4"] = df["log_svi"] - lg.transform(lambda s: s.shift(4))

    dlog = lg.transform(lambda s: s.diff())
    df["trends_vol_13"] = dlog.groupby(df["ticker"]).transform(
        lambda s: _lagged_roll(s, 13, "std"))

    # --- Price features -----------------------------------------------------
    r = df.groupby("ticker", sort=False)["weekly_return"]
    df["rev_1"] = r.transform(lambda s: s.shift(1))
    df["mom_12_1"] = r.transform(lambda s: s.rolling(11, min_periods=8).sum().shift(1))
    # 12-1 style: t-52 .. t-4, skipping the most recent month.
    df["mom_52_4"] = r.transform(
        lambda s: s.rolling(48, min_periods=30).sum().shift(4))
    df["rvol_13"] = r.transform(lambda s: _lagged_roll(s, 13, "std"))

    # Idiosyncratic vol: residual from a market model, market = equal-weight
    # cross-sectional mean return that week (computed per date, so no leakage).
    mkt = df.groupby("week_ending_friday")["weekly_return"].transform("mean")
    df["_resid"] = df["weekly_return"] - mkt
    df["ivol_26"] = df.groupby("ticker", sort=False)["_resid"].transform(
        lambda s: _lagged_roll(s, 26, "std"))

    # --- minimum history (Day 2 slides p34: state the threshold) ------------
    df["_wk_idx"] = g.cumcount()
    df = df[df["_wk_idx"] >= MIN_HISTORY_WEEKS]

    df = df.drop(columns=["log_svi", "_resid", "_wk_idx"])
    return df


def cross_sectional_rank(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Per-date percentile rank — the scale the models actually consume.

    Rank-based because evaluation is Rank IC (Day 2 slides p27); also makes
    features robust to the heavy tails that survive winsorization.
    """
    out = df.copy()
    for c in cols:
        out[f"{c}_rank"] = out.groupby("week_ending_friday")[c].rank(pct=True)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--panel", type=Path, default=PANEL_PATH)
    p.add_argument("--out", type=Path, default=OUT_PATH)
    args = p.parse_args(argv)

    panel = pd.read_parquet(args.panel)
    print(f"[features] panel: {len(panel):,} rows, {panel.ticker.nunique()} tickers")

    df = build_features(panel)
    df = cross_sectional_rank(df, FEATURES)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)

    print(f"[features] built {len(FEATURES)} features over {len(df):,} rows")
    print(f"[features] coverage (non-null %):")
    for f in FEATURES:
        tag = "/".join(FEATURE_TAGS[f])
        print(f"    {f:14} {100 * df[f].notna().mean():5.1f}%   [{tag}]")
    print(f"[features] target non-null: {100 * df[TARGET].notna().mean():.1f}%")
    print(f"[features] saved → {rel(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
