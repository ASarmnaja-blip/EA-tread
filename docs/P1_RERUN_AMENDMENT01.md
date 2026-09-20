# P1 re-run under Amendment 01 — result

**P1 FAILS, 17/18. No market price was read; `--p1-only` stops the runner
before the market stage.**

Circular-shift control, 400 walks, driftless random walk on the real bar
calendar. Path-level standard error throughout.

| | |
|---|---|
| t arm, \|t\| < 2 | **18/18 pass** (largest \|t\| = 1.97) |
| CI contains zero | **17/18** |
| the exception | **S4V2**, skill **+0.0113**, CI **[+0.000128, +0.022472]** |

S4V2's interval clears zero by **0.000128 R**.

## This is the same failure as A3b, not a new one

| | A3b (calibration) | P1 (this run) |
|---|---|---|
| configurations | 18 | 18 |
| intervals excluding zero | 1 | 1 |
| which | S3V2 | S4V2 |
| lower bound | +0.0001 | +0.000128 |

Both are the criterion "every one of 18 CIs contains zero" meeting the fact
that a 95 % interval misses 5 % of the time:

```
P(at least one of 18 excludes zero | true null) = 0.603
expected number of exclusions                   = 0.90
observed                                        = 1
```

**One exclusion is the single most likely outcome for a perfectly calibrated
instrument.** The criterion fails a correct instrument 60 % of the time, and it
has now done so twice on two independent datasets, naming a different
configuration each time. A criterion that picks a different "failure" each run
is not detecting anything about the instrument.

The user's ruling of 2026-09-20 reads exactly this pattern, on A3b, as one of
the false positives A2 budgets for. That ruling was about A3b specifically, so
it is **not** applied here on its own.

## What is and is not in doubt

**Not in doubt:** the control itself. Across the calibration and this run the
circular-shift control produced, on data with no information in it:

- median \|skill\| 0.0030–0.0045 R, max 0.0119 R (A1, 800 walks)
- a false positive rate of **0.053** against a budget of 0.10, over 360 tests
- 18/18 on GARCH volatility, 2/2 on reference-anchored nulls
- 18/18 on the t arm here, largest \|t\| 1.97

**In doubt:** nothing about the instrument that this run shows. What it shows
is that the pass mark is written in a form that cannot be met reliably.

## Options

1. **Extend the A3b ruling to P1** — one exclusion of eighteen sits inside the
   declared budget, so P1 passes.
2. **Amend the criterion once**, for A1, A3 and P1 together, to the
   false-positive form A2 already uses, and stop ruling case by case. The
   threshold would be declared before the re-run, as A2's was.
3. **Stop.**

Option 2 is the one that does not need a ruling again next time. It is a
criterion change and needs sign-off either way.

## Not changed by this

`GC=F`, `MGC=F` and `GLD` remain closed for evaluation. S3, S5 and the rest of
the earlier readings remain **UNINTERPRETABLE**. No setup is claimed to have an
edge, and nothing here is a trade signal.
