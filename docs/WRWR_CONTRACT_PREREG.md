# WRWR contracts and gates — pre-registration (2026-09-30, before any code change; answers Codex R18)

Scope (R18-12): WRWR is a **weekly higher-timeframe router + risk overlay** for XAUUSD on H1 / H4 / D1. It does not
complete the CLAUDE.md M5/M15 signal engine: M5/M15 failed the unseen 2009-2020 holdout (FOUNDRY_LEDGER) and are not
signal timeframes; they may later be used only for execution refinement under a separate pre-registration.
All rules below are frozen before implementation; any change is an amendment with a reason, written before re-running.

## C1 Time (R18-2)
- Cut k = Friday 22:15:00 UTC (`engine.regimes` cuts). A decision at cut k may use only data with timestamp <= cut k.
- Entries of week k: entry-bar OPEN time in the half-open interval [cut_k, cut_{k+1}).
- Realised results known at cut k: trades with exit time <= cut_k, where exit time = close time of the exit bar
  (bar open + bar length). Bars and trades are attributed by these two rules only.
- Synthetic tests (must pass before any rerun): for M5, M15, H1, H4, D1 bars and exits one second before, exactly at and
  one second after a cut, assert week assignment and decision visibility.

## C2 One event-driven portfolio simulator (R18-1, B1-B5)
- Per candidate, a trade table of **every** signal simulated independently (entry at the next bar open; exit at stop,
  target or max hold; stop-first on same-bar ties; gap-through-stop at the open) with entry_time, exit_time, gross,
  cost and swap. Selection statistics keep today's definition (the candidate's one-position shadow record, exits <= cut).
- Deployable systems have m in {1, 2} champions (CLAUDE.md §3); m > 2 is a research ensemble, reported, never deployed.
- At cut k the champion set C_k is chosen. A champion enters its own signal in week k only if it has no open live
  position, the portfolio open initial risk plus the new trade stays <= 3R, and the week's realised loss is > -3R.
- Handover: a position opened while c was champion stays open until its own exit, whoever is champion later.
- Sizing: risk = f x equity just before entry x vol_scale_k (C3); lots = risk / (stop distance x contract size), rounded
  DOWN to the 0.01 step; below 0.01 lot the trade is skipped and logged (never rounded up). Equity updates at each exit.
  Reported for f = 0.5 / 1 / 2 %, starting equity $10,000.
- Every decision (selection, equity filter, walk-forward-over-configs yearly choice) uses realised-by-cut results only;
  entry-cohort tables are descriptive and never feed a decision. The weekly calendar is built from cuts and
  `cell[k] != ""` only (no `EN > 0` filter; a zero-entry week is an explicit zero).
- The same simulator serves BASE, the optimiser, holdouts, compounding and the forward record.

## C3 Causal vol_scale (R18-3)
- Historical: B_REF_k = median weekly RV of the valid weeks in the 260 weeks before cut k (expanding until 260 exist,
  minimum 52), vol_scale_k = clip(sqrt(B_REF_k / F_k), 0.5, 1.0) with the existing calibration fail-safe. Results are
  also reported unsized. Forward: the frozen spec B_REF (WPWB_RISK_REPORT_SPEC) is kept, as it is known now.
- RV always from H1 bars; `vol.weekly_rv` gains an explicit bar-length argument and is never fed H4/D1 bars.

## C4 Costs and swap per symbol (R18-5)
| symbol | contract | lot min/step | round-trip cost (bp) | swap per night (MT5 read 2026-09-30) |
|---|---|---|---|---|
| XAUUSD | 100 oz | 0.01 / 0.01 | max(2.0, recorded spread_bp of entry bar + 1.0) | long -547.8 pt = -$0.5478/oz; short 0; x3 Wednesday; scaled by US 2y + markup (engine) |
| XAGUSD | 5,000 oz | 0.01 / 0.01 | max(4.0, spread_bp + 1.0); spread = recorded Exness bar spread 2023+, before 2023 the 2023-26 median by hour x 1.5 | long -7.7 pt = -$0.0077/oz; short 0; x3 Wednesday; same US 2y scaling with its own markup |
- Stress: +2 bp on every trade. Same-bar SL/TP ties: stop-first is the primary; tick/M1-resolved (HistData, 2009+)
  is a sensitivity, and uncovered years keep the stop-first bound.

## C5 Caches and data (R18-4)
- Every cache stores schema version, sha256 of the producing code (engine, zoo, walk-forward), of the input arrays, of
  the cut vector, cost version and data end; loaders reject any mismatch; stacking TFs asserts identical cuts / widths.
- Pools by explicit TF lists (`np.isin`); labels carry bar units (D1 hold 5/20 = days).
- Splice checks (Dukascopy -> Exness, HistData -> Exness): no duplicate timestamps, no gap > 4 days outside weekends,
  |log return| at the seam < 10 x median, spread continuity, source offset stable within +/- $0.50.

## C6 Nulls and gates (R18-7, R18-8)
- **Primary selection-skill test:** weekly excess e_k = R_system,k - B_k, B_k = the expected result of a random eligible
  champion with the same exit config (computed exactly from the trade tables with the same portfolio rules). Hansen SPA
  / White reality check over the whole deduplicated configuration family with a stationary bootstrap of weeks
  (Politis-Romano), mean block 10 weeks (sensitivity 4 and 26), K = 999, recentred under the null.
  BASE alone (one pre-registered hypothesis): one-sided bootstrap p <= 0.05 and a positive 95% lower bound.
  Family claim: SPA p <= 0.05. Monte Carlo p = (1 + #null >= real) / (K + 1).
- **Supporting path null:** week-block sign flips of H1 normalised increments (all bars of a week flipped together),
  everything recomputed (features, regimes, candidates, selection), H1 only, deployable grid, K = 199, run in the
  background; descriptive, not a start gate. A no-edge rule is expected to be NEGATIVE after cost, not 0.
- **PBO (CSCV):** 16 contiguous blocks with a 1-block purge, on the corrected causal matrix. Upper 95% bound <= 0.20 =
  robust; 0.20-0.50 = inconclusive -> shadow only; lower bound >= 0.50 = stop.
- **Cost gate:** at base cost the one-sided 95% stationary-bootstrap lower bound of mean weekly net R > 0; at +2 bp a
  positive point estimate and max DD <= 1.25 x the base-cost DD.
- Positive-year shares are reported with binomial and block-bootstrap intervals, never as a stand-alone pass.

## C7 XAGUSD (cross-asset robustness, not an XAU holdout) (R18-5, R18-8)
- Download now (approved with the plan), keep unopened until C4 costs, the trade tables and the rules below are frozen.
- Primary: BASE unchanged; one-sided Monte Carlo p <= 0.05 against the C6 benchmark and a positive lower bound.
- Secondary: at most 3 configurations chosen on gold only by this frozen rule: the 3 deployable (m <= 2) configurations
  with the highest gold stationary-bootstrap 95% lower bound of mean weekly excess R after all fixes; tested with
  maxT / Holm, familywise p <= 0.05.

## C8 Forward record (R18-10)
- Payoff = the actual weekly portfolio R under C2, floored at g = max(R, -4) where the Risk Manager enforces -3R per week;
  the floor binds only on gaps beyond stops, and every binding week is reported. The claim is about this payoff.
- e-process: mixture over lambda in {0.05, 0.10, 0.20} (1 + lambda g >= 0.2 > 0), DATA_GAP weeks factor 1.
- alpha (needs the operator's word, from the 0.02 reserve): H-WRWR-BASE 0.005 (e >= 200); H-WRWR-SEL 0.005 for the single
  configuration chosen by the C7 rule, only if C6 and C7 gates pass; otherwise SHADOW with no alpha.
- Weeks 13 / 26: safety only — stop if drawdown exceeds the 97.5th percentile of the horizon-specific forward drawdown
  simulated by stationary bootstrap of the corrected backtest; no promotion before week 52.
- Week 52 promotion discussion: e >= 1/alpha, positive anytime-valid lower confidence bound on mean g, demo execution
  quality (median slippage <= 0.10 R, fills >= 95%), then per-order operator confirmation for any real money.

## C9 Roles (R18-12)
Separate scripts and artefacts per cut: analyst (regime, vol, news JSON) -> strategist (champions with candidate
hashes and scores) -> risk manager (approve / reject each signal with rule IDs; rules frozen, never changed while a
position is open) -> execution (demo order / fill / spread / slippage log) -> auditor (scores, drift, e-process).

## C10 Targets (R18-11) — effect-size goals, not pass criteria (Calmar = R per year / max drawdown in R)
| tier | R / year | max DD | Calmar |
|---|---|---|---|
| usable | >= 10 R | <= 15 R | >= 0.5 |
| good | >= 20-25 R | <= 15-20 R | >= 1.0 |
| exceptional | >= 40-50 R | <= 20-25 R | >= 1.5 |
300 R/year has no supporting evidence; the evidence-supported expectation today is "unknown, plausibly zero".

## C11 Sieve (R18-9) — pre-registered later as SIEVE Amendment 3, before any real scan is read
Recompute every price-derived regime and mask on each placebo path; centre continuous exposures within the tested
mask (causal trailing mean); time flags as flagged-minus-matched-unflagged contrasts in the same month, mask and
volatility bucket; non-overlapping horizon subsampling or HAC (lag = h); familywise maxT / Westfall-Young with >= 999
week-block placebo seeds.
