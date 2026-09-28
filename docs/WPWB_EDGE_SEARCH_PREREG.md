# WPWB edge search — pre-registration (written 2026-09-28, before any run)

The user asked for an autonomous, multi-approach search for a setup/edge that
fits WPWB (Wednesday Report / Weekend Rebuild, `docs/AMENDMENT_22_WEEKLY_
OPERATING_PROTOCOL.md` + rule-9 addendum), self-checked and self-corrected,
presented only when done, judged by the user as pass/fail. This file is the
contract that keeps a multi-approach search from manufacturing a false edge.
It is committed before any approach below is run. Nothing here authorizes an
order, an EA change, or a PR.

## 0. What is already dead (not re-tested here)

- The 8,250-cell setup grid (sweep/expansion/vwap/failed/breakout/pullback):
  fails real-vs-random in every window and regime tested (LOGIC_LEDGER Parts
  18-28), including a pooled 145-week regime-matched sample.
- News acceptance/rejection (`news_acceptance_edge.py`): fails its own dev gate.
- 6,480 indicator-signal variants (Amendment 10 / `wide_search_manifest.json`):
  max-T p = 0.854.
- Hourly-horizon trend/breakout on 26-27 futures: reliably negative
  (RESEARCH_FINDINGS "The edge is real, it is just not intraday").

The approaches below were chosen to be structurally different from all of
these: none is an indicator-trigger entry on the 8,250-cell grid.

## 1. WPWB fit, made concrete

Every approach is a *weekly rebuild procedure*: at each Weekend Rebuild
boundary (Friday 22:15 UTC, `weekly_evolution_grid._week_boundary`), it uses
only data strictly before the boundary, weights recent weeks more (exponential
decay, half-life stated per approach), sets the coming week's tool (direction,
hours, or trigger), and that tool is fixed until the next boundary (rule 7:
retune only at Weekend Rebuild). The tool may differ every week (rule 4).

## 2. Data, costs, units

- Canonical XAUUSD M5 (`data/canonical_XAUUSD_M5.npz`, sha256 prefix 613d5e74),
  2021-01-03 .. 2026-09-21. H1 bars resampled from it (`mtf_engine.resample`).
- Prices are Bid. Long: buy at Bid+spread, sell at Bid. Short: sell at Bid,
  buy back at Bid+spread. Spread = bar spread floored at 0.090. Commission
  0.140 round turn, slippage 0.0165 per fill. Long swap 0.5493 per 21:00 UTC
  rollover (`mtf_engine.rollover_nights`, no triple-Wednesday adjustment —
  applied identically to strategy and controls). Short swap 0.
- 1.5x stress: commission + slippage + spread multiplied by 1.5 (swap unchanged).
- Unit: basis points of entry price (bp), so 2021 ($1,800) and 2026 ($4,300)
  weeks are comparable under fixed-fractional sizing. Weekly P&L = sum of the
  week's trade bp.

## 3. Split — sealed holdout

- **DEV**: rebuild boundaries from 2021-03-05 up to (not including) 2024-01-01.
  All design choices and finalist selection use DEV only.
- **HOLDOUT**: rebuild boundaries from 2024-01-01 to 2026-09-21. Opened exactly
  once per finalist, after finalists are frozen in this file's addendum.
- Disclosure: HOLDOUT price data is NOT blind — earlier Parts looked at this
  period for other questions. It IS blind to the results of every approach
  below. Genuine confirmation only comes from forward weeks after this date.

## 4. Approaches and their full, pre-declared variant grids

Total variants evaluated on DEV: **20**. All 20 will be reported.

**A. TSM — weekly time-series momentum.** Direction for the week = sign of the
decay-weighted mean of trailing weekly log returns, lookback L weeks, half-life
L/2. Enter at the first H1 open after the boundary, exit at the last H1 close
before the next boundary. Variants: L in {4, 8, 13, 26} (4).

**B. HOD — hour-of-day seasonality, weekly retuned.** For each UTC hour, the
decay-weighted mean and t-stat of that hour's return over the trailing window
(half-life = window/2). Trade next week, in each hour whose |t| >= T, in the
sign of its mean, one H1 bar per trade (open to next open). Variants: window
in {26, 52} weeks x T in {2.0, 3.0} (4).

**C. DOW — day-of-week seasonality, weekly retuned.** Same as B with UTC
weekday instead of hour, one day (00:00-23:59 UTC session) per trade.
Variants: window 52 weeks x T in {1.5, 2.0} (2).

**D. CHOPREV — regime-gated short-horizon reversal.** At the boundary, the
week is "chop" if the trailing-20-trading-day efficiency ratio of M5 closes
<= 0.05 (Part 28's criterion). In chop weeks only: when an H1 bar's return
exceeds z x ATR(14, H1) in either direction, fade it from the next H1 open for
H bars. Variants: z in {1.5, 2.5} x H in {2, 6} (4). Plus the SAME 4 variants
with no regime gate (D-ungated, 4) — to measure whether the gate adds value.

**E. GAP — weekend gap, weekly retuned.** Gap = first H1 open after the
boundary minus last H1 close before it. Mode (fade or follow) chosen each
week by the sign of the decay-weighted mean P&L of "follow" over the trailing
52 weeks (half-life 26); trade only if |gap| >= k x ATR(14, H1), hold to the
close of the first H-hour block. Variants: k in {0.5, 1.0} (2). H = 4 fixed.

## 5. Controls (all evaluated on the exact same weeks and costs)

- **RDIR** — same entry/exit timestamps, direction by fair coin (seed fixed).
  Averaged over 200 draws to remove control noise. Tests: does the chosen
  direction carry information?
- **LONG** — same entry/exit timestamps, always long. The drift benchmark.
- **RTIME** (B, C, D, E only) — same number of trades per week and same
  direction mix, placed at uniformly random eligible H1 bars of that week
  (200 draws averaged). Tests: does the chosen timing carry information?

## 6. DEV eligibility and finalist selection

A variant is DEV-eligible only if, on DEV, at 1.5x stress:
1. mean weekly P&L > 0;
2. paired weekly difference vs **every** applicable control has a moving-block
   bootstrap (block 4 weeks, 5,000 draws, seed fixed) one-sided 95% lower
   bound > 0;
3. at least 50% of DEV weeks contain a trade (D-ungated/E exempt at 25%: event
   strategies).

Finalists: at most one variant per approach (highest DEV paired t vs its
strictest control), at most **3 finalists total** (highest DEV t). Finalists
are written into this file's addendum and committed BEFORE holdout runs.
If zero variants are DEV-eligible, the search ends with a reported failure;
HOLDOUT is not opened for anything.

## 7. HOLDOUT pass criterion (per finalist, one run, no re-tuning)

All must hold on HOLDOUT:
1. mean weekly P&L > 0 at base AND at 1.5x stress;
2. paired weekly difference vs every applicable control: one-sided bootstrap
   p < 0.05 / (number of finalists) (Bonferroni);
3. not negative in either holdout regime half: holdout weeks split by the
   week's trailing-20d efficiency ratio at its median; mean weekly P&L >= 0 in
   both halves at base cost (guards against the Parts 18-27 drift artifact);
4. the evidence-floor from section 6 item 3.

A finalist passing all four is presented as a **candidate for a forward
shadow arm** under Amendment 27's discipline — not as a validated live edge.
A finalist failing any one is reported as failed. No criterion may be
changed after this file is committed; any change requires a new
pre-registration that discloses this one.

## 8. Verification duties (self-check before presenting)

- Unit test the P&L function on hand-computed trades (long, short, gap,
  rollover swap) before any approach runs.
- Look-ahead audit: for each approach, mutate all data after a boundary and
  confirm that boundary's chosen tool is unchanged.
- Control sanity: RDIR mean must be ~ -cost per trade on a driftless
  synthetic series; LONG on the real series must equal buy-and-hold minus
  costs/swap for the same exposure.
- Every number presented must be reproducible by a committed script.

## Amendment 1 — stricter significance test (before any approach ran)

The section 8 unit tests caught that the section 6/7 moving-block bootstrap
(block 4) is anti-conservative: on simulated null weekly series (n=140-200)
it gave p < 0.05 in 9% of runs (iid) and ~8-9% with AR(1) phi=0.3. Circular
block (8/12), Newey-West (lag 4/8) alone were all anti-conservative too
(6-10%). Replacement, strictly harder to pass than the original:

- p = max(centered circular-block-bootstrap p [block 8, 5,000 draws],
  Newey-West p [lag 8, Student-t]);
- DEV eligibility (section 6 item 2): p < **0.025** vs every applicable
  control (replaces "95% lower bound > 0");
- HOLDOUT (section 7 item 2): p < **0.025 / k** (replaces 0.05 / k).

Measured true false-pass rate of this rule on n=140 AR(1) nulls: 3.3% (phi
0), 4.1% (0.3), 5.0% (0.5) at 0.025; 0.9-1.7% at 0.0083 (k=3). Implemented
in `research/wpwb_search/common.py::block_boot`, guarded by
`test_common.py::test_boot_size_under_null`. Nothing else changes. RDIR/
RTIME controls are computed as their exact expectation (the limit of the
section-5 200-draw average), which removes control noise without favouring
either side.

## Addendum — finalists (to be filled after DEV, before HOLDOUT)

(empty at commit time)
