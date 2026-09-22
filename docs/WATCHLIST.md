# Watchlist — observations that are alive but unproven

A finding lands here when it survived something real but has **not** passed a
pre-registered test. Nothing on this list may be traded, promoted, or tuned. The
list exists so that a lead is not lost in a commit message, and so that the
reason it is not yet a candidate stays attached to it.

**Rules for this file.** An entry is added with its numbers and its defects at
the moment it is found. An entry is never edited to look better. It leaves this
list in one of two ways: it passes its own pre-registered amendment on data that
did not exist when it was written, or it is recorded as dead. Re-running the same
data with a different knob is neither.

---

## W1 — `gap_continuation/short` beats its matched control

**Found** 2026-09-22, in the Amendment 08 section 4 re-score.

```
n = 75 (2023-2026, development period, 11 entries unmatched and excluded)
own gross           +0.2934 R
matched control     -0.0549 R
excess              +0.3483 R
t                   +3.18
p(maxT), 22 candidates, both tails    0.0330
maxT critical value                   3.052
```

**What it is.** Shorting into a down-gap of at least 0.5 ATR, at RR 1:1 with a
1.5 ATR stop and a 72-bar time stop. It beat a placebo matched on direction,
calendar quarter, session, ATR tercile, news proximity and spread bucket by
+0.35 R per trade, in a market that rose 126 % over the sample. It was also the
largest raw number in Amendment 07's table (+0.3027) and went unremarked there
because that search was looking for losers.

It is the only |t| in that family of 22 above the family-wise critical value,
and it is on the winning tail.

**Why it is not a candidate.**

1. **The run was pre-registered as exploratory.** Amendment 08 section 6.4
   states in advance that it cannot establish an edge on this sample, whatever
   it returned, because the decision to score on excess was made after the raw
   outcome had been seen.
2. **Program-level multiplicity.** `p(maxT) = 0.033` corrects for the 22
   candidates in that family. It does not correct for this being the second
   statistic computed on the same 24 after the first was seen.
3. **No cost test has ever been run on it.** The excess cancels cost by
   construction, because the placebo pays it too. Whether the trade survives a
   round turn of 0.042 R is unknown.
4. **n = 75 over three years**, about 25 a year. That is the same rarity wall
   `ORDERLY_TREND` hit, which needs 2.6 to 4.3 years to accumulate a forward
   sample.
5. Gold gaps cluster at the weekly open and around session handoffs, so the 75
   are unlikely to be 75 independent observations.

**What would move it off this list.** Its own amendment, fixing in advance: the
gap definition and threshold, the geometry, the cost charged per trade, an
untouched slice, and a required number of forward events. Until then it is an
observation.

---

## W2 — two junk configurations kept their sign on the untouched slice

**Found** 2026-09-22, in the Amendment 09 search.

```
rsi:40/short       SELECT excess -0.2278   CONFIRM excess -0.0937
                   mirror net +0.1838 R, alive at 7x cost (+0.0942)
                   FAILED: n=33 against a required 50, |t|=1.23 against 2.576

emax:50-200/long   SELECT excess -0.1345   CONFIRM excess -0.1867
                   mirror net +0.1424 R, alive at 7x cost (+0.0370)
                   FAILED: n=47 against a required 50, |t|=1.01 against 2.576
```

**Why they are not candidates.** They failed pre-registered criteria. Both sit
just under the trade-count line, which is exactly the situation Amendment 09
section 8 was written for: lowering the threshold now would let the result write
the rule. Two of the other three carried forward flipped sign outright on the
same slice, which is what the minimum of 139 draws does on fresh data, and there
is no reason to assume these two are different in kind rather than in luck.

The plausible mechanism for both is **horizon mismatch** — a 40-period RSI and a
200-period EMA speak to moves longer than a 72-bar time stop can hold — and
horizon mismatch is a reason to lose that does not invert.

**What would move them off this list.** Forward data. Not a longer CONFIRM
window, not a lower trade-count threshold, and not a different time stop.

---

## Disclosure note, 2026-09-22

The operator asked for the names behind the Amendment 10 blinded shortlist. They
were given. The blinding rule in Amendment 10 section 6 is a discipline on the
RESEARCH PROCESS - it stops a shortlist drawn from 6,480 configurations from
becoming a candidate list - and it was never secrecy from the operator, who owns
the work. The names travel with their failures attached, and none of the ten is a
candidate.

For the record, the five winning-tail IDs all flipped sign on CONFIRM:

```
W1 ultosc:14/long      SELECT +0.1568  ->  CONFIRM -0.0112
W2 stochrsi:5/short    SELECT +0.0334  ->  CONFIRM -0.0124
W3 force:50/short      SELECT +0.0695  ->  CONFIRM -0.0377
W4 rvi:10/short        SELECT +0.0325  ->  CONFIRM -0.0182
W5 crsi:30/short       SELECT +0.0720  ->  CONFIRM -0.1223
```

and the losing-tail IDs were `L1 rsi:40/short`, `L2 mass:60/long`,
`L3 emax:50-200/long`, `L4 wpr:7/long`, `L5 chaikvol:40/short`. L1 and L3 are the
two already recorded above as W2 on this list.

## Correction to W2, added 2026-09-22

The mirror net figures quoted for W2 are **not** drift-adjusted. Only the matched
excess is. Set against the measured random-entry baselines at the same geometry
(random long +0.0656 R, random short -0.0507 R):

- `rsi:40/short` mirrors into a **long**, so its +0.1838 R contains roughly
  +0.07 R of drift.
- `emax:50-200/long` mirrors into a **short**, so its +0.1424 R sits about
  +0.19 R above what a random short earned. On this adjustment it is the
  stronger of the two.

This does not change their status. Both still fail on trade count and on
step-down maxT p values of 0.961 and 0.899, which means the data is fully
compatible with there being nothing there.
