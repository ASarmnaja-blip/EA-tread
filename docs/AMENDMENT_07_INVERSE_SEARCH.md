# Protocol Amendment 07 — searching for reliable losers, declared before it runs

**Written 2026-09-21. Committed alone, before the code it describes produces a
single number.** The operator proposed the route; the rules below are fixed now
so that whatever comes back can be believed.

Amends: nothing. It opens a new search direction and constrains it in advance.

Does not amend: `ORDERLY_TREND` as frozen by Amendment 05, Amendment 06's
failed replication, Amendment 04's one-champion rule, the prohibition on
real-money orders, or the prohibition on Grid and Martingale.

---

## 1. The idea, stated precisely

Every search so far looked for patterns that win. This one looks for patterns
that **lose reliably at RR 1:1**, on the reasoning that a mirror of a reliable
loser is a reliable winner.

The project already holds one instance of exactly this, which is why the route
is worth opening rather than dismissing: `UNSTABLE_HIGH_VOL` produced a gross
of **−0.069 R**, a genuine and repeated loss. Amendment 06 section 10 recorded
its inversion as roughly **+0.031 R**, and rejected it as too small to trade.

So the method is not speculative. What failed was **magnitude**. This amendment
searches for losses large enough to survive being inverted.

## 2. The arithmetic that decides what counts, fixed now

Let `g` be gross expectancy per trade in R and `c` the round-turn cost in R.

```
original   net = g - c
inverted   net = -g - c        <- cost is paid again, it does not cancel
```

Cost is therefore **subtracted twice over the pair**, and this is the whole
reason most reliable losers are not tradeable inverted.

### The measured cost, as of this amendment

Measured on the account in use (Exness-MT5Trial7, demo, `trade_mode=0`):

| component | measured value | source |
|---|---|---|
| spread, XAUUSD | 0.090 /oz | live tick sampling, `tools/measure_spreads.py` |
| **commission, XAUUSD** | **0.140 /oz round turn** | the demo's own deal history: $7.00 per lot per side |
| slippage | 0.0165 /fill, 0.033 round turn | measured floor, demo |
| **total** | **0.263 /oz** | |

With `R = 1.5 × ATR` and a median M15 ATR of 4.20, `R ≈ 6.30`, so:

```
c ≈ 0.042 R
```

**Commission had never been charged anywhere in this project before today**,
and at 0.140/oz it is 2.7 times the demo spread of 0.052. Every prior net
figure in this repository understated cost by roughly 0.022 R. The
cost-multiplier grids at 3x and 7x happen to cover it, which is why no earlier
conclusion is overturned, but the 1x column was wrong and is superseded.

### The threshold a candidate must clear

The minimum worthwhile edge stays at **+0.05 R**, unchanged from Amendment 03.
Therefore:

```
-g - c >= 0.05     =>     g <= -(0.05 + 0.042)     =>     g <= -0.092 R
```

**A candidate with a gross loss smaller than 0.092 R is not a candidate.** It
is recorded and it is not inverted. This is declared now, before any candidate
has been evaluated, so it cannot be relaxed to admit a near miss.

## 3. Geometry, fixed now

- **RR 1:1**, as the operator specified: stop at `1.5 × ATR(14)` on M15, target
  at the same distance. Symmetric by construction, so the inversion is a true
  mirror and not a second strategy wearing a mirror's clothes.
- time stop 72 M5 bars, unchanged from every other tool here
- one position at a time, signals resolved on the M5 series that generated them
- long and short evaluated separately as well as pooled, because the swap and
  the borrow are not symmetric

## 4. The ambiguity rule — the failure mode most likely to fake a result

At RR 1:1 the stop and the target are **equidistant**, so a single M5 bar whose
range covers both gives no information about which was reached first.

If worst case is charged to the original (assume the stop) and best case is
granted to the inversion (assume the target), the inversion manufactures profit
out of information nobody has. That is the single most likely way this search
produces a fake winner, and it is forbidden here.

**The rule: worst case is charged to BOTH directions.** An ambiguous bar is a
loss for the original and a loss for the inverted mirror. The inversion
recovers nothing from such bars.

Additionally:

- the **ambiguity rate** is measured and reported for every candidate
- a candidate whose ambiguity rate exceeds **15 %** is reported as
  `AMBIGUOUS - NOT ASSESSABLE` and is not eligible for inversion at any
  effect size, because too much of its outcome is unknown rather than measured
- the same candidate is re-run on **M1 bars** where M1 coverage exists, and a
  candidate whose sign depends on which resolution is used is reported as
  `RESOLUTION-DEPENDENT` and rejected

## 5. Multiplicity — the minimum of N is as biased as the maximum

Choosing the worst of N noisy estimates is exactly as optimistic as choosing
the best of N. There is no statistical discount for looking at the losing tail.

- the candidate family and its size **N are fixed in section 6 below and
  counted before any result is read**
- significance is judged at the **family-wise level** with the existing
  `core.bonferroni_z`, two-sided, because a candidate is interesting whichever
  way it deviates
- every candidate's number is reported, including the boring ones. **No
  candidate may be dropped after its result is seen.**
- the 120-day holdout is spent (Amendment 05 section 5) and is used here for
  diagnosis only, never for promotion

## 6. The candidate family, fixed now

`N = 24`. Six pattern families × two directions × two session filters
(all hours / London-NY only). Each is a mechanical rule with no free parameter
beyond what is listed:

| family | rule |
|---|---|
| late-extension entry | enter in the trend direction after price has travelled ≥ 2.0 ATR from the 20-bar mean |
| breakout into prior level | breakout of the 20-bar range whose target side sits within 0.5 ATR of the prior day's high or low |
| second failed push | second attempt at a 20-bar extreme that exceeds it by < 0.25 ATR |
| gap continuation | enter in the direction of an opening gap of ≥ 0.5 ATR |
| post-news chase | enter in the direction of the first 5-minute move after a USD HIGH release |
| inside-bar break | break of an inside bar following a range contraction of ≥ 30 % |

These six are chosen because each has a **nameable reason why a participant
might be systematically on the wrong side of it** — all six are late, crowded,
or reactive entries. A family with no such story would be excluded, because
without a mechanism a large negative number is the minimum of 24 draws.

## 7. Pass criteria for an inversion candidate, fixed now

All of the following, or it is recorded and not promoted:

1. gross expectancy `g <= -0.092 R` on the development period
2. significant at the **family-wise** level across N = 24, two-sided
3. ambiguity rate **below 15 %**, with worst case charged to both directions
4. sign unchanged when resolved on M1 instead of M5, where M1 exists
5. the loss is **not concentrated in one month or one session** — it must
   appear in at least 3 of 4 development quarters and in at least 2 sessions
6. a **circular-shift matched control** on the same bars shows nothing, so the
   result is the pattern and not the period
7. inverted net stays positive at **1.5x** measured cost, with 3x and 7x
   reported
8. the mechanism is stated in one sentence before the number is read

## 8. What passing does and does not authorise

Passing makes a candidate a **shadow challenger only**, subject unchanged to
Amendment 04: one champion, at most one shadow, and no promotion without
forward evidence that did not exist when this was written.

An inverted loser is **not** exempt from forward shadow. It is the same claim
about the future as any other, made from the other side.

## 9. What failure looks like, so it cannot be argued away later

- no candidate reaches −0.092 R → **the losing tail is not large enough to
  invert on this instrument**, and the route is closed rather than loosened
- a candidate reaches it but fails family-wise significance → **the minimum of
  24 draws**, not a finding
- ambiguity above 15 % → **not assessable**, and specifically not "probably
  fine"
- sign flips between M5 and M1 → **an artefact of bar resolution**
- inverted net dies at 1.5x cost → **a cost artefact**, which is the outcome
  Amendment 06 section 10 already recorded for `UNSTABLE_HIGH_VOL`

Any of these is recorded as a failed search. None is a reason to lower the
−0.092 R threshold, widen the geometry, or add a candidate to the family.

## 10. Status while this runs

The engine's answer today remains **NO TRADE**. `ORDERLY_TREND v2` remains a
rare shadow candidate with a failed cross-asset replication against it. No
real-money order is placed and no pull request is opened.
