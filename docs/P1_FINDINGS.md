# P1 calibration: what failed, what was fixed, what is still open

**No market data has been read.** The runner stopped itself at P1, as
pre-registered. `research/pilot/results/` contains no market result.

Everything below is measured on driftless random walks built on the real
timestamps of COMEX gold futures, so session structure, gaps and volume match
while the prices carry no information at all.

---

## 1. One real defect, found and fixed: the standard error

Skill was being measured with a standard error computed from pooled trades as
if they were independent. Trades that overlap in time share one price path, so
they are not. Ten independent walks give an honest standard error, and it is
**1.12x to 3.38x larger** (median 1.62x) than the pooled one.

| id | skill | se pooled | t pooled | se path | t path |
|---|---|---|---|---|---|
| S2V2 | −0.1107 | 0.0235 | **−4.71** | 0.0604 | −1.78 |
| S2V1 | −0.0651 | 0.0169 | **−3.85** | 0.0572 | −1.16 |
| S4V1 | +0.0560 | 0.0237 | **+2.36** | 0.0388 | +1.54 |
| S1V1 | −0.0692 | 0.0298 | **−2.32** | 0.0496 | −1.56 |

Every t over 2 in the first P1 run was an artefact of the wrong error term.
After the fix, **18/18 clear the t arm** at ten walks.

This is the error `RESEARCH_FINDINGS.md` already warns about: *"circular-shift
nulls for condition sweeps, because trades close in time share price paths and
a naive shuffle manufactures significance — one p-value moved from 0.0075 to
0.31 when this was fixed."* It was reintroduced and has now been removed again.

## 2. Three hypotheses tested and rejected

| hypothesis | test | result |
|---|---|---|
| the time stop truncates asymmetrically | removed it entirely | bias got **worse**, not better |
| intrabar ambiguity (one bar holding both stop and target) | counted them | **0.00 %** of exits |
| control under-matched on volatility | matched on ATR decile as well as session | **no change** |
| setup arm filtered by feasibility checks the control never faces | built controls from the accepted subset only | **no change** (7/18 before, 7/18 after) |

## 3. The exit engine itself is sound

A null whose answer is known exactly — enter every 7th bar, alternating
direction, fixed barriers — must return `P(target first) = 1/(1+R)` and `E = 0`
on a driftless walk, because first passage depends only on the ratio of the
barrier distances.

| R | time stop | n | target % | theory % | E gross | t |
|---|---|---|---|---|---|---|
| 2.0 | 72 bars | 6,010 | 29.32 | 33.33 | +0.0026 | 0.18 |
| 2.0 | none | 6,010 | **33.19** | **33.33** | −0.0005 | −0.04 |
| 3.0 | 72 bars | 6,010 | 15.69 | 25.00 | +0.0176 | 1.00 |
| 3.0 | none | 6,010 | **25.06** | **25.00** | +0.0091 | 0.32 |

`resolve()` and `run_signals()` are correct. The time stop truncates trades
that would still have resolved; it does not bias their direction.

## 4. What is still failing, and why it is not a bug in the code

At 400 walks the noise collapses and a **small, real, systematic** difference
between seven configurations and their matched random control survives:

| id | skill | se | t | 95 % CI |
|---|---|---|---|---|
| S3 | **+0.0102** | 0.0033 | +3.11 | [+0.0038, +0.0167] |
| S3V1 | **+0.0111** | 0.0039 | +2.86 | [+0.0035, +0.0188] |
| S3V2 | **+0.0130** | 0.0047 | +2.78 | [+0.0038, +0.0221] |
| S2V1 | **−0.0172** | 0.0065 | −2.63 | [−0.0300, −0.0044] |
| S5 | **−0.0228** | 0.0101 | −2.26 | [−0.0426, −0.0030] |
| S5V1 | **−0.0385** | 0.0139 | −2.77 | [−0.0659, −0.0112] |
| S5V2 | **−0.0239** | 0.0097 | −2.47 | [−0.0430, −0.0049] |

The other eleven are consistent with zero.

These are **properties of the pre-registered control**, not of the exit engine.
A control that re-enters at a *random time* cannot match a rule that conditions
on where price sits relative to a moving reference — a sweep of a 20-bar
extreme (S3) or a 2-sigma displacement from session VWAP (S5). The random
control samples a different part of the path distribution, and on a long enough
run that difference shows up as skill even when nothing predictive exists.

The magnitudes are small (0.010R to 0.039R) but they are the same order as any
edge this pilot could plausibly detect, so they cannot be waved through.

## 5. The other arm of the criterion is below the test's own resolution

The pre-registration asks for `|skill| <= 0.02R`. A null whose true skill is
**exactly zero** lands at `|skill|` up to **0.0245R** at ten walks:

| null variant | skill | se path | t |
|---|---|---|---|
| every 7th bar | −0.0245 | 0.0164 | −1.50 |
| every 11th bar | +0.0125 | 0.0225 | +0.56 |
| every 7th, 3R target | −0.0132 | 0.0176 | −0.75 |
| every 5th, 1.0 ATR stop | −0.0017 | 0.0107 | −0.16 |

At ten walks no instrument can pass that arm, correct or not. At 400 walks the
bound becomes reachable — 15 of 18 configurations now sit inside ±0.02R — but
the t arm then starts detecting the small real biases in section 4.

The criterion is therefore sample-size dependent in opposite directions: more
walks make the magnitude arm easier and the t arm harder. That is a flaw in how
the criterion was written, and rewriting a pass mark after seeing results is
the single thing a pre-registration exists to prevent. **It stands unchanged
until the user rules on it.**

## 6. Verdict

**P1 FAILS.** No market data has been read.

Three ways forward, none of them taken without approval:

1. **Change the control to a circular time shift.** The setups' own signal
   times are shifted by a random offset and wrapped, which preserves the rule's
   timing structure and clustering while destroying its alignment with price.
   This is the method `RESEARCH_FINDINGS.md` already recommends for exactly
   this situation, and it addresses section 4 directly. It changes the
   pre-registered control definition ("random entry bars"), so it needs
   sign-off.
2. **Amend the criterion** to something the test can resolve — a path-level CI
   containing zero, with the measured noise floor reported beside it. This
   changes a pass mark after seeing results and is the weakest of the three.
3. **Stop.** The pilot ends here with the instrument documented and no market
   result claimed.
