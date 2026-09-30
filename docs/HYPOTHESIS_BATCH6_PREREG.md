# Hypothesis batch 6 — gold/silver pair and the weekend de-risking rule — pre-registration (2026-10-01, before any statistic below)

Research only, paper only.

## P1 gold/silver ratio mean reversion (a pair trade)
- Daily log ratio r_t = log(gold D1 close) - log(silver D1 close) on common 22:00-anchored D1 dates (Dukascopy gold, HistData silver with
  the corrected clock); z_t = (r_t - mean of the previous 250 values) / their standard deviation (>= 250 needed).
- z >= +2: short gold / long silver (equal dollar legs) at the next D1 open; z <= -2: the opposite. Exit at the first D1 close with |z| <= 0.5,
  or when the ratio has moved a further 1.5 x (250-day sd of r) against the position (stop, checked at D1 closes), or after 60 D1 bars.
- Net return = both legs' returns - both legs' C4 costs - swap of the long leg; R = net return / (1.5 x sd of r at entry).
- DEV 2010-05 .. 2017-12, CHECK 2018-01 .. 2026-09; statistics as batch 1 (weekly sums, stationary bootstrap block 4, K 999, seed 20261001).
- PASS: DEV one-sided p <= 0.05 AND CHECK net mean R > 0 with p <= 0.05.

## R1 weekend de-risking (a Risk Manager rule, not an edge)
- High-gap regime at a weekend = the mean |gap| of the previous 8 weekends is above the 75th percentile of that 8-weekend mean over the
  previous 52 weekends (both known on Friday).
- Rule: on such a Friday, every open position is halved at the close of the last bar before the weekend (the other half runs unchanged).
- Evaluated on the realised live trades of the four SHADOW configurations on gold (2004-26) and silver (2010-26): per-trade counterfactual
  (trades not spanning such a weekend unchanged; spanning trades = half the original R + half the R of closing at that Friday close).
- **Adopt as a Risk Manager candidate** only if, averaged over the eight (metal x configuration) runs: the 1st percentile of weekly R improves,
  the maximum drawdown in R improves, and the total R changes by no worse than -10 % of its absolute value. Reported in any case.
