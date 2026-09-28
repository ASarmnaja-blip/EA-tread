# WPWB-live — current-era test of the frozen hour-of-day tools (pre-registration)

**Written 2026-09-28, before any current-era P&L of these tools was computed.**
Supersedes nothing in `docs/WPWB_EDGE_SEARCH_PREREG.md`; that search is closed
and recorded. No order, EA change or PR is authorized here.

## 1. Why this exists

The user rejected the closed search's framing: WPWB exists to read the
*current* market each week, and judging tools by their 2021-2023 behaviour
misses that. Two measurements (made without computing any tool P&L on
2024+ data) support the objection:

- **Cost relative to typical move collapsed.** Median round-trip cost as a
  share of the median absolute H1 move: 19.0% (2021), 16.4% (2022), 19.3%
  (2023), 13.5% (2024), 7.1% (2025), **3.6% (2026)** — gold went from ~$1,800
  to ~$4,500 while the dollar cost stayed ~$0.26. The DEV era was the worst
  possible era in which to judge intraday tools.
- **Which traces persist week to week** (`research/wpwb_live/traces.py`,
  Spearman next-week rho, 2024-01..2026-09): realised volatility +0.81, XAU/
  DXY correlation +0.34; every direction/character trace (session drifts,
  weekly return, intraday autocorrelation, variance ratios) ~0. So a WPWB
  tool cannot rely on "last week's direction repeats"; it can rely on
  volatility persisting and on structure that is stable over many weeks.

Hour-of-day selection was the only family in the closed search that beat
its controls in DEV (t vs RDIR up to +2.17, vs RTIME up to +1.81) and it
failed on cost. It is also the most WPWB-shaped tool: every Weekend Rebuild
re-estimates the hour profile from the trailing weeks, decay-weighted, and
sets the coming week's hours and directions.

## 2. Tools — frozen, zero changes

The six hour-of-day variants exactly as pre-registered and coded in the
closed search (`approaches.hod_week`, `approaches2.hodm_week`):
HOD W=26 T=2.0, HOD W=26 T=3.0, HOD W=52 T=2.0, HOD W=52 T=3.0,
HODM W=52 T=2.0, HODM W=52 T=3.0. Every variant is reported; none is
chosen after the fact.

## 3. Data and period

- Canonical XAUUSD M5 snapshot + fresh MT5 M5 bars after 2026-09-21 08:35
  (`research/wpwb_live/fetch_fresh.py`; verified identical to the snapshot
  on 216,085 overlapping bars, 99.9995% of closes within 0.01, offset 0h).
- Weekly rebuilds with cut from 2024-01-05 through the last cut whose week
  is complete in the data. Each week's tool uses only bars before its cut
  (the closed search's look-ahead audit is re-run here).
- Disclosure: `traces.py` printed 2024+ session-level mean drifts (Asia and
  London positive, NY slightly negative) before this was written. No tool
  parameter was changed because of it (all six were frozen days earlier).

## 4. Costs, controls, test — as the closed search, unchanged

Demo90 costs with long swap; judged at 1.5x stress. Controls LONG, RDIR,
RTIME, all exact expectations. p = max(circular-block-8 bootstrap,
Newey-West-8), threshold **0.025 / 6 = 0.00417** against **every** control
(Bonferroni over the six variants). Also required: mean weekly P&L > 0 at
base and 1.5x; >= 50% of weeks traded; mean weekly P&L >= 0 at base in both
halves of the period split at the median trailing-20-day efficiency ratio
(the drift-artifact guard). Year-by-year results reported for context only.

## 5. What a pass means

A variant that passes is a **candidate WPWB tool for a frozen forward shadow
arm**, with its weekly rebuild run every Saturday from 2026-10-03 — not a
licence to trade real money. A fail on every variant is reported as such.

## Result

(filled after the single run)
