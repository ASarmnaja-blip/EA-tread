# WPWB walk-forward champion backtest — pre-registration (2026-09-30, written before the first run)

Operator 2026-09-30: "จับ backtest เดินผ่านกราฟทีละแท่งด้วยเทคนิค wpwb". Follows the era-champion result
(FOUNDRY_LEDGER "Era champions"): champions picked on 5-6-year eras do not carry to the next era, so this test picks
weekly, from short trailing windows, and scores only the week after the pick. Descriptive, no alpha spent
(ALPHA_LEDGER unchanged; the historical HOLD budget is spent). Any rule that looks good goes to a paper forward record
only; nothing here authorises an order.

## Data and candidates (frozen before running)
- Dukascopy H1 mid 2003-05..2026-08 (`engine.load()`), cost 2 bp per round trip + swap, stop-first on same-bar ties.
- Signals: the 31 indicator-zoo signals (`indicator_zoo.signals()`, evaluated on bar close, entry at the next bar's open)
  x FOLLOW/FADE. Leak check before the run: signals up to bar j must not change when every bar after j is garbage.
- Exit sets: stop k ATR(14) with k in {1, 2}; target = RR x stop for RR 1:1, 1:2, 1:3, 1:5, 1:10 and stop / RR for
  2:1, 3:1, 5:1, 10:1; max hold {24, 72} H1 bars. 62 x 2 x 9 x 2 = 2,232 candidates.
- Bar by bar, one position per candidate: a candidate takes a signal only after its previous trade has exited
  (actual exit bar, not the maximum hold). Every candidate runs as a shadow the whole time.

## WPWB layer (frozen spec, `research/wpwb_weekly/vol.py`)
- Week k = (cut_k, cut_k + 7 d], cut = Friday 22:15 UTC. Regime cell of week k = WPWB vol class (EWMA forecast /
  52-week median RV: CALM/NORMAL/HIGH) x 13-week trend (DOWN/FLAT/UP), known at cut_k (`engine.regimes`).
- Size: vol_scale_k = clip(sqrt(B_REF / F_k), 0.50, 1.00), forced to 0.50 when the trailing-26-week calibration
  alarm fails, is undecidable, or the previous week is DATA_INVALID (`vol.effective_scale`). Size only reduces.

## Selection at each cut (no look-ahead)
- Evidence = trades of each candidate that EXITED before cut_k (exit bar close time <= cut_k).
- Score windows: last L weeks, L in {4, 13, 26, 52}; and SAME-CELL = trades that exited in weeks of the last 104 with
  the same WPWB cell as week k. Min trades in the window: 5 (L=4), 10 otherwise.
- Score: MEAN (mean net R) or LCB (mean - 1 standard error).
- Champions: the top 1 or top 2 candidates by score. NO TRADE for the week if the best score <= 0.
- 5 windows x 2 scores x 2 champion counts = 20 rules, all reported.
- Realised result of week k = net R of the champion's shadow trades that ENTER in week k (they may exit later), x
  vol_scale_k for the sized figure. Unsized R also reported. Champions of consecutive weeks can overlap briefly.

## Baselines and read-out
- ALL: equal-weight mean of every eligible candidate's trades entered in week k.
- RANDOM-PICK null: each week, a uniformly random eligible candidate (same trade/no-trade weeks as the rule),
  1,000 repetitions; p = share of repetitions with total R >= the rule's total.
- Report per rule: weeks traded, trades, mean R per trade, total R, R per year, share of weeks positive, week-clustered
  t, per era (2003-08, 2009-14, 2015-20, 2021-26), sized and unsized, and the RANDOM-PICK p.
- Reading: 20 rules on seen data; a p below 0.05 / 20 = 0.0025 is needed before calling anything more than noise,
  and even then it is only a nomination for a paper forward record.
