# MMF1927H — Workshop in Mathematical Finance

**Group:** Ricky Mao, Saier Ma, Tim Yuan, Nick Sun, Aaron Hou

Predicting the cross-section of weekly equity returns for the **8 largest US
companies per GICS sector (88 names)** from **Google Trends search-interest
anomalies**, on top of price data — course **Option 1, Trend-Driven Names**.
Study horizon: **5 years from 2021-08-01**.
Full project description [below](#project-trend-driven-names-google-trends-anomalies-in-the-equity-cross-section).

> **Scope change (2026-07-30, Day 4).** The news-sentiment half (Option 5) is
> **descoped**. Alpha Vantage's free tier could not fund the history
> (~5,280 requests ≈ 211 days), and GDELT — the free alternative — was
> reachable in a single verified probe but never completed a full 88-name pull
> before the deadline. Rather than ship a mostly-empty sentiment column, the
> project is now **prices + Trends only**. The sourcing analysis for both news
> sources is retained below as a documented, defensible sourcing decision
> ([#2](https://github.com/Rickymtl/mmf1927h-workshop/issues/2),
> [#6](https://github.com/Rickymtl/mmf1927h-workshop/issues/6),
> [#8](https://github.com/Rickymtl/mmf1927h-workshop/issues/8),
> [#15](https://github.com/Rickymtl/mmf1927h-workshop/issues/15)).

---

## TODO — start here

Work is tracked in [**GitHub Issues**](https://github.com/Rickymtl/mmf1927h-workshop/issues)
— claim one by assigning yourself, and open a PR that closes it. This list is
the map; the issues have the detail, context, and acceptance criteria.

### Where the data currently stands

| Source | Status |
|--------|--------|
| Prices | ✅ 88/88 (pulled from 2015 — a superset of the horizon, filter when building the panel) |
| Trends | ✅ 88/88 (all pulled across 22 batches; **rescaling done** — [#3](https://github.com/Rickymtl/mmf1927h-workshop/issues/3)) |
| GDELT | 🚫 **Descoped** — code works (probe + AAPL round-trip verified), but no full pull landed before the deadline. |
| AV news | 🚫 **Descoped** — free tier infeasible (~5,280 requests ≈ 211 days). |

> ⚠️ **Trends counts are per-machine.** `data/` is gitignored, so the 88/88
> pull lives only on the machine that ran it (plus the shared Drive folder).
> A fresh clone has **zero** rows until someone copies the data across — see
> [#16](https://github.com/Rickymtl/mmf1927h-workshop/issues/24).

### Blocking — finish sourcing first (Day 1→2)

- [x] [#1 Resume Google Trends pull — 44/88 missing](https://github.com/Rickymtl/mmf1927h-workshop/issues/1)
      · done: all 88/88 tickers pulled. Required switching to a residential IP (cell hotspot)
        to get past Google rate-limiting on the last 4.
- [ ] [#2 Verify GDELT and pull daily history](https://github.com/Rickymtl/mmf1927h-workshop/issues/2)
      · live response shape and a 366-row AAPL 2024 CSV verified. The shared
      pulling network was subsequently throttled; run the resumable full pull
      from a stable residential connection.
- [x] [#9 Study horizon follow-ups (5y from 2021-08-01)](https://github.com/Rickymtl/mmf1927h-workshop/issues/9)
      · fixed: `HORIZON_TIMEFRAME = "2021-08-01 2026-07-27"` in `paths.py`,
      all scripts now share one absolute window.
- [x] [#8 Pull Alpha Vantage news for all 88 tickers](https://github.com/Rickymtl/mmf1927h-workshop/issues/8)
      · closed in favour of [#6](https://github.com/Rickymtl/mmf1927h-workshop/issues/6) — AV dropped from scope
      (free tier infeasible: ~5,280 requests ≈ 211 days).

### Session 2 — cleaning & alignment

- [x] [#3 Rescale Trends by batch anchor](https://github.com/Rickymtl/mmf1927h-workshop/issues/3)
      · done: 88/88 tickers rescaled via `code/cleaning/rescale_trends.py`.
      Output in `data/processed/trends_rescaled/`. 68 tickers used an
      average anchor (batch anchors lost to resume overwrites; the 5
      surviving anchors are correlated at 0.9999+, so the impact is negligible).
- [x] [#4 Build the weekly Friday-to-Friday panel](https://github.com/Rickymtl/mmf1927h-workshop/issues/4)
      · the core Session 2 deliverable — Validate → Align → Impute/Winsorize →
        Analysis-ready.  Also covers: target definition, lineage manifest,
        minimum-history threshold, Parquet storage, categorical encoding.
        Watch the lookahead traps.
- [x] [#12 Missing-data policy & imputation](https://github.com/Rickymtl/mmf1927h-workshop/issues/12)
      · classify missingness per Rubin (MCAR/MAR/MNAR), choose imputation
        methods per source, set max gap lengths, prevent leakage.
- [x] [#13 Outlier treatment & cross-sectional standardization](https://github.com/Rickymtl/mmf1927h-workshop/issues/13)
      · per-date winsorization at p1/p99, rank vs. z-score, sector-neutralization.
- [x] [#7 Adjusted prices, corporate actions, missing-data policy](https://github.com/Rickymtl/mmf1927h-workshop/issues/7)
      · returns must come from `Adj Close`, or splits become fake signal.
      · **Verified:** NVDA 10-for-1 (Jun 2024): Adj Close ret 0.75%, AMZN 20-for-1
      (Jun 2022): 1.99%, GOOGL 20-for-1 (Jul 2022): -2.46% — all normal daily moves.
      · 26/88 tickers have 6–19 repeated-Close days (low-vol names, not data errors).
      · CEG (spin-off) is the only short-history ticker; starts 2022-01-19, kept in
      universe, flagged. Daily returns saved to `data/processed/returns/`.

### Methodology & write-up

- [x] [#5 Survivorship bias in the universe](https://github.com/Rickymtl/mmf1927h-workshop/issues/5)
      · disclosed and quantified below; Day 4 robustness check methodology recorded.
- [x] [#6 Decide Alpha Vantage's role](https://github.com/Rickymtl/mmf1927h-workshop/issues/6)
      · **Tim (suggestion): skip AV.** GDELT is the sole news source. AV free tier is
      infeasible (~5,280 requests ≈ 211 days). If a premium key becomes
      available, revisit. Document this limitation in the Friday write-up.
- [x] [#14 Data-quality memo](https://github.com/Rickymtl/mmf1927h-workshop/issues/14)
      · half-page Day 2 deliverable — imputation summary, winsorization
        thresholds, names/dates dropped, known limitations carried forward.
- [ ] [#15 GDELT integration runbook](https://github.com/Rickymtl/mmf1927h-workshop/issues/15)
      · step-by-step for wiring GDELT into the panel once #2 lands.

### Session 3 — feature engineering & modeling

- [ ] [#16 Build feature engineering module (core features)](https://github.com/Rickymtl/mmf1927h-workshop/issues/16)
      · every feature tagged internal/external + risk-model bucket
        (fundamental/statistical/macro). Feature-level cleaning distinct
        from Day 2. Feature log of everything tried, not just survivors.
- [ ] [#17 Paper-derived feature — Da, Engelberg & Gao (2011) ASVI](https://github.com/Rickymtl/mmf1927h-workshop/issues/17)
      · implement the Abnormal Search Volume Index (ASVI) from "In Search
        of Attention." Formula: log deviation of current Trends interest
        from its 8-week rolling median. Cite the paper, reproduce the
        construction, not just the abstract.
- [ ] [#18 Statistical risk model — PCA on returns](https://github.com/Rickymtl/mmf1927h-workshop/issues/18)
      · eigen-decompose weekly return covariance matrix, extract top-k
        PCs. Document loading instability (sign flips, rotation ambiguity
        across refits). Use as diagnostic / risk hedge, not alpha source.
- [ ] [#19 Penalized regression — Elastic Net](https://github.com/Rickymtl/mmf1927h-workshop/issues/19)
      · time-series CV (no random K-fold). Standardize features before
        penalizing. Lasso zeros correlated features. Report coefficients
        as literal β estimates — the interpretable model.
- [ ] [#20 Gradient boosting — LightGBM](https://github.com/Rickymtl/mmf1927h-workshop/issues/20)
      · time-series CV. SHAP summary + dependence plots. Compare GBM vs.
        Elastic Net gap — large gap suggests nonlinear structure. Watch
        lookahead bugs: no center=True, no shift(-1).
- [ ] [#21 Signal evaluation — IC, hit rate, IC-IR](https://github.com/Rickymtl/mmf1927h-workshop/issues/21)
      · rank IC (Spearman) per week — not one pooled snapshot. IC time
        series: mean, std, IC-IR (t-stat). Hit rate. By sub-period
        (2021–22, 2023, 2024–25, 2026 YTD).
- [ ] [#22 Target definition & cross-validation design](https://github.com/Rickymtl/mmf1927h-workshop/issues/22)
      · raw return vs. factor-neutral return — a named modeling decision.
        Design purged time-series CV splits (no future leak). Justify
        pooled model across all 88 tickers.
- [ ] [#23 Feature selection report](https://github.com/Rickymtl/mmf1927h-workshop/issues/23)
      · five criteria per feature: economic rationale, stability across
        sub-periods, turnover cost, orthogonality (VIF), OOS IC persistence.
        Keep/drop summary table. Multicollinearity clustering.

### Day 3 — data coverage constraints

⚠️ **GDELT still blocked** ([#2](https://github.com/Rickymtl/mmf1927h-workshop/issues/2)) —
news-based features (tone momentum, volume spikes, attention proxies) are
not buildable until the full 88-name GDELT pull lands. The Day 3 feature
set is **prices + Trends only**. This limitation is:
- flagged in the feature log ([#16](https://github.com/Rickymtl/mmf1927h-workshop/issues/16))
- carried forward in the data-quality memo ([#14](https://github.com/Rickymtl/mmf1927h-workshop/issues/14))
- a disclosed limitation in the Friday write-up

A `# TODO(#2)` block is in `code/build_panel.py` for wiring GDELT tone/volume
into the panel; [#15](https://github.com/Rickymtl/mmf1927h-workshop/issues/15) is
the integration runbook. Once #2 lands, re-run the panel build and feature
construction to add the news-derived features.

### Later (Days 4–5)

- [ ] Survivorship-bias robustness check (S&P 500 hold-out — see [#5](https://github.com/Rickymtl/mmf1927h-workshop/issues/5))
- [ ] Portfolio construction (long-short decile sort, mean-variance-lite)
- [ ] Implementation shortfall: paper vs. realized Sharpe
- [ ] Friday presentation

**New to the repo?** Jump to [Setup](#setup), then [Pulling raw data](#pulling-raw-data).

---

## Project: Alternative-Data Signals for Cross-Sectional Equity Returns

**Combining Topic 1 (Google Trends anomalies) + Topic 5 (news sentiment).**

We predict the cross-section of next-period equity returns using two
*orthogonal alternative-data signals* layered on top of standard price data:

1. **Search-interest anomalies** — abnormal Google Trends search volume for a
   company name (retail attention shocks that often lead short-horizon returns).
2. **News-headline sentiment** — ticker-level news tone
   (information flow not yet fully reflected in price).

Price/OHLCV data provides the return target and momentum/volatility controls;
the two alternative signals are the differentiating features. The thesis
(`r = α + β'F + ε`): retail attention and news sentiment carry short-horizon
**α** not spanned by standard price/volume factors.

### Universe

The **8 largest US companies per GICS sector** (11 sectors → **88 names**), a
cross-section wide enough for meaningful cross-sectional IC (avoiding the
small-N caveat that hits the sector-ETF / single-index paths). See
[`code/universe.py`](code/universe.py).

> **⚠️ Documented limitation — survivorship bias.** The universe is a
> *current-membership* snapshot (top 8 per GICS sector as of mid-2025), not
> point-in-time constituents. We are selecting firms we *already know* survived
> and thrived, then asking whether a signal predicted their returns — a
> textbook look-ahead selection bias.
>
> **Direction:** upward. Survivors by definition outperformed (or at minimum
> outlasted) the firms that were top-8 in 2021 but have since fallen. Any
> backtest return or IC estimated on this universe is overstated.
>
> **Rough magnitude — worst-affected names.** Several current top-8 names were
> nowhere near the top of their sector in 2021:
>
> | Ticker | Sector | Why it's a problem |
> |--------|--------|--------------------|
> | NVDA | IT | ~$350B market cap in 2021; ~$3T today. Was not a top-8 IT name. |
> | AVGO | IT | Massive acquisition-driven growth (VMware, etc.) since 2022. |
> | LLY | Health Care | GLP-1 drug boom (Mounjaro/Zepbound) drove multi-year rally starting 2022. |
> | CEG | Utilities | Nuclear/AI-data-center story emerged 2023–2024; not a top utility in 2021. |
> | GE | Industrials | Breakup announcement (2021) and subsequent re-rating; turnaround story. |
>
> These names' strong returns over our horizon are partly *selection*, not
> prediction — we put them in the universe *because* they did well. A model
> that loads on them will look better than it is.
>
> **What we're doing about it:**
> 1. **Now (Day 1):** disclosed here. The rubric explicitly credits an
>    identified, quantified limitation — hiding it is worse than having it.
> 2. **Day 4 robustness check (planned):** re-run the final model on a
>    broader, equal-weighted universe (e.g., all S&P 500 names with data,
>    or a random-N sample) to verify the signal does not vanish when
>    survivorship selection is removed. Methodology recorded below.
> 3. **Long run (beyond workshop):** reconstruct true point-in-time
>    top-8-per-sector membership from historical market-cap data (WRDS/
>    Compustat/CRSP) so selection is honest at every rebalance date.
>
> Tracked as [#5](https://github.com/Rickymtl/mmf1927h-workshop/issues/5).

> **⚠️ Documented limitation — back-adjusted prices.** Yahoo Finance restates
> the *entire* ``Adj Close`` history whenever a new dividend or split occurs.
> The ``Adj Close`` we pulled today is **not** what an investor would have
> observed in real time on a given historical date — it contains the benefit
> of hindsight for every subsequent corporate action.
>
> **Direction:** small for weekly returns. Splits and dividend adjustments
> affect daily levels, but the week-over-week return impact is typically
> immaterial compared to the signal we are looking for. NVDA's 10-for-1 split
> (June 2024) shows a 0.75% Adj Close return on the split date — a normal
> daily move. AMZN's 20-for-1: 1.99%. GOOGL's 20-for-1: -2.46%.
>
> **What we're doing about it:** stated here as a known point-in-time
> imperfection.  We keep raw ``Close`` and ``Adj Close`` as separate columns
> in the price CSVs (``auto_adjust=False`` at pull time).  For a production
> pipeline the fix is storing raw price + adjustment factor as separate
> series and computing adjusted returns on the fly, but for a 5-day workshop
> the residual bias is acceptable.
>
> Tracked as [#7](https://github.com/Rickymtl/mmf1927h-workshop/issues/7).

### Day 4 robustness-check methodology (survivorship bias)

When the model is trained and we have a signal, run this check before Friday:

1. **Build a hold-out universe.** Pull daily prices for all ~500 S&P 500
   constituents (or the largest ~300 by current market cap for tractability)
   over the same 2021-08-01 → 2026-07-27 horizon. This universe includes
   names that fell out of the top 8 — it does not pre-select winners.

2. **Apply the same signal.** Use the same feature pipeline (Trends anomaly,
   GDELT tone/volume, momentum controls) on thehold-out names. If Trends data
   is unavailable for some tickers (pytrends keyword mismatch), drop them
   and note the coverage gap.

3. **Compare IC.** Compute the rank IC on:
   - Our 88-name survivorship-biased universe
   - The broader S&P 500 universe
   - If the IC on the broader universe is meaningfully lower (or zero), the
     signal is partly an artifact of winner selection. If it holds, the
     signal is real.

4. **Report the spread.** A sentence for the Friday deck: *"IC on our 88-name
   universe was X; on the full S&P 500 it was Y. The delta of Z suggests
   survivorship bias accounts for roughly W% of the apparent signal."*

5. **Fallback if there's no time:** at minimum, state the expected direction
   (IC overstated) and note that the check was planned but not executed due
   to the 5-day scope — this is itself a disclosed limitation.

### Day 3 — Feature engineering methodology

We follow the Day 3 framework (slides p9–30): every feature is tagged along two
axes — **provenance** (internal vs. external) and **risk-model bucket**
(statistical, fundamental, macroeconomic). The five feature-selection criteria
from slide 22 gate what makes the final set.

#### Feature axes

**Internal / endogenous** — derived from the asset's own data (returns, Trends
interest). These answer "what is this asset doing?"

**External / exogenous** — derived from outside the asset (macro rates, regime
indicators). These answer "what is happening to this asset?"

#### Three risk-model buckets (slides 12–15)

| Model | Factor source | Interpretability | Our use |
|-------|--------------|-----------------|---------|
| **Fundamental** (Barra-style) | Pre-specified characteristics (momentum, ASVI, idiosyncratic vol) | High — every factor has an economic label | Primary alpha source — most features live here |
| **Statistical** (PCA) | Eigen-decomposition of return covariance | Low — no a priori label, loadings unstable across refits | Diagnostic / risk-hedging complement, not alpha |
| **Macroeconomic** | Observable series applied identically to all names (rate level, term spread) | High — tied to named macro regimes | Conditioning overlay; rate-sensitivity beta |

#### Feature table

| # | Feature | Axis | Risk-model bucket | Construction |
|---|---------|------|-------------------|-------------|
| 1 | momentum_12_1 | Internal | Fundamental | ret(t−12, t−1), most recent month skipped (Jegadeesh–Titman) |
| 2 | momentum_6_1 | Internal | Fundamental | ret(t−6, t−1), shorter-horizon variant |
| 3 | idiosyncratic_vol | Internal | Statistical | Std dev of rolling 52-week market-model residuals |
| 4 | trends_abnormal (ASVI) | Internal | Fundamental | log(Trends_t) − log(median(Trends_{t−1…t−8})) — Da, Engelberg & Gao (2011) |
| 5 | trends_momentum_4w | Internal | Fundamental | Δ Trends interest, 4-week |
| 6 | trends_volatility_12w | Internal | Fundamental | Std dev of Trends over trailing 12 weeks |
| 7 | rate_sensitivity_beta | External | Macro | Rolling 52-week β of return on ΔUST10Y |
| 8 | pca_1 … pca_k | Internal | Statistical | Top-k PCs of weekly return covariance |

⚠️ **GDELT features blocked** (tone momentum, volume spikes, news+tone
composite) — pending [#2](https://github.com/Rickymtl/mmf1927h-workshop/issues/2).
Logged as "planned, blocked" in the feature log.

#### Feature-level cleaning (slide 23)

Feature construction introduces a second layer of cleaning **distinct from
Day 2's panel-level work**:
- Feature-specific winsorization at construction time (a ratio feature like
  ASVI can produce extreme values from clean raw inputs)
- Decay weighting for momentum-style features
- Standardization at construction vs. inherited from Day 2

Every derived feature is checked again after construction — they can
reintroduce the exact problems Day 2 fixed at the panel level.

#### Feature selection: five criteria (slide 22)

A feature makes the final set only if it passes most of these:

1. **Economic rationale** — a story for *why* it should predict, not just
   that it happens to correlate
2. **Stability over time** — signal persists across sub-periods, not
   concentrated in one regime
3. **Turnover cost** — a feature that flips fast generates trading costs
   that can erase an on-paper IC
4. **Orthogonality** — low correlation with features already in the set
   (VIF = 1/(1−R²)). Redundancy adds noise, not information
5. **OOS IC persistence** — computed on data the feature-search process
   never touched

#### Feature-search discipline (slide 27)

Searching many candidates and keeping only the ones that "work" in-sample is
a multiple-comparisons problem. Our guardrails:
- **Every feature tried is logged**, not just the survivors
- Features with ex-ante economic rationale are preferred over those found
  by trawling
- A feature that fails most of the five criteria is dropped with a
  documented reason — showing negative results is itself rigor

#### Paper-derived feature (slide 19)

**Da, Engelberg & Gao (2011) — "In Search of Attention"** (Journal of Finance).
The Abnormal Search Volume Index (ASVI) captures retail attention shocks as
log deviations of search volume from an 8-week rolling median. Implemented as
`trends_abnormal` in the feature table above (feature #4). The paper's finding
— that high ASVI predicts short-term reversals — is testable with our data.

#### Target definition (slide 8)

**We predict raw weekly return.** Chosen over factor-neutral return because
our thesis is factor-timing: retail attention and news sentiment are
systematic drivers, and factor-neutralising the target would discard the
variance we are modelling. This is a named, defensible decision — the rubric
(20%) explicitly credits identifying whether α is idiosyncratic or factor
risk.

#### Model strategy (slides 29–30)

Two models are fit on the same feature set and compared:

| Model | Strength | Weakness | Diagnostic value |
|-------|----------|----------|-----------------|
| **Elastic Net** (penalized regression) | Interpretable coefficients = literal β estimates | Assumes linearity/additivity | Maps directly to β'F in the thesis equation |
| **LightGBM** (gradient boosting) | Captures nonlinearities/interactions automatically | Less interpretable without SHAP | The gap vs. Elastic Net tells us whether nonlinear structure exists |

- GBM ≫ linear → real nonlinear structure in the features
- GBM ≈ linear → simpler story works, prefer the interpretable model

Both use **time-series cross-validation** — purged splits, no random shuffle,
no future information in training folds. Random K-fold leaks temporal
structure and silently inflates OOS performance.

#### Evaluation metrics (slides 5–7)

| Metric | What it measures | Caveat |
|--------|-----------------|--------|
| **Rank IC** (Spearman ρ) | Cross-sectional ranking quality per week | A single-period number is noisy — look at the IC time series |
| **Hit rate** | Share of predictions with correct sign | Blind to magnitude |
| **IC-IR** (t-stat of IC series) | Whether the IC is stable enough to trade | mean(IC) / std(IC) × √n_weeks |

All three are reported by sub-period (2021–22, 2023, 2024–25, 2026 YTD).
An IC that is only strong pooled across the whole sample may be carried by
one regime.

### The four-stage pipeline

| Stage | Owning day | This repo |
|-------|-----------|-----------|
| **Source** | Day 1 | `code/pull_*.py` — raw prices, trends, news |
| Clean | Day 2 | `code/cleaning/` — rescale, verify, impute, winsorize, build panel |
| Feature / Model | Day 3 | `code/features/`, `code/models/`, `code/evaluate/` — feature construction, Elastic Net, LightGBM, IC |
| Evaluate | Day 4–5 | _tbd_ |

## Data sources

| Source | Signal | Native frequency | Coverage | Auth | Script |
|--------|--------|------------------|----------|------|--------|
| Yahoo Finance (`yfinance`) | OHLCV prices | **daily** | full horizon | none | [`code/pull_prices.py`](code/pull_prices.py) |
| Google Trends (`pytrends`) | search interest | **weekly** | full horizon (rolling) | none | [`code/pull_trends.py`](code/pull_trends.py) |
| GDELT DOC 2.0 | news tone + volume | **daily** | full horizon | none | [`code/pull_gdelt.py`](code/pull_gdelt.py) |
| Alpha Vantage `NEWS_SENTIMENT` | article sentiment | **event-level** | ~2022–, quota-limited | **API key** | [`code/pull_news.py`](code/pull_news.py) |

### Study horizon

All sources default to **`HORIZON_START = 2021-08-01`** (5 years), defined once
in [`code/paths.py`](code/paths.py). Google Trends is the binding constraint —
`HORIZON_TIMEFRAME = "2021-08-01 2026-07-27"` (5 years, fixed). It is a
**fixed** window, not "today minus 5 years", so the dataset stays reproducible.

Existing price CSVs were pulled from 2015 and are a harmless superset — filter
to the horizon when building the panel rather than re-pulling.

## The frequency mismatch (and how we handle it)

The mismatch is **real**, and it is a depth problem as much as a frequency one.
Measured from our own pulls:

- **Prices** — daily (the pulled files start 2015-01-02; we use the horizon).
- **Trends** — **weekly** (7-day buckets), 2021-08-01 onward. Google's
  granularity depends on window length: >5y returns monthly, 5y returns
  weekly, <9 months returns daily.
- **Alpha Vantage news** — event-level timestamps, but a default pull returned
  only **50 articles spanning 1–2 days per ticker**, because the endpoint
  returns the *most recent* N articles.

**Does Alpha Vantage offer aggregated news?** No — there is no pre-aggregated
daily-sentiment endpoint. `NEWS_SENTIMENT` is article-level only; you aggregate
to daily yourself. You *can* build history with its `time_from`/`time_to`
parameters (coverage starts ~2022, `limit` up to 1000), but that costs roughly
one request per ticker per month — for 88 names over our 5-year horizon that is
**5,280 requests ≈ 211 days** against a ~25 requests/day free tier. Not feasible
without a premium key; see [#8](https://github.com/Rickymtl/mmf1927h-workshop/issues/8).

**So GDELT is our primary news source.** Its DOC 2.0 API returns a
*pre-aggregated daily timeline* — no key, no meaningful quota, back to 2017:

- `timelinetone` → daily average tone of matching coverage (**sentiment**)
- `timelinevolraw` → daily count of matching articles (**attention**)

That volume series is a bonus second signal: news-based attention, which
complements and cross-checks the search-based Trends attention signal.

### Our alignment decision

**Model at weekly frequency, Friday-to-Friday.** Trends is the binding
constraint at weekly, and the only honest options are to model weekly or to
upsample Trends — and **forward-filling a weekly series to daily fabricates
information**, which would leak into every later evaluation stage. So:

| Series | Native | Aligned to weekly by |
|--------|--------|----------------------|
| Prices | daily | compounding to weekly returns |
| Trends | weekly | already weekly (rescale by batch anchor first) |
| GDELT tone | daily | mean over the week |
| GDELT volume | daily | sum over the week |
| AV article sentiment | event | relevance-weighted mean per week (recent only) |

Aggregate using **only information available up to each Friday close**, then
predict the *following* week's return — no lookahead. Alpha Vantage stays a
recent-window cross-check on the GDELT tone signal rather than a history source.

> If daily modelling turns out to matter, the alternative is stitching multiple
> overlapping <9-month Trends windows (which return daily granularity) and
> rescaling them on their overlaps. That is a real technique but meaningfully
> more sourcing work — weekly first.

## Setup

```bash
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# Parser, chunking, throttle, and output-validation tests:
./.venv/bin/python -m unittest discover -s tests -v
```

**API key (Alpha Vantage, free):** get one at
<https://www.alphavantage.co/support/#api-key>, then:

```bash
cp .env.example .env      # then edit .env and paste your key
```

`.env` is **gitignored** — the key never enters version control. The news
script reads it from the environment via `python-dotenv`.

## Pulling raw data

```bash
# Everything, full 88-name universe:
./.venv/bin/python code/pull_data.py

# One source at a time:
./.venv/bin/python code/pull_prices.py                 # all 88 tickers
./.venv/bin/python code/pull_trends.py  --tickers AAPL MSFT NVDA
./.venv/bin/python code/pull_gdelt.py   --tickers AAPL MSFT JPM
./.venv/bin/python code/pull_news.py    --tickers AAPL MSFT JPM

# Check whether GDELT is reachable from your network before a long run:
./.venv/bin/python code/pull_gdelt.py --probe

# Validate the completed 88-ticker GDELT pull:
./.venv/bin/python code/validate_gdelt.py

# Quick smoke test (first 8 tickers, all sources):
./.venv/bin/python code/pull_data.py --sample 8
```

Raw output lands under `data/raw/{prices,trends,gdelt,news}/`, each with a
`provenance.json` recording exactly what was pulled and when. The `data/`
folder is **not tracked by git at all** — raw pulls are regenerable, can be
large, and may be non-redistributable, so they stay local. The scripts create
the folders they need at runtime.

### Google Trends: batching and the anchor keyword

Trends normalises its 0–100 index *within each request*, so series pulled in
different batches are **not comparable as-is**. `pull_trends.py` reserves one
of the 5 keyword slots for a shared **anchor** (default `"stock market"`) and
saves that anchor series per batch as `_anchor_batch<N>.csv`. Rescaling each
ticker by its batch anchor puts all 88 names on one comparable scale — do this
in Session 2 before building features ([#3](https://github.com/Rickymtl/mmf1927h-workshop/issues/3)).

```bash
# Tune batching if Google pushes back:
./.venv/bin/python code/pull_trends.py --sleep 15 --retries 5
./.venv/bin/python code/pull_trends.py --anchor ''      # disable anchoring
```

The pull **resumes by default** — already-downloaded tickers are skipped, so an
interrupted run can just be re-run. Use `--no-resume` to force a full re-download
(e.g., if you change the study horizon and need all files to share the new window).

### Rate limits & gotchas

- **Google Trends** rate-limits `pytrends` hard (HTTP 429). The script retries
  with exponential backoff and a fresh client per attempt, which clears most
  soft blocks; persistent 429s usually mean the IP is flagged (a residential
  connection or a longer `--sleep` helps).
- **GDELT** asks for **≤1 request every 5 seconds** and returns HTTP 429 with a
  plain-text body when exceeded. The puller enforces six-second pacing,
  exponential retry, and at least a 60-second cooldown after an explicit
  throttle response. Some shared/datacenter IPs are still blocked regardless
  of pacing — run `--probe` first and use a residential connection for the
  multi-hour full pull.
  GDELT queries are disambiguated per ticker (`"Apple Inc"`, not `Apple`) plus a
  finance-term filter; see `gdelt_query()` in [`code/universe.py`](code/universe.py).
- **Alpha Vantage** free tier ≈ 25 requests/day — pull a small ticker sample
  at a time.

## What is / isn't committed

- **Committed:** code, tests, `requirements.txt`, `.env.example`, this README.
- **Never committed:** `.env` (your API key), everything under `data/`,
  the course PDFs, and the `.venv/`.
