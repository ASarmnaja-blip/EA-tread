# Hypothesis batch 1 — pre-registration (2026-10-01, committed before any statistic below is computed)

Source: docs/HYPOTHESIS_REGISTER_TH.md (operator: generate and test every hypothesis myself). Eight primary hypotheses testable with data on
disk. Research only, paper only, no orders, no alpha spent (descriptive for the alpha ledger).

## Data
- Gold H1: Dukascopy mid 2003-05 .. 2026-09 (engine.load; spread = recorded ask-bid). Gold M5 (C1, C2): data/history/XAUUSD_M5_2009_2026_spliced.npz
  rebuilt 2026-10-01 with the corrected HistData clock (research/history/histdata_time.py), HistData mid-adjusted 2009-2020 + Exness mid 2021+.
- Silver H1 / M5: HistData XAGUSD M1 with the corrected clock (research/wrwr/xag.py), bars as quoted; Exness spread 2023-09+.
- GVZ daily close (data/external/GVZ_History.csv, 2009-09-18 ..).
- M5 costs: gold uses the recorded Dukascopy ask-bid of the H1 bar containing the M5 entry bar (Exness M5 recorded spread after the Dukascopy
  data end); silver as its H1 rule. ATR(H1) on M5 bars = 14-bar ATR of H1 bars aggregated from the same M5 series, known at the open of the
  containing hour.
- Touch / cross bars (C1, C2): the entry bar itself is checked conservatively - if its range reaches the stop level the trade is a full stop at
  that bar (the order of the touch and the extreme inside the bar is unknown); otherwise the first-passage path starts at the next M5 bar with
  the entry price fixed at the level (C1) or the trigger (C2; a bar opening beyond the trigger fills at its open).
- Periods: gold **DEV 2004-01-01 .. 2015-12-31** (M5 and GVZ rules: from their data start), gold **CHECK 2016-01-01 .. 2026-09-30**,
  **SILVER 2010-01-01 .. 2026-09-24** (independent market).

## Common trade mechanics
Signal evaluated at a bar close; entry at the next bar open unless stated; engine.simulate first passage (stop first on a same-bar tie, gap
through the stop fills at the open); one position per hypothesis at a time (a signal while in a position is skipped). ATR = 14-bar ATR of
the stated timeframe known at the entry bar open. Net R = (gross - cost - swap) / stop, all in bp of the entry price; cost C4 (gold
max(2, spread + 1) bp; silver 11.615 bp before 2023, max(4, spread + 1) from 2023 with a recorded spread, else 11.615), swap
contracts.swap_bp (longs only).

## The eight primaries (parameters fixed now)
| ID | rule | direction |
|---|---|---|
| A3 | weekend gap fill: first H1 bar after a weekend with \|gap\| >= 90th percentile of the previous 104 weekend \|gaps\| (>= 52 needed); enter at the open of the SECOND bar after the weekend; stop 1.5 ATR(H1); exit after 24 H1 bars | against the gap |
| A4 | first-hour reversal: every weekend, first H1 bar after it with \|close - open\| >= 0.5 ATR(H1); enter at the next bar open; stop 1 ATR; exit after 6 H1 bars | against the first-hour move |
| A5 | Friday de-risking: every Friday, enter at the open of the H1 bar starting 17:00 UTC; exit at the close of the last bar before the weekend; stop 1.5 ATR(H1) | two-sided: DEV fixes the sign |
| C1 | round-number first touch (M5): levels = multiples of $50 (silver $0.50); the first M5 bar in 24 h whose high (low) reaches the nearest level above (below) the previous close; limit fill at the level; stop 1 ATR(H1) beyond the level, target 1 ATR(H1), exit after 144 M5 bars (12 h) | fade the approach |
| C2 | round-number cross (M5): after closing below (above) a level within the previous 12 M5 bars, the first M5 bar whose high (low) reaches level + (-) 0.25 ATR(H1); stop-order fill there; stop 0.75 ATR(H1) on the other side of the level; exit after 144 M5 bars | follow the cross |
| D3 | GVZ volatility risk premium (weekly; always GOLD's VRP, traded on gold and on silver): at each Friday cut, VRP = (GVZ/100)^2 / 52 - realised variance of the week's gold H1 log returns (GVZ = last close on or before the cut date); z-score vs the previous 52 weeks (>= 26 needed); enter at the first bar after the cut; exit at the last bar before the next cut; stop 2 ATR(D1) | two-sided: DEV fixes the sign of z |
| I2 | 52-week high: D1 close > max of the previous 252 D1 closes; enter at the next D1 open; stop 2 ATR(D1); exit after 20 D1 bars | long |
| I3 | all-time high: D1 close > the all-time highest close (seeded with the 1980 London fixes: gold $850.00, silver $49.45); same trade as I2 | long |
For C1 and C2 the same rule is also run on a **control grid** of non-round levels (level + 0.37 x spacing: gold $18.50 above each multiple
of $50, silver $0.185 above each multiple of $0.50). The primary statistic of C1 / C2 is **delta = mean net R (round) - mean net R (control)**
(equal costs on both sides); the absolute net R of the round-level rule is reported as the tradability read-out.

## Statistics and pass rule
- Per hypothesis and period: trades, mean net R per trade, mean gross R, win rate, total R. Inference: weekly sums of R and counts, stationary
  bootstrap over weeks (mean block 4, K = 999, seed 20261001), statistic = total R / total trades; one-sided p (two-sided for the DEV sign
  of A5 and D3). C1 / C2 delta: the same bootstrap on the paired weekly sums of the round and control rules.
- **PASS** = DEV Holm-adjusted p <= 0.05 across the eight primaries, AND CHECK: same sign with one-sided p <= 0.05, AND SILVER: same sign
  with one-sided p <= 0.10, AND the tradable net R per trade > 0 in CHECK and SILVER.
- Everything else is reported (per year, gross vs net); no parameter is changed after seeing results. Secondary descriptive only: C1 / C2
  on $100 multiples alone, A3 at the 75th percentile.
