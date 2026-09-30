# Hypothesis batch 3 — trend (CTA time-series momentum) and calendar — pre-registration (2026-10-01, committed before any statistic)

Research only, paper only. Same data, costs, mechanics, statistics and periods as batch 1 (gold DEV 2004-15, CHECK 2016-26; silver 2010-26),
and the batch 2 drift control (same-direction entries at every D1 open of the period, one at a time, mixed by the rule's long/short share).

## Primaries (gold D1 = Dukascopy 22:00 UTC anchor; all stops 3 ATR(D1); one position at a time)
| ID | rule | direction |
|---|---|---|
| T1 | time-series momentum, 12 months: non-overlapping blocks of 21 D1 bars from the first bar with 252 bars of history; sign of the log return over the previous 252 D1 bars; hold 21 D1 bars | with the trend |
| K1 | autumn effect (Baur): enter at the open of the first D1 bar of September and of November; hold 21 D1 bars | long |
| K2 | turn of the year: enter at the open of the 5th-last D1 bar of December; hold 10 D1 bars | long |
| K3 | before Chinese New Year: enter at the open of the D1 bar 10 bars before the first D1 bar on or after the Lunar New Year date; hold 10 D1 bars | long |
Lunar New Year dates used (public calendars, fixed now): 2004-01-22, 2005-02-09, 2006-01-29, 2007-02-18, 2008-02-07, 2009-01-26, 2010-02-14,
2011-02-03, 2012-01-23, 2013-02-10, 2014-01-31, 2015-02-19, 2016-02-08, 2017-01-28, 2018-02-16, 2019-02-05, 2020-01-25, 2021-02-12, 2022-02-01,
2023-01-22, 2024-02-10, 2025-01-29, 2026-02-17.
Descriptive only: T1 with 21 / 63 / 126-bar lookbacks.

## Pass rule
DEV Holm-adjusted p <= 0.05 over the four primaries, AND CHECK: net mean R > 0 with one-sided p <= 0.05 and excess over the drift control
> 0, AND SILVER: net mean R > 0 with p <= 0.10. Reported: n, net and gross R, cost, win rate, total R, p, control R, excess, per period.
