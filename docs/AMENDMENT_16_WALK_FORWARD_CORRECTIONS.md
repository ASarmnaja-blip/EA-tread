
# Protocol Amendment 16 — eleven corrections to the walk-forward design

**Written 2026-09-22. Committed alone, before the corrected search runs.**

Codex reviewed Amendment 15 before execution and **refused to run it**, finding
ten protocol defects. All are accepted. The refusal was correct and is the reason
the review step exists: the engine's 35 passing checks validated the trade
resolver and said nothing about the evaluation protocol wrapped around it.

Amends: Amendment 15's evaluation design. Does not amend Amendment 14's grid
(8,250 cells, verified), the measured cost model, any closure, W1's protocol, or
the standing prohibitions.

---

## 1. The 84-hour resolution embargo — the largest defect

**What was wrong.** Amendment 15 placed the selection cutoff on the *signal* time.
But the longest forward path a single signal needs is:

```
H4 limit with 15-bar expiry   15 x 4 h  =  60 h
time stop after the fill                =  24 h
                              total     =  84 h
```

A signal occurring **before** the cutoff can therefore be scored using prices from
**after** it. Forward information leaks into the ranking even though the signal
itself is in the past.

**The rule.** A trade may enter the selection window's ranking only if

```
final resolution time  <  selection cutoff
```

Checking the signal time alone is insufficient. The driver **purges** any signal
whose fill or exit crosses the boundary, and reports how many were purged per roll.

## 2. The holdout needs a buffer, not just an exclusion

The same arithmetic reaches the protected 120-day holdout through the decay curve.
For the 20-day decay point the required buffer is

```
20 days + 84 hours
```

before the holdout begins. The input series is **physically truncated** at that
point, so no signal, pending order, exit or decay horizon can touch the holdout.

## 3. State buckets must be frozen from the selection window

ATR tercile and spread-bucket edges computed over the **whole forward block** would
classify an early observation using volatility that happens later in that block.

**The rule.** Bucket edges are estimated on the trailing selection window, frozen,
and applied unchanged to the forward window.

`matched_control.build_strata` currently uses
`pd.Series(atr).shift(1).rolling(2880, min_periods=480).quantile(...)`, a
bar-by-bar trailing percentile over prior bars only, which Codex confirms is
acceptable. **It is verified rather than assumed**, and the frozen-edge path is
used for the spread bucket, which is computed from an hourly profile over the
whole series and is the one that does leak.

## 4. Day clustering is the wrong inference unit

The selection decision is made **once per roll** and held for ten days. Every day
in that block shares the same selection data, the same chosen cells, the same
ranking error and the same regime call. Days are not independent experiments, and
flipping them separately overstates the effective sample size.

**The rule.**

- the primary observation is **one score per roll**
- adjacent rolls reuse **50 of their 60** selection days, so roll decisions are
  correlated too. Inference uses **common sign flips over contiguous six-roll
  blocks**, matching the 60-day selection span
- with roughly 90 rolls this leaves about **15 largely independent blocks**.
  Power is materially lower than a 900-day sign-flip would suggest, and **the
  roll-level minimum detectable effect is reported before any null result is
  interpreted**

## 5. A single median cell is not a comparable null

One median cell has arbitrary setup identity, trade frequency and variance, and can
be far noisier than a five-cell selected group. The asymmetry, not leakage, is the
problem.

**The rule.** Three groups, all built identically: **equal-weight top-five,
central-five and bottom-five** cell means. The five central cells are those whose
selection ranks sit closest to the median.

**Trades are not pooled across the five cells.** Pooling lets the
highest-frequency cell dominate and counts overlapping trades repeatedly. Each
cell contributes its own mean, then the five means are averaged.

## 6. The primary statistic is ranking transfer

```
D_r = mean(Top5 forward excess) - mean(Bottom5 forward excess)
U_r = mean(Top5)    - mean(Mid5)
L_r = mean(Bottom5) - mean(Mid5)
```

> **`mean(D_r)` over rolls is the single primary hypothesis.** If
> selection-window ranking transfers at all, it is positive.

`U_r` and `L_r` are reported separately, as the operator requires both tails, with
a **joint max-statistic permutation adjustment across the two**. Two unadjusted
p-values would be an undeclared multiplicity choice.

The matched placebo remains the absolute "is there an edge" benchmark; the
central-five comparison answers only "did ranking help".

## 7. Duplicate cells inside a roll

8,250 unique *definitions* does not mean 8,250 distinct *realised* strategies
inside any 60-day window. Several targets, stops or expiries can produce the
identical trade set there, so the top five may be five copies of one strategy. The
global degeneracy check in Amendment 14 section 6a does not rule out roll-specific
degeneracy.

**The rule.** Before ranking each roll, build a **trade signature** per eligible
cell (signal indices, direction, fill bars, exit bars) and permit **one
representative per signature**. Otherwise parameterisations with more duplicate
forms get more chances at the tails. The number of collapsed duplicates is reported
per roll.

## 8. Zero-trade forward rolls, decided in advance

A cell can qualify in the trailing window and produce no forward trades. Removing
those cell-rolls *because of what happened next* is selection on the outcome.

**The rule — both estimands, with the primary declared:**

- **PRIMARY, policy return.** A cell-roll with no forward trade contributes
  **zero**, because capital sat idle. This is what a deployable engine actually
  earns.
- **SECONDARY, per-trade edge**, conditional on firing, with **coverage and
  missingness reported** and the conditioning stated.

## 9. The 15-trade gate selects for variance, and that is now stated

Ranking on a raw mean with a 15-trade floor lets high-variance, low-count cells
occupy the tails. That is a legitimate test **only of the selector "rank raw means
with a 15-trade floor"**, and it is not a test of adaptive selection in general.

**The rule.** The **selection-window trade-count distribution of the top, central
and bottom five is reported.** If the tails cluster at the minimum count, the
experiment is recorded as having tested **variance hunting** rather than edge
selection. A shrinkage or lower-confidence-bound selector would be better and
would require its own amendment; it is **not** substituted here after the fact.

## 10. Decay horizons overlap the next roll

The 20-day decay score reaches into the next roll's forward window, so adjacent
decay observations are dependent even though the primary 10-day windows tile
cleanly.

**The rule.** The simultaneous decay band uses the **same six-roll block
resampling** with common block flips across every decay horizon. Day-level flips
are invalid here. Horizons remain 1, 3, 5, 10, 20 days.

## 11. W1-scale rarity is NOT ASSESSED, stated now

W1 produced 75 trades in about three years — roughly **four per 60-day window**. It
can never pass a 15-trade gate.

> **`NOT ASSESSED: adaptive selection of rare, W1-scale setups is not identifiable
> from a 60-day selection window.`**

This search can test frequently firing members of the grid and nothing else. The
sentence above goes in the result whatever the result is.

## 12. Definitions tightened

- **"day" means calendar day** throughout, for clustering, gates and windows.
- rolls are indexed from the first roll whose selection window is fully inside the
  truncated series.

## 13. What failure looks like, so it cannot be argued away later

- `mean(D_r)` not significantly positive under six-roll block inference → **the
  ranking does not transfer, and adaptive selection over this grid does not work**
- the roll-level MDE is far above plausible values → **the sample cannot support
  the question**, which is the result
- the tails cluster at the minimum trade count → **variance hunting**, not edge
- the decay curve is flat → there was nothing to decay from

None of these licenses changing the selector, the window lengths, the gate, or the
number of cells carried forward.

## 15. Addendum — the primary statistic needs no placebo, and the power limit is accepted

**Written before the corrected run, at the operator's instruction to use whatever
data exists rather than decline on grounds of power.**

### 15.1 The placebo drops out of the primary statistic

`D_r = mean(Top5 forward) - mean(Bottom5 forward)` is a **difference between two
groups measured on the same roll, over the same calendar window, in the same
market**. Whatever drift, volatility regime or session mix that window contained is
present in both terms and **cancels in the subtraction**.

So the primary statistic is computed on **raw forward means**, not on matched
excess. This is not a weakening. It removes the one component that would otherwise
need a stratified placebo table per (timeframe, entry mode, stop, target,
direction) - 2,750 tables over ~60,000 bars each - which is what made the design
intractable, and it removes it without giving up the drift control that mattered.

- **PRIMARY:** `D_r` on raw forward means. Drift-neutral by construction.
- **SECONDARY:** `U_r` and `L_r` against the central five, also on raw means, with
  the joint max-statistic adjustment of section 6. Also drift-neutral, being
  differences within a roll.
- **TERTIARY, where computable:** the matched-placebo absolute check, which is the
  only quantity that answers "is there an edge at all" rather than "did ranking
  help". It is reported as NOT ASSESSED wherever the placebo table is not built.

Sections 1-14 are otherwise unchanged and all eleven corrections stand.

### 15.2 The power limit is accepted in advance

Roughly 90 rolls collapsing to about **15 independent six-roll blocks** is a small
sample for a permutation test, and the operator has been told so and has instructed
the run to proceed on the data that exists.

**The roll-level minimum detectable effect is therefore reported FIRST, before any
result**, exactly as section 13 requires. If the MDE lands far above any plausible
effect, the recorded finding is **"this sample cannot answer the question"** - which
is a finding, and is not presented as a null.

What is forbidden is the other thing: reading a non-significant result from an
underpowered test as evidence that the ranking does not transfer. The two are
distinguished by the MDE, which is why it is printed above the numbers rather than
below them.

## 14. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order has been sent,
no position is open, and no pull request is opened.
