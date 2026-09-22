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

## 8. First operational run — 2026-09-22

The first run used 40,000 live M5 bars from `Exness-MT5Trial7`. The newest closed
M5 bar was 1.9 minutes old. The scanner evaluated 48 arms and found 10 READY.
No READY event fired on the latest closed M15 bar, so the decision was
**NO_TRADE**.

This is not a negative research result. It means the scanner has healthy arms on
its watchlist but no current entry event. The top three READY arms were:

1. `crowded:post_news_chase / FOLLOW`, score `+0.2487 R`;
2. `crowded:breakout_into_level / FLIP`, score `+0.1903 R`;
3. `core:S5V1:VWAP reversion 2.5sd / FLIP`, score `+0.1786 R`.

All eligibility gates, including the 1.5x execution-cost stress, were applied.
The live snapshot is written to the ignored file `data/current_edge_signal.json`.
Run the scanner again with:

```powershell
$env:PYTHONIOENCODING='utf-8'; python research/pilot/current_edge.py
```

## 9. Operating cadence — observe midweek, rebuild on weekend

The tactical scanner is not a once-and-for-all backtest. The intended operating
cadence is:

- Wednesday, midweek: observe only. Run the live scanner and operational report,
  inspect drift, drawdown, streaks, and which READY arms are carrying the latest
  30-day basket. Do not change rules unless data freshness, spread, or risk
  limits are broken.
- Saturday or Sunday, while the market is closed: review and rebuild. Attribute
  the 0-30, 30-60, and 60-90 day baskets by family and mode, inspect the lead
  traces, then change gates or sizing only after rerunning the diagnostics.

Commands:

```powershell
$env:PYTHONIOENCODING='utf-8'
python research/pilot/current_edge_ops.py --mode wednesday
python research/pilot/current_edge_ops.py --mode weekend
```

The Wednesday report is produced by `research/pilot/current_edge_ops.py` and
writes the normal live snapshot through `research/pilot/current_edge.py`. The
weekend checklist calls the current-ready basket attribution in
`research/pilot/current_edge_backtest.py` and the weekly weekend lead-trace
diagnostics in `research/pilot/current_edge_lead_traces.py`.

The first lead-trace audit found that simple recent-performance momentum is not
a reliable selector. The audit now walks from weekend to weekend rather than in
10-day jumps, because rule changes are intended to happen while the market is
closed. Operationally, this means:

- keep `post_news_chase/FOLLOW` as a core arm only while both 30-day and 60-day
  means remain positive;
- treat `breakout_into_level/FLIP` as tactical, because its useful clue is
  crowded FOLLOW behaviour rather than a clean prior FLIP equity curve;
- cap `late_extension/FLIP` unless both recent and 30-day windows remain
  positive; and
- downsize or cut families that are detractors in the latest 0-30 day attribution.

All operational diagnostics charge the traded account cost. The Standard-account
spread is fixed as `260` points on a 3-decimal XAUUSD quote, i.e. `0.260` price
units, before commission, slippage and swap.

Risk sizing should be recalculated from the current 90-day drawdown. In the
2026-09-22 diagnostic, the current-ready basket's 90-day drawdown was
`-17.2165 R`, mapping roughly to `-34.43%` at 2.0% risk per trade and `-39.60%`
at 2.3% risk per trade. A 3.0% risk setting would have exceeded the stated
30-40% drawdown tolerance.
