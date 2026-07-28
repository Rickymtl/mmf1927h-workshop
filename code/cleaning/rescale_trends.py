"""Rescale Google Trends series by batch anchor for cross-batch comparability.

#3 in the Session-2 checklist.  Each Google Trends request normalises its
0-100 index *within the request*, so tickers pulled in different batches are
not directly comparable without a common yardstick.

The Day-1 puller reserved one keyword slot per batch for a shared anchor
("stock market") and saved it as ``_anchor_batch<N>.csv``.  This script:

1. loads every ticker's raw CSV and its batch anchor,
2. rescales ``search_interest_rescaled = raw / anchor``,
3. saves the rescaled series under ``data/processed/trends_rescaled/``,
4. produces a before/after diagnostic plot so you can verify batch steps
   were removed.

.. note::

   Due to the resume-based pulling strategy, many tickers lost their
   original batch anchor (overwritten by later runs).  The five surviving
   anchors are correlated at 0.9999+, so the per-batch rescaling correction
   is tiny — but the ratio method is still applied because even a 0.01%
   difference can matter in a cross-sectional ranking.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root or code/cleaning/ directly.
_code_dir = Path(__file__).resolve().parent.parent
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

import pandas as pd

from paths import TRENDS_DIR, PROCESSED_DIR, rel, utc_now_iso

RESCALED_DIR = PROCESSED_DIR / "trends_rescaled"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_provenance() -> dict:
    """Load the Trends sourcing provenance (best-effort)."""
    prov_path = TRENDS_DIR / "provenance.json"
    if not prov_path.exists():
        return {}
    with open(prov_path) as fh:
        return json.load(fh)


def _discover_tickers() -> list[str]:
    """Return every ticker that has a raw Trends CSV on disk."""
    return sorted(
        f.stem
        for f in TRENDS_DIR.glob("*.csv")
        if not f.name.startswith("_")  # exclude _anchor_batch*.csv
    )


def _discover_anchors() -> dict[int, pd.Series]:
    """Load every available batch anchor, keyed by batch number."""
    anchors: dict[int, pd.Series] = {}
    for f in sorted(TRENDS_DIR.glob("_anchor_batch*.csv")):
        # filename pattern: _anchor_batch1.csv
        try:
            batch_num = int(f.stem.split("batch")[1])
        except (IndexError, ValueError):
            continue
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        anchors[batch_num] = df["search_interest"]
    return anchors


def _deduce_batch(ticker: str, prov: dict) -> int | None:
    """Try to find which batch a ticker belongs to.

    1. Check the provenance JSON (only reliable for the *last* pull run).
    2. Fall back: match the ticker CSV's modification time against anchor
       file modification times (works for tickers pulled alongside an anchor
       that survived).
    """
    # 1) provenance (fragile — overwritten by resume runs)
    tickers = prov.get("tickers", {})
    if ticker in tickers:
        batch = tickers[ticker].get("batch")
        if batch is not None:
            return int(batch)

    # 2) file-modification-time heuristics
    ticker_path = TRENDS_DIR / f"{ticker}.csv"
    if not ticker_path.exists():
        return None
    ticker_mtime = ticker_path.stat().st_mtime

    best_batch = None
    best_delta = float("inf")
    for batch_num in _discover_anchors():
        anchor_path = TRENDS_DIR / f"_anchor_batch{batch_num}.csv"
        delta = abs(ticker_mtime - anchor_path.stat().st_mtime)
        if delta < 5.0 and delta < best_delta:  # within 5 seconds
            best_delta = delta
            best_batch = batch_num
    return best_batch


def _build_anchor(
    ticker: str,
    anchors: dict[int, pd.Series],
    prov: dict,
    use_average: bool = True,
) -> pd.Series | None:
    """Return the anchor series for *ticker*.

    When ``use_average`` is True and the ticker's batch anchor is missing,
    fall back to the element-wise mean of every available anchor (the
    anchors are virtually identical, so this is safe).
    """
    batch = _deduce_batch(ticker, prov)
    if batch is not None and batch in anchors:
        return anchors[batch]

    if use_average and anchors:
        # Build a composite anchor from the mean of all surviving anchors.
        combined = pd.DataFrame({b: a for b, a in anchors.items()})
        return combined.mean(axis=1)

    return None


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def rescale_trends(
    tickers: list[str] | None = None,
    zero_handling: str = "ffill",
    use_average_anchor: bool = True,
) -> dict:
    """Rescale every ticker's raw Trends series by its batch anchor.

    Parameters
    ----------
    tickers:
        Subset of tickers to rescale.  ``None`` means every ticker that has
        a raw CSV on disk.
    zero_handling:
        How to handle an anchor value of zero (rare, but Trends does return
        zeros for thin weeks):

        * ``"ffill"`` — forward-fill zeros, then backward-fill any leading
          zeros (default, causal, preserves all weeks)
        * ``"clip"`` — replace zero with 1 (minimum sensible interest)
        * ``"drop"`` — drop weeks where the anchor is zero
    use_average_anchor:
        If a ticker's own batch anchor is missing, fall back to the
        element-wise mean of all available anchors (recommended — the
        anchors are correlated at 0.9999+).

    Returns
    -------
    dict
        Provenance record written to
        ``data/processed/trends_rescaled/provenance.json``.
    """
    RESCALED_DIR.mkdir(parents=True, exist_ok=True)

    prov = _load_provenance()
    anchors = _discover_anchors()

    if tickers is None:
        tickers = _discover_tickers()

    if not anchors:
        print(
            "[rescale] WARNING: no anchor files found in data/raw/trends/. "
            "Rescaling cannot proceed — Trends series will not be comparable "
            "across batches.",
            file=sys.stderr,
        )
        return {"error": "no_anchors", "tickers_rescaled": 0}

    results: dict = {}
    skipped: list[str] = []
    zero_weeks_total = 0

    for ticker in tickers:
        raw_path = TRENDS_DIR / f"{ticker}.csv"
        if not raw_path.exists():
            skipped.append(ticker)
            continue

        anchor = _build_anchor(ticker, anchors, prov, use_average_anchor)
        if anchor is None:
            skipped.append(ticker)
            continue

        raw = pd.read_csv(raw_path, index_col=0, parse_dates=True)
        raw_col = raw["search_interest"]

        # Align on shared dates.
        common = raw_col.index.intersection(anchor.index)
        if len(common) == 0:
            skipped.append(ticker)
            continue
        raw_aligned = raw_col.loc[common]
        anchor_aligned = anchor.loc[common].copy()

        # --- zero-anchor handling ------------------------------------------
        zero_mask = anchor_aligned == 0
        n_zeros = int(zero_mask.sum())
        zero_weeks_total += n_zeros
        if n_zeros:
            if zero_handling == "ffill":
                anchor_aligned = anchor_aligned.replace(0, pd.NA).ffill().bfill()
            elif zero_handling == "clip":
                anchor_aligned = anchor_aligned.clip(lower=1.0)
            elif zero_handling == "drop":
                raw_aligned = raw_aligned.loc[~zero_mask]
                anchor_aligned = anchor_aligned.loc[~zero_mask]
            else:
                raise ValueError(
                    f"Unknown zero_handling={zero_handling!r}; "
                    "expected 'ffill', 'clip', or 'drop'"
                )

        # --- rescale -------------------------------------------------------
        rescaled = raw_aligned / anchor_aligned

        # Save
        out_path = RESCALED_DIR / f"{ticker}.csv"
        rescaled.to_csv(out_path, header=["search_interest_rescaled"])

        batch = _deduce_batch(ticker, prov)
        results[ticker] = {
            "batch": batch,
            "rows": len(rescaled),
            "n_zero_weeks": n_zeros,
            "zero_handling": zero_handling,
            "mean_raw": round(float(raw_aligned.mean()), 4),
            "mean_rescaled": round(float(rescaled.mean()), 4),
            "anchor_source": (
                f"batch_{batch}" if batch else "average"
            ),
        }

    # --- provenance --------------------------------------------------------
    rescale_prov = {
        "step": "rescale_trends",
        "timestamp_utc": utc_now_iso(),
        "input_provenance": rel(TRENDS_DIR / "provenance.json"),
        "method": "ratio — search_interest / batch_anchor",
        "anchor_keyword": prov.get("anchor_keyword", "stock market"),
        "zero_handling": zero_handling,
        "use_average_anchor": use_average_anchor,
        "n_anchors_available": len(anchors),
        "n_tickers_total": len(tickers),
        "n_rescaled": len(results),
        "n_skipped": len(skipped),
        "total_zero_anchor_weeks": zero_weeks_total,
        "tickers": results,
        "skipped": skipped,
    }

    prov_path = RESCALED_DIR / "provenance.json"
    prov_path.write_text(json.dumps(rescale_prov, indent=2))

    print(f"[rescale] {len(results)}/{len(tickers)} tickers rescaled")
    if skipped:
        print(f"[rescale] {len(skipped)} skipped: {skipped}")
    if zero_weeks_total:
        print(f"[rescale] {zero_weeks_total} zero-anchor weeks handled via '{zero_handling}'")
    print(f"[rescale] provenance -> {rel(prov_path)}")
    return rescale_prov


# ---------------------------------------------------------------------------
# Diagnostic plot
# ---------------------------------------------------------------------------


def plot_before_after(tickers: list[str] | None = None, max_tickers: int = 16):
    """Generate a before/after grid showing that batch steps were removed.

    Left column: raw search interest (0-100, per-batch scale).
    Right column: rescaled search interest (in anchor units).

    Each row is one ticker.  Sorted so tickers from different batches are
    interspersed, making any batch-level discontinuities visible.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[rescale] matplotlib not installed — skipping plot", file=sys.stderr)
        return

    prov = _load_provenance()
    if tickers is None:
        tickers = _discover_tickers()

    # Sort by batch so adjacent rows come from different batches when
    # possible (makes batch steps visually obvious).
    def _sort_key(t: str) -> tuple:
        b = _deduce_batch(t, prov) or 99
        return (b, t)

    plot_tickers = sorted(tickers, key=_sort_key)[:max_tickers]
    n = len(plot_tickers)
    if n == 0:
        print("[rescale] no tickers to plot", file=sys.stderr)
        return

    fig, axes = plt.subplots(
        n, 2, figsize=(14, 1.8 * n), sharex="col", sharey="col"
    )
    if n == 1:
        axes = axes.reshape(1, 2)  # keep 2-d

    for i, ticker in enumerate(plot_tickers):
        # raw
        raw_path = TRENDS_DIR / f"{ticker}.csv"
        if raw_path.exists():
            raw_df = pd.read_csv(raw_path, index_col=0, parse_dates=True)
            axes[i, 0].plot(raw_df.index, raw_df["search_interest"],
                            linewidth=0.5, color="steelblue")
        axes[i, 0].set_ylabel(ticker, fontsize=8, rotation=0, labelpad=30)
        if i == 0:
            axes[i, 0].set_title("Raw search interest (0–100 per batch)")

        # rescaled
        r_path = RESCALED_DIR / f"{ticker}.csv"
        if r_path.exists():
            r_df = pd.read_csv(r_path, index_col=0, parse_dates=True)
            axes[i, 1].plot(r_df.index, r_df["search_interest_rescaled"],
                            linewidth=0.5, color="darkorange")
        if i == 0:
            axes[i, 1].set_title("Rescaled (÷ batch anchor)")

    for ax in axes[:, 0]:
        ax.tick_params(labelsize=7)
    for ax in axes[:, 1]:
        ax.tick_params(labelsize=7)

    fig.tight_layout()
    out_path = RESCALED_DIR / "before_after.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[rescale] plot saved -> {rel(out_path)}")


def cross_sectional_summary(tickers: list[str] | None = None) -> pd.DataFrame:
    """Return a per-week summary comparing cross-sectional stats before/after.

    Columns: date, n_tickers, mean_raw, std_raw, mean_rescaled, std_rescaled
    """
    if tickers is None:
        tickers = _discover_tickers()

    raw_frames, rescaled_frames = [], []
    for t in tickers:
        rp = RESCALED_DIR / f"{t}.csv"
        if not rp.exists():
            continue
        raw_p = TRENDS_DIR / f"{t}.csv"
        if not raw_p.exists():
            continue
        raw = pd.read_csv(raw_p, index_col=0, parse_dates=True)
        res = pd.read_csv(rp, index_col=0, parse_dates=True)
        raw_frames.append(raw["search_interest"].rename(t))
        rescaled_frames.append(res["search_interest_rescaled"].rename(t))

    raw_panel = pd.concat(raw_frames, axis=1)
    res_panel = pd.concat(rescaled_frames, axis=1)

    summary = pd.DataFrame({
        "n_tickers": raw_panel.notna().sum(axis=1),
        "mean_raw": raw_panel.mean(axis=1),
        "std_raw": raw_panel.std(axis=1),
        "mean_rescaled": res_panel.mean(axis=1),
        "std_rescaled": res_panel.std(axis=1),
    })
    summary.index.name = "date"
    return summary


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
        help="Tickers to rescale (default: all tickers with a raw CSV).",
    )
    p.add_argument(
        "--zero", default="ffill", choices=["ffill", "clip", "drop"],
        help="How to handle zero-valued anchor weeks (default: ffill).",
    )
    p.add_argument(
        "--no-average-anchor", action="store_true",
        help="Do NOT fall back to average anchor; skip tickers whose batch "
             "anchor is missing instead.",
    )
    p.add_argument(
        "--plot", action="store_true", default=True,
        help="Generate before/after diagnostic plot (default).",
    )
    p.add_argument(
        "--no-plot", action="store_false", dest="plot",
        help="Skip the diagnostic plot.",
    )
    p.add_argument(
        "--summary", action="store_true",
        help="Print per-week cross-sectional summary and save as CSV.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    result = rescale_trends(
        tickers=args.tickers,
        zero_handling=args.zero,
        use_average_anchor=not args.no_average_anchor,
    )

    n = result.get("n_rescaled", 0)
    if n == 0:
        return 1

    if args.plot:
        plot_before_after(tickers=args.tickers)

    if args.summary:
        summ = cross_sectional_summary(tickers=args.tickers)
        print("\nCross-sectional summary (first 10 weeks):")
        print(summ.head(10).to_string())
        csv_path = RESCALED_DIR / "cross_sectional_summary.csv"
        summ.to_csv(csv_path)
        print(f"Full summary -> {rel(csv_path)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
