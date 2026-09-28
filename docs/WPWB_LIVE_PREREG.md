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

### Amendment 5 result (`research/wpwb_live/h1_traces.py`)

**0 of 5 Wednesday features pass.** W1 +0.03/−0.14, W3 +0.05/−0.08, W4
+0.03/−0.00, W5 +0.01/−0.03 (all p > 0.08). W2 (DXY so far) was
significant in both sub-eras but with OPPOSITE signs (−0.26, p 0.035; +0.23,
p 0.029) — not a stable trace. Hindsight library (era B): losing weeks were
broad-based (all three sessions negative, medians −49/−39/−49 bp), spread
evenly over weekdays, not concentrated in news hours (~1% of absolute
movement) or in a few jumps (top-3 H1 bars ~13%), with the dollar up
(median +0.21% vs −0.11%) and **an H1 close below the prior week's low in
51% of losing weeks vs 16% of winning weeks.**

## Amendment 6 — prior-week level break as an in-week trace (before running)

Nominated by the hindsight 51% vs 16% (disclosed). Question: after gold's
**first** H1 close beyond the prior week's range (below its low = BPL, or
above its high = BPH), occurring Monday-Thursday, does price CONTINUE for
the rest of the week? Signal d = −1 at BPL, +1 at BPH (first break of the
week only). Outcome = d x (Friday close / break-bar close − 1), bp, before
costs (costs reported separately). Pass: mean > 0 in BOTH eras (2021-07..
2023-12 and 2024-01..2026-09) with one-sided sign-flip permutation p < 0.05
in both, and the BPL half alone also mean > 0 in both eras. Runs once.

## Amendment 7 (Codex) — independent audit, external leading traces, and Fed-cycle FOMC test (before running)

**Written by Codex on 2026-09-28 at repository commit
`69d07613cad7be0823b8363ecd28ed01c8a8b08b`, before running any test below.**
This amendment authorizes read-only analysis only. It does not authorize an
order, an order-function call, a live/demo execution test, an EA change, or a
PR. The tests run once after this amendment is committed. If an implementation
bug is found, its fix and any changed/replacement test must be registered in a
new amendment before the affected result is rerun.

### A7.1 — independent audit tests

Scope is limited to `research/wpwb_search/common.py`,
`research/wpwb_search/test_common.py`, `research/wpwb_live/h1_traces.py`, and
`research/wpwb_live/fetch_fresh.py`, plus the directly called resampling,
rollover, week-boundary, event-loading, and fresh/canonical-combination helpers.
Static review is followed by these frozen executable checks:

1. run every existing test in `research/wpwb_search/test_common.py` once;
2. independently reconstruct synthetic H1 OHLC bars, including a missing-M5
   gap, and require exact timestamps/OHLC and no manufactured bar over the gap;
3. hand-check long and short Bid/Ask P&L, 1.5x spread/fee stress, entry and exit
   spread locations, and vector rollover counts against
   `mtf_engine.rollover_nights` at boundary instants;
4. require every included weekly H1 bar to start at/after its cut and end by
   the next cut, with cuts exactly Friday 22:15 UTC;
5. require calendar timestamps to be epoch seconds, the checkpoint to be
   Wednesday 00:00 UTC, every W1/W3/W4/W5 input to end before that checkpoint,
   and every three-hour W5 reaction to be fully known by it; and
6. on the existing local fresh files (do not call MT5), require sorted unique
   timestamps, measure XAU overlap agreement, require the chosen offset to be
   zero, and require `combined_bars()` to append only timestamps strictly after
   the canonical snapshot without duplicates.

The audit passes only if all invariants pass. A discrepancy is reported even
if it is conservative. The report classifies whether it can bias results
toward “no trace”, toward a false trace, or only affect descriptive output.
`fetch_fresh.py` is inspected but is not executed, so no MT5 function of any
kind is called by this audit.

### A7.2 — external data and ten pre-week traces

Data are downloaded from first-party public sources and stored under
`data/external/`, with raw files and a README recording exact URLs, retrieval
date, fields, transformations, and hashes:

- US Treasury daily nominal par curve: 2-year and 10-year yields;
- US Treasury daily real par curve: 10-year TIPS yield;
- Cboe daily GVZ close (gold implied volatility); and
- CFTC annual disaggregated futures-only reports: COMEX gold managed-money
  long and short positions.

Window: complete WPWB weeks with cuts from 2021-07-02 through 2026-09-25,
split without overlap into era A = 2021-07..2023-12 and era B =
2024-01..2026-09. Causal alignment is deliberately conservative: at a Friday
22:15 UTC rebuild, yield/GVZ observations must be dated no later than Thursday;
CFTC observations use the latest report whose public release Friday is at or
before the cut (the report's Tuesday `As of Date` alone is not treated as its
availability date). Missing/stale observations are left missing, never filled
from the future. Gold outcomes are the following complete week's gross return;
costs are irrelevant to a correlation trace and are not subtracted.

The ten frozen traces and directional alternatives are:

- N1/N2: 2-year yield level and 13-week change, negative with next-week gold;
- N3/N4: 10-year nominal yield level and 13-week change, negative;
- R1/R2: 10-year real yield level and 13-week change, negative;
- G1: GVZ divided by trailing-20-session realised gold volatility, positive
  with next-week absolute gold return;
- G2: 13-week GVZ change, positive with next-week absolute gold return;
- C1: managed-money net position `(long-short)` percentile in its trailing
  52 released reports, negative with next-week gold (crowding/reversal); and
- C2: four-report change in managed-money net position, positive with
  next-week gold (position momentum).

For each trace and each era, report n, Spearman rho, and a one-sided empirical
p-value from 20,000 seeded **random-timing controls** that circularly shift the
outcome by a non-zero lag while keeping the trace's time order intact. The
shared seed is 20260928. A trace passes only if it has its registered sign and
`p < 0.05 / 10 = 0.005` in **both** eras. Family size remains ten even if a
source is unavailable; an unavailable or insufficient trace is `NOT ASSESSED`,
not silently removed from the correction. Report all ten, including failures.

### A7.3 — FOMC direction from the Fed cycle

One hypothesis only: on a week containing a scheduled FOMC decision, define
the causal Fed-direction signal from the 2-year Treasury yield's 63-trading-day
change available at the rebuild: falling/unchanged is dovish (`+1` gold),
rising is hawkish (`-1` gold). The score is that signal times the complete
FOMC-week gross gold return. FOMC dates come from the already-used verified
2016-2021 list and the local calendar for 2022-2026; no event is chosen by its
return.

The confirmatory windows are the same two required eras A and B. In each era
report event count, direction counts, mean/median score, hit rate, and two
one-sided seeded controls (20,000 draws each): (a) random-direction sign flips
on the actual FOMC weeks, and (b) the same number of random weeks from that era
with the contemporaneous Fed-direction signal. The hypothesis passes only if
mean score is positive, hit rate exceeds 50%, and both empirical p-values are
below 0.05 in **both** eras. The 2016-08..2020-11 D1 period is reported only as
explicitly non-confirmatory cycle context because its FOMC returns were
already examined in Part 34.

Power is reported from the actual FOMC event counts and, separately, the
number of independent easing/tightening transitions. Event-week significance
must not be described as confirmation across policy cycles: with roughly two
cycles, cycle-level generalisation is `NOT ASSESSED` regardless of event-level
results. Random controls and A7.2/A7.3 outcomes are generated by one new
read-only script; it must contain no MetaTrader5 import or trading API call.

### Amendment 7a (Codex) — end-cut correction before the A7.2/A7.3 run

The A7.2 phrase “complete WPWB weeks with cuts ... through 2026-09-25” named
the latest rebuild cut, but its following week is not complete in local prices
on 2026-09-28. Before any A7.2/A7.3 result was computed, the final eligible
outcome cut is corrected to **2026-09-18**; 2026-09-25 is excluded. Everything
else in Amendment 7, including the trace family, signs, eras, controls, seed,
and pass criteria, is unchanged.

### Amendment 7b (Codex) — timestamp implementation correction before rerun

The first A7.2/A7.3 execution printed 272 weeks ending 2026-09-11. Inspection
showed the 2026-09-18 week has 115 H1 bars and is complete, but the code encoded
`FINAL_CUT` as midnight at the start of 2026-09-18; the actual WPWB cut at
22:15 was therefore greater than the limit and wrongly excluded. That first
output is **superseded**. Before rerunning, change only the constant to
2026-09-18 22:15 UTC. The family, data transformations, controls, seeds, and
pass rules remain frozen. The corrected 273-week run is the result of record;
both the defect and any numerical changes are reported.

### Amendment 7 result (Codex)

**A7.1 audit:** all 7 existing `test_common.py` tests passed. The independent
checks also passed: H1 OHLC/continuity, Bid/Ask and 1.5x costs, entry/exit
spread locations, rollover boundary equivalence, Friday 22:15 week boundaries,
Wednesday 00:00 checkpoint causality, epoch-second events/W5 completion, and
fresh/canonical combination. XAU overlap was 216,085 bars, 99.9995% within
0.01, best offset +0h; 1,373 bars were appended strictly after canonical.
No active bug was found that biases the tested traces toward “no trace.”

Two robustness limitations do not change the test results: `fetch_fresh.py`
writes files before its final validation and leaves them in place on a failed
validation (potential bias either way on a future failed fetch), while the H1
descriptive day/session summaries sum bar bodies and omit inter-bar gaps
(descriptive library only, not W1-W5 outcomes).

**A7.2 corrected run:** 273 complete weeks, 2021-07-02..2026-09-18 (era A
131, era B 142). **0 of 10 pass.** Rhos (A/B) and random-timing p-values:
N1 +0.077/−0.119 (0.853/0.178), N2 −0.005/−0.140 (0.531/0.022),
N3 +0.073/−0.144 (0.829/0.035), N4 −0.003/−0.107 (0.453/0.086),
R1 +0.102/−0.131 (0.969/0.058), R2 +0.051/−0.094 (0.680/0.130),
G1 +0.143/+0.042 (0.090/0.373), G2 +0.056/+0.154 (0.246/0.061),
C1 −0.150/−0.015 (0.016/0.403), C2 −0.158/+0.015 (0.939/0.418).
The pass threshold was p<0.005 in both eras. The first, superseded 272-week
run omitted the final cut due to Amendment 7b's midnight/22:15 bug; correcting
it changed some era-B numbers but no verdict.

**A7.3 corrected run: FAIL.** Era A: 20 FOMC weeks (6 dovish/14 hawkish),
mean score +5.0 bp, median +9.0, hit 55.0%, p=0.451 vs random direction and
0.314 vs random weeks. Era B: 22 (11/11), mean +102.2 bp, median +116.2,
hit 68.2%, p=0.0345 vs random direction but p=0.0954 vs random weeks. Both
controls had to pass in both eras. Binomial power for a true 60%/65%/70% hit
rate was only 12.6%/24.5%/41.6% in A and 15.8%/30.2%/49.4% in B. The already-
examined 2016-08..2020-11 context was positive (27 verified FOMC weeks, +48.6
bp mean score, 59.3% hit) but is not confirmation. With only about two policy
cycles, cycle-level generalisation is **NOT ASSESSED**. Fed-funds-futures data
were not retrieved and are also **NOT ASSESSED**. Engine decision remains
**NO TRADE**.
