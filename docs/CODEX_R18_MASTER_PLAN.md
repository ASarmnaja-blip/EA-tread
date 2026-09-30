1. **R18-1 [BLOCKING] B1–B5 are real, but the proposed B4/B5 fixes are incomplete**

| Bug | Verdict and evidence | Required fix |
|---|---|---|
| B1 | **Real.** Candidate statistics are stored by exit week in `S1`, but realized system returns are stored by entry week in `E1`: `wpwb_walkforward.py:135-140`. The equity filter then takes rolling sums of this entry-week series: `wrwr_optimize3.py:91-94`; `wrwr_holdout.py:50-53`. Thus a D1 trade can affect a cut before it has closed. | Maintain a trade-level event ledger with `entry_time`, `exit_time`, realized R and candidate. At every cut, selection and equity filters may query only `exit_time <= cut`. An exit-lag tensor is acceptable only if checked against the event ledger. |
| B2 | **Real.** `R` comes from `E1[:, weeks]` (`wrwr_optimize3.py:79,87`), is assigned to entry-week calendar years (`:46-48,105`), and those yearly totals select the next configuration (`:134-142`). | Select year Y using only cash flows realized before the Y decision timestamp. Entry-cohort reporting may be retained separately, but never used for selection. |
| B3 | **Real.** The backtest keeps a week only when future entries exist: `weeks = ... (EN[:, weeks].sum(0) > 0)` in `wpwb_walkforward.py:166-167`, `wrwr_optimize3.py:46-47`, `wrwr_compound.py:37-38`, and `wrwr_holdout.py:38-39`. | Construct the calendar solely from cuts, known regime availability, and declared data-quality checks. A zero-entry week must remain as an explicit zero. |
| B4 | **Real.** Every candidate is made sequential in its uninterrupted shadow history (`wpwb_walkforward.py:107-140`), then its precomputed weekly entries are simply harvested when selected (`:203`; `wrwr_optimize3.py:85-87`). Its shadow may therefore be busy because of an unselected prior-week entry. | Do not condition the correction on mismatch exceeding 5%. Build one event-driven portfolio simulation that carries actual selected positions across cuts, retires old positions under a frozen handover rule, and admits new entries only when live state permits. “Start flat at every cut” is itself wrong whenever last week’s live trade remains open. |
| B5 | **Real.** Compounding applies `equity *= 1 + f * R_week` after aggregating all trades (`wrwr_compound.py:63-79`), without chronological fills, concurrent risk, margin, lot steps, or intraweek insolvency. | Simulate orders chronologically using equity immediately before entry, open-risk ≤3R, broker volume step/minimum, and gaps. If calculated size is below 0.01 lot, skip the trade—do not round up and breach risk. |

The appropriate fix is one shared event-driven implementation used by BASE, optimiser, holdout, compounding and forward recording. Separate approximations will recreate inconsistencies.

2. **R18-2 [BLOCKING] The Friday-cut contract still has an unaddressed boundary error**

`engine.py:119` and the M5/M15 builder at `wpwb_walkforward.py:59` use:

> `np.searchsorted(cuts, t, side="left") - 1`

Consequently an M5/M15 bar opening exactly at Friday 22:15 UTC belongs to the old week, even though the comment says bars opening after the cut belong to the new week. Exit closes exactly at the cut are intentionally put in the completed week (`wpwb_walkforward.py:100-103`), so entry and exit boundary conventions need different explicit rules.

Fix: preregister half-open intervals—e.g. exits `(cut[k-1], cut[k]]`, new entries `[cut[k], cut[k+1])`—and add synthetic tests for entry/exit one second before, exactly at, and one second after the cut on every TF. The corrected simulator must also define which positions survive a champion change.

3. **R18-3 [BLOCKING] Historical `vol_scale` contains future calibration information**

The scaling reference `B_REF` was computed from 2021–2026 (`vol.py:39-43`) but is applied to the entire 2004–2026 backtest (`wrwr_optimize3.py:40-44`; `wrwr_compound.py:31-35`). Configurations are even allowed to optimise whether to use this sizing. That is look-ahead for pre-2021 performance.

The forecast and regime cell themselves otherwise appear point-in-time: `engine.regimes()` uses `f[k]`, the preceding 52 weeks, and trend through `k-1` (`engine.py:92-110`). The problem is the fixed future-derived risk reference.

Fix: either:

- use an expanding/rolling reference known at each historical cut, with its rule fixed in advance; or
- report historical results without WRWR sizing and treat the frozen 2026 `B_REF` as forward-only policy.

Also make `weekly_rv()` accept bar duration. It hard-codes a one-hour close offset (`vol.py:46-53`) even when called with resampled H4/D1 bars (`wpwb_walkforward.py:153`). Combined with `MIN_BARS=80`, H4/D1 calibration is not meaningful.

4. **R18-4 [IMPORTANT] There are additional pool, cache, splice, and reporting defects**

The optimiser’s purported H4+D1 pools are defined as `tfv != "H1"` (`wrwr_optimize3.py:54-56`). Once M5/M15 are loaded, those pools include M5 and M15. The ledger’s H4+D1 conclusions are therefore not trustworthy.

Caches contain arrays and candidate dictionaries but no source hash, code hash, cut vector, data end, cost version, or schema version (`wpwb_walkforward.py:115-149`). `wrwr_champions.py` chooses any existing spliced cache while independently loading the current spliced bars (`wrwr_champions.py:21-32`), allowing a stale cache/current-feed mismatch. The Dukascopy/Exness join is directly concatenated (`engine.py:156-175`) without a seam assertion.

Fix:

- define H4+D1 with `np.isin(tfv, ["H4","D1"])`;
- version every cache with code/data/cuts/cost hashes and reject mismatches;
- assert identical cut vectors and array widths before stacking TFs;
- test the splice for duplicates, gaps, return outliers, spread discontinuity and source-offset stability;
- correct D1 labels: `hold=5/20` represents bars/days, but output labels it as hours (`wpwb_walkforward.py:150`; `wrwr_champions.py:46`).

5. **R18-5 [BLOCKING] XAGUSD cannot use the present XAU cost and swap engine**

WRWR subtracts a constant `E.COST_BP` rather than the stored per-bar spread (`wpwb_walkforward.py:131-140`; `engine.py:32`). Swap is calibrated specifically from an Exness gold dollar-per-ounce charge and US two-year yield (`engine.py:360-378`), and shorts are assigned zero swap (`:382-405`). Those assumptions cannot simply be transferred to silver.

The plan’s “measured XAG spread +1 bp” (`MASTER_PLAN:85-90`) therefore requires a new asset-specific cost interface, not merely new data.

Fix: freeze symbol-specific spread/slippage, contract size, tick value, long and short swaps, triple-swap day, and lot constraints before opening XAG results. Use time-varying historical costs where available and conservative era buckets otherwise. Resolve same-bar exits with ticks/M1 where available, but retain and report stop-first bounds for uncovered years.

6. **R18-6 [IMPORTANT] The broad order is sound, but the audit specification must precede implementation**

“Fix → audit → untouched robustness data → forward record → sieve” is directionally correct. However, the static contract audit must move ahead of the expensive rerun; otherwise B4, cut semantics, causal sizing and asset costs will be implemented incorrectly and then discovered in Step 2.

Recommended sequence:

1. Freeze time, position, cost, cache and attribution contracts plus synthetic tests.
2. Implement the single event-driven simulator.
3. Repeat the read-only audit and reconcile every old/new result.
4. Run null/PBO/cost analyses.
5. Freeze exact candidate IDs and selection rule.
6. Read the blind XAG result as **cross-asset robustness**, not an XAU holdout.
7. Start append-only paper logging; the sieve can remain last or run independently.

XAG may be downloaded earlier while remaining unopened. Forward logging can start immediately after the corrected freeze rather than losing weeks waiting for unrelated sieve work.

7. **R18-7 [BLOCKING] Per-bar sign flipping is not a valid sole “luck ceiling,” and K=20 is too small**

The current mirror independently flips every bar (`run_scan.py:142-153`). That removes serial dependence, trend/reversal structure and realistic multi-bar technical patterns. Adding back one observed drift does not restore volatility-state-dependent drift, serial dependence, gaps or the joint behaviour across candidates. It therefore answers “performance on an artificial sign-symmetric path,” not “the best result obtainable by luck in realistic gold data.”

The expectation that placebo BASE should be approximately 0R (`MASTER_PLAN:139`) is also wrong: after costs, a no-edge trading strategy should generally be negative.

Use two complementary nulls:

- A whole-week/block wild bootstrap of normalized OHLC increments, with signs flipped by blocks rather than bars.
- A stationary bootstrap of the complete weekly configuration-return vector, recentered under the no-outperformance null, preserving cross-config dependence. Use mean block lengths 8–13 weeks and sensitivity at 4 and 26 weeks. Stationary bootstrap is designed for weakly dependent series ([Politis–Romano](https://statistics.stanford.edu/technical-reports/stationary-bootstrap)).

The entire 184,320-config selection must be rerun inside every replicate. Use Monte Carlo `p=(1+#null≥real)/(K+1)`. K=20 gives a minimum p of 0.0476 and an unstable 95th percentile. Require K≥199 for a preliminary gate and preferably K=999 for the final max-statistic gate. Compare net excess over a frozen matched benchmark, not raw R≈0.

8. **R18-8 [IMPORTANT] PBO, cost, and XAG pass gates are too permissive**

PBO is a descriptive estimate of how often an in-sample winner disappoints out of sample, not proof of alpha. The proposed PBO≤0.30 “pass” tolerates a 30% overfit probability. CSCV is appropriate in principle, but needs contiguous, purged blocks and the corrected causal return matrix; see the original [PBO/CSCV paper](https://escholarship.org/uc/item/4w1110bb).

Concrete gates:

- **PBO:** pass only if the upper 95% interval is ≤0.20, preferably point estimate ≤0.10; 0.20–0.50 = shadow/inconclusive; lower bound ≥0.50 = stop.
- **Cost:** at measured base costs, require the one-sided 95% stationary-bootstrap lower bound on mean net R to exceed zero. At 4 bp, require at least a positive point estimate and acceptable drawdown. A positive total at 4 bp alone is not statistical evidence.
- **XAG primary:** one frozen BASE hypothesis, one-sided Monte Carlo p≤0.05 and positive lower confidence bound. `p<0.10` is only supportive/exploratory.
- **Secondary XAG configurations:** use a maxT/Holm familywise p≤0.05. The rule choosing the “≤3” configurations must be frozen before XAG is viewed.
- **Positive 52-week periods:** 55% alone is weak—roughly 10 of 17 years. Report a binomial interval plus block-bootstrap mean/median-year intervals; do not make it an independent pass substitute.

9. **R18-9 [BLOCKING] The Sieve Amendment 3 diagnosis is plausible but not established, and K=50 cannot repair FDR**

A persistent endogenous predictor can suffer Stambaugh-type finite-sample bias, especially with overlapping long-horizon returns, but Stambaugh bias specifically requires correlation between predictor and return innovations; persistence alone is insufficient ([Federal Reserve discussion](https://www.federalreserve.gov/econres/ifdp/the-stambaugh-bias-in-panel-predictive-regressions.htm)).

The code shows more immediate problems:

- persistent conditioner masks are formed at `run_scan.py:185-188`;
- continuous exposures are ranked but not centered within each mask/month (`:197-204`);
- flags remain raw 0/1;
- the statistic is raw `sum(x*y)/sum(|x|)` (`:215-221`);
- horizons overlap (`:171-174`) but t-statistics treat monthly values with an ordinary `sqrt(k)` standard error (`:227-229`);
- after mirroring, the original path’s regime cells are retained: the bars are replaced at `:158-161`, but cells are not recomputed before masks use them at `:177-182`.

Thus uncentered time flags test a conditional mean rather than a contrast against comparable non-flag bars, and persistent masks plus overlapping targets can severely distort size. These are more concrete explanations than the label “Stambaugh bias.”

Fix before empirical calibration:

- recompute every price-derived regime/mask on each placebo path;
- center continuous exposure within its tested mask using training-only/cross-fitted estimates;
- test time flags as flagged-minus-matched-unflagged contrasts in the same month, mask and volatility bucket;
- use non-overlapping horizon subsamples or block/HAC inference;
- run direct martingale checks on open-to-open placebo returns and ATR normalization.

K=50 yields minimum empirical p=1/51 and cannot provide BH p-values for a large test family. Use a Westfall–Young/maxT familywise gate with ≥999 null seeds, or a rigorously stratified null with far more simulations. The proposed “≤1 of 20 held-out seeds has a survivor” is weak: observing 1/20 still has an approximate 95% upper false-survivor probability around 22%.

10. **R18-10 [BLOCKING] The forward e-value is valid only for the floored estimand, not raw profitability**

`forward_panel.py` defines `g=max(week_R,-2)` (`:14-17,238-239`) and multiplies by `1+λg` (`:257`). That can be a valid e-process for the explicitly stated null that the **floored** outcome has nonpositive conditional mean. It does not establish that raw weekly R has positive mean: replacing a −10R loss by −2R can make the floored mean positive while the real strategy loses money.

The e≥100 threshold is correct for one exact α=0.01 hypothesis, provided the payoff/null assumptions are valid and the strategy is predictable. Anytime-valid inference supports optional observation when constructed as a nonnegative supermartingale ([Howard et al.](https://doi.org/10.1214/18-PS321)).

Fix:

- base the e-process on the actually enforceable weekly portfolio payoff, with a genuine predictable lower bound from the risk engine; or explicitly call it a bounded/floored utility hypothesis and never equate rejection with raw alpha;
- allocate α separately to BASE, each configuration, or one frozen portfolio. One α=0.01 threshold cannot confirm several adaptively selected rules;
- use weeks 13/26 only for safety/futility, not promotion;
- at week 52 require e≥100, positive lower anytime confidence bound, execution-quality limits, and the operator’s per-order confirmation.

The plan’s “inside an 80% band” continuation rule and “below the 5th percentile” stop rule are inconsistent. Drawdown also does not scale linearly with elapsed time; simulate horizon-specific predictive drawdown quantiles instead.

11. **R18-11 [IMPORTANT] The 300R warning is right, but the proposed realistic-target table is internally inconsistent**

It is correct to say that 300R/year has no supporting evidence and is roughly 35 times the reported BASE rate (`MASTER_PLAN:35-45`). The “~20× compounded” figure is only the idealized `exp(3)` result with smooth returns and negligible variance, not a realistic forecast.

More importantly, BASE’s +8R/year is not established edge: its random-control p=0.041 missed its own 0.0025 gate (`MASTER_PLAN:21`), and the pipeline contains the bugs above. The evidence-supported expectation remains “unknown, plausibly zero.”

The table mixes incompatible quantities. At 1% risk, +10R/year is roughly 10% before compounding; with 20% max DD its annual return/DD is about 0.5, not ≥2. Replace “profit/DD” with an explicitly defined Calmar ratio and use coherent targets, for example:

- usable: ≥10R/year, max DD ≤15R, Calmar ≥0.5;
- good: ≥20–25R/year, max DD ≤15–20R, Calmar ≥1;
- exceptional: ≥40–50R/year, max DD ≤20–25R, Calmar ≥1.5.

All are effect-size goals, not statistical pass criteria; promotion still needs uncertainty bounds and forward evidence.

12. **R18-12 [IMPORTANT] Most safety rules comply with CLAUDE.md, but champion count, scope, roles and preregistration need tightening**

The plan correctly prohibits Grid/Martingale/averaging, fixes a Risk Manager, restricts automatic orders to Demo at 0.01 lot with SL, and retains per-order confirmation for real money (`MASTER_PLAN:6-7,96-104`; `CLAUDE.md:190-207,341-352`).

Remaining conflicts:

- CLAUDE permits only 1–2 Champions (`CLAUDE.md:98-104`), while the optimiser deploys `top_m` up to 8 (`wrwr_optimize3.py:58`). Top-3/5/8 configurations must remain research ensembles or be reduced to 1–2 deployable champions.
- The repository mandate is an XAUUSD M5/M15 signal engine (`CLAUDE.md:25-45,108-116`), while the surviving WRWR research uses H1/H4/D1. The plan must state whether WRWR is only a higher-timeframe router/risk overlay; it cannot be presented as completing the M5/M15 engine.
- Role separation (`CLAUDE.md:176-191`) needs enforceable artifacts: selector output, independent Risk Manager approval, execution log, and auditor scoring should be separate stages.
- Pre-registration must name exact candidate hashes, primary endpoint, costs, null generator, bootstrap parameters, multiple-testing rule and α allocation before XAG or forward outcomes are viewed.

**PLAN NOT OK TO START UNTIL: the cut/event-driven portfolio contract, causal vol scaling, asset-specific costs, cache/pool defects, valid null design, Sieve inference, and forward estimand/alpha allocation are corrected and preregistered.**