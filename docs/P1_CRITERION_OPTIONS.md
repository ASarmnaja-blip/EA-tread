# The P1 pass mark — three options, with what each one does

**Nothing is changed here. This is the proposal the user asked for.**

## The problem, in one line

"Every one of 18 confidence intervals must contain zero" asks eighteen 95 %
intervals to agree, and a 95 % interval misses 5 % of the time.

```
n = 18 independent 95% intervals, true null
  P(at least 1 exclusion) = 0.603     <- the modal outcome
  P(at least 2)           = 0.227
  P(at least 3)           = 0.058
  P(at least 4)           = 0.011
```

A correct instrument fails this mark **60 % of the time**. It has now done so
twice, naming a different configuration each run — S3V2 on A3b, S4V2 on the P1
re-run, clearing zero by 0.0001 R and 0.000128 R. A gate that picks a different
culprit every time is reporting its own error rate.

## What the candidates do to the four datasets already measured

Exclusion counts out of 18. The random-entry control is the one we **know** is
broken; the circular-shift control is the one under test.

| dataset / control | at 95 % | at family-wise 95 % (z = 2.99) |
|---|---|---|
| C1, **random-entry control (known bad)** | **7** | **4** |
| C1, circular-shift control | 0 | 0 |
| C2 GARCH volatility, shift | 0 | 0 |
| C3 missing bars, shift — *this is A3b* | 1 | **0** |
| P1 re-run, shift, 400 walks | 1 | **0** |

Both proposed fixes keep the separation that matters: the broken control still
fails loudly, the good one passes cleanly.

---

## Option A — rule case by case, as with A3b

Keep the mark; override it whenever a single exclusion appears.

**For:** nothing changes, no criterion is rewritten, each call is on the record.

**Against:** the next dataset has a 60 % chance of needing the same ruling. A
gate that is routinely overridden stops being a gate — from outside it is
indistinguishable from not having one. It also puts the decision after the
result every time, which is the shape of reasoning a pre-registration exists to
prevent, even when each individual call is correct.

**Effect now:** P1 passes.

---

## Option B — a false-positive budget, the form A2 already uses

Declare in advance: **fail if 4 or more of the 18 intervals exclude zero.**

`P(4 or more | true null) = 0.011`, so a correct instrument is wrongly failed
about once in ninety runs.

**For:** it is the same logic A2 already passed under (0.053 against a budget of
0.10), so the amendment would be internally consistent rather than using two
different standards for the same question. It discriminates: the bad control's
7 fails, the good control's 0–1 passes.

**Against:** a threshold on a count is coarse. Three large exclusions and three
marginal ones score identically, and it tolerates up to three real biases
without complaint.

**Effect now:** A3b passes (1), P1 passes (1).

---

## Option C — keep the form, fix the confidence level *(recommended)*

Keep "all 18 intervals must contain zero" and set the level so that **95 % is
the family-wise figure**, not the per-test one: `z = 2.99` instead of `1.96`
(Bonferroni over 18 tests, per-test alpha 0.00278).

**For:** this is what "all eighteen must hold" was always trying to say. The
intent does not change, only the arithmetic that was missing from it. It is the
sharpest of the three on the evidence: **0 exclusions on every dataset for the
good control, including both scenarios that failed under the old mark, and 4
for the control we know is broken.** Unlike Option B it stays sensitive to a
single *large* bias — one interval at z = 4 still fails it.

**Against:** it raises the bar for detecting small real biases, so a genuine
0.01 R mismatch could slip through where the 95 % mark would have caught it.
That is the price of not crying wolf 60 % of the time, and A2's budget still
runs alongside as a second check.

**Effect now:** A3b passes (0), P1 passes (0) — cleanly, not marginally.

---

## What none of them change

Whichever is chosen, it applies to **A1, A3 and P1 together** and is declared
before the affected runs are re-read. It says nothing about any setup having an
edge. S3, S5 and the rest stay **UNINTERPRETABLE**. Market prices stay closed.

And the plan of record is unchanged: **the whole calibration is redone on real
XAUUSD when the export lands.** A criterion chosen now is a criterion for that
run too.
