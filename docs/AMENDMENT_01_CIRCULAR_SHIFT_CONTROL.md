# Protocol Amendment 01 — Circular time-shift control

**Status: declared before any code was changed and before any calibration was
run. Committed separately from every result it will be judged against.**

Amends: `PILOT_PREREGISTRATION.md` §6 (matched random control) and §7 (P1 pass
criterion).
Does not amend: `ENGINE_PROTOCOL.md` Tier A, the cost model, the eighteen
registered configurations, or anything about the target instrument.

`P1_FINDINGS.md` is **not modified by this amendment**. It records what the
random-entry control measured, and it stays exactly as written.

---

## 1. Status of the earlier P1 results

| Result | New status |
|---|---|
| The pooled-vs-path standard error defect, and its fix | **STANDS.** A real defect, found and corrected. Not affected by this amendment |
| The known-answer harness null (target rate 33.19 % vs 33.33 % theory) | **STANDS.** The exit engine is validated independently of the control |
| The four rejected hypotheses (time stop, intrabar ambiguity, ATR matching, feasibility filter) | **STANDS.** All four were tested and none explained the residual |
| The residual skill on **S3, S3V1, S3V2, S5, S5V1, S5V2, S2V1** | **UNINTERPRETABLE** |
| The other eleven configurations reading "consistent with zero" | **PROVISIONAL.** A control that cannot bound S3 and S5 cannot certify the others either |

**UNINTERPRETABLE means exactly that: not PASS, not FAIL.** The measurement was
taken with an instrument now known to be unsuitable for those rules, so the
numbers say nothing about whether S3 or S5 carry information. They are not
evidence of an edge and they are not evidence against one.

**No claim that S3 or S5 has an edge is made anywhere, and none may be made
from any figure in `P1_FINDINGS.md`.**

## 2. Why the random-entry control cannot serve these rules

The pre-registered control re-enters at a **random time** in the same session.
That breaks two things the setups depend on.

### 2.1 Temporal clustering is destroyed

Real signals arrive in bursts. A breakout rule fires repeatedly while a range
is being resolved and then goes quiet for days; a sweep rule fires around the
same liquidity pocket several times in an hour. Trades inside a burst overlap
in time and share one price path, so their outcomes are correlated and their
pooled variance is far from `sd²/n`.

A uniform random control spreads its entries evenly and therefore has **less
within-arm dependence than the setup arm**. The two arms then differ in their
variance structure before any question of skill arises, and the difference of
their means inherits that mismatch.

### 2.2 Reference alignment is destroyed

This is the decisive one, and it is specific to S3 and S5.

- **S3 (liquidity sweep)** fires only when price has pierced a 20-bar extreme
  and closed back. By construction the entry sits at a known distance from a
  known recent extreme.
- **S5 (VWAP reversion)** fires only when price is at least 2 session sigma from
  session VWAP, and its **target is VWAP itself** — a reference that keeps
  moving, and that moves *toward* price mechanically, because VWAP is an
  average that the incoming prices are added to.

A random bar is, on average, at a typical distance from those references, not
an extreme one. So the control starts from a different part of the
price-versus-reference distribution. Matching the barrier ratio does not fix
this: on a driftless walk the *first-passage probability* depends only on the
barrier ratio, but the *distance-to-a-moving-target* dynamics do not. For S5 the
target's own drift toward price is a function of how far price is from it, so a
control entered near VWAP faces a target that behaves differently from one
entered 2 sigma away, even with nothing predictive in the price series.

That is the mechanism behind the residual: **+0.010R to +0.013R on the sweep
family and −0.023R to −0.039R on the VWAP family, measured on data that
contains no information at all.**

## 3. The replacement control

### 3.1 Definition

For each configuration, take its own signal timestamps. Shift **all of them
together** by a single whole-day offset and wrap circularly within the data
span:

```
t' = t_first + ( (t - t_first + k * 86400) mod (SPAN_DAYS * 86400) )
```

The shifted signal is used only if a 15m bar exists at exactly `t'`. Direction,
stop distance in ATR units, and target as an R multiple are carried over from
the original signal and re-expressed at the shifted bar's own ATR and price.
Exit logic is identical to the setup arm.

### 3.2 What it preserves and what it breaks

| Preserved | Broken |
|---|---|
| signal count | alignment between the signal and the price configuration that triggered it |
| direction mix | the rule's reference relationship (extreme, VWAP band) |
| **inter-signal spacing — clustering is carried across intact** | |
| **time of day, therefore session mix, exactly** | |
| the setup's own distribution of stop sizes and target multiples | |

Shifting by **whole days** is what preserves time-of-day, and therefore session
and the intraday volatility profile, which a bar-index shift would scramble.

### 3.3 Parameters, fixed here in advance

| Parameter | Value | Reason |
|---|---|---|
| offset `k` | uniform over `{±5, ±6, …, ±40}` days | see below |
| **minimum \|k\|** | **5 days** | the longest lookback in any configuration is the 200-bar ATR percentile window, about 50 hours of trading. Five days clears it with margin, so no residual alignment survives |
| maximum \|k\| | 40 days | the span is ~68 days; beyond this the wrap starts returning to the neighbourhood of the original time |
| shifts per configuration | **20** | matches the 20 draws the random-entry control used, so the two are compared at equal control sample size |
| applied | **the same rule to all 18 configurations**, no per-setup tuning | |
| bars missing at `t'` | the shifted signal is **dropped**, and the drop rate is reported | weekends and the CME break leave holes that no shift can fill |

`k = 0` and every `|k| < 5` are excluded by construction.

## 4. Calibration required before P1 may be re-run

The new control must be calibrated on four families of data where the true
answer is known to be zero.

| # | Dataset | Why |
|---|---|---|
| **C1** | driftless random walk on the real bar calendar | the baseline null |
| **C2** | driftless walk **with volatility clustering** (GARCH-like) | real volatility is not constant, and a control that only works at constant vol is not calibrated |
| **C3** | C2 plus **additional synthetic missing bars** beyond the real calendar's own gaps | the shift drops signals when a bar is absent; that must not create a bias |
| **C4** | a **reference-level null**: a rule shaped like S3/S5 — fires at a rolling extreme, targets a moving average — run on no-edge data | the failure being fixed is specific to reference-anchored rules, so the fix must be tested on one |

### 4.1 An explicitly declared data exception

C1–C4 need the **real bar calendar**: the timestamps, the weekend holes and the
CME maintenance break, plus **one scalar**, the 5-minute return standard
deviation, to set the synthetic volatility scale.

Reading that calendar and that one number is reading `GC=F`. It is declared
here rather than done quietly. **No setup is evaluated on real prices, no real
price series is scored, and no market result is produced.** If the user objects
to this exception, the calibration must instead use a wholly synthetic calendar,
which weakens C3.

## 5. Pass/fail criteria, fixed here in advance

| # | Criterion | Threshold |
|---|---|---|
| **A1** | On C1, every one of the 18 configurations has a path-level 95 % CI of skill that **contains zero** | 18/18 |
| **A2** | **False positive rate.** 20 independent universes × 18 configurations = 360 tests, each CI built from 40 walks. Fraction of 95 % CIs excluding zero | **≤ 0.10** |
| **A3** | A1 repeated on C2 and on C3 | 18/18 each |
| **A4** | On C4, the reference-level null's CI contains zero | pass |
| **A5** | Control drop rate from missing shifted bars, per configuration | **< 35 %** |
| **A6** | Noise floor reported: median and maximum \|skill\| over all known-zero tests | reported, not thresholded |

The absolute `|skill| ≤ 0.02R` bound from the pre-registration is **replaced**
by A1: an interval that contains zero, at the test's own resolution. The reason
is on the record in `P1_FINDINGS.md` §5 — a null with exactly zero skill lands
at 0.0245R at ten walks, so the old bound was below the noise floor of its own
test. The replacement is declared here, before the new control has been run
even once.

**Path-level standard error and the overlapping-trade correction are retained.
Pooled trade-level standard error is not permitted anywhere.**

## 6. Order of operations

1. Commit this amendment. *(separate from every result)*
2. Implement the circular-shift control.
3. Run C1–C4 and A1–A6. **If any of A1–A5 fails, stop and report.**
4. Only then re-run P1 on the random walk with the new control.
5. **If the new P1 fails, stop again. Market data stays closed.**

`GC=F`, `MGC=F` and `GLD` prices remain closed for evaluation until P1 passes
under this amendment and the user gives a separate approval.
