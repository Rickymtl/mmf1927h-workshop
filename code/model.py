"""Day 3 — fit and evaluate the two required models.

Models (Day 3 slides p29-30):
  * **Elastic Net** — penalised regression; coefficients map directly onto
    β′F, so the fitted model is a literal, readable estimate of factor
    exposures.
  * **LightGBM** — gradient-boosted trees; captures nonlinearity and
    interactions the linear model cannot.

Fitting both on the same feature set is itself the diagnostic: GBM ≫ linear
implies real nonlinear structure; GBM ≈ linear implies a simpler story.

Validation — walk-forward, purged, embargoed
--------------------------------------------
Standard k-fold shuffles time and leaks on autocorrelated financial panels
(Day 4 slides p20).  Instead:

  * **Expanding-window walk-forward** — train strictly on the past, test
    strictly on the future, roll forward.
  * **Purge** — drop the last ``purge`` weeks of each training block, whose
    label window (week t → t+1) would otherwise overlap the test block.
  * **Embargo** — skip ``embargo`` weeks after each test block before the
    next training block resumes, since features carry slowly-decaying
    information across the boundary.

Metrics
-------
  * **Rank IC** — per-week Spearman correlation between prediction and
    realised forward return.  Primary metric: only relative ordering drives a
    long-short book (Day 3 slides p6).
  * **IC-IR** — mean(IC)/std(IC), the t-stat of the IC series.  A mean IC of
    0.04 with wild variance is not tradeable.
  * **Hit rate** — share of correctly-signed predictions, reported relative to
    the 50% coin-flip baseline.

Missing features are filled with 0.5 — the neutral value for a percentile
rank — rather than dropped, so a name with one sparse feature still enters the
cross-section.  This is stated rather than silent because it is a modelling
choice (``trends_z_26`` is undefined for tickers whose Trends series is
constant, a known artifact of the legacy anchored pull).
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
from scipy.stats import spearmanr
from sklearn.linear_model import ElasticNet
from sklearn.preprocessing import StandardScaler

from features import FEATURE_TAGS, FEATURES, TARGET
from paths import PROCESSED_DIR, rel, utc_now_iso

FEATURES_PATH = PROCESSED_DIR / "features" / "features_weekly.parquet"
OUT_DIR = PROCESSED_DIR / "models"
RANK_COLS = [f"{f}_rank" for f in FEATURES]


def walk_forward_folds(weeks: np.ndarray, n_folds: int, min_train: int,
                       purge: int, embargo: int):
    """Yield (train_weeks, test_weeks) with purge + embargo applied."""
    n = len(weeks)
    test_size = max(1, (n - min_train) // n_folds)
    for k in range(n_folds):
        train_end = min_train + k * test_size
        test_start = train_end + embargo
        test_end = min(test_start + test_size, n)
        if test_start >= n or train_end <= purge:
            continue
        train = weeks[: train_end - purge]          # purge tail of train
        test = weeks[test_start:test_end]
        if len(test) == 0:
            continue
        yield train, test


def weekly_rank_ic(df: pd.DataFrame, pred_col: str) -> pd.Series:
    """Spearman IC per week; weeks with <5 names are skipped as too noisy."""
    out = {}
    for wk, g in df.groupby("week_ending_friday"):
        g = g.dropna(subset=[pred_col, TARGET])
        if len(g) < 5:
            continue
        ic, _ = spearmanr(g[pred_col], g[TARGET])
        if np.isfinite(ic):
            out[wk] = ic
    return pd.Series(out).sort_index()


def summarise(ic: pd.Series, preds: pd.DataFrame, pred_col: str, label: str) -> dict:
    valid = preds.dropna(subset=[pred_col, TARGET])
    # Hit rate on a demeaned prediction: does the cross-sectional tilt have
    # the right sign? A raw sign test is meaningless when all predictions
    # share the market's drift.
    dm_pred = valid[pred_col] - valid.groupby("week_ending_friday")[pred_col].transform("mean")
    dm_true = valid[TARGET] - valid.groupby("week_ending_friday")[TARGET].transform("mean")
    hit = float((np.sign(dm_pred) == np.sign(dm_true)).mean())
    icir = float(ic.mean() / ic.std()) if ic.std() > 0 else float("nan")
    return {
        "model": label,
        "weeks_evaluated": int(len(ic)),
        "mean_rank_ic": round(float(ic.mean()), 4),
        "median_rank_ic": round(float(ic.median()), 4),
        "std_rank_ic": round(float(ic.std()), 4),
        "ic_ir": round(icir, 3),
        "ic_t_stat": round(float(icir * np.sqrt(len(ic))), 2) if len(ic) else float("nan"),
        "pct_weeks_positive_ic": round(float((ic > 0).mean()) * 100, 1),
        "hit_rate_pct": round(hit * 100, 2),
        "n_predictions": int(len(valid)),
    }


def run(df: pd.DataFrame, n_folds: int, min_train: int, purge: int,
        embargo: int, seed: int = 0) -> tuple[dict, pd.DataFrame]:
    import lightgbm as lgb

    df = df.sort_values(["week_ending_friday", "ticker"]).reset_index(drop=True)
    df = df.dropna(subset=[TARGET])
    # Neutral fill for sparse ranks (see module docstring).
    X_all = df[RANK_COLS].fillna(0.5)
    weeks = np.array(sorted(df["week_ending_friday"].unique()))

    rows = []
    coefs: list[np.ndarray] = []
    gains: list[np.ndarray] = []

    folds = list(walk_forward_folds(weeks, n_folds, min_train, purge, embargo))
    print(f"[model] {len(folds)} walk-forward folds "
          f"(min_train={min_train}w, purge={purge}w, embargo={embargo}w)")

    for i, (tr_w, te_w) in enumerate(folds, 1):
        tr = df["week_ending_friday"].isin(tr_w)
        te = df["week_ending_friday"].isin(te_w)
        Xtr, ytr = X_all[tr], df.loc[tr, TARGET]
        Xte = X_all[te]
        if len(Xtr) < 200 or len(Xte) == 0:
            continue

        sc = StandardScaler().fit(Xtr)
        en = ElasticNet(alpha=1e-3, l1_ratio=0.5, max_iter=5000, random_state=seed)
        en.fit(sc.transform(Xtr), ytr)
        coefs.append(en.coef_)

        gbm = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.03, num_leaves=15,
            min_child_samples=50, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, reg_lambda=1.0, random_state=seed, verbose=-1)
        gbm.fit(Xtr, ytr)
        gains.append(gbm.booster_.feature_importance(importance_type="gain"))

        blk = df.loc[te, ["week_ending_friday", "ticker", TARGET]].copy()
        blk["pred_enet"] = en.predict(sc.transform(Xte))
        blk["pred_lgbm"] = gbm.predict(Xte)
        blk["fold"] = i
        rows.append(blk)
        print(f"    fold {i:2}: train {len(Xtr):>6,} rows → test {len(Xte):>5,} rows "
              f"({te_w[0].date()} … {te_w[-1].date()})")

    preds = pd.concat(rows, ignore_index=True)
    results = {}
    for col, lab in [("pred_enet", "ElasticNet"), ("pred_lgbm", "LightGBM")]:
        ic = weekly_rank_ic(preds, col)
        results[lab] = summarise(ic, preds, col, lab)
        results[lab]["ic_series"] = {str(k.date()): round(float(v), 4) for k, v in ic.items()}

    # Interpretability: mean standardised coefficient (β′F) and mean GBM gain.
    coef_mean = np.mean(coefs, axis=0)
    gain_mean = np.mean(gains, axis=0)
    gain_pct = 100 * gain_mean / gain_mean.sum() if gain_mean.sum() else gain_mean
    results["feature_importance"] = [
        {"feature": f, "category": "/".join(FEATURE_TAGS[f]),
         "enet_coef": round(float(c), 6), "lgbm_gain_pct": round(float(g), 2)}
        for f, c, g in zip(FEATURES, coef_mean, gain_pct)
    ]
    return results, preds


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--features", type=Path, default=FEATURES_PATH)
    p.add_argument("--folds", type=int, default=8)
    p.add_argument("--min-train", type=int, default=104, help="weeks (default 2y)")
    p.add_argument("--purge", type=int, default=1, help="weeks purged from train tail")
    p.add_argument("--embargo", type=int, default=1, help="weeks skipped after test")
    args = p.parse_args(argv)

    df = pd.read_parquet(args.features)
    print(f"[model] {len(df):,} rows, {df.ticker.nunique()} tickers, "
          f"{df.week_ending_friday.nunique()} weeks")

    results, preds = run(df, args.folds, args.min_train, args.purge, args.embargo)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(OUT_DIR / "oos_predictions.parquet", index=False)
    payload = {"run_at_utc": utc_now_iso(),
               "cv": {"folds": args.folds, "min_train_weeks": args.min_train,
                      "purge_weeks": args.purge, "embargo_weeks": args.embargo,
                      "scheme": "expanding-window walk-forward, purged + embargoed"},
               "features": RANK_COLS, "results": results}
    (OUT_DIR / "model_results.json").write_text(json.dumps(payload, indent=2))

    print("\n" + "=" * 66)
    print(f"{'metric':<26}{'ElasticNet':>18}{'LightGBM':>18}")
    print("-" * 66)
    for key in ["weeks_evaluated", "mean_rank_ic", "median_rank_ic", "std_rank_ic",
                "ic_ir", "ic_t_stat", "pct_weeks_positive_ic", "hit_rate_pct"]:
        print(f"{key:<26}{results['ElasticNet'][key]:>18}{results['LightGBM'][key]:>18}")
    print("=" * 66)
    print(f"\n{'feature':<16}{'category':<28}{'enet coef':>12}{'lgbm gain%':>12}")
    for r in sorted(results["feature_importance"], key=lambda x: -x["lgbm_gain_pct"]):
        print(f"{r['feature']:<16}{r['category']:<28}{r['enet_coef']:>12.5f}{r['lgbm_gain_pct']:>12.1f}")
    print(f"\n[model] saved → {rel(OUT_DIR / 'model_results.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
