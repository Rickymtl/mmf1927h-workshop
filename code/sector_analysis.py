"""Where does the signal actually work, and which keywords are noisy?

Two diagnostics that turn two of our stated limitations into measured ones.

------------------------------------------------------------------------------
1. Per-sector Information Coefficient — with false-discovery control
------------------------------------------------------------------------------
Rank IC computed *within* each GICS sector: each week we rank only that
sector's names and correlate against realised forward returns.

**The trap this must not fall into.** Testing 11 sectors and reporting the best
one is precisely the multiple-comparisons problem — with 11 independent tests
at α = 0.05 you expect ~0.5 false positives by chance, and the *maximum* t-stat
across 11 sectors is upward-biased even under a pure null. So we apply the
**Benjamini-Hochberg** procedure (Day 4) and report which sectors survive FDR
control at q = 0.10, not which sector happens to look best.

**The other trap: N = 8.** A Spearman correlation over 8 names per date is a
very weak statistic — Day 1's small-N caveat, relocated. Per-sector ICs are
therefore reported with wide error bars and should be read as *hypothesis
generating*, not as evidence a sector-specific strategy would work.

------------------------------------------------------------------------------
2. Keyword ambiguity
------------------------------------------------------------------------------
Our Trends keywords are company names, and several are ordinary words: "Apple"
catches the fruit, "Amazon" the river, "Visa" travel documents, "Caterpillar"
the insect, "Marathon" the race, "Duke" the university.  Ambiguous keywords add
search volume unrelated to the firm, which is noise in the signal.

We measure it rather than assert it.  For a keyword that genuinely tracks
attention to the *company*, weekly changes in search interest should co-move
with weekly changes in that firm's **trading activity**:

    ambiguity proxy  =  corr( Δ log SVI , Δ log dollar-volume )

**What we expected, and what we found.**  We flagged an a-priori list of
homonyms — "Apple" the fruit, "Amazon" the river, "Caterpillar" the insect —
expecting those to be the noisy ones.  **That prior was not supported**
(t = −1.04, p = 0.30).

The real driver turned out to be different: **consumer-brand search intent**.
Names people search in order to *shop* — Walmart, Costco, McDonald's, Home
Depot, Starbucks — have search that decouples from, and here actually inverts
against, trading activity.  B2B and industrial names with no consumer-search
channel — AbbVie, Broadcom, Nucor, NextEra — show the strongest coupling.

    Consumer sectors  mean corr =  0.043
    All other sectors mean corr =  0.340     (t = −4.03, p = 0.0008)

So the contaminating channel is *shoppers*, not homonyms.  That is a sharper
and more actionable finding than the one we went looking for.

This is a proxy, not proof: a low correlation could also mean the firm's news
simply does not drive retail search.  Read it alongside the sector breakdown.
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

from paths import PRICES_DIR, PROCESSED_DIR, rel, utc_now_iso
from universe import SECTORS, ticker_to_keyword, ticker_to_sector

OUT_DIR = PROCESSED_DIR / "sector_analysis"

# Keywords that are also ordinary words, proper nouns, or common products.
# Flagged a priori — before looking at any correlation — so the empirical
# measure below is a check on this list, not a replacement for judgement.
A_PRIORI_AMBIGUOUS = {
    "AAPL": "fruit", "AMZN": "river / general shopping", "V": "travel document",
    "META": "prefix, and the former Facebook brand", "ORCL": "prophecy",
    "TSLA": "the inventor", "CAT": "the insect", "UPS": "power supplies",
    "MPC": "the race", "DUK": "university", "NKE": "Greek goddess / footwear",
    "DIS": "theme parks and films, not the equity", "GOOGL": "navigational search",
    "LOW": "ordinary adjective", "SO": "ordinary word", "DE": "ordinary syllable",
    "PG": "also 'PG' film rating", "MO": "ordinary abbreviation",
    "T": "single letter", "D": "single letter", "O": "single letter",
}


# --------------------------------------------------------------------------
# 1. Per-sector IC with BH control
# --------------------------------------------------------------------------
def benjamini_hochberg(pvals: dict[str, float], q: float = 0.10) -> dict[str, bool]:
    """Return {key: rejected}. Controls expected false-discovery proportion."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    k_max = 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= (i / m) * q:
            k_max = i
    rejected = {k: False for k in pvals}
    for i, (k, _) in enumerate(items, start=1):
        if i <= k_max:
            rejected[k] = True
    return rejected


def sector_ic(preds: pd.DataFrame, pred_col: str, min_names: int = 5) -> pd.DataFrame:
    t2s = ticker_to_sector()
    df = preds.dropna(subset=[pred_col, "fwd_return"]).copy()
    df["sector"] = df["ticker"].map(t2s)

    rows = []
    for sector, g in df.groupby("sector"):
        ics = []
        for _, wk in g.groupby("week_ending_friday"):
            if len(wk) < min_names:
                continue
            ic, _ = stats.spearmanr(wk[pred_col], wk["fwd_return"])
            if np.isfinite(ic):
                ics.append(ic)
        if len(ics) < 20:
            continue
        ics = np.array(ics)
        mean, sd, n = ics.mean(), ics.std(ddof=1), len(ics)
        t = mean / (sd / np.sqrt(n)) if sd > 0 else np.nan
        p = 2 * (1 - stats.t.cdf(abs(t), df=n - 1)) if np.isfinite(t) else np.nan
        rows.append(dict(sector=sector, n_weeks=n, mean_ic=mean, std_ic=sd,
                         t_stat=t, p_value=p, pct_positive=100 * (ics > 0).mean(),
                         n_names=len(g.ticker.unique())))
    out = pd.DataFrame(rows).sort_values("t_stat", ascending=False)
    rej = benjamini_hochberg(dict(zip(out.sector, out.p_value)), q=0.10)
    out["survives_bh_q10"] = out.sector.map(rej)
    # Naive comparison: what a t>2 filter alone would have accepted.
    out["naive_t_gt_2"] = out.t_stat.abs() > 2
    return out


# --------------------------------------------------------------------------
# 2. Keyword ambiguity
# --------------------------------------------------------------------------
def _dollar_volume() -> pd.DataFrame:
    frames = []
    for f in sorted(PRICES_DIR.glob("*.csv")):
        try:
            d = pd.read_csv(f, usecols=["Date", "Close", "Volume"], parse_dates=["Date"])
        except ValueError:
            continue
        d["dv"] = d["Close"] * d["Volume"]
        d["ticker"] = f.stem
        frames.append(d[["Date", "ticker", "dv"]])
    return pd.concat(frames, ignore_index=True)


def keyword_ambiguity(panel: pd.DataFrame) -> pd.DataFrame:
    dv = _dollar_volume()
    dv["week"] = dv["Date"] + pd.to_timedelta((4 - dv["Date"].dt.dayofweek) % 7, unit="D")
    wk_dv = dv.groupby(["ticker", "week"], as_index=False)["dv"].sum()

    p = panel[["week_ending_friday", "ticker", "trends_interest"]].rename(
        columns={"week_ending_friday": "week"})
    m = p.merge(wk_dv, on=["ticker", "week"], how="inner").sort_values(["ticker", "week"])

    kw = ticker_to_keyword()
    t2s = ticker_to_sector()
    rows = []
    for ticker, g in m.groupby("ticker"):
        g = g[(g.trends_interest > 0) & (g.dv > 0)]
        if len(g) < 60:
            continue
        d_svi = np.log(g.trends_interest).diff()
        d_dv = np.log(g.dv).diff()
        ok = d_svi.notna() & d_dv.notna() & np.isfinite(d_svi) & np.isfinite(d_dv)
        if ok.sum() < 50:
            continue
        r, p_val = stats.pearsonr(d_svi[ok], d_dv[ok])
        rows.append(dict(ticker=ticker, keyword=kw[ticker], sector=t2s[ticker],
                         corr_svi_volume=r, p_value=p_val, n_obs=int(ok.sum()),
                         a_priori_flag=A_PRIORI_AMBIGUOUS.get(ticker, "")))
    out = pd.DataFrame(rows).sort_values("corr_svi_volume")
    out["flagged_a_priori"] = out.a_priori_flag != ""
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preds", type=Path,
                    default=PROCESSED_DIR / "models" / "oos_predictions_nested.parquet")
    ap.add_argument("--pred-col", default="pred_lgbm")
    ap.add_argument("--q", type=float, default=0.10)
    args = ap.parse_args(argv)

    preds = pd.read_parquet(args.preds)
    panel = pd.read_parquet(PROCESSED_DIR / "panel" / "panel_weekly.parquet")

    print("=" * 78)
    print(f"1. PER-SECTOR RANK IC  ({args.pred_col}, N≈8 per sector per week)")
    print("=" * 78)
    sec = sector_ic(preds, args.pred_col)
    print(f"{'sector':<26}{'names':>6}{'wks':>5}{'mean IC':>9}{'t':>7}"
          f"{'p':>8}{'%pos':>7}  {'BH q=.10':<9}")
    print("-" * 78)
    for r in sec.itertuples():
        mark = "SURVIVES" if r.survives_bh_q10 else ("t>2 only" if r.naive_t_gt_2 else "")
        print(f"{r.sector:<26}{r.n_names:>6}{r.n_weeks:>5}{r.mean_ic:>9.4f}"
              f"{r.t_stat:>7.2f}{r.p_value:>8.3f}{r.pct_positive:>7.1f}  {mark:<9}")
    n_naive = int(sec.naive_t_gt_2.sum())
    n_bh = int(sec.survives_bh_q10.sum())
    print("-" * 78)
    print(f"sectors with |t| > 2 taken naively: {n_naive}   surviving BH at q={args.q}: {n_bh}")

    print()
    print("=" * 78)
    print("2. KEYWORD AMBIGUITY — corr(Δlog search interest, Δlog dollar volume)")
    print("=" * 78)
    amb = keyword_ambiguity(panel)
    print(f"{'ticker':<7}{'keyword':<22}{'corr':>8}{'p':>8}   a-priori concern")
    print("-" * 78)
    print("WEAKEST 12 (search decoupled from trading activity):")
    for r in amb.head(12).itertuples():
        print(f"{r.ticker:<7}{r.keyword:<22}{r.corr_svi_volume:>8.3f}"
              f"{r.p_value:>8.3f}   {r.a_priori_flag}")
    print("\nSTRONGEST 8 (search tracks trading activity):")
    for r in amb.tail(8)[::-1].itertuples():
        print(f"{r.ticker:<7}{r.keyword:<22}{r.corr_svi_volume:>8.3f}"
              f"{r.p_value:>8.3f}   {r.a_priori_flag}")

    flagged = amb[amb.flagged_a_priori]
    clean = amb[~amb.flagged_a_priori]
    print()
    print("--- Does the a-priori homonym list explain it? ---")
    print(f"mean corr — a-priori ambiguous ({len(flagged)}): {flagged.corr_svi_volume.mean():.3f}")
    print(f"mean corr — rest ({len(clean)}):              {clean.corr_svi_volume.mean():.3f}")
    ap_t, ap_p = stats.ttest_ind(flagged.corr_svi_volume, clean.corr_svi_volume,
                                 equal_var=False)
    print(f"difference: t = {ap_t:.2f}, p = {ap_p:.3f}"
          f"  → {'supported' if ap_p < 0.05 else 'NOT supported — the prior was wrong'}")

    print()
    print("--- What actually explains it: consumer-brand search intent ---")
    by_sec = amb.groupby("sector")["corr_svi_volume"].mean().sort_values()
    for s, v in by_sec.items():
        bar = "▁" if v < 0 else "█" * max(1, int(v * 12))
        print(f"  {s:<26}{v:>8.3f}  {bar}")
    cons = amb[amb.sector.str.startswith("Consumer")]["corr_svi_volume"]
    rest = amb[~amb.sector.str.startswith("Consumer")]["corr_svi_volume"]
    c_t, c_p = stats.ttest_ind(cons, rest, equal_var=False)
    print()
    print(f"Consumer sectors (n={len(cons)}): mean {cons.mean():.3f}")
    print(f"All others       (n={len(rest)}): mean {rest.mean():.3f}")
    print(f"difference: t = {c_t:.2f}, p = {c_p:.4f}")
    print("\nReading: search for Walmart, Costco, McDonald's, Home Depot is dominated")
    print("by SHOPPING intent, not investor attention — so it decouples from (and here")
    print("inverts against) trading activity. B2B and industrial names — AbbVie,")
    print("Broadcom, Nucor, NextEra — have no consumer-search channel, so their search")
    print("IS investor attention. The mechanism is brand-vs-investor intent, not homonyms.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sec.to_csv(OUT_DIR / "sector_ic.csv", index=False)
    amb.to_csv(OUT_DIR / "keyword_ambiguity.csv", index=False)
    (OUT_DIR / "summary.json").write_text(json.dumps({
        "run_at_utc": utc_now_iso(), "pred_col": args.pred_col, "bh_q": args.q,
        "sectors_naive_t_gt_2": n_naive, "sectors_surviving_bh": n_bh,
        "mean_corr_ambiguous": float(flagged.corr_svi_volume.mean()),
        "mean_corr_rest": float(clean.corr_svi_volume.mean()),
    }, indent=2))
    print(f"\n[sector_analysis] saved → {rel(OUT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
