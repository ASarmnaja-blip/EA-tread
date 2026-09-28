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

## Result (single run, `research/wpwb_live/run_live_hod.py`)

142 current-era weeks (2024-01-05 .. 2026-09-25). All audits clean.
**0 of 6 pass.** Best by base P&L: HOD W=26 T=2.0 at +0.78 bp/week base,
−2.75 at 1.5x, t vs RTIME +0.77, vs RDIR +1.37, vs LONG −0.15, chop half
−8.58 / trend half +10.14. The W=52 variants were clearly negative vs RTIME
(t −1.2 to −1.3). The DEV-era hour information did not survive into the
current era even with costs 5x lighter relative to moves — consistent
with traces.py: session/hour direction does not persist.

Also explored and dead (design window 2023-09..2024-12 only): DXY -> XAU
M5 lead-lag. corr(DXY_t, XAU_t+1) = −0.009 (93,550 pairs); after the top
10% of DXY moves XAU moves +0.09 bp next bar in the opposite direction
(se 0.08) vs ~1 bp cost. Not tradable; its 2025-26 test window was never
used.

## Amendment 1 — every other frozen tool gets its current-era run

To answer the user's objection completely, the remaining 34 frozen tools
of the closed search (round-1 A, C, D, D-ungated, E; round-2 G, H, META;
round-3 K, I, L) run once on the same 142 current-era weeks, unchanged.
Multiple-comparison family = all 40, so threshold p < 0.025/40 = 0.000625
vs every control, plus the same net-positive, evidence-floor (each tool's
own floor from the closed search) and regime-half rules. Written before
the run.

## Amendment 1 result (`research/wpwb_live/run_live_all.py`)

**0 of 34 pass; 0 of 40 overall.** All audits clean. Two patterns:

- **Drift, not edge:** TSM (+32 to +53 bp/week) and META (+22 to +30) are
  strongly profitable in the current era but do not beat always-long at
  the same timing (t vs LONG −0.9 to +0.3). They are long gold, re-labelled.
- **The one tool with real evidence: VOLMAN** (volatility-managed weekly
  long). vs exposure-matched long: hl=13 t +1.87, p 0.0192; hl=4 t +1.72,
  p 0.0564. Fails the 40-tool threshold (0.000625); roughly one raw p<0.025
  is expected by chance among 40 tools, so this alone proves nothing.

## Post-hoc checks on VOLMAN (disclosed: chosen because it was strongest)

`research/wpwb_live/volman_checks.py`. Excess over exposure-matched long:
+7.3 bp/week (hl=13), +8.2 (hl=4). Positive in every year (hl=13: 2024
+2.3, 2025 +10.2, 2026 +10.3). Size-permutation test (same sizes, random
weeks): p 0.013 / 0.023 — the timing of size matters. **But 73-80% of the
total excess comes from 5 weeks** (high-vol weeks with sharp falls, where
VOLMAN held less) and it is positive in only 58-62% of weeks. Gross breadth
on the same era: XAU +8.2 (t 2.00), XAG +17.3 (t 1.03), DXY +1.1, US500
−8.8, EURUSD −2.6, USDJPY −2.0 — precious metals yes, equities/FX no.

**Reading:** a plausible, WPWB-native mechanism (volatility is the one trace
that persists week to week, rho 0.81) with suggestive but not proven
evidence. At the observed effect size a forward record needs ~162 weeks to
reach t=2 and ~365 for t=3. **Status: best candidate for a frozen forward
shadow arm, not a validated edge. Engine decision: NO TRADE.**

## Amendment 2 — loss-reduction rules (frozen before testing)

Nominated by the exploratory `research/wpwb_live/loss_diagnosis.py`
(hindsight, both eras seen — NOT BLIND). None of 13 pre-week traces
predicted next-week direction in both eras. Two readable-in-advance items
survived the diagnosis: FOMC weeks were worse for longs in BOTH eras (old
−59 vs +5 bp, new −55 vs +67 bp; p 0.19 / 0.10), and the catastrophic
week (−$522) went 2.4 weekly-sigma against entry while tight stops (<=1.5
sigma) cut winners more often than losers. Rules, applied on top of VOLMAN
(hl=13), evaluated on BOTH eras (old 2021-07..2023-12, new 2024-01..
2026-09):

- **R1** VOLMAN (reference).
- **R2** VOLMAN, stand aside in weeks containing a scheduled FOMC decision.
- **R3** VOLMAN with a catastrophe stop at 2.0 x weekly sigma below entry
  (weekly sigma = rebuild daily sigma x sqrt 5; M5 path; gap-through fills
  at the bar open).
- **R4** R2 + R3.
- **R5** VOLMAN with the stop at 2.5 x weekly sigma.

Controls: for R2/R4, the SAME number of weeks skipped at random (5,000
draws) — the rule must beat random skipping on net P&L AND max drawdown
(percentile of the actual result reported). For stops, the comparison is
the same weeks without the stop. A rule is kept only if it improves max
drawdown without lowering net P&L in BOTH eras.
