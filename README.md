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

| Source | Signal | Auth | Script |
|--------|--------|------|--------|
| Yahoo Finance (`yfinance`) | OHLCV prices | none | [`code/pull_prices.py`](code/pull_prices.py) |
| Google Trends (`pytrends`) | search interest | none | [`code/pull_trends.py`](code/pull_trends.py) |
| Alpha Vantage `NEWS_SENTIMENT` | news sentiment | **API key** | [`code/pull_news.py`](code/pull_news.py) |

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
./.venv/bin/python code/pull_news.py    --tickers AAPL MSFT JPM

# Quick smoke test (first 8 tickers, all sources):
./.venv/bin/python code/pull_data.py --sample 8
```

Raw output lands under `data/raw/{prices,trends,news}/`, each with a
`provenance.json` recording exactly what was pulled and when.
**All of `data/raw/` is gitignored** — raw pulls are regenerable, can be large,
and may be non-redistributable, so they stay local.

### Rate limits & gotchas

- **Google Trends** returns *relative* interest (0–100), rescaled per request,
  and Google rate-limits `pytrends` hard (HTTP 429) — pull in small batches,
  add `--sleep`, and expect to retry (often easier from a residential IP).
- **Alpha Vantage** free tier ≈ 25 requests/day — pull a small ticker sample
  at a time.

## What is / isn't committed

- **Committed:** code, `requirements.txt`, `.env.example`, this README.
- **Never committed:** `.env` (your API key), everything under `data/raw/`,
  the course PDFs, and the `.venv/`.
