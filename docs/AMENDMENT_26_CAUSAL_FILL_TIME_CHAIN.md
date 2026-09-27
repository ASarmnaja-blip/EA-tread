# Amendment 26 — causal fill-time cell chain and contamination re-measurement

**Written 2026-09-27 before any Amendment 26 implementation or result.** This
is a pre-registration only. Amendment 25 remains **NOT APPROVED** and is not
run. Its proposed shadow rule depended on a signal-order chain that used the
future fill of an earlier limit order to suppress a trade that had already
filled. Reproducing that chain exactly reproduced its look-ahead; it did not
validate it.

This amendment first replaces that defective state transition with a causal
one, then measures how much it changes three already-registered policies. It
does not introduce or judge a new selector. No result may be produced until
this document is independently reviewed.

## 1. Scope and order of work

The work has two ordered phases:

1. build and audit a causal per-cell chain in a new module; and
2. only after every causality audit passes, rebuild the universe and re-run
   Amendment 21's weekly baseline, Amendment 23, and Amendment 24 as
   registered, changing only the defective per-cell ordering/state rule.

The old and causal results are reported side by side. This is a contamination
measurement, not a search over chain choices, pending-order policies,
thresholds, families, ranks, or portfolio parameters. No Amendment 25 policy
is run in this amendment.

All historical data is already seen. Every replay is labelled
**CONTAMINATION RE-MEASUREMENT — DEVELOPMENT DATA — NOT BLIND**. A profitable
causal replay cannot constitute independent confirmation.

## 2. Chosen causal rule: fill-time position rule

This amendment chooses option **(a), the position rule in fill-time order**.
The reason is that it is the narrowest correction to the original declared
constraint of at most one open position per cell. It removes dependence on a
future fill without adding the materially different rule that one unfilled
pending order monopolizes a cell and suppresses later signals. Option (b), the
working-order rule, is causal but is not evaluated here; evaluating it would
be a separate strategy design after historical outcomes have been seen.

Each signal may create a local/virtual market or limit order using only values
known at its signal close. Multiple virtual pending orders from the same cell
may coexist. A pending order occupies no position state and blocks no later
signal or fill merely because it exists.

The engine processes each order's **first otherwise valid fill event** in
ascending M5 fill-bar order. Within the same fill bar, deterministic priority
is:

```text
(fill_M5_index, order_M5_index, original_signal_sequence)
```

The older order therefore has FIFO priority only when two orders first become
fillable on the same M5 bar. The final sequence field is a stable tie-break,
not a performance input.

For a fill event at bar `k`:

- if the cell is flat at `k`, accept the fill, resolve its frozen
  stop/target/time-stop plane, and mark the cell busy through its exit bar;
- if an accepted position has `entry_k <= k <= exit_k`, reject that fill
  permanently as `POSITION_BUSY_AT_FILL`; and
- the cell becomes eligible for another fill only on a bar strictly after the
  accepted position's exit bar.

An order whose first trigger happens while a position is open is cancelled at
that trigger; it is not deferred to a cheaper or later fill. An order that has
not yet triggered remains virtual until its own first trigger or expiry, even
if another order from the cell fills in the meantime. If its first trigger is
after the position has closed and before its frozen expiry, it may fill. This
is implementable causally with virtual orders and preserves the original
opportunity set more closely than making pending state exclusive.

Market orders have `fill_k = order_k`. Limit fills retain the canonical first
touch/gap fill, expiry, Bid/Ask, and no-same-bar-target rules. Nothing in the
sort may use gross return, exit reason, holding time, eventual spread, or
whether another order later fills.

## 3. The defect-catching test is mandatory

Before any historical result, construct at least this synthetic case:

- order A is signalled first and is a limit order whose first possible fill is
  later, at bar 20;
- order B is signalled later but first fills earlier, at bar 10; and
- the cell is flat at bar 10.

Run two worlds that are identical through B's decision at bar 10:

1. A eventually fills at bar 20; and
2. A's post-bar-10 path is mutated so that A expires without filling, or A is
   kept as the same signalled order but its precomputed future fill event is
   removed from the event input. In both forms, the information through bar 10
   is identical.

The causal chain must make the same decision about B in both worlds: B is
accepted at bar 10. The future fill or non-fill of A cannot change that
decision. A second version keeps B open through bar 20 and must reject A at
bar 20; a third version closes B before bar 20 and may accept A then. These
tests distinguish causal position state from future knowledge.

The unchanged legacy signal-order chain is a required negative control. It
must reject B when A later fills, accept B when A is removed or never fills,
and therefore **FAIL** the invariance test. The Amendment 26 audit passes only
when the old failure is observed and the new chain passes. If the old chain
unexpectedly passes, or the new chain fails, stop before all performance
output.

## 4. Streaming oracle and event implementation

The authoritative causality oracle is a bar-by-bar streaming implementation.
At M5 bar `k` it can see only signals closed before their permitted order time,
orders still inside their known expiry, current/past executable prices, and
the current position state. It cannot inspect whether any pending order fills
on a later bar.

A faster batch implementation may precompute each order's first possible fill
and sort the resulting events as section 2 specifies, but it must reproduce
the streaming oracle exactly. Test the equivalence on synthetic boundary cases
and a deterministic sample covering every family, timeframe, entry mode, stop,
and target. Shuffling the raw signal input must not change the result except
that the frozen original-signal tie-break remains attached to each event.

The busy interval includes the entry and exit bars. When an existing position
can exit and a pending order can trigger on the same OHLC bar, the new fill is
rejected; M5 data cannot establish that the exit occurred first. This is the
conservative counterpart of the existing stop-before-target ambiguity rule.

## 5. Separate candidate and actual ledgers retained

The useful architectural separation from Amendment 25 is retained without its
invalid chain:

- the **candidate ledger** is an always-on hypothetical cell history built by
  the causal fill-time rule; and
- the **actual ledger** contains only orders and positions that the weekly
  policy could have created under its frozen membership and admission rules.

Candidate P/L and hypothetical positions do not consume actual slots, margin,
risk, or capital. Actual portfolio rejection never edits candidate history.
Actual P/L never changes the candidate chain. Every output row carries one
stable raw-order ID so candidate eligibility and actual admission can be
reconciled without conflating the ledgers.

For the re-measurement, each old policy keeps its own registered interaction
between those ledgers. Amendment 24 retains its explicitly separate forward
actual state. Amendment 23 and Amendment 21 retain their original use of the
continuous cell opportunity sequence, except that sequence is now produced in
causal fill-time order. No result-dependent exception is added.

Actual pending orders still obey the registered weekly boundary: they are
cancelled at Weekend Rebuild, and a newly selected cell cannot inherit an
actual order created before its selection. A hypothetical candidate order may
exist across a cutoff only inside the candidate ledger and cannot become an
actual order retroactively.

## 6. Frozen universe and execution assumptions

The universe remains the declared 8,250 cells:

- `breakout`, `pullback`, `sweep`, `failed`, `vwap`, and `expansion`;
- M5, M15, M30, H1, and H4 signals;
- 0.75, 1.0, 1.5, 2.0, and 3.0 ATR stops;
- 0.5, 1.0, 1.5, 2.0, and 3.0 R targets; and
- market entry or 0.50/1.00 ATR limit entry expiring after
  5/8/10/12/15 signal bars.

Signal definitions, ATR availability, resampling, first valid fill, stop and
target geometry, time stop, Bid/Ask accounting, ambiguous-bar loss priority,
slippage, commission, and rollover are unchanged. The primary profile remains
Demo90: spread floored at 0.090 price units, 0.140 round-turn commission,
0.0165 slippage per fill, 0.5493 long swap per counted rollover, and zero short
swap. Amendment 24's gate still uses `max(b5.sp[k-1], 0.090)` while fill-bar
spread remains accounting only.

Neither `mtf_engine.py` nor `walk_forward.py` may be edited. The causal chain
belongs in a new module and new versioned cache. Legacy modules and caches stay
read-only so their contaminated outputs remain reproducible for comparison.

## 7. Cache and full-hash rules

The new cache key and embedded manifest must cover canonical data content,
signal inputs, raw-order records, the causal-chain module, every imported
resolver used to create fills/exits, execution costs, fill-time ordering,
same-bar tie-breaks, busy-boundary convention, and policy code. Filename and
timestamp matches are insufficient.

The legacy cache may be read only for the old-result reproduction and direct
trade-level comparison. It may not supply the causal universe. The Amendment
24 raw-opportunity cache may seed immutable raw events only after independent
full-hash validation; all causal acceptance decisions must be recomputed by
the new module.

## 8. Pre-result audit gate

All audits print before any net R, PF, DD, or profitability figure. Any failure
stops the run. Required audits are:

1. the section 3 future-fill mutation test, with the legacy chain failing and
   the causal chain passing;
2. streaming-oracle versus batch-event equality;
3. prefix invariance: truncating after B's fill, or mutating every later bar,
   cannot change B's state or any earlier decision;
4. raw-input permutation invariance with stable event IDs and tie-breaks;
5. same-bar FIFO, entry-bar busy, exit-bar busy, next-bar-flat, expiry, gap,
   and never-filled order boundary cases;
6. market-entry identity: because market fills follow signal time, the legacy
   and causal chains must match for every market-entry cell unless a separately
   explained non-ordering defect is found;
7. exact reproduction of each published old reference before comparing it to
   the causal result; an unexplained mismatch stops that policy's comparison;
8. Amendment 24's `sp[k-1]`/`sp[k]` mutation tests and its candidate gate
   semantics remain intact: a busy fill is rejected without changing state;
   when flat, a gate failure creates no position and advances no busy state;
9. candidate state cannot leak P/L, risk, slots, margin, or pre-selection
   pending orders into the actual ledger;
10. cache data/code/cost/order mutations invalidate the cache; and
11. all existing resampling, no-look-ahead, Bid/Ask, ambiguous-bar, resolver,
    rollover, cost, weekly-boundary, and basket tests remain green.

The old negative control is quarantined. Its deliberate failure of the new
test does not make the suite fail; failure to observe that expected failure
does.

## 9. Ordered contamination re-measurement

Only after section 8 passes, run these policies in this order. For each, first
reproduce the legacy result on unchanged code/cache, then run the causal
replacement. The only permitted change is section 2's per-cell chain.

### 9.1 Amendment 21 weekly evolutionary baseline

Retain its 8,250-cell menu, Friday 22:15 UTC cutoff, trailing 56-calendar-day
ranking window, 20-trade/eight-active-day eligibility, mean net R minus 0.75
standard errors, duplicate entry-signature collapse, one weekly champion,
seven-day forward holding rule, and registered Demo90 costs. Compare against
the published 1,757 trades and +248.785 R reference, but do not assume those
figures will survive.

### 9.2 Amendment 23 decay-weighted basket

Retain exit-week assignment, zero-inclusive weeks, three-week half-life,
26-week/eight-nonzero eligibility, LCB coefficient, three-to-five members,
family and duplicate caps, correlation limits, 10–35% weights, overlap/risk
rules, and base/1.5x costs. Replace only the defective cell chain. Report the
legacy +62.070 R 44-month reference as contaminated, not as a target.

### 9.3 Amendment 24 friction-gated basket as registered

Retain the prior-closed-bar `sp[k-1]` friction gate, gate threshold,
1.5x-stressed ranking, evidence floor, selector, weights, and causal forward
actual execution. In the causal candidate chain, a fill encountered while busy
is rejected; when flat, a gate failure creates no position and does not advance
busy state, matching Amendment 24's registered semantics. Correct only
candidate-history event ordering and the resulting busy chronology. Amendment
24's forward executor is not replaced; its selected membership may change
because its corrected candidate evidence changes.

No Amendment 25 shadow-filter result, alternative working-order chain, new
cost gate, or parameter search may be appended to this run.

## 10. Required old-versus-causal report

Begin with the causality verdict and contamination magnitude before discussing
profitability. For the universe, report:

- raw signals, orders, fills, expiries, accepted fills, and busy rejects;
- out-of-order legacy rejects and their gross/net R by period, family,
  timeframe, direction relation, stop, target, and entry mode;
- legacy-only, causal-only, and shared accepted trades, with exact identity
  and P/L reconciliation; and
- market-entry equality and limit-entry differences separately.

For each policy report legacy and causal results side by side, plus causal
minus legacy, over every window that policy originally required. At minimum
include the complete available walk-forward, 2022-01-01 through 2025-09-21,
and 2025-09-21 through 2026-09-21 where the policy supports them.

Report base and 1.5x cost wherever the registered policy required both. Show
trades, gross R, spread/commission/slippage R, swap R, net R, edge per trade,
PF, win rate, positive/active/zero weeks, realised and M5 MTM DD, worst
week/month, loss streak, member or champion turnover, composition, overlap,
and rejection counts. Costs must reconcile from a per-trade ledger rather than
a fitted residual.

For Amendment 24, separately report how corrected candidate histories change
eligibility, weekly membership, weights, gate cancellations, and its unchanged
causal forward admission logic. For Amendment 23, report the same basket
composition differences without reinterpreting them as a newly discovered
rule.

Apply each amendment's original unit-risk failure criteria to its causal
result and state the verdict, but do not tune or replace a failed policy inside
this run. Amendment 21 remains an exploratory baseline rather than a promotion
test.

## 11. Meaning of success and failure for Amendment 26

Amendment 26 succeeds as a measurement only when all causal audits pass, all
legacy references reproduce, and every reported aggregate reconciles to the
event/trade ledgers. It can succeed even if all three causal policies lose.

The measurement fails and stops if:

- the new decision about an earlier fill changes when a later fill is mutated;
- the causal batch engine differs from the streaming oracle;
- the legacy negative control does not exhibit the registered defect;
- market-entry chains differ without a proved, separately reported cause;
- an old reference cannot be reproduced before causal comparison;
- a hypothetical candidate state leaks into actual portfolio accounting;
- a cache/hash, cutoff, cost, Bid/Ask, or future-data audit fails;
- a policy rule other than the chain is changed; or
- a result is selected from alternatives after its outcome is observed.

Profitability is not the success criterion of this contamination measurement.
Each corrected policy's own frozen criteria determine only that policy's
historical development verdict.

Conditional DD sizing remains as originally registered: it may run for an
individual corrected basket only if that basket passes its own unit-risk gate.
If it does not pass, sizing, leverage, DCA, and finance projections are
`NOT RUN`. Scaling cannot repair expectancy.

## 12. Forward protocol retained, but not started here

Amendment 25's useful 26-week read-only confirmation protocol is retained. It
does not start under Amendment 26 because this amendment measures contamination
and nominates no new operating policy. After the causal re-measurement, any
policy proposed for confirmation requires a separately reviewed and committed
amendment that freezes its exact selector, chain, gate, weights, and costs.

The first complete market week after that future freeze starts a fixed
26-calendar-week clock. Before each week exists, an immutable content-hashed
record must store source cutoff, causal candidate state, actual state,
eligibility, membership, weights, scores, constants, and would-be decision.
During the week, a read-only logger appends signals, virtual orders, fill-time
state transitions, gate inputs, would-be actual admissions, exits, costs, and
M5 MTM marks. It sends no order.

There is no early promotion and no extension until a negative window becomes
positive. The checkpoint includes all zero weeks and requires no audit failure,
at least 13 weeks with a resolved would-be trade, positive cumulative unit-risk
net R at base and 1.5x cost, and no frozen-rule change. Passing permits review
of a possible Demo proposal; it never authorizes one automatically.

## 13. Frozen status and authorization

The fill-time rule, pending-order behaviour, event tie-break, busy-through-exit
boundary, audit suite, measurement order, three policies, report fields, and
forward protocol are frozen when this document is approved. Results may not be
used to revise them inside the same run.

This document authorizes no historical run yet. It authorizes no Demo, test,
or real order; no start or restart of `payoff_demo_autotrader.py`; no Demo
policy change; no PR; and no commit by Codex. The current engine decision
remains **NO TRADE**.
