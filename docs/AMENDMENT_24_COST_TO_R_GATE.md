# Amendment 24 — execution-friction-to-R gate

**Written 2026-09-27 before any Amendment 24 run.** This is a
pre-registration only. It responds to Amendment 23's finding that the weekly
selector retained a positive gross edge in both reported regimes, but fixed
dollar execution costs consumed 90.0% of that edge during the lower-stop-size
44-month regime. Nothing in this document authorizes a backtest before review,
a Demo or real order, an autotrader change, or a PR.

This amendment retains Amendment 23 except for the explicit changes below. It
does not add a new setup family, indicator, direction flip, news rule, macro
rule, DD target, or discretionary market-regime label.

## 1. Contamination statement and question

The 2022-01-01 through 2025-09-21 window has now been inspected. This design
was created in response to its Amendment 23 decomposition and is therefore
**informed by Amendment 23**, not blind validation. Its 44-month result will be
reported with that label every time and cannot be described as independent
confirmation, out-of-sample proof, or discovery on unseen data.

The trailing period through the canonical end on 2026-09-21 has also been
seen. Genuine confirmation can come only from observations that were not
available when this amendment was frozen: forward weeks after 2026-09-27, or a
separately sealed dataset whose outcomes can be demonstrated not to have been
inspected before this design. Replaying the existing canonical history is a
development test. A successful development test may justify forward
observation, but it cannot by itself authorize a Demo strategy replacement.

The development question is:

> Does rejecting trades whose stop is too small relative to executable
> friction, and ranking the surviving tools on cost-stressed returns, preserve
> enough of the gross edge to produce positive causal net walk-forward results
> at both base and 1.5x costs?

The DD target still determines size, not expectancy. Unit risk must pass before
the 35–40% sizing stage has any interpretation.

## 2. Candidate universe retained

The candidate universe remains Amendment 14's declared 8,250 cells:

- families: `breakout`, `pullback`, `sweep`, `failed`, `vwap`, and
  `expansion`;
- signal timeframes: M5, M15, M30, H1, and H4;
- stops: 0.75, 1.0, 1.5, 2.0, and 3.0 ATR;
- targets: 0.5, 1.0, 1.5, 2.0, and 3.0 R; and
- market entry or 0.50/1.00 ATR limit entry with expiry after
  5/8/10/12/15 signal bars.

The design does **not** impose an arbitrary higher-timeframe quota. Wider-stop
and higher-timeframe members should be preferred only when their actual
friction-to-R ratio is better. A low-timeframe member remains eligible when its
ATR and stop are wide enough to pass the same economic rule.

## 3. Frozen execution-friction gate

For every otherwise valid proposed fill, calculate:

```text
stop_price_distance = stop_ATR_multiple * ATR_known_at_signal_close

execution_friction_price =
    max(recorded_spread_on_last_closed_M5_bar, 0.090)
    + 0.140 round-turn commission
    + 2 * 0.0165 slippage

base_friction_R = execution_friction_price / stop_price_distance
stress_friction_R = 1.5 * base_friction_R
```

The opportunity may enter only if:

```text
base_friction_R <= 1 / 12       # 0.0833333333 R
stress_friction_R <= 1 / 8      # 0.125 R; algebraically the same gate
```

This threshold is frozen as an economic ratio: at 1.5x execution cost, the
planned geometric stop must be at least eight times execution friction. It may
not be optimized against the already-seen 44-month result. The threshold is
applied identically to every family, timeframe, direction, stop, target, and
entry mode.

For a historical proposed fill on M5 bar index `k`, the gate spread is exactly
`max(b5.sp[k-1], 0.090)`: the spread recorded on the last fully closed M5 bar
before the fill. If `k-1` has no finite positive recorded spread, use the
predeclared 0.090 floor. The fill bar's own `b5.sp[k]` is not available to the
historical go/no-go decision because the MT5 per-bar field summarises the whole
fill bar. It remains the accounting approximation for the cost actually paid,
including when it differs from the prior-bar gate value. In live operation the
current executable quote is known before sending the entry, so the live gate
uses that contemporaneously known quote; the `k-1` rule is the causal
historical proxy.

Market and limit entries are treated as local/virtual orders until the
otherwise valid entry event. If the first otherwise valid entry event fails
the gate, that opportunity is cancelled permanently; the backtest may not wait
for a later, cheaper spread after learning that the first event was expensive.
A failed gate is a zero contribution, not a missing observation.

The gate measures execution friction only. Long swap cannot be known from the
eventual holding period at entry and is not estimated using the future exit.
Actual causal rollover charges remain deducted exactly as in Amendment 23 and
are reported separately. Spread remains embedded once in the Bid/Ask geometry;
the ratio calculation does not deduct it a second time. Base net R and 1.5x
stress net R retain Amendment 23's accounting.

## 4. Weekly candidate series and cost-stressed ranking

A trade's result belongs to its exit/resolution calendar week. Every calendar
week remains present; no accepted trade means zero. At cutoff `C`, only exits
strictly resolved before `C` may participate.

The three-week half-life, 26-week minimum history, eight non-zero-week minimum,
and effective-sample-size formula remain unchanged:

```text
decay_weight(a) = 2 ** (-a / 3)
n_eff = sum(w) ** 2 / sum(w ** 2)
```

Amendment 24 changes which return drives selection. For each candidate, build
the zero-inclusive weekly series **after applying the friction gate and 1.5x
cost stress**, then calculate:

```text
mu_stress  = exponentially weighted mean(stressed weekly net R)
sd_stress  = exponentially weighted standard deviation(stressed weekly net R)
LCB_stress = mu_stress - 0.75 * sd_stress / sqrt(n_eff)
```

A candidate is eligible only if:

1. it has at least 26 completed history weeks;
2. at least eight weeks contain a non-zero gated return;
3. `LCB_stress > 0`; and
4. its corresponding exponentially weighted base-cost mean is also positive.

Members are sorted by descending `LCB_stress`, with tag as deterministic
tie-break. Correlations, downside deviations, the covariance matrix, raw member
weights, and the volatility floor are all calculated from the same gated,
1.5x-stressed, zero-inclusive weekly series. Thus cost robustness affects the
rank rather than appearing only as a final pass/fail check.

The Amendment 23 member-weight formula is retained with `LCB_stress` in place
of the prior base-cost LCB:

```text
raw_weight_i = max(LCB_stress_i, 0)
               / max(stressed_downside_deviation_i, volatility_floor)
```

All other portfolio constraints remain: three to five members, one member per
family, exact duplicate signatures collapsed before ranking, pairwise
correlation no greater than 0.70, individual weights 10–35%, and a combined
50% cap for pairs whose correlation is at least 0.50. An infeasible basket is
`NO TRADE`; idle weeks are zero.

## 5. Per-cell state fidelity fix

Amendment 23's cached cell trades were thinned as if every cell traded
continuously. A hypothetical position opened while a cell was not selected
could therefore block an opportunity in a later week when it was selected.
This was not look-ahead, but it was not faithful to the basket's actual state.
Amendment 24 fixes it rather than carrying it forward.

The new engine must preserve raw causal order/fill opportunities before the
per-cell one-position busy filter, or regenerate those opportunities from the
unchanged `mtf_engine` primitives. It keeps two state machines separate:

1. **Candidate-history state.** For scoring, each cell is replayed as an
   always-on, one-position-at-a-time strategy through the cutoff. This creates
   its causal historical evidence and applies the friction gate at each
   proposed fill.
2. **Actual basket-policy state.** In the forward week, only positions and
   pending orders actually created while that cell was selected can block it.
   A hypothetical position from an unselected week has no state and cannot
   suppress a signal. Actual carried positions retain their original member,
   rule, weight, and size and continue to consume a slot and gross risk.

Pending orders are cancelled at each Weekend Rebuild. A newly selected member
cannot inherit a pending order from candidate history or an unselected week.
Each cell may still hold at most one actual basket position.

Before the Amendment 24 result is produced, a reproduction audit must disable
the new friction gate, select a cell continuously, and show that the new raw
opportunity state machine reproduces the old cache's order, fill, direction,
and exit sequence. A second test must demonstrate a constructed week in which
an unselected hypothetical position no longer blocks a selected-week signal,
while a genuinely carried selected position still blocks it. Any unexplained
mismatch is a failure.

Because the representation and busy-state semantics change, Amendment 24 must
use a new versioned cache with a full content/data/code/cost hash. It may read
the old cache only for the reproduction audit, not as the forward execution
source. Neither `mtf_engine.py` nor `walk_forward.py` may be silently edited to
make an old cache appear valid.

## 6. Weekend basket operation and overlap retained

Selection and weighting occur only after the Saturday market-close cutoff and
are frozen for the next seven calendar days. No forward week's outcome may
affect its own membership, weights, cost estimate, or multiplier.

Opposing members remain independent gross-risk sleeves. They are not netted,
averaged, martingaled, or used to add to a losing position. There are at most
five concurrent actual basket positions. Carried positions occupy slots.
Simultaneous admissible entries are processed by the frozen current
`LCB_stress` order; entries exceeding the slot or gross-risk budget are skipped
and reported. Stop risk plus exit fees is charged to the risk budget.

## 7. Unit-risk proof, controls, and seen-window status

The selector is replayed weekend by weekend, seeing only resolved information
at each cutoff. Unit-risk results are judged before DD sizing. Report:

1. the 2022-01-01 through 2025-09-21 development result, labelled
   **INFORMED BY AMENDMENT 23 — NOT BLIND**;
2. the 2025-09-21 through 2026-09-21 development result, also already seen;
3. the complete weekly walk-forward through the canonical end;
4. Amendment 23 replayed on the same engine/state representation as a paired
   baseline, so the effect of the friction rule is not confused with the
   fidelity fix; and
5. the same-week equal-weight eligible family-middle control, using the same
   friction gate and cost-stressed eligibility.

The paired baseline must be produced in two steps:

- Amendment 23 logic on the new state-correct engine with no friction gate;
- Amendment 24 logic on that identical engine with the frozen gate and
  stressed ranking.

Report paired weekly differences in net R, gross R, cost R, trade count, zero
weeks, and MTM DD. Historical improvement is diagnostic because the design was
informed by that history.

For each required window and each policy, report at base and 1.5x cost:

- gross R before spread/commission/slippage/swap, execution-friction R, swap R,
  and final net R;
- gross edge, execution cost, net edge, and cost share of gross edge per trade;
- median and quartiles of stop-price distance and base/stress friction R;
- PF, positive-week percentage, realised and M5 MTM DD, worst week/month, loss
  streak, explicit zero weeks, and trades;
- friction-gate cancellations by week, family, timeframe, stop multiple, and
  entry mode;
- members, weights, risk contributions, binding caps, correlations, `n_eff`,
  member turnover, weight turnover, overlap, slot rejects, and risk rejects.

The decomposition must come from a per-trade cost ledger, not from a fitted
window-level residual. For every admitted trade, record spread drag,
commission, slippage, and swap separately; define pre-cost gross R as final net
R plus those recorded components. The gate's fill-time spread estimate and the
eventual realised spread drag are reported separately when they differ. Cost
share of gross is `NOT ASSESSED` when aggregate gross edge is non-positive,
never forced to a convenient percentage.

At least half of the forward weeks in each required window must contain one or
more resolved basket trades. This new evidence floor prevents the cost gate
from manufacturing a pass by leaving almost every week idle. Zero weeks remain
in every average regardless.

## 8. Cost profile retained

The primary profile remains Demo90:

- spread `max(recorded, 0.090)` price units;
- commission 0.140 price units round turn;
- slippage 0.0165 price units per fill;
- long swap 0.5493 per counted 21:00 UTC rollover and short swap 0.0; and
- Bid/Ask execution, stop before target on an ambiguous bar, and no same-bar TP
  after an intrabar limit fill.

Base and 1.5x execution costs are reported separately. The 260-point Cent
profile remains a separate execution profile and is not substituted into the
primary run.

## 9. DD sizing retained and conditional

Only if the Amendment 24 unit-risk basket passes section 11 may the Amendment
23 sizing protocol run unchanged:

- trailing 52 completed weeks only, no deposits in calibration;
- 37.5% target MTM DD, 35% soft gate, and 40% hard liquidation ceiling;
- past-only bisection, historical frozen member weights, equity-proportional
  compounding, volume steps, overlap, full costs, and 1.5x/all-history guards;
- weekly multiplier increases capped at 15%, decreases unlimited;
- volume rounded down, never up, minimum/cap/margin checks retained; and
- USD 100 initial equity plus USD 100 monthly deposits reported only as a
  separate finance view.

If unit risk fails, the 30/35/37.5/40/45/50% diagnostics, finance projection,
and leverage interpretation are `NOT RUN`, not zero.

## 10. Required causality and sensitivity audits

Before the result, tests must show:

1. truncating data at a weekend leaves that weekend's candidate histories,
   eligibility, membership, weights, and any permitted sizing multiplier
   unchanged;
2. mutating bars after a cutoff changes none of those pre-cutoff values;
3. the first-valid-fill friction decision uses no later spread, ATR, fill, or
   exit information. Include a constructed boundary case in which
   `b5.sp[k-1]` passes the gate while `b5.sp[k]` would fail it (and the reverse
   mutation): changing `sp[k]` alone must never change the gate decision but
   must change fill-cost accounting, while changing `sp[k-1]` across the
   threshold must flip the decision;
4. a deliberately mutated gate or timestamp is caught by the tests;
5. the new state-correct replay passes the reproduction and selected/unselected
   blocking tests in section 5;
6. cache validation uses full content and code hashes, not filename or
   timestamp alone; and
7. all existing no-look-ahead, resampling, Bid/Ask, ambiguous-bar, cost,
   rollover, and fast-resolver tests remain green.

Print the friction threshold, `n_eff`, gate rejection counts, and weekly member
turnover in the raw run output.

## 11. Failure definitions

Amendment 24 fails for promotion if any of the following occurs:

- any audit in section 10 fails;
- either required development window has non-positive unit-risk net R at base
  cost;
- either required development window has non-positive unit-risk net R at 1.5x
  cost;
- fewer than three eligible, correlation-compliant members form the basket in
  more than half of forward weeks;
- fewer than half of forward weeks in either required window contain a
  resolved basket trade;
- zero weeks or friction-gate rejections are omitted or treated as missing;
- a fill passes only by using later spread, ATR, price, or exit information;
- a hypothetical unselected-week position blocks an actual selected-week
  signal, or an actual carried position fails to block one;
- the improvement exists only after DD scaling while unit risk is non-positive;
- the conditional operating replay, if reached, produces full-period MTM DD
  below 35% or above 40%; or
- any threshold, family, correlation cap, weight bound, half-life, gate,
  calibration rule, or failure definition must be changed after seeing the
  result to make it pass.

A positive result on the seen history is only a development success. Promotion
still requires genuine post-freeze confirmation described in section 1 and the
standing independent review/approval path.

## 12. Frozen status and authorization

The friction threshold, stressed ranking, evidence floor, fidelity fix, and all
retained Amendment 23 rules are frozen when this document is reviewed and
approved. No search over alternative cost thresholds or higher-timeframe
quotas is authorized inside this amendment. A revision requires a new
pre-result amendment.

This document authorizes **no run yet**. Claude reviews it under
`docs/OWNERSHIP.md` before any code or backtest. It does not authorize starting
or restarting `payoff_demo_autotrader.py`, changing the Demo policy, sending a
test order, sending a real order, opening a PR, or committing on Codex's behalf.

Current engine decision: **NO TRADE**.
