# WRWR contracts and gates — pre-registration v4 (2026-09-30, before any code change)
v1 answered Codex R18, v2 R18b, v3 R18c, v4 the two BLOCKING items and the MINOR notes of R18d
(`docs/CODEX_R18d_MASTER_PLAN.md`).
This document and MASTER_PLAN Amendments 1-2 supersede every conflicting rule in the plan body.

**Scope.** WRWR = weekly higher-timeframe router + risk overlay for XAUUSD on H1 / H4 / D1. It does not complete the
CLAUDE.md M5/M15 engine: M5/M15 failed the unseen 2009-2020 holdout and are not signal timeframes (a later, separate
pre-registration may use them for execution only). No news veto in v1: the Risk Manager rules of C2 are the only filters.

## C1 Time
- Cut k = Friday 22:15:00 UTC (`engine.regimes`). Bar close time = open time + bar length.
- A decision at cut k (features, regimes, vol_scale, selection, equity filter) may use only bars with close_time <=
  cut_k and trades with exit_time <= cut_k (exit_time = close time of the exit bar).
- Entries attributed to week k: entry-bar open_time in the OPEN interval (cut_k, cut_{k+1}). A signal whose entry bar
  opens exactly at a cut is rejected (logged, zero return); the earliest entry after a decision opens strictly after it.
- Event order at one timestamp: exits -> cut processing (selection) -> entries.
- Synthetic tests before any rerun, on M5, M15, H1, H4 and D1: bars / exits at cut - 1 s, cut, cut + 1 s, and a bar that
  straddles the cut (e.g. H1 opened 22:00, closes 23:00) must not inform the decision at 22:15.

## C2 Event-driven portfolio (one implementation for BASE, optimiser, holdouts, compounding and the forward record)
- **Potential-signal table** per candidate: every signal, simulated independently (entry at the next bar open; exit at
  stop, target or max hold; stop-first on same-bar ties; gap through a stop fills at the open), with entry/exit time,
  gross bp, cost bp and swap bp. The **shadow ledger** (selection statistics: the chronological one-position filter, as
  today) and the **live ledger** (the rules below) each consume the potential-signal table independently; neither is
  derived from the other. A skipped live signal, for any reason, creates no position and does not alter any existing
  position; a candidate that was flat stays flat (so a skip never makes it busy), and one that already holds a live
  position keeps it unchanged.
- Deployable m in {1, 2} champions (CLAUDE.md §3); m > 2 is a research ensemble, reported separately, never deployed,
  and outside the primary family claim.
- Weekly R unit U_k = f x equity at cut_k. Weekly R = (sum of net $ P&L of all exits in (cut_k, cut_{k+1}], inherited
  positions included) / U_k.
- Admission of a champion's signal (in order of champion rank, then candidate hash): the champion has no open live
  position; cumulative realised P&L since cut_k > -3 U_k; total stop-loss $ of all open positions (former champions'
  included) + the new trade's <= 3 x f x current equity; free-margin test at a frozen leverage of 1:100: equity - used
  margin - new margin >= 50% of equity. Otherwise the signal is skipped and logged.
- Size: risk $ = f x equity just before entry x vol_scale_k; lots = risk $ / (stop distance x contract size), rounded down
  to 0.01; below 0.01 lot the signal is skipped with zero return, the candidate does NOT become busy, and the week stays
  an explicit calendar observation.
- Handover: positions are never force-closed; a former champion's open positions keep counting toward risk; its new
  signals are ignored.
- Every decision uses realised-by-cut results; entry-cohort tables are descriptive only. Calendar = all cuts with
  `cell[k] != ""` (no `EN > 0` filter).
- Reported for f = 0.5 / 1 / 2 %, starting equity $10,000.

## C3 Causal vol_scale
- F_k and the calibration test use only weeks with index < k (existing thresholds: |median log(RV/F)| <= log 1.5 over 26
  valid weeks and share of RV/F > 4 below 10%; otherwise 0.50).
- B_REF_k = median of finite RV_i, k - 260 <= i < k, weeks with >= 80 completed H1 returns; fewer than 52 valid weeks ->
  scale 0.50; never looks back beyond 260 weeks. vol_scale_k = clip(sqrt(B_REF_k / F_k), 0.50, 1.00).
- Forward keeps the frozen spec B_REF (known now). RV only from H1 bars; `weekly_rv` takes the bar length explicitly.

## C4 Symbol contracts (MT5 read 2026-09-30; `data/foundry/mt5_symbols_20260930.json`, sha256
4627adb587949264f4cd3ae8921f5df4b5ab7265f20d04e00298a5b70c4161bf; account leverage 1:2000 demo)
| field | XAUUSD | XAGUSD |
|---|---|---|
| contract / point / tick size / tick value | 100 oz / 0.001 / 0.001 / $0.1 | 5,000 oz / 0.001 / 0.001 / $5 |
| volume min / step / max | 0.01 / 0.01 / 200 | 0.01 / 0.01 / 200 |
| calc mode / margin currency | 0 (forex) / XAU | 0 (forex) / XAG |
| round-trip cost | max(2.0 bp, entry spread_bp + 1.0 bp) | 2023+: max(4.0 bp, entry spread_bp + 1.0 bp); before 2023: constant max(4.0, 1.5 x global 2023-26 median spread_bp + 1.0) |
| stress | base + 2.0 bp | base + 2.0 bp |
| swap long / short | engine calibration kept: $0.5493/oz/night at $4,154.5 = US 2y + 0.02%/yr (today's MT5 $0.5478 at $4,187.9 = 2y - 0.04%, difference immaterial) / 0 | $0.0077/oz/night at $60.976 = 4.61%/yr = US 2y (4.81%) - 0.20%/yr, frozen markup -0.20% / 0 |
| rollover | 17:00 New York, Wednesday x3 | same |
- spread_bp = the dataset's recorded ask-minus-bid of the entry bar, charged once per round trip; slippage exactly
  1.0 bp total. Same-bar SL/TP ties: stop-first is primary; tick/M1-resolved (HistData 2009+) is a sensitivity.
- Historical swap (longs only; shorts 0) is a fixed ANNUAL RATE of notional, never a fixed dollar charge: for the
  rollover at 17:00 New York on calendar day d, rate_d = (US 2y par yield `BC_2YEAR` of the latest Treasury date strictly
  before d, from the 11 files `data/external/treasury_nominal_2016..2026.xml`, concatenated in name order sha256
  ced897410400c41167d2711e942a3fceac2d76f812720c9ea9ace3097560751b) + markup (XAU +0.02, XAG -0.20 percentage points
  per year), clipped at >= 0; before the first 2016 Treasury value, that first value.
  bp charged = nights_d x rate_d / 100 / 365 x 1e4 with nights = 3 on Wednesday, 1 on Monday / Tuesday / Thursday /
  Friday, 0 on Saturday / Sunday; charged for every rollover in (entry open time, exit bar close time]. The only
  change from `engine.swap_bp` is the one-day publication lag.

## C5 Caches and splices
- Cache metadata: schema version; sha256 of the producing code (engine, zoo, walk-forward), of the ordered raw-source
  manifest and canonical array bytes, of the cut vector; cost version; data end. Loaders reject mismatches; stacking
  TFs asserts identical cuts and widths. Pools by explicit TF lists (`np.isin`). Labels carry bar units (D1 = days).
- Every series: timestamps strictly increasing and unique (a duplicate or a decrease = reject).
- Splice checks on 4 weeks either side of every seam (Dukascopy -> Exness, HistData -> Exness): H1 gaps <= 3 h except
  weekends <= 72 h and weekdays in the frozen holiday list (pandas USFederalHolidayCalendar 2003-2026 + Good Friday by
  the Easter algorithm + 24, 26 and 31 December + 2 January; generated with pandas 3.0.6 into
  `data/foundry/wrwr_holidays_2003_2026.txt`, 352 dates, sha256
  35a2d982c06c84faa9809c2a9b6073fcff4a2de70b79d7430e0c506854464e8f); median spread ratio in [0.5, 2.0]; source offset on the overlap
  |median| <= 2 bp and MAD <= 1 bp; seam |log return| < 10 x median |H1 log return| (seam excluded).

## C6 Nulls and gates (gold)
- **Primary family** (deployable, deduplicated, hashed before any rerun): window {26, 52, 78} weeks x LCB z {0.5, 1, 2}
  x pool {H1, H4, D1, H1+H4+D1} x m {1, 2} x equity filter {none, 26 weeks realised-by-cut} x causal WRWR sizing, min
  trades 10, NO TRADE when the best score <= 0: 144 configurations. Dedup key = that tuple. BASE = (52, 1, H1, 2, none).
- **Benchmark B_{j,k} (random router, configuration-specific):** for configuration j, a full C2 event-driven path in
  which, at every cut where j is active (cut-known: j selects n_k = the number of candidates with score > 0, capped at
  m; n_k = 0 is a stand-aside week), each of the n_k champion slots is replaced by a candidate drawn uniformly without replacement
  from the point-in-time eligible candidates (known at the cut) that share that champion's exit configuration; same m,
  handover, sizing, costs and admission rules; weeks where j stands aside are stand-aside weeks. 10,000 frozen-seed paths
  per configuration (seeds 0..9,999, ties broken by candidate hash); more paths until the Monte Carlo SE of the benchmark
  mean weekly R < 0.01 R. d_{j,k} = R_{j,k} - B_{j,k}.
- **Bootstrap object:** the T x 144 matrix of weekly (R_{j,k}, B_{j,k}) pairs, resampled jointly across configurations
  in stationary blocks. Each configuration is a fixed deterministic rule mapping cut-known information to positions, so
  its internal candidate selection is part of the rule and is not re-simulated (White 2000); path-level structure is
  covered by the supporting path null. A meta-selector over configurations (e.g. walk-forward-over-configs) is a
  secondary result, recomputed inside every replicate from the resampled matrix with its own frozen rule; the primary
  claim uses the 144 fixed configurations only.
- **Primary test:** studentized White Reality Check over the 144 configurations on d, least-favourable recentring
  d* - mean(d), vector stationary bootstrap (Politis-Romano) with mean block 10 weeks, K = 999; sensitivities: blocks
  4 and 26, Hansen SPA.
  Family claim (144 fixed configurations): p <= 0.05. BASE alone: one-sided stationary-bootstrap p <= 0.05 (block 10, K = 999) and a positive
  95% lower bound on mean d. Monte Carlo p = (1 + #null >= real) / (K + 1).
- **Supporting path null** (descriptive, not a gate): week-block sign flips of H1 normalised increments (mean block 10
  weeks), everything recomputed, K = 199, background. A no-edge rule is expected to be negative after cost.
- **PBO (CSCV):** 16 contiguous blocks, a 5-week embargo at every train/test boundary; 95% upper bound from a
  999-replicate outer stationary bootstrap that recomputes PBO. Upper bound <= 0.20 = robust; 0.20-0.50 = inconclusive
  -> shadow only; lower bound >= 0.50 = stop.
- **Cost gate:** one-sided 95% stationary-bootstrap lower bound (block 10) of mean weekly net R > 0 at base cost; at +2 bp
  a positive point estimate and max DD <= 1.25 x the base-cost DD.
- Positive-year shares only with binomial and block-bootstrap intervals, never as a pass on their own.

## C7 XAGUSD (cross-asset robustness, not an XAU holdout)
- Data downloaded unopened until C4, C5, the XAG trade tables and this section are frozen and hashed.
- Primary: BASE unchanged on XAG; one-sided 95% stationary-bootstrap lower bound (block 10, K = 999) of mean d > 0
  (benchmark as C6 on XAG).
- Secondary: at most 3 configurations chosen on gold only: the deployable configurations with a positive gold 95% lower
  bound of mean d AND a passed gold cost gate, ranked by that lower bound, ties by configuration hash, top 3; tested
  with step-down Westfall-Young maxT, K = 999, familywise p <= 0.05.
- SEL (forward) = the gold rank-1 configuration of that list, eligible only if it passes the adjusted XAG maxT test.

## C8 Forward record
- Two independent shadow portfolios, BASE and SEL, each f = 1%, $10,000 notional, C2 rules.
- Payoff statistic g = max(R_week, -4): a deliberate winsorisation, not an enforceable bound (open positions can take a
  week below -4 R after the -3 U_k entry stop). Raw R and every truncated amount are reported every week.
- e-process: E_t = (1/3) sum over lambda in {0.05, 0.10, 0.20} of prod(1 + lambda g_i). No DATA_GAP exemption: every week
  from the first cut is included (inclusion fixed before any week begins), strictly in cut order. A week whose data or
  job failed is PENDING and so are all later weeks: nothing is appended past it until it is reconstructed from recovered
  data (Exness, Dukascopy, HistData) or, 8 weeks after its cut, assigned g = -4 with raw R = NA and an audit reason; the
  pending weeks are then appended in cut order and the e-process is updated in that order only.
- Anytime-valid lower confidence bound: LCB_t = the largest mu on the grid -1.00, -0.99, ..., +0.50 with
  (1/3) sum_lambda prod(1 + lambda (g_i - mu)) >= 1/alpha (inverting the shifted-mean e-processes).
- alpha from the 0.02 reserve, only with the operator's word: H-WRWR-BASE 0.005 (E >= 200), H-WRWR-SEL 0.005 (only if
  C6/C7 gates pass); otherwise SHADOW without alpha.
- Weeks 13 and 26: safety only — stop if drawdown exceeds the 97.5th percentile of the horizon-specific drawdown
  simulated by stationary bootstrap (block 10) of the corrected backtest. No promotion before week 52.
- Week 52 promotion discussion: E >= 1/alpha, LCB > 0, demo execution quality (median slippage <= 0.10 R, fills >= 95%),
  then per-order operator confirmation for any real money.
- All selector, sizing and Risk Manager rules stay frozen for the whole 52-week record.

## C9 Roles and manifest
- Per cut, separate scripts and artefacts: analyst (regime, vol, news JSON) -> strategist (champions, candidate hashes,
  scores) -> risk manager (approve / reject per signal with rule IDs) -> execution (demo order / fill / spread /
  slippage log) -> auditor (scores, drift, e-process).
- Manifest `docs/WRWR_MANIFEST.md`, frozen and committed before any real gate statistic is computed and before XAG is
  opened: family hash and dedup key, endpoints, ranking and tie rules, candidate hashes (sha256 of tf, setup, mode,
  k_atr, exit, hold, code hash), benchmark seeds, the sieve test-family digest and its placebo seeds.

## C10 Targets — effect-size goals, not pass criteria (Calmar = R per year / max drawdown in R)
| tier | R / year | max DD | Calmar |
|---|---|---|---|
| usable | >= 10 R | <= 15 R | >= 0.5 |
| good | >= 20-25 R | <= 15-20 R | >= 1.0 |
| exceptional | >= 40-50 R | <= 20-25 R | >= 1.5 |
300 R/year has no supporting evidence; the evidence-supported expectation today is "unknown, plausibly zero".

## C11 Sieve — exact contract (SIEVE Amendment 3; frozen now, run last)
- Placebo generator (per path, frozen seed): split the base series (H1 for scan A, M5 for scans B/B2) into trading weeks
  by cut; draw stationary-bootstrap block lengths ~ Geometric(mean 10 weeks; sensitivities 4 / 26) along the ORIGINAL
  week order (no reordering); give each block an independent Rademacher sign; for sign -1 mirror every bar of the block
  about the previous (new) close exactly as `run_scan.mirror()` (log moves of open, high, low, close vs the previous
  close multiplied by -1, high and low swapped, the gap flipping with its bar); timestamps and volume unchanged. Higher
  TFs are rebuilt from the mirrored base series; gold-derived cross features are recomputed; external series (GVZ,
  yields, CFTC, news, DXY / XAG / US500 prices) are not mirrored. The WHOLE pipeline (features, WRWR regimes, masks,
  targets) is recomputed on each path.
- Pre-check before any real scan: on 20 placebo paths, the open-to-open mean and the ATR-normalised mean each have
  |t| < 1.96 (Newey-West, lag h - 1).
- Continuous exposure: trailing percentile rank as before, centred by its own mean over the preceding 60 months inside
  the tested mask (minimum 36 months, else not tested); statistic = mean(x_c y) / mean(|x_c|) over the period's bars in
  the mask, with the raw target (no target demeaning). Events (+1 / -1 / 0): mean(x y) / mean(|x|), raw target.
  Time flags: bar-level regression of y on the flag with fixed effects for every (month, mask, WRWR vol class) cell,
  i.e. the flagged-minus-unflagged contrast within each cell, each bar weighted equally; cells with < 20 flagged or
  < 20 unflagged bars are dropped.
- Inference: Newey-West with lag h - 1 on the bar-level statistic within each period; family = every feature x horizon
  x mask of the scan (two-sided |t|), the list fixed by data availability alone (>= 36 valid DEV months) and hashed
  before any real statistic is computed; step-down Westfall-Young maxT with K = 999 placebo paths; familywise p <= 0.05 on DEV, then
  the same sign with Newey-West |t| >= 1.5 in every CHECK period.
- Level maps (deciles, 5 x 5) only for survivors, each cell tested against the same placebo distribution.
