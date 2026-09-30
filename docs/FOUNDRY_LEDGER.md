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

### Result nomination 3
VAL **FAIL** (M = 8, p < 0.00625 needed): 2015-20 4,670 units, net +2.35 bp, **+0.026 R, t_R 0.90**,
p 0.18, 50 % of years, ~+20 R/yr; **excess over the menu +0.055 R, t 2.29** (second time the
selection edge survives out of sample).
Diagnosis: choosing adds about +0.05 R over the menu in both eras; the menu's average after costs
is about -0.03 R in 2015-20. Cost (2 bp) is a large share of R for narrow-stop intraday variants.

## Batch `batch11` (registered 2026-09-30, before running)
Menu `menu3` = menu2 filtered by a cost rule only: median stop >= 100 bp (cost <= 2 % of R).
26 variants (D1 trend/channel/RSI2/turn-of-month, weekly and prior-day breaks, with mirrors).
Because these trade rarely, the score needs >= 5 trades (not 10) in the lookback. Candidates:
TOPQ_L52_EW, TOPQ_L104_EW on menu3 (2).

### Result `batch11` (2 candidates; cumulative 2,893)
DISC pass 0: the cost-filtered D1/weekly menu carries no selection information (t_R 0.79-0.90,
excess t 0.83-0.85). Selection information lives in the intraday variants.

## Batch `batch12` (registered 2026-09-30, before running)
WPWB-conditioned ranking: TOPQ_L104_EW on menu2, scoring each variant only on trades from past
weeks with the same WPWB volatility class as the coming week (CALM / NORMAL / HIGH). 1 candidate.

### Result `batch12` (1 candidate; cumulative 2,894)
DISC pass 0. WPWB-conditioned ranking = unconditioned: t_R 2.56, excess t 3.76, +0.057 R, ~+42 R/yr.
Knowing the week's volatility class does not improve which tools to pick.
Diagnosis: selection alpha ~ IC x sqrt(breadth); menu2 is ~120 variants but many near-duplicates.
More independent variants, including ones whose edge is known to switch on and off with the era
(hour of day decayed after 2015, Part 49), are what a selector can exploit.

## Batch `batch13` (registered 2026-09-30, before running)
Menu `menu4` = menu2 + 48 hour-of-day variants (enter at the open of UTC hour h, hold 4 h, stop
2 ATR, long and short) + 10 day-of-week variants (D1, one day, long and short). Candidates:
TOPQ_L52_EW, TOPQ_L104_EW on menu4 (2).

### Result `batch13` (2 candidates; cumulative 2,896)
DISC pass 0. menu4 L104_EW: 15,612 units, +0.048 R, t_R 2.73, **excess t_R 4.40**, 83 % of years,
~+62 R/yr; L52_EW t_R 1.79 / excess 3.74. Breadth raised the excess t (3.79 -> 4.40).

## Nomination 4 (Amendment 2, registered 2026-09-30, before its VAL score is seen)
TOPQ_L104_EW on menu4.

### Result nomination 4
VAL **FAIL** (M = 9, p < 0.0056 needed): 2015-20 7,405 units, net +2.88 bp (stress +0.88),
**+0.027 R, t_R 1.26**, p 0.10, 67 % of years, ~+33 R/yr; **excess over the menu +0.059 R, t 3.26**.
The selection edge is now confirmed out of sample three times (t 2.09, 2.29, 3.26). What keeps net
small is cost: the menu averages ~0 gross, and 2 bp (twice Exness's ~1 bp) is ~0.03 R at the median
stop. The cost assumption is not relaxed.
Diagnostic (DISC only): future 4-week mean R by trailing-104-week decile on menu4 rises from
-0.112 (D1) to +0.035 (D9) and **+0.084 (D10)** - the top decile carries more than the top quintile.

## Batch `batch14` (registered 2026-09-30, before running)
Sharper selection on menu4, L104, equal risk per variant-week: top 10 % and top 5 %. 2 candidates.

### Result `batch14` (2 candidates; cumulative 2,898)
**First DISC pass of a selector: TOP5_L104_EW** (3,916 units, +0.088 R, t_R 3.16, excess t 4.18,
100 % of years) -> **VAL FAIL** (M = 10): 2015-20 +0.020 R, t_R 0.59, p 0.28, excess +0.049 R t 1.62.
TOP10_L104_EW DISC t_R 2.75. Sharper selection helps in DISC but not out of sample; VAL net stays
at +0.02..+0.03 R for every selector tried.
Diagnostic (DISC only) of the nomination-4 selector by WPWB class: CALM weeks +0.024 R (t 0.68),
NORMAL +0.062 (t 2.17), HIGH +0.065 (t 1.93).

## Batch `batch15` (registered 2026-09-30, before running)
WPWB overlay: TOPQ_L104_EW on menu4 traded only in weeks WPWB forecasts NORMAL or HIGH (stand
aside in CALM). 1 candidate.

### Result `batch15` (1 candidate; cumulative 2,899)
DISC pass 0 but close: TOPQ_L104_EW_NOTCALM 10,757 units, +0.063 R, **t_R 2.89**, excess t 3.86,
91 % of years, ~+62 R/yr.

## Nomination 5 (Amendment 2, registered 2026-09-30, before its VAL score is seen)
TOPQ_L104_EW_NOTCALM on menu4. Note: nomination 4 (same selector, all weeks) was already seen in
VAL; this subset has not been, and it counts as a new VAL look (M = 11).

### Result nomination 5
VAL **FAIL** (M = 11, p < 0.0045 needed): 2015-20 6,963 units, net +3.57 bp (stress +1.57),
**+0.034 R, t_R 1.48, p 0.069**, 67 % of years, ~+39 R/yr; excess +0.063 R, t 3.32.
Status summary for the operator: `docs/FOUNDRY_STATUS.md`.

## Batch `batch16` (registered 2026-09-30, before running)
Menu `menu5` = menu4 + a copy of every H1 variant held 4x longer with a 1.5x wider stop and no
target (cost becomes a smaller share of R; the selector decides which horizon is working).
Candidate: TOPQ_L104_EW_NOTCALM on menu5 (1).

### Result `batch16` (1 candidate; cumulative 2,900)
DISC pass 0: menu5 TOPQ_L104_EW_NOTCALM t_R 2.75, excess t 3.24, +0.069 R - no gain over menu4.
Not nominated (a near-duplicate of nomination 5 would only raise M). Note on units: "R per year"
grows with the number of variants held at once and is not a portfolio number; the clustered t over
weeks is. t 2.9 over 411 DISC weeks ~ annual Sharpe 1.0; t 1.48 over 294 VAL weeks ~ 0.6.

## Batch `batch17` (registered 2026-09-30, before running)
Ranking stabilised: each variant's trailing mean R shrunk toward its family's mean (k = 50 trades),
ranked separately for L = 52, 104, 156 weeks, ranks averaged; hold the top 20 % in NORMAL/HIGH
weeks, equal risk per variant-week, menu4. 1 candidate.

### Result `batch17` (1 candidate; cumulative 2,901)
DISC pass 0: shrunk multi-lookback ranking t_R 2.71, excess t 3.61 - no gain. Every selector variant
plateaus at DISC t 2.7-2.9 / VAL t 1.3-1.5.

## Batch `batch18` — WPWB forecast-scaled weekly OCO (registered 2026-09-30, before running)
Uses WPWB's own output directly. At each Friday cut, s = sqrt(B0 EWMA forecast of the week's RV);
C = open of the week's first H1 bar; buy stop at C(1 + k s), sell stop at C(1 - k s); first touch
wins (both in one bar: skip); stop back at C (distance k s) or at the opposite level (2 k s); exit at
the week's last bar. k in {0.25, 0.5, 1.0} x stop {C, opposite}; cells ALL, NOTCALM/*, HIGH/*; both
directions only. 18 candidates.

### Result `batch18` (18 candidates; cumulative 2,919)
DISC pass 0. WPWB forecast-scaled weekly OCO is flat: best t_R 0.93 (k 0.5, stop at C, HIGH weeks),
ALL cells -0.8..+0.8. Weekly horizon: no directional information, as the regime atlas found.

## Batch `batch19` — WPWB pace-compression breakout (registered 2026-09-30, before running)
Registry trace S6 (intraweek RV vs forecast pace). Checkpoint Tue or Wed 22:00 UTC; pace = RV so far
/ (B0 forecast x elapsed share of ~115 H1 bars); if pace < 0.6 or < 0.8, OCO stops at the last close
+/- k x the forecast's remaining weekly sigma (k 0.25 / 0.5), first touch wins, stop back at the
reference, exit at week end. 8 candidates, cell ALL, both directions.

### Result `batch19` (8 candidates; cumulative 2,927)
DISC pass 0; pace-compression breakouts are flat (t_R -0.7..+0.8). Knowing that the rest of the
week should be more volatile does not say which way.
Meta-diagnosis after 19 batches: two structures survive in this data - volatility clustering
(forecastable, not tradeable on spot without options) and cross-sectional persistence of setup
performance (+0.05 R selection edge, confirmed out of sample, net too thin after cost). Session
structure (NY morning continuation +, late session -) is the one remaining source of genuinely
different menu variants.

## Batch `batch20` (registered 2026-09-30, before running)
Menu `menu6` = menu4 + session-split copies (ASIA / LONDON / NYAM / LATE / OPEN, >= 100 trades)
of every continuation and breakout H1 variant, with mirrors. Candidate: TOPQ_L104_EW_NOTCALM (1).

### Result `batch20` (1 candidate; cumulative 2,928)
DISC pass 0: menu6 (414 variants) TOPQ_L104_EW_NOTCALM t_R 2.68, excess t 3.55 - breadth no longer helps.

## Batch `batch21` (registered 2026-09-30, before running)
Sizing inside WPWB's weekly risk frame: the nomination-5 selector (menu4, L104, top 20 %, NORMAL/HIGH
weeks) with a FIXED risk budget per week split equally over every selected variant-week unit (the
week's return = mean R of its units). 1 candidate.

### Result `batch21` (1 candidate; cumulative 2,929)
DISC pass 0: fixed weekly risk budget t 2.55 over 411 weeks (annual Sharpe ~0.9), excess t 3.95.
Sizing does not change the size of the edge.

## Batch `batch22` — continuation with trailing stops (registered 2026-09-30, before running)
Continuation profits come from a fat right tail that fixed holds cut off. Entries of CONT_UNION_h6,
SHOCK_CONT k2/k3 h6, MOM L6/L12 z1.5, PDHL_BRK, ASIA_BRK_t0; exit by an initial 2 ATR stop that
ratchets to (best extreme so far - m ATR), m in {2, 3}, max 120 h; overlapping positions allowed
(each trade 1R); cells ALL, NOTCALM/*, HIGH/*; both directions. 14 specs x 3 cells = 42 candidates.

### Result `batch22` (42 candidates; cumulative 2,971)
DISC pass 0. Trailing stops are worse than fixed holds: best t_R 1.94 (MOM_L6 trail 3 ATR); trail 2
ATR is negative for most. H1 gold continuation is a few-hour effect, not a trend to ride.

## Batch `batch23` (registered 2026-09-30, before running)
CONT_UNION_h6 and MOM_L6_z1.5 entries split by agreement with the D1 trend (previous completed
day's close vs its SMA50): WITH / AGAINST; cells ALL, NOTCALM/*; both directions. 8 candidates.

### Result `batch23` (8 candidates; cumulative 2,979)
DISC pass 0. D1-trend alignment changes nothing (WITH t_R 1.73-1.79, AGAINST 1.44-1.88).

## Forward shadow of the best tool (2026-09-30)
Historical periods are exhausted or sealed, so the best WPWB-native tool (nomination 5) is now
logged forward every Friday, paper only: `docs/FOUNDRY_SHADOW_PREREG.md`,
`research/foundry/selector_shadow.py`. Dry run for the week of 2026-09-25: NORMAL, 36 variants
selected, mostly long/trend (long bias after the 2024-26 rally, stated in the prereg).
Engine change (no effect on earlier results): the regime grid now includes the next cut after
the data so the coming week's class exists at a cut.

## Batch `batch24` (registered 2026-09-30, before running)
Two selector variants on menu4, L104, top 20 %, equal risk per variant-week, NORMAL/HIGH weeks:
(a) rank by R at the 4 bp stress cost (penalises cost-heavy variants); (b) hold each selection for
4 weeks (IC is higher at 4-13 week horizons). 2 candidates.

### Result `batch24` (2 candidates; cumulative 2,981)
DISC pass 0: stress-cost ranking t_R 2.81, 4-week hold t_R 2.74. Plateau confirmed.
Meta: a next VAL look needs p < 0.05/12 (t ~ 2.64 in 2015-20) while every selector gives t 1.3-1.5
there; further selector tweaks are DISC descriptives only, not routes to a pass.

## Batch `batch25` — information not used before (registered 2026-09-30, before running)
(1) Volume: CONT_UNION_h6, SHOCK_CONT_k2_h6, MOM_L6_z1.5 split by the signal bar's tick volume
relative to its usual level at that hour (>= 1.5x VOLHI, < 1.0x VOLLO). (2) Liquidity: an H1 bar
opening with spread > 3x its usual level at that hour and moving > 0.5 ATR -> follow or fade next
bar, hold 3 h. (3) GVZ: GVZ up > 10 % on the day (row dated two days before the D1 bar, conservative)
-> follow or fade gold's previous-day move, hold 1 / 3 days. Cells ALL, NOTCALM/*; both directions.
12 specs, 24 candidates.

### Result `batch25` — INVALID (look-ahead bug), and a second bias found by the new leak test
GVZ_JUMP_FOLLOW passed DISC, VAL and HOLD (+80..+160 bp per trade, t_R 4-10). Implausible, so
audited: **the trade direction was the sign of the ENTRY day's own close-to-close move** (a
look-ahead in my code; direction matched the same-day sign 100 %). The result is void. The two HOLD
looks it consumed stay spent (state hold_looks = 2), so the next HOLD alpha is 0.05/8.
Volume and spread-shock rows of batch25 were valid and all failed DISC (VOLHI vs VOLLO no difference).
New tool: `research/foundry/leak_test.py` - garbages every H1 value from bar j on (keeping bar j's
open), rebuilds D1, and requires identical entries up to j, with cut points placed AT real entries.
It flagged GVZ_JUMP and also **NR7, WPWB_OCO and PACE_BRK**: these stop-entry families skipped a
trade when one bar touched both levels. A real resting OCO would have filled one side and usually
been stopped in that bar, so skipping removed losers - an optimistic bias (it likely inflated NR7's
batch1 DISC t 4.9). Fix: both touched -> the side nearer the bar's open, then stop-first. After the
fix every family generator of batches 1-25 and menu4 passes the leak test. Consequence: NR7 results
of batch1, and every menu4 selector result (NR7 variants were among the champions), were optimistic;
they are re-run below as corrections, counted as new candidates.

## Corrections registered 2026-09-30 (before running)
`batch1nr7fix` (NR7_t1/t2 corrected, cell ALL, both/long/short) and `batch25b` (GVZ_JUMP with the
previous day's move, cells ALL, NOTCALM/*, both directions). Then the nomination-5 selector recomputed
on the corrected menu4 (DISC and VAL; the VAL recomputation is counted as a new VAL look).

### Results of the corrections
- `batch1nr7fix`: NR7_t1 both DISC t_R 4.53 (was t_net 4.00) -> VAL fail again (-0.001 R, p 0.51);
  NR7_t2 VAL +0.011 R, p 0.44 (M = 15). The skip bias was not what made NR7 look good in 2003-14.
- `batch25b` (GVZ jump, corrected): DISC pass 0; FOLLOW_h1 t_R 1.25, FADE negative. No GVZ-jump effect.
- Nomination-5 selector on the corrected menu4: DISC +0.062 R, t_R 2.81 (was 2.89); VAL +0.033 R,
  t_R 1.47, p 0.070 (M = 16), excess t 3.32 - effectively unchanged. The bias was small for the selector.

## Batch `batch26` (registered 2026-09-30, before running; leak test now mandatory in run_batch)
INSIDE_DAY and NR4 compression OCO (next-day stop entries at the day's high/low, target 1R/2R,
both-touch rule as fixed), LONDON_CLOSE_FADE (at 16:00 UTC fade the 07:00-16:00 move if > 1 ATR x
sqrt(9), exit 20:00), FRIDAY_FADE (Friday 14:00 fade of 07:00-14:00 move > 1 ATR x sqrt(7), exit
20:00), NFP_CONT (first Friday, follow the 12:00-14:00 UTC move > 0.5 ATR at 14:00, hold 4 h),
MONDAY_GAP_CONT (weekend gap > 1 ATR, follow, hold 12 h). Cells ALL, NOTCALM/*, HIGH/*; both. 24.

### Result `batch26` (21 candidates; cumulative 3,036)
Compression breakouts pass DISC strongly and die in VAL: NR4_t1 NOTCALM t_R 4.60 (91 % of years)
-> VAL +0.007 R p 0.43; NR4 ALL t_R 4.17 -> VAL p 0.45; INSIDE_DAY HIGH t_R 3.1-3.2 (not reached
VAL, max 20 per batch - 4 NR4 were first). Session fades, NFP continuation, Monday gap: DISC fail.

## Current-era test 1 (Amendment 3, registered 2026-09-30, before its HOLD number is seen)
NR4_t1, both directions, cell NOTCALM/* (highest DISC t_R of the batch). HOLD look 3, alpha 0.00625.

### Result current-era test 1
HOLD **FAIL**: NR4_t1 NOTCALM 2021-26 343 trades, net -2.95 bp, -0.003 R, t_R -0.08, p 0.53
(alpha 0.00625, look 3). Compression breakouts were a 2003-14 phenomenon; the current era is not a
repeat of it for this family. Next HOLD alpha 0.003125.

## Track B batch `trackB1` (registered 2026-09-30, before running; FOUNDRY_TRACK=B)
Every family built so far (menu4 176 variants + batch26 + corrected GVZ jump) re-discovered on
2015-20, cells ALL / NOTCALM/* / HIGH/*, both directions (mirrors cover the other side).

### Result `trackB1` (531 candidates, Track B cumulative 531)
DISC (2015-20) pass 0. Only 32 % of candidates have net R > 0; 5 of 474 have t_R > 2. Best:
HOD_21L (long 21:00-01:00 UTC) NOTCALM t_R 3.30, 100 % of years, but excess ~0 - see below.
Mean reversion is negative in this era too (BB_REV t_R -4.4).
**Design flaw found:** for time-defined variants (HOD, DOW, TOM) the matched control is drawn from the
same hour/weekday, i.e. it IS the variant, so excess ~ 0 by construction and they can never pass.
Correction: time-defined variants get a time-free control (same year x regime cell, same direction,
stop and hold). Earlier Track A batches used HOD/DOW only inside selector menus (whose control is the
menu average), so no earlier gate decision is affected.

## Track B batch `trackB2` (registered 2026-09-30, before running)
HOD (48), DOW (10), TOM long/short and their mirrors re-scored with the time-free control; cells ALL,
NOTCALM/*, HIGH/*; both.

### Result `trackB2` (182 candidates; Track B cumulative 713) - FIRST FULL PASS, under audit
**HOD_21L, NOTCALM/*** (long at the 21:00 UTC H1 open, hold 4 h to the 00:00 bar's close, stop 2 ATR,
only in weeks WPWB forecasts NORMAL or HIGH):
| stage | period | trades | net bp | net R | t_R | p | gate |
|---|---|---|---|---|---|---|---|
| DISC | 2015-20 | 536 | +4.91 | +0.084 | 3.30 | - | pass (excess t 3.09, 100 % of years) |
| VAL | 2021-23 | 225 | +3.95 | +0.080 | 2.98 | 0.0014 | pass (M = 1, needs < 0.05) |
| HOLD | 2024-26 | 208 | +9.89 (4 bp: +7.89) | +0.142 | 3.03 | 0.0012 | pass (look 4, alpha 0.003125) |
Consistent with Part 49 (overnight / Asian hours 21-04 UTC positive in 2003-15). NOT yet accepted:
the cost model has **no swap**, and every trade holds across the daily rollover (Exness long swap
-$0.5493/oz/night measured, triple on Wednesday, ~1.2 bp at $4,600, ~4 bp at $1,300); Part 50 found
the all-hours rule did not replicate on Exness 2021-26; whether a 21:00 UTC bar is tradable at the
broker all year is unchecked. Audit script: `research/foundry/check_hod21.py` (broker hours and
spreads, swap-adjusted results, adjacent hours 18-00, per-year, and a replication on the live Exness
feed with ask entry / bid exit and $0.10 slippage per fill).

### Audit of HOD_21L (2026-09-30) - the pass is WITHDRAWN
`research/foundry/check_hod21.py`, `check_hod21_swap.py`:
1. **Broker hours:** Exness has a 21:00 UTC bar only Nov-Mar (418 of ~1,350 per other hour): in US
   daylight time 21:00 UTC is the daily break. The rule is really "long in the last hour before the
   daily break (16:00 New York) into the Asian open", winter only.
2. **Swap was missing from the cost model.** Every trade holds across the rollover. With an era swap
   (US 2y yield + markup calibrated to today's measured $0.5493/oz/night; x3 Wednesday):
   DISC 2015-20 +4.35 bp, +0.071 R, t_R 2.81 (below the DISC bar 3.0); VAL 2021-23 +2.93 bp, t_R 2.31,
   p 0.010 (would pass); HOLD 2024-26 +8.35 bp, +0.117 R, t_R 2.47, p 0.0068 > alpha 0.003125 -> FAIL.
3. **Adjacent hours** do not agree: 22, 23, 00 UTC negative in all eras; 19-20 UTC positive only 2024-26.
4. **Per year** (Dukascopy, pre-swap): 2004-14 around zero, then positive every year 2015-2026.
5. **Vendor replication on the live Exness feed** (ask entry, bid exit, $0.10 slippage per fill,
   2 ATR stop, NOTCALM, swap): 301 trades 2021-26, +2.88 bp, +0.028 R - but by year +1.1, **-11.6
   (2022)**, +3.4, +1.2, +2.7, +26.4 (2026 partial): excluding 2026 it is about zero.
Verdict: not a tool. Kept as a paper forward record HOD21-SHADOW-1 (zero alpha).
Protocol Amendment 5 (below): swap is part of cost for any position held across the daily rollover.

## Engine: swap now in every gate (Amendment 5), for candidates and their controls and selector menus.

## Track B batch `trackB3` (registered 2026-09-30, before running) - CONTAMINATED hypothesis, stated
Economically motivated (Asian physical demand vs Western selling) but **informed by Part 49's hour
map and by the HOD_21L audit**, so its DISC/VAL/HOLD numbers are not clean evidence; the forward
record would be. OVERNIGHT_LONG: long at the 16:00 New York H1 bar open (DST-aware), exit at the close
of the bar before 08:00 London, stop 3 ATR. INTRADAY_SHORT: short 08:00 London -> close of the 15:00
New York bar, stop 3 ATR. Plus mirrors. Time-free control, swap included. Cells ALL, NOTCALM/*, HIGH/*.

### Result `trackB3` (12 candidates; Track B cumulative 725)
DISC pass 0. OVERNIGHT_LONG (16:00 NY -> London open) +0.00 R, t_R 0.14; INTRADAY_SHORT -0.04 R;
mirrors negative. The broad "Asia up / West down" split is absent in 2015-20 after swap, so HOD_21L's
effect is confined to the one pre-break winter hour - more likely a microstructure quirk of that bar
(or luck) than an overnight-demand pattern.

## Track B batch `trackB_sel1` (registered 2026-09-30, before running)
The WPWB Champion/Challenger selector TOPQ_L104_EW_NOTCALM on menu4 (swap now included) judged on
Track B periods: DISC 2015-20 (this period was Track A's VAL, already seen for the same selector
without swap: +0.033 R, t 1.47), VAL 2021-23, HOLD 2024-26. 1 candidate.

### Result `trackB_sel1`
DISC (2015-20, with swap) +0.032 R, t_R 1.39, excess t 3.31: not eligible for nomination (t_R < 2).

## Current-era test 2 (Amendment 3, registered 2026-09-30, before any number is seen)
TOP5_L104_EW (menu4, top 5 %, equal risk per variant-week; Track A batch14 full DISC pass before
swap, VAL fail). Condition: it must still pass the full DISC gate after swap (Amendment 5); only then
one HOLD look (Track A HOLD 2021-26) at the next alpha (look 5, 0.0015625).

### Result current-era test 2 - HOLD FAIL, and the selection edge is gone in 2021-26
DISC after swap still a full pass (+0.088 R, t_R 3.14, excess t 4.18, 100 % of years). HOLD 2021-26
(look 5, alpha 0.0016): 1,658 units, net -4.7 bp, **-0.053 R, t_R -1.54, 1 of 6 years positive,
excess over the menu -0.011 R (t -0.34)**. The cross-sectional persistence that held in 2003-14 and
2015-20 is absent in 2021-26. Consequence for SELECTOR-SHADOW-1 (top 20 % version, forward paper):
its expected forward value is now low; it stays as a paper record (it costs nothing) but is no
longer "the best candidate".
Budget: 5 HOLD looks spent (0.025 + 0.0125 + 0.00625 + 0.003125 + 0.0015625 = 0.0484). The next
look would need p < 0.00078 (t ~ 3.2). Historical confirmation is effectively exhausted; from here
history can only nominate, and confirmation must come from forward weeks.

## Forward panel frozen (Amendment 6, 2026-09-30) - H-FOUNDRY-PANEL-1, alpha 0.01
440 variant-cells scored on the last 104 weeks (to 2026-08-31, after cost and swap); only 32 were
positive in both the recent window and 2021-01..2024-08. Panel (top t_R, distinct families):
INSIDE_DAY_t2 NOTCALM (+0.31 R, t 3.00, check +0.10), HOD_21L ALL (+0.13, t 2.24, check +0.06),
SHOCK_CONT_k2_h48~INV ALL (fade after a > 2 ATR bar for 48 h; +0.18, t 1.44, check +0.16),
ASIA_BRK_t2 ALL (+0.05, t 1.22, check +0.01), NR7_t2 ALL (+0.10, t 1.06, check +0.07).
These historical numbers are nominations, not evidence (440 tries). Confirmation: e-process >= 500
per candidate on forward weeks from 2026-10-02. Hooked into the Saturday job.

## Corrections after Codex round 12 (2026-09-30)
- **batch26 entry was wrong (R12-8):** INSIDE_DAY did reach VAL (8 candidates went, M = 24):
  INSIDE_DAY_t2 HIGH/* 52 trades +7.7 bp, R +0.069, t_R 0.57, p 0.29; INSIDE_DAY_t1 HIGH/* +0.073 R,
  t_R 0.71, p 0.24 - both FAIL. The forward panel's INSIDE_DAY nomination therefore follows a seen VAL
  failure (2015-20); stated here.
- **Overstatements withdrawn (R12-14):** "the timing information is real" (batch4) is a discovery-sample
  statement after thousands of trials, not an established fact; "the selection edge confirmed out of
  sample three/four times" refers to related selector variants repeatedly adapted and scored on the
  same 2015-20 block - not independent confirmations - and the edge was absent in 2021-26 (current-era
  test 2).
- **All historical p-values are approximate (R12-6)** and Track B / current-era results are exploratory
  (R12-7).
- **HOD_21L after the exit-bar fix and DST swap:** on Dukascopy the last-104-week number fell from
  +0.130 R (t 2.24) to +0.033 R (t 1.08): part of the earlier result came from Friday 21:00 entries
  that spanned the weekend under the old i+3 rule. On the Exness feed with the 00:00 exit, 2021-26 by
  year: -1.9, -5.8, +1.0, +0.3, +2.2, +14.2 bp (2026 partial).
- **Forward panel re-frozen** with the corrected code (same rule, same 440 variant-cells; 31 positive in
  both windows): INSIDE_DAY_t2 ALL (+0.307 R, t 2.98), SHOCK_CONT_k2_h48~INV ALL (+0.177, t 1.44),
  ASIA_BRK_t2 ALL (+0.046, t 1.12), HOD_21L ALL (+0.033, t 1.08), NR7_t2 ALL (+0.102, t 1.04).
  Nominations only; e-process lambda 0.1; forward from 2026-10-02 22:15 UTC.

## Diagnostics after the panel (no gate, no alpha)
- `cost_share.py` (last 104 weeks): 47 % of variants have gross R > 0, 29 % net R > 0; cost is ~0.03 R
  and swap ~0.002 R at the median. The gross-positive list is dominated by LONG hour-of-day variants -
  gold's 2024-26 rally, not setup timing. A limit entry would save at most ~0.015 R.
- `gross_consistency.py`: 17 of 169 variants have gross R and excess > 0 in all three eras 2015-20,
  2021-23, 2024-26 - fewer than the ~21 a coin flip per era would give. Standouts with net > 0 in all
  three: SHOCK_CONT_k2_h48~INV (+0.04 / +0.13 / +0.20 R: fade a > 2 ATR H1 bar for 48 h),
  SHOCK_CONT_k3_h48~INV, INSIDE_DAY_t1/t2, NR7_t2 - three of these are already in the forward panel.

## Shock-fade surface and forward panel 2 (2026-09-30)
`research/foundry/shock_fade_surface.py` (descriptive; 60 grid points k 1.5-3.0 x hold 12-72 h x stop
2-4 ATR, clock-based holds): only 15 % of points are net positive in all of 2015-20, 2021-23, 2024-26
(about what chance gives), and the panel-1 variant SHOCK_CONT_k2_h48~INV changes sign under the
clock-hold definition - fragile. One contiguous ridge: k 2.5-3.0 with a 72 h hold is positive for every
stop in both 2021-23 (+0.15..+0.21 R) and 2024-26 (+0.10..+0.44 R), ~0 in 2015-20, negative in 2003-14:
a recent-era pattern (big H1 shocks revert over ~3 days). Its centre SHOCK_FADE_k2.5_h72_s3.0 was frozen
as forward panel 2 (H-FOUNDRY-PANEL-2, alpha 0.005, threshold 200), with its own code snapshot.

## What panel 2 really is (descriptive, seen data) - 2026-09-30
`shock_fade_mechanism.py` (2022-26): non-news shock bars revert (+0.31 R, n 149), shocks containing a
HIGH USD release do not (+0.05 R, n 64); the fade of DROPS (buy) earns +0.44 R, the fade of SPIKES
(sell) +0.01 R. Panel 2 is mainly **buying sharp non-news dips in a bull market**.
`dip_by_trend.py` / `dip_up_excess.py`: BUY_DIP in WPWB UP-trend weeks is net positive in all four eras
2003-08 / 09-14 / 15-20 / 21-26 at k = 2 (+0.20 / +0.16 / +0.10 / +0.29 R), but against random LONG
entries in the same UP weeks the excess is small: k 2.0 +0.13 R (t 1.45), k 3.0 +0.27 R (t 1.96),
negative in 2003-08 (when any long in an up week earned +0.26 R). 18 side x trend x k rows were
inspected, so one all-era-positive row is roughly what chance gives. SELL_SPIKE in DOWN weeks is
inconsistent. Reading: gold's up-trend drift plus mild dip reversion since 2015; no new panel.

## Forward portfolio (Amendment 10) - H-FOUNDRY-PORTFOLIO-1, alpha 0.01, threshold 100
`panel_portfolio_check.py` (seen data 2021-26): equal-risk portfolio of the six candidates +0.085 R per
week, annual Sharpe 1.33 (optimistic, the candidates were picked on these years); ~250 forward weeks
to a 2.9-sigma result if that held. Alpha ledger now: panels 0.01 + 0.005, portfolio 0.01, reserve 0.025.

## Re-freeze under Amendment 11 (after Codex round 13, 2026-09-30)
All forward records re-frozen with the valid clipped-mean mixture test, settle margins, full code
snapshots, hash-chained append-only files and exact-component portfolio aggregation. Same candidates:
panel 1 = INSIDE_DAY_t2, SHOCK_CONT_k2_h48~INV, ASIA_BRK_t2, HOD_21L, NR7_t2 (ALL cells); panel 2 =
SHOCK_FADE_k2.5_h72_s3.0; portfolio = the six. Hashes: `docs/FOUNDRY_FROZEN_MANIFEST.md`.

## Re-freeze under Amendment 12 (after Codex round 14, 2026-09-30)
Same six candidates and portfolio; settlement-window gap check, frozen-module binding, lockstep and
post-append validation, fail-closed portfolio, exact hashing, run-log-based LATE. Manifest re-issued.

## News proximity of the panel candidates (descriptive, 2022-26) - `news_proximity.py`
Pooled, trades starting 0-2 h after a HIGH USD release earn +0.149 R (n 478; mostly the shock / news fades,
which enter after releases by design), within 1 h before a release +0.071 R (n 124), away from releases
+0.062 R (n 1,799): no general harm near news. Breakouts entered in the hour BEFORE a release do worse
(ASIA_BRK_t2 -0.212 R n 56 vs +0.036 away; NR7_t2 -0.207 R n 15 vs +0.087): noted in the news playbook as
a weak protective rule, not applied to any frozen candidate.

## Random 1:1 baseline and the indicator zoo (operator request 2026-09-30; descriptive, nothing filtered)
- `random_1to1.py`: 240 random-entry 1:1 setups (direction LONG/SHORT/COIN x stop = target 0.5-3 ATR x
  hold 4-72 h x session). Net R > 0 over 2003-26 in 1 %. Gross R is ~0 for stops >= 1 ATR; at 0.5 ATR the
  simulator's conservative intrabar rule (a bar touching both levels = stop) makes gross -0.10 R
  (target-first bound +0.09 R) - tight stops are penalised by the simulator, for every setup equally.
  Cost is 0.03-0.16 R per trade (stop 3 -> 0.5 ATR).
- `indicator_zoo.py` / `zoo_wpwb.py`: 31 textbook indicators and candle patterns (SMA/EMA crosses, MACD,
  RSI14/RSI2, Stochastic, CCI, Williams %R, ROC, Aroon, Bollinger, Keltner, Donchian 20/55, ADX/DI,
  Parabolic SAR, Supertrend, Ichimoku TK and cloud, daily VWAP, OBV, Heikin-Ashi, engulfing, pin bar,
  inside bar), each FOLLOW and FADE x k 1/2 ATR x hold 24/72 h = 248 setups, 697,116 trades, all kept in
  `data/foundry/zoo_all_wpwb.xlsx` with era and WPWB-regime breakdowns next to random entries.
  Net R > 0 over 2003-26: 3 %; better than random: 46 %; better than random in all four eras: 22 (~16 by
  chance); net > 0 in all four eras: 0. By WPWB regime the share better than random is 42-55 % in every
  cell (coin flip); high-volatility cells lose less (-0.05 R vs -0.08 R) because ATR stops are wider
  relative to the fixed cost. Most consistent: RSI14 30/70 exit FADED (better than random in all four
  eras at every k and hold, +0.08 R vs random, net about 0), Stochastic/Williams %R OB-OS faded,
  Donchian 55 and Keltner breakouts followed - still net <= ~0.02 R after cost.

## RR 1:1 to 1:10 on everything (operator request 2026-09-30) - `zoo_rr.py`, `data/foundry/zoo_rr.xlsx`
2,604 indicator setups (31 indicators x FOLLOW/FADE x stop 1/2 ATR x RR 1, 1.5, 2, 3, 5, 7, 10 x hold
24/72/240 h) + 42 random, all kept. Best net R per trade rises with RR (1:1 +0.03, 1:3 +0.17, 1:10 +0.36
RSI2 FOLLOW 1 ATR 240 h, n 810, win 15 %), worst stays ~-0.2 to -0.25; the average goes from -0.07 (1:1)
to +0.01 (1:10) and the random baseline from -0.09 to -0.01. Cost is 0.06 R per trade on average at every
RR (it depends on the stop, not the target). At 1:10 most trades end on the 10-day time exit, so these are
really "stop + hold" trades; random 1:10/240 h swings -0.22..+0.26 R between eras, i.e. the high-RR rows
are dominated by a few large winners and are noisy. Setups net positive in all four eras: 113 of 2,604,
fewer than the ~163 a coin flip per era would give at 1:10's 53 % positive share - the best rows are the
upper tail of noise, not established edges.

## Multi-timeframe zoo x RR (operator request 2026-09-30) - `multi_tf.py`, `data/foundry/multi_tf.xlsx`
M5/M15/M30 on the Exness feed (2021-26), H1/H4/D1 on Dukascopy (2003-26); 31 indicators x FOLLOW/FADE x
stop 1/2 ATR x RR 1-10 x 2 holds = 7,420 setups + random, all kept. Cost per trade in R falls with the
timeframe: M5 0.26, M15 0.14, M30 0.09, H1 0.06, H4 0.03, D1 0.01; gross R before cost is ~0 on
M5-M30 (0.002-0.009) and small on H1-D1 (0.02-0.06). Share of setups net positive: M5 0 %, M15 4 %,
M30 13 %, H1 25 %, H4 41 %, D1 51 %. Best per TF: M5 -0.006 R (nothing positive), M15 +0.22, M30 +0.49,
H1 +0.34, H4 +0.94 (n 148), D1 +1.18 (n 61) - the largest numbers come from the smallest samples and
from 1:10 targets with long holds (D1 60 days over the 2003-26 gold rally). Worst per TF -0.33..-0.68 R.
Reading: below H1 the spread alone decides the result; on H4/D1 cost stops mattering but samples are
small and long holds mostly carry gold's drift.
