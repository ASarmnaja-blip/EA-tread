# Amendment 25 — explicit shadow-state re-signal filter with friction gate

**Written 2026-09-27 before any Amendment 25 code or result.** This is a
pre-registration only. It corrects the interpretation of the continuous
per-cell chain used before Amendment 24: that chain was a causal re-signal
filter, not an execution-fidelity defect. Amendment 24's registered result
remains a failure and is not rescored.

This amendment retains Amendments 23 and 24 except for the explicit shadow
state and paired comparisons below. It authorizes no backtest before review,
no Demo or real order, no autotrader change, no PR, and no commit by Codex.

## 1. Development question and order of proof

The primary policy is Amendment 24's execution-friction gate and stressed
weekly ranking, with one explicit always-on shadow chain for every candidate
cell. The development question is:

> Does the causal shadow filter remove late or overlapping per-cell
> re-signals while the friction gate removes trades whose stop is too small
> relative to cost, leaving a positive net weekly walk-forward basket at both
> base and 1.5x cost?

Unit risk is judged first. The 35–40% DD target determines how large a basket
with positive expectancy may trade; it cannot make a losing basket profitable.
DD sizing is not run unless the primary unit-risk policy passes section 12.

## 2. Contamination and status of the evidence

All canonical historical windows have now been inspected. The shadow rule is
specifically informed by the Amendment 24 review and Claude's all-cell
re-signal decomposition. Consequently, every historical replay in this
amendment is **DEVELOPMENT DATA — NOT BLIND**. This includes 2021, the
2022-01-01 through 2025-09-21 window, the trailing year through 2026-09-21,
and the complete canonical history.

The re-signal decomposition contains about 47 million overlapping raw signals;
those observations are not independent and no significance level is claimed.
It motivates this frozen causal rule but does not confirm it. Genuine
confirmation can come only from complete weeks whose market data did not exist
when this reviewed design was frozen. Section 14 defines the read-only forward
observation protocol.

## 3. Candidate universe retained

The candidate universe remains the declared 8,250 cells:

- six families: `breakout`, `pullback`, `sweep`, `failed`, `vwap`, and
  `expansion`;
- five timeframes: M5, M15, M30, H1, and H4;
- stops of 0.75, 1.0, 1.5, 2.0, and 3.0 ATR;
- targets of 0.5, 1.0, 1.5, 2.0, and 3.0 R; and
- market entry, or 0.50/1.00 ATR limit entry expiring after
  5/8/10/12/15 signal bars.

No setup, indicator, direction flip, timeframe quota, macro input, threshold
search, or new gene is introduced. Signal construction, pending-order fills,
Bid/Ask handling, ambiguous-bar loss priority, time stops, and rollover remain
the canonical tested rules.

## 4. Frozen shadow-state rule

Each of the 8,250 cells has exactly one always-on hypothetical shadow chain.
It is tracked continuously whether the cell is selected, unselected, rejected
by the basket risk/slot limits, or rejected by the friction gate. It carries no
capital and creates no broker order.

The chain must reproduce the old continuous cache semantics exactly:

1. Enumerate that cell's otherwise valid raw fill opportunities in the
   canonical deterministic signal order.
2. For an opportunity whose hypothetical fill is M5 bar `k`, reject it as
   `SHADOW_BUSY` when `k <= shadow_busy_until`.
3. When the shadow is flat, accept the opportunity into the shadow chain,
   resolve its frozen stop/target/time-stop plane, and set
   `shadow_busy_until = k + held_M5_bars`.
4. Keep the shadow occupied through the exit bar. A later fill is eligible
   only after that bar.

The shadow blocks **all fills while it is open, regardless of direction**.
Thus both same-direction and opposing re-signals are blocked. This choice
preserves the already-reproduced one-position-per-cell chain exactly. Although
the inspected aggregate `RE_OPPOSE` class was not worse than `FREE`, allowing
it now would create a new exception selected after seeing historical outcomes
and would no longer reproduce the reference chain. A direction-specific rule
requires a later pre-registration and new post-freeze confirmation.

The shadow is formed before the Amendment 24 friction gate. A fill accepted
into the shadow chain opens and advances the shadow even if the actual
opportunity later fails the cost/R gate, its cell is unselected, or portfolio
admission later fails. This ordering both reproduces the old chain and prevents
the actual basket outcome from feeding back into future shadow eligibility.
The gate may cancel an actual trade; it may not retroactively erase a known
hypothetical move from the cell's causal shadow history.

Expired, never-filled pending opportunities open no shadow position. As in the
canonical chain, a pending opportunity whose signal arose while the shadow was
busy may be accepted only if its eventual otherwise valid fill occurs after
the shadow has closed. The decision is made at the fill bar, not by using its
future exit.

## 5. Shadow state versus actual basket state

Shadow state and actual portfolio state are separate ledgers:

- **Shadow ledger:** one cost-free decision-state position per cell, always
  tracked. It determines only whether a raw fill survives the re-signal filter.
  It contributes no P/L, DD, margin, overlap slot, or risk charge.
- **Actual ledger:** contains only orders and positions the frozen weekly basket
  could really create. It alone contributes P/L, costs, MTM DD, slots, risk,
  margin, and carried exposure.

An actual entry is possible only if the raw fill is shadow-accepted, the cell
was selected when its actual order was created, the Amendment 24 friction gate
passes, and all actual slot/risk/margin rules pass. A shadow-accepted event
opens its shadow first; rejection from the actual ledger does not close or
rewind that shadow.

An actual admitted trade uses the same fill and exit plane as its corresponding
shadow event, but the ledgers are still not substituted for one another. An
actual carried position occupies an actual slot and risk budget until exit.
The shadow never liquidates, resizes, nets, or extends that actual position.
Conversely, actual protective action or portfolio rejection cannot change the
precomputed causal shadow sequence.

Shadow chains continue across Weekend Rebuild boundaries. Actual pending orders
do not: they are cancelled at the boundary as in Amendment 23. A newly selected
cell cannot inherit an actual pending order created before selection. A
pre-boundary hypothetical order may continue in the shadow ledger and may
eventually occupy shadow state, but its fill cannot become an actual trade
unless an actual order existed under the frozen membership rule. This must be
distinguished and counted in the audit ledger.

## 6. Primary policy and three paired variants

All variants run through one new engine, identical raw opportunities, weekend
boundaries, costs, overlap accounting, and report code. No result may be copied
from an earlier engine.

### V1 — A23 ranking plus explicit shadow filter, no friction gate

This is the paired baseline. It applies the section 4 shadow chain and otherwise
uses Amendment 23 exactly: its original weekly ranking/eligibility series,
three-week decay, membership and weight rules, and no cost/R gate.

### V2 — A24 gate and stressed ranking plus explicit shadow filter

This is the **Amendment 25 primary policy**. It applies the section 4 shadow
chain first, then Amendment 24's frozen prior-bar friction gate and gated
1.5x-cost weekly ranking. Only shadow-accepted, gate-passing results enter a
candidate's weekly evidence and can enter the actual basket.

### V3 — Amendment 24 as run

This control reproduces Amendment 24's registered state semantics on the same
new engine: gated candidate histories, but no always-on shadow suppression in
the forward actual ledger; only actual selected positions make their cells
busy. In its candidate-history chain, a gate failure does not advance the busy
state, exactly as in the registered Amendment 24 implementation. It must
reproduce Amendment 24's admitted-order list and headline
figures within exact integer fields and documented floating tolerance before
the V2 result is interpreted.

Report V2 minus V1 to isolate the friction gate and stressed ranking after the
shadow rule is held fixed. Report V2 minus V3 to show the combined effect of
restoring the explicit shadow rule under otherwise Amendment 24 logic. These
are paired development decompositions, not independent validation.

## 7. Candidate evidence, selection, and weighting retained

A trade's net R belongs to the calendar week of its exit/resolution. At cutoff
`C`, only exits resolved strictly before `C` are available. Every completed
calendar week is present; no resolved trade means zero, never missing.

The Amendment 25 primary V2 uses Amendment 24's gated 1.5x-stressed,
zero-inclusive weekly series and retains:

```text
decay_weight(a) = 2 ** (-a / 3)
n_eff = sum(w) ** 2 / sum(w ** 2)
LCB_stress = mu_stress - 0.75 * sd_stress / sqrt(n_eff)
```

Eligibility still requires 26 completed history weeks, eight non-zero weeks,
`LCB_stress > 0`, and a positive corresponding base-cost weighted mean.
Selection remains descending LCB with tag tie-break, three to five members,
one member per family, duplicate-signature collapse, correlation no greater
than 0.70, 10–35% member weights, and the 50% combined-weight cap for pairs
with correlation at least 0.50. The same stressed series supplies correlation,
downside deviation, covariance, volatility floor, and weights.

The half-life has asymptotic `n_eff` of about 8.7 weeks and must be printed at
each rebuild together with membership and weight turnover. If fewer than three
members form a feasible basket, the forward week is `NO TRADE` and contributes
zero.

V1 retains Amendment 23's corresponding ranking rather than silently borrowing
V2's stressed gated rank. V3 retains Amendment 24's registered rank and state.

## 8. Frozen friction gate and costs retained

For V2, an otherwise actual-eligible shadow-accepted fill on M5 bar `k` passes
only when the rule below holds. V3 applies the identical rule to its otherwise
valid fill, without V2's shadow prerequisite:

```text
gate_spread = max(b5.sp[k-1], 0.090)
gate_friction_price = gate_spread + 0.140 + 2 * 0.0165
base_friction_R = gate_friction_price / stop_price_distance

base_friction_R <= 1/12
1.5 * base_friction_R <= 1/8
```

The two inequalities are algebraically equivalent and remain frozen. The last
fully closed bar `sp[k-1]` controls the historical gate; fill-bar `sp[k]`
remains the accounting approximation for actual spread drag and cannot control
admission. If no finite positive `sp[k-1]` exists, the frozen 0.090 floor is
used. Failure at the first otherwise valid fill cancels the actual
opportunity permanently. Long swap is excluded from the entry gate because its
future holding period is unknown, then deducted from realised returns.

The primary execution profile remains Demo90: recorded spread floored at 0.090
price units, 0.140 round-turn commission, 0.0165 slippage per fill, long swap
0.5493 per counted 21:00 UTC rollover, and short swap 0.0. Report base and 1.5x
cost separately. The Cent 260-point profile is not substituted.

## 9. Weekend operation, overlap, and zero policy retained

Membership and weights change only after the Saturday market-close cutoff and
are frozen for the following seven calendar days. A forward week's data cannot
change its own decision. Actual carried positions keep their entry-time rule
and weight and consume slots/risk until exit.

At most five actual positions may coexist. Frozen member score determines the
order of simultaneous admission. Opposing sleeves remain independent and are
not netted, averaged, martingaled, or used to add to a loser. Slot, aggregate
stop-risk, broker volume, and margin failures skip the entry and are reported.
They do not alter the shadow ledger.

Idle capital is zero return. Every zero week remains in selection, performance,
activity, and forward-confirmation statistics.

## 10. Cache and pre-result audits

Amendment 25 must use a new versioned derived cache whose validation includes
full canonical-data, raw-content, engine-code, Amendment 25 code, cost-profile,
shadow-ordering, and gate hashes. A filename or timestamp match is insufficient.
The Amendment 24 raw-opportunity cache may be read only after independently
verifying its expected full hashes and contents; it is not accepted by name.
`mtf_engine.py` and `walk_forward.py` must not be edited.

Every audit must run and print before any performance result. Any failure stops
the run. Tests must include:

1. with the gate disabled, all 8,250 shadow chains reproduce the old continuous
   cache's order, fill, direction, exit, and busy rejection sequence;
2. constructed same-direction and opposing fills are both rejected while a
   shadow is open, and both become eligible only after its exit bar;
3. a shadow-accepted event rejected by the gate still advances shadow state
   and blocks the next fill; likewise for events rejected by membership, slot,
   risk, volume, or margin;
4. shadow P/L, risk, slot use, or hypothetical pending state can never enter
   the actual portfolio ledger;
5. an actual position is impossible without a corresponding shadow-accepted
   fill, while actual rejection never rewinds shadow history;
6. a newly selected cell cannot inherit an actual pre-cutoff pending order,
   while continuous hypothetical shadow state remains causal across cutoffs;
7. V3 reproduces the registered Amendment 24 admitted trades and results on
   the new engine within declared tolerance;
8. truncation at a weekend and mutation of all later bars leave that cutoff's
   shadow histories, candidate evidence, eligibility, membership, weights,
   and any permitted multiplier unchanged;
9. the `sp[k-1]`/`sp[k]` boundary tests from Amendment 24 still prove that
   fill-bar spread cannot change the gate but does change accounting;
10. mutations of a timestamp, gate, shadow busy boundary, cache content, or
    code hash are detected; and
11. all existing no-look-ahead, resampling, Bid/Ask, ambiguous-bar, cost,
    rollover, resolver, and basket tests remain green.

## 11. Required development reports

Report V1, V2, and V3 at base and 1.5x cost for:

1. 2022-01-01 through 2025-09-21;
2. 2025-09-21 through 2026-09-21;
3. the complete weekly walk-forward through the canonical end; and
4. the same-week equal-weight eligible family-middle control appropriate to
   each policy.

Every table must carry **DEVELOPMENT DATA — NOT BLIND**. For each window and
variant report net R, gross R, friction R, swap R, trades, PF, positive and
zero weeks, active-week percentage, realised and M5 MTM DD, worst week/month,
loss streak, family/timeframe/member composition, turnover, correlation,
weights, `n_eff`, overlap, and all rejection counts.

The per-trade ledger must separately record raw opportunity ID, shadow
accept/reject and busy-until state, direction relation to the open shadow,
weekly selection/order eligibility, gate estimate, actual accounting spread,
gate result, actual admission/rejection reason, weight, stop distance, entry
and exit UTC, gross R, spread, commission, slippage, swap, base net R, and
stress net R. Aggregate cost decomposition must reconcile exactly to it.

In addition, report:

- shadow cancellation share by `RE_SAME` and `RE_OPPOSE`, period, family,
  timeframe, stop, target, and entry mode;
- friction-gate cancellations before and after shadow filtering without
  double-counting them as executed trades;
- paired V2−V1 and V2−V3 weekly differences in gross/net R, cost, trades,
  active/zero weeks, MTM DD, and admitted-order identity; and
- the share and result of fills rejected only because shadow state continued
  through an unselected, gate-rejected, or portfolio-rejected event.

At least half the forward weeks in each required window must contain one or
more resolved primary V2 basket trades. Zero weeks remain included even when
this floor fails.

## 12. Development failure definitions

Amendment 25 fails for development promotion if any of the following occurs:

- any section 10 audit fails or V3 does not reproduce Amendment 24 as run;
- the primary V2 unit-risk net R is non-positive at base cost in either the
  44-month or trailing-12-month window;
- the primary V2 unit-risk net R is non-positive at 1.5x cost in either of
  those windows;
- fewer than three eligible, correlation-compliant members form the primary
  basket in more than half of forward weeks;
- fewer than half of the weeks in either required window contain a resolved V2
  trade;
- zero weeks, shadow rejections, gate rejections, or actual admission failures
  are omitted, treated as missing, or assigned to the wrong ledger;
- any actual fill depends on a pre-selection pending order, later spread, ATR,
  price, exit, or later weekly result;
- the edge appears only after DD scaling while unit risk is non-positive;
- the conditional sized replay, if reached, has full-period MTM DD below 35%
  or above 40%; or
- any frozen threshold, busy rule, direction treatment, ranking rule, family,
  half-life, correlation cap, weight bound, cost, or failure definition must be
  changed after viewing the result to make it pass.

A positive historical development result does not constitute confirmation or
authorize Demo replacement. It permits only the frozen forward observation in
section 14 after review.

## 13. Conditional DD sizing retained

Only if V2 passes section 12 may Amendment 23's causal sizing protocol run:
trailing 52 completed policy weeks, 37.5% target MTM DD, 35% soft entry gate,
40% hard protective ceiling, past-only bisection, 1.5x/all-history guards,
15% maximum weekly multiplier increase, immediate decreases, compounding,
volume rounded down, and full overlap/margin/cost checks.

Report 30/35/37.5/40/45/50% diagnostics and the USD 100 initial plus USD 100
monthly-deposit finance view only after the unit-risk pass. Deposits remain
outside calibration and are separated from trading profit. If unit risk fails,
all sizing and finance views are `NOT RUN`.

## 14. Genuine post-freeze confirmation protocol

Forward observation is read-only shadow logging; it sends no broker order.
It begins with the first complete market week whose Weekend Rebuild cutoff is
after this amendment is independently reviewed and committed. At every cutoff,
the logger must write an immutable, content-hashed decision record before the
next week's bars exist: source-data end timestamp, shadow state, eligible
cells, V2 membership, weights, scores, `n_eff`, gate constants, and any
unit-risk decision. During the week it appends raw signals, shadow transitions,
prior-bar gate inputs, would-be admissions, exits, costs, and M5 MTM marks.
Corrections are append-only and preserve the original record.

The first confirmation checkpoint is fixed at **26 complete calendar weeks**.
There is no early promotion for a temporarily positive curve and no extension
of a failed window until it becomes positive. At the checkpoint, all 26 weeks,
including zeros, are reported. Forward confirmation requires:

- no causality, hash, ledger, or data-freshness audit failure;
- at least 13 weeks with a resolved would-be basket trade;
- positive cumulative unit-risk net R at both base and 1.5x cost; and
- no frozen rule change during the observation window.

Failure leaves the policy unconfirmed. A redesigned rule requires a new
pre-registration and a new forward clock; the failed observations remain in
the permanent ledger. Passing the checkpoint permits independent review of a
possible Demo proposal but does not itself authorize an order or an autotrader
change.

## 15. Frozen status and authorization

The all-direction shadow block, shadow-before-gate ordering, three variants,
cost/R threshold, stressed ranking, evidence floor, and failure definitions
are frozen when this document is approved. No historical result may be run or
reported before that review.

This document authorizes no Demo or real order, no test order, no start or
restart of `payoff_demo_autotrader.py`, no Demo policy change, no PR, and no
commit by Codex. The current engine decision remains **NO TRADE**.
