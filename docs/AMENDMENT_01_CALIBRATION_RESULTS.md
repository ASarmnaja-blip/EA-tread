# Amendment 01 calibration — results

**Verdict: CALIBRATION FAILS on A3b. Market prices stay closed.**

Run under `AMENDMENT_01_CIRCULAR_SHIFT_CONTROL.md`, which was committed alone
(`e70891b`) before any of this was written or run. `P1_FINDINGS.md` is
unmodified.

All data below is synthetic and driftless, so the true skill of every rule is
exactly zero. Only the bar calendar and one volatility scalar come from `GC=F`,
as the amendment declared. **No real price was scored. No market result exists.**

---

## 1. Old control vs new control, same data, 800 walks

Both controls were run inside the same walk, on the same synthetic series, so
the only difference between the two columns is the control definition.

| id | random-entry skill | 95 % CI | | circular-shift skill | 95 % CI | |
|---|---|---|---|---|---|---|
| S1 | −0.0142 | [−0.0225, −0.0059] | **EXCL** | −0.0038 | [−0.0125, +0.0050] | ok |
| S1V1 | −0.0177 | [−0.0277, −0.0077] | **EXCL** | −0.0057 | [−0.0161, +0.0048] | ok |
| S1V2 | −0.0192 | [−0.0289, −0.0094] | **EXCL** | −0.0073 | [−0.0176, +0.0030] | ok |
| S2 | −0.0068 | [−0.0181, +0.0044] | ok | +0.0053 | [−0.0065, +0.0170] | ok |
| S2V1 | −0.0135 | [−0.0219, −0.0050] | **EXCL** | −0.0024 | [−0.0113, +0.0066] | ok |
| S2V2 | −0.0075 | [−0.0203, +0.0054] | ok | +0.0030 | [−0.0104, +0.0165] | ok |
| S3 | +0.0048 | [−0.0003, +0.0099] | ok | −0.0004 | [−0.0056, +0.0048] | ok |
| S3V1 | +0.0082 | [+0.0023, +0.0141] | **EXCL** | +0.0025 | [−0.0037, +0.0086] | ok |
| S3V2 | +0.0055 | [−0.0012, +0.0121] | ok | −0.0013 | [−0.0081, +0.0055] | ok |
| S4 | +0.0070 | [+0.0009, +0.0131] | **EXCL** | +0.0014 | [−0.0047, +0.0076] | ok |
| S4V1 | +0.0103 | [+0.0030, +0.0176] | **EXCL** | +0.0030 | [−0.0048, +0.0108] | ok |
| S4V2 | +0.0065 | [−0.0009, +0.0139] | ok | +0.0019 | [−0.0058, +0.0095] | ok |
| S5 | −0.0020 | [−0.0167, +0.0126] | ok | −0.0057 | [−0.0209, +0.0095] | ok |
| S5V1 | +0.0051 | [−0.0148, +0.0250] | ok | +0.0002 | [−0.0206, +0.0209] | ok |
| S5V2 | −0.0026 | [−0.0160, +0.0108] | ok | −0.0084 | [−0.0222, +0.0054] | ok |
| S6 | −0.0006 | [−0.0233, +0.0222] | ok | −0.0020 | [−0.0257, +0.0216] | ok |
| S6V1 | −0.0100 | [−0.0364, +0.0164] | ok | −0.0037 | [−0.0312, +0.0238] | ok |
| S6V2 | +0.0066 | [−0.0189, +0.0320] | ok | +0.0119 | [−0.0142, +0.0381] | ok |

| | contains zero | median \|skill\| | max \|skill\| |
|---|---|---|---|
| random-entry | **11/18** | 0.0069 | 0.0192 |
| circular-shift | **18/18** | 0.0030 | 0.0119 |

**This is what changed because of the control definition, and nothing else.**
Every bias shrank. The sweep and VWAP families that were the headline problem in
`P1_FINDINGS.md` now sit on zero: S3 moved from +0.0102 (t +3.11) to −0.0004,
and S5 from −0.0228 (t −2.26) to −0.0057.

At 800 walks the random-entry control fails on **seven** configurations, and the
set is wider than the one visible at 400 walks — the breakout and pullback
families join the sweep family once there is enough power to see them. The
mismatch was never confined to S3 and S5; those were simply the largest.

## 2. Criteria

| # | Check | Result | Verdict |
|---|---|---|---|
| A1 | C1, all 18 CIs contain zero, 800 walks | 18/18 | **PASS** |
| A2 | false positive rate, 360 independent tests, budget 0.10 | **19/360 = 0.053** | **PASS** |
| A3a | C2 GARCH volatility, 250 walks | 18/18 | **PASS** |
| A3b | C3 clustering + extra holes, 250 walks | **17/18** — S3V2 | **FAIL** |
| A4 | C4 reference-anchored nulls, 400 walks | 2/2 (N-EXT −0.0068, N-MOV +0.0030) | **PASS** |
| A5 | control drop rate | median 31.2 %, max 31.9 % (limit 35 %) | **PASS** |
| A6 | noise floor | median \|skill\| 0.0045 R, max 0.0185 R | reported |

## 3. The A3b failure, stated precisely

S3V2 on C3: **skill +0.0134, CI [+0.0001, +0.0266]**.

The lower bound clears zero by one part in ten thousand. Every other
configuration on C3 contains zero.

The honest reading is that **the criterion, not the control, is what failed
here.** A1 and A3 were written as "all 18 CIs must contain zero" at 95 %
confidence. Under a true null, a single 95 % interval misses zero 5 % of the
time, so across 18 independent configurations:

```
P(at least one exclusion) = 1 - 0.95^18 = 0.60
```

A correct instrument fails that criterion **more often than it passes it**. This
is the same defect as the `|skill| <= 0.02R` bound recorded in
`P1_FINDINGS.md` §5: a threshold written without reference to the test's own
error rate.

A2 is the statistically correct form of the same question — it budgets false
positives across many tests instead of forbidding any — and A2 **passed at
0.053**, almost exactly the 0.05 a correct instrument should produce.

**This is reported, not acted on.** Re-running C3 with a different seed until
S3V2 lands inside its interval would be seed-shopping, and rewriting A1/A3 now
would be rewriting a pass mark after seeing the result. Neither is done here.

## 4. What is now established, and what is not

### Established
- The circular-shift control removes every bias the random-entry control
  exhibited, at 800 walks, on identical data.
- Its false positive rate is 0.053 against a declared budget of 0.10.
- It holds under volatility clustering (A3a) and on reference-anchored rules of
  exactly the shape that broke the old control (A4).
- Its noise floor is median 0.0045 R, max 0.0185 R.

### Not established
- **Whether the instrument is clean under missing bars.** A3b is the one
  scenario that failed, and the failure is small enough to be indistinguishable
  from the expected false positive rate. It is unresolved either way.
- **Anything about S3, S5 or any other configuration on real data.** The earlier
  readings remain **UNINTERPRETABLE**, exactly as Amendment 01 §1 set them. The
  new control has not been pointed at a single real price.
- **Whether any setup has an edge.** No such claim is made, and none can be made
  from anything in this document.

## 5. Stop

Amendment 01 §6 step 3: *"If any of A1–A5 fails, stop and report."* A3b failed.

P1 has **not** been re-run under the new control. `GC=F`, `MGC=F` and `GLD`
prices remain closed.
