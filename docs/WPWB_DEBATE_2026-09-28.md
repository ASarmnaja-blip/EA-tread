## Round 1 — Codex objections to draft v0

1. **Severity: critical — The claim is still broader than the procedure being tested.**

   **Problem:** Section 1 states a WPWB-level claim, but section 2 tests only a selector over the 40 legacy variants from a search whose menu was itself shaped by repeated inspection of 2021-2023 DEV. Rounds 2 and 3 were explicitly DEV-guided, the 2024-2026 period has since been opened repeatedly, and two menu entries (`META hl=3/8`) are already selectors over the round-1 menu. A result can establish, at most, something about this hindsight-shaped menu and this selector. It cannot establish that the broader WPWB idea works or fails, especially for M5/M15 conditional tools not represented by these weekly P&L series.

   **Concrete proposed change:** Narrow the claim to: “Does frozen selector P add next-week value over a specified no-skill benchmark when choosing among these 40 legacy tools?” State explicitly that failure says nothing general about WPWB or unrepresented tools. Treat `META` as a nested policy rather than an ordinary tool, or remove it from the base menu to avoid a selector selecting another selector. Any broader claim must wait for a menu and procedure fixed before genuinely new weeks.

2. **Severity: critical — The primary outcome is a dimensionless backtest score, not a deployable portfolio return.**

   **Problem:** Dividing each tool by its own trailing standard deviation and then averaging selected normalized P&Ls is not “equal risk weight” in a portfolio sense. It ignores cross-tool correlation, concurrent gross exposure and duplicate trades. Top-3 can select three near-identical HOD/CHOPREV parameter variants and call that diversification. It also implies inverse-volatility leverage with no leverage, gross-exposure or position cap. A near-zero estimated standard deviation can create an arbitrarily large normalized outcome. The 40 tools also have radically different trade counts and holding periods, so this statistic is not net bp on a common capital base.

   **Concrete proposed change:** Define actual predictable weights at Friday's cut, a target portfolio volatility, a per-tool cap, a total gross/concurrent-exposure cap, and a family/duplicate-exposure cap. Net overlapping identical trades before computing costs and P&L. Compute the primary outcome in net bp on deployable capital (or a fully specified utility) after those constraints. If normalized P&L is retained, call it a research score only and do not use it for promotion.

3. **Severity: high — “Past-only risk normalisation” is not sufficiently specified and can select noise.**

   **Problem:** The draft does not define sample versus population SD, whether zero/no-trade weeks enter the SD, treatment of missing weeks, the minimum positive SD, stale estimates, or what “active” means. Eight active observations in 26 weeks is far too little to estimate a stable scale, particularly after maximizing over 40 tools. Sparse tools can be promoted by one outlier; dense tools and sparse tools are not comparable if zeros are handled differently. It is also unclear whether each historical observation keeps its contemporaneous denominator or is retrospectively rescaled at cut w.

   **Concrete proposed change:** Write the formula. Each week-t return must retain a scale computed strictly from t-26..t-1 using a stated `ddof`, with calendar zero/no-trade weeks handled explicitly. Define active as an executed trade count known after the historical week, require a materially larger effective sample (or use a shrinkage scale), set a positive volatility floor and a hard weight cap using values fixed before running, and specify NaN/staleness behavior. Add tests proving that changing rows t and later cannot change the normalized value or decision at t.

4. **Severity: high — The top-k and flat actions are ambiguous, and flat is not actually in the nested competition.**

   **Problem:** “Hold the top-k tools by score, equal risk weight, if their score > 0; otherwise flat” does not say whether k=3 selects one, two or three sleeves when only some scores are positive; whether unused sleeves remain cash or the positive sleeves are rescaled; what happens with fewer than k eligible tools; how ties are broken; or how NaNs are ordered. Worse, the outer hyper-parameter selector always chooses one of six settings even when all six produced negative inner-window means. The procedure can therefore activate a historically losing setting even though “flat” is supposedly a menu option.

   **Concrete proposed change:** Provide deterministic pseudocode covering partial k, cash weights, eligibility, NaNs and ties. Make flat a seventh hyper-parameter candidate with inner outcome zero; if the best active setting does not strictly beat flat, or ties it within a predeclared tolerance, choose flat. Use a stable, predeclared tool ID for all remaining ties.

5. **Severity: critical — The 52-week warm-up is arithmetically impossible under the stated nesting.**

   **Problem:** Let raw tool outcome be r_t. Its normalized value first exists at t=26 because its scale needs 26 prior weeks. A fixed (h,k) setting first has a full 26-week score at t=52. At outer cut w, choosing among settings from 26 full prior prequential setting outcomes requires w-26 >= 52, hence w >= 78. The proposed 52-week warm-up leaves the earliest inner outcomes undefined. Partial windows, backfilling or recomputing them from the current cut would change the procedure and can introduce look-ahead. Base tools with their own 26/52-week histories may push their first valid dates later still.

   **Concrete proposed change:** Derive validity recursively and start outer evaluation only after 26 valid normalization weeks plus 26 valid fixed-setting outcomes: at least 78 weeks after the first common valid raw-tool week. Better, use sufficient pre-2021 data solely for causal warm-up and name the exact first scored cut. Never shorten an inner window silently. Publish a validity mask per tool and setting.

6. **Severity: high — The six hyper-parameter candidates are not being compared on a common risk basis.**

   **Problem:** The mean of a k=1 normalized sleeve and the mean of three correlated normalized sleeves have different variances and gross exposures. Averaging three sleeves mechanically reduces variance only when correlations permit it, while the selection score ignores that covariance. A 26-week winner-take-all choice among six noisy estimates will churn and suffer severe winner's curse. The outer replay will expose some of that, but it does not make the procedure economically coherent or the warm-up definition complete.

   **Concrete proposed change:** Risk-target every candidate setting to the same predictable portfolio risk and gross cap before comparing inner outcomes. Require 26 valid setting outcomes, include flat, specify a deterministic tie rule and either freeze weekly winner-take-all as the deliberate design or add a predeclared switching penalty/hysteresis. The full state machine—including eligibility changes and any switching penalty—must be replayed in every calibration replicate.

7. **Severity: critical — The proposed placebo is not selection-aware in the sense claimed.**

   **Problem:** Section 3 keeps P's realized choices and hyper-parameter path fixed, then evaluates those choices on another outcome row. That conditions on the selector produced from the actual outcome matrix. It does not repeat risk estimation, eligibility, tool scoring, flat decisions or hyper-parameter selection under a null dataset. It is an alignment shuffle of a fitted action path, not a null distribution of the full selection/rebuild pipeline. Calling it “the entire procedure P run identically” contradicts the next sentence.

   **Concrete proposed change:** Stop calling this selection-aware. For a historical calibration exercise, generate a full multivariate null outcome matrix, preserve cross-tool dependence with common block indices, remove the null mean relative to the primary benchmark, and rerun normalization, eligibility, scoring, flat decisions and hyper-parameter selection from scratch in every replicate. Validate empirical size under null simulations with the observed cross-correlation, heavy tails, volatility clustering, drift breaks and plausible AR dependence. If no credible null generator can be defended, the historical exercise must remain descriptive and only the forward stream may carry inferential weight.

8. **Severity: critical — Circular shifts are not a valid null under this drift, autocorrelation and memory structure.**

   **Problem:** A cyclic-shift randomization is exact only under a defensible shift-invariance/stationarity assumption. The whole motivation for WPWB is regime change; 2021-2026 contains major price-level, cost-to-move, volatility and policy drift. Risk normalization does not remove mean drift, common factor exposure or volatility regimes. Worse, s=N-13 is a signed lag of -13: week w is evaluated on w-13, an observation directly inside the selector's 26-week score window. Other large shifts similarly evaluate choices on their own training observations. A 13-week exclusion is nowhere near the effective memory: 26-week scaling, 26-week scoring, 26-week hyper-parameter evaluation, and base tools with up to 52-week histories. Positive 13-week shifts also retain any medium-term persistence the null is supposed to destroy.

   **Concrete proposed change:** Do not use these shifts as a p-value null. If shifts are kept as a diagnostic, report signed lags, exclude every lag inside the maximum dependency horizon, forbid wraparound across regime boundaries, and show sensitivity to local/block-restricted shifts. A better primary design is paired prequential excess versus a predictable implementable benchmark, followed by a calibrated multivariate block/surrogate test that reruns P. Given the already-mined history and nonstationarity, genuine validation should come from the forward sequence, not from pretending rotations are exchangeable.

9. **Severity: high — The stated add-one p-value is not justified by the set of roughly 247 shifts.**

   **Problem:** The transformations s=13..N-13 are an ad hoc subset, not a group closed under composition, and the identity transformation is excluded. The usual exact permutation rank argument therefore does not apply. `(b+1)/(B+1)` is valid for appropriately sampled random transformations under the null; it does not repair a non-exchangeable, dependent, exhaustively enumerated set. The nominal ~0.004 resolution is not the main issue. At p=.05 there are only about twelve tail shifts, and adjacent shifts are strongly dependent, so the effective information can be far smaller than 247.

   **Concrete proposed change:** Do not attach an inferential p-value to this shift set. If an exact randomization design is proposed, specify an exchangeability group including the observed assignment and calculate its exact rank; if Monte Carlo transformations are sampled, specify the sampling law and report Monte Carlo uncertainty. Otherwise report the shift rank and lag plot as diagnostics only. Calibration and power must be demonstrated before any cutoff is named.

10. **Severity: critical — The primary statistic does not test incremental adaptive value against one economic benchmark.**

    **Problem:** Absolute mean normalized P outcome versus time-shifted outcomes can pass because P concentrates in tools with an unconditional premium, long-gold exposure or era-specific favorable costs—not because Friday information improves next-week choice. The equal-weight eligible menu and always-long comparators are relegated to diagnostics even though the methodology review explicitly required one primary implementable benchmark. “Placebo-expected outcome” is not itself an observable trading policy.

    **Concrete proposed change:** Predeclare one past-only, implementable benchmark B and make d_w = net return(P_w) - net return(B_w) the primary series. A defensible B is an equal-risk eligible-menu portfolio under the same gross, family and volatility caps; alternatively use the exact expected return of a preregistered random-k policy conditional on that week's past-known eligible set. Match costs, forecast risk, cash allocation and leverage. LONG and other contrasts may remain mechanism diagnostics.

11. **Severity: critical — A new historical p<0.05 gate does not reset the error rate after repeated mining.**

    **Problem:** Calling this “the single primary hypothesis this pre-registration tests” does not make 2021-2026 unmined. The menu, half-lives, k values, 26-week windows, normalization idea and even the decision to test a selector were chosen after extensive use of these observations. The resulting historical p-value has no project-wide 5% false-positive interpretation. At the same time, making it a hard gateway to the forward shadow can kill a real but modest edge; no power or minimum detectable effect is provided for this much noisier nested procedure.

    **Concrete proposed change:** Remove historical p<0.05 as an evidentiary gate. Report the historical effect, uncertainty, concentration, null-calibration results and power/MDE as development diagnostics. Freeze P before 2026-10-02 and let genuinely future paired outcomes provide the only confirmatory evidence. If resources require a historical screen, label it a heuristic resource rule, not a significance test, and specify an economic effect/robustness threshold rather than laundering it through p=.05.

12. **Severity: critical — Section 6 does not specify an e-process; it merely promises one.**

    **Problem:** “E-process on the weekly outcome vs the placebo-expected outcome” leaves every validity-bearing choice open: the null, comparator, units, boundedness or moment assumptions, betting strategy/mixture, clipping, start date, missing weeks, threshold, stopping rule and treatment of later modifications. Weekly normalized P&L is unbounded, so a bounded betting e-process cannot simply be asserted. Testing mean > 0 also permits promotion of an economically useless edge. An anytime-valid test does not require vague “alpha spending” at every look; one e-process normally uses a fixed allocation and a threshold such as 1/alpha.

    **Concrete proposed change:** Before the first forward outcome, define paired d_w against the primary benchmark and an economically material margin delta. Choose one valid construction for the assumptions actually enforced—for example, a predeclared mixture betting e-process for a bounded/capped test variable x_w derived from d_w, testing H0: E[x_w | F_{w-1}] <= 0, with all caps and transformations frozen from pre-forward information. State the exact update equation or cite a fully specified implementation, use threshold 1/alpha_alloc, and separately report uncapped economic P&L. If conditional-mean validity is too strong, state the weaker null and use a method valid for it; do not improvise after observing tails.

13. **Severity: high — The alpha ledger is nonexistent and “alpha 0.05 spent once” is internally incomplete.**

    **Problem:** `docs/ALPHA_LEDGER.md` does not currently exist. The draft does not define the project family, whether earlier tests consumed any budget, the allocation to P, or what happens when P, the menu, costs or benchmark are changed. A replacement tested on the same accumulating stream cannot reset to 0.05. Nor is it clear whether historical selection of P creates multiple prospective candidates waiting in the wings.

    **Concrete proposed change:** Create and freeze the ledger before the first forward outcome. Give this exact P-versus-B hypothesis a named alpha allocation no larger than the remaining project budget, a start timestamp and an e-value threshold. Predeclare that any material change creates a new hypothesis and consumes separately reserved alpha or follows a specified online alpha-investing rule; old forward observations cannot be reused. Safety stops may terminate exposure but must not be used to redesign and restart the same test for free.

14. **Severity: critical — The implementation plan leaves several direct look-ahead routes open.**

    **Problem:** “Every week 2021-07..2026-09” is not an exact outcome set. As of 2026-09-28, the cut at 2026-09-25 does not have a completed following week; the repository already corrected this exact end-cut mistake in Amendment 7. Building a full 40-column matrix and then applying rolling functions is also dangerous unless every scale uses an explicit one-week lag. Historical inner actions must be the action that would have been produced at that historical cut, not a reconstruction using the current cut's scale, eligible set or hyper-parameter. Full-sample volatility terciles, scale floors, quantiles, data cleaning and tie order are additional leakage paths if chosen or computed after loading all outcomes.

    **Concrete proposed change:** Name the first and last eligible cut; the last historical outcome cut should be 2026-09-18 unless later complete data are independently added before freeze. Define cut-to-outcome intervals exactly. Implement normalization as an auditable lagged operation; cache the entire state at each cut; and run future-garbage invariance tests on the complete P, not only on the underlying tools. Freeze and hash code, configuration, tool manifest, input snapshot and dependency versions. Add assertions that mutating any row at or after cut w cannot alter weights chosen at w, and that the incomplete final week is rejected.

15. **Severity: high — Tool-level costs do not settle portfolio-level executability.**

    **Problem:** Each legacy tool's series includes its own modeled costs, but combining tools can create simultaneous, offsetting or duplicate positions. Averaging their separate P&Ls can charge impossible duplicate capital, miss netting, or understate market impact and spread at concentrated entry times. Base Demo90 cost is the primary input while 1.5x stress is merely diagnostic; a statistically positive result that vanishes at plausible executable costs could still reach the forward test and eventually pass a test of the wrong estimand.

    **Concrete proposed change:** Reconstruct one combined order/exposure ledger per week, with explicit netting and caps, then apply the frozen execution-cost model to that portfolio. Predeclare the cost assumption used in d_w and an economic promotion floor. Keep zero/base/adverse sensitivities, including swap, but do not allow statistical significance on a knowingly nondeployable base-cost convention to imply promotion.

16. **Severity: high — There is no mandatory size/power validation for the new complete procedure.**

    **Problem:** The earlier review showed that nominal weekly tests had poor power and bad tail calibration. This draft changes the statistic, adds inverse-risk scaling, maximum selection over 40 tools, weekly selection over six settings, flat decisions and a nonstandard shift null, yet offers no null-size or planted-edge simulation. That is exactly how a false edge gets through or a real decaying edge gets killed without anyone knowing which occurred.

    **Concrete proposed change:** Before touching the historical result, publish a simulation harness for the complete frozen pipeline. Include nulls with common drift, cross-tool correlation, AR dependence, volatility clustering, heavy tails and regime breaks, plus alternatives with 5/10/20 bp-equivalent persistent and decaying/regime-switching edges. Report family/type-I error, power, time-to-detection for the forward e-process, false-flat rate, turnover and concentration. A procedure whose claimed 5% test is not empirically near 5% under the stated nulls cannot be run as a gate.

17. **Severity: medium — Some “diagnostics” can still leak future information or invite post-hoc rescue stories.**

    **Problem:** Rebuild-volatility terciles are not defined as causal or full-sample; full-sample terciles use future observations. “By chosen family” is ill-defined when top-3 spans families. Leave-one-26-week-block-out can generate many tempting narratives, and there is no rule against using those narratives to revise P after seeing the primary result. Diagnostics do not affect the current p-value mechanically, but they can drive the next round of historical mining.

    **Concrete proposed change:** Define all diagnostic variables now. Use past-only expanding thresholds for any “causal regime” label and label full-sample strata explicitly as retrospective. Define attribution for multi-family weeks. State that diagnostics cannot change P after the historical run; any revision is P2, receives no confirmatory credit from 2021-2026, and requires a new prospective allocation.

### Accepted as is

- The unit of scientific interest should be a frozen adaptive procedure, not an invariant fixed rule.
- Calendar-era results should be diagnostics rather than same-sign pass gates.
- Friday decisions must use only information available before the cut, and weekly outputs may legitimately change.
- Turnover, flat share, hyper-parameter path, concentration and cost sensitivity should all be reported.
- Add-one counting is the right housekeeping rule when the underlying Monte Carlo/randomization test is valid; it does not rescue the current shift null.
- No price-filtered event set belongs in this test.
- A 26-week safety review is not statistical confirmation, and no historical result authorizes trading.
- Freezing a code hash is necessary, although data, configuration and dependency hashes must be added.

In summary, draft v0 has the right high-level target—evaluate an adaptive procedure prequentially—but the proposed historical inference is not ready to freeze. The 52-week warm-up is inconsistent with the nesting, the portfolio outcome is not deployable, the circular shifts are neither exchangeable nor genuinely selection-aware and can evaluate choices on their own training weeks, and a fresh p<0.05 label cannot erase repeated mining of 2021-2026. The forward section is directionally correct but statistically empty until P, its benchmark, bounded test variable, e-process, economic margin and project-wide alpha allocation are specified. Freeze none of sections 2, 3 or 6 in their current form; demote the mined-history result to development diagnostics and make genuinely future paired evidence the only confirmation route.

## Round 1 — Claude responses

Accepted outright: 1, 3, 5, 7, 8, 9, 10, 12, 13, 14, 16, 17. Accepted with a
counter-proposal: 2, 4, 6, 11, 15. Details:

- **1 (claim too broad) — accept.** Claim narrowed to "selector P over this
  frozen legacy menu vs one implementable benchmark". META hl=3/8 removed from
  the menu (a selector must not select a selector): menu = 38 tools.
- **2, 4, 6, 15 (non-deployable portfolio, ambiguous top-k, no common risk
  basis, no netting) — accept the problem, counter with a simpler design:
  k = 1 only.** One tool (or flat) per week removes cross-tool netting,
  duplicate positions, partial-k ambiguity and the covariance problem in one
  step. The chosen tool is run at a risk-targeted size s_w = min(cap,
  target / scale_w), with target and cap fixed before any run. Every tool
  closes its positions within its week (verified in code), so there is no
  carry-over netting. I argue this is better than building a multi-sleeve
  portfolio engine for a menu whose members all failed individually: if the
  best single tool chosen each week adds nothing, a correlated top-3 will not
  rescue it. Codex to rebut.
- **5, 6 (warm-up arithmetic, winner's curse in 6-way inner tuning) — accept
  the arithmetic; counter: drop the inner hyper-parameter search.** Fix h = 8
  weeks a priori (middle of the draft's grid, chosen before any P result) and
  k = 1. Fewer knobs = less winner's curse and a shorter valid warm-up
  (26 weeks for the scale + 26 for the score = first scored cut 52 weeks after
  the first common valid tool week). The inner search is where selection
  noise would have entered twice; removing it is the conservative choice.
  Flat is still an action: choose flat when the best score <= 0.
- **7, 8, 9, 10 (placebo invalid; no economic benchmark) — accept.** The
  circular-shift null is dropped entirely. Primary series: d_w = P_w - B_w,
  where B_w is the **exact expectation of choosing one eligible tool uniformly
  at random** at the same cut, run at the same risk-targeted size, same costs
  (a no-information selector with identical eligibility, sizing and cost
  rules). Always-long remains a diagnostic.
- **11 (historical p<0.05 gate) — partly accept, counter.** No historical
  p-value will be called evidence. But a forward shadow costs 26+ weeks of
  calendar time, so a **resource screen** is kept, stated as an economic rule,
  not a test: forward shadow only if mean d_w > 0 at base AND 1.5x cost, over
  the full scored history, and in at least 60% of leave-one-26-week-block-out
  recomputations. Codex to rebut whether 60% is defensible.
- **12, 13 (no real e-process, no ledger) — accept.** v1 specifies: x_w =
  clip(d_w, -c, c)/c with c = 3 x the sd of d over the historical scored weeks
  (fixed at freeze); H0: E[x_w | past] <= m, margin m = 0.02 (≈ 2% of the clip
  scale); e-process E_t = mean over lambda in {0.05, 0.1, 0.2, 0.3, 0.5} of
  prod(1 + lambda (x_w - m)); reject when E_t >= 1/alpha_P. New
  `docs/ALPHA_LEDGER.md`: project forward budget 0.05, alpha_P = 0.025, the
  rest reserved; any change to P is P2 with its own allocation, no reuse of
  P's forward weeks.
- **14 (look-ahead routes) — accept all.** Last outcome cut 2026-09-18;
  lagged-scale operator with explicit one-week lag; state cached per cut;
  future-garbage invariance test on the complete P; input/config/code hashes.
- **16 (no size/power harness) — accept.** Before the historical run: null
  simulations (menu demeaned per tool, common block resampling preserving
  cross-tool dependence) and planted persistent and decaying edges; report
  false-screen rate, power of the screen, and expected time-to-detection of
  the forward e-process.
- **17 (diagnostics) — accept.** Causal (expanding past-only) regime labels
  only; with k = 1 the chosen family is well defined; diagnostics cannot
  change P — any change is P2.

## Round 2 — Codex assessment of draft v1

### Code audit and arithmetic

I inspected the cited files and the draft implementation now present in
`research/wpwb_procedure/`. A read-only build over all 38 tools and all 273
complete cuts (2021-07-02 through 2026-09-18) completed the implementation's
within-week and non-overlap assertions: every observed trade entered and exited
inside its own week, and no tool held two positions at once. Thus `k = 1`
really does remove cross-tool concurrent-position/netting problems for this
menu. This verification made no MT5 call and wrote no file.

The lookbacks are not yet stated accurately enough in v1. The implementation's
actual conservative manifest is: TSM/TSMI `L+1`; HOD 26/52, HODM 52, DOW 52,
and SESSION 52/104 weeks (their respective `W`); gated CHOPREV 5 weeks (20
distinct UTC dates plus H1 ATR warm-up); ungated
CHOPREV 1; GAP 53; DAYREV 32 (26 weeks plus 40 calendar days, rounded up); and
VOLMAN 78. In particular, GAP actually scans 52 previous cuts, DAYREV reads
`26 weeks + 40 days`, and VOLMAN can read a 26-week sigma at each of 52 prior
cuts. The prose placeholders “CHOPREV/GAP as their code requires” are not a
frozen manifest.

There is also a material start-date contradiction. Although the M5 file begins
2021-01-03, the first usable resampled H1 bar is 2021-07-02 10:00 UTC and the
first cut is 2021-07-02 22:15. The metadata-only rule in
`procedure.first_scored_cut` first reaches ten at **2022-08-05 22:15 UTC**
(13 lookback-valid tools); the full eligibility rule, including
`MIN_ACTIVE = 13`, first reaches ten at **2022-09-30 22:15 UTC** (11 tools).
Therefore “eligible ... exact date ... metadata only” is false: activity is an
outcome/path-derived property. The current code would start at the former date,
when only five tools pass full eligibility.

Sizing arithmetic: `TARGET/CAP = 100/3 = 33.333 bp`. Consequently the 3x cap,
not the 10 bp floor, controls sizing whenever estimated SD is below 33.333 bp;
the 10 bp floor still changes ranking for SD below 10. With `h = 8` over 26
scores, effective sample size is about 18.70 weeks. The forward threshold
`1/0.025 = 40` is arithmetically correct.

### Disposition of the 17 objections

1. **RESOLVED.** The claim is correctly narrowed to this frozen legacy menu and
   selector, failure is not generalized to WPWB, and both nested META policies
   are removed.

2. **PARTLY.** One selected tool, a predictable multiplier and net bp remove the
   top-3 covariance/netting fiction, but the cap is not yet a total exposure
   cap: VOLMAN already sizes up to 2x internally, so the outer 3x permits 6x.

3. **PARTLY.** `ddof=1`, zero weeks, contemporaneous denominators, the 26/26
   windows, floor and activity definition are now explicit; the manifest,
   first-cut logic and justification/calibration of 10 bp and 13/26 remain
   incomplete or inconsistent.

4. **RESOLVED.** With `k = 1`, lowest-index tie-breaking, explicit NaN
   ineligibility, and flat when no eligible positive score exists, the action
   is deterministic and flat genuinely competes.

5. **PARTLY.** Dropping the outer hyperparameter competition makes the 52-week
   recursion correct, but v1 still does not name the first cut and conflates
   metadata validity with activity-based eligibility, yielding two different
   candidate dates.

6. **RESOLVED.** There is no longer a six-way comparison of unequal-risk `k`
   candidates or weekly winner-take-all hyperparameter path; the remaining
   sizing defects are exposure-definition issues, not the old comparison.

7. **PARTLY.** The fixed-action circular placebo is gone and v1 promises to
   rerun the complete P, but its proposed resampled matrix is not a valid
   no-edge null, so the claimed false-screen calibration would not answer the
   objection.

8. **RESOLVED.** Circular shifts, wraparound lag arguments and shift-based
   inference have been removed from the historical analysis.

9. **RESOLVED.** No add-one p-value or exactness claim is attached to the old
   non-group set of shifts.

10. **PARTLY.** A past-known random-choice policy now defines a concrete paired
    comparator, but setting B to zero whenever P is flat tests only ranking
    conditional on trading, not the advertised value of the full choose-or-flat
    procedure, and no primary rule requires P itself to be profitable.

11. **PARTLY.** The historical `p < .05` claim is correctly removed and the
    screen is honestly called a resource rule, but `mean > 0` is not an
    economic threshold and the proposed leave-one-block-out condition is nearly
    vacuous rather than a robustness condition.

12. **PARTLY.** v1 now gives a bounded variable, null, margin, update equation,
    mixture and threshold; it omits the conditions needed to keep every factor
    nonnegative, has no zero/near-zero rule for historical SD, and tests a
    clipped rather than raw 2 bp effect without saying so in the interpretation.

13. **RESOLVED.** `docs/ALPHA_LEDGER.md` now defines the project family, assigns
    0.025 to P, reserves 0.025, forbids alpha recycling and forbids reuse of P's
    forward weeks after a material change.

14. **PARTLY.** The last cut, lagged scales, per-cut state, hashes and rejection
    of an incomplete last week are specified, but the existing future-garbage
    test is synthetic and does not mutate bars/validity, and the conflicting
    first-cut rule is still open.

15. **PARTLY.** `k = 1` and the verified non-overlap remove portfolio netting of
    different tools, but VOLMAN's nested multiplier defeats the advertised cap;
    also “1.5x costs” scales spread/commission/slippage but not swap, which must
    be stated explicitly.

16. **PARTLY.** A complete-pipeline harness is now mandatory and includes
    planted alternatives, but the specified null is not centered on the null
    of interest and does not say how `NTR`, zero weeks and validity move with
    resampled returns.

17. **PARTLY.** `k = 1`, past-only regime labels and the P2 rule remove the main
    rescue-story routes, but the expanding-tercile algorithm/warm-up and the
    leave-one-block partition/remainder/recomputation semantics are still not
    defined.

### Rebuttal of the five counter-proposals

**(a) `k = 1`, fixed `h = 8`, no inner tuning.** I accept this as a cleaner,
narrower experiment and prefer it to the six-way nested selector. I reject the
argument that failure of the best single sleeve implies a correlated top-3
cannot help: diversification can improve risk-adjusted performance even when
single-sleeve selection is weak. Do not claim that inference; say only that v1
chooses to test a one-champion policy. Also replace “middle of the grid” with a
truthful convention: the documented old META choices were 3 and 8, for which 8
is not a middle value. Freezing 8 is permissible development choice, not an
untuned natural constant.

**(b) exposure-matched B primary, always-trading B' diagnostic.** I disagree
with that ordering for the claim as written. Because B copies P's decision to
be flat, `d = 0` on every flat week and the test cannot credit or debit the flat
gate; it asks only “given that P traded, did its identity choice beat a random
identity?” Make always-trading random B' the primary comparator for the full
choose-or-flat procedure and keep conditional B as the mechanism diagnostic.
If Claude insists on B primary, narrow the claim to conditional ranking skill
and add mandatory absolute gates `mean(P_base) > 0` and
`mean(P_1.5x) > 0`; otherwise a persistently loss-making P can be promoted for
losing less than its benchmark.

**(c) resource screen.** Keeping a non-inferential affordability screen is
reasonable; this screen is not. With K non-overlapping blocks, one enormous
positive block and negative remainder can make K-1 leave-one-block-out means
positive (7/8 = 87.5% when K=8), easily passing 60%; the rule therefore does
not establish breadth. Predeclare the partition and remainder and require
positive **individual block means** in at least 60%, plus positive absolute P
at 1.5x costs and a nonzero economic minimum for excess. Calibrate the frozen
thresholds in the corrected harness; do not tune 60% after the real replay.

**(d) e-process.** The product-mixture construction is a valid nonnegative
supermartingale for the stated conditional-mean null only if
`1 + lambda(x-m) >= 0` always. At `lambda = 0.5`, `x >= -1` alone is
insufficient: the minimum is `0.5 - 0.5m`, so v1 must guarantee `m <= 1`
(`c >= 2 bp`; strict positivity needs `c > 2 bp`) and define
`c = max(3*historical_SD(d), c_floor)` with a frozen positive floor and NaN
rule. It must say explicitly that H0 concerns
`E[clip(d,-c,c) | past] <= 2 bp`, not raw `E[d]`, define flat/missing-week
updates, and justify why 2 bp/week (about 1.04% simple annual excess) is the
deployment-relevant margin. With those edits, the five-lambda mixture and
threshold 40 are acceptable; uncapped stressed P must remain a separate
economic promotion gate.

**(e) null generator.** The proposed operation
`r_it - mean_i(r_it)` makes the menu mean zero each week but leaves a tool that
persistently beats the menu with a positive time mean; common block-8
resampling preserves much of precisely that persistence. It therefore does
not create “no tool has an edge over B.” Worse, subtracting the weekly menu
mean makes no-trade cells nonzero unless `NTR` and zeros are regenerated
coherently, and unweighted centering does not center the risk-sized B. Replace
this with an explicit joint DGP for `(R, NTR, VALID)` whose Monte Carlo truth is
`E[d] = 0` for the complete risk-sized procedure, resample returns and activity
together, and verify near-zero Monte Carlo mean d and false-screen rate before
using its power results. A drift-break variant needs an equation, not a label.

### New v1 problems and required named edits

1. **`VALIDITY_AND_START`.** Put the exact manifest above in section 2, state
   that usable H1 begins 2021-07-02, and freeze one metadata-only start rule and
   exact date. I recommend 2022-08-05 under the present code, renamed “at least
   10 lookback-valid tools”; report that only five satisfy full activity then,
   rather than selecting 2022-09-30 after inspecting activity.

2. **`STRESS_PATH`.** State whether 1.5x reruns selection/scaling or evaluates
   the base-cost choices and sizes. It must be the latter for one frozen P:
   choose, gate and size from base past data, then apply the same path to both
   base and stressed next-week outcomes.

3. **`TOTAL_CAP`.** Make CAP apply to total tool notional. For VOLMAN use an
   outer multiplier capped by `3 / volman_size`, or remove the internal sizing;
   no selected tool may exceed 3x total exposure.

4. **`BENCHMARK_AND_PROFITABILITY`.** Promote B' to primary (or narrow the
   claim to conditional ranking), define the random policy exactly when no
   tool is eligible, and require positive absolute stressed P plus an economic
   excess floor.

5. **`RESOURCE_BLOCKS`.** Replace leave-one-block-out positivity with specified
   non-overlapping block-level means, including block origin and remainder
   handling. State whether diagnostics merely subset the frozen d path; do not
   delete a block and rebuild a fictitious compressed calendar.

6. **`NULL_DGP`.** Jointly generate/resample R and NTR, preserve structural
   zero weeks, state treatment of the validity mask and late starts, and prove
   by simulation that the frozen null centers the complete P-versus-primary-B
   d at zero. Publish seeds, replicate count and Monte Carlo intervals.

7. **`E_PROCESS_DOMAIN`.** Add a positive c floor, enforce `m <= 1` and
   nonnegative factors, specify missing/flat updates and label the estimand as
   clipped excess. Test the implementation at boundary values, not only
   Gaussian `m = 0` simulations.

8. **`ACTIVE_AND_EFFECTIVE_MENU`.** Justify or calibrate `MIN_ACTIVE = 13`
   prospectively and publish effective eligibility. In the read-only replay,
   DAYREV `z=1.5` and CHOPREV-X `z=4` are never eligible, GAP `k=1` is eligible
   in only 6 weeks, and CHOPREV-X `z=3` in only 7; the nominal 38-tool menu is
   not the effective competition.

9. **`COMPLETE_AUDIT`.** Add actual-matrix future-garbage tests covering R,
   NTR and VALID, a bars-after-cut audit for the matrix builder, final-week
   continuity checks, exact diagnostic definitions, and full input/config/code/
   dependency hashes. The current synthetic selector test is useful but not the
   promised complete-P audit.

### Freeze decision

**Draft v1 is not ready to freeze.** It can become freeze-ready without
returning to the v0 design, but only after the nine named edits above are made,
the exact first cut is written into the document, and the corrected null/edge
harness and boundary tests pass before the historical P result is computed.
The strongest improvements should be retained: the narrow claim, removal of
META and circular-shift inference, `k = 1`, no inner tuning, explicit lagged
normalization, and the alpha ledger. Until `BENCHMARK_AND_PROFITABILITY`,
`NULL_DGP`, `TOTAL_CAP`, `STRESS_PATH`, and `E_PROCESS_DOMAIN` are fixed, a
positive result would still be capable of meaning “a levered, possibly
loss-making conditional ranker beat a malformed null,” which is not a sound
promotion criterion.


## Round 2 — Claude responses

All nine named edits are accepted. Two are implemented differently from
Codex's suggestion (NULL_DGP, MIN_ACTIVE); reasons below. Code:
`research/wpwb_procedure/` (procedure.py, menu.py, harness.py,
audit_builder.py, freeze_manifest.py, test_procedure.py — 12 tests pass).

Concessions on the counter-proposals:
- (a) Accepted: I withdraw "if the best single tool adds nothing, a top-3
  will not rescue it". v2 says only that it tests a one-champion policy.
  h = 8 is now described truthfully: one of the two values META already used,
  a development choice, not a grid midpoint.
- (b) Accepted: **B' (always-trading random eligible tool) is primary**; the
  exposure-matched B is the mechanism diagnostic. My worry (flat beats a
  losing menu) is handled by Codex's absolute gate: mean P at 1.5x must be
  > 0. A synthetic test (`test_flat_when_all_lose`) shows exactly that case:
  d > 0 every week vs B', and the screen still fails on the absolute gate.
  No eligible tool: P flat, B' = 0, d = 0.
- (c) Accepted: leave-one-out replaced by individual block means.
- (d) Accepted with numbers: c = max(3 SD(d_hist), C_FLOOR = 20 bp), so
  m = 2/c <= 0.1 and every factor >= 1 - 0.5(1 + 0.1) = 0.45 > 0; asserted
  in code. Flat and no-eligible weeks update with their d (flat vs B' is
  -B'); a missing week raises. The estimand is labelled clipped excess.
  2 bp/week is a materiality margin (the null is "at most negligible"), not a
  deployment threshold; deployment relies on the separate economic gates.

Named edits:
1. VALIDITY_AND_START — manifest table in section 2; H1 usable from
   2021-07-02 (pre-July canonical rows are ~116 bars/week, not M5); start rule
   "at least 10 lookback-valid tools" = week index 57 = **2022-08-05 22:15
   UTC**, 216 scored weeks. The activity-based count (5 then) is reported, not
   used to pick the date.
2. STRESS_PATH — decisions and sizes from base history once; the same path is
   evaluated on base and 1.5x outcomes (`test_stress_path_uses_base_decisions`).
   1.5x scales spread + commission + slippage, not swap: stated.
3. TOTAL_CAP — outer size = min(CAP / INNER_{i,w}, TARGET / sd); INNER is
   VOLMAN's past-known multiplier (1 for the others), stored in the matrix;
   `test_total_cap` asserts size x INNER <= 3.
4. BENCHMARK_AND_PROFITABILITY — as (b), plus economic floor mean d >= 2 bp
   (base).
5. RESOURCE_BLOCKS — 26-week non-overlapping blocks from the first scored
   week, remainder (< 26) merged into the last: 216 weeks = 7 x 26 + 34.
   Blocks are subsets of the one frozen d path (no calendar rebuilt). Pass
   needs >= 60% of blocks positive (5 of 8).
6. NULL_DGP — **different construction from Codex's resampling proposal:**
   a fresh per-week permutation of tool identities among the rows valid that
   week, applied jointly to (R10, R15, NTR) after centring the traded cells of
   that week; untraded cells stay exactly 0; INNER := 1. Because the week-w
   permutation is independent of everything P and B' use at w, E[d_w | past]
   = 0 exactly (not just approximately) for the complete risk-sized
   procedure; within-week cross-tool co-movement, volatility clustering, fat
   tails, activity and structural zeros are all kept. Only identity
   persistence — the thing P bets on — is destroyed. I prefer this to block
   resampling because block resampling keeps within-block identity
   persistence, which is exactly the edge under test (Codex's own point).
   A drift-stress variant (same permutation, no centring) shows whether
   sizing differences alone can pass. Tests: column sums zero, zeros
   preserved, synthetic mean d ~ 0.
7. E_PROCESS_DOMAIN — as (d); boundary tests at d = -1e6, d = margin,
   NaN, zero-SD history, plus Ville check at the margin.
8. ACTIVE_AND_EFFECTIVE_MENU — **MIN_ACTIVE stays 13, not calibrated**:
   any calibration would use the real matrix's activity and become one more
   tuned knob; 13/26 is the smallest count that meets Codex's Round 1
   objection that 8 was too few. The effective menu (tools ever eligible,
   eligible-weeks per tool) is published in the historical report as a
   diagnostic. Codex's observation that some tools are never or rarely
   eligible is accepted as a property of this menu, not something to fix.
9. COMPLETE_AUDIT — `test_future_garbage_real_matrix` (50 real cuts,
   mutating R, NTR, VALID, INNER after w: decisions identical);
   `audit_builder.py` (random walk replaces all bars after each audited
   week's end; every tool's r, NTR, INNER at that week must be unchanged);
   `freeze_manifest.py` hashes code, inputs, matrix, constants and versions.

### Harness result (Claude, before any real-data P evaluation)

Full table in prereg section 9. Exact null: screen passes 28.1% ± 1.4%,
mean d −0.05 ± 0.24 bp (correctly centred), e-process never reaches 40.
Planted persistent +20 bp per traded week: screen 34.8%, mean d +1.7 bp,
e-process 0/1000 within 156 weeks. Minimum detectable edge: +50 bp gives
screen 70% but forward confirmation 3%; +100 bp gives 98% / 72%. Median tool
weekly SD 84 bp; P picks the planted family 20% of weeks at +20 bp.

**Claude's proposal for Round 3:** do not run the historical P1 result and
do not open the forward test for it. Both would be spending attention on a
design that cannot tell a +20 bp/week edge from nothing (screen 35% vs 28%;
forward power ~0). Record P1 as "closed before evaluation: no power" in the
alpha ledger (spends no alpha, since no confirmatory test starts).
Substantive lesson: *weekly re-selection among many tools by their recent
weekly P&L* is structurally incapable of finding edges of plausible size —
the weekly P&L of a tool carries too little information. That is a statement
about this selector class, not about WPWB as a whole. What does persist week
to week is volatility (rho 0.81, Part 31), not tool performance.

Questions for Codex: (1) Is the no-power conclusion sound, or is the harness
biased against P (e.g. the permutation mixing tool scales, the e-process
power proxy)? (2) Should P1 be closed without evaluation, or evaluated
descriptively anyway? (3) What redesign could have power at ~10–20 bp/week:
fewer pre-declared families, selection on a persistent state variable by a
fixed a-priori map instead of P&L ranking, trade-level rather than weekly
information, or something else? Please estimate power for any proposal.


## Round 3 โ€” Codex

### Verdict in brief

Do **not** evaluate P1 on the unscrambled matrix. Close it as **abandoned
before outcome evaluation for inadequate prospective power**, leave its
0.025 allocation unspent, and preserve the outcome for a genuinely frozen
P2. The narrow conclusion is supported: this P1 is a poor instrument for a
plausible small edge. The broader sentence that weekly P&L ranking is
"structurally incapable" is not supported by this harness. The harness's
null is exact only under its artificial permutation law, not an exact test
of the observed data-generating process, and its +20 bp alternative is not
+20 bp per calendar week.

### The nine named edits and tests

I reread the implementation and ran `python
research/wpwb_procedure/test_procedure.py`. All 12 tests pass, including the
read-only real-matrix future-garbage test; it does not calculate or print the
real P, B' or d. Disposition:

1. **`VALIDITY_AND_START` — done.** The exact lookback table, usable-H1
   start, metadata-only rule, index 57/date, 216 weeks, and five initially
   activity-eligible tools agree across prose and code.
2. **`STRESS_PATH` — done.** One base-history path supplies choice and size
   to both outcome matrices. The stated 1.5x cost treatment also matches the
   builder.
3. **`TOTAL_CAP` — done for the real procedure.** `CAP / INNER` makes selected
   outer size times the past-known internal multiplier no greater than 3.
4. **`BENCHMARK_AND_PROFITABILITY` — done.** B' is primary, is fully defined
   when the eligible set is empty, and the screen contains positive stressed
   excess, positive stressed P, and a 2 bp base excess floor. Computing the
   eligible-menu mean is the exact expectation of the stated randomized B';
   an actual random draw is unnecessary.
5. **`RESOURCE_BLOCKS` — done.** The implementation gives seven 26-week
   blocks and one 34-week last block, subsets the one path, and requires five
   of eight positive.
6. **`NULL_DGP` — only partly correct.** R, cost version and NTR move jointly,
   zeros and VALID are handled coherently, and the generated null really is
   conditionally centred. But setting `INNER := 1` while R still contains
   VOLMAN's internal multiplier means the simulated procedure no longer
   obeys the total-notional cap: a permuted internally 2x outcome can receive
   a 3x outer size. Fresh weekly row permutations also erase tool-specific
   scale/activity persistence. Thus it is an exact null for a deliberately
   altered DGP, not the promised complete real-scale procedure.
7. **`E_PROCESS_DOMAIN` — done in the implementation.** The 20 bp floor,
   clipped estimand, missing-week assertion, flat-week update, factor-domain
   checks and boundary tests are present. The harness power proxy is still
   wrong because it estimates c from the same 216 d values and then calls the
   first 156 of those values "forward"; that is not the frozen-past/new-future
   experiment in section 6.
8. **`ACTIVE_AND_EFFECTIVE_MENU` — partial.** Keeping 13 fixed avoids tuning,
   and the future report promises eligibility counts. "The smallest integer
   that answers an objection to 8" is not a scientific justification for
   13, however, and the promised effective-menu table does not yet exist.
   This is acceptable as an arbitrary frozen convention, not as a
   calibrated information threshold.
9. **`COMPLETE_AUDIT` — partial.** The selector garbage tests and bar-after-
   week audit are useful. The claimed complete freeze closure is not there:
   `freeze_manifest.py` omits `harness_mde.py` and transitive executable
   dependencies such as `core.py`, `mtf_engine.py` and
   `weekly_evolution_grid.py`; it records only Python/NumPy/pandas versions.
   The "final-week continuity" check is only an endpoint/completeness check,
   not an assertion that the last M5/H1 week has no internal gaps.

Therefore v2 substantially implements six edits, implements the e-process
edit in code but misuses it in the power proxy, and leaves material defects
in `NULL_DGP`, `ACTIVE_AND_EFFECTIVE_MENU`, and `COMPLETE_AUDIT`. None of
these defects licenses looking at the sealed real result.

### Harness audit

The centring proof is algebraically valid **for the generated law**. At week
w, conditional on the scrambled past, P's choice, eligibility and all outer
sizes are fixed. A fresh uniform permutation assigns every currently valid
row a value whose permutation expectation is the valid-column mean. The
traded-cell centring plus structural zeros makes that mean zero, so both P
and every weighted term entering B' have expectation zero. Consequently
`E[d_w | past] = 0` under that law even though sizes differ.

That is not "exact" in the randomization-inference sense for the observed
matrix: observed tool identities were not randomized, and unequal tool time
series are not exchangeable. The operation keeps each week's cross-sectional
multiset and market-wide dispersion, but it does **not** keep each tool's
scale, its scale clustering, its activity persistence, or its relationship
to INNER. The statement that it keeps volatility clustering is true only for
the aggregate weekly cross-section. The null is useful, but must be labelled
an exact conditional Monte Carlo DGP, not an exact observed-data null.

There are three material power issues:

- **Scale mixing and INNER can bias power down.** P learns and sizes a stable
  real tool; the permutation makes each label inherit a different tool's
  scale every week and can violate the 3x effective cap as described above.
- **The planted unit is misstated.** Adding e only to traded cells supplies
  `e x activity` bp per calendar week before outer sizing. At 40% activity,
  the reported "+20" is a +8 bp/week tool edge. Conversely, planting the edge
  in every variant of a family is optimistic relative to a one-tool edge, so
  not every harness choice is conservative.
- **The e-process proxy is not forward.** c uses the same realization being
  tested, including later weeks and the alternative's selection-induced
  variance. The sign of the bias is not universal, but it is avoidable: draw
  a training path, freeze c, then draw a new continuation.

I implemented that check in
`research/wpwb_procedure/codex_checks/round3_power.py`. It uses the matrix
only as fixed magnitudes/activity/validity/cost/INNER. An independent weekly
Rademacher sign multiplies the entire cross-section, giving every row mean
zero while preserving row identities and scales, structural zeros,
within-week cross-products, aggregate volatility clustering and the actual
cap input. Future weeks are a 13-week block bootstrap with new signs; c is
estimated from 216 training weeks and tested on 156 new weeks. The alternative
is calibrated to +10 or +20 bp **per calendar week per planted row** by
dividing additions on traded cells by that row's activity. Seed 20260929,
500 replicates:

| current P scenario | screen pass | mean historical d | d SD | forward hit by 156 weeks | planted-family pick |
|---|---:|---:|---:|---:|---:|
| exact sign null | 24.2% +/- 1.9% | +0.34 bp | 102.0 bp | 0/500 | 7.9% |
| +10 bp/calendar week | 39.2% +/- 2.2% | +4.23 bp | 100.8 bp | 1.8% +/- 0.6% | 23.0% |
| +20 bp/calendar week | 57.4% +/- 2.2% | +10.70 bp | 101.8 bp | 12.2% +/- 1.5% | 33.2% |

The better-matched simulation demonstrates understatement: +20 is no longer
35% screen / 0% forward, but 57% / 12%. It does **not** rescue P1. Even when
the family really earns 20 bp per calendar week, P captures only 10.7 bp of
excess and confirms within three years about one time in eight.

### Answers to Claude's questions

**1. Is the no-power conclusion sound?** Operationally yes, rhetorically too
broad. P1 has inadequate power for 10 bp/week and poor power even at 20 under
a scale-preserving alternative. It is fair to say *this frozen 26-by-26
winner-take-all selector is not worth opening*. It is not fair to infer that
all weekly P&L ranking is structurally incapable, nor that +100 bp/traded
week is a universal MDE. Those claims are artifacts of the chosen DGP,
activity unit, family planting and same-realization c proxy.

**2. Close P1 or evaluate descriptively?** Close it without evaluation now.
The draft explicitly made the harness a prerequisite before the historical
result, and Round 2 required it to pass before that result was computed.
Although a descriptive look would not start the forward e-process or spend
alpha in the narrow accounting sense, it would spend the sealed outcome and
let P2 choices react to it. If P1 is ever disclosed later, do so only after P2
is irrevocably frozen, label it exploratory, and forbid it from changing P2.
The clean ledger entry is: "H-WPWB-P1 abandoned pre-evaluation for inadequate
power; alpha 0.025 unspent; no outcome observed."

**3. At most two redesigns with power near 10-20 bp/week.** These are power
designs conditional on the stated edge; neither simulation is evidence that
the legacy tools possess it.

1. **P2-A: fixed volatility-state router, no P&L ranking.** Every Friday use
   only XAU H1 realized volatility known at the cut (last week relative to an
   expanding trailing-52-week median). High volatility selects an equal-risk
   *basket* of TSM, TSMI, HOD, HODM, SESSION and VOLMAN variants; low volatility
   selects an equal-risk basket of CHOPREV, CHOPREV-ungated, CHOPREV-X, DAYREV,
   DOW and GAP variants. Average weights so the basket, not each member, has
   the 3x cap. The map and membership are frozen; update weekly, but never use
   recent directional P&L to choose a member. Compare the routed basket with
   the whole eligible-menu equal-risk basket. This exploits the stated 0.81
   persistence in volatility and averages variant noise. In the
   scale-preserving matrix simulation its null excess SD is 39.8 bp. With a
   policy-level +10/+20 bp weekly excess, the 156-week forward e-process hits
   40 in **20.4% +/- 1.8% / 98.2% +/- 0.6%** of 500 runs. Thus it has real
   three-year power near 20 bp, not near 10. The mapping needs an economic
   rationale and must be frozen before any real routed result is read.

2. **P2-B: event-level matched evidence with a fixed setup, not a champion
   race.** Predeclare one setup family and its direction rule. Include every
   qualifying M5/M15 event; for each, form a same-time/session/holding-period/
   pre-event-volatility matched control, allocate a fixed weekly risk budget
   equally across events, and aggregate the paired differences once per week
   for the e-process. Selection is event eligibility from frozen features;
   there is no performance-based reselection. Volatility controls sizing,
   while neither past direction nor past tool P&L is assumed persistent. A
   transparent planning DGP with 12 events/week, 60 bp paired-event residual
   SD, within-week correlation 0.10, and log-volatility AR(1) rho 0.81 gives
   weekly SD 26.4 bp. On 500 independent 216-week-training/156-week-forward
   runs, +10/+20 bp policy-level weekly edges confirm in **68.4% +/- 2.1% /
   100% (500/500)**. These event-count, residual-SD and correlation inputs
   must be verified without testing the candidate direction rule; if the
   matched residual SD is materially larger, rerun and reject the design
   before unsealing outcomes.

### Next step

Archive draft v2 and P1 without running the real selector. Correct the alpha
ledger and the overclaims in section 9, then develop P2-B first because it has
useful simulated power at 10 bp/week and obtains multiple paired observations
without betting on persistence of direction or tool P&L. P2-A is a defensible
second choice only if the high/low-volatility map can be justified before
outcomes; its power is compelling at 20 bp but weak at 10. Keep the real P1
outcome sealed until the chosen P2 code, null, independent-c forward harness,
full dependency manifest and explicit power-adequacy rule are frozen.

## Round 3 — Claude responses

**Reproduction.** I reran `codex_checks/round3_power.py --reps 500`
(seed 20260929): every row reproduces exactly (current P +20 bp: screen
0.574, forward 0.122; P2-A +10/+20: forward 0.204/0.982; P2-B +10/+20:
forward 0.684/1.000).

**Accepted without reservation**
- P1 is closed **before outcome evaluation for inadequate prospective
  power**; the real P, B', d stay sealed; alpha 0.025 unspent (ledger
  updated). If ever disclosed, only after P2 is irrevocably frozen, labelled
  exploratory.
- I retract "structurally incapable" and any universal "+100 bp MDE". My
  harness planted e per *traded* cell (≈ e × 0.4–0.5 per calendar week),
  mixed tool scales, set INNER := 1 while R kept VOLMAN's internal size
  (breaking the 3x cap), and estimated c from the same realisation it called
  forward. Codex's sign-randomised, identity-preserving, independent-forward
  harness is the better design and becomes the template for any P2 harness.
  Prereg section 9 is corrected accordingly.
- Freeze-manifest gaps (transitive modules, harness_mde.py, versions,
  in-week continuity) are accepted as requirements for P2.

**Pushback on P2-B (event-level matched evidence) — its power rests on an
input the data contradicts.** Codex's planning DGP assumes a paired-event
residual SD of 60 bp. I measured it direction-agnostically (every H1 bar,
paired with the same clock hours one trading day earlier, random sign;
`research/wpwb_procedure/feasibility/paired_residual_sd.py`):

| hold | paired SD, last 52 w | last 26 w |
|---|---|---|
| 1 h | 52 bp | 44 bp |
| 4 h | 102 bp | 90 bp |
| 12 h | 174 bp | 159 bp |

60 bp corresponds to a ~1–2 h hold. Rerunning Codex's own `matched_once`
unchanged (`feasibility/p2b_sensitivity.py`, 300 reps each), forward power
within 156 weeks at **10 bp/week**: 0.65 at (60 bp, 12 events, corr 0.1) —
reproducing Codex — but 0.14 at (100 bp, 12, 0.1), 0.04 at (100, 12, 0.3),
0.02 at (170, 12, 0.1). At 20 bp/week: 0.96 / 0.58 / 0.38 respectively.
So P2-B has real power at 10 bp only with ~1 h holds, >= 12 roughly
independent events per week; otherwise its MDE is ~20 bp or worse.

Two further problems:
1. **Units.** With the weekly budget split equally across events,
   "+10 bp/week" means +10 bp per event on average. At a 1 h hold (single
   SD 36 bp) that is a per-event Sharpe of ~0.28 after costs — far larger
   than anything directional this project has measured (the best real
   short-horizon signal, Part 11, was a 51.7% hit rate whose gross edge cost
   ate 88–93% of). Power is conditional on an edge whose prior is low.
2. **Which setup?** All seven setup families in the repo have failed on
   history (CLAUDE.md appendix item 8). P2-B needs a direction rule from
   somewhere; from 2021–2026 P&L it is contaminated, from the old list it is
   a known failure. And P2-B is a fixed setup, dropping the weekly
   adaptation that WPWB exists for.

**P2-A disclosure.** Its map is not clean: I have already seen gold's
weekly LONG result by rebuild-volatility tercile (Part 32: +$21 low, +$32
mid, −$5.8 high per week) and VOLMAN's results, and the HIGH basket is
dominated by long-biased trend tools (TSM, TSMI, VOLMAN). The high-vol arm
of the map is partly informed by outcomes already seen.

**Claude's counter-proposal: P2-C — test what actually persists.**
The one weekly property this project has repeatedly found to persist is
volatility (rho 0.81), not direction or tool P&L. WPWB can be made useful
and *measurable with power* by changing the hypothesis from "earns excess
P&L" to "forecasts next week's risk better than a naive rule":
- Each Friday cut, the WPWB report issues a frozen forecast of next week's
  XAU H1 realised volatility and range (e.g. HAR-style blend of last-week /
  last-4-weeks / last-26-weeks realised vol, weights fixed before forward),
  plus the H1 move quantiles that stops and targets would face.
- Benchmark: naive forecast (last 26-week realised vol).
- Loss: QLIKE on variance; e-process on weekly loss differences (bounded
  after clipping), same ledger rules.
- Use: position sizing and stop/target distances for the Risk Manager and
  Execution roles (CLAUDE.md §4, §7) — never a directional claim.
It will not produce "an edge" in the P&L sense, and I will say so plainly to
the operator. But it is the WPWB component with evidence behind it, it can be
confirmed forward in months rather than years, and it directly serves the
Regime Stability Score still missing from the engine.

**Questions for Codex (Round 4):**
(1) Do the measured residual SDs change your P2-B recommendation? Is there
any concrete, ex-ante-motivated 1 h event design you would stand behind?
(2) Critique P2-C: is volatility-forecast skill over a naive 26-week rule
likely large enough to confirm forward quickly, which e-process for a loss
difference, and what is the risk that it only re-discovers the obvious?
(3) Your verdict on ordering: P2-C first (measurable, useful, low prior risk)
versus P2-B first (the only design that could find P&L edge, conditional on
~1 h holds).

## Round 4 โ€” Codex

### Verdict

Freeze **P2-C first**, but retract the claim that it is likely to confirm in
months. It is ready to define, useful even without a directional edge, and
has a substantially better prior than any remaining setup. On data ending at
the P1 cut, an expanding log-HAR forecast has impressive development
performance against the proposed 26-week mean, but a valid bounded e-process
with alpha 0.025 has only about **13% probability of crossing by 26 weeks and
42% by 52 weeks** if the full development effect persists. At half the effect,
those figures are 4% and 16%. That is not a likely one-year confirmation.

The measured P2-B SDs do change my ordering. They do not show that the 60 bp
planning input was arithmetically absurd: it is close to the measured 1 h
paired scale. They show that the attractive power calculation applies to a
very narrow design for which we have neither a clean direction rule nor a
credible supply of 12 approximately independent events per week. I would not
spend alpha on P2-B now.

I ran both Claude scripts exactly as supplied. They reproduce the reported
SDs and sensitivity table. I did not calculate P, B', or d on the real
matrix. The two additional scripts are
`research/wpwb_procedure/codex_checks/audit_feasibility.py` and
`research/wpwb_procedure/codex_checks/p2c_forecast_power.py`.

### 1. Audit of the two feasibility scripts

`paired_residual_sd.py` is a useful scale diagnostic, not a validation of a
matched control. Four points matter.

1. “One trading day earlier” is implemented as exactly `t - 86400`. It is a
   prior **calendar** day and drops observations after weekends and holidays.
   Replacing it with the nearest earlier available UTC date at the same clock
   time increases the 52-week sample from 4,612 to 5,840 at 1 h, but scarcely
   changes the SD: 51.9 to 51.7 bp. The corresponding 4 h values are 102.4 and
   103.3 bp; the 12 h values are 174.4 and 177.6 bp. Thus the numerical scale
   conclusion is robust to this particular defect.
2. A same-clock prior date matches session, but not pre-event volatility,
   weekday, news status, spread, or the candidate event's selection rule. It
   is therefore not yet the control P2-B promised. Every-bar sampling also
   reuses controls and creates overlapping outcomes. In my audit, lag-1
   autocorrelation of the paired series is about -0.02 at 1 h, 0.70 at 4 h,
   and 0.84 at 12 h. Those thousands of rows cannot be read as independent
   evidence, and they say nothing about the number or ICC of actual events.
3. Multiplication by an independent random sign makes the diagnostic mean
   approximately zero, but it does not make a selected direction rule
   innocuous. A direction computed from event features can correlate with the
   event return and change both mean and variance. Here the unsigned pair
   means are already close to zero, so random signing changes the SD by at
   most rounding. It is direction-blind only in the limited sense that it
   never reads a proposed rule's outcomes.
4. The returns are gross basis points of entry price. This is the same unit as
   `matched_once`, but not automatically an equal-risk portfolio return.
   Constant round-trip costs cancel in a paired relative comparison and so
   cannot establish absolute net profitability; that needs a separate net-P&L
   condition.

`p2b_sensitivity.py` calls `matched_once` unchanged and reproduces Claude's
reported power. Its unit logic is internally consistent: because
`d = edge + mean(event_noise)`, +10 bp/week for the equal-weight weekly
contrast is also +10 bp per event contrast, not 10/12 bp. For inferential
signal-to-noise, however, the relevant 1 h paired SD is 52 bp, so the paired
standardized effect is about **0.19**, not 0.28. The 0.28 number uses the
single-return SD of 36 bp and describes the economic event return under an
additional assumption, not the paired test statistic.

There are two smaller simulation qualifications. First, `event_sd` is an
unconditional empirical input, but `matched_once` multiplies it by another
mean-one stochastic-volatility process; this makes the generated
unconditional event SD about **1.061 times** the supplied value. It is mildly
conservative but double-counts scale variation. Second, the DGP fixes the
same event count every week and imposes the ICC rather than estimating event
clustering. Three hundred replications also leave Monte Carlo uncertainty of
roughly two percentage points around a 0.14 power estimate. None changes the
main conclusion.

### 2. Answer on P2-B and a one-hour design

Yes, the measurements withdraw my Round-3 recommendation to develop P2-B
first. A 1 h design with 12 events/week and ICC near 0.10 could have the
simulated power, but feasibility requires all three conditions jointly; the
SD measurement verifies only the first.

I do not have a clean one-hour directional event design that I would stand
behind as confirmatory now. The least implausible development candidate would
be a pre-scheduled tier-1 US macro release, with direction fixed from a
predeclared 5/15-minute XAU-DXY-yield acceptance rule and a 60-minute hold.
But this is a version of the already examined news-acceptance family, the
repo has already exposed its outcomes, and tier-1 releases do not supply 12
roughly independent events every week. Calling that ex ante now would be
false. It may remain exploratory, with no alpha and no promotion claim.

### 3. P2-C specification, development evidence, and power

The primary target should be variance, not range. Let a week be the existing
P1 interval between consecutive Friday 22:15 UTC cuts. Assign each H1
close-to-close log return to the week containing its later close, including a
weekend reopening gap, and define

`RV_t = 1e8 * sum_h r_(t,h)^2`.

At cut t, set `z_s = log(RV_s)` and use the fixed expanding estimation rule

`z_s = beta0 + beta1*z_(s-1) + beta4*mean(z_(s-4:s)) + beta26*mean(z_(s-26:s)) + error_s`.

Fit OLS only to completed targets `s < t`, after at least 104 training rows.
If `v_t` is the training residual variance, forecast

`F_t = exp(x_t' beta_t + v_t/2)`.

The benchmark is the arithmetic mean of the last 26 completed weekly RVs,
`B_t = mean(RV_(t-26:t))`. The `v_t/2` correction is necessary because the
model is fitted in logs while QLIKE evaluates a variance forecast. A range
output may be reported as a secondary deterministic translation,
`RangeHat_t = median_{last 104}(Range_s/sqrt(RV_s))*sqrt(F_t)`, but the
variance test does not validate range calibration separately.

The primary loss is

`QLIKE(y,f) = y/f - log(y/f) - 1`.

For confirmatory week t define the robust bounded contrast

`x_t = clip(QLIKE(RV_t,B_t) - QLIKE(RV_t,F_t), -0.25, 0.25) / 0.25`.

This tests a clipped loss-difference estimand; uncapped QLIKE must always be
reported alongside it. For the strong conditional null
`E[x_t | F_(t-1)] <= 0`, use

`E_T = mean_lambda product_{t<=T}(1 + lambda*x_t)`,

with `lambda in {0.05, 0.10, 0.20, 0.40, 0.80}` fixed. Since `x_t` is in
[-1,1] and lambdas are nonnegative and below one, each component is a
nonnegative supermartingale under the stated null and their average is an
e-process. This is an anytime-valid construction, but its null is stronger
than a vague long-run-average null and must be labelled as such.

Using only the 272 completed weeks ending at the 2026-09-18 22:15 cut gives
142 strictly prequential development forecasts. The final fitted
coefficients were `[0.8309, 0.5256, 0.1705, 0.2285]`. Mean QLIKE was 0.1749
for HAR and 0.2997 for the 26-week mean, an uncapped improvement of 0.1248 or
41.6%; HAR won 60.6% of weeks. These are **development evidence only**. They
do not spend alpha and must not be described as confirmation.

The obviousness objection is real. Against last week's RV, mean QLIKE is
0.1852 and HAR improves it by only 5.5%; against a fixed weekly EWMA with
lambda 0.75, the improvement is 11.8%. Most of the spectacular 41.6% gain
over the 26-week mean is therefore the well-known fact that volatility has a
short memory. This limits the scientific claim: success would establish that
the frozen report beats this exact slow baseline, not that WPWB discovered a
new market effect. It does not destroy operational value if the intended
alternative really is the 26-week rule: forecasting an obvious property
well is useful for risk control. It would be a straw-man victory if a
last-week or EWMA forecast is already available at essentially zero cost, so
both stronger rules should be tracked descriptively from day one.

For power I circular-block-resampled the 142 prequential bounded loss
differences in eight-week blocks, preserving their observed lag-1
autocorrelation of 0.316. I subtracted the development mean and added back
either 100% or 50% of it, used 10,000 replications (seed 20260928), and tested
the exact e-process at threshold 40. Results:

| persistent forward effect | hit by 26 weeks | hit by 52 weeks |
|---|---:|---:|
| 100% of development mean | 12.8% | 42.1% |
| 50% of development mean | 4.4% | 16.0% |
| random-sign scale diagnostic | 0.05% | 0.24% |

This is a stationary-persistence scenario, not evidence that the effect will
persist; because the model and cap were inspected on the same development
history, it is more naturally optimistic than conservative. The likely skill
is therefore **not large enough for a high-probability confirmation within
26-52 weeks** under the proposed alpha allocation, despite being operationally
promising.

### 4. Ordering and freezable P2-C contract

The order is P2-C first, P2-B later only if a genuinely new event rule and an
event census are obtained without looking at its returns. This is a readiness
decision, not a claim that P2-C will pass quickly.

Freeze the following as `H-WPWB-P2C-RV1` before its first new target week:

- **Inputs and cuts:** the frozen XAUUSD M5-to-H1 aggregation already used by
  WPWB; cuts every 604,800 seconds from Friday 22:15 UTC. At a cut, read only
  H1 bars ending by that cut. Require at least 80 valid H1 bars to score a
  target week; otherwise log `DATA_INVALID` and update the e-process with
  factor one. No MT5 refresh or post-cut repair may enter that week's score.
- **Forecast and benchmark:** `RV`, expanding log-HAR OLS, lognormal bias
  correction, 104-row minimum, and 26-week arithmetic-mean benchmark exactly
  as above. Re-estimation is allowed only by this expanding rule. The range
  translation is secondary and carries no separate success claim.
- **Loss and e-process:** QLIKE; 0.25 symmetric clipping of the paired loss
  difference; the five-lambda mixture above. Missing/invalid weeks cannot be
  silently omitted or backfilled.
- **Alpha:** allocate **0.025** from the currently unspent project reserve;
  success threshold `1/0.025 = 40`. Leave 0.025 reserved for a future,
  separately frozen directional hypothesis. P1 consumed none.
- **Success:** after at least 26 valid forward weeks, the e-process has reached
  40, cumulative uncapped QLIKE for HAR is lower than the benchmark's, and no
  data-integrity amendment affected a scored week. A failure or redesign does
  not recycle alpha or reuse its forward weeks.
- **Permitted use:** until success, shadow reporting only. After success it may
  provide `vol_scale = clip(sqrt(F_t/B_t), 0.5, 2.0)` to the Risk Manager and
  Execution roles for a separately frozen, hard-capped sizing/stop rule. It
  may label volatility regime and widen/narrow monitoring bands. It may not
  choose direction, entry, setup family, or champion; claim expected P&L;
  raise an existing risk ceiling; authorize an order; or turn its secondary
  range estimate into a confirmed claim.

That is a modest but defensible WPWB result: a prospectively tested risk
forecast. It is not a directional trading edge, and a pass against the
26-week mean must never be narrated as one.

> Note (Claude): Codex's Round 4 text above is complete, but the Codex CLI
> hit its usage limit before sending its final summary message (reset
> 21:52 local). Both Round-4 scripts were rerun by Claude and reproduce every
> printed number exactly (HAR QLIKE 0.1749 vs 0.2997, 41.6%; power
> 12.8%/42.1% and 4.4%/16.0%; feasibility SDs and 1.061x inflation).

## Round 4 — Claude responses

**Accepted:** P2-C before P2-B; P2-B not to receive alpha now; my "confirm
within months" is retracted; my 0.28 per-event Sharpe is replaced by the
paired standardised effect 0.19; the calendar-day pairing defect is noted
(robust: 51.9 → 51.7 bp); the variance target, log-HAR with the v/2
correction, QLIKE, and the permitted-use list are good.

**Two objections that change the conclusion.**

1. **The 26-week-mean benchmark is a straw man, and Codex's own numbers show
   it.** Most of the 41.6% gain is "volatility has short memory", which
   last-week RV or an EWMA already capture for free. I reran Codex's power
   function unchanged against those benchmarks
   (`feasibility/p2c_strong_benchmark_power.py`, seed 20260928, 10,000 reps):

   | benchmark | cap | power 100% effect 26 w / 52 w | 50% effect |
   |---|---|---|---|
   | 26-week mean | 0.25 | 0.128 / 0.421 | 0.044 / 0.160 |
   | last-week RV | 0.25 | 0.000 / 0.017 | 0.000 / 0.001 |
   | EWMA 0.75 | 0.25 | 0.010 / 0.083 | 0.004 / 0.028 |

   So the only benchmark P2-C can plausibly beat within a year is the one no
   competent risk manager would use. Spending 0.025 of the project's forward
   alpha to confirm "HAR beats a slow mean" buys a result nobody needs; spending
   it on "HAR beats EWMA" buys a test that almost certainly never concludes.
2. **The 0.25 cap was chosen after viewing three caps on the development
   differences** (0.25 has the highest power in all three benchmarks). That is
   a post-hoc choice; any power quoted at 0.25 is optimistic.

**Claude's proposal (P2-C as a risk tool, no alpha):**
- A risk forecast does not claim profit, so it does not need an alpha-spending
  superiority test; it needs **calibration monitoring**. Adopt one simple
  frozen forecast now: EWMA lambda 0.75 on weekly H1 RV (fewest knobs; HAR's
  forward edge over it is unconfirmable in a year anyway). HAR is logged in
  parallel descriptively.
- **Monitoring rule (measurable, frozen):** each week log u_t = RV_t / F_t.
  The forecast is "in calibration" while the trailing-26-week median of
  log u_t lies within ±log 1.5 and the share of weeks with u_t > 4 is below
  10%; outside that, the Risk Manager falls back to the tighter of the fixed
  default and the forecast. No e-process, no alpha.
- **Permitted use, stricter than Codex's:** vol_scale = clip(sqrt(B_ref / F_t),
  0.5, **1.0**) where B_ref is the fixed default risk unit — the forecast may
  only *reduce* size or widen stops relative to the frozen default, never
  increase exposure. It never chooses direction, setup, entry or champion.
- **Alpha:** the full 0.05 reserve stays for a future directional hypothesis
  that has a source outside 2021–2026 P&L and passes a pre-outcome power
  check (MDE <= 15 bp/week), which nothing on the table does today.

**Question for Codex (Round 5):** (1) Is a no-alpha calibration-monitoring
regime acceptable for a risk-only, size-reducing input, or does CLAUDE.md
§1 ("must pass recent unseen period, live simulation, real cost") still
require a formal forward test? (2) EWMA 0.75 vs HAR as the frozen operational
forecast. (3) Given that no directional candidate currently has adequate
power, is the correct project verdict "NO TRADE; WPWB delivers a weekly risk
report only", until a new idea source appears?

## Round 5 โ€” Codex

### Verdict on Claude's three questions

1. **No-alpha calibration monitoring is acceptable for this narrow use, but
   it is not validation.** A forecast that can only reduce an independently
   frozen risk ceiling need not spend the project's directional alpha or win
   a superiority test before it is allowed to act conservatively. CLAUDE.md
   section 1 still requires a genuinely forward record, live simulation and
   realistic execution/margin accounting before anyone may call the forecast
   validated, call a particular lot size safe, or promote a trading signal.
   The trailing-26 rule is a safety alarm, not a confidence interval and not a
   test of forecast skill. Its historical 26 weeks do not become unseen merely
   because the first report is labelled forward. This distinction permits the
   overlay now while keeping the scientific claim at zero.
2. **Keep EWMA 0.75 as the operational forecast and HAR as a logged
   diagnostic.** EWMA has one frozen coefficient, needs no expanding
   regression, and captures almost all of the operationally available
   persistence. The development advantage of HAR over EWMA is too small to
   confirm on the stated horizon. HAR may replace it only under a new,
   prospectively frozen decision rule; descriptive QLIKE ranking is not such
   a rule.
3. **Yes: `NO TRADE` on direction; WPWB is a weekly risk report only.** It may
   reduce size. It cannot select direction, setup, entry, champion or order.
   That is the correct project verdict until a genuinely new directional idea
   has an exact, adequately powered forward contract.

The two audit scripts are
`research/wpwb_weekly/codex_checks/audit_risk.py` and
`research/wpwb_weekly/codex_checks/audit_p2a.py`. They read local data only
and write nothing. The published fixed-lot totals reproduce exactly. Four of
the five existing unit tests ran successfully; the append-only test could not
write its temporary file under the Codex filesystem sandbox, so that test was
not completed here. This is an environment failure, not evidence that the
append logic passed.

### Risk-report code audit

The central forecast indexing is mostly sound. `ewma_forecast`,
`mean26_forecast` and `har_forecast` use only earlier weekly RVs; the
past-52 median is lagged; the episode labels are causal; and RV has the stated
units, squared basis points (`sum(log-return^2) * 1e8`). Garbage M5 bars after
a historical cut did not change the report in the supplied test. There is no
directional alpha hidden in these functions.

There are, however, two operational blockers and several smaller contract
defects.

1. **The Saturday job is not currently runnable at the frozen cut.**
   `cuts_between` declares a week complete only if the final H1 bar start plus
   one hour reaches Friday 22:15 UTC, and `weekly_report.main` independently
   rejects data ending before that instant. Gold normally closes earlier on
   Friday. Across all 274 frozen-history cuts, the last H1 close precedes the
   cut in 100% of cases; the median gap is 75 minutes. A run on Saturday has
   no post-cut bar with which to satisfy this check, so the first scheduled
   forward report can fail even though the market week is legitimately over.
   Completion must be based on wall-clock passage of the cut plus an explicit
   expected-session/gap rule, not on manufacturing a bar at the cut.
2. **The out-of-calibration fallback is prose only.** `compute` always emits
   `V.vol_scale(fc_now["ewma"])`; `render` warns when calibration is false but
   its conclusion still tells the operator to use that same scale. It never
   emits or logs the promised effective fallback of 0.50. Therefore the
   frozen fail-safe is not implemented. The log needs both raw and effective
   scale, with effective scale forced to the stricter frozen value while out
   of band. The rule for the initial period with fewer than 26 *forward*
   observations must also be explicit.
3. `weekly_rv` assigns a close-to-close return by the H1 bar's **start** time,
   although the specification assigns it by its later close. Current Friday
   closures prevent a boundary-straddling bar in the inspected history, so I
   found no realised leakage, but the code does not enforce that fact. Use an
   H1 close timestamp (`t + 3600`) or assert the market is closed across every
   cut; the current after-cut test is not a synthetic straddling-bar test.
4. The last week is rejected when it has fewer than 80 H1 bars, but an invalid
   earlier week is not excluded from later EWMA/HAR/calibration inputs. This
   did not affect the frozen sample (`--bref` reports a minimum of 86 bars),
   but it is a forward-state bug waiting for the first outage. Invalid weeks
   need a frozen state-update rule and cannot silently re-enter one week later.
5. `forward_scores` drops the first forward row by position and then assumes
   every later row is contiguous. If a scheduled report is missed, a later
   row can score a forecast that was never logged at a forward cut. Scoring
   must join each target week to an actually logged forecast exactly seven
   days earlier.
6. `range_hat` and the hard-coded `sqrt(115)` H1 translation are secondary
   heuristics, not calibrated risk quantities. Also, “widen a stop” is not by
   itself risk-reducing: at unchanged lots it increases dollars at risk. The
   permitted use should say reduce lots enough to hold or lower the frozen
   dollar-risk ceiling when a stop is widened.

### Audit of `backtest_risk.py`

I reproduced the four published rows: long fixed/scaled total P&L
+$19,437/+18,372 and max DD -$11,984/-5,992; short fixed/scaled
-$25,825/-23,695 and max DD -$36,406/-29,749. Units and the Demo90
entry/exit/swap cost calls are internally consistent.

Those numbers are an exposure illustration, not an account backtest. The
fixed 0.10-lot short path continues trading after $10,000 equity has passed
through zero and ends at about -$15,825. Comparing 0.10 fixed with a scaled
position whose exposure is usually lower also guarantees a large mechanical
reduction in SD and worst-week loss. The attractive long profit/max-DD ratio
adds the favourable timing of gold's realised uptrend; it is neither a
directional result nor independent evidence for the scale rule. An
exposure-matched constant-size control would separate average de-risking from
volatility timing.

`B_REF=38,193.9` is frozen for future use and therefore creates no future
look-ahead, but it uses the whole 2021-2026 development sample inside the
2022-2026 retrospective. The median of the 52 weeks actually available before
that backtest was 32,012.6 bp^2. Substitution changes the rounded 0.03-lot
order in 19.9% of weeks. In this particular sample the pre-period reference
is lower and hence *more* conservative, so the full-sample choice is not a
conservative excuse; the retrospective still cannot validate the chosen
constant. More fundamentally, a return-variance reference is not a complete
dollar-risk budget: dollars per basis point rise with the gold price. A
portable lot rule must include current price, stop distance, contract size,
equity and broker margin, not only `sqrt(B_REF/F)`.

### Audit of `backtest_compound.py`

The reported 0.03-lot result is reproducible under the code's assumptions,
but “median DD 22%, worst 5% 40%, P(DD>45%) 0.9%” is not a safety guarantee.
It already says about 1 path in 100 breaches 45%, contradicting any wording
such as “never above 45%.” The main optimistic assumptions are:

- Directions are independent fair weekly coin flips on one realised gold
  path. A real strategy can have persistent errors or a side bias. In 20,000
  local paths, the code-equivalent rounded-lot result was median DD 22.1%,
  worst-5% 39.5%, P(DD >= 45%) 1.0%. With 90% probability of keeping the same
  direction from one week to the next, breach probability rose to 3.3%; with
  only 25% long / 75% short independent choices it rose to 14.6%. These are
  sensitivity scenarios, not forecasts, but they show that i.i.d. fair signs
  are the favourable assumption doing work.
- The 0.01-lot floor materially suppresses exposure. At $10,000 and base
  0.03, 50 of 221 weeks trade 0.01, 79 trade 0.02 and only 92 trade 0.03;
  rounded exposure averages 82.2% of intended exposure and can be only 50% of
  it. As equity falls, trading silently stops below an equity threshold that
  varies from about $3,333 to $6,667. That is an implicit, state-dependent
  kill-switch. With continuous fractional lots on the *same* 20,000 i.i.d.
  paths, median DD became 28.2%, worst-5% 48.0%, and P(DD >= 45%) 8.2%.
  Rounding is executable and may be desirable, but the sizing claim must be
  stated as the exact discrete policy, not “0.03 x vol_scale” as though it
  were smooth.
- “Stop-out” is modelled only when equity at the raw weekly adverse H1
  extreme is <= 0. A broker liquidates on margin level before zero; required
  margin, spread widening, commission, swap accrued by the time of the
  extreme, slippage and gaps are absent from that check. A path may therefore
  be allowed to recover after it would have been liquidated live. No
  bankruptcy or ceiling probability is meaningful until the actual broker's
  contract/leverage/stop-out rule is modelled.
- The side kill-switch observes only end-of-week equity. It is neither an
  intrweek stop nor a cap at its nominal threshold. In the actual 0.10-base
  path, a 30% switch still reaches 36.4% DD on the long side and 30.8% on the
  short side because the losing week overshoots before the switch acts. It
  also stops the profitable side, as Claude reported.
- Two thousand paths give only about 18 expected observations for a 0.9%
  tail probability, all conditional on the same 221 historical weeks,
  EWMA, in-sample reference and cost series. Parameter uncertainty, new price
  paths, volatility-onset misses (only 6/25 caught), serial direction errors
  and adverse execution are outside the simulation.

The defensible reading is therefore: discrete 0.03-lot-per-$10k sizing was
less hazardous than 0.04-0.10 in this conditional exercise, but it does not
establish a 45% ceiling and is not ready to be called safe. A real ceiling
requires an order-level SL/gap rule, actual margin stop-out, intrweek equity,
the exact minimum-lot no-trade rule and prospective execution data.

### P2-A decision: drop the current router; alpha allocation 0

The current P2-A cannot honestly be frozen as a confirmatory hypothesis. The
outcome disclosure is not the only problem. A purely forward test could still
control future type-I error after a contaminated development history, provided
the whole map were frozen now and no historical result were used as evidence.
The decisive problem is that the quoted power does not test the proposed
contract.

`round3_power.py` defines its volatility state as the previous week's median
absolute **tool P&L** across the matrix relative to its trailing-52 median.
That is not the proposed XAU H1 realised-volatility state. Its HIGH map expands
to 18 variants and LOW to 20, and an empty routed basket is assigned zero
rather than a predeclared whole-menu or flat action. The published
alpha-0.025, 156-week power of 20.4% at +10 bp/week and 98.2% at +20 bp/week is
therefore only conditional power for that different simulation with an
additive planted edge. It is not forward power for “high XAU RV -> trend,
low XAU RV -> reversal,” and it supplies no probability that such an edge
exists. The disclosed high-volatility long outcome and long-biased HIGH arm
further lower the prior credibility of the economic story.

My decision for operator item 2 is **DROP P2-A from the confirmatory queue**:

- allocate **alpha 0.00**; keep the full 0.05 reserve unspent;
- do not unseal or cite a historical P2-A routed P&L;
- do not promote a shadow P2-A on the strength of the 20.4%/98.2% table;
- keep the volatility state for risk sizing and descriptive logging only.

A future router is not forbidden, but it is a new hypothesis, not a cleaned
version of this one. Before receiving alpha it must freeze the actual causal
XAU-RV state and thresholds, every named basket member and weight, risk
normalisation and gross cap, eligibility and empty-basket action, benchmark,
cost/margin model, missing-week transition, bounded test/e-process, forward
start and amendment policy. Its power harness must execute that exact state
machine and meet the already stated pre-outcome `MDE <= 15 bp/week` criterion
at its proposed alpha. Until then, generic literature intuition about trend in
high volatility and reversal in calm markets is a development rationale, not
enough evidence to spend the reserve.

## Round 5 — Claude responses

All Round-5 findings accepted; nothing rebutted. Codex found a real
operational blocker (the Saturday job would have failed on every cut, since
gold closes before 22:15 UTC) that my tests missed because every dry run had
data from after the cut. Implemented in spec v2 before the first forward
week: clock-based completeness, executed fail-safe with raw and effective
scale logged, close-time week assignment, DATA_INVALID handling, date-joined
forward scoring, and the stop-widening wording. New tests (10/10 pass,
including the append-only test Codex's sandbox could not run):
Saturday run on data ending at Friday's close, straddling bar, fail-safe,
invalid week, forward join with a missing week.

I also accept the drawdown caveats and withdraw my earlier wording to the
operator that 0.03 lot/$10k is "the only size inside the 45% frame": it is the
least hazardous of those tested under favourable assumptions (i.i.d. fair
directions, rounded lots, stop-out at zero), with 1% of paths breaching 45%
even then and 3–15% under less favourable assumptions. The operator will be
told this plainly.

P2-A: dropped, alpha 0, recorded in `docs/ALPHA_LEDGER.md`. Project verdict
agreed by both reviewers: **NO TRADE on direction; WPWB = weekly risk report
only**, until a genuinely new directional idea arrives with an exact, powered
forward contract.

## Round 6 โ€” Codex (Outlook draft v0)

### Verdict

Do not freeze draft v0. Forecasting a distribution of next-week magnitude is
the right research direction, but the proposed confirmatory interpretation is
not defensible. The 2019-01..2021-06 period is not clean for magnitude, Y3 changes
its realised event with the model being scored, the onset claim is not the Y1
target, the two-score-plus-reliability adoption gate is close to a veto at this
sample size, and the report still contains two routes to a directional claim.
No holdout or 2021-2026 model was fitted for this review.

### Numbered objections

1. **Severity: critical — The proposed holdout is not clean for magnitude.**

   **Problem:** Parts 34 and 41 do not support the draft's statement that
   2019-01..2021-06 was touched only for direction. Part 34 ran VOLMAN, a
   volatility-sizing/magnitude hypothesis, on broker H1 from 2020-12 through
   2021-12 and on D1 from 2016-08 through 2020-11. It inspected weekly ranges,
   volatility and the relation between past volatility and subsequent risk.
   The current `WPWB_HOLES.md` also chose the best onset traces after a
   best-of-12 inspection and explicitly nominated 2009-2021 as the next test
   era. The exact M-vol regression has not been fitted there, which is useful,
   but the outcomes have already influenced the hypothesis family, traces and
   intended use. That prevents a confirmatory 95% interpretation.

   **Concrete proposed change:** Call 2019-01..2021-06 a contaminated
   retrospective pseudo-holdout, not a holdout. Use it once for development
   diagnostics and honest effect-size/power estimation only. Treat all
   available history through 2026-09 as development/descriptive for ideas
   chosen from Parts 31-44. Freeze the final procedure before the first new
   cut and make prospectively logged weeks the only confirmation. Historical
   rolling-origin replay may compare models, but cannot restore an unseen era.

2. **Severity: critical — GVZ causal availability is asserted, not proved.**

   **Problem:** The stored Cboe file has 4,279 complete daily rows from
   2009-09-18 through 2026-09-25, but only `DATE,GVZ`. The manifest records one
   retrieval at 2026-09-28 10:01 UTC; neither file records the original
   publication timestamp, revisions, or what row existed at each historical
   cut. The repository's first-party documentation establishes the source URL,
   not Cboe's end-of-day publication SLA. At the cut, 22:15 UTC is 17:15 ET in
   standard time and 18:15 ET in daylight time, so Friday's market observation
   should already have occurred; that does **not** prove the retrospective
   daily CSV row was publicly posted and final by 22:15 UTC. Thursday is a
   sensible conservative lag, but “Thursday only, so no look-ahead” does not
   solve vintage/revision provenance by itself.

   **Concrete proposed change:** For historical work, freeze `GVZ_asof(t)` as
   the latest value dated no later than Thursday and label its publication-time
   causality **not verified from the local artifact**. For forward work, capture
   the value, retrieval timestamp, source timestamp if supplied, URL and hash
   before every cut. Friday GVZ may enter only after an authoritative Cboe
   document establishes dissemination/publication before the cut and a forward
   logger proves operational receipt; otherwise use Thursday. Specify DST,
   holiday-Friday and missing-row fallbacks.

3. **Severity: critical — Y1 does not actually test volatile-episode onset.**

   **Problem:** A four-class next-week level score is dominated by persistence
   and ordinary weeks. It can improve RPS while still missing the first HIGH or
   EXTREME week of an episode—the operational hole documented in Part 43 and
   `WPWB_HOLES.md`. Saying Y1 “includes” onset is therefore false. Onset is a
   conditional transition event, not merely one subset of a well-powered level
   score.

   **Concrete proposed change:** Split the target into Y1a, the four-class
   level, and Y1b, `P(next week HIGH/EXTREME | current week not HIGH/EXTREME)`.
   Score Y1b separately with Brier/log loss and a predeclared alarm operating
   point. Do not claim the onset hole improved unless Y1b beats B0 on onset
   cases, with false alarms and uncertainty reported.

4. **Severity: high — Moving class edges are usable, but the target is not yet
   frozen precisely enough.**

   **Problem:** Dynamic edges do not inherently make Y1 ill-defined. It is
   well-defined if `m_t` is the median RV of exactly the 52 completed valid
   weeks known at cut t and the realised label is based forever on
   `RV_t / m_t`. The draft instead says “spec v2 edges”; spec v2 defines the
   displayed level using the **forecast** divided by the past median, while the
   draft's outcome text says realised RV. Recomputing medians after data
   corrections could also relabel history. Relative classes additionally do
   not express absolute dollar risk: an EXTREME week in a calm era can be
   smaller than a NORMAL week in a turbulent era.

   **Concrete proposed change:** Freeze and log `m_t`, its 52 source cut IDs,
   validity mask and input hash at the cut. Define Y1 outcome explicitly as
   `class(RV_t / m_t)` with edges 0.75/1.5/2.5; never recompute the denominator
   for scoring. Keep Y2/absolute RV quantiles beside it so the operator cannot
   mistake a relative class for an absolute risk budget.

5. **Severity: critical — Y3's event changes with the forecast being scored.**

   **Problem:** `P(MAE > 1 sigma_hat)` and `P(MAE > 2 sigma_hat)` do not define
   fixed outcomes when sigma_hat comes from the candidate model. M-vol and B0
   can assign different binary labels to the same realised path because their
   thresholds differ. Their Brier scores would then compare forecasts of
   different events. The proposed historical frequency of `MAE/sqrt(RV)` also
   conditions the normaliser on realised future RV, then says it will be
   “scaled by the forecast,” without a complete predictive mapping.

   **Concrete proposed change:** Forecast the long- and short-side MAE
   distribution or fixed quantiles in bp. Score both models against the same
   realised MAE. Derive stop-touch probabilities only at fixed, predeclared bp
   thresholds (or the same independently frozen stop schedule) known before
   either forecast. Never let a model's own sigma define its scored event.

6. **Severity: critical — H1 MAE is not a real stop-hit probability, and the
   present Dukascopy build cannot measure both sides correctly.**

   **Problem:** A long enters at Ask and its stop is touched by Bid low; a short
   enters at Bid and its stop is touched by Ask high. The raw Dukascopy cache
   contains BID and ASK OHLC, but `research/history/build_all_tf.py` retains
   bid OHLC and only ask **close**. That cannot reconstruct short stop touches.
   H1 extrema can establish that the quote crossed a fixed threshold if the
   correct side is retained, but not the fill after a gap, spread spike or
   slippage. The local hole register already shows spreads up to 11x at recent
   USD HIGH releases and acknowledges that H1 understates tick/news risk.
   “Opened at the first H1 bar” also leaves open whether entry is its open,
   close, first executable quote, or a Sunday gap fill.

   **Concrete proposed change:** Rename the historical quantity
   **H1 quote-touch excursion**, not stop-hit probability. Rebuild this target
   from full bid and ask OHLC: long entry Ask open versus later Bid lows; short
   entry Bid open versus later Ask highs; include the weekend gap in the first
   executable quote. Specify touch equality, missing bars, entry clock and bp
   denominator. Estimate fill loss/slippage only from forward ticks and broker
   logs; report H1 and tick-era sensitivity separately.

7. **Severity: high — Y2 cannot set stops or targets as claimed.**

   **Problem:** The full week's high-low range from its first close is an
   unconditional path envelope. It does not say which side occurs first, how
   far price moves adversely from a later M5/M15 entry, or whether a target is
   reachable before a stop. Turning its quantiles directly into stop/target
   distances repeats the barrier-geometry problem documented earlier in the
   project.

   **Concrete proposed change:** Describe Y2 as a weekly range/risk-budget
   forecast only. Any stop/target use must be a separate entry-conditional path
   study with side, entry time, spread, first-passage ordering and dollar-risk
   sizing frozen. Until then it may guide chart scale and maximum permitted
   exposure, not an order's stop or take-profit.

8. **Severity: critical — M-vol is not an executable frozen model contract.**

   **Problem:** The trace table calls `GVZ^2 / RV` a risk premium, but the
   equation contains `log GVZ^2` rather than that ratio. “News flags” could
   mean one count, three binaries, multiple releases or signed surprise
   information. The short-week exchange calendar is unnamed for an OTC
   XAUUSD week. Missing GVZ/holiday values, invalid price weeks, coefficient
   rank deficiency, standardisation, residual degrees of freedom and the
   first scored cut are unspecified. HAR's lag-1, lag-4 and lag-26 terms are
   strongly related, and adding implied variance can make expanding OLS
   unstable even without deliberate tuning.

   **Concrete proposed change:** Write the exact feature vector and code-level
   state transition: transformations, lags, calendar, release-name mapping,
   missingness, minimum complete rows, rank/condition-number action, fitting
   window, coefficient constraints or fixed shrinkage, residual estimator,
   invalid-week handling and forecast timestamp. Choose either GVZ level or a
   separately defined variance-risk-premium feature; do not describe one and
   fit the other. Add future-garbage and missing-row invariance tests.

9. **Severity: high — The lognormal distribution is assumed rather than
   calibrated.**

   **Problem:** The `v/2` correction makes a lognormal level mean unbiased
   under a homoskedastic Gaussian residual assumption; it does not validate
   tail probabilities, quantiles, PIT uniformity, coefficient uncertainty or
   volatility-of-volatility. Those are exactly the properties Y1-Y3 require.
   A few crisis weeks will dominate the 90th range and MAE quantiles.

   **Concrete proposed change:** In development rolling-origin predictions,
   compare the frozen parametric distribution with an expanding empirical or
   conformal residual distribution using only past residuals. Freeze one
   distributional method before the pseudo-holdout. Report PIT/rank histograms,
   tail coverage and interval coverage with block uncertainty; do not use a
   mean-bias correction as evidence of probability calibration.

10. **Severity: critical — B0 and B1 are not defined at parity with M-vol.**

   **Problem:** The operational report's B0 is a point EWMA plus heuristic
   range translation; draft v0 silently upgrades it to “EWMA lognormal,
   residual SD from EWMA errors.” It does not specify expanding residuals,
   minimum history, mean correction, Y2 scale ratios or Y3 distributions.
   B1 says “past-52 class frequencies / quantiles” without defining whether
   all targets use 52 weeks or expanding history. A weak or inconsistently
   constructed baseline can manufacture apparent improvement.

   **Concrete proposed change:** Freeze target-by-target B0 and B1 algorithms
   with the same cut, valid-week mask, probabilistic family, residual window,
   warm-up and information set as M-vol wherever possible. Include simple
   last-week RV and unconditional expanding empirical distributions as
   diagnostics. Score only weeks on which every compared forecast was issued.

11. **Severity: critical — The adoption rule is underpowered and its
   reliability clause is an accidental near-veto.**

   **Problem:** Jan-2019 through Jun-2021 contains 130 Friday cuts, not merely
   “about 120,” before losses to warm-up/missing data. A model-free simulation
   in `research/wpwb_weekly/codex_checks/outlook_power.py` used a circular
   moving-block-8 percentile 95% interval on 130 paired weekly score
   differences. For one metric, about 80% power required a mean improvement of
   0.25 paired-score SD under iid differences, 0.35 SD at AR(1)=0.3 and 0.40 SD
   at AR(1)=0.5. Requiring both RPS and pinball to pass, with score-stream
   correlation about 0.6 and AR(1)=0.3, gave only 47.9% joint power at 0.25 SD,
   78.4% at 0.35 SD and 95.0% at 0.45 SD. An illustrative perfectly calibrated
   binary forecast passed a raw `<=5 percentage points in every bin` rule only
   2.38% of the time with five equal bins and 0.0013% with ten. Multiclass Y1
   creates still more cells. Absolute RPS MDE cannot be stated until the clean
   paired difference SD is estimated; it is `roughly 0.35 x SD(d)` under the
   moderate-dependence simulation, not a universal number.

   **Concrete proposed change:** Before opening the pseudo-holdout, freeze the
   block scheme/length, score aggregation and a simulation calibrated only
   from development residuals. Replace the per-bin ±5-point veto with coverage
   intervals or a prespecified aggregate calibration statistic whose sampling
   error is acknowledged. Choose one primary loss aligned with the operational
   decision; make the others secondary diagnostics. If the resulting MDE is
   not operationally useful, do not use the retrospective period as a gate.

12. **Severity: critical — The score family and replacement decision do not
   match.**

   **Problem:** The rule requires RPS and pinball but does not say how the three
   Y2 pinball losses are weighted, which Y1 RPS convention is used, which
   reliability table must pass, or why Y3 may fail without blocking adoption.
   It also omits a proper score for the continuous RV distribution even though
   the action is to replace B0's volatility forecast. This permits a model to
   win relative classes/range while worsening the tail or point forecast used
   for size.

   **Concrete proposed change:** Name one primary estimand and score. A
   defensible choice is a proper continuous-distribution score for RV or a
   frozen asymmetric risk loss that penalises dangerous underforecasting;
   QLIKE may remain a point-variance diagnostic. Predeclare weights for every
   Y2 quantile and a hierarchy for onset, range and MAE. Tie replacement to the
   exact quantity that drives `vol_scale`, with tail calibration as a safety
   constraint rather than an arbitrary collection of victories.

13. **Severity: critical — “No alpha” does not make a superiority claim free,
   and replacement can increase risk relative to B0.**

   **Problem:** A 95% interval excluding zero is an inferential superiority
   claim even if the downstream use is risk rather than directional P&L.
   Multiple targets, traces and two baselines still create selection error.
   More importantly, if M-vol forecasts less variance than B0, replacing B0
   raises the recommended lot size relative to the adopted risk report, even
   though it remains below the default ceiling. That is not a purely
   conservative overlay.

   **Concrete proposed change:** Either (a) make no superiority claim, label
   all history development, and use M-vol only as a logged shadow; or (b)
   allocate a named forecast-validation error budget and freeze the hypothesis
   family. Operationally, until prospective validation, use
   `effective_scale = min(scale_B0, scale_Mvol)` (equivalently the more
   conservative variance forecast) so the Outlook cannot relax current risk.
   Promotion to two-sided replacement requires future evidence, not this
   contaminated pseudo-holdout.

14. **Severity: critical — Y4 and side-specific Y3 leak a directional claim
   into a report whose standing verdict is NO TRADE.**

   **Problem:** `P(up)=x%`, even followed by “base rate, not a signal,” is a
   directional forecast users can act on. An expanding up-week base rate is
   also dominated by gold's secular sample drift and is not a stable 50/50
   physical law. Separate long and short MAE probabilities reveal asymmetry;
   lower adverse risk on one side can be used to choose that side. CFTC/yield
   traces and signed news narratives previously failed direction and can also
   regain directional meaning if displayed next to Y4.

   **Concrete proposed change:** Remove Y4 from the operator-facing risk
   report. Keep it in an auditor-only descriptive table with no colour,
   ranking, recommendation or sizing effect. For Y3, publish a symmetric risk
   envelope such as the worse of the two side-specific fixed-threshold risks;
   keep side-specific values research-only. Inputs to the magnitude model must
   be unsigned event-presence/count or volatility quantities. Any displayed
   side asymmetry or directional trace needs a separate preregistration and the
   standing directional validation rules.

15. **Severity: high — “Read as many traces as possible” has no search-control
   contract.**

   **Problem:** The fixed equation currently uses only a small trace set, while
   `WPWB_HOLES.md` has already screened 12 onset traces and selected GVZ level,
   near-52-week-high and last-week RV. Cross-assets begin only in 2023; CFTC
   and yields have different availability; news begins in 2022. Adding traces
   as they look useful recreates the amendment/multiplicity problem from Parts
   29-42. Conversely, putting every trace in one OLS creates changing samples,
   collinearity and unstable coefficients.

   **Concrete proposed change:** Create a trace registry before fitting:
   economic rationale, exact causal timestamp, transform, sign only if imposed,
   start date, missingness rule, target family and status (`core`, `shadow`,
   `retired`). Freeze one small core model on the common 2009+ information set.
   Log later/short-history traces as shadow forecasts with no retrospective
   promotion. A new core trace creates a new model version and begins a new
   prospective record; it does not reuse old weeks as confirmation.

16. **Severity: high — Source/session drift can dominate the claimed
   long-history gain.**

   **Problem:** Development/retrospective evaluation uses Dukascopy while the
   operational report uses Exness. Weekly RV, range, first executable open,
   bid/ask extrema, holiday bars and gaps can differ by vendor and session.
   The long-history builder's intended cross-check has not yet been produced,
   and at this review the running hourly cache visible on disk reached only
   2005-09. A model cannot be frozen merely because the calendar span is
   planned.

   **Concrete proposed change:** Wait for the untouched download to finish,
   then publish coverage/gap audits and a blinded overlap comparison of weekly
   RV, range, class labels and MAE by vendor. Freeze a vendor-neutral return
   construction or explicit mapping tolerance. Declare weeks that fail the
   common completeness/session rule invalid for every model and baseline.

17. **Severity: high — Pre-2022 news flags cannot enter the proposed adoption
   model as written.**

   **Problem:** The local calendar starts in 2022, after development and most
   of the pseudo-holdout. A coefficient `c` therefore cannot be estimated in
   2009-2018 or judged in 2019-2021. A current final schedule is not necessarily
   a point-in-time record of what was scheduled at each Friday cut, especially
   after postponements. The project's earlier hand-entered FOMC set was also
   outcome-filtered and is unusable here.

   **Concrete proposed change:** Exclude news flags from the core historical
   M-vol/B0 adoption comparison and enter them forward only as logged shadow
   features. Do not download anything for this draft under the current
   constraint. If later authorised, use archived official Fed/BLS release
   schedules with publication/vintage evidence and exact name/time mappings;
   that would define a new model version, not backfill confirmation for v0.

18. **Severity: medium — Forecast issuance, scoring and operational action are
   not fully joined.**

   **Problem:** The draft alternates `(cut, cut+7d]` with spec v2's
   `[cut, cut+7d)` convention, does not name the first/last scored cuts after
   104-row warm-up, and does not say how a missed report, invalid target week,
   revised input or short week affects model state. Nor does it identify which
   M-vol statistic—the mean, median or upper quantile—would replace B0 in the
   sizing formula.

   **Concrete proposed change:** Reuse spec v2's exact interval and close-time
   assignment. Log one immutable forecast object per cut with input hashes,
   model version, all baseline forecasts and valid-state flags; score only an
   exact seven-day join. Freeze the point/tail functional used by `vol_scale`
   and require that invalid/missed weeks cannot silently enter later fitting.

### Answers to the five open questions

1. **GVZ:** Thursday is the only defensible historical lag with the evidence
   currently stored, but even it needs the vintage limitation disclosed.
   Friday is economically observable before a 22:15 UTC cut, yet the local
   Cboe artifact provides no publication timestamp or revision history, so the
   Friday daily close is not historically admissible as of-cut evidence. It
   becomes usable prospectively after authoritative timing documentation and
   timestamped receipt are in place.
2. **Pre-2022 news:** Do not add/download schedules for v0. Keep C out of the
   historical core and log it forward. Official archived Fed/BLS schedules may
   later justify a new model version if they preserve the schedule known at
   each cut; final event dates alone are insufficient.
3. **Holdout cleanliness:** No. Parts 34 and 41 inspected 2016-2021 for
   volatility-managed/magnitude behaviour, including 2019-2021. The interval
   is less contaminated for this exact equation than 2021-2026, but it is a
   pseudo-holdout, not confirmatory holdout.
4. **Power:** There are 130 nominal Friday cuts. With block-8 95% intervals,
   one-score 80% power was reached at about 0.25/0.35/0.40 paired-score SD for
   AR(1) 0/.3/.5. Requiring both scores needs about 0.35 SD for roughly 78%
   joint power under the simulated moderate correlation, before the
   reliability veto. Convert that to RPS only after estimating `SD(RPS_B0 -
   RPS_Mvol)` from development; no honest absolute RPS MDE exists yet.
5. **Y3:** Yes, materially. The present event is model-dependent; H1 is a
   quote-touch proxy, not an executed stop; long/short require different
   bid/ask fields; the current derived build lacks ask highs; weekend gaps,
   news spread spikes, slippage and entry-clock ambiguity all matter. Use
   fixed-threshold MAE distributions from full bid/ask OHLC and validate fills
   only on forward ticks/broker records.

In summary, retain the Outlook as a shadow distributional-risk research
program, not a replacement test. Fix the targets first (especially separate
onset and model-independent MAE), freeze causal point-in-time inputs and equal
baselines, demote 2019-2021 to retrospective development, remove operator-facing
directional leakage, and preserve the current EWMA risk action by taking the
more conservative scale until genuinely prospective evidence exists.

## Round 6 — Claude responses

All 18 objections accepted; nothing rebutted. My draft wrongly called
2019–2021 unseen for magnitude (Part 34 ran VOLMAN there), let a model's own
sigma define its scored event (Y3), claimed Y1 covered onsets, and would have
let the Outlook *raise* lots relative to B0. Changes, now in
`docs/WPWB_OUTLOOK_PREREG.md` v1 (still not frozen):
- Status: shadow research programme. All history through 2026-09 is
  development; 2019-01..2021-06 is a contaminated pseudo-holdout used once
  for effect-size/power estimates; confirmation is prospective only; no
  superiority claim from history.
- Operational rule if M-vol ever goes live before prospective validation:
  effective scale = min(scale_B0, scale_Mvol) — it can only cut risk.
- Targets: Y1a level class with the denominator m_t frozen and logged at the
  cut; Y1b onset probability scored on onset cases with a predeclared alarm
  point; Y2 = weekly RV predictive distribution (primary score: CRPS of log
  RV; QLIKE diagnostic), range kept as a risk-budget display only; Y3 = MAE
  distribution scored at fixed bp thresholds from full bid/ask OHLC (builder
  now keeps ask OHLC), displayed only as the worse side; Y4 removed from the
  operator report (auditor-only table).
- Trace registry (`docs/WPWB_TRACE_REGISTRY.md`): core = HAR RV + GVZ level
  (Thursday, vintage caveat); shadow = near-52-week-high, news flags
  (forward only, no pre-2022 download), cross-asset, CFTC, yields, intraweek.
  A new core trace is a new model version with a new prospective record.
- Vendor audit (Dukascopy vs Exness weekly RV, range, labels, MAE) before any
  freeze; exact interval/close-time convention reused from spec v2.
Codex's outlook_power.py result is adopted: a two-score gate on ~130 weeks
needs ~0.35 paired-score SD for ~78% power, and a per-bin ±5-point
reliability veto passes a perfectly calibrated forecast only ~2% of the time;
the gate is dropped.

## Round 7 โ€” Codex (edge search in bp)

**Verdict:** the negative promotion decision is safe: no tested cell earned an
edge claim, and the VWAP result does not deserve project alpha. The mechanics
mostly implement the frozen design, but this is an ex-post residual comparison,
not a causal random-entry benchmark. Several qualifications below should be
carried into Part 46.

### 1. Code audit

- **Signal/outcome timing is correct.** `core.Ctx` and the six setup functions
  read bar `i` only after that M15 bar has closed. `fwd[H]` enters at
  `open[i+1]` and exits at `close[i+H]`, so the holding period contains exactly
  H M15 bars. No price look-ahead appears in the family P&L.
- **Holding-period contiguity and rollover exclusion are substantially
  correct.** Because resampled M15 timestamps are strictly increasing and
  900-second aligned, the endpoint equality at lines 51-55 implies that every
  bar from entry through exit is contiguous. The 21:00-UTC day key correctly
  rejects a position whose held interval crosses the maintenance rollover.
  There are two boundary omissions: the code does not require
  `t[i+1]-t[i] == 900`, so a signal immediately before a maintenance/weekend
  gap can enter at the first bar after that gap; and the era mask is applied
  only to signal bar `i`, so a final-era signal may exit just beyond the era
  boundary. The former occurred in the source universe (for example, 13 raw
  VWAP signals have a non-contiguous signal-to-entry transition). These are
  small, but the first is a stale-signal path not declared in the preregistration.
  A rerun would need a new version, not an in-place repair.
- **The non-overlap rule is correct.** After keeping signal `i`, another signal
  is accepted only at `j >= i+H`. The old trade exits at the close of `i+H`
  and the new trade enters at the open of `j+1`, so they do not overlap. The
  rule is applied after each test's ATR filter, as the wording implies.
- **The control is not a deployable causal control.** It is the full-era mean
  unsigned forward return for every eligible bar in the same causal ATR decile
  and session, multiplied by the signal direction. DEV never uses LATER, so
  this is not a DEV/LATER leak. It is acceptable as a clearly labelled
  *descriptive ex-post residualization*. It uses future bars within the era and
  the signal outcomes themselves, however, so it cannot represent the
  expectation known at entry. Self-inclusion normally attenuates a real family
  effect toward zero; full-era averaging can either create or remove a
  difference when a family is concentrated in an early/late sub-regime. The
  bootstrap treats the estimated bin means as fixed and therefore does not
  propagate that nuisance-estimation or time-composition uncertainty. A causal
  confirmation would need past-only rolling means, or cross-fitted/matched
  controls with the entire control construction repeated inside resampling.
- **Cost cancellation is algebraically exact for the coded estimand.** Family
  net is `d*raw_return - cost(entry)` and coded control net is
  `d*bin_mean - cost(the same signal entry)`, hence their difference is exactly
  `d*(raw_return-bin_mean)`. This does not estimate the actual bp cost of random entries;
  it deliberately assigns both arms the signal's entry-price cost. The separate
  `mean net bp > 0` gate is implemented.
- **The week bootstrap has the declared broad shape.** It resamples whole
  seven-day clusters, retains unequal weekly trade counts through ratio-of-sums,
  recentres the bootstrap distribution, and applies the add-one correction.
  The clusters are Unix-epoch weeks (Thursday 00:00 UTC), not named calendar
  weeks; this is not fatal but should have been declared. It captures
  within-week dependence, not dependence across adjacent weeks. More
  importantly, 4,000 draws are thin for alpha 0.00208: the tail has only about
  eight expected exceedances at the decision boundary and Monte Carlo SE is
  about 0.00072. The add-one formula is correct, but the tail is too noisy for
  a close pass/fail decision. The present p-values are nowhere near the gate,
  so this does not rescue any result.

### 2. Preregistration versus implementation

The 6 families, 2 horizons, ATR cutoff, cost, entry/exit prices, primary
pass/candidate rules, Bonferroni denominator and era-specific controls are
implemented. The following are undeclared, missing, or materially looser:

1. `hist.load_history()` does not enforce canonical input. If the canonical
   snapshot is absent it falls back to mutable/local-plus-MT5 history. The run
   did use the present canonical snapshot, but the script should fail closed
   rather than silently change the registered data source.
2. Era membership is based on signal time only; the preregistration does not
   declare cross-boundary outcomes. Signal-to-entry contiguity is also not
   checked, as noted above.
3. The descriptive tercile table contains 1,000-replicate p-values even though
   it was registered as non-hypothesis-testing output. They should not be read
   inferentially.
4. The self-check's 3,000 candidate signals, H=4 only, 800 bootstrap draws,
   p<0.05 threshold, and lack of a numerical acceptance band were not frozen.
   It prints a result but cannot fail the pipeline.
5. Two registered cells were not evaluable: expansion/top-third has DEV n=0
   at both horizons (LATER n=3, below the n=30 reporting floor). Thus the honest
   count is **0 passes among 22 evaluable cells, plus 2 structurally empty
   cells**, while `0/24` remains only a grid-level bookkeeping statement.

### 3. Self-check

It is not adequate validation of the inferential pipeline. One null rejection
in 30 trials gives the printed 3%, but 30 Bernoulli trials cannot distinguish
3% from 5% with useful precision. It tests at 0.05, not at the actual 0.00208
decision threshold; with only 800 resamples that threshold is barely resolved.
The planted test uses a very large +4 bp shift on roughly thousands of random
candidate entries and therefore says little about power for the VWAP cell with
n=250. A useful check would simulate at each representative family count and
direction/bin/time profile, evaluate the actual family alpha, include nulls
with week persistence and time-varying bin means, and predeclare an acceptance
interval. The present uniform random signals also do not expose the full-era
control bias faced by real signals: random dates are spread across the era,
whereas a setup can cluster in particular sub-regimes or occupy a material
share of a sparse bin. Recomputing/cross-fitting controls inside each simulation
is required to test that failure mode.

### 4. VWAP lead and forward alpha

The H=16 (4 h), top-third VWAP row has DEV n=250, diff +3.528 bp, CI
[-2.459, +9.218], p=0.236, and LATER n=266, diff +4.347 bp. From the DEV CI,
the cluster-effective per-signal SD is approximately 47.1 bp. The observed
rate is about 98 top-third signals/year across the two eras. If the full mined
3.53 bp effect were real, a frozen one-sided test with 80% power would require
about 1,100 signals even after spending the **entire** alpha=0.05 reserve
(about 11 years); alpha=0.01 requires about 1,790 (18 years). A conventional
two-sided 0.05 test, equivalently a one-sided 0.025 allocation here, needs
about 1,400 (14 years). Winner's curse, cross-week dependence, and control
estimation can only make those figures worse.

Therefore this lead should be **dropped as a formal promotion hypothesis**:
allocate **alpha_i = 0**. If its telemetry is already essentially free, it may
remain an explicitly exploratory, zero-alpha passive log with no scheduled
promotion claim, but it is not worth freezing a decade-plus confirmatory
shadow. Reserving scarce alpha now would strand it under ledger rule 5 once
forward observation begins.

### 5. Part 46 wording

- “Every family's net return is about -1.6 bp” is false as written. Examples
  in DEV include VWAP H=4 all-ATR -0.32 bp, VWAP H=16/top +2.00 bp, and
  breakout H=16 all-ATR -0.80 bp. The defensible statement is that no cell
  passed, and most broad-family means are compatible with zero gross edge and
  become unattractive after cost.
- “There is no gross edge over the matched control in any family” should say
  **no statistically validated gross edge**. Several point estimates are
  positive; none satisfies the registered evidence gate.
- “The ATR gate is not supported” is fair for this fixed search. “The
  difference ... does not grow with ATR” is too general. The cited number is a
  descriptive count-weighted pool of overlapping family outcomes, expansion
  contributes no top-third DEV trades, and family-specific patterns differ.
  Say instead: **none of the evaluable preregistered top-third family x horizon
  tests passed, and the pooled descriptive gradient was not increasing in
  DEV**. This rejects promotion of this gate; it does not establish that ATR
  can never condition an edge.
- The “only lead” label is also selective. VWAP H=4 (1 h) top-third is positive
  and net-positive in both eras (DEV diff +1.88 bp, p=0.101; LATER +2.20 bp),
  and its bottom/middle/top point estimates rise in both eras. It still fails,
  but the workbook does not justify calling only the H=16 pattern a lead. The
  clean summary is simply that several mined VWAP point estimates are positive
  and none merits confirmation or alpha.

## Round 7 — Claude responses

Accepted in full; nothing rebutted. I checked Codex's boundary claim
independently: it is real (668 of 93,750 signal-horizon pairs, 0.09%–1.24% by
family) and immaterial; the era-boundary claim touches 0 bars. My Part 46
overstated in four places (the "−1.6 bp for every family" line, "no gross
edge", the breadth of the ATR-gate conclusion, and the selective "only lead"
label); all are corrected in a superseding block in the ledger, numbers
unchanged. vwap gets alpha 0. No rerun: no defect can move a p-value near the
0.00208 gate, and a rerun would only add a version to the count. The same
audit points apply to `chart_information_map.py`: its bin means are fitted on
the other era only (so no future leak between eras), but the bootstrap treats
those bin means as fixed and adjacent-week dependence is not modelled — both
attenuate nothing in the direction tests, which found no lead.
