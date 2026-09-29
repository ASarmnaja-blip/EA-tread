# Tool Foundry ledger (append-only; each batch registered before it runs)

Protocol: `docs/FOUNDRY_PROTOCOL.md`. Trials: `data/foundry/trials.csv`; state (cumulative VAL
count M, HOLD looks j): `data/foundry/state.json`.

## Batch `batch1` (registered 2026-09-30, before running)
36 variants from 12 families, each × direction {both, long, short} × 10 cells (ALL + 9):
ASIA_BRK (Asia 00-07 UTC range break 07-16, stop opposite side, target 1R/2R/none, exit 20:00),
ASIA_FAIL (failed break of the Asia range, fade, target range opposite / 1R), NY_ORB (13-15 UTC
range, break 15-20), SHOCK_REV / SHOCK_CONT (H1 move > 2 or 3 ATR, fade or follow, hold 3/6/12 h,
stop 2 ATR), DONCH (D1 20/55-day channel, hold 10/20 d, stop 2.5 ATR), SMA_TREND (D1 close vs
SMA200 with SMA50, hold 5/20 d, stop 3 ATR), RSI2 (Connors RSI(2) < 10 above SMA200 / > 90 below,
hold 3/5 d), BB_REV (H1 Bollinger 20/2 fade to the middle band, hold 6/12 h, stop 2 ATR), NR7 (D1
narrowest range of 7 -> next-day OCO stop entries on H1, target 1R/2R), GAP_FADE (weekend gap > 1/2
H1 ATR, fade to Friday close), TOM_LONG / TOM_SHORT (turn of month, 4 days).

### Result `batch1` (730 DISC candidates; cumulative 730)
DISC pass 4, all NR7 (narrow-range-7 breakout, t_net 3.4-4.9, long side strongest); **all 4 failed
VAL** (2015-20 net -3.3..+0.3 bp, p 0.47-0.70; M = 4). Nothing reached HOLD.
Diagnosis (DISC only): (1) mean reversion loses almost everywhere - BB_REV, SHOCK_REV, ASIA_FAIL,
RSI2 short all gross < 0, worst in HIGH/UP; (2) every continuation variant is gross > 0: SHOCK_CONT
18/18 rows positive, strongest in HIGH-vol cells (+12..+35 bp), ASIA_BRK without a target +3.9 bp
gross but a 1R/2R target caps winners; (3) D1 trend families (DONCH, SMA_TREND, TOM) make money
only on the long side with excess <= 0: gold's 2003-14 drift, not the setup; (4) CALM/FLAT is
negative for nearly every family - a no-trade cell; (5) NR7 passed DISC beyond Bonferroni for 730
tests yet vanished in 2015-20: decay after the 2003-14 bull/high-vol era (not re-tuned: tuning on
VAL is forbidden). Per-cell samples are thin (n < 20 for D1 families).
Fix: pool power along one regime axis (marginal cells HIGH/*, NOTCALM/* etc.) and test the
continuation idea directly.

## Batch `batch2` (registered 2026-09-30, before running)
Cells now ALL + 9 + 7 marginal (CALM/*, NORMAL/*, HIGH/*, NOTCALM/*, */DOWN, */FLAT, */UP).
MOM (H1 momentum: |move over L = 3/6/12/24 h| > z = 1.0/1.5/2.0 x ATR x sqrt(L) -> follow, hold L,
stop 2 ATR, no target), PDHL_BRK (break of the previous day's high/low, follow to the day's end,
stop 2/4 ATR), WEEK_BRK (break of the previous week's high/low, follow to the week's end, stop
0.5/1 x last week's range), plus SHOCK_CONT (6) and ASIA_BRK_t0 re-scored on the new cells.
Each x {both, long, short}. SHOCK_CONT and ASIA_BRK_t0 were already seen in DISC; their re-score
is a new look and counts as new candidates.

### Result `batch2` (1,054 DISC candidates; cumulative 1,784)
DISC pass 0. Continuation again positive nearly everywhere (MOM L6/L12 at z >= 1.5 +5..+13 bp,
SHOCK_CONT k3 +10..+26 bp in HIGH/*), best t_net 2.93 (WEEK_BRK long */UP, excess t 1.5 = drift),
SHOCK_CONT_k3_h6 both t 2.91 / excess t 2.73. Mean-reversion and CALM results unchanged.
Diagnosis: the effect is consistent in sign but its t is capped by bp-variance from the 2008-13
high-volatility years; fixed-risk sizing is how it would be traded -> protocol Amendment 1 (R units).

## Batch `batch3` (registered 2026-09-30, before running)
SHOCK_CONT (6), MOM (12), PDHL_BRK (2), WEEK_BRK (2), ASIA_BRK_t0 (1) re-scored in R units on the
17 cells x {both, long, short}. NR7 is excluded (it already failed VAL; re-sending it would reuse VAL).

### Result `batch3` (1,054 DISC candidates; cumulative 2,838)
Risk units did not lift power: t_R ~ t_net. DISC pass 1: WEEK_BRK_s1.0 long */UP (t_R 3.60, excess
t 2.47) -> **VAL fail** (2015-20 net -1.0 bp, R +0.09, p 0.17; M = 5). Long-only in up-trend weeks
is close to drift. Diagnosis: the continuation edge is ~0.05-0.15 R per trade; with 12 DISC years a
single variant cannot reach t 3. Two ways left inside the data: pool the continuation signals into
one tool (more independent trades) and let WPWB's weekly regime choose when it is switched on
(operator 2026-09-30: use the tool that fits WPWB; do not stop until "หยุด").

## Batch `batch4` — WPWB router v1 (registered 2026-09-30, before running)
One pooled tool, CONT_UNION_h6: follow after a > 3 ATR H1 bar, or a 6 h move > 1.5 ATR*sqrt(6),
or a 12 h move > 1.5 ATR*sqrt(12); hold 6 h; stop 2 ATR; no target; one position at a time; both
directions only. Router cells pre-declared: HIGH/* (WPWB forecast HIGH weeks only), NOTCALM/*
(every week except CALM), ALL. 3 candidates only.

### Result `batch4` (3 candidates; cumulative 2,841)
DISC pass 0. CONT_UNION_h6 ALL: 1,240 trades, net +4.0 bp, R +0.07, t_R 2.31, **excess over matched
random t_R 4.02**; NOTCALM t_R 1.58; HIGH t_R 1.35 (only 407 trades). Pooling beat random entries
clearly but not zero after costs, and restricting to WPWB HIGH weeks cost more power than it gained.
Diagnosis: the timing information is real relative to random entries; the net edge is small
relative to its noise. Next: is it concentrated in the liquid sessions?

## Batch `batch5` (registered 2026-09-30, before running)
CONT_UNION_h6, SHOCK_CONT_k3_h6, MOM_L6_z1.5 split by entry hour UTC: ASIA 0-6, LONDON 7-11,
NYAM 12-16, LATE 17-21, OPEN 22-23; cells ALL and NOTCALM/*; both directions. 30 candidates.

### Result `batch5` (26 candidates; cumulative 2,867)
DISC pass 0. Continuation lives in New York morning (CONT_UNION@NYAM 614 trades, +7.6 bp, t_net 2.46)
and Asia; LATE (17-21 UTC) and the Sunday open are negative. Splitting by session costs power.

## Nomination 1 (Amendment 2, registered 2026-09-30, before its VAL score is seen)
CONT_UNION_h6, cell ALL, both directions (DISC t_R 2.31, t_excess_R 4.02, net +4.0 bp). Chosen
because it is the pooled form of the only effect seen in every batch, not the best-looking slice
(the best slices were smaller subsets of it).

### Result nomination 1
VAL **FAIL**: 2015-20 n 739, net -2.86 bp, R -0.045, t_R -1.25, p 0.89 (M = 6). Note: the DISC
excess t_R came out 3.10 on the nomination run vs 4.02 in batch4 - the matched random control has
seed noise of about +/-1 in t; it still met the nomination bar.
**Diagnosis across everything so far:** every effect found in 2003-14 (NR7, continuation, weekly
breakout) is flat or negative in 2015-20. Edges are era-specific. That is the premise of
CLAUDE.md (current-regime, Champion/Challenger) and of WPWB's weekly clock: a fixed setup is the
wrong tool; a procedure that re-chooses the setup from recent evidence is the right one to test.

## Batch `batch6` — WPWB Champion/Challenger selector v1 (registered 2026-09-30, before running)
Menu `menu1`: all 59 distinct variants of batches 1-2 plus CONT_UNION_h6 (both directions). At each
Friday cut: score_v = sum of net R over the variant's trades that EXITED within the last L weeks
/ sqrt(count) (count >= 10); champion = argmax; trade the champion's entries of the coming week if
score >= s, else NO TRADE. Grid L in {26, 52, 104} x s in {1, 2} x regime in {off, on} (on = score
only trades from the same WPWB volatility class as the coming week): 12 candidates. Control =
equal-weight average R of all menu variants' trades that week (does choosing beat holding the
whole menu?). Same DISC/VAL/HOLD gates in R units.

### Result `batch6` (12 candidates; cumulative 2,879)
DISC pass 0. Best SELECT_L104_s1.0: t_R 1.44, +3.6 R/yr, 19 different champions; regime-conditioned
scoring is worse (t_R -1.8..+0.3). Top-1 champion choice is too noisy.
Diagnostic (DISC only, `research/foundry/persistence.py`): performance does persist - rank IC
between trailing-L-week and next-H-week mean R across variants is +0.03..+0.105 with intervals
above 0, strongest for L = 52, H = 4-13. Future mean R by trailing-score quintile (L52, H13):
Q1 -0.077, Q2 -0.017, Q3 -0.004, Q4 +0.018, Q5 +0.039 R per trade - monotonic. The information is
in holding the whole top group, not in one champion.

## Batch `batch7` — WPWB top-quintile portfolio selector (registered 2026-09-30, before running)
At every Friday cut: score each menu1 variant = sum R / sqrt(count) over trades exited in the last
L weeks (count >= 10, >= 10 variants eligible); trade every variant in the top 20 % during the
coming week. L in {26, 52} x {all top 20 %, only those with score > 0}: 4 candidates. Control =
equal-weight menu average that week. Same gates in R units.

### Result `batch7` (4 candidates; cumulative 2,883)
DISC pass 0 (the score > 0 filter never bit: top-20 % scores were always positive, so _pos = plain).
TOPQ_L52: 10,782 trades in 604 weeks, net +3.3 bp, **+0.047 R per trade, about +42 R per year,
t_R 2.18, excess over the menu t_R 2.97, 92 % of years positive**. TOPQ_L26 +0.038 R, t_R 1.83.
Not nominated: Amendment 2 needs excess t_R >= 3.0 and 2.97 is below it; not re-run for a luckier
control seed. Diagnosis: 10,782 trades collapse to ~600 weekly clusters; variants that fire often
(many near-duplicate continuation variants) dominate the per-trade weighting and their trades in a
week move together.

## Batch `batch8` (registered 2026-09-30, before running)
Equal risk per selected variant per week (one unit = mean R of a variant's trades in that week):
TOPQ_L52_EW, TOPQ_L104_EW, and TOPQ_L104 per trade. 3 candidates, same gates.

### Result `batch8` (3 candidates; cumulative 2,886)
DISC pass 0, but equal risk per variant per week lifted the statistic: **TOPQ_L52_EW 4,238
variant-weeks, +0.063 R, t_R 2.79, excess over the menu t_R 4.07, 100 % of the 12 DISC years
positive, ~+22 R/yr**; TOPQ_L104_EW t_R 2.78 / excess 3.98; TOPQ_L104 per trade t_R 2.39.

## Nomination 2 (Amendment 2, registered 2026-09-30, before its VAL score is seen)
TOPQ_L52_EW (menu1, top 20 % by trailing-52-week score, equal risk per selected variant per week,
reselected every Friday cut). Chosen over L104_EW as the shorter memory with the same DISC evidence.

### Result nomination 2
VAL **FAIL** (M = 7, threshold p < 0.0071): 2015-20 2,246 variant-weeks, net +1.9 bp, **+0.030 R,
t_R 0.97**, p 0.17, 4 bp stress -0.1 bp, 50 % of years positive, ~+11 R/yr. But the selection
edge survives out of sample: **excess over the menu +0.045 R, t 2.09**. First candidate whose net
stays above zero in VAL.
Diagnosis: choosing works in both eras; the menu average after costs is below zero, so the top
group is only slightly positive in 2015-20. CLAUDE.md: NO TRADE when the edge is unclear - so
hold a variant only if its own trailing score clears an absolute bar.

## Batch `batch9` (registered 2026-09-30, before running)
TOPQ_L52_EW plus an absolute bar: of the top 20 %, keep only variants with trailing score
(sum R / sqrt n, last 52 weeks) >= s; if none, NO TRADE that week. s in {1.5, 2.0, 3.0}: 3 candidates.

### Result `batch9` (3 candidates; cumulative 2,889)
DISC pass 0. An absolute bar hurts: s 1.5 t_R 2.02, s 2.0 t_R 1.06, s 3.0 t_R -0.08. The hottest
variants do not keep winning; the information is in the rank, not the level of the score.

## Batch `batch10` (registered 2026-09-30, before running)
Menu `menu2` = menu1 + 6 longer-hold continuation variants (SHOCK_CONT k2/k3 hold 24/48 h, MOM
L6/L12 hold 4L, stop 3 ATR) + the mirror (opposite direction, same timing, stop and hold) of every
variant, so the selector can fade what is failing. Candidates: TOPQ_L52_EW and TOPQ_L104_EW on
menu2 (2).

### Result `batch10` (2 candidates; cumulative 2,891)
DISC pass 0. menu2 L104_EW: 9,439 units, +0.060 R, t_R 2.53, excess t_R 3.79, 83 % of years, ~+47 R/yr;
L52_EW t_R 1.68. The mirrors roughly double the menu (109 distinct champions used).

## Nomination 3 (Amendment 2, registered 2026-09-30, before its VAL score is seen)
TOPQ_L104_EW on menu2 (DISC t_R 2.53, excess t_R 3.79, net +4.9 bp).
