# Presentation Script — Trend-Driven Names

**MMF1927H · Day 5 · 15 minutes (12–13 speaking + Q&A)**

> 22 slides. Aaron carries the two follow-up analyses (sector, keyword
> ambiguity) — if you are running long, **slide 16 is the one to cut**; the
> keyword finding is stronger and more memorable.

| # | Speaker | Slides | Time | Owns |
|---|---------|--------|------|------|
| 1 | **Ricky Mao** | 1–3 | 2:00 | Thesis & sourcing |
| 2 | **Saier Ma** | 4–5 | 2:30 | The anchor bug & the panel |
| 3 | **Tim Yuan** | 6–9 | 2:30 | Features, ASVI, validation design |
| 4 | **Nick Sun** | 10–13 | 2:45 | Results, turnover, the strategy |
| 5 | **Aaron Hou** | 14–22 | 3:00 | Honest reading, follow-ups & close |
| — | all | — | 3:00 | Q&A |

**How to use this.** The prose is what to say, not what to read aloud
word-for-word — deliver it in your own voice. **Bold** marks the sentence in
each block you must not lose. Handoffs are scripted so nobody stalls.

Advance slides with → or click. Timings are cumulative from zero.

---

## 1 · RICKY MAO — Thesis & sourcing (0:00 – 2:00)

### [SLIDE 1 — Title] 0:00

> Good evening. We're group — Ricky, Saier, Tim, Nick and Aaron — and our
> project is **Trend-Driven Names**: can Google Trends search attention predict
> the cross-section of equity returns.
>
> Short answer up front, so you know where we're going: **we found a real but
> weak signal, we found and fixed a serious bug in our own data, and we do not
> claim alpha.** The honest result is a null.

### [SLIDE 2 — Thesis] 0:25

> The whole week hangs off `r = α + β′F + ε`.
>
> **F** is two blocks: search-attention anomalies — our differentiating signal —
> plus price controls, momentum, reversal, realised and idiosyncratic
> volatility. **α** is what's left after we make the book dollar- and
> sector-neutral, so we're not just being paid for a sector call. And **ε** we
> actually interrogate at the end rather than assume it's noise.
>
> Universe is the **eight largest names per GICS sector — 88 names across 11
> sectors**. Horizon is five years, fixed dates, and weekly Friday-to-Friday.
>
> **The economic story is attention: retail search precedes retail order flow.**

### [SLIDE 3 — Sourcing & scope change] 1:05

> Prices from Yahoo, Trends from pytrends — both complete, 88 out of 88.
>
> We originally planned a second signal, news sentiment, and **we dropped it on
> Thursday.** Alpha Vantage has no aggregate endpoint, so building history costs
> about one request per ticker-month — **5,280 requests, roughly 211 days on the
> free tier.** GDELT worked on a probe but never completed a full pull from the
> networks we had.
>
> **We'd rather present a disclosed gap than a column that's mostly empty.**
> That's a sourcing decision we'll defend, not an omission.

> **HANDOFF →** "Saier is going to tell you about the mistake we made in the
> data we *did* collect."

---

## 2 · SAIER MA — The anchor bug & the panel (2:00 – 4:30)

> ⭐ **This is the strongest material in the deck. Slow down. Take the full time.**

### [SLIDE 4 — The anchor destroyed our own signal] 2:00

> Google Trends doesn't give you absolute search volume. It gives a 0–100 index
> **normalised within each request**. Pull five keywords together and they're
> scaled relative to whichever is biggest.
>
> We knew that, and we thought we'd solved it: we put a shared anchor keyword —
> `"stock market"` — in every batch, so batches would be comparable.
>
> **That anchor peaks at 100 in every single request, and it has roughly fifty
> times the search volume of a typical company name.** So after integer
> rounding, the actual companies got crushed toward zero.
>
> *(point at the table)* Marathon Petroleum: **one distinct value across 261
> weeks — a flat line of zeros.** Welltower, the same. T-Mobile, the same.
> Seven tickers were perfectly constant. A third of our cross-section was tied
> at zero every single week.
>
> And here's the part we're least proud of and most want to show you: **we
> wrote this up in our Day 2 data-quality memo as "MNAR — genuinely low search
> interest, the zeros are real signal."** We had a story for it. The story was
> wrong.
>
> **The test that settled it wasn't statistical, it was procedural: re-measure
> the same quantity with the instrument changed.** We re-pulled one ticker per
> request, so each series is normalised to its own peak. Marathon Petroleum
> went from 1 distinct value to **59**. Median across the universe went from
> **6 to 45**. Constant columns, **seven to zero**.
>
> The detail that convinced us it's the right explanation rather than a lucky
> fix: **Apple, Google and Amazon didn't change at all** — they were already the
> biggest keyword in their own batch, so they had nothing to lose. That's
> exactly what the mechanism predicts.

### [SLIDE 5 — The panel] 3:50

> Briefly, the panel itself. Weekly, Friday-to-Friday — **Trends is weekly and
> it's the binding constraint, so forward-filling it to daily would fabricate
> information we never had.**
>
> Returns from adjusted close, verified against three known splits — NVIDIA
> ten-for-one, Amazon and Google twenty-for-one — no artificial jumps.
> Winsorized per date at the 1st and 99th percentile, percentile-ranked,
> 52-week minimum history before a name enters.
>
> 22,855 ticker-weeks.

> **HANDOFF →** "Tim will take you through what we built on top of it."

---

## 3 · TIM YUAN — Features, ASVI, validation (4:30 – 7:00)

### [SLIDE 6 — Feature set] 4:30

> Nine features. Four from Trends — highlighted — and five price-based controls.
> Every one is tagged internal or external and mapped to a risk-model bucket.
>
> **The controls are there deliberately: if search interest only "works"
> because it proxies for volatility or momentum, we want that visible in the
> coefficients rather than hidden.**

### [SLIDE 7 — ASVI, the paper feature] 5:00

> Our paper-derived feature is **ASVI**, from Da, Engelberg and Gao, *In Search
> of Attention*, Journal of Finance 2011 — the canonical Google-Trends-in-
> finance paper.
>
> It's log search volume minus the log **median** of the previous eight weeks.
>
> **The median is the part that matters, and it's the authors' own choice.** A
> mean baseline would be dragged around by a single viral week. The median is
> robust to spikes, so ASVI measures *sustained* abnormal attention. We
> reproduced the construction from the methodology, not the abstract — our only
> change is `log1p` so zero weeks stay finite.
>
> One nice confirmation: **on our clean data ASVI takes the positive sign Da et
> al. report. On the partially-degraded data it came out negative.** The sign
> was tracking our data quality, not economics.

### [SLIDE 8 — Why no anchor is needed] 5:50

> Back to the anchor for one moment, because the fix has a design consequence.
>
> Without an anchor, levels aren't comparable across tickers. **Our answer is
> that they never were** — keywords differ in ambiguity. "Apple" catches the
> fruit. "Welltower" catches only the REIT. Comparing raw levels across those
> two is meaningless however you normalise.
>
> **Every Trends feature we build is a within-ticker anomaly, and any
> within-ticker transform cancels the per-ticker scale constant exactly.** So
> we compute the anomaly first, then rank cross-sectionally. Order matters.

### [SLIDE 9 — Models & validation] 6:20

> Two models. Elastic Net because its coefficients *are* β′F — you can read the
> exposures straight off. LightGBM for nonlinearity. **The comparison is the
> diagnostic, not a horse race.**
>
> Validation: expanding-window walk-forward, **purged and embargoed**. Standard
> k-fold shuffles time and leaks badly on an autocorrelated panel.
>
> And **nested cross-validation** — the inner loop picks hyperparameters using
> training data only, the outer loop reports. Tuning on the split you report is
> a second, separate leak. That cost us 342 model fits, and Aaron will come back
> to why that number matters.

> **HANDOFF →** "Nick has the results."

---

## 4 · NICK SUN — Results, turnover, strategy (7:00 – 9:45)

### [SLIDE 10 — Signal quality] 7:00

> Out-of-sample, 102 weeks, nested CV.
>
> **LightGBM: rank IC 0.031, IC-IR 0.253, t-statistic 2.56, positive IC in
> nearly 65% of weeks.** Elastic Net has a higher raw IC but a worse IC-IR and
> t of 1.88.
>
> Here's the number I'd point at. **On the degraded Trends data, LightGBM was
> our worst model — IC 0.015, t of 0.86. Cleaning the data alone took it to
> 0.031 and t of 2.56. Same code, same universe, same horizon.** That
> improvement can only have come from the Trends block.
>
> And under nested CV, Elastic Net retains **all four** Trends features. Under
> the hand-set penalty we started with, it retained **none** — that penalty was
> quietly regularising our entire thesis out of the model.

### [SLIDE 11 — Best signal, worst portfolio] 7:55

> Then we built portfolios, and got a shock.
>
> **LightGBM has the best signal in the study and by far the worst book.**
> Gross Sharpe 1.30 — net Sharpe **minus 5.17**.
>
> The reason is turnover: **110% a week.** The entire book flips every week.
> The predictions are individually informative but not *stable*, so we were
> paying to chase rank changes that were estimation noise, not new information.
>
> **A signal you can't hold is worth nothing. Our binding constraint was never
> predictive power — it was turnover.**

### [SLIDE 12 — Fixing turnover] 8:40

> So we attacked the cause. **We smooth the prediction over the trailing four
> weeks before ranking** — averaging out the churn while keeping the signal.
>
> Turnover halves, 35.6% to 17.1%. Gross Sharpe drops slightly, 1.07 to 0.94.
> **Net Sharpe goes from 0.26 to 0.65, and net return from 3.1% to 7.7% a year.**
>
> We also tried weight blending, similar result, and a no-trade band, which
> barely helped — **and that's informative: banding treats the symptom,
> smoothing treats the cause.**
>
> **And this isn't a tuned artifact — net Sharpe stays positive between 0.45 and
> 0.65 for every smoothing window from two weeks to twelve.** The specific
> choice of four is optimised; the finding isn't.

### [SLIDE 13 — Backtest] 9:20

> 102 out-of-sample weeks, August 2024 to July 2026. Green is smoothed and net
> of costs, grey dashed is the baseline net, blue is gross.
>
> **The gap between green and grey is the entire contribution of the turnover
> work** — same signal, same model, just held differently. Drawdown below,
> trough at −14.9%.
>
> Dollar- and sector-neutral, 5% name cap, costs are 5 basis points linear plus
> Almgren square-root impact on each name's own average daily volume.

> **HANDOFF →** "Aaron will tell you why we're still not claiming this is alpha."

---

## 5 · AARON HOU — Honest reading & close (9:45 – 12:00)

### [SLIDE 14 — Breadth] 9:45

> Before the headline number, one correction to how it should be read.
>
> The Fundamental Law says IR is roughly IC times root breadth — but **breadth
> counts *independent* bets, not names.** Our 88 names have a mean pairwise
> correlation of 0.25. The participation ratio of that correlation matrix gives
> **10.5 effectively independent bets — about 12% of headcount.**
>
> **Using 88 would imply an IR of 2.85. Using 10.5 gives 0.98.** We report the
> second one.

### [SLIDE 15 — Significance] 10:20

> And the number we most want to be straight about.
>
> Our t-statistic of 2.56 clears the conventional bar. **The Deflated Sharpe
> Ratio does not — it's 0.12, and it needs to be above 0.95.**
>
> The reason is the 342 model fits Tim mentioned. **Under that much searching,
> the expected maximum Sharpe from pure noise alone is about 0.30 — not zero.**
> That's the bar. We don't clear it.
>
> **Searching harder made our result look better and raised the threshold it had
> to beat. Net of both, we do not reject the null.** We'd rather report that
> than a Sharpe ratio we can't defend.

### [SLIDE 16 — Sector analysis] 10:55

> Two follow-ups we were asked about. First: **does it work in particular
> sectors?**
>
> We ranked within each sector separately. Materials looks best at t of 1.82 —
> **and no sector reaches t of 2, and none survives false-discovery control.**
>
> **With eleven simultaneous tests, a p of 0.07 is about what the null gives you
> anyway.** We ran Benjamini-Hochberg specifically so we couldn't talk ourselves
> into the best-looking one. And at eight names per sector, the correlation is a
> very weak statistic to begin with.

### [SLIDE 17 — Keyword ambiguity] 11:20

> Second: **do ambiguous keywords add noise?**
>
> We predicted homonyms — "Apple" the fruit, "Amazon" the river. **That
> prediction was wrong, p of 0.30.**
>
> What actually drives it is **shopping intent.** Walmart, Costco, McDonald's,
> Home Depot — people search those to shop, not to invest, and that traffic
> swamps the attention signal. Consumer sectors average a correlation of 0.04
> with their own trading volume; everything else averages 0.34. **t of −4.03,
> p of 0.0008.**
>
> AbbVie, Broadcom, Nucor — B2B names with no consumer channel — are the
> cleanest at 0.6 and above.
>
> **We've re-pulled the 16 contaminated names as "name plus stock" to force
> investor intent.**

### [SLIDE 18 — Did the fix work?] 11:40

> Yes — on the axis we designed it for. **All sixteen improved. Mean coupling
> went from minus 0.095 to plus 0.59, paired t of 17.6.** They now couple more
> tightly than the names that were never contaminated.
>
> **And it made no difference to the model.** IC 0.031 to 0.031, net Sharpe
> 0.65 to 0.60 — within noise, and LightGBM's t-stat actually ticked down.
>
> **We're presenting the disambiguated version anyway, because it's justified
> in advance rather than because it scored better — it didn't.** Picking the
> dataset after seeing both results is exactly the selection bias we spend the
> rest of this deck warning about.
>
> The lesson we'll take: **cleaner data on one axis doesn't automatically mean
> a better model, and we'd have assumed it would.**

### [SLIDE 19 — Residual diagnostics] 11:55

> Quickly on ε. Durbin-Watson 2.21, Ljung-Box p of 0.25 — **no autocorrelation
> left, so nothing obvious we failed to model.**
>
> But Breusch-Pagan and Jarque-Bera both reject hard: heteroskedastic, skew
> −1.45, kurtosis 8.9. **Fat tails mean our Sharpe and drawdown language
> understates tail risk — our standard errors should be read as optimistic.**

### [SLIDE 20–21 — Limitations, two slides] 12:10

> Two of these we'd rather you heard from us than found yourselves.
>
> **First — we have a look-ahead.** Google Trends weekly buckets run Sunday to
> Saturday, and we map each bucket to the Friday *inside* it. So week *t*'s
> search value contains Saturday — one day out of seven that wasn't knowable at
> that Friday's close, and it falls inside the window we're predicting. Our
> rolling baselines are all lagged, but the current-week level isn't, so it
> reaches ASVI directly. Direction is plausibly favourable: Friday-night news
> lifts both weekend search and Monday's open. **The fix is one line — align the
> bucket to the Friday after it's fully observable — and it invalidates every
> number on these slides. We found it too late to re-run and re-rehearse, so we
> disclosed it instead. It's item one on what we'd do next.**
>
> **Second — our sector labels aren't point-in-time.** Visa and Mastercard moved
> from Information Technology to Financials in March 2023. We label them
> Financials for all sixty months, so the sector-neutrality constraint and two
> rows of the sector-IC table are wrong for about a third of the sample.
>
> Then the ones you'd expect: survivorship bias — our universe is a
> current-membership snapshot, which biases returns up. Beta-neutrality isn't
> applied, so that's two of the three Day 4 constraints. The macro and PCA
> risk-model buckets are empty. Short-side borrow and recall aren't modelled and
> we haven't stated a capacity number. The smoothing window was chosen over five
> candidates. And the signal is built from entirely free public data, so
> **assume it's at least partially crowded.**
>
> Keyword ambiguity is the one item on this list we *did* close — Saier will
> have covered that.

### [SLIDE 22 — Close] 12:20

> With another week: fix the Trends bucket alignment first — it's the only open
> item that could change whether the result is real. Then meta-labelling for the
> turnover problem — a *learned* sizing layer rather than the three heuristics
> we have now. Then a point-in-time universe **and** sector membership, an
> ensemble of the two models, and daily Trends via stitched windows.
>
> **What we'd defend tonight: a sourcing bug we found by testing our own
> assumption instead of trusting it, a cost analysis that says turnover — not
> predictive power — is the binding constraint, and a result we're reporting as
> a null. What we wouldn't claim is that the pipeline is point-in-time correct
> end to end. It isn't. We found one look-ahead late and put it on the
> limitations slide rather than hope nobody asked.**
>
> Thank you — happy to take questions.

---

## Q&A — who takes what (12:00 – 15:00)

Answer in **one or two sentences**, then stop. Don't fill silence.

| Question type | Lead | Backup |
|---|---|---|
| Data sourcing, the anchor, Trends mechanics | **Saier** | Ricky |
| Why drop news / Alpha Vantage / GDELT | **Ricky** | Saier |
| Feature construction, ASVI, the paper | **Tim** | Nick |
| Leakage, CV design, nested CV | **Tim** | Nick |
| IC, model comparison, why LightGBM | **Nick** | Aaron |
| Portfolio, turnover, costs, backtest | **Nick** | Aaron |
| Significance, DSR, breadth, limitations | **Aaron** | Tim |
| Anything about scope or team decisions | **Ricky** | — |

### Rehearsed answers

**"Isn't this just the low-volatility anomaly?"** *(Nick)*
> `rvol_13` is our largest Elastic Net coefficient — we'll concede that openly.
> But under nested CV all four Trends features are retained, and the stronger
> evidence is LightGBM: cleaning the Trends data alone moved it from t = 0.86 to
> t = 2.56 with nothing else changed. That can only have come from Trends.

**"Your DSR fails. So what have you actually got?"** *(Aaron)*
> A correctly-built pipeline, an honest null, and a diagnosed instrument bug
> that we suspect most Trends projects ship silently. We think reporting t = 2.56
> alongside a DSR of 0.12 is more useful than reporting only the first.

**"How do you know there's no leakage?"** *(Tim)*
> Purged and embargoed walk-forward, every rolling statistic shifted by one,
> panel sorted before any groupby-rolling, and `center=True` and `shift(-1)`
> appear nowhere except constructing the target. The residual diagnostics show
> no serial structure, which is consistent with that.

**"Why one request per ticker instead of a better anchor?"** *(Saier)*
> Any anchor costs resolution for the smaller names. And we don't need one —
> cross-ticker levels were never comparable because keyword ambiguity differs,
> and all our features are within-ticker anomalies where the scale factor
> cancels exactly.

**"Why smooth the signal rather than optimise turnover directly?"** *(Nick)*
> Time. Turnover inside the objective is the right answer and it's first on our
> list for another week. Smoothing was the cheapest thing that attacks the cause
> rather than the symptom, and it doubled net Sharpe.

**"What breaks if a key assumption is wrong?"** *(Aaron)*
> Survivorship bias is the big one. Our universe already knows who survived to
> 2025, so returns are biased upward. We disclose it rather than correct it —
> a point-in-time membership file was out of scope this week.

**If you genuinely don't know:**
> "We didn't test that — it's a fair gap." Then stop. Do not speculate.

---

## Pre-flight

- [ ] Each speaker has run through their own section once, aloud, on a clock
- [ ] One full run-through together — target 12:00, hard stop 12:30
- [ ] `slides.html` open and tested on the presenting laptop
- [ ] PDF export saved locally as backup (`Cmd+P` → Save as PDF)
- [ ] Repo URL shared with the instructor
- [ ] Decide who drives the clicker (suggest Ricky — opens and closes)
