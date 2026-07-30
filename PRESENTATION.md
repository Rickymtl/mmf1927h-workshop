# Day 5 Presentation Plan — 15 minutes

**Group members:** ⟨FILL: all names — must match REPORT.md and the repo⟩
**Repo:** <https://github.com/Rickymtl/mmf1927h-workshop>

Budget: **3 + 5 + 4 + 3 = 15 min**. Guardrail, not a stopwatch — but land on 15.
If you run long, cut narration, not results.

> All numbers final — 88/88 Trends re-pulled one request per ticker.

---

## Segment 1 — Source & Clean (3 min)

Brief. Do **not** re-derive the pipeline.

**Slide 1 — Title**
Trend-Driven Names: Google Trends Anomalies in the Equity Cross-Section.
All group member names. Repo URL visible.

**Slide 2 — Thesis in one line**
`r = α + β′F + ε`. Abnormal search attention predicts next-week cross-sectional
returns. Universe: 8 largest per GICS sector = 88 names. Horizon: 5y fixed,
2021-08-01 → 2026-07-27.

**Slide 3 — Sourcing, and one scope change**
Prices (yfinance) + Trends (pytrends). News sentiment **descoped Day 4**: Alpha
Vantage needed ~5,280 requests ≈ 211 days on the free tier; GDELT verified but
never completed a full pull. Chose a disclosed gap over a mostly-empty column.

**Slide 4 — ⭐ The anchor bug (this is your best slide)**
Before/after table. We anchored every Trends batch on `"stock market"`; it peaks
at 100 in every request and has ~50× the volume of a typical company name, so
quantisation crushed the rest to zero.

- 7 tickers perfectly constant, 32 with ≤3 distinct values, 33% tied at zero weekly
- We had documented this as *"MNAR — zeros are real signal."* **Wrong.**
- Fix: one ticker per request. MPC 1 → 59 distinct values; PG 2 → 29; TMUS 2 → 50.
- AAPL/GOOGL/AMZN unchanged — they were already the batch max, exactly as the
  mechanism predicts. That's why we believe the explanation, not just the result.

> **Land this line:** *the test that settled it was procedural, not statistical —
> re-measure the same quantity with the instrument changed.*

**Slide 5 — Panel**
Friday-to-Friday weekly (Trends is the binding constraint; forward-filling it to
daily fabricates information). Returns from `Adj Close`, verified on three splits.
Per-date winsorization p1/p99, percentile-rank standardization, 52-week minimum
history.

---

## Segment 2 — Feature & Model Decisions (5 min)

The longest segment — this is where 20% of the grade lives.

**Slide 6 — Feature table**
All 9 features, each tagged internal/external and mapped to a risk-model bucket.

**Slide 7 — Paper-derived feature: ASVI**
Da, Engelberg & Gao (2011), *JF* 66(5).
`ASVI_t = log SVI_t − log median(SVI_{t−1..t−8})`.
Say **why the median**: robust to one-off spikes, so it measures *sustained*
attention. Reproduced construction, not just cited.

**Slide 8 — Why every Trends feature is within-ticker**
Cross-ticker levels were never comparable — keywords differ in ambiguity
("Apple" catches the fruit). Within-ticker transforms cancel the per-ticker
scale constant exactly, so no anchor is needed at all. Anomaly first, then
cross-sectional rank.

**Slide 9 — Two models, and why both**
Elastic Net (coefficients = β′F, readable) vs LightGBM (nonlinearity). The
comparison is the diagnostic, not a horse race.

**Slide 10 — Validation**
Expanding-window walk-forward, **purged + embargoed**. Say why k-fold is wrong
here: it shuffles time and leaks on an autocorrelated panel.

---

## Segment 3 — Results & Interpretation (4 min)

**Slide 11 — Signal quality (nested CV)**
LightGBM **IC 0.0313, IC-IR 0.253, t = 2.56**, positive IC in 64.7% of weeks —
now ahead of Elastic Net (0.0446 / 0.186 / 1.88). On the *degraded* data
LightGBM was the weaker model (t = 0.86); cleaning the Trends data more than
doubled its IC. GBM > linear = genuine nonlinear structure.

**Slide 12 — Portfolio, gross vs net**
Dollar- and sector-neutral, 5% cap. Elastic Net **0.84 gross → 0.33 net**;
costs consume ~60%. Lead with the net number.

**Slide 13 — ⭐ The central tension: best signal, worst portfolio**
LightGBM has the **highest IC (t = 2.56)** and the **worst book (net Sharpe
−5.0)**. At **105% weekly turnover** it flips entirely every week, so costs
turn +0.38 gross into −5.0 net. A signal you cannot hold is worth nothing —
the binding constraint is turnover, not predictive power.

**Slide 14 — Effective breadth is 10.5, not 88**
Mean pairwise correlation 0.25 → participation ratio ~10.5 independent bets
(12% of headcount). IR ≈ IC·√BR gives **0.98**, not the naive **2.85**.

**Slide 15 — ⭐ Significance: we do not clear the bar**
LightGBM IC t = 2.56 clears 2.0 — but **Deflated Sharpe fails at 95%**.
Nested CV performs **342 model fits**, which raises E[max Sharpe | noise] to
~0.30. Searching harder made the result look better *and* raised the bar;
net, it still does not reject the null.

> **Say it out loud:** *this is a weak, cost-sensitive signal that does not yet
> reject the null.* Claiming alpha here is exactly what Q&A will dismantle.

**Slide 16 — ε diagnostics**
DW 2.21, Ljung-Box p 0.25 → nothing left on the table. But Breusch-Pagan and
Jarque-Bera both reject: heteroskedastic, skew −1.45, kurtosis 8.9. Sharpe
language understates tail risk.

**Slide 17 — Disclosed limitations**
Survivorship bias (mid-2025 snapshot), keyword ambiguity, short-side frictions
not modelled, no turnover control, crowding. Disclosed limitations aren't
penalised; undisclosed ones are.

---

## Segment 4 — Q&A (3 min)

### Rehearse these

**"Why one ticker per request instead of an anchor?"**
Cross-ticker levels were never comparable — keyword ambiguity differs. Our
features are within-ticker anomalies, so the scale constant cancels exactly.
The anchor bought nothing and cost 57% of the universe.

**"Your IC isn't significant. So what have you got?"**
A correctly-built pipeline, an honest null result, and a diagnosed instrument
bug that most groups using Trends will have shipped silently. We'd rather report
t = 1.84 than a deflated Sharpe we can't defend.

**"How do you know it isn't leakage?"**
Purged + embargoed walk-forward; every rolling stat `.shift(1)`-ed; panel sorted
before any groupby-rolling; `center=True` and `.shift(-1)` appear nowhere but the
target. Residual diagnostics show no serial structure.

**"Why does LightGBM win on IC but lose on the portfolio?"**
It finds real nonlinear structure — IC 0.031 vs 0.045 for Elastic Net but a
much better IC-IR (0.253 vs 0.186) and t = 2.56. Its predictions are just not
*stable* week to week, so at 105% turnover costs erase everything. Signal
quality and tradeability are different problems; we measured both.

**"Isn't your α just the low-volatility anomaly?"**
`rvol_13` is still the largest Elastic Net coefficient — concede that openly.
But under nested CV **all four Trends features are retained** with nonzero
weight, and `asvi` takes the positive sign Da et al. report. The stronger
evidence is LightGBM: cleaning the Trends data alone moved its IC 0.015 →
0.031 and t 0.86 → 2.56, with the code and universe unchanged. That
improvement can only have come from the Trends block.

**"What breaks if a key assumption is wrong?"**
Survivorship bias is the big one — a current-membership universe already knows
who survived, so returns are biased up. We disclose rather than correct it.

**"What would you do with one more week?"**
Turnover-aware construction first — the cost analysis says that is where the
return is, not in more signal. Then ensemble the two models, a point-in-time
universe, and daily Trends via stitched <9-month windows.

---

## Pre-flight checklist

- [x] All numbers re-run on the complete 88/88 dataset
- [ ] **All group member names** on slides, repo, and report — consistently
- [ ] Repo URL shared with the instructor (not just local)
- [ ] `REPORT.md` finalised and committed
- [ ] Static PDF export of slides on the machine as a backup
- [ ] Environment pre-loaded — no live installs during the slot
- [ ] Screen-share / HDMI tested before the block starts
- [ ] Rehearsed once against a clock — 3 + 5 + 4 + 3

## Rubric coverage

| Rubric line | Weight | Where |
|---|---|---|
| Technical rigor & pipeline completeness | 25% | Slides 3–5, 10 |
| Modeling decisions & justification | 20% | Slides 6–9 |
| Quality of results & interpretation | 15% | Slides 11–16 |
| Presentation clarity & Q&A | 15% | Segment 4 |
| Creativity | 10% | Slide 4 (anchor diagnosis), 14 (effective breadth), 15 (DSR) |
