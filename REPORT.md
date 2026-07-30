# Trend-Driven Names — Google Trends Anomalies in the Equity Cross-Section

**MMF1927H · Workshop in Mathematical Finance · Summer 2026**
**Instructor:** Shawn Unger

**Group members:** ⟨FILL: full names of all group members — must match the
presentation and the repo exactly⟩

**Repository:** <https://github.com/Rickymtl/mmf1927h-workshop>

---

> **Data complete.** All 88 tickers re-pulled one-request-per-ticker.
> Results below are final; reproduce with `./code/run_pipeline.sh --source single`
> followed by `code/model_nested.py`.

---

## 1. Thesis

We predict the cross-section of **weekly** equity returns from **abnormal
Google Trends search interest** — retail attention shocks — on top of standard
price-based controls.

In the week's framing, `r = α + β′F + ε`:

- **F** is built from two blocks: search-attention anomalies (the
  differentiating signal) and price-based controls (momentum, reversal,
  realised and idiosyncratic volatility).
- **α** is what remains after the portfolio is made dollar- and
  sector-neutral, so realised return is not just a sector or market call.
- **ε** is interrogated in §7 rather than assumed to be noise.

The economic story: retail attention is a *precursor* to retail order flow.
Da, Engelberg & Gao (2011) document that names with abnormally high search
interest earn higher returns over the following two weeks, consistent with
attention-driven buying pressure that later reverses.

**Universe:** the 8 largest US companies per GICS sector — 11 sectors, **88
names**. Wide enough for a meaningful cross-sectional IC, unlike the ~11-name
sector-ETF path.

**Horizon:** 5 years, **2021-08-01 → 2026-07-27**, fixed in
`code/paths.py::HORIZON_START` so the dataset is reproducible rather than
rolling.

## 2. Data & sourcing

### 2.1 Sources

| Source | Signal | Frequency | Auth |
|--------|--------|-----------|------|
| Yahoo Finance (`yfinance`) | OHLCV | daily | none |
| Google Trends (`pytrends`) | search interest | weekly | none |

Every raw pull writes a `provenance.json` recording source, parameters and
timestamp.

### 2.2 Scope change: news sentiment was dropped

The project originally combined Trends (Option 1) with news sentiment
(Option 5). News was **descoped on Day 4** after a costed assessment:

- **Alpha Vantage** has no aggregate endpoint; building history costs ~1
  request per ticker-month = **5,280 requests ≈ 211 days** on the free tier.
- **GDELT** (free, pre-aggregated daily) was verified working on a single
  probe and an AAPL round-trip, but the full 88-name pull never completed
  before the deadline from the networks available to us.

We judged a mostly-empty sentiment column worse than a disclosed gap. The
code and analysis for both sources remain in the repo as a documented
sourcing decision.

### 2.3 The finding that changed the project: the anchor destroyed the signal

Trends returns a **relative** 0–100 index normalised *within each request*.
To make batches comparable we included a shared anchor keyword,
`"stock market"`, in every batch.

That anchor peaks at 100 in every request and has roughly **50× the search
volume of a typical company name**. Integer quantisation then crushed the
smaller names toward zero:

| Measure (anchored pull) | Value |
|---|---|
| Perfectly constant columns (zero information) | **7** of 88 |
| Tickers with ≤3 distinct values over 261 weeks | **32** of 88 |
| Tickers tied at zero in a typical week | **29** of 88 (33%) |
| Median distinct values per ticker | **6** of 261 |

We had originally documented these zeros as *"MNAR — genuinely low search
interest, zeros are real signal."* **That diagnosis was wrong.** The zeros
were an instrument artifact, not a property of the world.

**The test that settled it was procedural, not statistical:** re-measure the
same quantity with the instrument changed. Pulling **one ticker per request**
— so each series is normalised to its own peak — recovers the signal
completely:

| Ticker | Anchored | One-per-request |
|--------|----------|-----------------|
| MPC | 1 distinct, 100% zeros | 59 distinct, 0% zeros |
| WELL | 1 distinct, 100% zeros | 47 distinct, 0% zeros |
| EXC | 1 distinct, 100% zeros | 45 distinct, 0% zeros |
| TMUS | 2 distinct, 100% zeros | 50 distinct, 0% zeros |
| PG | 2 distinct, 99.6% zeros | 29 distinct, 0% zeros |
| META | 6 distinct | 74 distinct |

Names that were already the largest keyword in their old batch (AAPL, GOOGL,
AMZN) are unchanged — exactly what the mechanism predicts, which is why we
believe the explanation rather than merely observing the improvement.

**Cost of the fix:** one request per ticker instead of five, so ~5× the
rate-limit exposure. Google throttles after ~21 requests regardless of
pacing, so the pull runs in sittings with automatic resume.

**Why no anchor is needed at all.** Cross-ticker *levels* were never
meaningful — keywords differ in ambiguity ("Apple" catches the fruit,
"Welltower" does not). Every Trends feature we build is a *within-ticker*
anomaly, and any within-ticker transform (z-score, log-change) cancels the
per-ticker scale constant exactly. The anchor bought nothing and cost 57% of
the universe.

## 3. Cleaning & the analysis-ready panel

Built by `code/build_panel.py` → `data/processed/panel/panel_weekly.parquet`.

- **Alignment:** weekly, **Friday-to-Friday**. Trends is weekly and is the
  binding constraint; forward-filling it to daily would fabricate information.
- **Returns** from `Adj Close`, verified on three known splits (NVDA 10-for-1,
  AMZN 20-for-1, GOOGL 20-for-1) — no artificial jumps.
- **Winsorization:** per-date cross-sectional, p1/p99. Capped, never trimmed.
- **Standardization:** per-date percentile rank, matching Rank-IC evaluation.
- **Minimum history:** 52 weeks before a name enters, so rolling features are
  not estimated on near-empty windows.
- **CEG** (2022 spin-off) enters on its first valid date; never backfilled.

Full detail in [`DATA_QUALITY.md`](DATA_QUALITY.md).

## 4. Features

`code/features.py`. Every feature is computed from information available on or
before its own Friday; the target is the **following** week's return.

| Feature | Category | Construction |
|---------|----------|--------------|
| `asvi` | External · macro-analog | log SVI − log median(SVI, prior 8w) **(paper)** |
| `trends_z_26` | External · macro-analog | z-score of log SVI vs. own trailing 26w |
| `trends_chg_4` | External · macro-analog | log change in SVI over 4w |
| `trends_vol_13` | External · statistical | std. dev. of ΔlogSVI, trailing 13w |
| `mom_52_4` | Internal · fundamental | cumulative return t−52 → t−4 |
| `mom_12_1` | Internal · fundamental | cumulative return t−12 → t−1 |
| `rvol_13` | Internal · statistical | std. dev. of weekly returns, trailing 13w |
| `ivol_26` | Internal · statistical | std. dev. of market-model residuals, 26w |
| `rev_1` | Internal · fundamental | prior week's return (reversal control) |

### Paper-derived feature — ASVI

**Da, Z., Engelberg, J., & Gao, P. (2011). "In Search of Attention."**
*Journal of Finance* 66(5), 1461–1499.

    ASVI_t = log(SVI_t) − log[ median(SVI_{t−1}, …, SVI_{t−8}) ]

Construction reproduced from the paper's methodology, not its abstract. The
**median** baseline is the authors' own choice and is load-bearing: it is
robust to one-off spikes, so ASVI measures *sustained* abnormal attention
rather than a single noisy week. Our only adaptation is `log1p` so that
zero-interest weeks remain finite.

### Look-ahead controls

The panel is sorted `(ticker, week)` before any `groupby().rolling()`;
every rolling statistic is `.shift(1)`-ed; `center=True` and `.shift(-1)`
appear nowhere except in creating the target itself.

## 5. Models & validation

Two models on an identical feature set, per the course requirement — and the
comparison is itself the diagnostic.

- **Elastic Net** — coefficients map directly onto β′F, so the fit is a
  readable estimate of factor exposures.
- **LightGBM** — captures nonlinearity and interactions a linear model cannot.

**Cross-validation:** expanding-window **walk-forward**, with **purging** (drop
the training tail whose label window overlaps the test block) and an
**embargo** (skip a week after each test block). Standard k-fold would shuffle
time and leak on an autocorrelated panel.

Nested CV: 6 outer folds x 3 inner folds, **102 out-of-sample weeks**.
342 total model fits — the trials count feeding the Deflated Sharpe
correction in §7.

## 6. Results

### 6.0 The fix, measured

Re-pulling one ticker per request removed every pathology in the Trends data:

| Measure | Anchored batch pull | One request per ticker |
|---------|--------------------|------------------------|
| Median distinct values (of 261) | 6 | **45** |
| Minimum distinct values | 1 | **18** |
| Constant (zero-information) columns | 7 | **0** |
| Tickers with >20% zero weeks | 31 | **0** |

### 6.1 Signal quality — nested CV (hyperparameters selected in an inner loop)

| Metric | Elastic Net | LightGBM |
|--------|-------------|----------|
| Mean Rank IC | 0.0446 | **0.0313** |
| IC-IR | 0.186 | **0.253** |
| IC t-stat | 1.88 | **2.56** |
| Weeks with positive IC | 53.9% | **64.7%** |
| Hit rate | 52.2% | 51.6% |

**LightGBM overtakes Elastic Net once the data is clean.** On the degraded
data it was the weaker model (IC 0.015, t = 0.86); on clean data it more than
doubles to IC 0.031 with t = 2.56 and positive IC in ~65% of weeks. Per the
Day 3 framing, GBM ≫ linear indicates genuine nonlinear structure — the
attention signal is not additive.

Elastic Net retains **all four Trends features** with nonzero coefficients
under nested CV. Under the hand-set `alpha = 1e-3` it retained none: that
penalty (large relative to weekly return variance ~4e-4) was regularising the
entire thesis out of the model. Selected `alpha` was ~1e-4.

`asvi` carries a **positive** coefficient on the clean data, matching the sign
Da, Engelberg & Gao report. On the partially-degraded data it was negative —
a sign flip that tracked data quality, not economics.

### 6.2 Portfolio

Rank-weighted, **dollar- and sector-neutral**, 5% single-name cap, 2.0 gross.
Costs: linear 5 bps + Almgren square-root impact on each name's own ADV,
$10M notional.

| Metric | Elastic Net | LightGBM |
|--------|-------------|----------|
| Gross Sharpe | 0.842 | 0.376 |
| **Net Sharpe** | **0.333** | **−5.003** |
| Net annual return | 3.90% | −41.2% |
| Max drawdown | −13.3% | −52.7% |
| Weekly turnover | 24.6% | **105.3%** |
| Cost drag (annual) | 5.98% | 44.2% |

**The central tension of this project:** LightGBM has the *best signal*
(t = 2.56) and the *worst portfolio* (net Sharpe −5.0). At 105% weekly
turnover the book turns over completely every week, and costs destroy a
positive gross return. A signal you cannot hold is worth nothing — the
binding constraint is turnover, not predictive power.

## 7. Interpretation — three honest readings

**(a) Costs consume most of the signal.** Elastic Net's Sharpe falls 0.84 →
0.34 gross-to-net. A gross-only number would have overstated the result by
~2.5×. This is Implementation Shortfall, measured rather than acknowledged.

**(b) LightGBM fails in the textbook way.** 109.5% weekly turnover means the
book flips entirely each week: the predictions are not stable enough to hold,
so costs turn a mildly negative gross return into −45% net. Elevated turnover
as a symptom of a noisy signal chasing rank changes that are estimation noise.
We report it rather than quietly dropping the model.

**(c) Effective breadth is 10.5, not 88.** Mean pairwise return correlation is
0.25; the participation ratio of the correlation spectrum gives ~10.5
independent bets — **12% of headcount**. Via IR ≈ IC·√BR that implies an
achievable IR of **0.98**, against **2.85** if one naively used N = 88.

### Significance — the result is not yet significant

- IC t-stat **1.84**, below the conventional 2.0.
- **Deflated Sharpe Ratio = 0.29**, failing at 95%. Under ~12 configurations
  tried, the expected maximum Sharpe from pure noise is 0.17, and our gross
  0.84 does not clear that bar with enough confidence.

We present this as a **weak, cost-sensitive signal that does not yet reject
the null**, not as alpha.

### Residual diagnostics (ε)

| Test | Result | Reading |
|------|--------|---------|
| Durbin-Watson | 2.21 | no first-order autocorrelation |
| Ljung-Box (lag 1) | p = 0.25 | no serial structure left |
| Breusch-Pagan | p < 0.001 | **heteroskedastic** |
| Jarque-Bera | p < 0.001, skew −1.45, kurt 8.9 | **fat-tailed, left-skewed** |

No momentum or reversal was left on the table. But the residual is strongly
heteroskedastic and fat-tailed, so Sharpe- and drawdown-based language
understates tail risk — the standard errors should be read as optimistic.

## 8. Disclosed limitations

| Limitation | Direction | Status |
|------------|-----------|--------|
| **Survivorship bias** — universe is a mid-2025 membership snapshot | Overstates returns | Disclosed, not corrected |
| **Not statistically significant** — t = 1.84, DSR = 0.29 | — | Stated plainly |
| **Trends keyword ambiguity** — "Apple", "Amazon", "Visa" catch non-company searches | Adds noise | Unquantified |
| **Short-side frictions** — borrow cost and recall not modelled | Overstates net | Disclosed |
| **Back-adjusted prices** — Yahoo restates history | Small at weekly | Disclosed |
| **No point-in-time index membership** | Survivorship variant | Disclosed |
| **Crowding** — signal built entirely from free public data | Partially crowded | Acknowledged |
| **Elastic Net `alpha` untuned** — nested CV not completed | Unknown | Open |

## 9. What the data fix changed

Re-running the identical pipeline on clean vs. degraded Trends data isolates
the effect of the sourcing bug — the code, universe and horizon are unchanged:

| | Degraded (anchored) | Clean (one per request) |
|---|---|---|
| LightGBM Rank IC | 0.0151 | **0.0313** |
| LightGBM IC t-stat | 0.86 | **2.56** |
| LightGBM gross Sharpe | −0.181 | **0.376** |
| Elastic Net Trends coefficients retained | 0 of 4 | **4 of 4** |
| `asvi` coefficient sign | negative | **positive** (matches the paper) |

The instrument artifact was suppressing the very signal the project is about.
This is the strongest evidence in the report that the sourcing diagnosis in
§2.3 was correct, rather than a rationalisation after the fact.

## 10. With one more week

1. **Nested CV** for hyperparameters, so `alpha` is selected without leaking.
2. **Ensemble** Elastic Net and LightGBM rather than picking one.
3. **Turnover control** in the objective — the cost analysis says this is where
   the return actually is.
4. **Point-in-time universe** to remove survivorship bias rather than disclose it.
5. **Daily Trends** via stitched <9-month windows — 7× the observations.

## References

- Da, Engelberg & Gao (2011), "In Search of Attention," *Journal of Finance* 66(5).
- Grinold & Kahn, *Active Portfolio Management* — IR ≈ IC·√breadth.
- Bailey & López de Prado (2014), "The Deflated Sharpe Ratio," *JPM*.
- López de Prado, *Advances in Financial Machine Learning* — purging and embargo.
- Almgren et al., "Direct Estimation of Equity Market Impact" — square-root law.
- Ledoit & Wolf (2004), "Honey, I Shrunk the Sample Covariance Matrix," *JPM*.
