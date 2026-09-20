# Ruling on A3b — 2026-09-20

**Decision (user): A3b's single exclusion falls inside the false-positive
budget A2 declared in advance. Amendment 01 calibration is therefore PASS.**

## What was ruled on

`AMENDMENT_01_CALIBRATION_RESULTS.md` recorded:

| | |
|---|---|
| A1, A2, A3a, A4, A5 | PASS |
| A3b | 17/18 — S3V2 on the missing-bars dataset, CI [+0.0001, +0.0266] |

A1 and A3 were written as "all 18 CIs contain zero" at 95 % confidence. Across
18 configurations a true null produces at least one exclusion 60 % of the time,
so that form of the criterion fails a correct instrument more often than it
passes one. A2 asks the same question in the form that accounts for it — a
false-positive budget across many tests — and A2 returned **0.053 against a
declared budget of 0.10**, almost exactly the 0.05 a correct instrument should
produce.

The ruling reads A3b's one exclusion as one of those expected false positives.

## What this does and does not license

**Does:** the circular-shift control is calibrated. P1 may be re-run under it.

**Does not:**
- It is not evidence that S3V2 has an edge. S3V2's reading was taken on
  **synthetic data with no information in it at all**; a positive number there
  is noise by construction.
- It does not revive any earlier reading. S3, S3V1, S3V2, S5, S5V1, S5V2 and
  S2V1 remain **UNINTERPRETABLE** under Amendment 01 §1.
- It does not open market prices. `GC=F`, `MGC=F` and `GLD` stay closed for
  evaluation.

## Standing caveat

The ruling is a judgement about a borderline interval, not a measurement. The
plan of record is unchanged: **the whole calibration is re-run on real XAUUSD
once the export lands**, including the A3b scenario. If A3b fails there too,
that is a real instrument problem and this ruling will have been the wrong
call — which is the point of writing it down rather than quietly proceeding.
