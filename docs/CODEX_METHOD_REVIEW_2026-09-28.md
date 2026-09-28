# Codex critical review of Claude's WPWB measurement methodology

**Date:** 2026-09-28  
**Scope:** today's WPWB work in `research/wpwb_search/`,
`research/wpwb_live/`, the two WPWB preregistrations, the operating protocol,
`CLAUDE.md` sections 1/4/5, and `LOGIC_LEDGER.md` Parts 29-40. This is a
methodology review, not a rerun of the earlier pilot-engine review in Part 40.
No MT5 function was called and no order was placed.

## Overall verdict

**The operational decision `NO TRADE` is defensible; the scientific conclusion
"only volatility is readable; weekly direction is not" is not. It must be
softened to: _among the specific, low-powered and often stability-gated
procedures tested, no weekly-direction procedure earned promotion; volatility
magnitude persistence was the strongest repeatable descriptive trace, but its
profit contribution was not validated_.**

The work is conservative at the final decision layer, but conservatism is not
the same as identification. The tests often answer whether a fixed association
survives two eras and beats every attribution control. WPWB's stated target is
different: a procedure that changes with the current regime, weights recent
data most, and may replace the active tool weekly (`CLAUDE.md:22-36,108-146`;
`docs/AMENDMENT_22_WEEKLY_OPERATING_PROTOCOL.md:25-34,54-68`). The methodology
therefore has high false-negative risk against the very class of edge WPWB was
designed to exploit.

## Prioritised issues

| priority | severity | issue and evidence | concrete fix |
|---:|---|---|---|
| 1 | **Critical** | **The estimand conflicts with the mission.** The mission says current-regime, decay-weighted, replace-on-decay, M5/M15 (`CLAUDE.md:22-36,108-146`), and the weekly protocol expects frequent tool changes (`docs/AMENDMENT_22_WEEKLY_OPERATING_PROTOCOL.md:25-34`). Yet W1-W5 and level-break require the same sign/significance in both fixed eras (`docs/WPWB_LIVE_PREREG.md:235-239,255-262`; `research/wpwb_live/h1_traces.py:153-171`; `research/wpwb_live/level_break.py:45-59`). This structurally rejects sign-changing and decaying edges. | Test a **frozen adaptive procedure** by nested rolling-origin replay. Let the procedure choose/re-size/stand aside from past data at every cut; score its prequential actions out of sample. Do not require the selected rule or coefficient sign to be invariant. Reserve a final prospective sequential shadow stream for promotion. |
| 2 | **Critical** | **Power is far below what the broad negative conclusion requires.** The code uses `max(CBB8,NW8)` (`research/wpwb_search/common.py:142-183`) and thresholds as small as `0.025/40` (`research/wpwb_live/run_live_all.py:25,28-34`). The repository itself disclosed weak power for a different planted-direction experiment (`docs/WPWB_EDGE_SEARCH_PREREG.md:278-284`), but did not quantify 5/10/20 bp effects. This review's exact simulation finds only 0.4-1.7% power for 5-10 bp/week and 3.2-7.4% for 20 bp/week at the 40-tool threshold under iid noise. | State minimum detectable effects before interpreting failures. Replace flat all-tool Bonferroni with predeclared hierarchical families and a family-level maxT/randomisation test that reruns the whole selector. Use Holm inside a passed family; BH may be used for labelled discovery only. Confirm promotion prospectively with an anytime-valid sequential test/alpha-spending rule. |
| 3 | **High** | **The extreme p-value tail is not calibrated.** `_cbb_p` reports `count / 5000` with no add-one correction (`research/wpwb_search/common.py:142-150`). At `0.025/40=0.000625`, the decision is determined by about three bootstrap exceedances. Null simulation gives per-test rejection 0.13-0.29%, not 0.0625%, so Bonferroni's advertised 2.5% family guarantee does not follow. The per-test `0.025` rule rejects 3.1-4.2%, not 2.5%. | Never use raw `b/B`; use `(b+1)/(B+1)`, enough draws for the target tail (preferably >=100,000 here), and validate the **whole family decision** under realistic serial dependence. Better: use joint block randomisation/maxT, which directly calibrates familywise error and uses correlation among tools. |
| 4 | **High** | **Attribution controls are incorrectly made conjunctive nulls.** `summarize` requires the worst p across every control (`research/wpwb_search/evaluate.py:65-80`), and the runners gate on that maximum (`research/wpwb_search/run_dev.py:92-97`; `research/wpwb_live/run_live_all.py:28-34`). A timing-selected long can equal `LONG` at the selected timestamps and therefore fail even when its timing is valuable; a weekly directional forecast can be absorbed by `RTIME`, which uses the realised same-week path. | Predeclare one primary implementable benchmark matched to the tool's economic claim. Use LONG/RDIR/RTIME as **mechanism decomposition**, not three hurdles. Test the composite procedure once; report which component contributes. |
| 5 | **High** | **Freezing after hindsight does not create an independent test.** FOMC skip and catastrophe stops were nominated after both eras were inspected (`docs/WPWB_LIVE_PREREG.md:123-147`) and tested on those same eras (`research/wpwb_live/rules_test.py:64-112`). The level-break rule was nominated from the 51%/16% hindsight contrast and then tested on the same history (`docs/WPWB_LIVE_PREREG.md:253-262`). | Treat these results as exploratory. Either repeat the entire nomination process inside nested resampling, with multiplicity over every candidate trace/threshold, or freeze now and use only future weeks. |
| 6 | **High** | **The purported unseen FOMC test selects events using their price outcome.** Hand-entered dates are retained only when statement-hour/day range exceeds a price-derived median (`research/wpwb_live/oos_2016.py:75-96`; `research/wpwb_live/oos_2016_d1.py:49-67`). That is outcome-conditioned inclusion, not date verification. The D1 replacement was also designed after the H1 coverage result (`docs/WPWB_LIVE_PREREG.md:186-195`). | Validate dates against an authoritative calendar independent of XAU returns and include every scheduled event. Missing price coverage should remain missing, never become an event-selection rule. Label the existing FOMC OOS tests contaminated, although their failures do not create a false positive. |
| 7 | **High** | **Multiplicity is local, not project-wide.** The search expands through three DEV-guided rounds (`docs/WPWB_EDGE_SEARCH_PREREG.md:179-192,233-260`), the same current-era history is then reopened for 6 and later all 40 tools (`docs/WPWB_LIVE_PREREG.md:68-104`), and post-hoc candidates generate more tests (`docs/WPWB_LIVE_PREREG.md:106-147`). Part 40 already acknowledged that amendment-by-amendment resetting biases toward false edges (`docs/LOGIC_LEDGER.md:1638-1642`). | Maintain a single hypothesis registry and alpha ledger. For historical discovery, validate the **entire search algorithm**, including later-round design and nomination, with nested replay. Spend fresh alpha only on genuinely future observations. |
| 8 | **Medium** | **The economic unit and deployment target drift.** Search P&L sums per-trade bp (`research/wpwb_search/common.py:93-108`; `research/wpwb_search/evaluate.py:37-58`), implicitly giving every trade equal fractional capital and allowing weeks with many trades to carry more gross exposure. The money report instead assumes a fixed 0.01 lot/no compounding (`research/wpwb_live/backtest_report.py:4-10`). The primary mission is M5/M15, while the headline conclusion is drawn heavily from Sunday-open-to-Friday-close bets (`CLAUDE.md:25`; `research/wpwb_live/backtest_report.py:4-9`). | Declare one deployable sizing/exposure convention. Report return on peak margin or average gross exposure, turnover, and overlapping-position limits. Do not generalise failure of week-long direction to M5/M15 conditional direction. |
| 9 | **Medium** | **Costs are conservative but not historically identified.** A fixed $0.09 spread floor and today's long swap feed all eras (`research/wpwb_search/common.py:31-33,55-59,93-108`; `research/pilot/mtf_engine.py:69-75`). Stress scales spread/fees/slippage but not swap (`research/wpwb_search/common.py:96,102-106`). The D1 code approximates swap nights from weekday bars (`research/wpwb_live/oos_2016_d1.py:69-78`). | Use timestamped historical spread/swap schedules where available; otherwise give zero/base/adverse sensitivity bands. Stress financing separately. For D1 weekly-open execution, model the opening spread explicitly or label it unavailable. |

## Q1. Controls

### Random direction (RDIR) — **Low severity as a component test; High if treated as the whole null**

The implementation is the exact fair-coin expectation,
`0.5 * (long P&L + short P&L)`, at the strategy's timestamps
(`research/wpwb_search/evaluate.py:49-56`). This correctly retains asymmetric
long swap and transaction costs, and is cleaner than adding Monte Carlo noise.
It answers a narrow question: whether chosen signs add mean P&L beyond a fair
coin at those exposures. It does not reproduce the variance/drawdown of an
implementable randomised strategy, and passing it can still be nothing more
than long drift; LONG is needed for that diagnosis.

**Fix:** retain RDIR as a directional-attribution statistic, preferably with a
paired sign-flip/block-randomisation distribution for the complete tool. Do not
make it one of several unrelated mandatory hurdles.

### Always-long (LONG) — **High severity for timing and risk-sizing tools**

LONG uses the strategy's exact selected timestamps (`research/wpwb_search/evaluate.py:51-55`). That
is appropriate when the claimed edge is sign selection and the question is
"better than long drift?" It is inappropriate as a universal pass gate. If a
tool's real information is _when to be long_, LONG inherits those chosen times,
so strategy-minus-LONG is zero by construction. Likewise, VOLMAN is a risk
policy; requiring higher mean than a long benchmark can reject a genuine
drawdown/utility improvement.

**Fix:** choose the primary benchmark by claim: unconditional scheduled long
for timing tools, same-time LONG for directional tools, and equal-risk/utility
benchmark for sizing tools. Keep the other contrasts descriptive.

### Random timing within the same week (RTIME) — **High severity as a pass gate; Medium construction weakness**

RTIME preserves the strategy's directions and durations but averages their P&L
over eligible placements (`research/wpwb_search/evaluate.py:13-33`). This is a
reasonable marginal test of intrawEEK timing. It is not an implementable
benchmark and uses the whole realised week's path; consequently it inherits a
correct weekly direction forecast and can absorb that real edge. Requiring a
procedure to beat both RTIME and LONG demands separate timing and direction
alpha, rather than a profitable interaction.

The eligible pools are also not consistently matched. HOD pools all H1 bars
(`research/wpwb_search/approaches.py:61-67`), HODM allows every entry and
truncates each hold at gaps/week-end (`research/wpwb_search/approaches2.py:18-33`),
while SESSION uses session runs only (`research/wpwb_search/approaches2.py:77-82`). These controls
can change liquidity/hour mix and realised duration, so some are too weak and
some too strong.

**Fix:** generate random schedules from the same tradable hour/session set,
same duration multiset, overlap constraint, and pre-week information. For a
composite weekly procedure, use block-shifted procedure outputs against future
weeks, which destroys timing/direction alignment together without conditioning
on the realised target week.

### Random week-skip — **High severity: too weak**

`research/wpwb_live/rules_test.py` skips the same count of uniformly random weeks within an era
(`research/wpwb_live/rules_test.py:88-100`). FOMC weeks are clustered in
calendar time and differ in volatility, event load, and Fed regime. Uniform
random weeks do not match those properties, so secular drift or event-risk
avoidance can masquerade as FOMC information. Moreover, the keep rule requires
raw net/DD improvement in both eras, not a calibrated joint significance test
(`docs/WPWB_LIVE_PREREG.md:143-147`).

**Fix:** match or stratify skips by year/Fed regime, forecast volatility and
other tier-1 event count; preserve event cadence with block/circular shifts;
and evaluate one preregistered utility statistic (for example mean minus a
drawdown penalty) rather than two uncalibrated endpoints.

### Exposure-matched long (LONGMATCH) — **Medium severity**

VOLMAN's comparator is full-evaluation mean size times LONG
(`research/wpwb_search/run_round3.py:60-75`). This is a valid ex-post
decomposition of size/return covariance and is much better than unmatched
LONG. But it is neither an online tradable benchmark nor risk matched; it
matches mean exposure only. Its size-permutation follow-up arbitrarily permutes
weeks (`research/wpwb_live/volman_checks.py:68-86`), breaking persistent
volatility regimes and overstating effective independent timing opportunities.

**Fix:** compare with (a) an expanding, past-only mean-size long, and (b) a
constant-risk benchmark matched on realised/forecast volatility and leverage
cap. Use block permutations of the complete size path. Judge a sizing policy on
predeclared utility/drawdown as well as mean return.

## Q2. Power and calibration

### Simulation design

`research/wpwb_live/codex_review/simulate_power.py` uses 10,000 replications per
cell and exactly reproduces the repository's CBB8 (5,000 fixed-seed draws), NW8,
and `max(p)` rule. Weekly P&L is Gaussian with marginal sd 150 or 200 bp,
n=130 or 142, true mean 5/10/20 bp, under iid and stationary AR(1) phi=0.3.
`simulate_null.py` performs the matching null calibration. A direct one-series
check matched `common.block_boot` to machine precision. Full results are in
`power_results.csv` and `null_results.csv` beside the scripts.

IID detection rates below are ranges across n=130 and n=142:

| weekly sd | true edge | p<.025 | p<.025/6 | p<.025/20 | p<.025/40 |
|---:|---:|---:|---:|---:|---:|
| 150 bp | 5 bp | 6.9-7.2% | 1.8-2.2% | 0.7-1.0% | 0.5-0.6% |
| 150 bp | 10 bp | 13.3-13.7% | 4.4-4.8% | 1.9-2.5% | 1.2-1.7% |
| 150 bp | 20 bp | 34.9-37.0% | 15.8-17.0% | 9.1-9.9% | 6.5-7.4% |
| 200 bp | 5 bp | 5.8-6.1% | 1.5-1.8% | 0.6-0.8% | 0.4-0.5% |
| 200 bp | 10 bp | 9.7-10.0% | 2.8-3.3% | 1.2-1.6% | 0.8-1.0% |
| 200 bp | 20 bp | 22.8-24.0% | 8.6-9.3% | 4.6-5.2% | 3.2-3.6% |

With AR(1) phi=0.3, power at `/40` is 0.4-0.6% (5 bp), 0.7-1.3%
(10 bp), and 2.4-4.4% (20 bp). The rule therefore has almost no chance to
detect economically modest effects after the live family correction. Failure
is expected even when the edge is real.

**Implementation discrepancy:** the closed search did not actually divide the
DEV threshold by 20 (or 40). `DEV_P_MAX` is `.025`
(`research/wpwb_search/common.py:186`) and every round gates each variant at
that value (`research/wpwb_search/run_dev.py:92-97`;
`research/wpwb_search/run_round2.py:112-114`;
`research/wpwb_search/run_round3.py:120-122`). Its intended multiplicity guard
was finalist selection followed by a corrected holdout, which was never opened.
The `/20` column above therefore answers the requested family-rule
counterfactual, not the implemented DEV gate. The current-era runs did use `/6`
and `/40` (`research/wpwb_live/run_live_hod.py:22-23,65-67`;
`research/wpwb_live/run_live_all.py:25,28-34`).

Null rejection at nominal per-test `.025` was 3.11-4.18%. At the `/40` cutoff,
the per-test null rejection was 0.13-0.29%, versus the 0.0625% needed for a
literal Bonferroni 2.5% family bound. Dependence among the 40 real tools may
reduce family error, but the marginal p-values are not super-uniform at the
used tail, so the claimed bound is unavailable.

### Better-calibrated alternative

1. **One procedure-level primary hypothesis.** Score the locked weekly
   adaptive procedure against one economic benchmark. Simulate the whole
   selection/rebuild pipeline under joint block shifts or sign randomisation.
2. **Hierarchical families.** Predeclare direction, timing, event-conditioned,
   and sizing/risk families. Test four family-level maxT statistics and apply
   Holm at family level. Only inside a passed family use closed testing/Holm to
   identify components. Correlation among variants is retained rather than
   discarded by `/40`.
3. **Discovery versus confirmation.** BH-FDR at q=10% may rank explicitly
   exploratory historical candidates, but cannot promote them. Promotion uses
   a frozen prospective shadow stream with an anytime-valid e-value or alpha-
   spending plan. Replacements consume alpha wealth; they do not reset it.
4. **Honest precision.** Report effect estimate, block-bootstrap/HAC interval,
   MDE, and probability of detecting 5/10/20 bp before interpreting a miss.

Holm alone cannot manufacture power when only one signal exists—the smallest
p still faces the family threshold. The main gain comes from testing the
adaptive procedure and correlated families at their proper level, while future
sequential evidence prevents repeated historical reuse from creating false
discoveries.

## Q3. Both-era or old-OOS requirement

**Severity: Critical. Yes, it structurally rejects the regime-specific,
decaying class WPWB claims to seek.** A true relationship that is positive in
one regime, absent/reversed in the next, and correctly switched off by a causal
regime detector should pass WPWB. The current gate fails it because the
_feature's unconditional sign_ must agree in both eras. Conversely, two weak
same-sign era estimates can pass without demonstrating that the weekly rebuild
actually detects regime changes.

The 2016-2020 alternative is not a fair substitute for a current-regime
procedure. Market level, costs, policy cycle, and available predictors differ;
the current swap is back-cast; and the FOMC event set is selected using XAU
range. It is useful stress context, not a mandatory invariance domain.

### Concrete evaluation design for a regime-adaptive weekly procedure

1. **Freeze the algorithm, not the weekly rule.** Specify inputs available at
   Friday 22:15, candidate tools, decay choices, regime state, turnover/risk
   constraints, and deterministic selection/tie rules. Weekly outputs may
   change.
2. **Nested rolling-origin replay.** After a fixed warm-up, at every historical
   cut choose all hyperparameters using only earlier weeks. If half-life or
   family selection is tuned, tune it in inner past-only folds. Generate one
   untouched action and P&L for the next week, then advance. The unit of
   evidence is the outer prequential P&L series of the entire procedure.
3. **Selection-aware null.** Run that whole replay under block-shifted future
   returns/randomised directions, including every retune and stand-aside
   choice. This tests whether adaptation adds value beyond churn and drift.
4. **Primary endpoint.** Predeclare net bp per unit average gross exposure, or
   a utility such as net return minus a fixed drawdown/variance penalty, versus
   one implementable benchmark. Report turnover and worst drawdown separately.
5. **Regime diagnostics, not invariance gates.** Report conditional effects and
   selection frequency by causal regime. Require no catastrophic concentration
   (for example, leave-one-block-out stability), but do not require profit or
   coefficient sign in each calendar era.
6. **Genuine confirmation.** Because 2021-2026 has now been repeatedly mined,
   freeze the full procedure and accumulate future weekly shadow results with
   an anytime-valid sequential test. Use a 26-week safety review, but do not
   call 26 weeks statistically confirmatory unless the evidence threshold is
   actually reached.

This design permits decay and switching while guarding against a selector that
merely chases noise.

## Q4. Units and costs

**Weekly sums in bp — Medium severity, bias depends on deployment.** Per-trade
price P&L is divided by that trade's entry price and summed
(`research/wpwb_search/common.py:93-108`; `research/wpwb_search/evaluate.py:37-58`). This is coherent
for equal fractional capital recycled trade by trade, but it is not the fixed
one-ounce/0.01-lot economics used in the live money report
(`research/wpwb_live/backtest_report.py:4-10`). It also does not cap total weekly/concurrent gross
exposure. It can favour or penalise high-turnover tools relative to the actual
account. Use return on deployable capital/margin and an exposure cap.

**Sunday-open to Friday-close — High scope limitation, not inherently biased.**
It is a clean weekly carry target, but it is not the M5/M15 conditional-signal
mission. It loads gold drift, weekend/opening spread, five-day event risk and
long financing into one outcome. It can bias toward "no directional edge" if
the actual edge exists only intrawEEK or conditionally after news; it can bias
toward a false edge during a secular gold trend. The LONG control diagnoses
some drift but does not make the target representative of all WPWB signals.

**H1 resolution — Medium, mostly toward missed edge.** H1 is adequate for
hour/day scheduling and the catastrophe stop is resolved on M5
(`research/wpwb_live/rules_test.py:24-42`). But a first H1 close then next-bar
entry can miss fast M5/M15 acceptance/rejection and makes the level-break test
a test of slow continuation to Friday, not of all usable responses. H1/D1
opening spreads are also less reliable than timestamped M5 execution spreads.

**1.5x cost stress — Medium, deliberately toward no edge.** It multiplies
spread, commission and slippage, not swap (`research/wpwb_search/common.py:96,102-106`). This is a
useful adverse scenario, but demanding profitability at it as a hard gate
raises false negatives and does not cover financing stress. Report base and
several empirical adverse quantiles; reserve a hard gate for a justified live
cost bound.

**Today's long swap on 2016-2020 — Medium, mainly toward no edge.** The document
claims it cancels because it is constant (`docs/WPWB_LIVE_PREREG.md:199-205`).
That is approximately true for equal-length FOMC versus non-FOMC weeks and
exact for VOLMAN only if every week's cost is identical, since
`sum(s-mean(s))=0`. It is not exact with holiday/missing-day night counts
(`research/wpwb_live/oos_2016_d1.py:69-78`) or size/cost correlation. Historical financing can
also differ materially. It biases raw long profitability downward if today's
charge is unusually high, while relative-test bias is smaller and ambiguous.

**$0.09 spread floor — Medium, usually toward no edge on M5; possibly false edge
on D1 opens.** The engine uses actual recorded spread or the floor
(`research/wpwb_search/common.py:55-59`; `research/pilot/mtf_engine.py:69-75`). When the true spread is below nine
cents it is conservative. When old/D1 bar spread fails to represent the Sunday
reopen, a nine-cent floor can understate actual opening cost and favour a false
weekly edge. Use historical bid/ask or sensitivity bands around the opening
spread.

## Q5. Hindsight-nominated rules

**Severity: High. They are not adequately guarded.** Disclosure and freezing
are good audit hygiene, but freezing after looking does not turn reused data
into a holdout.

- **FOMC skip:** selected after both eras showed poor FOMC-long returns
  (`docs/WPWB_LIVE_PREREG.md:123-147`) and then tested on both. `luck_check.py`
  correctly shows a selection penalty and best-of-15 baseline
  (`research/wpwb_live/luck_check.py:66-118`), which makes it exploratory, not
  confirmed. The later old-data test is contaminated by price-based event
  inclusion (`research/wpwb_live/oos_2016.py:75-96`; `research/wpwb_live/oos_2016_d1.py:49-67`).
- **Catastrophe stops:** thresholds were nominated after seeing the catastrophic
  week and recovery paths (`WPWB_LIVE_PREREG.md:125-141`), then assessed on the
  same paths (`research/wpwb_live/rules_test.py:24-56,72-112`). Their failure is useful diagnosis,
  but not an unbiased estimate of stop value.
- **Prior-week level break:** the rule was nominated from the 51% versus 16%
  hindsight contrast and tested on the same eras (`WPWB_LIVE_PREREG.md:243-262`;
  `research/wpwb_live/level_break.py:24-59`). Changing the endpoint from "appears in losing weeks"
  to "continues to Friday" reduces but does not remove selection: feature,
  direction, timing and horizon were chosen after inspecting outcomes.

**Fix:** either replay the whole feature/threshold/horizon nomination inside
nested resampling and use a max statistic across everything considered, or
freeze these hypotheses now and wait for future data. Authoritative event dates
must be independent of price. Existing failures may remain recorded, but none
is a clean estimate of generalisation.

## Q6. Does “only volatility is readable; weekly direction is not” stand?

**Severity of current wording: High. It needs softening, not reversal.**

What stands:

- No tested weekly-direction procedure cleared its registered promotion gate.
- Many profitable results were explained by long-gold drift, and the use of
  LONG was valuable for exposing that (`docs/WPWB_LIVE_PREREG.md:94-104`).
- Volatility magnitude/persistence is the most consistent descriptive signal
  found, and using it for risk sizing is plausible.
- `NO TRADE` remains the correct action because no candidate has clean,
  adequately powered confirmation.

What does not stand:

- A 0/40 result with 0.4-7.4% power for 5-20 bp/week at the family threshold
  cannot establish absence of directional information.
- Same-sign-in-both-eras gates test invariance, not a regime-adaptive WPWB
  procedure.
- Failure of Sunday-to-Friday direction does not establish failure of M5/M15
  conditional direction.
- VOLMAN's return advantage failed old-data checks and is concentrated, so
  “volatility is readable” should refer to **magnitude/risk**, not a validated
  profitable edge (`docs/WPWB_LIVE_PREREG.md:106-121,197-213`).

**Approved replacement conclusion:**

> In the features, horizons and procedures tested through 2026-09-28, no
> weekly-direction procedure has enough clean evidence for promotion. Volatility
> magnitude is the strongest repeatable trace and may support risk sizing, but
> neither a directional edge nor a VOLMAN return edge has been validated. The
> absence of a detected direction rule is not evidence that weekly direction is
> intrinsically unreadable.
