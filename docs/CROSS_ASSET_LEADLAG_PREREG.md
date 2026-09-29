# Cross-asset intraday lead-lag into gold — pre-registration v1 (2026-09-29)

Committed BEFORE `research/pilot/cross_asset_leadlag.py` is run. Operator
request: make WPWB able to find an edge. This is the one trace class the
project has not measured at intraday scale (weekly cross-asset traces failed,
Part 37; the chart's own price features carry no direction, Part 47). Codex
audits afterwards. Nothing here is a promise that an edge exists.

## Question
Does what DXY, US500, silver, USDJPY or EURUSD did over the last 5-30 minutes,
*beyond what gold itself did in that window*, predict gold's next 15-30 minutes
by enough to matter after cost?

## Design (frozen)
- Data: `data/fresh/*_M5.npz` (Exness M5, verified identical to canonical at
  offset 0), six symbols aligned on timestamps: 215,533 bars, 2023-09..2026-09,
  99.6% of steps exactly 300 s.
- Predictor at the close of bar i (all six bars closed): for asset A and window
  k ∈ {1, 3, 6} bars, the residual r_A(k) − β·r_gold(k), where r is the log
  return over k bars and β is gold's beta of A's 1-bar returns estimated on the
  previous 4,000 bars only (causal). Plus one non-cross instrument, **gold's own
  k-bar return** (short-horizon reversal, the sibling program's 51.7% signal).
- Outcome: gold forward return from the open of bar i+1 to the close of bar
  i+h, h ∈ {3, 6} bars (15, 30 min), era mean removed. Windows with a gap or
  crossing the 21:00 UTC rollover are excluded; the predictor window must also
  be contiguous.
- Eras: DEV 2023-09-01..2025-03-31, LATER 2025-04-01..2026-09-28 (both are
  recent and mined by the project's volatility work, so neither is a clean
  holdout).
- Test: out-of-era transfer as in Part 47 — bin the predictor into deciles
  fitted on the training era, take the training-era bin means of the outcome as
  the predictor, measure Pearson ρ in the other era; week-clustered bootstrap,
  4,000 resamples, add-one two-sided p.
- **Primary tests: 36** = 6 instruments (5 cross-asset + gold own) × 3 windows
  × 2 horizons, DEV → LATER, α = 0.05/36 = 0.00139.
- A **lead** needs: p < α DEV→LATER, same sign LATER→DEV with p < 0.05, **and**
  an implied gross edge 0.8·ρ·SD(outcome) larger than the round-trip cost
  (0.8 bp at current prices). A statistical lead that cannot beat cost is
  reported as "informative but untradeable".
- Self-check before reading results: 100 random circular shifts of one
  predictor (each ≥ 2 weeks) must reject at about the nominal 5% (acceptance
  band 1%–10%), and a planted ρ ≈ 0.05 must be found.

## Expected outcome, stated in advance
Markets are efficient at these scales for a retail-quality feed; prior: 0 of 36
leads and none tradeable. The value of the run is the measurement: the largest
ρ any cross-asset trace has, versus the ρ ≈ 0.05 needed just to cover cost at
a 30-minute hold.
