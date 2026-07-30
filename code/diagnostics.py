"""Day 4 — ε under interrogation, and honest significance.

Three blocks:

1. **Classical residual diagnostics** (Gauss-Markov assumptions 3 and 4, which
   fail far more often than they hold on financial panels):

   | Test | Detects | Classical fix on failure |
   |------|---------|--------------------------|
   | Durbin-Watson | first-order autocorrelation | lagged terms, Newey-West, GLS |
   | Ljung-Box | autocorrelation across lags | as above, or ARMA the residual |
   | Breusch-Pagan | heteroskedasticity vs. regressors | WLS, White standard errors |
   | Jarque-Bera | non-normality (skew/kurtosis) | usually none needed; flags fat tails |

   **The reframe that matters** (Day 4, "When Failing the Test Is the
   Finding"): a classical statistician laundering an autocorrelated residual
   with Newey-West throws away the very pattern a stat-arb trader would
   trade.  Positive autocorrelation at short lags = momentum left on the
   table; negative = mean reversion.  The test statistic cannot distinguish
   "noise" from "structure I haven't modelled" — so we report the tests *and*
   say which reading we take.

2. **Deflated Sharpe Ratio** (Bailey & López de Prado 2014).  Under N trials
   from pure noise the *expected maximum* Sharpe is not zero — it grows with
   N.  That maximum, not zero, is the bar a real signal must clear.  DSR is
   the probability the true Sharpe exceeds it, adjusted for the skew and
   kurtosis of the actual return series rather than assuming Gaussian.

3. **The Fundamental Law** — IR ≈ IC · √breadth.  Breadth counts *independent*
   bets, not names: 88 large-caps in 11 sectors are heavily correlated, so
   effective breadth is far below 88.  We estimate it from the eigenvalue
   spectrum of the return correlation matrix (participation ratio), which is
   the honest number to quote next to a backtested IR.
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
from scipy import stats
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan
from statsmodels.stats.stattools import durbin_watson, jarque_bera

from paths import PROCESSED_DIR, rel, utc_now_iso

PRED_PATH = PROCESSED_DIR / "models" / "oos_predictions.parquet"
PANEL_PATH = PROCESSED_DIR / "panel" / "panel_weekly.parquet"
PORT_PATH = PROCESSED_DIR / "portfolio"
OUT_PATH = PROCESSED_DIR / "diagnostics" / "diagnostics.json"


# --------------------------------------------------------------------------
# 1. Residual diagnostics
# --------------------------------------------------------------------------
def residual_diagnostics(preds: pd.DataFrame, pred_col: str) -> dict:
    d = preds.dropna(subset=[pred_col, "fwd_return"]).copy()
    d["resid"] = d["fwd_return"] - d[pred_col]

    # Aggregate to a weekly residual series: cross-sectional mean residual.
    # Serial structure here is what a trader would care about.
    wk = d.groupby("week_ending_friday")["resid"].mean().sort_index()
    e = wk.to_numpy()

    dw = float(durbin_watson(e))
    lb = acorr_ljungbox(e, lags=[1, 4, 8], return_df=True)
    jb_stat, jb_p, skew, kurt = jarque_bera(e)

    X = np.column_stack([np.ones(len(d)), d[pred_col].to_numpy()])
    bp_stat, bp_p, _, _ = het_breuschpagan(d["resid"].to_numpy(), X)

    # ACF of the weekly residual — the trading-relevant read.
    acf1 = float(pd.Series(e).autocorr(1))

    if dw < 1.7 and lb["lb_pvalue"].iloc[0] < 0.05:
        reading = ("Residuals are positively autocorrelated at lag 1 — last week's "
                   "unexplained return predicts this week's. That is momentum left "
                   "on the table, i.e. candidate structure, not merely a standard-error "
                   "problem. Treat as a hypothesis to test out-of-sample before trading.")
    elif dw > 2.3 and lb["lb_pvalue"].iloc[0] < 0.05:
        reading = ("Residuals are negatively autocorrelated — mean reversion left on "
                   "the table. Candidate structure; test out-of-sample before acting.")
    else:
        reading = ("No significant first-order autocorrelation in the weekly residual: "
                   "no obvious unmodelled serial structure at this frequency.")

    return {
        "durbin_watson": round(dw, 3),
        "dw_interpretation": ("~2 = none; <2 positive autocorr; >2 negative"),
        "residual_acf_lag1": round(acf1, 4),
        "ljung_box": {f"lag_{int(r.Index)}": {"stat": round(float(r.lb_stat), 3),
                                              "p_value": round(float(r.lb_pvalue), 4)}
                      for r in lb.itertuples()},
        "breusch_pagan": {"stat": round(float(bp_stat), 3), "p_value": round(float(bp_p), 4),
                          "reject_homoskedastic": bool(bp_p < 0.05)},
        "jarque_bera": {"stat": round(float(jb_stat), 3), "p_value": round(float(jb_p), 4),
                        "skew": round(float(skew), 3), "kurtosis": round(float(kurt), 3),
                        "reject_normal": bool(jb_p < 0.05)},
        "reading": reading,
    }


# --------------------------------------------------------------------------
# 2. Deflated Sharpe Ratio
# --------------------------------------------------------------------------
def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """E[max SR] across n_trials of pure noise (Bailey & López de Prado)."""
    if n_trials < 2:
        return 0.0
    g = np.euler_gamma
    z1 = stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(sr_variance) * ((1 - g) * z1 + g * z2))


def deflated_sharpe(returns: pd.Series, n_trials: int,
                    sr_benchmark: float | None = None) -> dict:
    r = returns.dropna()
    n = len(r)
    if n < 10:
        return {"error": "too few observations"}
    sr = float(r.mean() / r.std()) if r.std() > 0 else 0.0     # per-period
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))

    # Variance of the SR estimator across trials, proxied by its sampling variance.
    sr_var = (1 - skew * sr + (kurt - 1) / 4 * sr ** 2) / (n - 1)
    bench = expected_max_sharpe(n_trials, max(sr_var, 1e-12)) if sr_benchmark is None \
        else sr_benchmark

    denom = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    z = (sr - bench) * np.sqrt(n - 1) / denom
    return {
        "n_periods": int(n),
        "sharpe_per_period": round(sr, 4),
        "sharpe_annualised": round(sr * np.sqrt(52), 3),
        "skew": round(skew, 3),
        "kurtosis": round(kurt, 3),
        "n_trials_assumed": int(n_trials),
        "expected_max_sharpe_under_noise": round(bench, 4),
        "deflated_sharpe_prob": round(float(stats.norm.cdf(z)), 4),
        "passes_at_95pct": bool(stats.norm.cdf(z) > 0.95),
    }


# --------------------------------------------------------------------------
# 3. Fundamental Law — effective breadth
# --------------------------------------------------------------------------
def effective_breadth(panel: pd.DataFrame) -> dict:
    wide = panel.pivot(index="week_ending_friday", columns="ticker",
                       values="weekly_return").dropna(axis=1, how="all")
    corr = wide.corr().to_numpy()
    corr = np.nan_to_num(corr, nan=0.0)
    eig = np.linalg.eigvalsh(corr)
    eig = eig[eig > 0]
    # Participation ratio: (Σλ)² / Σλ² — number of "effectively independent"
    # directions in the cross-section.
    n_eff = float((eig.sum() ** 2) / (eig ** 2).sum())
    n_names = wide.shape[1]
    off = corr[~np.eye(n_names, dtype=bool)]
    return {
        "n_names": int(n_names),
        "mean_pairwise_correlation": round(float(off.mean()), 3),
        "effective_independent_bets": round(n_eff, 1),
        "breadth_ratio_pct": round(100 * n_eff / n_names, 1),
        "note": ("Breadth in IR ≈ IC·√breadth counts INDEPENDENT bets. "
                 "Quoting √88 overstates the achievable IR."),
    }


def fundamental_law(mean_ic: float, n_eff: float, rebalances_per_year: int = 52) -> dict:
    br = n_eff * rebalances_per_year
    return {
        "mean_rank_ic": round(mean_ic, 4),
        "effective_names": round(n_eff, 1),
        "rebalances_per_year": rebalances_per_year,
        "breadth_BR": round(br, 1),
        "implied_annual_IR": round(mean_ic * np.sqrt(br), 3),
        "naive_IR_using_all_88": round(mean_ic * np.sqrt(88 * rebalances_per_year), 3),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trials", type=int, default=12,
                   help="configurations tried, for the Deflated Sharpe correction")
    args = p.parse_args(argv)

    preds = pd.read_parquet(PRED_PATH)
    panel = pd.read_parquet(PANEL_PATH)
    model_res = json.loads((PROCESSED_DIR / "models" / "model_results.json").read_text())

    out: dict = {"run_at_utc": utc_now_iso()}

    print("=" * 70)
    print("1. RESIDUAL DIAGNOSTICS (weekly cross-sectional mean residual)")
    print("=" * 70)
    for col, lab in [("pred_enet", "ElasticNet"), ("pred_lgbm", "LightGBM")]:
        d = residual_diagnostics(preds, col)
        out.setdefault("residual_diagnostics", {})[lab] = d
        print(f"\n{lab}:")
        print(f"  Durbin-Watson      {d['durbin_watson']}   (resid ACF(1) = {d['residual_acf_lag1']})")
        print(f"  Ljung-Box lag1 p   {d['ljung_box']['lag_1']['p_value']}")
        print(f"  Breusch-Pagan p    {d['breusch_pagan']['p_value']}  "
              f"heteroskedastic={d['breusch_pagan']['reject_homoskedastic']}")
        print(f"  Jarque-Bera p      {d['jarque_bera']['p_value']}  "
              f"skew={d['jarque_bera']['skew']} kurt={d['jarque_bera']['kurtosis']}")
        print(f"  → {d['reading']}")

    print("\n" + "=" * 70)
    print(f"2. DEFLATED SHARPE (assuming {args.trials} configurations tried)")
    print("=" * 70)
    for lab in ["elasticnet", "lightgbm"]:
        f = PORT_PATH / f"weights_{lab}.parquet"
        if not f.exists():
            continue
        w = pd.read_parquet(f)
        wide_w = w.pivot(index="week_ending_friday", columns="ticker", values="weight").fillna(0)
        wide_r = w.pivot(index="week_ending_friday", columns="ticker", values="fwd_return").fillna(0)
        ret = (wide_w * wide_r).sum(axis=1)
        d = deflated_sharpe(ret, args.trials)
        out.setdefault("deflated_sharpe", {})[lab] = d
        print(f"\n{lab}: SR(ann)={d['sharpe_annualised']}  "
              f"E[max SR|noise]={d['expected_max_sharpe_under_noise']}  "
              f"DSR={d['deflated_sharpe_prob']}  passes95%={d['passes_at_95pct']}")

    print("\n" + "=" * 70)
    print("3. FUNDAMENTAL LAW — effective breadth")
    print("=" * 70)
    eb = effective_breadth(panel)
    out["effective_breadth"] = eb
    print(f"  names={eb['n_names']}  mean pairwise corr={eb['mean_pairwise_correlation']}")
    print(f"  effectively independent bets = {eb['effective_independent_bets']} "
          f"({eb['breadth_ratio_pct']}% of headcount)")
    for lab in ["ElasticNet", "LightGBM"]:
        fl = fundamental_law(model_res["results"][lab]["mean_rank_ic"],
                             eb["effective_independent_bets"])
        out.setdefault("fundamental_law", {})[lab] = fl
        print(f"  {lab}: IC={fl['mean_rank_ic']} → implied IR={fl['implied_annual_IR']} "
              f"(naive using all 88: {fl['naive_IR_using_all_88']})")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\n[diagnostics] saved → {rel(OUT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
