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

## Amendment 1 (2026-09-30, after batch2, registered before batch3)
Diagnosis of batches 1-2: continuation is positive almost everywhere but t stays below 3 because
per-trade variance in bp is dominated by the 2008-2013 high-volatility years. A trader sizes to a
fixed risk per trade, so from batch3 on the **primary statistic is in risk units**:
R = net bp / stop distance bp (fixed-risk sizing). DISC gate: n >= 60, net bp > 0, net R > 0,
excess > 0, t_R >= 3.0, t_excess_R >= 2.0, >= 60 % of years positive in R. VAL/HOLD p-values use
t_R and additionally require net bp > 0 (and net at 4 bp > 0 for HOLD). bp numbers stay reported.
Batches 1-2 keep their original bp gate. Re-scoring a family under the new metric is a new look and
counts as new candidates.

## Amendment 2 (2026-09-30, after batch5, before any nominated candidate is scored in VAL)
The DISC gate (t_R >= 3) is a filter for efficiency; the real tests are VAL and HOLD, which a DISC
selection cannot contaminate. After batches 1-5 the only consistent finding (continuation beats
matched random entries, t_excess_R up to 4.0) sits at t_R 2-2.9, below the filter. So: **at most one
diagnosis-nominated candidate per iteration** may go to VAL directly if in DISC t_R >= 2.0,
t_excess_R >= 3.0 and net bp > 0. It increments M exactly like a DISC survivor; the VAL and HOLD
gates are unchanged. Nominations are logged in state.json and never repeated.

## Amendment 3 (2026-09-30, after batch26, before any HOLD number of the chosen candidate is seen)
VAL (2015-20) was designed as a "must also work in a different era" gate. CLAUDE.md section 1 says
the operator does NOT require a tool to win in every era, only in the current one, provided it is
checked on a recent period not used for tuning, live simulation and real costs. Batches 1-26 show
one repeated pattern: breakout/compression/continuation tools pass DISC (2003-14, a high-volatility
gold bull era) and are flat in VAL (2015-20, a quiet era); 2024-26 is again a high-volatility bull.
**Current-era route:** at most one candidate per iteration that passed the FULL DISC gate but failed
VAL may be tested on HOLD (2021-01..2026-08), spending the next alpha_j = 0.05 * 2^-j exactly like any
HOLD look, with the same HOLD gate (net > 0 at 2 and 4 bp, excess > 0, p < alpha_j). A pass is
reported as **era-specific** (failed 2015-20), needs an explicit on/off rule, and goes only to a
Demo/paper forward test - never to real money without the operator.

## Amendment 4 (2026-09-30) - Track B, recent-era discovery
Every Track A finding came from 2003-14 and decayed (current-era test 1: NR4 in 2021-26 -0.003 R).
CLAUDE.md section 5 asks for recent data first. Track B re-runs the search with DISC = 2015-01..
2020-12 (the old VAL: burnt as validation, usable for discovery), VAL = 2021-01..2023-12,
HOLD = 2024-01..2026-08, then the forward shadow. Same gates (R units), same leak test. Track B has
its own VAL count M (state in data/foundry/trackB/) but **shares the global HOLD-look sequence**
alpha_j = 0.05 * 2^-j with Track A (looks 1-3 already spent), so the total error budget stays 0.05.
Known contamination: 2021-26 was seen by Track A for NR4_t1 NOTCALM and the void GVZ_JUMP rows, and
the wider project mined 2021-26 on Exness M5 (Parts 18-50); Track B results carry that caveat.

## Amendment 5 (2026-09-30, after the HOD_21L audit)
Every gate is applied **after swap** for positions held across the daily rollover: long swap per
night = (US 2y yield + markup) / 365 of price, markup calibrated so today's value equals the measured
Exness swap ($0.5493/oz/night), x3 on Wednesday; before 2016 the 2016-01 yield is used. Short swap is
set to 0 (not measured; conservative only if the true short swap is positive). A candidate that
passes only without swap is reported as failed.

## Amendment 6 (2026-09-30) - forward panel: history nominates, forward weeks confirm
The historical HOLD budget is spent (5 looks, 0.0484 of 0.05). New rule: candidates are NOMINATED
from the most recent data (CLAUDE.md section 5) and CONFIRMED only on forward weeks.
Nomination (one-time, `research/foundry/forward_panel.py --nominate`): every variant of trackB1 +
overnight_split, cells ALL / NOTCALM / HIGH, after 2 bp cost and swap; score t_R on the last 104
weeks of data; keep only those with net R > 0 and net bp > 0 there AND mean R > 0 on 2021-01..2024-08;
take the top 5 by t_R from distinct families; freeze names, cells and a SHA-256 of the code.
Confirmation: from the week starting 2026-10-02 22:15 UTC, weekly R = mean R of the candidate's
trades entered that week (0 if none); e-process E_t = prod(1 + 0.2 * clip(week R, -1, 1)); a
candidate is confirmed when E_t >= 1 / (0.01 / 5) = 500. Alpha 0.01 for the whole panel, recorded
in `docs/ALPHA_LEDGER.md` as H-FOUNDRY-PANEL-1. Paper only; a confirmed candidate goes to the
operator as a proposal for a Demo test, never straight to real money.
