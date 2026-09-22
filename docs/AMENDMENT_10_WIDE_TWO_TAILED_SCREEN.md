# Protocol Amendment 10 — the wide two-tailed screen, declared before it runs

**Written 2026-09-22. Committed alone, before the code it describes produces a
single number.** The operator asked for every entry tool stacked and tuned, with
both tails reported. Codex reviewed the first draft of this design and rejected
it. What follows is the corrected version, and the corrections are recorded
rather than applied silently.

Amends: nothing. It opens a third search and constrains it in advance.

Does not amend: `ORDERLY_TREND` (Amendment 05), the failed cross-asset
replication (Amendment 06), the measured cost model or matched-control strata
(Amendment 08), the closed inverse routes (Amendments 07 and 09), the watchlist,
the prohibition on real-money orders, or the prohibition on Grid and Martingale.

---

## 1. What the first draft got wrong, and what replaces it

The first draft proposed 3,360 configurations, ranked on matched excess, with
individual candidates named from each tail. Three defects, all accepted:

**The count was wrong.** "A fires while B contradicts" follows A's direction, so
the operation is not symmetric and the anchor matters. Both anchors must be
counted for both stack modes.

**The design cannot support candidate-level discovery.** At N in the thousands
the permutation maxT critical value lands near 4.0–4.5 in |t|. With a trade-level
standard deviation near 1 R, detecting an effect of 0.092 R at that threshold
needs on the order of **3,000 independent trades**, and day clustering makes it
worse. Almost no candidate here has that. A search that names a winner under
those conditions is reporting noise with a decimal point.

**The control contaminated itself.** A stratum's full-pool mean includes the
focal trade and the rest of its day, so a candidate was being compared against a
benchmark it had helped construct.

### The replacement, in one sentence

**SELECT ranks and tests the family as a whole; it makes no claim about any
individual candidate. CONFIRM tests a small, pre-fixed, blinded set. HOLDOUT is
opened only for CONFIRM survivors.**

Because SELECT and CONFIRM are independent slices, SELECT does not have to defeat
6,480 comparisons. The formal multiplicity burden is **2K at CONFIRM**, not
6,480 at SELECT. That is what makes the exercise informative instead of futile.

## 2. The universe, counted correctly and named honestly

```
singles      40 tools x 3 parameter settings x 2 directions            =   240
agreement    780 pairs x 2 anchors x 2 directions                      = 3,120
contradiction 780 pairs x 2 anchors x 2 directions                     = 3,120
                                                                   N = 6,480
```

**This is a fixed grid of 40 named tools at three settings each, with pairs
taken at the textbook setting. It is NOT "every possible entry tool or
parameter", and no claim of exhaustive coverage is made.** The forty are listed
in `research/pilot/tools_wide.py` and were fixed before any result was read.

## 3. Gates, fixed now

- **minimum trades on SELECT: 40**
- **minimum active days on SELECT: 20.** A minimum trade count alone is not
  enough: fifty trades falling on six days do not support day-cluster inference,
  and the first draft would have admitted them.
- **minimum control-pool size: 30 eligible bars** after the leave-one-day-out
  removal
- minimum trades on CONFIRM: **50**, minimum active days: **20**

## 4. The control, corrected

The control is the stratum's **leave-one-day-out pool mean**: the mean gross of
every eligible bar in the focal bar's stratum, with the focal bar's whole
calendar day removed. Implemented by precomputing each stratum's total and count
and subtracting the focal day's contribution, which keeps it vectorised.

- the focal trade is excluded, and so is the rest of its day
- the strata are unchanged from Amendment 08 section 6.5: direction, calendar
  quarter, session, ATR tercile from prior bars, news state within 30 minutes of
  a USD HIGH release, hourly spread bucket
- because **quarter is one of the strata**, a control pool never reaches more
  than three months away from its focal bar. That bounds, but does not
  eliminate, the use of later observations in an earlier benchmark, and it is
  recorded as a known limitation rather than claimed as solved.
- the full-pool mean replaces Amendment 08's 20 random draws. It is the
  conditional expectation of that estimator with the Monte Carlo noise removed,
  there is no seed and nothing to tune once the strata are fixed. It is a new
  pre-registered estimator, not a better version of the old claim.

**Known residual dependence:** one control mean is reused by many candidates'
trades, which a one-way day-clustered standard error does not fully represent.
This is stated, not fixed.

## 5. Statistics, fixed now

### The day-clustered statistic

```
mu   = sum_d S_d / n
SE^2 = G/(G-1) * sum_d (S_d - n_d*mu)^2 / n^2
```

with `S_d` the sum of excesses on day d, `n_d` the count, `G` the number of
active days. **The `G/(G-1)` finite-cluster correction is retained** — the first
draft dropped it.

### The permutation

Signs are flipped **per calendar day**, and **the same flip vector is applied to
every candidate in a draw**, which preserves both the within-day dependence and
the correlation between candidates that share components. Under such a flip the
statistic depends only on the per-day sums and counts, so the whole family
reduces to matrix products against a (candidates x days) matrix. That reduction
is exact **conditional on the excesses being fixed**, and it stops being exact if
the control means are recomputed inside each permutation, which they are not.

**This is a wild-cluster sign-flip approximation, not an exact randomisation
test**, because trade returns at RR 1:1 are not symmetric. Recorded as a
limitation.

### The two global statistics, pre-registered as the primary result

1. **max |t| across the family** — the statistic for a sparse signal, one
   candidate genuinely different
2. **Berk–Jones, calibrated from the same shared permutations** — the statistic
   for a distributed signal, many candidates slightly shifted. Its analytical
   independent-test distribution is not usable here, so it is calibrated from
   the permutation draws.

Both are reported with permutation p-values. **These are the primary result of
SELECT.** "Does this family contain more than chance produces" has a defensible
answer at this N; "which one is real" does not.

### What is reported but not claimed

- **Benjamini–Hochberg q-values are DESCRIPTIVE ONLY and are not a formal FDR
  control here.** BH needs independence or positive regression dependence, and a
  family containing both agreement and contradiction stacks of the same tools has
  negative and non-monotone relationships. Labelled as a sensitivity readout.
- Storey q-values are not used: estimating the null proportion is unstable with
  correlated, discrete permutation p-values.
- Formal candidate-level claims, where any are made at all, use **Westfall–Young
  step-down maxT**.

### A power table, produced before the search is interpreted

The run prints the **empirical distribution of day-clustered standard errors**
across the family, and the effect size detectable at 80 % power at the
permutation critical value, at the 25th, 50th and 75th percentile SE. If that
table shows the detectable effect is far above anything plausible, **that is the
finding**, and it is reported as such rather than buried under 6,480 numbers.

## 6. Reporting, and the rule that stops the winning tail becoming a generator

The operator asked to see both tails. The danger is that the largest positive t
from a 6,480-way search becomes "the finding" no matter what caveats follow.

**On SELECT, no individual candidate is named.** What is reported:

- the full distribution of excess and t, with fixed quantiles
- counts exceeding pre-registered thresholds, beside what chance produces
- the two global permutation p-values
- the K per tail identified by **blinded ID only** (`L1..L5`, `W1..W5`)

A manifest mapping each ID to its tool, parameters, direction, stack mode and
the code hash is **frozen to disk before CONFIRM runs.**

**A name is revealed only after that candidate passes CONFIRM.** Failures are
reported collectively as failed confirmations.

## 7. CONFIRM, fixed now

The `2K = 10` frozen hypotheses are tested on the untouched slice. K = 5 per tail
is fixed now and is carried **regardless of how interesting any candidate looks**.

All of the following, or it fails:

1. matched excess has the **same sign as on SELECT**
2. the thing that would actually be traded — the mirror for a loser, the
   candidate itself for a winner — has **net expectancy per trade ≥ +0.05 R**
   after every measured cost charged per trade
3. at least **50 trades** and **20 active days**
4. significance after **step-down maxT across the 10**, not a raw threshold
5. survives every cost multiplier at **1.5x**, with 3x and 7x reported
6. **a positive excess produced only by an unusually bad control does not
   qualify.** Both the excess and the candidate's own expectancy must carry the
   required sign.

## 8. HOLDOUT

The 120-day HOLDOUT is **opened only for CONFIRM survivors**, adjusted for how
many enter, and nothing — parameters, costs, exits, thresholds — may change
afterwards. Passing it grants **forward-shadow status only**, never a live order.

## 9. What is explicitly kept out

`gap_continuation/short` (watchlist W1) is **not part of this search**. It was
found unplanned, it has never had a cost test, and folding it into a grid it did
not belong to would launder an exploratory observation into a screened result. It
keeps its place on the watchlist and needs its own prospective protocol.

## 10. What failure looks like, so it cannot be argued away later

- both global statistics non-significant → **the family contains nothing beyond
  chance**, and no individual candidate may be named or pursued, whatever its t
- the power table shows the detectable effect far above plausible values →
  **the sample cannot support this search**, which is reported as the result
- a CONFIRM candidate flips sign → **the extreme of 6,480 draws**
- excess survives but net is below +0.05 R → **not tradeable**
- net dies at 1.5x cost → **a cost artefact**

Any of these is recorded as a failed search. None is a reason to add a tool,
widen the grid, raise K, move a slice boundary, relax a threshold, or reveal a
blinded name.

## 11. Addendum — second review, and the two-tier split it forces

Codex reviewed the corrected design as well, and raised two things that change it
again. Both are accepted, and both make the exercise narrower.

### 11.1 The measured power, from this project's own numbers

The standard error is not hypothetical; two earlier results give it directly:

```
breakout_into_level/short/ldn-ny   0.1848 / 1.79  =>  se ~ 0.103 R
gap_continuation/short            0.3483 / 3.18  =>  se ~ 0.110 R
```

At a maxT critical value of 4.0–4.5, 80 % power needs roughly
`(crit + 0.84) x se`:

| se | effect needed for 80 % power |
|---|---|
| 0.110 R | **0.53 – 0.59 R** |
| 0.100 R | 0.48 – 0.53 R |
| 0.050 R | 0.24 – 0.27 R |

And CONFIRM is worse, not better: 245 days against 730 inflates the standard
error by about `sqrt(730/245) = 1.73`.

**So this design can detect only very large effects.** An edge of the size this
project has been hunting — 0.05 to 0.15 R — is invisible to it at
candidate level. That is recorded here, before the run, as the honest
expectation rather than discovered afterwards as an excuse.

What the design **can** answer is the global question: does this indicator
family, as a whole, depart from the matched null. That is why the global
statistics in section 5 are the primary result and not a garnish.

### 11.2 The pairs cannot generate named candidates

No mechanistic hypothesis about any specific pair was declared before the pair
results existed. Amendment 09 tried a general one — that a stack firing on its
own components' disagreement fires where stops pile up — and it was **not
established**. Carrying a pair forward now, chosen because it came out extreme
among 6,240, would be discovery and confirmation in the same breath.

**The family therefore splits into two tiers, and the tiers have different
rights:**

| tier | what it is | may name a candidate | may reach CONFIRM |
|---|---|---|---|
| **A** | the **240 singles** — 40 tools x 3 settings x 2 directions | yes, blinded until it passes | yes, K = 5 per tail |
| **B** | the **6,240 stacked pairs** | **no, ever** | **no** |

Tier B is reported as an **anonymous global diagnostic only**: its distribution,
its quantiles, and its two permutation statistics. No pair is named, ranked into
a shortlist, or carried anywhere, whatever it returns. If tier B's global test
fires, the correct next step is a **new amendment declaring a mechanistic pair
hypothesis in advance** — not a shortlist drawn from this run.

### 11.3 Stack semantics, frozen

The reviews differed on the count because the semantics were not pinned down.
They are pinned down now:

> A stacked candidate is **anchored**. The anchor tool is the one that FIRES and
> supplies the direction; the other tool supplies only its STATE. So
> `A!B` and `B!A` are different candidates, and so are `A&B` and `B&A`.

Under that definition both modes are ordered and the count is:

```
singles       40 x 3 x 2                              =   240   (tier A)
agreement     780 pairs x 2 anchors x 2 directions    = 3,120   (tier B)
contradiction 780 pairs x 2 anchors x 2 directions    = 3,120   (tier B)
                                                    N = 6,480
```

This is larger than either review's arithmetic because both treated agreement as
symmetric. Under the anchored definition it is not, and the larger count is the
one the code actually builds.

## 12. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order has been
sent, no position is open, and no pull request is opened.
