# WRWR Family 2 — structure, levels and calendar candidates: pre-registration (2026-09-30, before any table is built)

Why: the zoo (31 indicators) is one hypothesis class. The operator asked for the other tool groups (SMC: FVG / order block /
BOS / CHoCH / liquidity sweep; levels: previous day/week extremes, pivots, round numbers, gaps; calendar: London fixes, NY
open, turn of month; volatility: inside day / NR7 / squeeze). Family 2 adds them as NEW candidates and is judged by exactly
the gates of docs/WRWR_MANIFEST.md (contract v6): same simulator (C2), costs (C4), selector family (144 configurations),
random-router benchmark (same exit configuration, same pool), studentized Reality Check, PBO, cost gate and the same staging
rule. Family 2 is a separate family (its own multiplicity accounting); pooled zoo + Family 2 is only ever a later, separately
registered step. No parameter below is tuned; every constant is fixed here.

## Signals (evaluated at a bar's close t, entry at the next bar's open; `ATR` = 14-bar ATR including bar t; all levels come
from COMPLETED days / weeks with the 22:00 UTC day anchor and the Friday 22:15 UTC week cut)
Each signal gives a long event and a short event; every candidate is run FOLLOW and FADE.
| id | long event | short event |
|---|---|---|
| fvg_form | low_t > high_{t-2} (bull fair value gap formed) | high_t < low_{t-2} |
| fvg_retest | first bar after creation (age 1..20 bars) whose low <= upper edge of an unfilled bull FVG and close > its lower edge (filled = price traded to the lower edge) | mirrored |
| bos | close_t > last confirmed fractal(2,2) swing high (confirmed 2 bars late) while the prior structure state was up | close_t < last swing low while the state was down |
| choch | structure state flips from down to up (close beyond the last swing high) | flips from up to down |
| sweep_pd | low_t < prior-day low and close_t > prior-day low | high_t > prior-day high and close_t < prior-day high |
| sweep20 | low_t < 20-bar low (excl. t) and close_t > that low | mirrored with the 20-bar high |
| disp | range_t > 2 ATR_{t-1}, body > 60 % of range, close in the top 25 % of the range | mirrored |
| ob_retest | after a bull displacement bar d: the most recent bearish bar among d-1..d-3 is the order block [low, high]; first later bar (age <= 30) with low <= block high and close >= block low, invalidated by a close below the block low | mirrored |
| pd_break | close_t > prior-day high and close_{t-1} <= it | close_t < prior-day low and close_{t-1} >= it |
| pw_break | close_t > prior-week high and close_{t-1} <= it | below prior-week low |
| pivot_x | close crosses above the classic pivot P = (H+L+C)/3 of the prior day | crosses below |
| round50_x | floor(close / 50) rises | falls |
| round100_x | floor(close / 100) rises | falls |
| gap_day | first bar of a trading day whose open gaps up by > 0.5 ATR_{t-1} from the prior close (event at that bar's close) | gaps down by > 0.5 ATR |
| fix_am | the NEXT bar contains the 10:30 London time (DST-aware): long | none (FADE = short at the fix) |
| fix_pm | the next bar contains 15:00 London | none |
| ny_open | the next bar contains 09:30 New York | none |
| tom | the next bar is the first bar of the last trading day of the month | none |
| nr7_break | prior day has the narrowest range of 7 days and close_t crosses above its high | crosses below its low |
| inside_break | prior day is an inside day and close_t crosses above its high | crosses below its low |
| squeeze_break | Bollinger(20, 2) width / its 120-bar median < 0.7 at t-1 and close_t crosses above the upper band | crosses below the lower band |
Clock signals (fix_am, fix_pm, ny_open) exist on H1 only; tom on H1 / H4 / D1; all others on all three timeframes.
Session variants (entry-bar UTC hour): ALL, ASIA 00-07, LONDON 07-12, NY 12-17, on H1 only; H4 / D1 use ALL.

## Candidates and family
Same exits (9 reward:risk shapes), stops 1 and 2 ATR, holds 24 / 72 (H1), 6 / 30 (H4), 5 / 20 (D1), FOLLOW / FADE, as the zoo
tables (signals.build, `sigset="f2"`). Pools H1 / H4 / D1 / H1+H4+D1 of these candidates; the 144 selector configurations of
the manifest apply unchanged. Potential-signal tables: `data/wrwr/tables_XAUUSD_<TF>_f2.npz` (C5 metadata as the zoo tables).

## Checks before any result is read
Leak test of every signal (garbage after bar j, H1 / H4 / D1, three cut points); unit tests of each definition on synthetic
series (a constructed gap, sweep, FVG, order block, break, calendar bar); tables rebuilt from scratch with C5 verification.
EOF
git add docs/WRWR_FAMILY2_PREREG.md && git commit -q -m "WRWR Family 2 (SMC / levels / calendar / volatility candidates) pre-registered before any table is built

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>" && git log --oneline -1