# Q&A Helper — Trend-Driven Names

**MMF1927H · Day 5** · Ricky Mao, Saier Ma, Tim Yuan, Nick Sun, Aaron Hou

Print this. Keep it face-up during Q&A.

---

## The three rules

1. **Answer in one or two sentences, then stop.** Silence is the questioner's
   problem, not yours. Rambling is where marks are lost.
2. **Concede fast when the point is fair.** "That's a fair hit" costs nothing
   and buys credibility for the next answer.
3. **Never speculate.** If you didn't test it: *"We didn't test that — it's a
   fair gap."* Full stop.

## Who takes what

| Topic | Lead | Backup |
|---|---|---|
| Sourcing, the anchor bug, Trends mechanics | **Saier** | Ricky |
| Dropping news / Alpha Vantage / GDELT | **Ricky** | Saier |
| Features, ASVI, the paper | **Tim** | Nick |
| Leakage, CV design, nested CV | **Tim** | Nick |
| IC, model choice, why LightGBM | **Nick** | Aaron |
| Portfolio, turnover, costs, backtest | **Nick** | Aaron |
| Significance, DSR, breadth | **Aaron** | Tim |
| Sector analysis, keyword ambiguity | **Aaron** | Saier |
| Scope, team, what we'd do next | **Ricky** | — |

---

## Numbers you must have cold

| | |
|---|---|
| Universe / horizon | 88 names, 11 sectors · 2021-08-01 → 2026-07-27 · weekly |
| Panel | 22,855 ticker-weeks · 102 OOS weeks |
| Anchor bug | 7 constant columns → 0 · median distinct 6 → 45 |
| Best IC | LightGBM **0.031**, IC-IR 0.253, **t = 2.17** (nested CV) |
| Elastic Net | IC 0.045, t = 1.95 |
| Strategy | net Sharpe **0.60**, net **7.4%** p.a., turnover 19% |
| Baseline (no smoothing) | net Sharpe **0.00** — costs eat everything |
| LightGBM book | turnover **104%**/wk → net Sharpe **−3.9** |
| Breadth | 10.5 independent bets, not 88 → IR **0.98**, not 2.85 |
| Significance | **DSR ≈ 0.1, fails at 95%** · 342 model fits |
| Keyword coupling | contaminated −0.095 → **+0.592** after fix (16/16) |

---

## Likely questions

### On the result

**"Is this alpha?"**
> No. Our Deflated Sharpe is about 0.1 against a 0.95 bar — we don't reject the
> null. It's a real but weak, cost-sensitive signal.

**"Your t-stat is 2.17. Why isn't that significant?"**
> Because we ran 342 model fits. Under that much searching the expected maximum
> Sharpe from pure noise is ~0.30, not zero. That's the bar DSR measures against,
> and we don't clear it.

**"So what did you actually achieve?"**
> A pipeline that's point-in-time correct end to end, a sourcing bug we found by
> testing our own assumption, and a result we're reporting honestly as a null.
> We'd rather that than a Sharpe we can't defend.

**"Isn't your signal just the low-volatility anomaly?"** *(Nick)*
> `rvol_13` is our largest Elastic Net coefficient — fair hit. But under nested
> CV all four Trends features are retained, and cleaning the Trends data alone
> moved LightGBM from t = 0.86 to t = 2.5 with nothing else changed. That can
> only have come from the Trends block.

### On the data

**"Why one request per ticker instead of a better anchor?"** *(Saier)*
> Any anchor costs resolution for the smaller names. And we don't need one:
> cross-ticker levels were never comparable because keyword ambiguity differs,
> and all our features are within-ticker anomalies where the scale cancels.

**"How do you know the anchor was the cause and not something else?"** *(Saier)*
> Apple, Google and Amazon were unchanged by the re-pull — they were already the
> largest keyword in their batch, so they had nothing to lose. That's exactly
> what the mechanism predicts, and it's why we believe it rather than just
> observing an improvement.

**"You said the zeros were MNAR. Why should we trust your other diagnoses?"**
> Fair. We got that one wrong and we're showing it rather than hiding it. What
> changed our mind was re-measuring with the instrument changed — and that's the
> check we'd apply to the others.

**"Why drop news sentiment?"** *(Ricky)*
> Alpha Vantage would have taken ~5,280 requests, about 211 days on the free
> tier. GDELT verified on a probe but never completed a full pull. We chose a
> disclosed gap over a mostly-empty column.

### On method

**"How do you know there's no leakage?"** *(Tim)*
> Purged and embargoed walk-forward, every rolling statistic shifted by one, the
> panel sorted before any groupby-rolling, and `center=True` and `shift(-1)`
> appear nowhere except constructing the target. Residual diagnostics show no
> serial structure, which is consistent.

**"Why nested CV rather than just cross-validating once?"** *(Tim)*
> Tuning on the same split you report is a second leak. Our first run used a
> hand-set penalty that zeroed every Trends coefficient — nested CV picked a
> penalty ten times smaller and retained all four. The hyperparameter was
> silently deciding our conclusion.

**"Why is your target weekly and not daily?"** *(Tim)*
> Trends is weekly and it's the binding constraint. Forward-filling it to daily
> would fabricate information we never had.

**"Why Rank IC rather than R²?"**
> Only relative ordering drives a long-short book. Out-of-sample R² in finance
> is near zero or negative and would tell us little.

### On the portfolio

**"Why does LightGBM win on IC but lose on the portfolio?"** *(Nick)*
> It finds real nonlinear structure but its predictions aren't stable week to
> week. At 104% turnover we'd be paying to chase rank changes that are
> estimation noise. Signal quality and tradeability are different problems.

**"Isn't smoothing just curve-fitting the turnover parameter?"** *(Nick)*
> The specific window is optimised, yes. But net Sharpe stays positive between
> 0.45 and 0.65 for every window from 2 to 12 weeks — the finding doesn't depend
> on the choice, only the exact number does.

**"Are your cost assumptions realistic?"** *(Nick)*
> 5bp linear plus Almgren square-root impact on each name's own ADV, at $10M
> notional on large caps. If anything that's conservative for this universe —
> but we don't model borrow cost or recall on the short side, which we disclose.

**"What's your capacity?"**
> We didn't compute it formally — fair gap. Directionally it's high: large-cap
> universe, weekly rebalance, median ADV around $700M.

### On the follow-ups

**"Materials had the highest sector IC — isn't that worth trading?"** *(Aaron)*
> No. With eleven simultaneous tests a p of 0.07 is about what the null gives
> you, and no sector survives false-discovery control. We ran Benjamini-Hochberg
> specifically so we couldn't talk ourselves into it.

**"You fixed the keywords and nothing improved. Doesn't that undermine the
finding?"** *(Aaron)*
> It undermines the assumption that cleaner data means a better model — which we
> held going in. The contamination was real and measurable: coupling went from
> −0.10 to +0.59, all sixteen improved. It just didn't carry predictive content
> we weren't already getting.

**"Then why present the disambiguated version?"** *(Aaron)*
> Because it's justified in advance on measurement grounds. Picking the dataset
> after seeing which scored better is exactly the selection bias we criticise
> elsewhere in the deck.

### On limitations

**"What breaks if a key assumption is wrong?"** *(Aaron)*
> Survivorship bias is the big one. Our universe already knows who survived to
> 2025, so returns are biased upward. We disclose it rather than correct it — a
> point-in-time membership file was out of scope this week.

**"Is your signal crowded?"**
> Almost certainly partially. It's built entirely from free public data, so we
> assume no edge from the data itself — any edge would be in combination or
> timing.

**"What would you do with one more week?"** *(Ricky)*
> Turnover inside the objective rather than as a post-hoc filter — the cost
> analysis says that's where the return is. Then ensemble the two models, a
> point-in-time universe, and daily Trends via stitched windows.

---

## Traps — do not say these

| Don't say | Say instead |
|---|---|
| "We found alpha" | "A weak signal that doesn't reject the null" |
| "Our Sharpe is 1.08" *(that's gross)* | "Net Sharpe 0.60 — gross was 0.93" |
| "IR could be 2.85" | "Effective breadth is 10.5, so IR ≈ 0.98" |
| "The model works" | "IC is positive; significance doesn't survive correction" |
| "Trends predicts returns" | "Trends features are retained and contribute" |
| Guessing at a number | "I don't have that figure to hand" |

**If a question lands on someone else's section**, say *"[Name] ran that"* and
hand over. Don't answer from memory on someone else's numbers.
