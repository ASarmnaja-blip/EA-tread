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

## Amendment 7 (2026-09-30, after Codex round 12, before the first forward week) - all 14 findings accepted
`docs/CODEX_R12_FOUNDRY_FORWARD.md`.
- **Status of the historical tracks (R12-3, R12-6, R12-7).** Under `docs/ALPHA_LEDGER.md` rule 1 all
  data up to 2026-09-28 is development evidence. The Foundry's HOLD "alpha" (5 looks, 0.0484) was an
  internal screening budget, not project confirmatory alpha: a HOLD pass could only have sent a tool to
  a forward paper test, never to Demo promotion. Amendments 3-4 changed rules after seeing failures;
  Track B and the current-era tests are **exploratory**, and every historical p-value in the ledger is
  approximate (week clusters are treated as independent although multi-day holds, rolling rankings and
  regime persistence create dependence across weeks). Only forward weeks confirm.
- **e-process (R12-1).** E_t = prod(1 + 0.1 * week R), no clipping; null = the conditional mean of
  week R given the past is <= 0 each week; valid while week R > -10 R, otherwise the candidate fails
  (E = 0). lambda is read from the frozen panel file.
- **Immutability (R12-2, R12-5, R12-11).** Forward scores are append-only: each completed week (or
  trade) is scored once, after all of its trades have closed, with a hash of the bars used; a change
  of code after freezing stops panel scoring; HOD21 trades recorded > 8 days after their exit are LATE
  and not scored; a late first selector run logs MISSED cuts.
- **Code fixes:** HOD exits at the last bar opening within 3 h of entry (the 00:00 bar; Exness has no
  22:00 winter bar and Friday entries no longer span the weekend) (R12-4); swap rollover at 17:00 New
  York (DST-aware), each night at its own date's rate, also in trailing-stop controls and the selector
  shadow (R12-10); matched-control outcomes stay aligned with their own trades (R12-13); seeds from
  SHA-256 instead of Python's salted hash (R12-13); the leak test also compares targets and exit bars
  and uses more cut points (R12-12).
- **Splice (R12-9).** The Dukascopy -> Exness spliced series is a defined paper index (bid + half the
  recorded entry spread, flat 2 bp cost), not broker-replicated execution.
- The panel was re-frozen with the corrected code (the first freeze is archived in
  `data/foundry/shadow/archive/`); no forward week had been observed.

## Amendment 8 (2026-09-30, before the first forward week)
The panel e-process becomes a mixture: E_t = mean over lambda in {0.05, 0.1, 0.2} of
prod(1 + lambda * week R) (an average of e-processes is an e-process; a component whose factor is
<= 0 is set to 0). Threshold unchanged (500). Panel re-frozen with the same five candidates (the
fixed-lambda freeze is archived). Power check, replaying the scoring code over the 107 in-sample
nomination weeks (not evidence - these are the weeks the candidates were picked on): the best E
reached 5.6 (INSIDE_DAY_t2), the others 1.2-2.0. At these effect sizes confirmation at
alpha 0.002 needs roughly 8+ years of forward weeks; the panel is a long-run record, not a fast gate.

## Amendment 9 (2026-09-30) - frozen code snapshots, and forward panel 2
- Every forward panel is scored from its own frozen copy of families.py / engine.py /
  forward_panel.py (`research/foundry_frozen_<label>/`), whose SHA-256 is in the panel's JSON. Panel 1's
  snapshot is taken from commit 8e0fb93 (hash verified equal to its JSON). Later edits to
  `research/foundry/` therefore cannot change or stop an existing panel.
- **Panel 2 (H-FOUNDRY-PANEL-2, alpha 0.005):** one pre-specified candidate, SHOCK_FADE_k2.5_h72_s3.0
  (fade an H1 bar whose close-to-close move exceeds 2.5 ATR, enter at the next open, exit at the last
  bar opening within 71 clock hours, stop 3 ATR, one position at a time, all weeks). Chosen as the
  CENTRE of the one contiguous positive ridge in `shock_fade_surface.py` (k 2.5-3.0 x hold 72 h x stop
  2-4 ATR positive in both 2021-23 and 2024-26; ~0 in 2015-20; negative in 2003-14), not its best
  point. It is a recent-era effect selected on seen data: nomination only. Same mixture e-process,
  threshold 1 / 0.005 = 200, forward from the week of 2026-10-02 22:15 UTC.

## Amendment 10 (2026-09-30) - the six candidates as one portfolio (H-FOUNDRY-PORTFOLIO-1, alpha 0.01)
Weak, weakly correlated edges confirm faster together. Seen-data estimate 2021-26 (selection-biased,
so optimistic): weekly-R correlations between candidates -0.10..+0.19 except NR7/INSIDE_DAY 0.47 and
the two shock fades 0.43; single-candidate annual Sharpe 0.33-1.04; equal-risk portfolio 1.33, i.e.
~250 forward weeks to t 2.9. Portfolio week R = mean of the six candidates' weekly R (0 for a
candidate without trades) for weeks that all six have recorded; mixture e-process as in Amendment 8;
threshold 1 / 0.01 = 100. Frozen aggregator `research/foundry_frozen_portfolio1/portfolio.py`, hash
in `data/foundry/shadow/portfolio1.json`, hash-checked by the dispatcher before each run. This is a
separate hypothesis from the single-candidate panels (overlapping evidence; separate allocation).

## Amendment 11 (2026-09-30, after Codex round 13, before the first forward week) - all findings accepted
`docs/CODEX_R13_FOUNDRY_FORWARD.md`. Every forward record was re-frozen (earlier freezes archived in
`research/foundry_frozen_archive/` and `data/foundry/shadow/archive/`; no forward week had been scored).
- **Valid test (R13-1).** g = clip(week R, -2, 2); null: the conditional mean of g given the past is <= 0
  each week (a robust, clipped mean - stated as such); E = mean over lambda in {0.05, 0.1, 0.2, 0.4} of
  prod(1 + lambda g). Every factor is >= 0.2, so no zeroing is ever needed and E is a nonnegative
  supermartingale under the null for dependent weeks. Raw week R is recorded beside it.
- **No truncated trades (R13-2).** A panel week is scored only when the feed extends 6 days past its
  end (max hold 72 h + weekend); the selector shadow waits 30 days (longest menu hold: 20 D1 bars).
- **Frozen implementation (R13-3).** Each snapshot holds engine, families, forward_panel, vol.py,
  build_all_tf.py, external_traces.py, a frozen 2y-yield series and a FROZEN marker that makes engine
  import these copies first; the swap markup is a constant (0.02 %/yr). The JSON stores a SHA-256 over
  every snapshot file. Still unfrozen, stated: `research/wpwb_weekly/bars.py` (Exness data access) and
  the data files themselves.
- **Append-only, validated (R13-4, R13-5).** Rows carry a hash chain (canonical formatting, stable
  across CSV round trips); before appending, the file must have the frozen schema, only the frozen
  candidate names, contiguous weeks from the forward start, and an intact chain - otherwise scoring
  stops. A week with < 80 H1 bars is DATA_GAP and a week scored > 8 days after it became scorable is
  LATE; both get factor 1 (no bet), a choice that does not depend on the outcome. A frozen candidate
  missing from the universe stops scoring. The portfolio requires exactly one row for each of its six
  named components per week; if any component is not OK the week is NO_BET.
- **Shadows (R13-6).** The selector's week R now counts selected variants without trades as 0; HOD21
  records a bar hash and seals occurrences with no 00:00 exit bar (NO_EXIT_BAR).
- Replay test on a temp copy (2024-09..2026-08): scoring, re-running (0 new rows) and tamper detection
  (a changed value stops scoring) behave as specified.

## Amendment 12 (2026-09-30, after Codex round 14, before the first forward week)
`docs/CODEX_R14_FOUNDRY_FORWARD.md`: 3 fixed, 4 partial, 3 new defects - all addressed, then every
forward record re-frozen (the R13 freeze archived as `*_v3_R13`).
- Settlement completeness: a week is DATA_GAP (factor 1) if it has < 80 H1 bars or any gap > 72 h in
  the week plus its 6-day settlement window, so a truncated hold cannot be finalised.
- Snapshot imports: engine binds the snapshot's own vol.py, build_all_tf.py and external_traces.py in
  sys.modules before anything can prepend a live directory (verified: the snapshot's engine.V resolves
  to the snapshot's vol.py).
- Validation: candidates must be in lockstep (equal row counts), and the file must re-validate after
  every append; the dispatcher holds a lock and runs the portfolio only if every panel succeeded
  (fail-closed); the portfolio validates each component file's hash chain.
- Hashing: every field (including recorded_utc) is hashed; numbers as float.hex; files are written with
  17 significant digits and read with round-trip float parsing (tested: a 1e-9 change, a timestamp
  change, and a single dropped row are all detected).
- LATE: only when the job did not run at all during the 8 days after the week became scorable (from an
  append-only run log); a late-arriving feed with the job running normally is not LATE.
- Residual limitation, stated: deleting the newest week for every candidate at once is not detectable
  from the file alone (the week would be re-scored from the same data). The weekly Thai summary prints
  the chain-tip hashes so an outside record exists; committing them is the operator's choice.

## Amendment 12b (2026-09-30, after Codex round 15)
`docs/CODEX_R15_FOUNDRY_FORWARD.md`: 9 of 10 R14 items fixed; the remaining partial item is the stated
limitation (deleting the newest week of every candidate at once). One new defect fixed: a week is LATE
unless a run occurred within the FIRST 8 days after it became scorable (the search no longer extends to
the present, so a late week cannot turn OK afterwards). Records re-frozen (R14 freeze archived `*_v4_R14`),
manifest re-issued.

## Amendment 13 (2026-09-30) - news reaction study and forward panel 3
`research/foundry/news_reaction.py` (descriptive, 2022-26, 715 scheduled HIGH USD release times with a
trailing-sigma surprise): 14 of 48 case x hold x trade rows are positive in both halves (~12 by chance).
Two structured results: FADING a move that REJECTS the news (price against the surprise) loses heavily
(-0.28..-0.61 R, t -3.2..-6.4) and following it earns only ~+0.1 R (whipsaw); FADING a move that
ACCEPTS the news (> 1 ATR in the implied direction) over 24 h earns +0.23 R (t 1.75, +0.16 / +0.30 in
2022-23 / 2024-26). **Panel 3 (H-FOUNDRY-PANEL-3, alpha 0.005, threshold 200):**
NEWS_ACCEPT_FADE_m1.0_h24 - after an accepted release-hour move > 1 ATR (combined |z| >= 0.5, no
conflicting series), fade it from the next bar's open, exit within 23 clock hours, stop 2 ATR, one at a
time; 113 trades 2022-26, positive every year (seen data, nomination only). Its snapshot also freezes
`calendar_feed.py` (sign table, trailing sigma); the calendar data itself is refreshed weekly by the
Saturday job and is not frozen - a revised 'actual' would change a trade, stated as a limitation.

## Amendment 14 (2026-09-30, before the first forward week) - floor instead of clip
Computing the historical expectation for the Auditor showed that clipping week R at +/-2 changed the
tested quantity for fat-right-tailed candidates (SHOCK_CONT_k2_h48~INV weekly mean +0.142 R raw but
+0.027 clipped; SHOCK_FADE +0.205 vs +0.068; NEWS_ACCEPT_FADE +0.052 vs +0.016). Validity needs only a
lower bound, so g = max(week R, -2) (floor only; historical weekly minimum -1.1 R, so g equals the raw
week R in every week of 2021-26). Factors 1 + lambda g >= 0.2 for lambda <= 0.4. Null: the conditional
mean of the floored week R <= 0. Panels 1-3 and the portfolio re-frozen (R15 freeze archived
`*_v5_R15`); manifest re-issued. The Auditor section of the Thai weekly summary compares each
candidate's forward mean with its 2021-26 expectation (`data/foundry/shadow/expectations.json`) and
flags a shortfall beyond 2 standard errors after >= 8 weeks - a warning, not a test.
