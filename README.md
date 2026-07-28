# MMF1927H — Workshop in Mathematical Finance

## Project: Alternative-Data Signals for Cross-Sectional Equity Returns

**Combining Topic 1 (Google Trends anomalies) + Topic 5 (news sentiment).**

We predict the cross-section of next-period equity returns using two
*orthogonal alternative-data signals* layered on top of standard price data:

1. **Search-interest anomalies** — abnormal Google Trends search volume for a
   company name (retail attention shocks that often lead short-horizon returns).
2. **News-headline sentiment** — Alpha Vantage's ticker-level news sentiment
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

> **Documented limitation (survivorship bias):** the universe is a *current-
> membership* snapshot as of mid-2025, not point-in-time index constituents.
> We surface this rather than hide it — a Day 2 (cleaning / point-in-time)
> concern to address before drawing return conclusions.

### The four-stage pipeline

| Stage | Owning day | This repo |
|-------|-----------|-----------|
| **Source** | Day 1 | `code/pull_*.py` — raw prices, trends, news |
| Clean | Day 2 | _tbd_ |
| Feature / Model | Day 3 | _tbd_ |
| Evaluate | Day 4–5 | _tbd_ |

## Data sources

| Source | Signal | Native frequency | Coverage | Auth | Script |
|--------|--------|------------------|----------|------|--------|
| Yahoo Finance (`yfinance`) | OHLCV prices | **daily** | 2015– | none | [`code/pull_prices.py`](code/pull_prices.py) |
| Google Trends (`pytrends`) | search interest | **weekly** | 5y window | none | [`code/pull_trends.py`](code/pull_trends.py) |
| GDELT DOC 2.0 | news tone + volume | **daily** | 2017– | none | [`code/pull_gdelt.py`](code/pull_gdelt.py) |
| Alpha Vantage `NEWS_SENTIMENT` | article sentiment | **event-level** | ~1–2 days/pull | **API key** | [`code/pull_news.py`](code/pull_news.py) |

## The frequency mismatch (and how we handle it)

The mismatch is **real**, and it is a depth problem as much as a frequency one.
Measured from our own pulls:

- **Prices** — daily, 2,906 rows from 2015-01-02.
- **Trends** — **weekly** (7-day buckets), 2021-07-25 onward. Google's
  granularity depends on window length: >5y returns monthly, 5y returns
  weekly, <9 months returns daily.
- **Alpha Vantage news** — event-level timestamps, but a default pull returned
  only **50 articles spanning 1–2 days per ticker**, because the endpoint
  returns the *most recent* N articles.

**Does Alpha Vantage offer aggregated news?** No — there is no pre-aggregated
daily-sentiment endpoint. `NEWS_SENTIMENT` is article-level only; you aggregate
to daily yourself. You *can* build history with its `time_from`/`time_to`
parameters (coverage starts ~2022, `limit` up to 1000), but that costs roughly
one request per ticker per month — for 88 names over 5 years that is ~1,000+
requests against a **~25 requests/day** free tier. Not feasible in a five-day
workshop.

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

# Quick smoke test (first 8 tickers, all sources):
./.venv/bin/python code/pull_data.py --sample 8
```

Raw output lands under `data/raw/{prices,trends,news}/`, each with a
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
in Session 2 before building features.

```bash
# Tune batching if Google pushes back:
./.venv/bin/python code/pull_trends.py --sleep 15 --retries 5
./.venv/bin/python code/pull_trends.py --anchor ''      # disable anchoring
```

The pull **resumes by default** — already-downloaded tickers are skipped, so an
interrupted run can just be re-run. Use `--no-resume` to force a re-download
(do this if you change `--timeframe`, so all files share one timeframe).

### Rate limits & gotchas

- **Google Trends** rate-limits `pytrends` hard (HTTP 429). The script retries
  with exponential backoff and a fresh client per attempt, which clears most
  soft blocks; persistent 429s usually mean the IP is flagged (a residential
  connection or a longer `--sleep` helps).
- **GDELT** asks for **≤1 request every 5 seconds** and returns HTTP 429 with a
  plain-text body when exceeded. Some shared/datacenter IPs appear blocked
  outright regardless of pacing — run `--probe` first to check your network.
  GDELT queries are disambiguated per ticker (`"Apple Inc"`, not `Apple`) plus a
  finance-term filter; see `gdelt_query()` in [`code/universe.py`](code/universe.py).
- **Alpha Vantage** free tier ≈ 25 requests/day — pull a small ticker sample
  at a time.

### Current pull status

| Source | Status |
|--------|--------|
| Prices | ✅ 88/88 |
| Trends | ⚠️ 44/88 — Google cut off after 11 batches; re-run to resume the rest |
| GDELT | ⛔ 0/88 — code ready, but this network is 429-blocked; run `--probe` on yours |
| AV news | ✅ 3 sample tickers (recent-window cross-check only) |

## TODO

Work is tracked in [**GitHub Issues**](https://github.com/Rickymtl/mmf1927h-workshop/issues)
— claim one by assigning yourself, and open a PR that closes it. This list is
the map; the issues have the detail, context, and acceptance criteria.

### Blocking — finish sourcing first (Day 1→2)

- [ ] [#1 Resume Google Trends pull — 44/88 missing](https://github.com/Rickymtl/mmf1927h-workshop/issues/1)
      · re-run `pull_trends.py`, it resumes automatically. Best from a home network.
- [ ] [#2 Verify GDELT and pull daily history](https://github.com/Rickymtl/mmf1927h-workshop/issues/2)
      · ⚠️ **the GDELT code has never round-tripped live data** — run `--probe`
      and validate one ticker before trusting it.

### Session 2 — cleaning & alignment

- [ ] [#3 Rescale Trends by batch anchor](https://github.com/Rickymtl/mmf1927h-workshop/issues/3)
      · without this, tickers from different batches are **not on a comparable scale**.
- [ ] [#4 Build the weekly Friday-to-Friday panel](https://github.com/Rickymtl/mmf1927h-workshop/issues/4)
      · the core Session 2 deliverable. Watch the lookahead traps.
- [ ] [#7 Adjusted prices, corporate actions, missing-data policy](https://github.com/Rickymtl/mmf1927h-workshop/issues/7)
      · returns must come from `Adj Close`, or splits become fake signal.

### Methodology & write-up

- [ ] [#5 Survivorship bias in the universe](https://github.com/Rickymtl/mmf1927h-workshop/issues/5)
      · we must disclose this before Friday Q&A asks about it.
- [ ] [#6 Decide Alpha Vantage's role](https://github.com/Rickymtl/mmf1927h-workshop/issues/6)
      · recent cross-check against GDELT, or fallback history on a reduced universe.

### Later (Days 3–5)

- [ ] Feature engineering: abnormal search interest, tone momentum, attention spikes
- [ ] Model selection with time-series CV (no random K-fold — it leaks)
- [ ] Signal evaluation: IC, hit-rate, long-short portfolio construction
- [ ] Friday presentation

## What is / isn't committed

- **Committed:** code, `requirements.txt`, `.env.example`, this README.
- **Never committed:** `.env` (your API key), everything under `data/raw/`,
  the course PDFs, and the `.venv/`.
