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

## Multi-TF inverted SL/TP (operator 2026-09-30: "กลับด้าน sl กับ tp สลับกัน", "เอา sl ที่ 1 r")
`INVERT=1 python research/foundry/multi_tf.py` -> data/foundry/multi_tf_inverted.{xlsx,png,log}. Same 7,420 setups + 120 random
rows as the multi-TF run; stop kept at k ATR (= 1 R), target = 1 R / RR (RR 1:1, 2:1, 3:1, 5:1, 10:1). All rows kept. Descriptive only.
- Win rate rises as the target shrinks (≈0.50 at 1:1 → ≈0.85 at 10:1, every TF) but net R falls monotonically on every TF;
  the average setup is negative at every TF x RR cell. Best at 10:1: D1 +0.071 R, H4 +0.041 R; M5-H1 no positive 10:1 setup.
- Gross R before cost is already negative on average (−0.02 to −0.04 R): the stop-first same-bar rule and 1 R losses outweigh
  the small targets. Cost per trade is unchanged (M5 0.263 R … D1 0.011 R) but at 10:1 it equals 2.6 targets on M5.
- Best rows overall are the 1:1 cells (D1 +0.23 R n 59, H4 +0.22 R n 135) - small samples, not tools.

## Era champions (operator 2026-09-30: "ต้องการหาตัวเต็งแต่ละยุค")
multi_tf.py now also writes n_<era>; both runs re-run (same seed). data/foundry/multi_tf_era_champions.xlsx: top 10 per TF x era
(n in era >= 30, normal + inverted pooled, inverted 1:1 dropped as duplicate) and how each era's picks did in the NEXT era.
- Era #1 in the next era: positive in 5 of 12 TF x era steps (H1 3/3 small: +0.07, +0.24, −0.08; H4 0/3: −0.43, −0.56, −0.59).
- Top 5% of an era, next era mean: M5 −0.13, M15 −0.07, M30 −0.04, H1 −0.01 to +0.02, H4 −0.05 to +0.06, D1 −0.10 to +0.16.
  Better than the all-setup mean every step, but mostly by picking cheap configs (SL 2 ATR, long hold): rank_corr is highest on M5
  (0.80) where cost dominates and lowest on H4/D1 (0.16-0.35) where cost is small - rank persistence = cost persistence.
- Era champions are almost all 1:10 / hold 240 bars = the highest-variance cells; winner's curse. Only D1 2015-20 -> 2021-26
  top 5% held up (+0.16, 82% positive), which coincides with the 2021-26 gold rally on long holds.

## WPWB walk-forward champion backtest (docs/WPWB_WALKFORWARD_PREREG.md + Amendment 1; operator 2026-09-30)
`research/foundry/wpwb_walkforward.py` -> data/foundry/wpwb_walkforward.{xlsx,png,log}. H1 2003-26, 2,232 shadow
candidates bar by bar (one position each, actual exits), weekly pick at the Friday cut from trades already closed,
WPWB vol_scale sizing. Leak check PASS. 20 rules, 1,131-1,156 weeks each.
- 9 of 20 rules lose money; best = 52-week LCB top 2: +0.047 R/trade, 5,533 trades, +183 R sized (+8.3 R/yr), weekly t 1.38,
  43.7% of weeks positive; by era +5 / +112 / +43 / +22 R (mostly 2009-14). 13-week MEAN top1 +0.054 R/trade (+83 R).
  4-week and SAME-CELL (WPWB regime-matched) rules are all negative (-0.03 to -0.07 R/trade).
- Pre-registered RANDOM-PICK null: every rule p 0.000, but the null loses ~-0.074 R/trade and trades twice as often -
  it measures exit-config cost, not selection skill (Amendment 1).
- SAME-EXIT-CONFIG null (reading of record): best p 0.041 (52 LCB top2), then 0.104, 0.159; none below 0.0025.
  Picking the indicator/direction adds nothing distinguishable from chance; the gain over random is the exit config
  (long hold, wide target).
- The NO TRADE gate (best score <= 0) never fired: with 2,232 candidates one always looks positive - a weakness of the
  rule, to fix before any forward use (require a margin over the same-config pool).
- Verdict: no rule nominated. Not added to any forward panel.

## WRWR system (WPWB renamed WRWR by the operator) - optimiser and weekly champions (2026-09-30)
Operator: "เมื่อย้อนหลังมาแล้วระบบต้องทำให้ได้กำไร" / "ผมต้องการตัวเต็งทุกสัปดาห์ตามหลักคิด wrwr".
`research/foundry/wrwr_optimize.py` -> data/foundry/wrwr_system.{xlsx,png}: 134,400 selector configurations over the cached
shadow trades (window 8-104 w, LCB z 0-2, min trades, top 1-5, NO TRADE margin, pool, WRWR sizing, equity filter,
skipped vol classes). No Grid/Martingale/averaging; sizes only shrink.
- Baseline (pre-registered 52w LCB top2) reproduced: +182.6 R, 8.2 R/yr, all eras positive, worst year -48.9 R, max DD 107 R.
- (1) WALK-FORWARD over configurations (each year uses the best config of the prior 4 years): -44.3 R over 2008-26
  (-2.3 R/yr), 42% positive years; +261 R in 2009-14 then -265 R (2015-20) and -193 R (2021-26). Choosing the selector
  from recent history does not carry forward.
- (2) IN-SAMPLE (hindsight, a curve fit): 14,411 configs positive in every era; best = 52w LCB z1, SL 2 ATR pool, top 5,
  equity filter (stand aside while the rule's own last 26 weeks are negative), no sizing: +896 R (40.5 R/yr), 0.123 R/trade,
  7,299 trades, max DD 123 R, worst year -55 R, 61% positive years; eras +231 / +280 / +259 / +126 R.
`research/foundry/wrwr_champions.py` (spliced Dukascopy + live Exness cache to 2026-09-28) -> data/foundry/wrwr_champions.xlsx,
wrwr_champion_now.md: every week's WRWR regime, vol_scale and champions for BASE and IS. Week of the 2026-09-25 cut:
NORMAL/FLAT, vol_scale 0.63; BASE trades ParabolicSAR_flip FOLLOW SL2 1:5 72h + MACD_signal_cross FOLLOW SL1 1:10 24h;
IS stands aside (its last 26 weeks are negative). Paper only.

## WRWR optimiser v2/v3 (operator 2026-09-30: "ดีไม่พอ", "เอา tf เล็ก m5/m15", "ผมอยากได้ข้อมูล 5 ปีและ 3 ปี")
Candidate caches now H1 + H4 + D1 (Dukascopy 2003-26) + M15 + M5 (Exness 2021-26), 2,232 each, leak check PASS each.
`wrwr_optimize3.py` (184,320 configs) -> data/foundry/wrwr_system_v3.{xlsx,png,log}. Numbers net of cost and swap.
- Full 2004-26: walk-forward over configs (year uses best of prior 4 years) +605 R (+31.8 R/yr, 63% positive years;
  eras +235 / +339 / -92 / +123). In-sample best +1,159 R (52w LCB z2, H1 pool, top 8, 13w equity filter, DD 128 R).
  Best return/DD in-sample: 78w LCB z2, SL 2 ATR pool, top 8, 26w equity filter: +823 R, DD 65 R, worst year -23 R, 70% positive years.
- Last 5 years (2021-09 .. 2026-08): pre-registered baseline -14.6 R (2 of 5 years positive); walk-forward over configs,
  calendar 2021-26: +123 R; in-sample only 544 configs positive in all five 52-week blocks, best +103 R (26w LCB z0.5,
  SL2ATR, top 5, skip HIGH weeks).
- Last 3 years (2023-09 .. 2026-08): baseline +29.7 R; walk-forward 2023-26 +105 R; in-sample best +280 R (52w LCB, H1,
  top 8, skip CALM, DD 90 R); best return/DD +126 R with DD 15 R (H4+D1 SL2 pool) but that configuration loses -85 R
  over 2004-26.
- M5/M15 pools on their own are not in any top-5 table; M15 appears only mixed with H1.

## WRWR compounding by timeframe (operator 2026-09-30: "Tf ไหนทำผลทาง finance ทบต้นได้ดีที่สุด")
`research/foundry/wrwr_compound.py` -> data/foundry/wrwr_compound.{xlsx,png,log}. Weekly compounding equity *= 1 + f x R_week,
f in 0.25-3% per trade; "best" = highest CAGR with max DD <= 30% over 144 selector settings per pool (in-sample).
| pool | best CAGR full 2004-26 | best CAGR 5y | best CAGR 3y | pre-registered rule at 1%: 5y / 3y CAGR |
|---|---|---|---|---|
| M5 (2021+) | 1.5% | 16.8% (DD 27%) | 29.6% | 16.8% / 29.5% (DD 30%) |
| M15 (2021+) | 0.5% | 4.1% | 30.8% | -50% / -42% |
| H1 | 8.7% (DD 29%, x6.4) | 14.2% | 24.7% | -6.8% / 5.2% |
| H4 | 3.3% | 19.2% | 55.7% (DD 25%, x3.8) | 7.8% / 27.1% |
| D1 | 2.7% | 17.9% | 40.1% | 1.7% / 2.6% |
| ALL 5 TF | 6.4% | 29.1% (DD 26%, x3.6) | 57.7% (DD 26%, x3.9) | 8.3% / 34.1% |
Best single TF recently = H4; over 2004-26 = H1; pooling all five TFs is best in every window. All "best" figures are
hindsight settings; pre-registered-rule figures are not tuned.

## Registered 2026-09-30 before running: M5/M15 unseen-history holdout (HistData 2009-03 .. 2020-12)
The M5/M15 caches so far cover Exness 2021-01..2026-09 only; every M5/M15 selector setting above was chosen on that span.
HistData M1 (2009-03..2020-12, New York time with DST -> UTC, shifted to Dukascopy mid, offset -0.08..+0.26 $) has never
been used. Same 2,232 candidates per TF, same engine (2 bp + swap, stop-first). Settings tested, fixed now:
(a) pre-registered 52w LCB z1 top2 WRWR-sized; (b) M5 best-compounding 78w z1 top1 sized; (c) M15 best-compounding 78w z1
top5 unsized 26w equity filter; (d) v3 "M15+H1" 52w LCB z2 top8 unsized 13w equity filter. Read-out: net R, R/yr, positive
52-week blocks and 1%-risk CAGR / max DD over 2009-03..2020-12 per setting. Pass = net R > 0 and CAGR > 0; this spends no
alpha and is descriptive, but it is the first genuinely unseen test of any M5/M15 rule.

### Result: M5/M15 unseen-history holdout (HistData 2009-03 .. 2020-12) - FAIL
Long-history caches (HistData + Exness, leak check PASS). `research/foundry/wrwr_holdout.py` -> data/foundry/wrwr_holdout.xlsx.
| setting | holdout net R (R/yr) | positive 52w blocks | CAGR @1% / max DD |
|---|---|---|---|
| (a) pre-registered, M5 | -609 (-51.5) | 0/11 | -46.6% / 99.9% |
| (a) pre-registered, M15 | -558 (-47.3) | 2/11 | -46.1% / 99.9% |
| (b) M5 best-compounding | -177 (-15.0) | 2/11 | -18.4% / 92.8% |
| (c) M15 best-compounding | -176 (-14.9) | 2/11 | -28.8% / 98.9% |
| (d) M15+H1 (H1 half is NOT unseen) | +214 (+18.1) | 6/11 | -7.7% / 93.1% |
Every setting that relies on M5/M15 loses on the unseen years; (d) is positive in R only through its H1 half and still
compounds negatively at 1% per trade (8 concurrent champions -> large weekly swings). The 2021-26 M5/M15 results were a
fit to one bull-market span. Verdict: no M5/M15 WRWR setting is usable; small-TF candidates are dropped from the WRWR pool.

## Correction (2026-09-30, Codex R18-4): v3 "H4+D1" pools were defined as tf != "H1" and therefore also contained M5
and M15 once those caches were loaded; the v3 statement "best 3-year return/DD = H4+D1 SL2 pool" is withdrawn. Other
known defects of the WRWR numbers above (entry-week equity filter, EN>0 week filter, future-derived B_REF in vol_scale,
shadow-vs-live position state, weekly compounding) are listed in docs/CODEX_R18_MASTER_PLAN.md; every WRWR figure in
this ledger before this note is provisional until the corrected simulator (docs/WRWR_CONTRACT_PREREG.md) reruns it.

## WRWR corrected simulator — first run and BASE reconciliation (2026-09-30; plan step 1 stop rule triggered)
Code `research/wrwr/` (contracts, signals, portfolio, run_family; contract and portfolio tests pass; Codex R18e OK TO START).
Potential-signal tables: gold H1 25.8M, H4 6.9M, D1 1.26M signal rows (2,232 candidates each). Family sha256
fb28ac097eee30b5904185dec3e5771b5d620eae616955722707c6b055b6bf59 (144 deployable configurations), 1,164 active weeks.
- **BASE corrected (C2 + C4 + causal vol_scale, f = 1%, $10,000): -224.1 R 2004-26 (-10.0 R/yr), CAGR -11.9%, max DD 94%;**
  eras -84 / -9 / -58 / -72 R; last 5 years -66.7 R, last 3 years -23.8 R. Old walk-forward BASE was +182.6 R.
- Decomposition (`research/wrwr/decompose_base.py`), the > 20% change rule of the plan:
  | step | BASE 2004-26 |
  |---|---|
  | old accounting (shadow trades by entry week, flat 2 bp, old B_REF) rebuilt on the new tables | +178.0 R (reproduces +182.6) |
  | corrected live ledger, flat 2 bp, weekly -3U entry stop OFF | +180.3 R (B1-B5 fixes ~ neutral for BASE) |
  | + weekly -3U entry stop (C2 Risk Manager rule) | +18.1 R |
  | + C4 costs (recorded Dukascopy spread + 1 bp; median spread 10.4 bp in 2004, 5.3 in 2008, ~2 from 2012) | -224.1 R |
  Not a bug: the loss comes from the pre-registered weekly stop (high-RR champions lose several 1R trades before a
  winner) and from realistic historical spreads. Neither rule is changed after seeing this; the no-weekly-stop run is a
  disclosed sensitivity only.
- Best of the 144 (descriptive, not a gate): 78w LCB z2 H1 m2 +107 R (4.8 R/yr, max DD 96 R, last 5 years -41 R);
  26w z0.5 H4 m1 +77 R (3.5 R/yr, DD 28 R, last 3 years +44 R); 78w z2 H1+H4+D1 m2 +63 R (DD 28 R). None reaches the
  C10 "usable" tier (10 R/yr).

### The other side of corrected BASE (operator: "ติดลบขนาดนี้แล้วอีกฝั่งจะเป็นยังไง"; `research/wrwr/counterparty_base.py`)
Per-trade R of the original stop, unit size, 3,850 live trades 2004-26:
| side | gross R | cost R | swap R | net R |
|---|---|---|---|---|
| BASE | +168.8 | -427.1 | -22.4 | -280.7 |
| exact counterparty (opposite direction, stop/target swapped, same lots) | -177.0 | -427.1 | -19.7 | -623.8 |
Both sides lose: the selection has a positive gross (+0.044 R/trade) but costs are 0.111 R/trade on H1 stops, paid by
either side. By era the counterparty is worse in 2004-20 and less bad only in 2021-26 (BASE -101 R vs -39 R; BASE's
gross was negative there). FADE/FOLLOW twins of the same champions through the C2 portfolio: -266.1 R (BASE -224.1 R).

## WRWR after the R19 fixes (contract v5) - reruns and the clean factorial decomposition (2026-09-30)
Fixes: mark-to-market equity, first-constituent H4/D1 spread, C5 fail-closed integrity, audit trail, explicit bar length,
frozen XAG cost constant, LF holiday digest (docs/WRWR_SELF_AUDIT_R19.md). Tables rebuilt (0 signals rejected at a cut),
family rerun at f = 0.5 / 1 / 2 % (family sha fb28ac09...).
- **BASE (52w LCB z1, H1, m 2): -151.8 R (f 0.5 %), -220.4 R (1 %), -157.0 R (2 %)** (before the fixes -224.1 R); eras at 1 %:
  -94 / -10 / -63 / -54 R; last 5 years -53 R, last 3 years -24 R. The R19 fixes barely move BASE.
- Best of the 144 at f = 1 % (descriptive): 78w z2 H1 m2 equity filter 26: +83.6 R (3.7 R/yr, max DD 56 R, L5 +11.9 R);
  26w z0.5 H4 m1: +66.5 R (3.0 R/yr, DD 28 R, L5 +25.7 R, L3 +39.3 R); 78w z2 H1+H4+D1 m2: +54.3 R (DD 31 R). None reaches the C10
  "usable" tier (10 R/yr).
- **Factorial decomposition of BASE (f 1 %), replaces the earlier sequential attribution** ("weekly stop -162 R, spreads -242 R" was
  order dependent and is withdrawn): costs x weekly stop x champion handling
  | costs | champions | weekly -3U stop off | on |
  |---|---|---|---|
  | flat 2 bp | (same either way) | +149.2 R | +33.6 R |
  | C4 | fixed to the flat-cost champions | -242.1 R | -321.3 R |
  | C4 | re-selected under C4 | -181.5 R | -220.4 R |
  Weekly-stop effect: -115.6 R at flat cost, -79 / -39 R at C4 (fixed / re-selected). Cost effect (C4 vs flat): -391 / -355 R
  (stop off / on, fixed champions), -331 / -254 R (re-selected). Interaction +36 R (fixed), +77 R (re-selected). Costs dominate;
  the stop costs roughly a third of the flat-cost gain; with C4 costs BASE loses even without the stop (-181.5 R), and also in the
  low-cost modern era (2021-26: -54 R at C4 vs +18 R at flat 2 bp, where the cost difference is only about 1 bp) - the rule's
  net edge is of the order of the cost.

## WRWR gates, endpoint 1 - BASE alone vs its random-router benchmark (2026-09-30; manifest docs/WRWR_MANIFEST.md frozen before this)
`research/wrwr/run_bench.py BASE` (10,000 seeded full event-driven random-router paths; each BASE champion slot replaced by a random
same-exit-configuration eligible candidate; 4 workers, 345 s) and `analyze_gates.py BASE`:
- mean weekly R (f 1 %, 1,164 active weeks): **BASE -0.189 R/week, random router -0.214 R/week; mean d = +0.025 R/week**, one-sided
  stationary-bootstrap p = **0.371** (block 10; 0.371 at block 4, 0.344 at block 26), 95% lower bound -0.113 R/week.
  **Endpoint 1 NOT PASSED: picking the indicator and direction adds nothing distinguishable from chance**; BASE loses because the
  exit structures it selects (mostly 1:10 targets on H1 stops) lose after cost whoever picks the entry.
- Benchmark Monte Carlo SE: 0.0246 R per single week, 0.0009 R for the time-averaged weekly benchmark (contract target < 0.01 R is read as
  the SE of the time-averaged benchmark, which is what enters d's mean; a 0.01 R SE per single week would need about 58,000 paths).

## WRWR gates, endpoints 2-4 for the zoo family (2026-09-30; manifest frozen before; `analyze_gates.py`)
- **Stage S (500 paths x 144 configurations), Reality Check over d = R - B (studentized, stationary bootstrap K = 999):**
  V = 3.09, **p = 0.105 (block 10)**, 0.071 (block 4), 0.097 (block 26); benchmark time-averaged SE <= 0.004 R per week.
  Best configurations: 78-week LCB z 2 on H4 (m 2: mean d +0.153 R/week, t 3.09, own p 0.005; m 1: +0.091, t 2.99), 78w z2 H1+H4+D1
  (+0.088, t 2.94), 78w z2 D1 m1 (+0.025, t 2.61), 26w z0.5 H4 m1 (+0.112, t 2.35). Their own mean R is small positive
  (+0.016 to +0.057 R/week) while their random-router benchmarks are negative (-0.02 to -0.13 R/week), i.e. within the zoo the
  conservative (z 2, long-window) selection on H4 beats random picks by more than chance at the single-configuration level, but
  the family-wise test (144 configurations) does not reject at 0.05. By the frozen rule (p < 0.20) Stage F runs (v7: 2,000 paths).
- **Endpoint 3, PBO (CSCV, 16 blocks, 5-week embargo) of the 144 weekly-R series: 0.537** (about a coin flip: the in-sample best
  configuration is as often below as above the median out of sample). The 999-replicate outer stationary bootstrap returns
  0.537 as its 95% value, but its resamples repeat weeks across the train / test blocks (leakage), so the bootstrap values
  (mean 0.27, range 0-0.77 in a 60-replicate check) are biased low and the bound is reported with that caveat; either way the
  robust criterion (upper <= 0.20) is not met. **Endpoint 3 NOT PASSED.**
- **Endpoint 4, cost gate for BASE: FAIL** (base mean -0.189 R/week, 95% lower bound -0.333; at +2 bp -0.279 R/week, DD 93 % -> 97 %).
- **Family 2** (SMC / levels / calendar / volatility candidates, docs/WRWR_FAMILY2_PREREG.md): tables built (H1 5,328, H4 1,296,
  D1 1,296 candidates, all signal tests and leak tests pass), selector family run (descriptive, before any gate): best of 144 at
  f = 1 %: 52w LCB z1 H1+H4+D1 m2 +87.4 R (3.9 R/yr, max DD 63 R, last 3 years +19.7 R); BASE-equivalent (52w z1 H1 m2) +67.5 R;
  none reaches 10 R/yr.

## WRWR gates: zoo Stage F and Family 2 Stage S (2026-09-30)
- **Zoo family, Stage F (2,000 paths x 144 configurations; v7 amendment): Reality Check p = 0.111 (block 10), 0.086 (block 4), 0.103
  (block 26) -> endpoint 2 NOT PASSED (needs <= 0.05).** Same top configurations as Stage S (78w LCB z2 on H4: mean d +0.151 R/week,
  t 3.06; 78w z2 H1+H4+D1 +0.086; 26w z0.5 H4 m1 +0.114). BASE alone at 2,000 paths: d +0.026 R/week, p 0.370. The zoo shows a
  weak single-configuration effect on H4 that does not survive the 144-configuration family test.
- **Family 2 (SMC / levels / calendar / volatility), Stage S (500 paths x 144):** Reality Check **p = 0.003 (block 10), 0.001 (4),
  0.002 (26); V = 4.72** (by the frozen rule Stage F must run and decides alone). Top: 78w LCB z2 H4 m2 (mean d +0.133 R/week,
  t 4.72, mean R +0.006, benchmark -0.127); 52w z2 H4 m2 (+0.117, t 4.31); the BASE-equivalent 52w z1 H1 m2: mean R +0.058 R/week
  vs random router -0.203, d +0.261 R/week, one-sided p 0.001, 95% lower bound +0.116 (endpoint 1 pattern passed for Family 2's BASE).
  Caveat before any reading as edge: selection from trailing performance can be capturing the persistence of gold's drift
  (long-biased clock / level candidates) rather than a setup; diagnostics follow, and endpoints 3-4 (PBO, cost gate) and Stage F
  (2,000 paths) are pending. Two families have now been tested; with a Bonferroni split of alpha across the two pre-registered
  families the family-claim threshold would be 0.025.

### Family 2: endpoints 3-4 and the Auditor's drift / timing diagnostics (2026-09-30)
- **PBO = 0.449** (the 999-replicate outer bootstrap upper value 0.586 is biased by repeated weeks, see the zoo entry) -> robust criterion (upper <= 0.20) **NOT MET**.
- **Cost gate FAIL for all four configurations tested**: 52w z1 H1 m2 (BASE-equivalent): mean +0.058 R/week, 95% lower bound -0.074, +2 bp
  +0.006, DD 59 % -> 70 %; 78w z2 H4 m2: +0.006 (lb -0.040), +2 bp -0.012; 52w z2 H4 m2: -0.025; 52w z2 H4 m1: 0.000 (lb -0.034).
  None has a positive lower bound on its mean weekly net R.
- **What the champions are** (`diag_f2.py`; descriptive): the BASE-equivalent is 1,009 live trades, **long trades +85.1 R (+0.155 R each) vs short trades
  +3.6 R (+0.008 R each)**; mostly FOLLOW (75 %), H1 1:10 and 1:5 exits, from nr7_break, tom, inside_break, squeeze_break and round100_x;
  52w z1 H1+H4+D1: long +114.6 R, short +17.0 R. The H4 configurations with the largest Reality Check t (78w z2 H4 m2) are direction
  neutral (long -4 R, short +5 R, total +7 R over 22 years).
- **Timing control** (`diag_drift.py`: each live trade re-simulated at 30 random other bars of the same week, same direction, same entry hour for
  H1, same exit shape): BASE-equivalent actual +0.088 R/trade vs matched -0.055, excess +0.143 R/trade (long +0.185, short +0.092),
  weekly-cluster t = +1.42 over 497 weeks (not significant); H1+H4+D1 52w z1: excess +0.167, t +1.63; **H4 78w z2 m2: excess -0.063 R/trade
  (t -1.67) - its positive d versus the random router comes from choosing directions, not from timing.** Reading: the Reality Check
  significance of Family 2 is mostly direction persistence (the selector keeps the side that recently worked, which in gold's
  uptrends is long) plus cheap wide exits; signal timing adds a positive but statistically weak increment on H1; absolute
  profits after cost are small (about +3 to +4 R per year for the best configurations) and no lower bound is positive.

### Family 2 Stage F (2,000 paths x 144) and era stability of the excess d (2026-09-30)
- **Endpoint 2 for Family 2: PASSED - Reality Check p = 0.003 (block 10), 0.001 (block 4), 0.002 (block 26), V = 4.76**; also below the
  Bonferroni threshold 0.025 for two families. BASE-equivalent (52w z1 H1 m2): mean R +0.058 vs random router -0.200, d +0.258 R/week,
  p 0.001, 95% lower bound +0.115 (endpoint-1 pattern passed for Family 2). Zoo family stays NOT PASSED (Stage F p 0.111).
- **d is positive in every era for the top configurations** (Family 2 52w z1 H1 m2: +0.33 / +0.53 / +0.03 / +0.15 R/week for 2004-08 /
  2009-14 / 2015-20 / 2021-26; H4 78w z2 m2: +0.09 / +0.22 / +0.11 / +0.11); share of the 144 configurations with mean d > 0 by era:
  70 % / 88 % / 35 % / 73 % (Family 2), 49 % / 62 % / 74 % / 66 % (zoo). The mean weekly R of those configurations is above zero
  only in 2009-14 (+0.34 R/week for the BASE-equivalent) and about zero elsewhere.
- **Reading (Auditor):** selecting from trailing performance beats a random pick with the same exit shape reliably and across
  eras (part of it is avoiding the cost drag of poor, high-turnover candidates, part is keeping the side that recently worked),
  but the net profit after cost stays near zero (best about +3 to +4 R/year, all cost-gate lower bounds negative) and the choice of
  WHICH configuration to use is unstable (PBO 0.45). Nothing is promoted; Family 2 is eligible for a SHADOW record without alpha.

## WRWR SHADOW record 1 built and frozen (2026-09-30; docs/WRWR_SHADOW_PREREG.md, docs/WRWR_SHADOW_MANIFEST.md)
Paper only, no alpha, no orders. `research/wrwr/forward_shadow.py` (added to the Saturday job after the Foundry forward panels): for the Family 2
configurations F2-66, F2-78, F2-134, F2-86 it builds the potential-signal tables from the spliced Dukascopy + Exness H1 (C5 splice validation
must pass), selects the champions at every cut, appends the frozen rows (hash-chained) at each Friday 22:15 UTC cut from 2026-10-02, replays
the frozen history through the C2 simulator (forward vol_scale mode) for weekly paper R (FINAL after 30 days, else PROVISIONAL) and writes a Thai
summary (data/wrwr/forward/summary_th.md). Fail-closed on code digest, chain, reproduction of frozen rows, and C5 checks.
- Tests: forward pipeline = research pipeline for 4,852 (config, cut) champion sets up to 2026-08-07 (needed the research tie-break salt: exactly tied
  candidates, e.g. `tom` with exits whose targets were never reached, are ordered by candidate hash); truncating the data at the cut 2026-08-14 22:15
  leaves 4,620 champion sets unchanged (no leak; trades that resolved inside the data before the cut are counted); scratch runs wrote 28 rows,
  the second run appended none and re-verified them, an edited byte broke the chain check. A design point fixed on the way: gold closes 21:00-22:00
  UTC, before the 22:15 cut, so a cut counts as covered once 30 minutes have passed and the data ends within 4 hours of it (the job runs at 23:00 UTC).
- Splice: the real Dukascopy -> Exness seam FAILED the v5 raw-spread rule (ratio 0.14) and passes the amended charged-cost rule (0.815); costs of the
  Dukascopy-quoted years 2021-26 are about 0.5-1 bp above what the Exness account would be charged.
- All tables were rebuilt after the last code edits: array digests identical to before (only the code digest changed), all test suites pass.

## WRWR historical out-of-sample Test A: the research procedure replayed year by year on gold (2026-09-30; docs/WRWR_HISTORY_OOS_PREREG.md)
Operator: use past data instead of waiting for forward weeks. The 2004-26 champion history is in-sample for the CHOICE of the four SHADOW
configurations, so Test A re-runs the whole research decision at the first cut of every year 2010..2026 using only weeks already known
(studentized Reality Check on d = R - B of the frozen Stage F files; adopt the largest-t configuration only if the family p <= 0.05) and
scores the following year. `research/wrwr/history_oos.py`, output data/wrwr/history_oos_A.json / .log. Nothing re-simulated.
| family | procedure | years adopted | weeks | total R | mean R/wk (95% lb) | mean d/wk (95% lb) | positive years |
|---|---|---|---|---|---|---|---|
| zoo | P1 (primary) | 0 | 0 | 0 | - | - | - |
| zoo | F1 forced top-1 | 17 | 869 | -96.2 | -0.111 (-0.232) | +0.065 (-0.054) | 41 % |
| zoo | F4 forced top-4 | 17 | 869 | -46.8 | -0.054 (-0.104) | +0.035 (-0.013) | 35 % |
| Family 2 | **P1 (primary)** | 16 (2011-26) | 816 | **-81.8** | -0.100 (-0.186) | **+0.093 (+0.006)** | 38 % |
| Family 2 | P4 top-4 | 16 | 816 | -74.5 | -0.091 (-0.168) | +0.082 (+0.007) | 44 % |
| Family 2 | F1 forced top-1 | 17 | 869 | -30.9 | -0.036 (-0.182) | +0.179 (+0.032) | 41 % |
| Family 2 | F4 forced top-4 | 17 | 869 | -44.1 | -0.051 (-0.149) | +0.132 (+0.022) | 47 % |
- **Verdicts (pre-registered): zoo INSUFFICIENT** (its Reality Check never reached p <= 0.05 at any decision date, so the procedure never trades;
  forced picks lose); **Family 2 WEAK**: the procedure passes its own gate every year from 2011 and its picks beat the same-cost random router out
  of sample (lower bound of mean d just above zero, +0.006 R/week), but they lose after cost (-82 R over 16 years; random picks lose about
  -0.19 R/week, the chosen configurations about -0.10).
- Picks: 2011-13 52w z2 H1+H4+D1 m2, 2014 26w z2 H1, 2015-18 52w z1 H1 m2 (= F2-66; 2018 alone -33.8 R), 2019-26 78w z2 H4 m2 (= F2-134).
  The in-sample totals of the SHADOW configurations (F2-66 +63.6 R, F2-78 +81.8 R) come mostly from before the configuration would have been
  chosen (2004-10; 2010 alone +51 R for the top-t configuration, a year the gate did not yet pass).
- Reading: the selection has a small, real relative edge over random picks, not a profit after cost. Waiting for forward weeks would test the
  same thing; Test B (silver) is the independent check.

## Plan step 2d closed: same-bar SL/TP ties (2026-09-30; research/wrwr/tie_bound.py, data/wrwr/tie_bound.log)
Rule fixed before running: re-simulate every realised live trade of the four SHADOW configurations with the tie rule reversed (target first);
if no configuration moves by more than 10 R and no lower bound of mean weekly R changes sign, keep stop-first; otherwise resolve the ties
from finer data. Every re-simulation reproduced the stored gross to <= 0.0001 bp.
| metal | config | trades | ties | total R (stop-first) | target-first bound | resolved (silver M1) |
|---|---|---|---|---|---|---|
| gold | F2-66 / 78 / 134 / 86 | 1009 / 843 / 1080 / 1082 | 1 / 1 / 5 / 3 | +67.5 / +87.4 / +7.2 / -29.3 | +3.9 / +3.9 / +6.2 / +2.8 | not needed |
| silver | F2-66 / 78 / 134 / 86 | 721 / 558 / 666 / 570 | 0 / 1 / 4 / 7 | -34.2 / -0.1 / +12.5 / -30.7 | 0 / +2.8 / +4.3 / +12.9 | 0 / +2.8 / +4.3 / +6.8 |
- Silver F2-86 exceeded the 10 R trigger, so its ties were resolved with HistData M1 (no silver ticks on disk): 5 target-first, 2 stop-first,
  none inside a single M1 bar; total -30.7 -> -24.0 R. No lower bound changes sign anywhere. Stop-first is slightly pessimistic (at most about
  +0.4 R per year) and changes no conclusion; tick resolution is not needed.

## WRWR historical out-of-sample Test B: silver (2026-09-30; docs/WRWR_HISTORY_OOS_PREREG.md; research/wrwr/xag.py, xag_run.py)
Data: HistData XAGUSD M1 2009-05..2026-09-24 (5,859,870 M1 bars, 0 dropped at DST changes, 5 M1 moves > 5 % kept) -> 103,394 H1 bars (median
115 per week), Exness spread on 18,033 hours (2023-09+). Timezone checks PASS: HistData vs Exness close MAD 1.22 / 1.01 bp at shift 0 vs
17-21 bp at +-1 h (summer / winter; the C5 info thresholds 2 bp / 1 bp are narrowly missed on MAD, two feeds); silver-gold H1 return
correlation peaks at lag 0 in every year and DST half (0.50-0.84, lags +-1 h near 0). Builder bit-parity with the frozen gold tables: H4 zoo,
H4 Family 2 and H1 Family 2 with 4 sessions all identical. Silver tables: Family 2 5,400 (H1) + 1,296 (H4) + 1,296 (D1) candidates, zoo H1
2,232; 0 entries rejected at a cut; 830 active weeks 2010-02..2026-09.
| endpoint | result |
|---|---|
| **B1 primary: Family 2 Reality Check on silver** | Stage S p 0.001 (V 6.82) -> **Stage F p 0.001 (V 6.87): PASS** |
| **B2: F2-66 / F2-78 / F2-134 / F2-86 vs random router** | mean d +0.335 / +0.295 / +0.156 / +0.140 R per week, all p 0.001, **all Holm-significant** |
| B2 cost gates | **all FAIL**: mean R per week -0.041 / -0.000 / +0.015 / -0.037, lower bounds -0.165 / -0.124 / -0.045 / -0.092 |
| B2 totals 2010-26 | -34.2 / -0.1 / +12.5 / -30.7 R; eras 2010-14 / 2015-20 / 2021-26: F2-78 +44.1 / -0.5 / -43.7, F2-134 +39.3 / -10.1 / -16.7 |
| B3 (C7 as frozen) zoo BASE | mean R -0.302 per week vs random -0.311, d +0.010 (lb -0.145), p 0.437, total -250.3 R: **FAIL** |
| PBO (reported) | **0.830** (gold 0.449) |
- Long / short (live trades): longs +0.07 to +0.14 R each for F2-66/78/134, shorts -0.06 to -0.15 R each (silver rose over the sample).
- Cost decomposition (research/wrwr/xag_decompose.py): gross +86.6 / +77.7 / +52.3 / +2.2 R, cost -115.5 / -72.2 / -37.5 / -31.9 R, swap about -1 to -2 R;
  cost 0.16 R per trade on H1 configurations, 0.06 on H4; zoo BASE gross -34.2 R, cost -215.1 R. Gold for comparison (in-sample 2004-26):
  gross +189.1 / +177.1 / +57.8 / +19.0 R, cost -116.2 / -83.5 / -48.1 / -43.4 R.
- Compounded at 1 % risk per trade (C2 equity): silver F2-66 -2.8 % per year (max DD 47 %), F2-78 -0.35 %, F2-134 +0.71 % (DD 32 %), F2-86 -2.0 %;
  best silver configuration chosen in-sample +3.3 % per year (DD 46 %). Gold Test A procedure (out of sample 2010-26): -5.3 % per year, DD 61 %.
- Exploratory, NOT pre-registered: the Test A year-by-year procedure applied to silver 2012-26 is also WEAK: adopts 2014-26, total -43.6 R,
  mean R -0.068 per week (lb -0.143), mean d +0.224 (lb +0.111).
- **Reading (pre-registered wording):** the gold selection skill replicates on silver in the RELATIVE sense (Reality Check p 0.001, every SHADOW
  configuration beats the same-exit random router), but it pays no profit after cost on either metal and the choice among configurations is
  overfit (PBO 0.83). Random picks lose heavily to cost (silver random router -0.09 to -0.39 R per week), and the selector mostly avoids that drag.
  No alpha; Family 2 stays SHADOW only; the forward record continues unchanged (SHADOW digest re-checked: unchanged).

### Out-of-sample gross vs cost of the year-by-year procedure (2026-09-30; data/wrwr/oos_cost_breakeven.log)
- Gold Test A P1 (2011-26, 624 trades): gross **-32.1 R**, cost -47.7 R, swap -2.0 R, net -81.8 R. Silver exploratory P1 (2014-26, 456 trades):
  gross **+8.7 R**, cost -51.9 R, swap -0.4 R, net -43.6 R.
- Reading: chosen without look-ahead, the Family 2 selections have about zero gross edge; the large in-sample gross (+58 to +189 R on gold) is
  selection-inflated. Cheaper execution alone cannot make WRWR-F2 profitable. Next ideas need other information than H1-D1 price patterns:
  docs/DEEP_RESEARCH_2026-09-30_TH.md.

## Hypothesis batch 1 (2026-10-01; docs/HYPOTHESIS_BATCH1_PREREG.md, research/hyp/batch1.py, data/hyp_batch1.log): 0 of 8 PASS
Net R per trade after C4 cost and swap (DEV gold 2004-15 / CHECK gold 2016-26 / SILVER 2010-26):
| id | DEV | CHECK | SILVER | note |
|---|---|---|---|---|
| A3 weekend gap fill | +0.113 (p 0.25) | -0.094 | -0.085 | gross ~0 after 2016 |
| A4 first-hour reversal | -0.129 | +0.028 | -0.071 | gross +0.12..+0.15 R, cost 0.12..0.25 R eats it |
| A5 Friday 17:00 UTC to close (DEV sign long) | +0.025 | -0.055 | -0.165 | none |
| C1 round-number first touch, fade | -0.422 | -0.299 | -0.294 | round WORSE than the control grid (delta -0.27 / -0.10 / -0.08) |
| C2 round-number cross, follow | -0.282 | -0.125 | -0.325 | round minus control +0.118 (p 0.052) / +0.083 (p 0.077) / +0.003: Osler-consistent relative effect on gold, not tradable |
| D3 GVZ VRP weekly (DEV sign -1) | +0.063 | -0.068 | +0.009 | none |
| I2 52-week high, long 20 D1 | **+0.780 (p 0.006, Holm reject)** | +0.233 (p 0.19) | +1.151 (p 0.011) | vs an always-long control: excess +0.605 / **+0.004** / +1.071 -> recent gold = drift |
| I3 all-time high, long 20 D1 | +0.603 (n 17) | +0.498 (n 18) | +0.496 (n 3) | excess vs always-long +0.43 / +0.27; too few trades |
Reading: nothing passes; the only persistent effects are trend/drift (I2, I3) and a relative round-number cascade (C2) that costs cannot pay.

## Hypothesis batch 2: cross-asset drivers (2026-10-01; docs/HYPOTHESIS_BATCH2_PREREG.md, research/hyp/batch2.py, data/hyp_batch2.log): 0 of 6 PASS
MT5 clock verified = UTC (MAD 0.17 bp at shift 0 vs 9.7 bp at +-1 h against Dukascopy).
| id | DEV | CHECK | SILVER | excess vs same-direction random timing (CHECK) |
|---|---|---|---|---|
| X1 US500 crash -> short gold 10 D1 | n 2 | -0.201 (n 29) | -0.020 | +0.025 |
| X2 USDJPY surge -> gold 5 D1 (DEV sign long) | +0.065 | +0.045 | +0.039 | -0.043 |
| X3 oil shock -> gold with oil 5 D1 | -0.041 | -0.007 | +0.036 | +0.038 |
| X4 DXY 60-day trend -> gold opposite 20 D1 | -0.100 | +0.020 | +0.058 | +0.115 |
| X5 yuan weakness -> long gold 20 D1 | -0.024 | +0.169 (n 14) | -0.124 | -0.038 |
| X6 gold residual reversal vs DXY/JPY/US500, H1 | -0.150 | -0.110 | -0.081 | -0.034 |
- **Lead-lag map (H1, 2016/2019-2026):** same-hour correlation with gold: DXY -0.41, AUDUSD +0.42, EURUSD +0.37, USDCHF -0.38, USDJPY -0.32,
  USDCNH -0.32, US500 +0.19, BTC +0.13, JP225 +0.11, USOIL +0.03, silver +0.78; at lags of 1-4 hours every |corr| <= 0.015. Nothing leads gold by
  an hour: cross-asset information is priced within the same hour.

## Hypothesis batch 3: trend and calendar (2026-10-01; docs/HYPOTHESIS_BATCH3_PREREG.md, research/hyp/batch3.py, data/hyp_batch3.log): 0 of 4 PASS
| id | DEV | CHECK | SILVER | excess vs drift control (DEV / CHECK / SILVER) |
|---|---|---|---|---|
| T1 12-month time-series momentum, 21 D1 blocks | +0.147 (p 0.035) | +0.034 (p 0.36) | +0.150 (p 0.027) | +0.117 / -0.049 / +0.162 |
| K1 autumn (Sep, Nov) | +0.389 (n 24, p 0.06) | -0.101 | -0.034 | +0.285 / -0.307 / -0.095 |
| K2 turn of the year (5th-last Dec bar, 10 D1) | +0.165 (n 12) | +0.518 (n 10, p 0.038) | +0.248 (n 16, p 0.056) | +0.115 / +0.425 / +0.228 |
| K3 before Chinese New Year (10 D1) | -0.107 | +0.260 | +0.012 | -0.157 / +0.167 / -0.008 |
- TSMOM with 1 / 3 / 6-month lookbacks: all small (+0.006 to +0.091 R), none significant. The 12-month trend paid on gold 2004-15 and on
  silver but not on gold 2016-26 (below the drift control), consistent with the earlier finding that breakout/trend setups worked mainly
  in 2003-14. The autumn effect has decayed. The turn of the year is positive and above drift in all three periods but has one trade a year
  (12 / 10 / 16 trades): kept as a watch item, not a rule.

## Hypothesis batch 5 (2026-10-01; docs/HYPOTHESIS_BATCH5_PREREG.md, research/hyp/batch5.py, data/hyp_batch5.log): 0 of 3 PASS
| id | DEV | CHECK | SILVER | excess (DEV / CHECK / SILVER) |
|---|---|---|---|---|
| D4 GVZ panic -> gold 5 D1 (DEV sign short) | +0.158 (n 20) | -0.215 | -0.020 | +0.235 / -0.079 / +0.039 |
| A7 quarter end, 5 D1 (DEV sign long) | -0.021 | +0.126 | +0.002 | -0.047 / +0.067 / -0.001 |
| W1 Monday D1 (DEV sign short) | -0.013 | -0.029 | -0.018 | +0.022 / +0.022 / +0.009 |
- J2 ensemble (descriptive): the equal-weight mean of all 144 Family 2 configurations: gold 2004-26 -19.7 R (equity x0.81), median configuration
  -13.2 R, best in-sample +87.4 R, 33 % of configurations positive; silver (corrected clock) -10.2 R (x0.90), median -8.1 R, best +46.1 R, 35 %.

## Test B rerun after the HistData clock fix (2026-10-01; docs/WRWR_HISTORY_OOS_PREREG.md Amendment 1)
HistData changed its clock convention in 2019 (EST + European summer time); from 2019 about four weeks a year were 1 h early in the silver bars
(and in the gold HistData M5 file, rebuilt). Corrected silver: Reality Check Stage F **p 0.001 (V 7.07) PASS**; F2-66 / 78 / 134 / 86 total
-24.4 / +13.5 / +3.4 / -39.9 R (first run -34.2 / -0.1 / +12.5 / -30.7), all beat the random router (Holm), all cost gates FAIL, PBO 0.877;
zoo BASE -251.3 R FAIL. The conclusions are unchanged; that a one-hour label shift in 8 % of the weeks moves single-configuration totals by
10-14 R is another sign of how unstable the choice of configuration is.

## Hypothesis batch 4: regime-conditional champion selection (2026-10-01; docs/HYPOTHESIS_BATCH4_PREREG.md, research/hyp/batch4_regime.py): FAIL
Exact-equivalence check passed (one class for every week reproduces WRWR v2 bit for bit, gold and silver). Out-of-sample yearly procedure
(largest trailing t of weekly net R), 1 % risk:
| family | gold 2010-26 total (mean/wk) | silver 2012-26 total (mean/wk) | minus v2 per week (p) gold / silver |
|---|---|---|---|
| v2 (unconditional) | -42.4 R (-0.049) | -31.4 R (-0.043) | - |
| V: volatility class | -35.6 R (-0.041) | -14.8 R (-0.020) | +0.008 (0.49) / +0.023 (0.33) |
| T: trend class | **+3.4 R (+0.004)** | **+17.2 R (+0.024), equity x1.14** | +0.053 (0.25) / +0.067 (0.09) |
- Both variants FAIL (gold Holm not significant). Full-sample totals of the SHADOW configuration indices collapse under conditioning (for
  example gold F2-78 +87.4 -> -211.8 R under V): splitting the shadow history by regime leaves too few trades per class and the scores become
  noise. The trend-class procedure improves the out-of-sample result on both metals by about +46 / +49 R but not significantly: a watch item.

## Hypothesis batch 6 (2026-10-01; docs/HYPOTHESIS_BATCH6_PREREG.md, research/hyp/batch6.py)
- P1 gold/silver ratio mean reversion: DEV -0.283 R (n 19), CHECK +0.175 R (n 19, p 0.28): FAIL.
- R1 weekend de-risking (halve positions into weekends of a high-gap regime, 28 % of weekends): over the 8 SHADOW runs the 1st-percentile week
  improves +0.018 R, max drawdown -0.57 R, total -13.6 R (limit -27.3 R) -> meets the pre-registered adoption rule for a Risk Manager
  CANDIDATE. The effect is small (the worst weeks are not weekend weeks). Not deployed: Risk Manager rules change only with the operator.

## News batch N (2026-10-01; docs/HYPOTHESIS_BATCH_NEWS_PREREG.md written before the download; research/hyp/news_run.py, data/hyp_news.log): 0 of 4 PASS
Data fetched with the operator's permission into data/macro/ (manifest with sha256; 54.5 MB; GLD archive returned a PDF and is not used).
Tweet times are taken from the Twitter snowflake ids (exact UTC; the archive's own time column is unreliable: the covfefe tweet shows 12:06 but
the id gives 04:06:25 UTC = 00:06 New York, the known time).
| id | DEV | CHECK | SILVER | excess vs drift control (DEV / CHECK / SILVER) |
|---|---|---|---|---|
| N2 GPR spike (99th pct) -> short gold 20 D1 | -0.141 (n 29) | +0.042 (n 23) | +0.054 | +0.034 / +0.312 / +0.145 |
| N3 high-GPR regime -> long 21-bar blocks | +0.022 | +0.148 (p 0.17) | -0.006 | -0.082 / -0.058 / -0.067 |
| N4 EPU or TPU spike (97.5th pct) -> long gold 5 D1 | +0.017 (p 0.40) | **+0.110 (n 162, p 0.024)** | +0.041 (p 0.23) | -0.009 / +0.052 / +0.038 |
| N6 Trump keyword posts -> gold 12 H1 (DEV sign long) | -0.078 (n 748) | +0.014 | -0.137 | -0.023 / -0.022 / +0.021 |
- Read-outs: the weekend change of the GPR index correlates +0.089 (gold) / +0.073 (silver) with the Monday gap; weekends with a GPR jump (z > 1)
  gap +3.6 bp (gold) / +13.2 bp (silver) on average, |gap| 13.0 vs 11.1 bp. Weekends with many Trump posts (z > 2) do NOT have larger gaps
  (mean |gap| 13.9 vs 15.0 bp gold). Policy-uncertainty spikes -> gold up is the only effect significant in a period (CHECK), not in DEV.

## Exploration: scale-and-flip, and the D1 trend basket confirmation (2026-10-01; operator: "ขยายไม้ ... สลับด้าน ... ทำอะไรแปลกๆไปก่อน")
- research/hyp/explore_scale.py: 149 signal x TF combos on gold; the DEV rule (follow if net > 0; scale the stop/hold up when gross > 0 but net <= 0;
  flip when scaling makes it worse) kept 114 (61 follow, 42 scaled up, 11 flipped). 22 were positive on gold CHECK and silver; 21 of them also beat
  same-direction random timing on both (D1 displacement +0.47 / +0.18 R per trade, Bollinger breakout +0.34 / +0.13, Donchian 55 +0.26 / +0.09,
  turn of month +0.22 / +0.08). Not significant after BH over the 114 kept, and chosen by looking at CHECK.
- Confirmation (docs/HYPOTHESIS_TREND_BASKET_PREREG.md; members = the 37 D1 rows kept on gold DEV only, explore_scale.csv sha256 fb9a68cd...;
  research/hyp/trend_basket.py): eight markets never used for selection (EURUSD, USDJPY, AUDUSD, USDCHF, US500, USTEC, USOIL, BTCUSD; MT5 D1
  2016/2017/2018/2019-2026; fixed costs, no swap). **Pooled excess over random timing +0.0016 R per week, p 0.378: FAIL.** Only BTCUSD shows a positive
  basket (+17.1 R, p 0.066; excess +0.026 R/week, p 0.145); FX and indices about zero or negative. The daily short-term trend effect seen in gold
  2016-26 and silver does not generalise; it is either specific to precious metals in their strong uptrend or selection noise.

## Exploration: weird batch (2026-10-01; research/hyp/explore_weird.py, data/hyp_explore_weird.log)
18 quick rules, both directions on gold DEV, the better kept, then gold CHECK and silver with the random-timing control. Consistent (positive and
above random timing in all three): 3 of 18, about what chance gives for 18 rules x 2 directions:
| rule | DEV | CHECK | SILVER | excess CHECK / SILVER |
|---|---|---|---|---|
| VIX crosses above 30 -> long gold 10 D1 | +0.228 (n 17) | **+0.431 (n 20, p 0.020)** | +0.276 (n 28, p 0.079) | +0.338 / +0.256 |
| COT non-commercial net share >= 90th pct of 3 years -> long (follow the crowd) 20 D1 | +0.206 (n 17) | +0.200 (n 33, p 0.082) | +0.192 (n 36) | +0.015 / +0.127 |
| 10-year real yield 1-day drop <= 5th pct -> long gold 5 D1 | +0.072 (n 122) | +0.062 (p 0.18) | +0.033 | +0.003 / +0.029 |
Not consistent: lunar new moon, first five days of the month (CHECK +0.125 p 0.052 but DEV -0.007), seasonal momentum, month-to-date momentum,
shock follow-through, Fibonacci 61.8 %, Asian-range breakout (-0.12 to -0.34 R), VIX spike, real-yield rise / trend, breakeven trend, 2-year
hawkish shock, broad dollar trend, COT washout, hedgers less short. VIX > 30 has a mechanism (forced selling of gold for margin first, then the
haven bid within two weeks) and is a candidate for a forward paper watch list; nothing here is evidence on its own.

## Exploration: sieve-lite and the buy-and-hold reference (2026-10-01)
- research/hyp/sieve_lite.py: the 158 sieve features on gold H1, extreme deciles / events / time flags, h = 4 and 24 bars: 18 DEV cells with
  |cluster t| >= 3 (mostly the old hour-of-day pattern: Asian hours up, 06-08 UTC down, plus Friday); as trading rules on gold 2016-26 and silver
  2016-26: **0 of 18 consistent**. The full C11 sieve (999 placebo paths, about 4-5 h) is deferred: the lite scan gives it little expected value.
- Buy and hold gold CFD (1x notional, C4 swap, 2 bp per change): 2004-26 x6.99 (+8.7 % a year, max DD 48 %; pre-2016 swap understated because the
  Treasury file starts in 2016), 2016-26 x3.19 (+11.2 %, DD 28 %), 2021-26 x1.90 (+11.7 %, DD 28 %); a 200-day SMA filter lowers the return in every
  window (+6.3 / +7.5 / +7.3 %). Every active rule tested so far has done worse than simply holding gold.
- R1 weekend de-risking adopted for new records with the operator's word (docs/RISK_MANAGER_RULES_TH.md); the frozen SHADOW record is unchanged.

## Exploration: entry location on market structure (2026-10-01; operator: "เราเข้าไม้ในจุดไหน hh hl ll lh"; research/hyp/structure_entries.py)
Fractal(2) swings, structure UP = HH + HL, DOWN = LH + LL; structural stop beyond the opposite swing (min 0.5 ATR); time exit or 2R target.
Net R per trade (gold DEV 2004-15 / gold CHECK 2016-26 / silver 2010-26) and excess over same-direction random timing:
| D1 entry | 2R target net | excess | time-exit net |
|---|---|---|---|
| buy the HH breakout in UP (stop under the HL) | **+0.109 / +0.128 / +0.093** | +0.058 / +0.029 / +0.065 | +0.102 / +0.052 / +0.069 |
| buy at the HL once confirmed | -0.132 / +0.003 / -0.120 | -0.209 / -0.208 / -0.182 | -0.121 / +0.098 / -0.088 |
| buy limit at 50 % of the last up leg (stop under the HL) | -0.182 / +0.212 / -0.295 | -0.277 / +0.034 / -0.362 | -0.129 / -0.023 / -0.270 |
| sell the LL breakdown in DOWN | -0.093 / -0.086 / +0.008 | +0.011 / +0.090 / +0.087 | |
| sell at the LH / limit 50 % rally | -0.391 / -0.175 / -0.321 ; -0.336 / -0.331 / -0.237 | negative | |
H4 shows the same order (HH breakout best: time exit -0.011 / +0.192 / +0.062; HL and limit pullbacks below random timing). Buying pullbacks loses to
buying breakouts on gold and silver: a limit at a pullback is filled most often when the pullback keeps going and missed when the trend runs
(adverse selection). On D1 the cost is only 0.02-0.03 R per trade; the gross edge itself (+0.12 to +0.18 R for the HH breakout) is what is thin.

## Classic trend following with trailing exits (2026-10-01; operator: simple and consistent; research/hyp/turtle.py, data/hyp_turtle.log, data/hyp/turtle_finance.log)
Canonical parameters only (Turtle S1 20/10, S2 55/20, 2 N initial stop; Chandelier 55-day entry, highest high - 3 ATR22). All earlier tests capped
winners (2R targets or 5-day holds); letting profits run changes the per-trade picture:
- Gold D1 long-only, net R per trade 2004-15 / 2016-26: S2 +0.70 / **+1.49** (best trade +17 R), S1 +0.37 / +0.60, Chandelier +0.56 / +0.89; long+short
  versions weaker. Silver S1 long-only +0.32. Eight untouched MT5 markets: long-only average +0.44 to +0.60 R per trade, long+short +0.16 to +0.25.
- Finance ($10,000, risk per trade fixed at entry, one position per market): gold-only S2 long-only 2016-26 at 1 / 3 / 5 % risk: CAGR +3.1 / +8.5 /
  +13.2 %, max DD 4 / 11 / 17 % (2004-26: +2.2 / +6.1 / +9.4 %, DD 4 / 13 / 20 %). Ten-market portfolio 2016-08..2026-09 at 1 % per trade:
  **Chandelier long-only CAGR +13.9 %, max DD 15 %, 10 of 11 years positive, worst year -3.0 %** (without BTC +8.2 %, DD 12 %); Turtle S1 long-only
  +15.3 %, DD 16 % (without BTC +7.6 %); S2 long-only +11.9 %, DD 23 %; long+short versions +1 to +5 % with DD 27-66 %.
- Caveats: long-only in markets that mostly rose over 2016-26 is partly beta; swap is modelled for gold and silver only (a long BTC / index CFD pays a
  large swap, not deducted); parameters are canonical, but choosing long-only was informed by these runs. The value against buy-and-hold is the
  drawdown (gold B&H 2016-26 +11.2 %, DD 28 %).

## Big bundle X1-X7 (2026-10-01; prereg docs/BUNDLE_2026-10-01_PREREG.md, commit a729070 before any run; research/bundle/, data/bundle/; Thai report docs/BUNDLE_2026-10-01_RESULTS_TH.md)
Separate experiments, uncapped exits, full costs (spread + 1 bp, broker or C4 swap).
- X1 every-signal autopsy (889,043 independent overlapping trades; S1 / S2 / Chandelier, M5..W1, gold DEV / CHECK, silver, 16 MT5 markets):
  M5 / M15 lose after cost everywhere; H1 ~ 0; H4 / D1 / W1 longs positive in gold DEV, CHECK and silver (D1 long +0.27..+0.85 R gold CHECK,
  +0.43..+1.39 silver); shorts lose almost everywhere. Skipped (in-position) signals stay positive on D1 / H4 longs, below the taken ones on gold,
  above on silver. Stable winner/loser markers: D1 long wins in calm markets (low 1-year ATR percentile, AUC 0.26-0.46), M15 the opposite.
  Stacking (every signal opens a position) = leverage: gold H4 S2 long +6.7 %/yr DD 11 % (one position, 1 %) vs +8.5 % DD 13.5 % (stack, 0.25 %)
  vs +20.6 % DD 45 % (stack, 1 %, up to 35 open); "add only while in profit" ~ same as stacking all.
- X2 martingale (research only; forbidden for orders): loss-doubling on random entries ruined 34-100 % of 200 seeds (x2), median -3.8 %/yr; on
  the trend trades 67 % of rows ruined, median DD 101 %. Averaging grid: 94-100 % of configurations ruined at least once in 17 years (up to 29
  times) while 96.5-99.9 % of cycles closed in profit; only long gold grids made money (gold x4.5), still ruined 1-14 times.
- X3 opposite side: 0 / 54 pass (loser-profile fade gold CHECK -0.15 R, silver -0.35 R; candle reversal with 1 ATR stop / 1 ATR trail gross
  +0.006..+0.04 R, net -0.08 (H1) .. -0.46 (M5) R).
- X4 trend refinements: 6 / 18 pass (silver better AND >= 60 % of other markets better AND pooled p < 0.05): candle filter on D1 Chandelier
  and S1 (+0.42 / +0.25 R silver, 75 % of markets up, p 0.027 / 0.002), W1 agreement for D1 S1, D1 agreement for H1 (three systems, one
  finding). Other-market medians stay ~0 or below after filtering. Pyramiding helps gold / silver D1 only (gold D1 Chandelier +2.0 -> +7.5 %/yr
  with 4 units) and hurts the other markets; breakeven at +1 R does not help.
- X5 wild ideas: 0 / 41 pass against 50 mirrored placebo paths (storms, sunspots, flux, NY / London weather, moon, eclipses, Mercury
  retrograde, DST Mondays, Friday 13th, pre-CNY, calendar effects); round-number levels no effect.
- X6 ten markets with broker swaps (Chandelier long, D1, 1 %): +11.2 %/yr DD 17.5 % (no swap +14.1 %); without BTC +5.9 %; the 8 untouched
  markets -2.8 %/yr (+0.3 % without USDINR): the multi-market trend portfolio is NOT confirmed on untouched markets.
- X7 WRWR uncapped vs Chandelier long-only: gold -22 R (4/17 years), silver -41 R (3/15) vs +29 R / +3 R -> WRWR does not add value. A first
  run booked channel exits at the trigger bar (fill at the next open): +62 / +36 R; fixed (booked at the fill bar) the full-sample 144-config
  distribution barely moved (gold half positive, median 0 R), so the yearly selection outcome is fragile. First run kept in
  data/bundle/x7_wrwr_uncapped_v0_exitbar.json.

## X8 consistency scan (2026-10-01, descriptive, after the bundle; research/bundle/x8_consistency_scan.py, data/bundle/x8_consistency_cells.csv)
Every feature decile / flag / entry-hour block / weekday of the X1 every-signal trend trades (systems pooled per TF and side), net R in gold
DEV, gold CHECK, silver and the 2012-10..2015-12 gold bear phase. 3,887 cells with >= 100 trades per sample; the excess over the sample mean has
one sign in all three for 33.1 % (chance 25 %; M5 43.8 %, D1 20.5 %). Recurring: entries aligned with the D1 / W1 direction win on H1 (e.g. H1
short with the D1 close 0.7-1.0 ATR below its SMA20: +0.33 / +0.42 / +0.43 R, bear +0.45), entries against it lose (H1 long after a W1 body
<= -0.77 ATR: -0.39 / -0.14 / -0.41); late entries lose (H4 long after 3+ up weeks: -0.31 / -0.36 / -0.24); M5 everything negative, worst in
the lowest 1-year ATR decile and at 20-24 h UTC. Bear phase: D1 breakout shorts still lose (-0.30 R) while H1 / H4 shorts win (+0.42 / +0.26 R).

## Bundle 2 Y1-Y8 (2026-10-01; prereg docs/BUNDLE2_2026-10-01_PREREG.md, commit 74f554a; research/bundle/y*.py, data/bundle2/; Thai report docs/BUNDLE2_2026-10-01_RESULTS_TH.md)
Clean evidence = 15 MT5 markets (USDINR excluded) and gold 2003-05..2008-12; gold 2009-26 and silver in-sample.
- Y1 higher-TF-aligned system (anchor direction + side switch + no chasing): 0 / 18 pass. Side switch alone improves BASE by +0.03..+0.10 R on
  M30 / H1 / H4 (p < 0.05 in several) but pooled R stays <= 0; the no-chasing filter makes H4 / D1 worse in the clean markets (the gold /
  silver pattern does not travel). The long-only reference D1 S1 meets every criterion (pooled +0.245 R, 60 % of markets positive, p 0.017,
  +0.22 R vs BASE, gold 2003-08 +0.36 R; 15-market portfolio +13.1 %/yr DD 23 %) but 2016-26 was a rising period for most markets (beta).
- Y2 the 7 old setups without caps: 0 / 72 pass. Pullback / expansion on H4 turn positive in gold DEV, gold CHECK and silver and beat random
  timing with the same exits (pullback CHAN20 +0.31 / +0.58 / +0.20 R, excess +0.33 R), but are positive in only 27-47 % of the other
  markets (median -0.14 R). News accept / reject on M5: nothing stable.
- Y3 cutting losing conditions: dropping 20-24 h UTC and the lowest-volatility decile helps M5 by about +0.07 R (still -0.41 R); dropping
  chase entries hurts on every TF. Y4: small TFs anchored to big ones stay negative (M5 -0.4, M15 -0.2, M30 -0.1 R).
- Y5 grid fixes: basket or equity stops prevent ruin on gold, not on silver (gaps through the stop); every grid variant loses with random or
  regime directions while a single order of the same first size loses only the cost; the only profitable grids are leveraged long gold.
- Y6 WRWR: averaging the top 10 or all 144 configurations narrows the out-of-sample range across perturbations (gold 66 R -> 9-15 R; silver
  23 R -> 3-8 R) but the out-of-sample R is not positive on both metals (gold ~0, silver -19..-32 R): fragility fixed, no edge to select.
- Y7 invalidation exit: mixed. Y8 volatility router (corrected to one position per market): better than fixed H4 / H1, not better than D1.

## Trend vs holding (2026-10-01; prereg docs/TREND_VS_HOLD_PREREG.md; research/bundle/z1_trend_vs_hold.py, data/bundle2/z1_*.csv)
15 clean MT5 markets, D1, one position per market. Test 1 timing alpha against 2,000 random placements of the same trades: S1 long +0.51 %
per trade (p 0.089, 40 % of markets), Chandelier long +0.49 % (p 0.15, 53 %), S2 long +0.16 % (p 0.39); long + short -0.11..+0.17 % -> FAIL
everywhere: the D1 trend result is mostly beta, not timing. Test 2 buy-and-hold at the same maximum drawdown: Chandelier long-only beats it in
67 % of markets and at the portfolio level (+8.2 %/yr DD 28 % vs +7.9 %) -> PASS; S1 long portfolio +13.1 % vs +6.5 % but only 53 % of markets;
long + short far worse than drawdown-matched holding. Test 3: in 30-80 % crashes of holding, long-only trend lost 0-6 % at 1 % risk per trade.
Reading: trend following's value here is drawdown control (crisis protection), not timing alpha. Research answer on edge difficulty and
remedies (with literature): docs/EDGE_DIFFICULTY_AND_SOLUTIONS_TH.md.

## Plans P01-P16 (2026-10-01; separate preregistrations docs/plans/P00..P16, commit 7353c94 before any run; research/setups/; data/setups/; Thai report docs/plans/RESULTS_TH.md)
14 setups decoded from the operator's six videos (transcribed with faster-whisper on CPU), the operator's HL-test-to-HH plan and the
long-history trend-vs-hold plan. P01-P15: 0 of 184 tests pass. On gold CHECK the mean gross R is about 0 (-0.07..+0.18) and the net R
negative (-0.04 .. -1.16, intraday structures are small relative to costs); RR 1:1 setups win 41-49 % before costs (claims: QM 80-90 % ->
41 %, three-bar 70 % -> 36 %). The few positive cells (P15 H4 +0.38 R, P05 H1 uncapped +0.30 R) are gold-only (silver and the other markets
negative). P04 accumulation breakouts are too rare to judge. P16 (14 FRED daily closes, 1949-2026, close-only, no carry, 2-3 bp): every
system passes: timing alpha +0.52..+0.94 % per trade (p <= 0.01, 93-100 % of markets) and beats drawdown-matched holding in 86-93 % of
markets; positive in every decade 1950s-2020s; long + short gained in the long bear phases (Nikkei 1989-2009 +52 %, oil 2008-20 +92 %).
Deviation: P03 limit orders are cancelled on a new extreme beyond L2 (the plan's "TP before fill" was ill-defined). A verdict bug (column
name `sample`) was fixed and verdicts recomputed from the saved rows.

## G768 (2026-10-01; prereg docs/plans/G768_PREREG.md, commit be96586; research/grid768/g768.py, data/grid768/)
768 combinations (H4 / D1 x context x Donchian / squeeze / broker-swap carry / cross-sectional momentum x volume x structural or 2 ATR stop x
Chandelier / channel / 3 R x pyramiding x long-only or higher-TF direction) on 17 MT5 markets, entries 2021-10..2026-09, one position per
market. Real: 79 basic passes (p < 0.05, R > 0), 0 strict (Holm + >= 60 % of markets); all 79 long-only, mostly H4, higher-TF filter,
pyramiding. Pre-registered fake count (10 mirrored paths, drift removed): basic 0..48 (mean 7.6), strict 0. Added after the results (not
pre-registered): 10 drift-preserving mirrored paths: basic 25..253 (mean 124), strict 0..30 (mean 10.4). The real 79 sit inside the
drift-only distribution: the passes are explained by the 2021-26 rise of most markets, not by timing; no combination shows an edge beyond drift.
- G768 within the five years (operator: rely on the last five years only): choosing on 2021-10..2024-09 by CAGR / DD and checking on
  2024-10..2026-09, 8 of the top 10 stay positive (R +0.26..+0.90 per trade, p 0.04-0.10; the two broker-carry choices flip negative); the R
  correlation between the halves over all 768 is 0.06 and 69 % of all combinations are positive in the second half (long bias in a rising
  period). Best five-year combination H4 Donchian-20 long-only with D1 agreement, 2 ATR stop, 20-bar channel exit, Turtle pyramiding:
  1,331 trades, CAGR 48 % / DD 20 % at 0.25 % per unit (93 % / 36 % at 0.5 %, 160 % / 61 % at 1 %), positive every calendar year 2022-26,
  13 of 17 markets positive; without pyramiding 13 % / 10 % at 0.25 %. Explained by the period's drift (drift-preserving placebo above).
- G768 correction (2026-10-01, found while building the MT5-style report `research/grid768/report768.py`): g768.simulate booked Turtle adds at
  their levels even when the bar opened beyond them, and checked the raised stop only from the next bar. USOIL 2026-02-27: the Monday open
  jumped 67.2 -> 72.7, the adds were booked at 68.2-69.1 (prices that never traded) and the trade made +43R; filled at the real open, with
  stops and adds walked on the H1 bars inside each H4 bar, it makes +0.7R and the next three trades lose -5.8R. Re-run with G768_FIX=h1
  (adds gapped through fill at the open, stops / take-profits / adds walk H1 bars, worst case only inside one H1 bar, swap per unit from its
  add): real 66 basic (was 79), 0 strict; I4 passes 53 -> 40, I1 unchanged (26). Same fills on the placebos: drift-free basic 0..47
  (mean 7.1), strict 0; drift-preserving basic 26..239 (mean 114), strict 0..24 (mean 9.4). Best combination unchanged
  (H4/C2/D1/E1/F1/G3/H7/I4/J1) at 857R (was 982R); best-of-768 in the drift-preserving placebos 261..932R (2 of 10 >= 857R) and in the
  drift-free placebos 101..796R; the same combination earns -641..-36R without drift and -126..+837R with drift. Conclusion unchanged:
  drift plus selection, no timing edge shown. G768_FIX=1 (worst-case order inside the whole H4 bar) kept as the pessimistic bound: real 40 basic.
- MT5-style report of that combination ($100k, 0.25 % per unit compounding on balance, equity marked at every H4 close with open P&L carried
  across closed markets): net +$438k, CAGR 36.6 %, PF 1.34, 19 % winners, balance DD 28.5 %, equity DD 40.5 % (2026-01-29 -> 2026-08-19,
  still 30.9 % below the peak on 2026-09-30); the top 1 % of trades make 115 % of the net R; BTC alone +385R of +857R; costs -122R spread and
  -261R swap against +1,240R gross. The same signals with one unit at the same equity DD (1 % per trade): CAGR 43.3 %, so pyramiding adds
  nothing per unit of drawdown. The earlier "48 % / DD 20 % at 0.25 %" came from the bugged fills and a balance-only drawdown.
- TF sweep (2026-10-01; prereg docs/plans/TF_SWEEP_PREREG.md, commit f43a7eb; research/grid768/tf_sweep.py, data/grid768/tf_sweep.json):
  the report768 system on M5..W1 for gold, silver and BTC, entries 2021-10..2026-09, same costs, swap and risk. Three-market account,
  A (adds, 0.25 % per unit) / B (one unit, 1 % per trade), total return and equity DD: M5 -100 % / -100 %; M15 -41 % (DD 81 %) / +42 %
  (DD 69 %); M30 +36 % (61 %) / +363 % (55 %); H1 +217 % (33 %) / +213 % (45 %); H4 +338 % (19 %) / +562 % (18 %); D1 +65 % (26 %) /
  +65 % (28 %); W1 +22 % (13 %) / +32 % (16 %). Equal-weight buy-and-hold of the three: +134 % (DD 41 %). Cost per trade in R: 0.16-0.46
  on M5, 0.07-0.19 on M30 / H1, rising again with swap on D1 / W1 (0.20-1.05). H4 has the best return per drawdown (B: CAGR 46 % / DD 18 %)
  but is the timeframe the grid selected; BTC M5 / M15 data start 2025-10 / 2023-11. Gold alone does better on M15 / M30 in total return
  (B +200 % / +98 %) with equity DD 58 % / 44 % against 11 % on H4.
- Cent account check (2026-10-01, research/grid768/cent_gold.py): gold-only trades of the report768 systems on XAUUSDc (real-account spec
  data/spec_real_XAUUSDc.json: 1 oz per lot, 0.01 minimum, so 0.01 lot = 1 USC per $1), sized in whole 0.01 lots from the balance. Gold now
  $4,153, ATR20 H4 $33.7, stop 2N $67 = 0.67 % of 10,000 USC per 0.01 lot. B (one unit, 1 %): fits; 2021-10..2026-09 +60 % (equity DD 8.4 %,
  worst run 8 losses = -847 USC) against +77 % with fractional lots. A (adds, 0.25 % per unit): the minimum lot forces 2.7x the target now,
  equity DD 21.7 % against 11.6 % fractional; needs ~27,000 USC at today's volatility.
- Cent account check extended (research/grid768/cent_account.py, was cent_gold.py): XAGUSDc / BTCUSDc assumed at 1/100 of the standard
  contracts (0.5 oz and 0.0001 BTC per 0.01 lot; not verified on the real account). 0.01 lot risks now gold 0.67 %, silver 0.83 %, BTC
  0.19 % of 10,000 USC. B (1 % per trade) from 10,000 USC, whole lots: gold +60 % (DD 8.4 %), gold+silver +124 % (DD 13.1 %),
  gold+silver+BTC +553 % (CAGR 45.6 %, equity DD 16.7 %, worst run 12 losses = -1,077 USC) against +562 % fractional. A (adds) from
  10,000 USC: gold+silver+BTC +263 % with DD 23.9 % (fractional +338 % / 19.2 %): the minimum lot over-sizes A until ~20,000 USC.

## G27K (2026-10-01; prereg docs/plans/G27K_PREREG.md, commit cd1cee2; research/grid27k/, data/grid27k/, results docs/plans/G27K_RESULTS_TH.md)
27,648 setups (context 8 incl. real yields / VIX / GPR / USD news x entry 8 x confirmation 3 x entry method 2 x stop 3 x exit 6 x adds 2 x
direction 2) on H4 for gold, silver and BTC in one account (operator's fixed choices), entries 2021-10..2026-09, H1-walked fills. Real: 87 %
positive, 9,390 basic passes; strict not claimable (bootstrap floor 0.001 vs Holm 1.8e-6). Best total R C1/D8/E1/F1/G2/H2/I2/J1 +836R
(CAGR 42 % at 0.25 % per unit); best CAGR C8/D3/E1/F1/G2/H2/I1/J1 53.6 % at 1 %. Channel-20 exit best, fixed TPs worst, market entry > limit,
no confirmation best, macro filters worst (real yields), long-only > both. Drift-preserving placebos (10): basic 361..14,456, best-of-grid
304..2,286R (2 of 10 >= real), best CAGR up to 53.6 %, 3y-choose/2y-check median +289R real vs -17..+271R; drift-free (5): basic 51..594,
best 136..824R. Real sits at the top of every placebo range (rank 1-3 of 11) but inside it. Other 14 markets, same period: 0 basic passes of
1,728, the #1 setup -426R. Added after the results (not pre-registered): 2017-01..2021-09 on the same three markets: grid median +2R, 213 basic;
the five-year top 20 by total R sit at the 99th percentile there (+272R median, CAGR 11 %, 15/20 positive) but almost all from BTC (gold and
silver ~0 or negative); the D7 pullback setups that made 2024-26 gold profits lose; rank correlation 0.21.
- Fix (2026-10-01): report768.account labelled balances in heap-pop order and then sorted by exit time, so when several positions closed at
  the same time (the last bar) the final row missed tied exits and CAGR / GHPR read low. Balances are now relabelled in exit order
  (also in cent_account.lot_account). 17-market report: CAGR A 36.6 -> 40.0 %, B 43.3 -> 47.2 %; net profit, drawdowns and every three- and
  single-market figure unchanged. G768 page republished. G27K page: research/grid27k/report27k.py + report27k_template.html (S1 best CAGR,
  S2 best total R, S0 the G768 system; gold + silver + BTC, each alone, the other 14 markets; five years 2021-10..2026-09).
- G27K profit factor (R-based) added to the grid and re-run (results otherwise identical). Of 19,459 setups with >= 100 trades, grouped by
  five-year PF, the median PF on 2017-01..2021-09 (not used for choosing): < 1.0 -> 0.96; 1.0-1.3 -> 0.97; 1.3-1.5 -> 1.10; 1.5-2.0 -> 1.33;
  2.0-2.5 -> 1.59 (69 % still profitable); 2.5-3.0 -> 1.53; 3.0-4.0 -> 1.09; >= 4.0 -> 0.62 (4 setups). Rank correlation 0.26. The very
  high-PF setups are mostly D7 pullbacks with adds and few trades, which lose before 2021. S1 PF 2.19 -> 1.51, S2 2.03 -> 2.30, S0 2.85 -> 2.36.
- G27K top three by CAGR together (research/grid27k/combine_top3.py): setups 2 and 3 share 239 of 280 entries, setup 1 shares about a third.
  Alone at 1 %: balance DD 13-17 %, equity DD 21-24 %, max leverage ~3x. Together at 1 % each: balance DD 38.0 %, equity DD 47.8 %, 9 open
  positions, 8.2x notional, worst month -24 %, a 28-loss run; close to setup 1 alone at 3 % (42.3 % / 53.0 %). Together at 0.33 % each: equity
  DD 20.9 %, CAGR 52.4 %, about the same as one setup at 1 %: little diversification between near-identical setups.
- Stress test (prereg docs/plans/STRESS_TOP3_PREREG.md, commit bf71b41; research/grid27k/stress_top3.py): gold / silver Candle Lab H1 before
  2016-08 then MT5, BTC from 2018-03; fresh $100k per window. 2011-09..2015-12 metals bear: setup 1 at 1 % -57 % (equity DD 59.8 %, low 43 %
  of start, PF 0.55, win 17 %; -60R of the -79R is price, not costs); three at 1 % each -87 % (DD 88 %, low 13 %: blown by the plan's 70 %
  rule); three at 0.33 % each -44 % (DD 47 %). 2013: -19 % / -46 % / -17 %. 2018: -11 % / -17 % / -6 %. 2022: +12 % / +31 % (DD 46 %) / +12 %.
  Whole 2009-09..2026-09: setup 1 CAGR 15.7 % with equity DD 60.9 % and 11.6 years under the 2011 peak; three at 1 % each CAGR 37.8 % with DD
  89.5 %; three at 0.33 % CAGR 17.2 %, DD 49.9 %. Setup 1 at 0.25 / 0.5 / 0.75 %: whole-history DD 20.5 / 37.0 / 50.3 %, CAGR 4.5 / 8.6 / 12.3 %.
