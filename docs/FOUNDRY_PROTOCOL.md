# Tool Foundry — protocol v1 (2026-09-30, frozen before any candidate is simulated)

Operator instruction (Thai, 2026-09-30): find a tool tonight; if none works, ask
why, find a fix and fix it without asking for approval; then find tools again
and backtest; propose one that works; otherwise loop — repeat without end
until the operator types "หยุด" (stop).

## The danger this protocol exists to control
An endless search on the same history always ends with something that
backtests well by chance (CLAUDE.md §1: no single-dataset tuning into fake
profit). So: every candidate ever simulated is written to the trial ledger;
the gates tighten as the cumulative count grows; the later periods are looked
at only through gates that spend a fixed error budget. A tool can come out of
the loop only as a **proposal for a Demo forward test**, never as a real-money
signal (CLAUDE.md §8; `data/DEMO_ORDER_PERMISSION.md`).

## Data, prices, costs
- Dukascopy H1 bid/ask 2003-05..2026-08. Signals and fills on the **mid**
  ((bid+ask)/2) OHLC; D1 bars built from H1 with the 22:00 UTC anchor.
- Entry at the open of the bar after the signal bar (or at a stop-entry level
  inside a later bar, filled at the worse of level and bar open).
- Stops/targets by first passage on the bar's high/low; if both are touched
  in the same bar the **stop** is assumed first; a gap through a stop fills at
  the bar open. Time exits at the close of the last bar.
- **Cost: 2.0 bp per round trip** (Exness today ≈ 1.0 bp: spread $0.26 +
  2 × $0.10 slippage at ~$4,600; doubled for safety), **stress 4.0 bp**.
  Dukascopy's own historical spread (11 bp in 2003 → 1.5 bp in 2026) is
  reported as a sensitivity, not the gate (it would test the 2003 broker, not
  today's).

## Regime cells (causal, fixed at each Friday 22:15 UTC cut, apply to the whole week)
- Volatility: WPWB B0 forecast ÷ median RV of the past 52 weeks, variance
  edges 0.75 / 1.5 → CALM / NORMAL / HIGH (HIGH includes EXTREME).
- Trend: 13-week return z (regime_atlas `trend_z`), ≤ −0.5 DOWN, ≥ +0.5 UP,
  else FLAT.
- 9 cells + ALL. A candidate = (family, parameters, direction rule, cell).

## Metrics per candidate and period
Trades n; mean net bp per trade; **week-clustered t** of net; year share
positive; **excess** over a matched random control (same direction, exit
rule, stop/target in the same ATR units, entry drawn at random from bars in
the same year × hour-of-day (H1) or weekday (D1) × regime cell; 5 replicates);
week-clustered t of the excess.

## Periods and gates
| stage | period | gate |
|---|---|---|
| DISC | 2003-05..2014-12 | n ≥ 60; net > 0; excess > 0; t_net ≥ 3.0; t_excess ≥ 2.0; ≥ 60 % of years with trades positive |
| VAL | 2015-01..2020-12 | net > 0; excess > 0; one-sided p(net) < 0.05 / M, **M = cumulative number of candidates ever sent to VAL** |
| HOLD | 2021-01..2026-08 | the j-th HOLD look ever (cumulative) spends α_j = 0.05 · 2^−j; net > 0 at 2.0 bp and at 4.0 bp; excess > 0; one-sided p(net) < α_j |

At most 20 DISC survivors per iteration go to VAL (highest t_net). A HOLD
pass is reported to the operator as a proposal with every number, the trial
count, and a Demo forward-test plan. No parameter may be changed after VAL or
HOLD; a changed candidate is a new candidate and starts again at DISC.

## The loop
1. Run an iteration (a registered batch of families × parameters × cells).
2. If nothing passes HOLD, **diagnose** from DISC/VAL numbers only
   (never from HOLD): gross ≤ 0 (no information) / gross > 0 but cost eats it /
   net > 0 but excess ≤ 0 (drift, not the setup) / DISC pass but VAL fail
   (decay or luck) / regime-specific sign flips.
3. Write the diagnosis and the fix it motivates in `docs/FOUNDRY_LEDGER.md`,
   register the next batch there **before** running it, run, repeat.
4. All numbers (passes and failures) stay in `data/foundry/trials.csv`.

The Risk Manager rules, the WPWB risk report and the Demo-only order
permission are unchanged by anything here.
