# Amendment 19 — Current Edge Scanner

**Written before the first run: 2026-09-22.**

## 1. Objective

This amendment changes the operational question. It does not ask whether a rule
was profitable over the whole history or whether it will remain profitable in a
future holdout. It asks:

> Which already-defined event and direction, if any, has positive net behaviour
> in the market that exists now, and is that event firing on the latest closed
> bar?

This is a tactical selector, not a confirmation experiment. Its output can decay
and may change whenever it is run. It must therefore carry its data time and its
recent health statistics. It may emit a signal for observation or manual paper
execution, but it cannot send an order.

## 2. Fixed candidate universe

The scanner evaluates event definitions that existed before this amendment:

1. the 18 configurations in `core.REGISTRY`; and
2. the six crowded/late-entry patterns in `inverse_search.MECHANISMS`.

Each event is evaluated in two directions:

- **FOLLOW** — the direction produced by the event definition;
- **FLIP** — the opposite direction, run as a separate trade.

The scanner does not infer a flipped result by negating the FOLLOW result. Both
directions are independently resolved through M5 bars. If one M5 bar covers both
stop and target, the stop is booked first for each direction, as in `core.resolve`.
This prevents ambiguous bars from becoming artificial profits when a loser is
reversed.

To make FOLLOW and FLIP comparable, every event uses the same execution geometry:

- entry: first M5 open after the event's M15 bar closes;
- stop: 1.5 M15 ATR from entry;
- target: 1.5 M15 ATR from entry (1:1 reward/risk);
- time stop: 72 M5 bars;
- one position at a time within each candidate arm.

Changing this geometry after seeing a result is a new amendment.

## 3. What “current” means

The scanner uses only the most recent **90 calendar days** to score an arm. It
reports plain results for the latest 30, 60 and 90 days and computes an
exponentially weighted mean over the 90-day sample with a **21-day half-life**.
Older history is loaded only to warm indicators and is not part of the score.

No holdout is reserved. The latest data is deliberately used for selection. The
result is descriptive and operational; it is not evidence of a permanent edge.

## 4. Cost model

Every completed trade pays the more conservative of the two known account
structures at its entry hour:

- Standard-account spread model: 0.260 price units, shaped by the recorded
  hour-of-day spread profile, with zero commission;
- Raw-account model: the recorded per-bar spread plus 0.140 round-turn
  commission.

The larger of those is charged, plus 0.0165 slippage per fill (0.033 round turn).
Long trades crossing 21:00 UTC also pay 0.5493 price units per rollover; short
swap is zero. A second score is calculated at **1.5 times execution cost**.

These figures are account-specific operational assumptions. The output must print
which source and cost were used.

## 5. Eligibility and ranking

An arm is **READY** only when all of the following hold:

1. at least 20 completed trades in 90 days;
2. at least 5 completed trades in 30 days;
3. net mean is positive in both the 30-day and 60-day windows;
4. the 21-day-half-life weighted net mean is at least +0.05 R;
5. the shrunken score, weighted mean minus 0.5 weighted standard errors, is
   positive;
6. the weighted mean remains positive at 1.5 times execution cost; and
7. the latest 10 completed trades have positive net mean.

The ranking score is the shrunken score. Correlated variants are allowed in the
report, but only the highest-scoring arm whose event fires on the latest closed
M15 bar may become the current signal.

A FLIP arm must additionally have a negative 60-day net mean in its FOLLOW arm.
This makes “flip a loser” literal. A merely good opposite-direction backtest is
not labelled a flipped loser unless the source direction is currently losing.

There is no multiplicity-adjusted significance claim. The shrinkage and
cross-window gates reduce variance chasing but do not turn this operational scan
into proof.

## 6. Live signal gate

The scanner may emit `LONG` or `SHORT` only when:

- MT5 or the fallback file contains enough history;
- the newest closed M5 bar is no more than 20 minutes old;
- a READY arm fires on the latest fully closed M15 bar;
- the next M5 entry bar exists; and
- current spread is known and does not exceed twice the modelled spread for that
  hour.

Otherwise the decision is `NO_TRADE`, with a specific reason. A READY arm that is
not firing now belongs on the watchlist; it is not a current signal.

Entry, stop, target, expiry, invalidation, arm type, recent net means, weighted
score, cost stress, data timestamp and source must be printed. A JSON snapshot is
written to `data/current_edge_signal.json`; a rolling diagnostic log may be kept
under the ignored results directory.

## 7. Safety and stopping

The module must contain no `order_send` call and import no order helper. It is a
read-only scanner.

An arm ceases to be READY automatically when any eligibility condition fails on
a later run. No grace period and no parameter rescue is allowed. The scanner is
expected to change its mind as the current market changes.

This amendment does not authorize real-money or demo orders. Any order remains a
separate operator decision.
