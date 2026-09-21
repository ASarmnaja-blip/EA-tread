# Protocol Amendment 08 — the measured cost model, and a direction-neutral re-score

**Written 2026-09-22. Committed alone, before either run it describes produces a
number.** Both changes are being made AFTER results were seen, which is the
most dangerous moment in this process, so both are written down first with their
expected outcomes stated.

Amends: the cost model used by every evaluation in `research/pilot`.
Re-opens: Amendment 06's cross-asset replication and Amendment 07's inverse
search, as **corrected re-runs**, with the original verdicts preserved.

Does not amend: `ORDERLY_TREND` as frozen by Amendment 05, the geometry of any
tool, Amendment 04's one-champion rule, the prohibition on real-money orders, or
the prohibition on Grid and Martingale.

---

## 1. Why a correction is legitimate here, and where the line is

Two defects were found after Amendment 06's and 07's results were read. The
distinction that matters:

- **changing a threshold, a window or a rule after seeing a result is tuning**,
  and it is forbidden. Nothing of that kind is done here.
- **charging a cost that exists and was never charged is a bug fix.** Refusing
  to fix it would not be discipline, it would be preserving a known error.

The protection against a bug fix becoming a tuning opportunity is this
amendment: the corrected model is fixed now, in full, before it runs, and **the
original verdicts stay on the record unchanged.** A corrected run that comes
back better does not retroactively pass anything.

## 2. The cost model, measured and fixed now

All figures measured on the account in use (Exness-MT5Trial7, demo,
`trade_mode=0`, USD) on 2026-09-21 and 2026-09-22, by
`tools/demo_slippage_probe.py` (fills and commission, from closed deals),
`tools/measure_spreads.py` (live spread sampling) and
`tools/build_cost_model.py` (unit conversion via `order_calc_profit`).

| symbol | spread | commission, round turn | swap long / night | swap short / night |
|---|---|---|---|---|
| XAUUSD | 0.09000 | **0.14000** | −0.549300 | 0 |
| XAGUSD | 0.01700 | **0.00140** | −0.008300 | 0 |
| EURUSD | 0.00000 | **0.00005** | −0.000058 | 0 |
| GBPUSD | 0.00001 | **0.00005** | −0.000021 | −0.000006 |
| USDJPY | 0.00000 | **0.00787** | 0 | 0 |
| US500 | 0.03000 | **0.26200** | −1.493000 | 0 |

All in each symbol's own price units. Slippage stays at the measured floor of
0.0165 per fill on XAUUSD, carried to other symbols as the same fraction of
their own ATR, unchanged from Amendment 06.

### Three things this table fixes

1. **Commission had never been charged anywhere in this repository.** On
   XAUUSD it is 0.140 per ounce per round turn against a demo spread of 0.052 —
   2.7 times larger than the cost the code did charge.
2. **A zero-spread account is not a zero-cost account.** EURUSD and USDJPY
   quote at spread 0 on this account. The earlier code filtered those bars out
   as though zero were missing data and took the median of the surviving
   widest few percent, which is what classified 99 % of EURUSD's bars
   `TOO_EXPENSIVE` and produced zero signals. The zeros are real; the cost is
   the commission.
3. **Swap is now measured for all six**, read-only from `symbol_info`, so the
   NOT MEASURED caveat in Amendment 06's run is removed rather than papered
   over. It never needed to be transferred across instruments.

### What does NOT change

The multiplier grid stays **1x / 1.5x / 3x / 7x**. These are demo figures and
the live account differs; on XAUUSD the live Standard spread of 0.260 against
the demo's 0.037 is a ratio near seven. The grid is the honest bound and it is
not narrowed because the 1x figure is now better measured.

## 3. The corrected cross-asset replication

Amendment 06's seven pass criteria are **unchanged** and are not renegotiated.
The re-run changes only the cost charged and the spread estimate.

**Stated before running:** EURUSD's cost/ATR at the corrected model is
0.00005 / 0.00055 = **0.091**, which is still above the 0.08 gate. So EURUSD is
expected to produce few or no signals even after the fix, and that will now be
a **genuine economic fact about trading EURUSD on M15 at this account's cost**
rather than an artefact. If it still returns zero, criterion 2 ("positive on at
least 4 of 6") remains unreachable and the replication remains failed.

That is written here so the corrected run cannot be presented as a rescue.

## 4. The direction-neutral re-score of the inverse search

`research/pilot/drift_audit.py` measured what a random entry earns at the
search's own RR 1:1 geometry over the same period:

```
random LONG   n=1488   gross +0.0656
random SHORT  n=1477   gross -0.0507
long-minus-short gap from randomness alone: +0.1163 R
```

That gap is **larger than every family's own long-minus-short gap** (0.0566 to
0.0982), so drift accounts for 118–206 % of what the search found. The patterns
separate long from short *less* than chance does.

The remaining question is whether any pattern loses more than **a random trade
in the same direction**. That is the only version of the operator's idea that
survives on a trending instrument, and it is tested as follows.

### Construction, fixed now

**Excess over a direction-matched control.** Each candidate is scored as its own
gross minus the gross of random entries of the **same direction**, over the
**same index range**, with the **same geometry and the same worst-case
resolution**, so the drift is present in the control and cancels.

A direction-matched control is chosen over regressing out a linear drift term
because the outcome here is path-dependent — a stop, a target and a time stop —
and a linear adjustment does not respect that path. The control does, because it
is the same machinery.

### Multiplicity, fixed now

The excess is a **second statistic on the same 24 candidates, chosen after the
first was seen.** The honest accounting is therefore **N = 48**, not 24, and the
family-wise z rises accordingly. Reusing N = 24 would be claiming the second
look was free.

### Pass criteria, unchanged in substance

Amendment 07 section 7 applies as written, with `g` read as the **excess**:
excess ≤ −0.092 R, family-wise significance at N = 48, ambiguity below 15 %,
sign stable on M1, not concentrated in one quarter or session, circular-shift
control clean, inverted net alive at 1.5x, mechanism stated in advance.

### The prediction, recorded before the run

**No candidate is expected to reach −0.092 R in excess terms.** The largest
visible gap is `post_news_chase/short` at −0.1003 against a random short of
−0.0507, an excess of about **−0.050** — roughly half the threshold. Every other
candidate's excess is expected to be smaller still, and several positive.

Recording the prediction is the point. If the run returns what is predicted,
the route is **closed on XAUUSD** and that is the finding. If it returns
something much larger, the prediction was wrong and that is a result worth
having — but it will then have to pass the same seven criteria, and the first
question asked of it will be which defect produced it.

## 5. What a closed route means, and what it does not

If the prediction holds, the conclusion is narrow and should be stated narrowly:

> On XAUUSD, over 2023–2026, at this account's cost, the losing tail of a
> pattern search contains the direction effect and nothing else large enough to
> invert.

It is **not** a finding that inversion is a bad idea in general. It would be
expected to behave differently on an instrument without a 42 %-per-year drift,
and the measurement tooling to check that now exists. Whether to spend the next
run on that is a separate decision and is not pre-authorised here.

## 6. Addendum — peer review, incorporated before either run

Codex reviewed sections 1–5 before they were executed and raised three
objections that are accepted in full. They make the tests stricter, not looser,
and they are recorded here rather than applied silently.

### 6.1 DerSimonian–Laird is the wrong estimator at k = 4

Accepted. With four effects, `tau2` is unstable, DL can understate
heterogeneity, and the assets share USD and macro shocks so they are not
independent studies. The corrected replication therefore uses:

- **Paule–Mandel** for `tau2` in place of DerSimonian–Laird
- **Hartung–Knapp–Sidik–Jonkman** for the interval around the pooled mean,
  **with the safeguard** that prevents HK from returning a NARROWER interval
  than the uncorrected one when its scale factor falls below 1
- a **prediction interval** alongside the confidence interval
- the **number of independent calendar-day clusters per asset**, reported

### 6.2 Per-asset day clustering does not capture cross-asset dependence

Accepted, and this is the more serious of the two statistical objections.
Clustering each instrument's own trades by its own days says nothing about the
fact that a single macro release moves all six at once.

Replaced by a **synchronised day-block bootstrap**: resample calendar days,
keep **every asset's observations from each selected day together**, recompute
each asset's estimate, recompute `tau2` and the pooled estimate inside every
draw. XAGUSD's leave-one-day-out sensitivity is reported, because its +0.84 R on
22 trades supplies most of the positive numerator even at only 14 % of the
weight.

None of this can turn the run into a successful replication — criteria 1 and 2
already fail — and it must not be used to try. It improves the failure report.

### 6.3 The threshold must be per-trade, not an average

Accepted. `−0.092 R` was derived from an average cost divided by an average R,
and risk distances vary trade by trade. A single averaged threshold is unsafe
once commission is charged per trade.

**Replaced by a two-part requirement, both of which must hold:**

1. the candidate **underperforms its direction-matched control** by a
   significant margin after multiplicity correction, and
2. the **explicitly simulated mirror** has positive net expectancy per trade
   after all measured costs charged per trade

A negative excess does not by itself mean the mirror can pay its own costs, and
the second condition is what actually decides whether the idea is tradeable.
The +0.05 R minimum worthwhile edge now attaches to the mirror's **net**, where
it belongs, instead of to a gross threshold standing in for it.

### 6.4 Multiplicity, and what this run can and cannot claim

Accepted, and it is the most important point Codex made. Bonferroni over the
re-scored family controls that family **only if** all 24 candidates are re-run,
excess is the single frozen primary statistic, and the matching variables,
placebo draw count, seed and threshold are all fixed before running — in
particular, **it is forbidden to screen down to the three raw losers first.**

But choosing to score on excess **after** inspecting the raw outcome creates
program-level multiplicity that no per-family correction erases. Therefore:

> **This run is an EXPLORATORY DIAGNOSTIC, not a confirmatory test.** It cannot
> establish an edge on this sample no matter what it returns. A confirmatory
> claim requires forward data that does not exist yet.

Two further changes follow:

- a **permutation maxT statistic across all 24** is reported in addition to
  Bonferroni, because the candidates are correlated and separate Bonferroni
  tests are the wrong shape for correlated tests. N is accounted at **48** for
  Bonferroni, which is more conservative than either the 24 Codex allows or a
  maxT alone.
- **no new matching definition may be tried after the result is seen.** One
  run, one definition, fixed below.

### 6.5 The matched control's strata, fixed now

Codex's list is adopted. A placebo entry for a given candidate entry is drawn
from bars matching it on:

- **direction** — the same side
- **holding horizon and exit mechanics** — the identical engine, stop, target
  and 72-bar time stop
- **calendar block** — the same quarter
- **session** — asia / london / ny by the same boundaries
- **volatility state** — the same ATR tercile, computed on prior bars
- **news state** — both inside or both outside 30 minutes of a USD HIGH release
- **cost environment** — the same hourly spread bucket
- **overlap restrictions** — one position at a time, as the candidate has

Placebo draws per candidate entry: **20**. Seed: **20260922**. Both fixed here.

Where a stratum has too few eligible bars to draw from, that entry is reported
as unmatched and excluded from the excess, with the excluded count printed. It
is not quietly matched on fewer variables.

### 6.6 On whether a reliable losing tail should exist at all

Codex's answer to the question was **no**, and it is worth recording because it
is the part that most constrains how this result should be read. A strategy can
lose from instrument drift, from costs, from random timing, from slight barrier
asymmetry, or from genuine negative timing information — **and only the last is
invertible.** Nothing in market theory says a search over weak patterns must
contain a useful anti-signal.

All three observed facts point at drift rather than timing information: every
reliable loser is a short, longs are broadly positive, and 25 % of circular
shifts beat the real timing. If the diagnostic returns what section 4 predicts,
the honest record is **"closed for these 24 candidates, this sample and this
execution model"** — that exact scope, and no broader claim.

## 7. Status while this runs

Unchanged. `ORDERLY_TREND v2` is a rare shadow candidate with a failed
cross-asset replication against it. The engine's answer is **NO TRADE**. No
real-money order has been sent, no position is open, and no pull request is
opened.
