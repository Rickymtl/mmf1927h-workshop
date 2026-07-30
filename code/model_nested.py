"""Day 4 — nested cross-validation: tuning without leaking twice.

Why this exists
---------------
``model.py`` fits Elastic Net with a hand-set ``alpha=1e-3``.  Two problems:

1. Tuning that value against the same folds used to report performance is a
   second, distinct leak — try enough configurations against one split and the
   best score is optimistic by construction (Day 4, "Nested CV: Tuning Without
   Leaking Twice").
2. At ``alpha=1e-3`` the L1 term zeroes **every Trends coefficient**, so the
   model's entire signal comes from ``rvol_13``/``ivol_26``.  Weekly return
   variance is ~4e-4, so that penalty is large relative to the target.  We
   cannot tell from that run whether search interest is genuinely useless in a
   linear model, or merely regularised out of it — and those have very
   different implications for the project's thesis.

The scheme
----------
    OUTER loop  expanding-window walk-forward, purged + embargoed.
                Reports unbiased out-of-sample performance.  Never used for
                any selection decision.
    INNER loop  a second walk-forward split *inside each outer training
                block only*.  Selects hyperparameters by mean inner Rank IC —
                matching the metric the signal is actually judged on rather
                than optimising MSE and hoping it transfers.

Per outer fold: inner CV picks parameters on training data, the model is
refit on the full training block, and evaluated exactly once on the untouched
outer test block.

Selection metric
----------------
Rank IC, not MSE.  The deck is explicit that a regression target evaluated via
Rank IC is a defensible pairing, but the mismatch should be named — so we name
it and select on the metric we report.

Trials accounting
-----------------
The total number of (fold × configuration) fits is recorded, because that
count is the input to the Deflated Sharpe correction in ``diagnostics.py``.
Searching more configurations raises the bar a result must clear.
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
from sklearn.linear_model import ElasticNet
from sklearn.preprocessing import StandardScaler

from features import FEATURE_TAGS, FEATURES, TARGET
from model import RANK_COLS, summarise, walk_forward_folds, weekly_rank_ic
from paths import PROCESSED_DIR, rel, utc_now_iso

OUT_DIR = PROCESSED_DIR / "models"

# Grid spans several orders of magnitude *below* the old hand-set 1e-3,
# because weekly return variance (~4e-4) makes that value very aggressive.
ENET_GRID = [
    {"alpha": a, "l1_ratio": r}
    for a in [1e-7, 1e-6, 1e-5, 1e-4, 1e-3]
    for r in [0.1, 0.5, 0.9]
]
LGBM_GRID = [
    {"num_leaves": n, "learning_rate": lr, "min_child_samples": m}
    for n in [7, 31]
    for lr in [0.03]
    for m in [50, 150]
]


def _ic_of(pred: np.ndarray, block: pd.DataFrame) -> float:
    tmp = block[["week_ending_friday", TARGET]].copy()
    tmp["p"] = pred
    ic = weekly_rank_ic(tmp, "p")
    return float(ic.mean()) if len(ic) else float("nan")


def _fit_enet(params, Xtr, ytr, Xte):
    sc = StandardScaler().fit(Xtr)
    m = ElasticNet(max_iter=5000, random_state=0, **params)
    m.fit(sc.transform(Xtr), ytr)
    return m.predict(sc.transform(Xte)), m


def _fit_lgbm(params, Xtr, ytr, Xte):
    import lightgbm as lgb
    m = lgb.LGBMRegressor(n_estimators=300, subsample=0.8, subsample_freq=1,
                          colsample_bytree=0.8, reg_lambda=1.0, random_state=0,
                          verbose=-1, **params)
    m.fit(Xtr, ytr)
    return m.predict(Xte), m


def _inner_select(df, X, train_weeks, grid, fitter, n_inner, purge, embargo):
    """Pick the config with the best mean inner-fold Rank IC. Train data only."""
    min_train = max(52, int(len(train_weeks) * 0.5))
    inner = list(walk_forward_folds(np.array(train_weeks), n_inner, min_train, purge, embargo))
    if not inner:
        return grid[0], {}
    scores = {i: [] for i in range(len(grid))}
    for itr_w, ite_w in inner:
        itr = df["week_ending_friday"].isin(itr_w)
        ite = df["week_ending_friday"].isin(ite_w)
        if itr.sum() < 200 or ite.sum() == 0:
            continue
        for gi, params in enumerate(grid):
            pred, _ = fitter(params, X[itr], df.loc[itr, TARGET], X[ite])
            ic = _ic_of(pred, df.loc[ite])
            if np.isfinite(ic):
                scores[gi].append(ic)
    mean_scores = {gi: float(np.mean(v)) for gi, v in scores.items() if v}
    if not mean_scores:
        return grid[0], {}
    best = max(mean_scores, key=mean_scores.get)
    return grid[best], mean_scores


def run_nested(df, n_folds, min_train, purge, embargo, n_inner):
    df = df.sort_values(["week_ending_friday", "ticker"]).reset_index(drop=True)
    df = df.dropna(subset=[TARGET])
    X = df[RANK_COLS].fillna(0.5)
    weeks = np.array(sorted(df["week_ending_friday"].unique()))

    outer = list(walk_forward_folds(weeks, n_folds, min_train, purge, embargo))
    print(f"[nested] {len(outer)} outer folds; inner grids: "
          f"ElasticNet {len(ENET_GRID)}, LightGBM {len(LGBM_GRID)}")

    rows, chosen, coefs, n_fits = [], {"ElasticNet": [], "LightGBM": []}, [], 0

    for i, (tr_w, te_w) in enumerate(outer, 1):
        tr = df["week_ending_friday"].isin(tr_w)
        te = df["week_ending_friday"].isin(te_w)
        if tr.sum() < 200 or te.sum() == 0:
            continue
        Xtr, ytr, Xte = X[tr], df.loc[tr, TARGET], X[te]

        p_en, _ = _inner_select(df, X, list(tr_w), ENET_GRID, _fit_enet,
                                n_inner, purge, embargo)
        p_gb, _ = _inner_select(df, X, list(tr_w), LGBM_GRID, _fit_lgbm,
                                n_inner, purge, embargo)
        n_fits += (len(ENET_GRID) + len(LGBM_GRID)) * n_inner

        pred_en, m_en = _fit_enet(p_en, Xtr, ytr, Xte)
        pred_gb, _ = _fit_lgbm(p_gb, Xtr, ytr, Xte)
        coefs.append(m_en.coef_)
        chosen["ElasticNet"].append(p_en)
        chosen["LightGBM"].append(p_gb)

        blk = df.loc[te, ["week_ending_friday", "ticker", TARGET]].copy()
        blk["pred_enet"], blk["pred_lgbm"] = pred_en, pred_gb
        rows.append(blk)
        print(f"  fold {i}: enet alpha={p_en['alpha']:.0e} l1={p_en['l1_ratio']} | "
              f"lgbm leaves={p_gb['num_leaves']} mcs={p_gb['min_child_samples']}")

    preds = pd.concat(rows, ignore_index=True)
    results = {}
    for col, lab in [("pred_enet", "ElasticNet"), ("pred_lgbm", "LightGBM")]:
        ic = weekly_rank_ic(preds, col)
        results[lab] = summarise(ic, preds, col, lab)

    coef_mean = np.mean(coefs, axis=0)
    nonzero = int((np.abs(coef_mean) > 1e-12).sum())
    trends = [f for f in FEATURES if FEATURE_TAGS[f][0] == "external"]
    trends_nonzero = [f for f, c in zip(FEATURES, coef_mean)
                      if f in trends and abs(c) > 1e-12]
    results["enet_coefficients"] = [
        {"feature": f, "category": "/".join(FEATURE_TAGS[f]), "coef": float(c)}
        for f, c in zip(FEATURES, coef_mean)]
    results["_summary"] = {
        "nonzero_coefficients": nonzero,
        "trends_features_retained": trends_nonzero,
        "n_trends_features": len(trends),
        "total_fits": n_fits,
        "selected_params": chosen,
    }
    return results, preds


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--features", type=Path,
                   default=PROCESSED_DIR / "features" / "features_weekly.parquet")
    p.add_argument("--folds", type=int, default=6)
    p.add_argument("--inner", type=int, default=3)
    p.add_argument("--min-train", type=int, default=104)
    p.add_argument("--purge", type=int, default=1)
    p.add_argument("--embargo", type=int, default=1)
    args = p.parse_args(argv)

    df = pd.read_parquet(args.features)
    results, preds = run_nested(df, args.folds, args.min_train, args.purge,
                                args.embargo, args.inner)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(OUT_DIR / "oos_predictions_nested.parquet", index=False)
    (OUT_DIR / "model_results_nested.json").write_text(
        json.dumps({"run_at_utc": utc_now_iso(),
                    "scheme": "nested CV — inner selects params, outer reports",
                    "results": results}, indent=2, default=str))

    print("\n" + "=" * 66)
    print(f"{'metric':<26}{'ElasticNet':>18}{'LightGBM':>18}")
    print("-" * 66)
    for k in ["weeks_evaluated", "mean_rank_ic", "ic_ir", "ic_t_stat",
              "pct_weeks_positive_ic", "hit_rate_pct"]:
        print(f"{k:<26}{results['ElasticNet'][k]:>18}{results['LightGBM'][k]:>18}")
    print("=" * 66)

    s = results["_summary"]
    print(f"\nElastic Net coefficients (mean across outer folds):")
    for c in sorted(results["enet_coefficients"], key=lambda x: -abs(x["coef"])):
        flag = "  <-- TRENDS" if c["category"].startswith("external") else ""
        print(f"  {c['feature']:<16}{c['category']:<28}{c['coef']:>14.6f}{flag}")
    print(f"\nnonzero coefficients: {s['nonzero_coefficients']}/{len(FEATURES)}")
    print(f"Trends features retained: {len(s['trends_features_retained'])}/"
          f"{s['n_trends_features']} → {s['trends_features_retained']}")
    print(f"total model fits (for Deflated Sharpe trials): {s['total_fits']}")
    print(f"\n[nested] saved → {rel(OUT_DIR / 'model_results_nested.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
