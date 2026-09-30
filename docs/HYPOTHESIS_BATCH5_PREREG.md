# Hypothesis batch 5 — panic, quarter-end, weekday, ensemble — pre-registration (2026-10-01, before any statistic below is computed)

Research only, paper only. Data, costs, mechanics, statistics, drift control and periods exactly as batch 3 (gold DEV 2004-15 or data start,
CHECK 2016-26, SILVER 2010-26); all two-sided rules: DEV fixes the sign and its p is doubled.

## Primaries
| ID | rule | direction |
|---|---|---|
| D4 | GVZ panic: daily log change of GVZ >= its causal 97.5th percentile (previous 500 days, >= 250); gold for 5 D1 bars from the first D1 open after that day ends; stop 2 ATR(D1) | two-sided |
| A7 | quarter end: enter at the open of the 3rd-last D1 bar of March, June, September and December; hold 5 D1 bars; stop 2 ATR(D1) | two-sided |
| W1 | Monday: every Monday D1 bar (Sunday 22:00 UTC open to Monday 22:00 close); stop 2 ATR(D1) | two-sided |
PASS: DEV Holm-adjusted p <= 0.05 over the three, AND CHECK net > 0 with p <= 0.05 and excess over the drift control > 0, AND SILVER net > 0 with
p <= 0.10.

## Descriptive (never a pass)
- J2 ensemble: equal-weight mean of the weekly R of all 144 WRWR Family 2 configurations (gold 2004-26, silver 2010-26), total R, compounded
  growth at 1 % risk, and the same for the median configuration, next to the best configuration chosen in-sample.
