"""Day 4 — from a ranked signal to an evaluated portfolio.

Implements the four construction steps the deck requires each project to show
explicitly (Day 4, "From Ranked Signal to Positions"):

  1. **Score & rank** — rank the universe each Friday by predicted return.
  2. **Choose construction** — decile long-short, or rank-weighted (smoother
     turnover).  Both are provided; the choice is a stated modelling decision.
  3. **Apply neutrality** — dollar- and sector-neutrality imposed *at
     construction time*, not checked for afterwards.
  4. **Apply limits** — single-name cap and gross-exposure normalisation.

What is and is not neutralised
------------------------------
Day 4 lists three neutrality constraints: dollar, sector and beta.  **We apply
two of the three.**

* **Dollar-neutral** — always.  Long $ = short $; the constraint we never relax.
* **Sector-neutral** — always, by demeaning within GICS sector each date.
* **Beta-neutral** — **not applied.**  ``beta_neutral`` defaults to ``False``
  and the panel carries no ``beta`` column, so the branch in ``_neutralise``
  never executes.  The rationale: the universe is 88 US mega-caps whose betas
  cluster tightly around 1, so a dollar-neutral rank-weighted book already has
  small residual market beta.  This is a **stated simplification, not a claim
  that residual beta is zero** — we have not measured it.  Wiring in a rolling
  52-week market beta and switching the flag on is the correct fix and is
  listed under "with one more week" in ``REPORT.md``.

Two constructions live in this repo
-----------------------------------
``portfolio.py`` (this file) is the **baseline**: full rebalance to target
weights every Friday.  ``strategy.py`` implements three **turnover-aware**
variants on top of the same weights, costs and constraints.  Numbers from the
two are not interchangeable — ``REPORT.md`` §6.2 quotes this file, §7.5.4
quotes ``strategy.py``.

Neutrality is approximate, not exact
------------------------------------
The constraints are applied as **sequential projections**, not as constraints
inside a solver.  ``_apply_limits`` clips to the single-name cap and then
re-demeans to restore dollar-neutrality — which does **not** restore exact
within-sector zeros.  So sector-neutrality holds up to the residual introduced
by capping.  Day 4 asks for neutrality constructed at optimisation time (a
constrained solver, e.g. ``cvxpy``); sequential projection is the cheaper
approximation we chose, and the residual sector exposure it leaves is a
disclosed simplification rather than a checked-and-passed property.

Then evaluates the book on Sharpe / IR, max drawdown and turnover read
together, and — critically — **net of transaction costs**.

Cost model (Day 4, "A Concrete Cost Model")
-------------------------------------------
Per unit of notional traded:

    cost = linear_bps/1e4  +  c · σ · sqrt(participation)

where ``participation = trade_notional / ADV``.  The square-root term is the
Almgren et al. market-impact law: a 4× larger trade costs ~2× more per share,
not 4×.  ADV is each name's own average daily dollar volume from the raw price
data, so the haircut reflects the actual liquidity of what we trade.

Why neutrality matters here
---------------------------
Predictions are ranked cross-sectionally, but a raw decile book can still
carry a large sector tilt or market beta — in which case realised return
measures factor performance, not α.  Neutralising makes the return a cleaner
(still noisy) estimate of the α the model is actually claiming.

Note on shorting
----------------
The long-short book assumes shorting is available and costless beyond the
modelled spread/impact.  Borrow fees and recall risk are **not** modelled;
for a large-cap universe borrow is typically cheap, but this is a disclosed
simplification, not a claim that it is free.

Note on sector labels
---------------------
``sector`` comes from ``universe.py``, a **static mid-2025 GICS snapshot**
applied to the whole horizon.  GICS reclassifications inside the sample window
therefore mislabel some names for part of it — concretely, Visa and Mastercard
moved from Information Technology to Financials on 2023-03-17, so for the first
~20 months of a 60-month sample the sector-neutrality constraint here groups
them incorrectly.  Disclosed in ``REPORT.md`` §8 and ``DATA_QUALITY.md`` §5.
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

from paths import PRICES_DIR, PROCESSED_DIR, rel, utc_now_iso

PRED_PATH = PROCESSED_DIR / "models" / "oos_predictions.parquet"
PANEL_PATH = PROCESSED_DIR / "panel" / "panel_weekly.parquet"
OUT_DIR = PROCESSED_DIR / "portfolio"

WEEKS_PER_YEAR = 52


# --------------------------------------------------------------------------
# Liquidity
# --------------------------------------------------------------------------
def average_daily_dollar_volume() -> pd.Series:
    """Mean daily $ volume per ticker, from the raw price files."""
    adv = {}
    for f in sorted(PRICES_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(f, usecols=["Close", "Volume"])
        except ValueError:
            continue
        dv = (df["Close"] * df["Volume"]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(dv):
            adv[f.stem] = float(dv.mean())
    return pd.Series(adv, name="adv")


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------
def _decile_weights(g: pd.DataFrame, pred: str, n_groups: int) -> pd.Series:
    """Equal-weight long top decile, short bottom decile."""
    r = g[pred].rank(pct=True)
    w = pd.Series(0.0, index=g.index)
    long, short = r > 1 - 1 / n_groups, r < 1 / n_groups
    if long.sum():
        w[long] = 1.0 / long.sum()
    if short.sum():
        w[short] = -1.0 / short.sum()
    return w


def _rank_weights(g: pd.DataFrame, pred: str) -> pd.Series:
    """Weights linear in demeaned cross-sectional rank — smoother turnover."""
    r = g[pred].rank(pct=True)
    w = r - r.mean()
    s = w.abs().sum()
    return w / s * 2.0 if s > 0 else w


def _neutralise(w: pd.Series, g: pd.DataFrame, sector_neutral: bool,
                beta_neutral: bool) -> pd.Series:
    """Impose dollar-, sector- and beta-neutrality as linear constraints."""
    if sector_neutral and "sector" in g:
        # Remove the within-sector mean so each sector nets to zero.
        w = w - w.groupby(g["sector"]).transform("mean")
    if beta_neutral and "beta" in g and g["beta"].notna().any():
        b = g["beta"].fillna(1.0)
        denom = float((b * b).sum())
        if denom > 0:
            w = w - b * float((w * b).sum()) / denom
    # Dollar-neutral last: it is the constraint we never relax.
    w = w - w.mean()
    return w


def _apply_limits(w: pd.Series, max_weight: float, gross: float) -> pd.Series:
    w = w.clip(-max_weight, max_weight)
    w = w - w.mean()                      # capping can break dollar-neutrality
    s = w.abs().sum()
    return w / s * gross if s > 0 else w


def build_weights(df: pd.DataFrame, pred: str, scheme: str = "rank",
                  n_groups: int = 5, sector_neutral: bool = True,
                  beta_neutral: bool = False, max_weight: float = 0.05,
                  gross: float = 2.0) -> pd.DataFrame:
    out = []
    for wk, g in df.groupby("week_ending_friday", sort=True):
        g = g.dropna(subset=[pred])
        if len(g) < 10:
            continue
        w = _decile_weights(g, pred, n_groups) if scheme == "decile" else _rank_weights(g, pred)
        w = _neutralise(w, g, sector_neutral, beta_neutral)
        w = _apply_limits(w, max_weight, gross)
        blk = g[["week_ending_friday", "ticker", "fwd_return"]].copy()
        blk["weight"] = w.values
        out.append(blk)
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------
# Costs & evaluation
# --------------------------------------------------------------------------
def add_costs(weights: pd.DataFrame, adv: pd.Series, aum: float,
              linear_bps: float, impact_c: float, vol: pd.Series) -> pd.DataFrame:
    """Per-week turnover and cost, using the linear + square-root model."""
    w = weights.pivot(index="week_ending_friday", columns="ticker", values="weight").fillna(0.0)
    dw = w.diff()
    dw.iloc[0] = w.iloc[0]                     # initial build is a real trade

    traded_notional = dw.abs() * aum
    participation = traded_notional.div(adv.reindex(dw.columns).fillna(adv.median()), axis=1)
    sigma = vol.reindex(dw.columns).fillna(vol.median())

    linear = dw.abs() * (linear_bps / 1e4)
    impact = dw.abs() * impact_c * sigma * np.sqrt(participation.clip(lower=0))
    cost = (linear + impact).sum(axis=1)

    turnover = dw.abs().sum(axis=1) / 2.0
    return pd.DataFrame({"turnover": turnover, "cost": cost})


def evaluate(weights: pd.DataFrame, costs: pd.DataFrame) -> dict:
    w = weights.pivot(index="week_ending_friday", columns="ticker", values="weight").fillna(0.0)
    r = weights.pivot(index="week_ending_friday", columns="ticker", values="fwd_return").fillna(0.0)
    gross_ret = (w * r).sum(axis=1)
    net_ret = gross_ret - costs["cost"].reindex(gross_ret.index).fillna(0.0)

    def _stats(x: pd.Series, label: str) -> dict:
        ann = float(x.mean() * WEEKS_PER_YEAR)
        vol = float(x.std() * np.sqrt(WEEKS_PER_YEAR))
        sharpe = ann / vol if vol > 0 else float("nan")
        eq = (1 + x).cumprod()
        mdd = float((eq / eq.cummax() - 1).min())
        downside = x[x < 0].std() * np.sqrt(WEEKS_PER_YEAR)
        return {
            f"{label}_ann_return_pct": round(100 * ann, 2),
            f"{label}_ann_vol_pct": round(100 * vol, 2),
            f"{label}_sharpe": round(sharpe, 3),
            f"{label}_max_drawdown_pct": round(100 * mdd, 2),
            f"{label}_sortino": round(ann / float(downside), 3) if downside and downside > 0 else None,
            f"{label}_calmar": round(ann / abs(mdd), 3) if mdd < 0 else None,
        }

    res = {"weeks": int(len(gross_ret)), **_stats(gross_ret, "gross"), **_stats(net_ret, "net")}
    res["mean_weekly_turnover_pct"] = round(100 * float(costs["turnover"].mean()), 2)
    res["annual_turnover_x"] = round(float(costs["turnover"].mean()) * WEEKS_PER_YEAR, 1)
    res["mean_weekly_cost_bps"] = round(1e4 * float(costs["cost"].mean()), 2)
    res["cost_drag_ann_pct"] = round(
        res["gross_ann_return_pct"] - res["net_ann_return_pct"], 2)
    # Market-neutral book: benchmark return ~0, so IR collapses onto Sharpe.
    res["note_ir_vs_sharpe"] = ("dollar- and sector-neutral book: benchmark exposure ~0, "
                                "so IR ≈ Sharpe — they are one number, not two")
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preds", type=Path, default=PRED_PATH)
    p.add_argument("--scheme", choices=["rank", "decile"], default="rank")
    p.add_argument("--n-groups", type=int, default=5, help="quantiles for decile scheme")
    p.add_argument("--max-weight", type=float, default=0.05)
    p.add_argument("--gross", type=float, default=2.0, help="gross exposure (1.0 long + 1.0 short)")
    p.add_argument("--aum", type=float, default=10e6, help="notional AUM for the impact model")
    p.add_argument("--linear-bps", type=float, default=5.0, help="spread + commission, bps")
    p.add_argument("--impact-c", type=float, default=0.5, help="square-root impact constant")
    p.add_argument("--no-sector-neutral", action="store_true")
    args = p.parse_args(argv)

    preds = pd.read_parquet(args.preds)
    panel = pd.read_parquet(PANEL_PATH)[["week_ending_friday", "ticker", "sector", "weekly_return"]]
    df = preds.merge(panel, on=["week_ending_friday", "ticker"], how="left")

    adv = average_daily_dollar_volume()
    vol = (df.groupby("ticker")["weekly_return"].std() * np.sqrt(WEEKS_PER_YEAR))

    print(f"[portfolio] {df.week_ending_friday.nunique()} weeks, "
          f"{df.ticker.nunique()} tickers, scheme={args.scheme}, "
          f"sector_neutral={not args.no_sector_neutral}")
    print(f"[portfolio] median ADV ${adv.median()/1e6:,.0f}M, AUM ${args.aum/1e6:,.0f}M")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for pred_col, label in [("pred_enet", "ElasticNet"), ("pred_lgbm", "LightGBM")]:
        if pred_col not in df:
            continue
        w = build_weights(df, pred_col, scheme=args.scheme, n_groups=args.n_groups,
                          sector_neutral=not args.no_sector_neutral,
                          max_weight=args.max_weight, gross=args.gross)
        costs = add_costs(w, adv, args.aum, args.linear_bps, args.impact_c, vol)
        results[label] = evaluate(w, costs)
        w.to_parquet(OUT_DIR / f"weights_{label.lower()}.parquet", index=False)

    payload = {"run_at_utc": utc_now_iso(),
               "config": {k: v for k, v in vars(args).items() if k != "preds"},
               "cost_model": "linear bps + Almgren square-root impact on own ADV",
               "results": results}
    (OUT_DIR / "portfolio_results.json").write_text(json.dumps(payload, indent=2, default=str))

    keys = ["weeks", "gross_ann_return_pct", "gross_sharpe", "net_ann_return_pct",
            "net_sharpe", "net_max_drawdown_pct", "mean_weekly_turnover_pct",
            "annual_turnover_x", "mean_weekly_cost_bps", "cost_drag_ann_pct"]
    print("\n" + "=" * 62)
    print(f"{'metric':<28}{'ElasticNet':>16}{'LightGBM':>16}")
    print("-" * 62)
    for k in keys:
        a = results.get("ElasticNet", {}).get(k, "-")
        b = results.get("LightGBM", {}).get(k, "-")
        print(f"{k:<28}{a:>16}{b:>16}")
    print("=" * 62)
    print(f"\n[portfolio] saved → {rel(OUT_DIR / 'portfolio_results.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
