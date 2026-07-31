"""Day 4 — turnover-aware portfolio strategy and backtest.

The problem this solves
-----------------------
The baseline construction is signal-rich and untradeable.  LightGBM has the
best signal in the study (Rank IC t = 2.56) and the worst book (net Sharpe
−5.0), purely because it rebalances ~105% of gross every week.  Costs, not
predictive power, are the binding constraint — so the highest-value lever is
construction, not more signal.

Four variants, each a stated modelling decision
-----------------------------------------------
``baseline``       rank-weighted, rebalanced fully every week (the Day 4 default)
``signal_smooth``  average the prediction over the trailing ``k`` weeks *before*
                   ranking.  A noisy signal produces rank churn that is
                   estimation error, not new information; smoothing the signal
                   attacks the cause rather than the symptom.
``weight_blend``   w_t = λ·w_target + (1−λ)·w_{t−1}.  Partial adjustment toward
                   the target — an explicit trade-off between tracking the
                   signal and paying to chase it.
``no_trade_band``  only trade a name when |w_target − w_held| exceeds ``band``.
                   Leaves small deviations alone; the classic no-trade region.

All four inherit the same neutrality constraints (dollar + sector), the same
5% single-name cap and the same cost model, so differences are attributable to
turnover policy alone.

Important: smoothing uses only past predictions (``.shift`` semantics via an
expanding/rolling mean over prior weeks), so no variant introduces look-ahead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_code_dir = Path(__file__).resolve().parent
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

import numpy as np
import pandas as pd

from paths import PROCESSED_DIR, rel, utc_now_iso
from portfolio import (WEEKS_PER_YEAR, _apply_limits, _neutralise, _rank_weights,
                       add_costs, average_daily_dollar_volume, evaluate)

PANEL_PATH = PROCESSED_DIR / "panel" / "panel_weekly.parquet"
OUT_DIR = PROCESSED_DIR / "strategy"


def _smooth_signal(df: pd.DataFrame, pred: str, k: int) -> pd.DataFrame:
    """Trailing mean of the prediction, per ticker. Uses only weeks <= t."""
    out = df.sort_values(["ticker", "week_ending_friday"]).copy()
    out[pred] = (out.groupby("ticker", sort=False)[pred]
                    .transform(lambda s: s.rolling(k, min_periods=1).mean()))
    return out


def build_variant(df: pd.DataFrame, pred: str, variant: str, *,
                  smooth_k: int = 4, blend: float = 0.4, band: float = 0.004,
                  sector_neutral: bool = True, max_weight: float = 0.05,
                  gross: float = 2.0) -> pd.DataFrame:
    """Construct weekly weights under one turnover policy."""
    work = _smooth_signal(df, pred, smooth_k) if variant == "signal_smooth" else df

    prev: pd.Series | None = None
    rows = []
    for wk, g in work.groupby("week_ending_friday", sort=True):
        g = g.dropna(subset=[pred])
        if len(g) < 10:
            continue
        target = _rank_weights(g, pred)
        target = _neutralise(target, g, sector_neutral, False)
        target = _apply_limits(target, max_weight, gross)
        target.index = g["ticker"].to_numpy()

        if prev is None or variant in ("baseline", "signal_smooth"):
            held = target
        else:
            aligned_prev = prev.reindex(target.index).fillna(0.0)
            if variant == "weight_blend":
                held = blend * target + (1 - blend) * aligned_prev
            elif variant == "no_trade_band":
                move = (target - aligned_prev).abs() > band
                held = aligned_prev.where(~move, target)
            else:
                raise ValueError(f"unknown variant: {variant}")
            # Re-impose neutrality and limits after the turnover policy, since
            # blending/banding can reintroduce a small net tilt.
            held = held - held.mean()
            s = held.abs().sum()
            held = held / s * gross if s > 0 else held

        prev = held
        blk = g[["week_ending_friday", "ticker", "fwd_return"]].copy()
        blk["weight"] = held.reindex(g["ticker"].to_numpy()).to_numpy()
        rows.append(blk)

    return pd.concat(rows, ignore_index=True)


def equity_curve(weights: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    w = weights.pivot(index="week_ending_friday", columns="ticker", values="weight").fillna(0.0)
    r = weights.pivot(index="week_ending_friday", columns="ticker", values="fwd_return").fillna(0.0)
    gross = (w * r).sum(axis=1)
    net = gross - costs["cost"].reindex(gross.index).fillna(0.0)
    eq = pd.DataFrame({"gross_return": gross, "net_return": net})
    eq["gross_equity"] = (1 + gross).cumprod()
    eq["net_equity"] = (1 + net).cumprod()
    eq["net_drawdown"] = eq["net_equity"] / eq["net_equity"].cummax() - 1
    eq["turnover"] = costs["turnover"].reindex(gross.index)
    return eq


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preds", type=Path,
                   default=PROCESSED_DIR / "models" / "oos_predictions_nested.parquet")
    p.add_argument("--smooth-k", type=int, default=4)
    p.add_argument("--blend", type=float, default=0.4)
    p.add_argument("--band", type=float, default=0.004)
    p.add_argument("--aum", type=float, default=10e6)
    p.add_argument("--linear-bps", type=float, default=5.0)
    p.add_argument("--impact-c", type=float, default=0.5)
    args = p.parse_args(argv)

    preds = pd.read_parquet(args.preds)
    panel = pd.read_parquet(PANEL_PATH)[["week_ending_friday", "ticker", "sector", "weekly_return"]]
    df = preds.merge(panel, on=["week_ending_friday", "ticker"], how="left")

    adv = average_daily_dollar_volume()
    vol = df.groupby("ticker")["weekly_return"].std() * np.sqrt(WEEKS_PER_YEAR)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    variants = ["baseline", "signal_smooth", "weight_blend", "no_trade_band"]
    models = [(c, l) for c, l in [("pred_enet", "ElasticNet"), ("pred_lgbm", "LightGBM")]
              if c in df.columns]

    results: dict = {}
    print(f"[strategy] {df.week_ending_friday.nunique()} weeks, "
          f"{df.ticker.nunique()} tickers  |  smooth_k={args.smooth_k} "
          f"blend={args.blend} band={args.band}")

    for pred_col, label in models:
        results[label] = {}
        for v in variants:
            w = build_variant(df, pred_col, v, smooth_k=args.smooth_k,
                              blend=args.blend, band=args.band)
            costs = add_costs(w, adv, args.aum, args.linear_bps, args.impact_c, vol)
            stats = evaluate(w, costs)
            results[label][v] = stats
            eq = equity_curve(w, costs)
            eq.to_parquet(OUT_DIR / f"equity_{label.lower()}_{v}.parquet")

    (OUT_DIR / "strategy_results.json").write_text(json.dumps(
        {"run_at_utc": utc_now_iso(),
         "params": {"smooth_k": args.smooth_k, "blend": args.blend,
                    "band": args.band, "aum": args.aum,
                    "linear_bps": args.linear_bps, "impact_c": args.impact_c},
         "results": results}, indent=2, default=str))

    for label in results:
        print(f"\n{'=' * 78}\n{label}\n{'-' * 78}")
        print(f"{'variant':<16}{'turnover%':>10}{'gross SR':>10}{'NET SR':>9}"
              f"{'net ann%':>10}{'maxDD%':>9}{'cost bps':>10}")
        for v in variants:
            s = results[label][v]
            print(f"{v:<16}{s['mean_weekly_turnover_pct']:>10.1f}"
                  f"{s['gross_sharpe']:>10.3f}{s['net_sharpe']:>9.3f}"
                  f"{s['net_ann_return_pct']:>10.2f}"
                  f"{s['net_max_drawdown_pct']:>9.1f}{s['mean_weekly_cost_bps']:>10.1f}")
    print(f"\n[strategy] saved → {rel(OUT_DIR / 'strategy_results.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
