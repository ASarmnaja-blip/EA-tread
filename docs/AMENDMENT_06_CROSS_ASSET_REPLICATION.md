# Protocol Amendment 06 — cross-asset replication, declared before any result

**Written 2026-09-21. Committed alone, before the code runs and before any
result on any asset other than XAUUSD has been looked at.**

Amends: nothing. It adds a validation route and fixes its rules in advance.

Does not amend: the `ORDERLY_TREND` definition frozen by Amendment 05, the
entry, stop or target of the pullback, Amendment 04's one-champion rule, or
the standing prohibition on real-money orders.

---

## 1. The problem this exists to solve

`ORDERLY_TREND` produced **69 signals in 1,094 days — about 23 a year**. The
forward-shadow requirement of 60–100 non-overlapping trades therefore needs
**2.6 to 4.3 years**. That is this program's oldest wall in a new costume:
selective enough to hold an edge means too few trades to prove it.

Two things must not happen in response, and both are forbidden here:

- **loosening `ORDERLY_TREND` to buy sample size.** The definition produced a
  positive number and fires rarely; relaxing it now would be using the result
  to finish designing the rule. Any relaxation is a **new v3 candidate** with
  its own amendment, its own holdout, and a stated count of every variant
  tried.
- **pooling trades across assets into one row count.** Gold, silver, the
  majors and an equity index move on shared macro events, so stacking their
  orders and calling it `n` inflates confidence by counting the same shock
  several times.

## 2. What replication can and cannot establish

Replication tests whether **the mechanism exists**. It does not establish that
XAUUSD is profitable. If an orderly trend rewards pullbacks because slow
participants rebalance into it, that should appear in more than one market. If
it appears only in gold, the honest reading is gold-specific fitting, which is
exactly the verdict `RESEARCH_FINDINGS.md` already recorded for the volume
filter when it failed on six of seven futures.

**XAU still needs its own forward evidence afterwards.** Cross-asset success
is permission to keep going, never permission to trade.

## 3. The universe, fixed now

Chosen for liquidity and for having three years of M5 on this account. **Not
chosen by result — none has been examined.**

| asset | group |
|---|---|
| XAUUSD | metals |
| XAGUSD | metals |
| EURUSD | FX |
| GBPUSD | FX |
| USDJPY | FX |
| US500 | equity index |

All six are tested and all six are reported. **No asset may be dropped after
its result is seen**, for any reason, including "it is not comparable".

## 4. What is held identical

- the `ORDERLY_TREND` definition from Amendment 05, unchanged
- the pullback entry, the 1.5 ATR stop, the 2R target, the 72-bar time stop
- every feature dimensionless: `ATR/price`, `jump_share`, `cost/ATR`
- thresholds as the 70th and 30th percentile of a **45-day trailing window
  computed within each asset**, never shared across assets
- signals resolved on the same M5 series that generated them
- one position at a time per asset, identical overlap handling

What differs per asset, because it must: its own spread, its own ATR, its own
session clock.

## 5. Costs

Each asset is charged **its own measured per-bar spread** from its own export,
plus the measured slippage floor of **0.0165 per fill**.

That is a **floor and not an estimate**. These files come from a demo Raw
account; on XAUUSD the live Standard spread is 0.260 against the demo's 0.037,
a ratio near seven. The ratio for the other five is unknown, so results are
reported at:

```
1x   as measured
1.5x
3x
7x   the XAU live-to-demo spread ratio, as a pessimistic bound
```

**A sign that does not survive 3x is reported as cost-fragile.**

## 6. How the evidence is combined

**Random-effects meta-analysis on the effect estimates, not on the rows.**

1. each asset's net expectancy per trade and its standard error, clustered by
   **calendar day**, so orders sharing one macro event are one observation
2. combined with a random-effects model, which lets the true effect differ by
   asset instead of assuming one number fits all
3. heterogeneity reported, not hidden: if the assets disagree, that is a
   result about the mechanism
4. **per-asset results always shown beside the pooled figure**

## 7. Pass criteria, fixed now

All of the following, or it does not pass:

1. pooled random-effects net expectancy positive, with the lower bound of its
   interval above zero
2. positive on **at least 4 of the 6** assets
3. **leave-one-asset-out**: every one of the six subsets stays positive
4. no single asset contributes more than **35 %** of the pooled weight
5. the sign survives **1.5x** cost, and 3x is reported
6. day-clustered intervals, not naive ones
7. **XAU positive**, though its own interval may still straddle zero

## 8. Evidence, not trade counts

Amendment 05's "60–100 trades" is replaced as the promotion trigger, because a
trade count does not measure precision. A 1R standard deviation and a +0.15 R
effect needs several hundred trades, not sixty.

Promotion evidence is instead:

- **H0**: net expectancy after measured cost ≤ 0 R
- **minimum worthwhile edge**: +0.05 R
- an **always-valid confidence sequence / e-process**, evaluated whenever new
  data arrives, which cannot be inflated by looking often
- promotion at **e-value ≥ 20**
- and, regardless of what other assets show, **at least 12–20 independent
  XAU forward events**, so nothing is promoted on other markets alone

## 9. What a failure looks like, so it cannot be argued away later

- pooled interval straddles zero → **mechanism not established**
- positive on 3 or fewer assets → **not replicated**
- any leave-one-out subset turns negative → **carried by one market**
- one asset above 35 % of the weight → **not a cross-asset result**
- sign lost at 1.5x cost → **cost artefact**
- XAU negative while others are positive → **the mechanism may exist, but not
  in the instrument the operator trades**, and the project's answer is still
  NO TRADE

Any of these is recorded as a failed replication. None of them is a reason to
adjust `ORDERLY_TREND`.

## 10. Status while this runs

`ORDERLY_TREND v2` remains a **rare shadow candidate**. `UNSTABLE_HIGH_VOL`
remains a **validated avoidance state** and is used as a kill switch for
trend-family tools, never inverted into a strategy: its gross is −0.069 R
against a 0.038 R cost, so inverting leaves roughly +0.031 R before path
effects and slippage, which is too small and too fragile to trade.

The engine's answer today is **NO TRADE**, and this amendment does not change
that. No real-money order is placed and no pull request is opened.
