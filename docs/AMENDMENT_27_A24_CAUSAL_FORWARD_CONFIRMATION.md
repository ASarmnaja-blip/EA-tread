# Amendment 27 — A24 causal basket forward confirmation and optional Demo mirror

**Written 2026-09-27 before any Amendment 27 implementation, forward record,
or order.** This is a pre-registration only. It freezes Amendment 24 on the
current engine with Amendment 26's causal fill-time candidate chain for a
26-complete-week prospective test. It does not rehabilitate Amendment 24's
historical failure and it does not authorize a backfilled week.

Nothing in this document starts, stops, or changes
`payoff_demo_autotrader.py`, sends an order, opens a PR, or authorizes a real-
money order. Implementation and operational activation require review after
this document is committed.

## 1. Status of the claim

The policy is nominated only because, on the corrected current engine and
causal chain, it was the sole tested policy positive in the already-seen
trailing 12 months at both registered costs: +31.643 R at base cost and
+18.000 R at 1.5x cost. Its 2022-01-01 through 2025-09-21 result was -80.397 R
at base and -109.119 R at 1.5x. It therefore failed Amendment 24's historical
unit-risk gate.

Those figures, every other historical result, all candidate diagnostics, and
the choice to carry this policy forward are **DEVELOPMENT DATA — NOT BLIND**.
No replay of data available on or before this freeze can confirm the edge.
Only complete weeks whose outcomes did not exist when the reviewed design was
frozen can do that.

This amendment does not run the 35–40% DD sizing protocol. DD determines how
large a profitable policy may trade; it cannot create expectancy. The forward
test is at unit risk. The optional Demo mirror uses minimum lots for execution
observation and has safety limits, not a calibrated 37.5% risk multiplier.

## 2. Exact frozen policy

The forward policy is Amendment 24 exactly, except that its candidate history
is built with Amendment 26's causal fill-time chain. This is the same corrected
variant reported in Amendment 26, not a new parameter search.

### 2.1 Candidate universe and causal chain

The universe remains exactly 8,250 cells:

- families `breakout`, `pullback`, `sweep`, `failed`, `vwap`, and `expansion`;
- signal timeframes M5, M15, M30, H1, and H4;
- ATR stops 0.75, 1.0, 1.5, 2.0, and 3.0;
- targets 0.5, 1.0, 1.5, 2.0, and 3.0 R; and
- market entry, or 0.50/1.00 ATR limit entry expiring after
  5/8/10/12/15 signal bars.

Each cell's candidate ledger uses the fill-time position rule. Multiple local
virtual pending orders may coexist and block nothing until their first valid
fill. Fill events are processed by
`(fill_M5_index, order_M5_index, original_signal_sequence)`. A fill is rejected
only when an accepted position is open on that fill bar. The busy interval
includes both entry and exit bars; the cell is flat only on the next bar. A
first trigger while busy is permanently rejected, not deferred. Market fills,
limit first-touch/gap handling, expiry, Bid/Ask geometry, stop-before-target
ambiguity, no same-bar TP following an intrabar limit fill, and time exits stay
unchanged.

The candidate ledger is always-on hypothetical evidence. The actual/shadow
basket ledger contains only virtual orders that could have been created while
the cell was selected. Candidate state contributes no actual slot, margin,
risk, or P/L. Actual pending orders are cancelled at Weekend Rebuild; carried
positions retain their entry-time member, weight, rule, and exit and consume a
slot until resolution.

Amendment 24 semantics are retained: a candidate fill encountered while the
cell is busy is rejected without changing state. When the cell is flat, a
friction-gate failure creates no candidate position and advances no busy
state.

### 2.2 Causal friction gate and cost accounting

At the first otherwise valid historical fill on M5 bar `k`:

```text
gate_spread = max(b5.sp[k-1], 0.090)
gate_friction_price = gate_spread + 0.140 + 2 * 0.0165
base_friction_R = gate_friction_price / stop_price_distance

admit only if base_friction_R <= 1/12
          and 1.5 * base_friction_R <= 1/8
```

`stop_price_distance` is the frozen stop ATR multiple times ATR known at the
signal close. The last fully closed M5 bar controls the historical decision;
the fill bar's spread is accounting only. A failure cancels that opportunity
permanently. It may not wait for a later cheaper spread. Live shadow and Demo
decisions use the executable quote known immediately before submission in
place of the historical `sp[k-1]` proxy.

The primary Demo90 profile remains recorded spread floored at 0.090 price
units, 0.140 round-turn commission, 0.0165 slippage per fill, 0.5493 long swap
per counted 21:00 UTC rollover, and zero short swap. Base cost and 1.5x
execution-cost stress are both recorded. Spread remains in Bid/Ask geometry
and is not deducted twice. Future holding time is not used by the entry gate;
realized swap is charged after it occurs. The Cent 260-point profile is not
substituted.

### 2.3 Weekly evidence, ranking, membership, and weights

A trade's net R belongs to its exit/resolution calendar week. At cutoff `C`,
only exits strictly resolved before `C` are known. Every completed calendar
week is present; no resolved trade is zero, never missing.

At every Saturday Weekend Rebuild after XAUUSD closes, each gated candidate is
scored on its zero-inclusive, 1.5x-cost-stressed weekly series:

```text
decay_weight(a) = 2 ** (-a / 3)
n_eff = sum(w) ** 2 / sum(w ** 2)
LCB_stress = mu_stress - 0.75 * sd_stress / sqrt(n_eff)
```

Eligibility requires 26 completed history weeks, at least eight non-zero
weeks, `LCB_stress > 0`, and a positive corresponding exponentially weighted
base-cost mean. Undefined variance or correlation means ineligible. Members
are sorted by descending `LCB_stress`, then tag.

The basket contains three to five members, at most one per family. Exact
duplicate realized order signatures are collapsed. Pairwise exponentially
weighted correlation must be at most 0.70. Adding a member must leave the
basket's stressed weighted mean positive. Fewer than three feasible members
means `NO TRADE` for that week.

Weights are frozen for the next seven calendar days and are calculated from
the same stressed zero-inclusive series:

```text
raw_weight_i = max(LCB_stress_i, 0)
               / max(stressed_downside_deviation_i, volatility_floor)
```

`volatility_floor` is the 25th percentile of positive downside deviations
among that weekend's eligible cells. Normalized weights are redistributed
deterministically into the 10–35% member bounds. Any pair with correlation at
least 0.50 is capped at 50% combined weight, with excess redistributed within
the same bounds. Infeasible weights mean `NO TRADE`.

There are at most five simultaneous actual/shadow basket positions. Carried
positions occupy slots. Simultaneous fills are admitted in the member-score
order frozen before the week. Opposing sleeves remain separate gross
positions; there is no netting, Grid, Martingale, averaging, pyramiding, or
adding to a loser. Idle capital and every idle week return zero.

Membership and weights are adaptive outputs recomputed each Weekend Rebuild;
the formulas and inputs above are frozen. No outcome from a week may alter its
own selection, weight, gate, or admission order.

## 3. Frozen implementation identity and data continuation

The starting implementation is the current engine at repository state
`f1a099d6512d5eaeaab172fd49120e0e9b5406c4`, with these SHA-256 identities:

```text
research/pilot/mtf_engine.py
  EEED9B37F804B3440EBB98FB6B18B8A8A688E2855002277CF8719D52065A5372
research/pilot/causal_chain.py
  90F3EB5EFB1A7B77B0086B6C24E47CC0B6370A9CF7374E4CF7B92D18359FA129
research/pilot/basket_gate.py
  6DBD05D4B27E166FBD53A45151CDC612334E29AD11D4BC2C5228B8571BA7FF14
data/canonical_XAUUSD_M5.npz seed snapshot
  DFA12A60AC16C0260522AE30AF5132322A6407E3A1BE9D4F08A96472614F3C67
```

Forward bars necessarily extend beyond the seed snapshot. Every ingestion
must record the previous content hash, source timestamps, bar count, first and
last UTC time, duplicate/gap checks, and new content hash. Corrections are
append-only in the evidence ledger: the original decision and original data
version remain readable. A strategy-code change, semantic engine change, or
silent repair during the 26-week clock invalidates confirmation; a necessary
repair requires a new amendment and clock.

## 4. Primary forward shadow ledger

The read-only shadow ledger is the primary and authoritative evidence. It
sends no broker order and is not altered by what the Demo mirror accepts,
rejects, fills, closes, or loses.

The first eligible week is the first complete market week whose Weekend
Rebuild occurs after this amendment is independently reviewed and committed
and after the logger passes its pre-start audits. If the logger is not ready
before that cutoff, the clock begins at the next complete week. Nothing is
backfilled and a partial week never becomes week 1.

Before the next week's bars exist, the logger writes an immutable decision
record containing at least:

- cutoff and source-data end timestamps and all content/code/config hashes;
- complete causal candidate and actual carried state;
- eligible cells, scores, base mean, `LCB_stress`, `n_eff`, correlations;
- selected members, family, order signature, rank, weights, binding caps,
  turnover, and frozen simultaneous-admission order;
- friction constants, cost profile, zero-week history, and `NO TRADE` reason;
  and
- the previous record hash, making the weekly decisions a hash chain.

During the week it appends stable raw-order IDs, signals, virtual orders,
first-fill events, busy decisions, gate inputs, gate results, would-be actual
admissions and rejection reasons, entries, exits, component costs, unit-risk
base/stress R, and M5 mark-to-market R. Corrections never overwrite a record;
they append the old hash, correction, reason, author, and new hash.

A stale/missing bar, unresolved timezone, failed hash, late Weekend Rebuild,
or logger outage is `DATA/AUDIT FAILURE`, not a zero-return week. The affected
week remains visible and prevents confirmation under section 8; it is not
silently removed or extended away.

## 5. Optional live Demo mirror

After separate implementation review and activation, a Demo mirror may submit
the same frozen policy's otherwise admitted decisions. It is secondary
execution evidence only. It must never replace, edit, or validate the shadow
ledger. Demo P/L includes broker fill noise, minimum-lot distortion, safety
overlays, other programs on the account, and therefore is not the policy's
confirmation statistic.

### 5.1 Minimum-lot mapping

The broker's current 0.01-lot minimum cannot faithfully encode basket weights
between 10% and 35% at the lowest possible risk. The Demo mirror therefore
sends **one 0.01-lot order per admitted policy event**, subject to the safety
checks below. It does not round a theoretical weighted volume up, split an
event into child orders, or use extra lots to approximate weight ratios. Each
row is labelled `MIN_LOT_UNWEIGHTED` and retains its theoretical member weight
beside the broker volume.

Consequently, the shadow ledger uses the frozen weights and remains the only
evidence about weighted basket expectancy. The Demo ledger is an equal-
minimum-lot execution mirror for spread, slippage, rejection, stop, target,
time-exit, and operational reliability. A missed Demo order caused by a
safety rule remains a would-be trade in shadow.

### 5.2 Order and account safety

Every Demo loop must fail closed unless MT5 reports both
`ACCOUNT_TRADE_MODE_DEMO` and a retail hedging account, and the login/server
match the activation record. It uses reserved magic **20260927** and comment
prefix `A27_A24_CAUSAL`; the existing payoff bot retains magic 20260923 and
the W1 rollover probe retains magic 20260922.

For every admitted event:

- one stable event ID may create at most one broker order and one position;
- the cell must be flat in the Demo actual ledger; no duplicate retry may
  create a second position after an ambiguous response;
- SL is attached in the original entry request; TP and the frozen time exit
  are recorded and enforced independently;
- local virtual limit orders are used until their first causal trigger so the
  fill-time gate can run before any broker submission; they expire under the
  frozen cell rule and are cancelled at Weekend Rebuild;
- the immediately executable spread must be no more than 0.135 price units
  and must also pass the frozen 1/12 base and 1/8 stress friction-to-R gate;
- volume is exactly the broker minimum only when it equals 0.01; any changed
  symbol minimum/step is `NOT ASSESSED` and stops Demo entries pending review;
- free margin, symbol trade mode, quote freshness, stop level, SL loss, and
  order result must be known and logged before another event is attempted;
  and
- no Grid, Martingale, averaging, loss recovery, discretionary addition,
  position netting, or SL widening is permitted.

The normal basket maximum remains five A27 positions including carried ones.
All request payloads, quotes, spread, calculated stop loss in USD, result
codes, deal/position IDs, fill, slippage, costs, exits, and rejection reasons
are append-only.

## 6. Coexistence and one account risk budget

`payoff_demo_autotrader.py` may be running independently. Amendment 27 does
not start, stop, edit, close, or claim its magic-20260923 positions. Distinct
magic numbers keep management and P/L attribution separate, but safety is
account-wide.

The A27 process keeps a persistent account-equity high-water mark from its own
activation. Before any A27 entry it calculates projected account drawdown to
all currently visible positions' attached stops, across every magic and
symbol, using current executable prices, `order_calc_profit`, and estimated
exit costs. Because current equity already contains current floating P/L,
`aggregate_additional_loss_to_all_SL` means only the further adverse loss from
each current executable close quote to its SL, floored at zero:

```text
projected_DD = (account_peak_equity - current_equity
                + aggregate_additional_loss_to_all_SL
                + proposed_A27_loss_to_SL) / account_peak_equity
```

If any open position has no valid SL, its loss cannot be bounded and A27 sends
no new order. A proposed order is rejected when projected DD would exceed the
35% soft boundary. At observed account DD of 35% or more, A27 cancels its local
pending orders and blocks new A27 entries while existing positions retain
their SL. At observed account DD of 40% or more, A27 cancels its pending
orders, closes only its own magic-20260927 positions at the next executable
quote, and enters a persistent halt requiring review. Gaps can exceed 40% and
must be reported.

This check reserves budget around payoff-bot and other positions already
visible; it cannot prevent another independent process from opening a later
position. A27 therefore rechecks on every loop and never assumes that distinct
magic numbers create distinct account equity. It never closes or modifies a
different magic's order. A true shared hard ceiling would require a separately
reviewed coordinator honored by every order sender; this amendment does not
pretend one already exists.

The W1 rollover probe's stricter rule remains intact: it refuses to submit a
probe whenever **any** account position is open. A27 never bypasses that check
or closes a strategy position merely to make a probe possible. During a
pre-announced W1 probe window, A27 blocks new Demo entries until the probe ends;
an already-open A27 or payoff position may still force W1 to skip. Such a skip
is reported as a Demo/W1 operational conflict and has no effect on the A27
shadow ledger.

## 7. Demo-only early stop

In addition to the account 35/40 guards, the Demo mirror has a smaller
strategy-specific kill switch. From its fixed activation equity, sum all
realized magic-20260927 P/L and current floating magic-20260927 P/L, including
commission and swap. If that A27-only mark-to-market loss reaches **10% of
activation account equity**, cancel A27 virtual pending orders, close all and
only magic-20260927 positions at the next executable quote, and persistently
halt A27 Demo submission. Restart requires a reviewed amendment or explicit
review decision; restarting the process may not reset the loss baseline.

This is a capital-preservation overlay on the distorted equal-minimum-lot
ledger. Triggering it is neither forward confirmation nor a registered failure
of the weighted policy. It may be operational evidence about the Demo mirror,
but only the uninterrupted shadow ledger determines section 8. Shadow logging
continues through a Demo halt, and shadow outcomes may not be censored at the
halt date.

## 8. Fixed 26-week checkpoint

The clock is 26 consecutive complete calendar market weeks from section 4's
first eligible cutoff. There is no early promotion, no shortening after good
results, and no extension until a losing window becomes positive. Every one of
the 26 weeks, including true zero weeks and `NO TRADE` decisions, is reported.

Forward confirmation requires all of the following:

1. no causality, engine-identity, hash-chain, cutoff, ledger, data-freshness,
   Bid/Ask, gate, rollover, or cost audit failure;
2. at least 13 of the 26 weeks contain one or more resolved would-be shadow
   basket trades;
3. cumulative **weighted unit-risk** shadow net R is positive at base Demo90
   cost;
4. the same cumulative shadow net R is positive at 1.5x execution cost; and
5. no frozen selector, chain, universe, threshold, half-life, rank, weight,
   correlation, cost, overlap, zero-week, or admission rule changed during the
   clock.

The checkpoint report must include both cost ledgers, gross R, spread,
commission, slippage, swap, net R, trades, PF, active/positive/zero weeks,
realized and M5 MTM DD in R, worst week/month, loss streak, members, families,
weights, `n_eff`, correlations, member and weight turnover, overlap, gate/busy/
slot/risk rejects, data failures, and a reconciliation from every admitted
trade. Demo results are shown separately with all safety rejections, minimum-
lot distortion, account interaction, and any early-stop event.

Passing permits independent review of whether to run Amendment 23's past-only
35–40% sizing calibration or revise Demo operation. It does not automatically
authorize larger Demo risk or any real-money order. Failure leaves the policy
unconfirmed. A redesign requires a new pre-registration and a new forward
clock; all failed and zero observations remain in the permanent ledger.

## 9. Pre-start audit gate

Before week 1 can be sealed, tests must print and pass:

1. Amendment 26's future-fill mutation, streaming-oracle, prefix, permutation,
   same-bar/busy/expiry/gap, and all-market-cell identity tests;
2. Amendment 24's `sp[k-1]`/`sp[k]` boundary and gate-failure-no-state tests;
3. truncation after a Weekend Rebuild leaves that decision record unchanged;
4. a later data mutation cannot alter an already-sealed week or its hash;
5. candidate state, Demo state, payoff magic, and W1 magic cannot cross-manage
   positions or P/L;
6. duplicate/retry simulation proves one event cannot create two orders;
7. non-Demo, non-hedging, stale quote, missing SL, excessive spread, insufficient
   margin, changed minimum lot, 35% projected risk, 40% DD, and 10% A27-loss
   conditions all fail closed;
8. a Demo rejection leaves the shadow event and weighted ledger unchanged; and
9. all existing engine, basket, cost, rollover, and weekly-boundary tests remain
   green.

Any failure prevents the forward clock and Demo mirror from starting. Audit
output is saved before the first weekly decision record.

## 10. Frozen authorization boundary

After independent review and commit, this amendment authorizes building and
auditing the read-only forward logger. A separate reviewed implementation is
required before activating optional Demo submission. This document by itself
does not start a process or send an order.

Real-money trading remains prohibited without the operator's explicit
confirmation for the specific order. Historical DD sizing remains `NOT RUN`.
No PR or commit by Codex is authorized in this task.

Current action under this pre-registration: **NO RUN; NO ORDER**.
