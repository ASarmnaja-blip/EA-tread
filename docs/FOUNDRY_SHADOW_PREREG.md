# Foundry selector shadow — pre-registration v1 (2026-09-30)

A forward, paper-only record of the best WPWB-native tool the Tool Foundry has produced, so that
evidence can come from weeks nobody has seen (every historical period is now used or sealed).
**No order is ever sent. Nothing here changes the risk report, `vol_scale` or any rule.** Zero
alpha is spent (a passive research watch, as for H-BP-VWAP in `docs/ALPHA_LEDGER.md`); any use
beyond logging needs its own pre-registration and the operator's approval.

## Frozen configuration SELECTOR-SHADOW-1 (= Foundry nomination 5, `docs/FOUNDRY_LEDGER.md`)
Menu `menu4` (176 variants: batches 1-2, CONT_UNION, longer holds, mirrors, hour-of-day, day-of-week;
code `research/foundry/families.py` at this commit). At each Friday 22:15 UTC cut C: score every
variant = sum of net R / sqrt(count) over its trades that exited in (C - 104 weeks, C], count >= 10;
select the top 20 % (>= 10 eligible). If the WPWB B0 forecast class of the coming week is CALM (or
unknown) -> NO TRADE. Each selected variant carries 1R per week, split across its trades that week.
Cost 2 bp per round trip. History of record: DISC 2003-14 t_R 2.89; VAL 2015-20 +0.034 R, t 1.48,
p 0.069 (failed the Foundry gate p < 0.0046); HOLD 2021-26 never opened.

## Data at the cut
Dukascopy H1 mid to 2026-08-31, then the live Exness H1 feed (bid + half the recorded spread;
measured offset vs Dukascopy mid $0.04). The selection is computed with every bar opening at or
after C removed (`engine.load_spliced(until=C)`).

## Log and scoring
`data/foundry/shadow/selector_shadow_log.csv` (fixed schema, append-only, a second run for the
same cut is refused); the selection is saved as JSON with its SHA-256 in the row. A row counts as
prospective (`FORWARD`) only if generated before Sunday 22:00 UTC after the cut; later runs are
`LATE`, skipped cuts `MISSED`; cuts before 2026-10-02 22:15 UTC are `DRY_RUN` in a separate file.
After a week ends, the selected variants' trades with entries in that week are simulated on the
same feed; week R = mean over selected variants of their mean trade R (NO TRADE weeks = 0).
Scores are recomputable in `selector_shadow_scores.csv`. Reported descriptively; power: at the VAL
effect (weekly Sharpe ~0.09) about 5-10 years of weeks would be needed for a 2-sigma result.

## Known bias, stated now
The first selection (dry run, week of 2026-09-25) holds 36 variants, mostly long or trend-following
(Donchian, SMA trend, long hour-of-day, turn of month): after the 2024-26 gold rally the selector is
long-biased. Its forward record will partly measure gold's direction until its ranking turns over.

## Operation
Runs in the Saturday 06:00 Bangkok job (`run_weekly.py`) after the outlook shadow; a failure is
logged and never blocks the risk report.

## Amendment 1 (2026-09-30, before the first forward cut)
The Foundry leak test found an optimistic bias in the stop-entry families (NR7 in menu4): a bar that
touched both levels was skipped; now the side nearer the bar's open is taken and the stop is checked
first. `families.py` is corrected, so SELECTOR-SHADOW-1 runs with the corrected menu4 from the first
forward cut. Recomputed history: DISC t_R 2.81, VAL +0.033 R, t_R 1.47 (was 2.89 / 1.48). The
2026-09-25 dry-run selection was made before the fix and is not scored.

## Amendment 2 (2026-09-30) - second paper record HOD21-SHADOW-1
Rule frozen in `research/foundry/hod21_shadow.py`: at every Exness H1 bar opening 21:00 UTC (winter
only) in a WPWB NORMAL/HIGH week, paper long at the ask + $0.10, stop 2 ATR14 on bid lows, else exit at
the bid close of the 00:00 UTC bar - $0.10, swap $0.5493/oz/night (x3 Wed). Trades from the week
starting 2026-10-02 22:15 UTC, recorded once each after they close, in
`data/foundry/shadow/hod21_shadow_trades.csv`. History of record: Foundry Track B pass before swap,
failed after swap (ledger). A check on 2021-26 history with the same code gave 301 trades, +2.88 bp,
+0.028 R, carried by 2026. Zero alpha, no orders.
