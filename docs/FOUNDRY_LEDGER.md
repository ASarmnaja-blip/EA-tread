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
