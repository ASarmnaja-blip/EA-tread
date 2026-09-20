# Amendment 02 — re-test results

**All six re-tests pass, including the one designed to fail.**

Criterion: every path-level confidence interval must contain zero at
**family-wise 95 %**, `z = 2.9913` computed from the test count
(`core.bonferroni_z(18)`). Declared in `AMENDMENT_02_FAMILYWISE_CRITERION.md`,
committed alone as `e16a1a3`, before the code was touched or anything re-run.

All data below is **synthetic and driftless**, so the true skill of every
configuration is exactly zero.

---

## The six re-tests

| # | Test | Required | Result |
|---|---|---|---|
| R1 | C1 driftless walk, circular-shift control, 800 walks | 0 exclusions of 18 | **18/18 contain zero** |
| R2 | C2 GARCH volatility, 250 walks | 0 of 18 | **18/18** |
| R3 | C3 clustering + missing bars — *the A3b scenario* | 0 of 18 | **18/18** |
| R4 | C4 reference-anchored nulls, 400 walks | 0 of 2 | **2/2** |
| **R5** | **C1, random-entry control — the one we know is broken** | **must STILL FAIL** | **14/18 — 4 exclusions. Still fails.** |
| R6 | P1 re-run end to end under the amended code, 400 walks | 0 of 18 | **18/18, P1 PASS** |

**R5 is the one that matters.** A criterion that lets the known-bad control
through would not be a criterion, and the amendment said it would be withdrawn
if that happened. It did not: the random-entry control still shows four
intervals excluding zero, on data with no information in it.

## The two readings that used to fail

| | old mark (z = 1.96) | new mark (z = 2.9913) |
|---|---|---|
| A3b, S3V2 | +0.0134, CI **[+0.0001, +0.0266]** — excluded | +0.0134, CI **[−0.0069, +0.0336]** — contains zero |
| P1, S4V2 | +0.0113, CI **[+0.0001, +0.0225]** — excluded | +0.0113, CI **[−0.0057, +0.0284]** — contains zero |

Neither measurement changed. Only the level they are read at did, and both now
sit comfortably inside rather than marginally outside.

## Unchanged criteria, re-confirmed

| | | |
|---|---|---|
| A2 false-positive rate | 19/360 = **0.053** vs budget 0.10 | **not amended** — still evaluated at the per-test level, exactly as Amendment 01 declared |
| A5 control drop rate | median 31.2 %, max **31.9 %** vs limit 35 % | pass |
| A6 noise floor | median \|skill\| **0.0045 R**, max **0.0185 R** | reported |

A2 keeping the per-test level is deliberate. It is the second check the
amendment's cost section relies on: a drift small enough to slip past the
family-wise gate should still be visible in a budget across 360 tests.

---

## What this does not mean

**None of this is evidence that any setup has an edge in the current market,
and it may not be cited as such.**

Every number above was measured on synthetic data containing no information at
all. "P1 passes" means one thing: **the instrument does not manufacture skill
where none exists.** It says nothing about XAUUSD, nothing about now, and
nothing about any of the eighteen configurations as trading rules.

Also unchanged:

- S3, S3V1, S3V2, S5, S5V1, S5V2 and S2V1 remain **UNINTERPRETABLE** under
  Amendment 01 §1.
- Market prices stay closed. `GC=F`, `MGC=F` and `GLD` are not substitutes for
  XAUUSD and may not be used as one.
- No order has been placed and none can be: `decide.py` caps every path at
  RESEARCH WATCH and returns `tradeable=False` on all of them.

## Still the plan of record

The whole calibration is re-run on **real XAUUSD M1/M5 from the broker's MT5**
when the export lands, under this criterion. Passing on synthetic data is the
precondition for that run, not a substitute for it.
