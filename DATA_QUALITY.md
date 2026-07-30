# Data-Quality Memo — Day 2 Deliverable

Short reference for anyone reading the analysis-ready panel
(`data/processed/panel/panel_weekly.parquet`).  Full details in the linked
issues.

> **Revised 2026-07-30 (Day 4).** Two changes since the Day 2 version:
> the news-sentiment sources are descoped (project is now course Option 1,
> prices + Trends), and the Trends missingness diagnosis in §1 was **found to
> be wrong and has been corrected** — see §6.

---

## 1. Imputation (per Rubin taxonomy)

| Source | Mechanism | Method | Max gap |
|--------|-----------|--------|---------|
| **Prices** | Structural (CEG spin-off — firm didn't exist pre-2022) | Leave NaN. CEG enters on first valid date. | ∞ (never forward-fill prices) |
| **Trends** | **Instrument artifact — not a missingness mechanism at all** (see §6) | Fixed at the source by re-pulling one ticker per request. No imputation needed. | N/A |

All imputation uses only data available on or before the date being filled,
naturally enforced by Friday-to-Friday alignment (#12).

## 2. Winsorization

Per-date cross-sectional winsorization at **p1/p99** applied to
`weekly_return` and the constructed Trends features.

Winsorized, never trimmed — extreme values are capped, not dropped (#13).

> **Note:** winsorizing raw `trends_interest` was a no-op under the old
> anchored data, which was quantised to {0,1,2} for most names.  It only
> becomes meaningful on the re-pulled series.

## 3. Standardization

**Percentile-rank** (0–1) within each Friday's cross-section.  Rank-based is
the natural fit for Rank IC evaluation.  Sector-neutral variants produced by
demeaning within GICS sector×date (#13).

> **Ordering:** Trends features are computed as **within-ticker anomalies**
> (deviation from the name's own trailing baseline) *before* any
> cross-sectional ranking.  This is deliberate: single-request pulls
> normalise each series to its own peak, so raw levels are not comparable
> across tickers — but any within-ticker transform (z-score, log-change)
> cancels that scale factor exactly.  Cross-ticker raw levels were never
> meaningful anyway, since keywords differ in ambiguity ("Apple" catches the
> fruit; "Welltower" does not).

## 4. Names / dates dropped

| Item | Decision | Reason |
|------|----------|--------|
| CEG pre-2022-01-19 | Missing from panel (no price data) | Spin-off — didn't exist yet. Enters ~Jan 2023 per 252-day min-history rule (#4). |
| Weeks with <3 valid trading days | Dropped from panel | Cannot reliably compound returns from ≤2 days. 0 weeks dropped — all weeks have 5 days except US holidays. |
| News sentiment (GDELT + Alpha Vantage) | Not in panel | Descoped Day 4 — AV free tier infeasible (~5,280 requests ≈ 211 days); GDELT never completed a full pull. Project refocused on Option 1. |

**No tickers were manually dropped** — 88/88 names are present for every week
with valid price data.  Note this is a statement about *rows*, not about
*information*: see §6 for how many names carried usable Trends signal before
and after the re-pull.

## 5. Known limitations carried forward

| Limitation | Impact direction | Tracked |
|------------|-----------------|---------|
| Survivorship bias (current-membership snapshot) | Overstates backtest returns | #5 |
| Back-adjusted prices (Yahoo restates history) | Small for weekly returns | #7 |
| No news-sentiment features | Feature set is Trends + price only; original two-signal thesis reduced to one | #2, #6, #8 |
| No true point-in-time universe membership | Survivorship-bias variant | #5 |
| Trends levels not comparable across tickers | By design — features are within-ticker anomalies (§3) | — |
| Trends keyword ambiguity | "Apple", "Amazon", "Visa" capture non-company searches; unquantified | — |

## 6. Correction: the Trends missingness diagnosis was wrong

**What the Day 2 memo said.** Trends missingness was classified
*MNAR-adjacent — "zeros = genuinely low interest, zeros are real signal"* —
and the anchor-rescaling caveat was recorded as *"impact negligible
(r = 0.9999+)"*.

**What was actually happening.** Both statements were wrong.  Every batch was
pulled alongside the anchor keyword `"stock market"`, which peaks at 100 in
every request.  Google normalises the 0–100 index *within* each request, so
company names with ~50× less search volume were quantised into {0,1,2} and,
for the smallest, to a constant 0.  The r = 0.9999 figure measured agreement
*between the surviving anchor files* — a real number answering the wrong
question.  It said nothing about resolution loss.

**Evidence.** Re-pulling the affected names **one ticker per request** (so
each series is normalised to its own peak) recovers the signal completely:

| Ticker | Anchored pull | One-per-request |
|--------|---------------|-----------------|
| MPC | 1 distinct value, 100% zeros | 59 distinct, 0% zeros |
| WELL | 1 distinct value, 100% zeros | 47 distinct, 0% zeros |
| EXC | 1 distinct value, 100% zeros | 45 distinct, 0% zeros |
| FCX | 1 distinct value, 100% zeros | 47 distinct, 0% zeros |
| TMUS | 2 distinct, 100% zeros | 50 distinct, 0% zeros |
| META | 6 distinct | 74 distinct |

Across the first 19 re-pulled names, median distinct values rose **17 → 43**,
with 16 of 19 improved.  The three unchanged (AAPL, GOOGL, AMZN) were already
the largest keyword in their old batch, so they had nothing to gain — exactly
as the mechanism predicts.

**Damage to the Day 2 panel.** On the anchored data:

| Measure | Value |
|---------|-------|
| Perfectly constant columns (zero information) | 7 — FCX, MPC, WELL, SPG, EXC, EOG, WMB |
| Tickers tied at zero in a typical week | 29 of 88 (33%) |
| Distinct values available to rank per week | 27 of 88 |
| Tickers with ≤3 distinct values over 261 weeks | 32 of 88 |

A third of the cross-section was tied every week, so per-date percentile
ranks over that region were close to arbitrary.

**Fix applied.** Trends is re-pulled one ticker per request — no anchor, no
stratification, no rescaling step.  `code/cleaning/rescale_trends.py` and the
`#3` averaged-anchor caveat are retired.  The panel builder is unchanged
apart from its input: the re-pulled series are written to the same
`data/processed/trends_rescaled/` path.

**Methodological note.** Day 2's own guidance is to *test the missingness
mechanism before choosing a treatment* — the wrong choice for MNAR data adds
bias, not just noise.  The original memo asserted a mechanism without testing
it, and would have carried a systematic instrument artifact into every
downstream feature as if it were signal.  The test that settled it was not
statistical but procedural: re-measure the same quantity with the instrument
changed.

<!-- TODO: fill in once the 88-ticker re-pull completes (currently 19/88)
     - final constant-column count (expect 0)
     - final median distinct values across all 88
     - median tickers tied at zero per week (expect 0)
     - re-run build_panel.py and regenerate panel_weekly_manifest.json -->

## 7. Day 3 — feature-level cleaning note

Feature engineering introduces a **second layer of cleaning** distinct from
the panel-level work above (Day 3 slides p23):

- Feature-specific winsorization at construction time (a ratio feature like
  ASVI can produce extreme values even from a clean panel)
- Decay weighting for momentum-style features
- Standardization at construction vs. inherited from Day 2
- Every derived feature can reintroduce problems Day 2 fixed — check each one
  again after construction

---

*Generated by `code/build_panel.py` (#4).  See `panel_weekly_manifest.json`
for the exact commit hash and parameters that produced the current panel.*
