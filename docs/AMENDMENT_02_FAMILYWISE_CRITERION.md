# Protocol Amendment 02 — family-wise confidence for the 18-configuration gate

**Declared before the code was changed and before anything was re-run.
Committed alone, separately from every result it will be judged against.**

Amends: `PILOT_PREREGISTRATION.md` §7 (P1), `AMENDMENT_01_...` §5 criteria A1
and A3.
Does not amend: A2 (the false-positive budget), A4, A5, A6, the control
definition, the cost model, the eighteen configurations, or the target
instrument.

`P1_FINDINGS.md`, `AMENDMENT_01_CALIBRATION_RESULTS.md`, `P1_RERUN_AMENDMENT01.md`
and `AMENDMENT_01_RULING.md` are **not modified**.

---

## 1. The change

A1, A3 and P1 keep the form "**every one of the 18 path-level confidence
intervals must contain zero**". Only the confidence level changes:

| | before | after |
|---|---|---|
| per-test alpha | 0.05 | **0.05 / 18 = 0.002778** |
| two-sided z | 1.96 | **2.9913** |
| what 95 % refers to | one interval | **all eighteen together** |

`z` is computed from the test count at runtime (`core.bonferroni_z`), not
hardcoded, so it follows the registry rather than going stale if its size
changes. At 18 tests the realised family-wise rate is `1 − (1 − 0.002778)^18 =
4.88 %`.

## 2. Why

"All eighteen must hold" is a statement about the family. It was being checked
with a per-test level, which is a different statement. Under a true null:

```
P(at least one of 18 exclusions at 95% per test) = 0.603
```

A correct instrument fails that 60 % of the time, and it has now done so twice,
naming a different configuration each run — S3V2 on A3b clearing zero by
0.0001 R, S4V2 on the P1 re-run by 0.000128 R. A gate whose culprit changes
every run is reporting its own error rate.

This amendment does not loosen the intent. It supplies the arithmetic the
sentence was always missing.

## 3. The cost of the change, stated plainly

**Sensitivity to small real biases falls.** At 400 walks a typical path-level
standard error in this work is 0.004–0.02 R. A genuine bias near **0.01 R**
that the old mark would have caught can now pass unflagged.

That is a real loss and it is accepted for a specific reason: a gate that fires
on 60 % of correct instruments carries no information, so its apparent
sensitivity was never usable. Two things limit the exposure:

- **A2 is unchanged** and runs alongside. It budgets false positives across 360
  independent tests at the per-test level, and it caught the old control at
  0.053 vs a 0.10 budget. A drift small enough to slip past the family-wise
  gate is still visible there.
- A single **large** bias still fails: one interval at z = 4 excludes zero at
  2.99 just as it did at 1.96. What is given up is the tail of small effects,
  not the ability to see a broken control.

## 4. What must be re-tested before this counts as passed

Every control already measured, under the new level, and P1 re-run with the
amended code:

| # | must show |
|---|---|
| R1 | C1, circular-shift control — 0 exclusions of 18 |
| R2 | C2 GARCH volatility — 0 of 18 |
| R3 | C3 missing bars (the A3b scenario) — 0 of 18 |
| R4 | C4 reference-anchored nulls — 0 of 2 |
| R5 | **C1, random-entry control — must STILL FAIL.** A criterion that passes the control we know is broken is not a criterion |
| R6 | P1 re-run end to end under the amended code — 0 of 18 |

R5 is the one that matters. If the change makes the known-bad control pass, the
amendment is wrong and is withdrawn.

## 5. What this is explicitly not

**This amendment is about the measuring instrument. It is not evidence that any
setup has an edge in the current market, and it may not be cited as such.**

Every configuration's reading was taken on **synthetic data containing no
information at all**. "Passes P1" means the tool does not manufacture skill
where none exists. It says nothing about XAUUSD, nothing about now, and nothing
about any setup.

S3, S3V1, S3V2, S5, S5V1, S5V2 and S2V1 remain **UNINTERPRETABLE** under
Amendment 01 §1. Market prices stay closed. No order is placed.

## 6. Still the plan of record

The whole calibration is re-run on **real XAUUSD M1/M5 from the broker's MT5**
when the export lands — including the A3b scenario. A criterion chosen now is
the criterion for that run too.
