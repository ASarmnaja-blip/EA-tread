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

## Amendment 3 — out-of-era test on never-examined data (before running)

`research/wpwb_live/luck_check.py` showed the two surviving rules rest on
few events (VOLMAN's edge over LONG = its best 3 weeks; the new-era FOMC
gain = one week; best-of-15 random skip rules beat the FOMC gain 30% of
the time; pooled permutation p 0.008 becomes ~0.12 after the selection
penalty). The only honest way to separate a readable trace from luck is
data never looked at: broker XAUUSD H1 from **2016-08-09 to 2021-12-31**
(MT5 history; no test in this project has used it for these questions).

- FOMC decision dates 2016-2021 are entered by hand (the local calendar
  starts 2022) and each is **verified against the price data before use**:
  the H1 bar containing the statement time must have a range above the
  median range of that same UTC hour on non-FOMC Wednesdays of the same
  year. Dates that fail verification are reported and excluded.
- Weekly Sunday-open to Friday-close long, Demo90 costs and long swap, bp.
- **Test F (FOMC):** mean bp of FOMC weeks < mean of other weeks, one-sided
  permutation p < 0.05, AND the share of losing weeks is higher in FOMC
  weeks. Both required.
- **Test V (VOLMAN, hl=13):** excess over exposure-matched long > 0 with
  size-permutation p < 0.05, AND the excess stays positive after removing
  its best 3 weeks. Both required.
- Each test runs once. Whatever it shows is recorded as the answer.

### Amendment 3 result — H1 run (data coverage failure disclosed)

`research/wpwb_live/oos_2016.py`. Broker H1 history before 2020-12 is NOT
intraday: only 7,864 H1 bars exist for 2016-08..2022-01 (vs ~30,000
expected), so only 9 of 43 FOMC dates had a statement-hour bar. All 9
verified (statement-hour range 3.1x-9.9x the same hour on ordinary
Wednesdays — the hand-entered dates are correct where checkable). The
weekly test therefore covered only 2020-12-04..2021-12-24 (56 weeks, 9
FOMC weeks). **Test F: FAIL** (FOMC weeks −20.8 bp vs −21.3 bp other,
losing 44% vs 51%, p 0.485). **Test V: FAIL** (excess −60 bp, size-
permutation p 0.858). Underpowered, but neither rule shows the expected
sign.

## Amendment 4 — D1 run for the part H1 could not cover (after seeing the H1 result)

Decided AFTER the H1 result above, disclosed as such: the pre-registered
window was 2016-08..2021-12; H1 could only cover 2020-12 onward. Broker D1
bars exist for the whole window and suffice for weekly Sunday-open ->
Friday-close returns and daily sigma. Same Tests F and V, same pass rules,
on D1 for **2016-08-09 .. 2020-11-27** (disjoint from the H1 run). FOMC
dates verified on D1 instead (statement-day range above the median range
of non-FOMC Wednesdays of the same year). Swap = one night per Mon-Thu
daily bar in the week. Runs once; both runs are reported together.

### Amendment 4 result (`research/wpwb_live/oos_2016_d1.py`)

224 weeks, 2016-08-12..2020-11-20; 27 of 34 FOMC dates verified on D1 (7
quiet days excluded by the strict rule). **Test F: FAIL, and reversed** —
FOMC weeks +95.9 bp vs −20.8 bp other, losing 30% vs 51% (p 0.999 for the
"worse" hypothesis). **Test V: FAIL** — VOLMAN excess −588 bp, size-
permutation p 0.900, −890 bp without its best 3 weeks. (Today's swap rate
applied to 2016-2020 overstates costs, but it is a constant per week and
cancels out of both tests.)

By year, FOMC-minus-other bp: 2016 +145, 2017 −28, 2018 +69, 2019 +110,
2020 +389, 2021 −29, 2022 −88, 2023 −46, 2024 −31, 2025 −37, 2026 −357;
pooled 2016-2026 FOMC +3.2 vs other +7.9 bp/week — no stable effect. The
sign tracks the Fed cycle (easing 2019-2020: FOMC weeks good for gold;
tightening from 2022: bad). **Conclusion: both surviving rules were
regime-specific / luck, not stable readable traces.** Neither is carried
forward as a rule.

## Amendment 5 — H1 Wednesday-checkpoint traces (before running)

User: the weeks are past, so find at H1 what the trace was, WPWB-style.
Two parts. (a) A descriptive H1 trace library for every week 2021-07..
2026-09 (hindsight, for the rule-9 guideline library, not a test). (b) A
test of whether the H1 trace visible at the **Wednesday Report checkpoint
(Wednesday 00:00 UTC, after the Monday and Tuesday sessions)** predicts the
rest of the week (Wednesday 00:00 -> Friday close). Five features, frozen:

- **W1** gold return so far (week open -> checkpoint);
- **W2** DXY return so far (DXY H1 exists from 2023-09 only);
- **W3** prior-week level acceptance: +1 if the latest H1 close beyond the
  prior week's range before the checkpoint was above its high, −1 if below
  its low, 0 if none;
- **W4** realised H1 volatility so far / volatility forecast at the rebuild
  (tested against the rest-of-week |move| and against its direction);
- **W5** event reaction: sum over tier-1 USD releases before the
  checkpoint of the sign of gold's 3-hour return starting at the release
  bar (acceptance direction of the news).

Eras: A = 2021-07..2023-12, B = 2024-01..2026-09 (W2: 2023-09..2024-12 vs
2025-01..2026-09). A feature counts as a readable Wednesday trace only if
its Spearman correlation with the rest-of-week return has the **same sign
in both eras and p < 0.01 in both** (Bonferroni over 5). W4-vs-|move| is
reported separately (magnitude, not direction). Runs once.
