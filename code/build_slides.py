"""Generate the self-contained Day 5 slide deck.

Reads the backtest equity curves produced by ``code/strategy.py`` and renders
them as inline SVG, so the deck needs no network and no external assets.

    ./code/run_pipeline.sh && python code/model_nested.py \
        && python code/strategy.py && python code/build_slides.py
"""
import pathlib

import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
STRAT = REPO / "data" / "processed" / "strategy"
OUT = REPO / "slides.html"


def _svg_path(vals, w=760, h=200, lo=None, hi=None):
    lo = min(vals) if lo is None else lo
    hi = max(vals) if hi is None else hi
    rng = (hi - lo) or 1
    n = len(vals)
    return "M" + " L".join(
        f"{i / (n - 1) * w:.1f},{h - (v - lo) / rng * h:.1f}" for i, v in enumerate(vals))


def _chart_paths():
    sm = pd.read_parquet(STRAT / "equity_elasticnet_signal_smooth.parquet")
    base = pd.read_parquet(STRAT / "equity_elasticnet_baseline.parquet")
    allv = (list(sm.net_equity) + list(base.net_equity) + list(sm.gross_equity))
    lo, hi = min(allv) * 0.995, max(allv) * 1.005
    dd = list(sm.net_drawdown * 100)
    return {
        "smooth_net": _svg_path(list(sm.net_equity), lo=lo, hi=hi),
        "base_net": _svg_path(list(base.net_equity), lo=lo, hi=hi),
        "smooth_gross": _svg_path(list(sm.gross_equity), lo=lo, hi=hi),
        "dd": _svg_path(dd, h=110, lo=min(dd) * 1.05, hi=0),
        "lo": lo, "hi": hi,
        "first": str(sm.index.min().date()), "last": str(sm.index.max().date()),
    }


P = _chart_paths()

SLIDES = []


def slide(kind, title, kicker, body):
    SLIDES.append(f'<section class="slide {kind}"><div class="inner">'
                  f'{f"<p class=kicker>{kicker}</p>" if kicker else ""}'
                  f'{f"<h2>{title}</h2>" if title else ""}{body}</div></section>')


# 1 title
slide("title", "", "", """
<p class="course">MMF1927H · Workshop in Mathematical Finance</p>
<h1>Trend-Driven Names</h1>
<p class="sub">Google Trends attention anomalies in the equity cross-section</p>
<p class="names">Ricky Mao · Saier Ma · Tim Yuan · Nick Sun · Aaron Hou</p>
<p class="repo">github.com/Rickymtl/mmf1927h-workshop</p>
<p class="foot">Instructor: Shawn Unger · 31 July 2026</p>""")

# 2 thesis
slide("", "The thesis", "SEGMENT 1 · SOURCE &amp; CLEAN", """
<div class="eq">r = α + β′F + ε</div>
<div class="cols3">
<div class="card"><h3>F</h3><p>Search-attention anomalies (the differentiating
signal) plus price controls — momentum, reversal, realised and idiosyncratic
volatility.</p></div>
<div class="card"><h3>α</h3><p>What remains after the book is made dollar- and
sector-neutral, so return isn't a sector call in disguise.</p></div>
<div class="card"><h3>ε</h3><p>Interrogated with classical diagnostics, not
assumed to be noise.</p></div>
</div>
<div class="strip"><b>Universe</b> 8 largest per GICS sector = 88 names
&nbsp;·&nbsp; <b>Horizon</b> 5y fixed, 2021-08-01 → 2026-07-27
&nbsp;·&nbsp; <b>Frequency</b> weekly, Friday-to-Friday</div>""")

# 3 sourcing
slide("", "Sourcing — and one scope change", "SEGMENT 1", """
<table class="t">
<tr><th>Source</th><th>Signal</th><th>Freq</th><th>Status</th></tr>
<tr><td>Yahoo Finance</td><td>OHLCV</td><td>daily</td><td class="ok">88/88</td></tr>
<tr><td>Google Trends</td><td>search interest</td><td>weekly</td><td class="ok">88/88</td></tr>
<tr class="dim"><td>Alpha Vantage</td><td>news sentiment</td><td>event</td><td class="no">descoped</td></tr>
<tr class="dim"><td>GDELT</td><td>news tone</td><td>daily</td><td class="no">descoped</td></tr>
</table>
<div class="note"><b>Why we dropped news.</b> Alpha Vantage has no aggregate
endpoint — building history costs ~1 request per ticker-month = <b>5,280
requests ≈ 211 days</b> on the free tier. GDELT verified on a probe but never
completed a full pull. We chose a <b>disclosed gap over a mostly-empty
column</b>.</div>""")

# 4 the bug
slide("hero", "The anchor destroyed our own signal", "SEGMENT 1 · THE FINDING", """
<p class="lead">Trends normalises 0–100 <i>within each request</i>. We anchored
every batch on <code>"stock market"</code> — which peaks at 100 every time and
has ~50× the volume of a typical company name. Quantisation crushed the rest
to zero.</p>
<div class="split">
<table class="t compact">
<tr><th>Ticker</th><th>Anchored</th><th>One per request</th></tr>
<tr><td>MPC</td><td class="no">1 distinct, 100% zeros</td><td class="ok">59 distinct, 0%</td></tr>
<tr><td>WELL</td><td class="no">1 distinct, 100% zeros</td><td class="ok">47 distinct, 0%</td></tr>
<tr><td>TMUS</td><td class="no">2 distinct, 100% zeros</td><td class="ok">50 distinct, 0%</td></tr>
<tr><td>PG</td><td class="no">2 distinct, 99.6% zeros</td><td class="ok">29 distinct, 0%</td></tr>
<tr><td>META</td><td class="no">6 distinct</td><td class="ok">74 distinct</td></tr>
</table>
<div class="stats">
<div class="stat"><span class="big">7 → 0</span><span>constant columns</span></div>
<div class="stat"><span class="big">6 → 45</span><span>median distinct values</span></div>
<div class="stat"><span class="big">31 → 0</span><span>tickers &gt;20% zeros</span></div>
</div></div>
<div class="callout"><b>We had documented these zeros as "MNAR — zeros are real
signal." That was wrong.</b> They were an instrument artifact. AAPL/GOOGL/AMZN
are unchanged — they were already the batch max, exactly as the mechanism
predicts. <i>The test that settled it was procedural, not statistical:
re-measure the same quantity with the instrument changed.</i></div>""")

# 5 panel
slide("", "The analysis-ready panel", "SEGMENT 1", """
<div class="flow"><span>Raw</span><i>→</i><span>Validate</span><i>→</i><span>Align</span><i>→</i><span>Impute / Winsorize</span><i>→</i><span class="on">Analysis-ready</span></div>
<div class="cols2">
<ul class="tick">
<li><b>Weekly, Friday-to-Friday.</b> Trends is the binding constraint —
forward-filling it to daily would fabricate information.</li>
<li><b>Returns from Adj Close</b>, verified on NVDA 10-for-1, AMZN and GOOGL
20-for-1 — no artificial jumps.</li>
<li><b>Winsorized</b> per-date cross-sectionally at p1/p99 — capped, never
trimmed.</li>
</ul>
<ul class="tick">
<li><b>Percentile-rank</b> standardisation per date, matching Rank-IC
evaluation.</li>
<li><b>52-week minimum history</b> before a name enters.</li>
<li><b>CEG</b> (2022 spin-off) enters on first valid date, never backfilled.</li>
</ul></div>
<div class="strip">22,855 ticker-weeks · 88 tickers · 260 weeks</div>""")

# 6 features
slide("", "Feature set", "SEGMENT 2 · FEATURE &amp; MODEL", """
<table class="t">
<tr><th>Feature</th><th>Category</th><th>Construction</th></tr>
<tr class="hl"><td>asvi</td><td>External · macro-analog</td><td>log SVI − log median(SVI, prior 8w) &nbsp;<b>← paper</b></td></tr>
<tr class="hl"><td>trends_z_26</td><td>External · macro-analog</td><td>z-score of log SVI vs own trailing 26w</td></tr>
<tr class="hl"><td>trends_chg_4</td><td>External · macro-analog</td><td>log change in SVI over 4w</td></tr>
<tr class="hl"><td>trends_vol_13</td><td>External · statistical</td><td>std dev of ΔlogSVI, trailing 13w</td></tr>
<tr><td>mom_52_4</td><td>Internal · fundamental</td><td>cumulative return t−52 → t−4</td></tr>
<tr><td>mom_12_1</td><td>Internal · fundamental</td><td>cumulative return t−12 → t−1</td></tr>
<tr><td>rvol_13</td><td>Internal · statistical</td><td>std dev of weekly returns, 13w</td></tr>
<tr><td>ivol_26</td><td>Internal · statistical</td><td>std dev of market-model residuals, 26w</td></tr>
<tr><td>rev_1</td><td>Internal · fundamental</td><td>prior week return (reversal control)</td></tr>
</table>""")

# 7 ASVI
slide("", "Paper-derived feature — ASVI", "SEGMENT 2", """
<p class="cite">Da, Engelberg &amp; Gao (2011), “In Search of Attention,”
<i>Journal of Finance</i> 66(5), 1461–1499</p>
<div class="eq small">ASVI<sub>t</sub> = log(SVI<sub>t</sub>) − log[ median(SVI<sub>t−1</sub> … SVI<sub>t−8</sub>) ]</div>
<div class="cols2">
<div class="card"><h3>Why the median</h3><p>The authors' own choice, and it is
load-bearing: robust to one-off spikes, so ASVI measures <b>sustained</b>
abnormal attention rather than a single noisy week.</p></div>
<div class="card"><h3>What we changed</h3><p>Only <code>log1p</code>, so
zero-interest weeks stay finite. Construction reproduced from the methodology,
not the abstract.</p></div>
</div>
<div class="callout ok-c">On clean data <code>asvi</code> carries the
<b>positive</b> sign Da et al. report. On the partially-degraded data it was
negative — the sign tracked data quality, not economics.</div>""")

# 8 within-ticker
slide("", "Why no anchor is needed at all", "SEGMENT 2", """
<div class="cols2">
<div class="card"><h3>Levels were never comparable</h3><p>Keywords differ in
ambiguity — “Apple” catches the fruit, “Welltower” catches only the REIT.
Comparing raw search levels across tickers is meaningless however you
normalise.</p></div>
<div class="card"><h3>Scale cancels exactly</h3><p>Google returns
100·v(t)/M<sub>batch</sub>. Every Trends feature is a within-ticker anomaly,
and any within-ticker transform — z-score, log-change — cancels
100/M<sub>batch</sub> algebraically.</p></div>
</div>
<div class="flow"><span>within-ticker anomaly</span><i>→</i><span>cross-sectional rank</span><i>→</i><span class="on">model input</span></div>
<div class="note">So the anchor bought nothing and cost <b>57% of the
universe</b>. Order matters: anomaly first, ranking second.</div>""")

# 9 models + validation
slide("", "Two models, and validation that doesn't leak", "SEGMENT 2", """
<div class="cols2">
<div class="card"><h3>Elastic Net</h3><p>Coefficients map directly onto β′F —
a readable estimate of factor exposures.</p></div>
<div class="card"><h3>LightGBM</h3><p>Captures nonlinearity and interactions a
linear model cannot. The comparison is the diagnostic, not a horse race.</p></div>
</div>
<div class="cols3">
<div class="card sm"><h3>Walk-forward</h3><p>Expanding window: train on past,
test on future. k-fold shuffles time and leaks on an autocorrelated panel.</p></div>
<div class="card sm"><h3>Purge + embargo</h3><p>Drop the training tail whose
label window overlaps the test block; skip a week after each test block.</p></div>
<div class="card sm"><h3>Nested CV</h3><p>Inner loop selects hyperparameters on
training data only; outer loop reports. Tuning on the reporting split is a
second leak.</p></div>
</div>
<div class="strip">6 outer × 3 inner folds · 102 out-of-sample weeks · 342 total model fits</div>""")

# 10 signal quality
slide("", "Signal quality", "SEGMENT 3 · RESULTS", """
<table class="t big-t">
<tr><th>Metric</th><th>Elastic Net</th><th>LightGBM</th></tr>
<tr><td>Mean Rank IC</td><td>0.0446</td><td class="ok">0.0313</td></tr>
<tr><td>IC-IR</td><td>0.186</td><td class="ok">0.253</td></tr>
<tr class="hl"><td>IC t-stat</td><td>1.88</td><td class="ok"><b>2.56</b></td></tr>
<tr><td>Weeks with positive IC</td><td>53.9%</td><td class="ok">64.7%</td></tr>
</table>
<div class="callout ok-c"><b>Cleaning the Trends data alone moved LightGBM from
IC 0.015 / t = 0.86 to IC 0.031 / t = 2.56</b> — same code, same universe, same
horizon. That improvement can only have come from the Trends block. GBM &gt;
linear indicates genuine nonlinear structure.</div>
<div class="note">Elastic Net retains <b>all four</b> Trends features under
nested CV (α ≈ 1e-4). Under a hand-set α = 1e-3 it retained <b>none</b> — that
penalty was regularising the thesis out of the model.</div>""")

# 11 the tension
slide("hero", "Best signal, worst portfolio", "SEGMENT 3 · THE CENTRAL TENSION", """
<div class="split">
<table class="t compact">
<tr><th></th><th>Elastic Net</th><th>LightGBM</th></tr>
<tr><td>Gross Sharpe</td><td>1.07</td><td>1.30</td></tr>
<tr><td>Weekly turnover</td><td>35.6%</td><td class="no">109.9%</td></tr>
<tr class="hl"><td>Net Sharpe</td><td>0.26</td><td class="no"><b>−5.17</b></td></tr>
<tr><td>Cost drag p.a.</td><td>−</td><td class="no">44%</td></tr>
</table>
<div class="stats">
<div class="stat"><span class="big no">110%</span><span>weekly turnover — the book flips every week</span></div>
<div class="stat"><span class="big">1.30 → −5.17</span><span>gross to net Sharpe</span></div>
</div></div>
<div class="callout"><b>LightGBM has the best signal in the study and the worst
book.</b> Unstable predictions chase rank changes that are estimation noise,
not new information. <i>A signal you cannot hold is worth nothing — the binding
constraint is turnover, not predictive power.</i></div>""")

# 12 the fix
slide("hero", "Fixing turnover, not the signal", "SEGMENT 3 · STRATEGY", """
<p class="lead">Smooth the prediction over the trailing 4 weeks <b>before</b>
ranking — attack the cause (rank churn from estimation noise) rather than the
symptom.</p>
<table class="t">
<tr><th>Construction</th><th>Turnover</th><th>Gross SR</th><th>Net SR</th><th>Net p.a.</th><th>Max DD</th></tr>
<tr><td>baseline (full rebalance)</td><td>35.6%</td><td>1.072</td><td>0.257</td><td>3.09%</td><td>−12.9%</td></tr>
<tr class="hl"><td><b>signal smoothing (k=4)</b></td><td class="ok"><b>17.1%</b></td><td>0.941</td><td class="ok"><b>0.645</b></td><td class="ok"><b>7.71%</b></td><td>−14.9%</td></tr>
<tr><td>weight blending (λ=0.4)</td><td>16.2%</td><td>0.859</td><td>0.590</td><td>7.25%</td><td>−14.6%</td></tr>
<tr><td>no-trade band</td><td>33.1%</td><td>1.072</td><td>0.288</td><td>3.49%</td><td>−12.8%</td></tr>
</table>
<div class="callout ok-c"><b>Net Sharpe 0.26 → 0.65, turnover halved.</b> And
the finding is not a tuned artifact: net Sharpe stays positive at
<b>0.45–0.65 for every smoothing window from k=2 to k=12</b>. The no-trade band
barely helps — banding treats the symptom, smoothing treats the cause.</div>""")

# 13 equity curve
slide("", "Backtest — 102 out-of-sample weeks", "SEGMENT 3 · BACKTEST", f"""
<div class="chart">
<svg viewBox="0 0 760 200" preserveAspectRatio="none" class="eq-svg">
  <line x1="0" y1="{200 - (1.0-P['lo'])/(P['hi']-P['lo'])*200:.1f}" x2="760"
        y2="{200 - (1.0-P['lo'])/(P['hi']-P['lo'])*200:.1f}" class="axis"/>
  <path d="{P['smooth_gross']}" class="l-gross"/>
  <path d="{P['base_net']}" class="l-base"/>
  <path d="{P['smooth_net']}" class="l-net"/>
</svg>
<div class="legend"><span class="k net"></span>smoothed, net of cost
<span class="k base"></span>baseline, net <span class="k gross"></span>smoothed, gross</div>
<div class="axis-lbl"><span>{P['first']}</span><span>{P['last']}</span></div>
</div>
<div class="chart dd">
<svg viewBox="0 0 760 110" preserveAspectRatio="none" class="eq-svg">
  <path d="{P['dd']}" class="l-dd"/>
</svg>
<div class="axis-lbl"><span>drawdown, net</span><span>trough −14.9%</span></div>
</div>
<div class="strip">Dollar- and sector-neutral · 5% single-name cap · 2.0 gross ·
costs = 5bp linear + Almgren square-root impact on each name's own ADV · $10M notional</div>""")

# 14 breadth
slide("", "Breadth is 10.5, not 88", "SEGMENT 3", """
<div class="split">
<div class="stats wide">
<div class="stat"><span class="big">0.25</span><span>mean pairwise return correlation</span></div>
<div class="stat"><span class="big">10.5</span><span>effectively independent bets<br>(participation ratio)</span></div>
<div class="stat"><span class="big">11.9%</span><span>of headcount</span></div>
</div>
<div class="card"><h3>IR ≈ IC · √BR</h3>
<p class="mono">using N = 88 &nbsp;→&nbsp; IR = <b>2.85</b><br>
using N<sub>eff</sub> = 10.5 &nbsp;→&nbsp; IR = <b>0.98</b></p>
<p>Breadth counts <b>independent</b> bets. 88 large-caps across 11 sectors are
heavily correlated, so quoting √88 overstates the achievable IR by ~3×.</p></div>
</div>
<div class="note">This is why we report the effective number alongside any
backtested IR — it is the difference between a defensible claim and an
arithmetic error.</div>""")

# 15 significance
slide("hero", "We do not clear the significance bar", "SEGMENT 3 · HONEST READING", """
<div class="split">
<div class="stats wide">
<div class="stat"><span class="big">2.56</span><span>LightGBM IC t-stat — clears 2.0</span></div>
<div class="stat"><span class="big no">0.12</span><span>Deflated Sharpe — needs &gt;0.95</span></div>
<div class="stat"><span class="big">342</span><span>model fits searched</span></div>
</div>
<div class="card"><h3>Why DSR fails</h3><p>Under 342 configurations, the
<b>expected maximum Sharpe from pure noise is ~0.30</b> — not zero. Our
realised Sharpe does not clear that bar with confidence.</p>
<p>Searching harder made the result look better <i>and</i> raised the
threshold. Net, it still does not reject the null.</p></div>
</div>
<div class="callout"><b>Our claim:</b> a real but weak, cost-sensitive signal
that survives a correctly-built pipeline — <b>not alpha</b>. We would rather
report an honest null than a Sharpe we cannot defend.</div>""")

# 15b sector analysis
slide("", "Does it work in particular sectors?", "SEGMENT 3 · FOLLOW-UP", """
<p class="lead">We ranked within each sector separately, to see whether a
sector-specific strategy was hiding inside a weak aggregate.</p>
<div class="split">
<table class="t compact">
<tr><th>Sector</th><th>Mean IC</th><th>t</th><th>p</th></tr>
<tr><td>Materials</td><td>0.072</td><td>1.82</td><td>0.071</td></tr>
<tr><td>Consumer Discretionary</td><td>0.051</td><td>1.40</td><td>0.164</td></tr>
<tr><td>Consumer Staples</td><td>0.049</td><td>1.29</td><td>0.199</td></tr>
<tr class="dim"><td>… five more between</td><td>0.03 / 0.02</td><td>&lt;1</td><td>ns</td></tr>
<tr><td>Energy</td><td class="no">−0.025</td><td>−0.65</td><td>0.518</td></tr>
<tr><td>Information Technology</td><td class="no">−0.025</td><td>−0.68</td><td>0.498</td></tr>
</table>
<div class="stats">
<div class="stat"><span class="big no">0 of 11</span><span>sectors reach |t| &gt; 2</span></div>
<div class="stat"><span class="big no">0 of 11</span><span>survive Benjamini-Hochberg at q = 0.10</span></div>
<div class="stat"><span class="big">N = 8</span><span>names per sector per week — Spearman is very weak here</span></div>
</div></div>
<div class="callout"><b>No sector-specific strategy is supported.</b> Materials
looks best, but across eleven simultaneous tests a p of 0.071 is about what the
null produces on its own — and the <i>maximum</i> t across eleven tests is
upward-biased by construction. <b>We applied FDR control precisely so we
couldn't cherry-pick it.</b></div>""")

# 15c keyword ambiguity
slide("hero", "Our own hypothesis was wrong", "SEGMENT 3 · FOLLOW-UP", """
<p class="lead">Do ambiguous keywords add noise? We measured it:
<code>corr(Δlog search, Δlog dollar volume)</code> — a keyword that tracks the
<i>firm</i> should co-move with trading in it.</p>
<div class="split">
<table class="t compact">
<tr><th>Weakest</th><th>corr</th><th>Strongest</th><th>corr</th></tr>
<tr><td>Walmart</td><td class="no">−0.336</td><td>AbbVie</td><td class="ok">0.656</td></tr>
<tr><td>Costco</td><td class="no">−0.316</td><td>Broadcom</td><td class="ok">0.620</td></tr>
<tr><td>McDonald&rsquo;s</td><td class="no">−0.308</td><td>Nvidia</td><td class="ok">0.595</td></tr>
<tr><td>Home Depot</td><td class="no">−0.222</td><td>Nucor</td><td class="ok">0.593</td></tr>
<tr><td>Starbucks</td><td class="no">−0.159</td><td>NextEra</td><td class="ok">0.580</td></tr>
</table>
<div class="stats">
<div class="stat"><span class="big">0.043</span><span>mean corr — Consumer sectors</span></div>
<div class="stat"><span class="big">0.340</span><span>mean corr — all others</span></div>
<div class="stat"><span class="big ok">p = 0.0008</span><span>t = −4.03</span></div>
</div></div>
<div class="callout"><b>We predicted homonyms — “Apple” the fruit, “Amazon” the
river. That prior failed (p = 0.30).</b> The real channel is
<b>shopping intent</b>: people search “Walmart” to shop, not to invest, and
that traffic swamps the attention signal. B2B and industrial names have no
consumer-search channel, so their search <i>is</i> investor attention.
<b>Fix: 16 contaminated names re-pulled as “&lt;name&gt; stock”.</b></div>""")

# 16 residuals
slide("", "ε under interrogation", "SEGMENT 3", """
<table class="t">
<tr><th>Test</th><th>Result</th><th>Reading</th></tr>
<tr><td>Durbin-Watson</td><td>2.21</td><td class="ok">no first-order autocorrelation</td></tr>
<tr><td>Ljung-Box (lag 1)</td><td>p = 0.25</td><td class="ok">no serial structure left on the table</td></tr>
<tr><td>Breusch-Pagan</td><td>p &lt; 0.001</td><td class="no">heteroskedastic</td></tr>
<tr><td>Jarque-Bera</td><td>p &lt; 0.001, skew −1.45, kurt 8.9</td><td class="no">fat-tailed, left-skewed</td></tr>
</table>
<div class="cols2">
<div class="card"><h3>What passed</h3><p>No momentum or mean-reversion left in
the residual — nothing obvious we failed to model at this frequency.</p></div>
<div class="card"><h3>What failed, and why it matters</h3><p>Fat tails and
heteroskedasticity mean <b>Sharpe- and drawdown-based language understates tail
risk</b>. Our standard errors should be read as optimistic.</p></div>
</div>""")

# 17 limitations
slide("", "Disclosed limitations", "SEGMENT 3", """
<table class="t">
<tr><th>Limitation</th><th>Direction</th><th>Status</th></tr>
<tr><td><b>Survivorship bias</b> — mid-2025 membership snapshot</td><td>overstates returns</td><td>disclosed, not corrected</td></tr>
<tr><td><b>Not statistically significant</b> — DSR 0.12</td><td>—</td><td>stated plainly</td></tr>
<tr><td><b>Keyword ambiguity</b> — “Apple”, “Amazon”, “Visa”</td><td>adds noise</td><td>unquantified</td></tr>
<tr><td><b>Short-side frictions</b> — borrow &amp; recall not modelled</td><td>overstates net</td><td>disclosed</td></tr>
<tr><td><b>Smoothing window k=4</b> searched over 5 values</td><td>mild optimism</td><td>full curve reported</td></tr>
<tr><td><b>Crowding</b> — built entirely from free public data</td><td>partially crowded</td><td>acknowledged</td></tr>
</table>
<div class="note">Disclosed limitations are not penalised; undisclosed ones
are. Every number above is reproducible from the repo:
<code>./code/run_pipeline.sh</code></div>""")

# 18 close
slide("close", "What we'd do with one more week", "", """
<ol class="big-list">
<li><b>Turnover in the objective</b>, not as a post-hoc filter — the cost
analysis says that is where the return is.</li>
<li><b>Ensemble</b> Elastic Net and LightGBM — complementary blind spots,
uncorrelated errors.</li>
<li><b>Point-in-time universe</b> to remove survivorship bias rather than
disclose it.</li>
<li><b>Daily Trends</b> via stitched &lt;9-month windows — 7× the observations.</li>
</ol>
<div class="callout ok-c"><b>What we'd defend:</b> a pipeline that is
point-in-time correct end to end, a sourcing bug we found by testing our own
assumption rather than trusting it, and a result we report honestly as a null.</div>
<p class="thanks">Thank you — questions?</p>""")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;color:#e6edf3}
.slide{width:100vw;height:100vh;display:none;padding:3.2vh 4vw;position:relative}
.slide.on{display:flex;align-items:center}
.inner{width:100%;max-width:1180px;margin:0 auto}
h1{font-size:clamp(38px,5.6vw,76px);font-weight:800;letter-spacing:-.02em;line-height:1.03;margin:.12em 0}
h2{font-size:clamp(24px,3.1vw,42px);font-weight:750;letter-spacing:-.018em;margin-bottom:.5em;line-height:1.1}
h3{font-size:15px;font-weight:700;color:#f0b72f;margin-bottom:.45em;letter-spacing:.01em}
p{font-size:clamp(14px,1.25vw,18px)}
.kicker{font-size:11px;font-weight:800;letter-spacing:.16em;color:#7d8590;margin-bottom:1.1em;text-transform:uppercase}
.course{font-size:12px;letter-spacing:.15em;color:#f0b72f;font-weight:700;text-transform:uppercase}
.sub{font-size:clamp(16px,1.9vw,25px);color:#adbac7;margin-top:.5em;font-weight:400}
.names{margin-top:2.2em;font-size:17px;font-weight:600;color:#e6edf3}
.repo{margin-top:.35em;font-size:14px;color:#6ea8fe;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.foot{margin-top:1.6em;font-size:12px;color:#7d8590}
.slide.title .inner{border-left:4px solid #f0b72f;padding-left:2.2vw}
.eq{font-family:Georgia,"Times New Roman",serif;font-size:clamp(30px,4.4vw,56px);text-align:center;margin:.35em 0 .7em;color:#fff;letter-spacing:.01em}
.eq.small{font-size:clamp(18px,2.4vw,30px)}
.lead{font-size:clamp(15px,1.5vw,20px);color:#adbac7;margin-bottom:1.1em;max-width:62em}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:.9em 0}
.cols3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:.9em 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:9px;padding:16px 18px}
.card.sm p{font-size:13.5px;color:#adbac7}
.card p{color:#adbac7;font-size:14.5px}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:15px!important;color:#e6edf3!important;margin-bottom:.7em}
table.t{width:100%;border-collapse:collapse;margin:.5em 0;font-size:clamp(12px,1.12vw,15.5px)}
table.t th{text-align:left;padding:8px 11px;border-bottom:2px solid #30363d;color:#7d8590;font-size:11px;letter-spacing:.09em;text-transform:uppercase;font-weight:700}
table.t td{padding:8px 11px;border-bottom:1px solid #21262d}
table.t.compact td,table.t.compact th{padding:6px 9px;font-size:13.5px}
table.t.big-t td{padding:11px;font-size:17px}
table.t tr.hl td{background:#1c2128;font-weight:650}
table.t tr.dim td{color:#6e7681}
.ok{color:#3fb950;font-weight:650}
.no{color:#f85149;font-weight:650}
.split{display:grid;grid-template-columns:1.35fr 1fr;gap:22px;align-items:center;margin:.5em 0}
.stats{display:flex;flex-direction:column;gap:13px}
.stats.wide{gap:18px}
.stat{display:flex;flex-direction:column;background:#161b22;border:1px solid #30363d;border-radius:9px;padding:12px 15px}
.stat .big{font-size:clamp(22px,2.9vw,38px);font-weight:800;letter-spacing:-.02em;line-height:1.05}
.stat span:last-child{font-size:12px;color:#7d8590;margin-top:3px;line-height:1.35}
.callout{margin-top:1em;background:#1c2128;border-left:3px solid #f0b72f;border-radius:0 8px 8px 0;padding:13px 17px;font-size:clamp(13px,1.2vw,16px);color:#e6edf3}
.callout.ok-c{border-left-color:#3fb950}
.note{margin-top:.9em;font-size:13.5px;color:#adbac7;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 15px}
.strip{margin-top:1em;padding:9px 15px;background:#161b22;border-radius:7px;font-size:12.5px;color:#adbac7;text-align:center;border:1px solid #21262d}
.flow{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:.9em 0;font-size:13px}
.flow span{background:#161b22;border:1px solid #30363d;padding:8px 14px;border-radius:7px;color:#adbac7}
.flow span.on{background:#f0b72f;color:#0d1117;border-color:#f0b72f;font-weight:700}
.flow i{color:#484f58;font-style:normal}
ul.tick{list-style:none}
ul.tick li{padding:6px 0 6px 20px;position:relative;font-size:14.5px;color:#adbac7;line-height:1.45}
ul.tick li:before{content:"▸";position:absolute;left:0;color:#f0b72f}
ul.tick li b{color:#e6edf3}
ol.big-list{margin-left:1.1em}
ol.big-list li{font-size:clamp(14px,1.35vw,18px);padding:7px 0;color:#adbac7}
ol.big-list li b{color:#e6edf3}
.cite{font-size:13px;color:#7d8590;font-style:italic;margin-bottom:.3em}
code{font-family:ui-monospace,Menlo,monospace;background:#21262d;padding:1px 5px;border-radius:4px;font-size:.9em}
.chart{margin:.3em 0}
.eq-svg{width:100%;height:clamp(120px,20vh,200px);display:block;background:#0f141b;border:1px solid #21262d;border-radius:7px}
.chart.dd .eq-svg{height:clamp(66px,11vh,110px)}
.eq-svg path{fill:none;vector-effect:non-scaling-stroke}
.l-net{stroke:#3fb950;stroke-width:2.4}
.l-base{stroke:#7d8590;stroke-width:1.5;stroke-dasharray:5 4}
.l-gross{stroke:#6ea8fe;stroke-width:1.4;opacity:.62}
.l-dd{stroke:#f85149;stroke-width:1.7}
.axis{stroke:#30363d;stroke-width:1;stroke-dasharray:3 3}
.legend{display:flex;gap:16px;align-items:center;font-size:11.5px;color:#7d8590;margin-top:6px;flex-wrap:wrap}
.k{width:15px;height:2.5px;display:inline-block;margin-right:5px;vertical-align:middle}
.k.net{background:#3fb950}.k.base{background:#7d8590}.k.gross{background:#6ea8fe}
.axis-lbl{display:flex;justify-content:space-between;font-size:11px;color:#6e7681;margin-top:3px}
.slide.hero .inner{border-left:4px solid #f0b72f;padding-left:2vw}
.slide.close .inner{border-left:4px solid #3fb950;padding-left:2vw}
.thanks{margin-top:1.3em;font-size:clamp(17px,2vw,26px);font-weight:700;color:#f0b72f}
#nav{position:fixed;bottom:14px;right:18px;font-size:12px;color:#6e7681;font-family:ui-monospace,Menlo,monospace;z-index:9}
#bar{position:fixed;top:0;left:0;height:2.5px;background:#f0b72f;transition:width .18s;z-index:9}
@media print{.slide{display:flex!important;page-break-after:always;height:100vh}#nav,#bar{display:none}}
"""

JS = """
const s=[...document.querySelectorAll('.slide')];let i=0;
const nav=document.getElementById('nav'),bar=document.getElementById('bar');
function go(n){i=Math.max(0,Math.min(s.length-1,n));
 s.forEach((el,k)=>el.classList.toggle('on',k===i));
 nav.textContent=(i+1)+' / '+s.length;
 bar.style.width=((i+1)/s.length*100)+'%';}
document.addEventListener('keydown',e=>{
 if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();go(i+1)}
 if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){e.preventDefault();go(i-1)}
 if(e.key==='Home')go(0); if(e.key==='End')go(s.length-1);});
document.addEventListener('click',e=>{if(!e.target.closest('a'))go(i+1)});
go(0);
"""

html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trend-Driven Names — MMF1927H</title>
<style>{CSS}</style></head><body>
<div id="bar"></div>{''.join(SLIDES)}<div id="nav"></div>
<script>{JS}</script></body></html>"""

OUT.write_text(html)
print(f"wrote {OUT} — {len(SLIDES)} slides, {len(html)//1024} KB")
