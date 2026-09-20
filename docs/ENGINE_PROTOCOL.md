# Current-Regime Engine — Protocol v2

Binding rules for the Adaptive Current-Regime Signal Engine. Where this file
and an older document disagree, this file wins. Nothing here promises profit.

Status of every claim in this file: **design, not measurement.** No threshold
below has been validated against data yet.

---

## 0. Two states that must never be conflated

| State | Meaning | Where it can be reached |
|---|---|---|
| **AUTHORED** | written, and its invariants checked by synthetic tests | container |
| **VERIFIED** | compiles in MetaEditor and reproduces the prior backtest byte for byte | **MT5 only** |

The container has no MetaTrader 5 and no price data. Work done here is
AUTHORED at best. **No task may be reported as complete on the strength of
container work alone.** Every change carries an explicit MT5 regression list
until someone runs it.

---

## 1. The long-horizon record is a prior, not a verdict

`RESEARCH_FINDINGS.md` records ~47 configurations, most of them negative, and
intraday results that are significantly negative across many markets. Those
results enter as a **prior over the effect size** and as a warning about which
mistakes are easy to repeat. They are **not** proof that a setup cannot work in
the current regime, and they never veto a candidate on their own.

They are reported beside every current-regime result so the reader can see what
the engine is arguing against.

---

## 2. Two tiers of criteria

### Tier A — Structural safety (hard veto, not negotiable)

These concern whether the measurement is *correct*, not whether the edge is
*permanent*. A candidate failing any of these is not measured at all.

1. No look-ahead. Negative control on a driftless random walk returns ~0.
2. No leakage between fitting window and validation slice.
3. Exits resolved on M1 bars, never on the signal bar.
4. Costs from **measured** spread, not an assumed figure.
5. A matched control with the same direction mix. No control, no number.

### Tier B — Current-regime usefulness (graded, never an automatic veto)

Measured rolling and walk-forward on recent data. Reported as a distribution,
not a pass mark. `t > 3`, sign stability across horizons, and the long-horizon
prior are **reported as risk information beside the result** — they do not
block a candidate by themselves.

---

## 3. Posterior bands and what each permits

`P` below is the posterior probability that the candidate's **net** per-signal
expectancy exceeds 0, on the current regime window, after measured costs.

| Band | Label | What it permits |
|---|---|---|
| `P < 0.60` | **INCONCLUSIVE** | nothing. Not a rejection — an absence of evidence |
| `0.60 ≤ P < 0.75` | **RESEARCH WATCH** | keep measuring, no signal emitted |
| `P ≥ 0.75` | **SHADOW CANDIDATE** | runs in shadow, may emit an experimental signal |
| promotion to paper | see below | stricter, and cost-stressed |

**Promotion to paper champion** requires a higher bar than the shadow band, on
`P(net expectancy > 0)` specifically:

- `P(net > 0) ≥ 0.85` on the current regime window, **and**
- still `≥ 0.75` when costs are stressed to **1.5×**, **and**
- still `> 0.50` when costs are stressed to **2×**, **and**
- wins the paired comparison against the incumbent champion (§5)

A candidate that only clears the bar at the measured cost, and collapses at
1.5×, is a cost artefact and is reported as one.

### Multiplicity within a regime

Every band above is adjusted for **the number of candidates evaluated in the
same regime window**. With `k` candidates tested in the window, the evidence
required scales with `k`:

```
required e-value  =  k / alpha
```

The candidate ledger counts configurations **inside the current regime window**.
It does not carry the lifetime count of ~47 forward as a fixed debt, and it does
not pretend the history never happened — the history is the prior in §1.

---

## 4. Sequential protocol (fixed in advance, before any data is read)

Declared here so it cannot be chosen after seeing results.

| Item | Value |
|---|---|
| **H0** | net per-signal expectancy `≤ 0` R, after measured costs |
| **H1** | net per-signal expectancy `≥ MWE` |
| **MWE** (minimum worthwhile edge) | `max(0.05 R, 2 × measured round-turn cost in R)` — the cost term is unknown until `SpreadMonitor` reports; until then MWE is **undefined and no test may be run** |
| **alpha** | 0.05, divided by the candidate count `k` in the regime window |
| **beta** | 0.20 (power 0.80) at `MWE` |
| **minimum sample** | 30 signals. No decision is permitted below this, whatever the statistic says |
| **maximum sample** | the lesser of 400 signals or 3 consecutive regime windows |
| **outcome if max reached without a decision** | **INCONCLUSIVE** — recorded as such, never rounded to "promising" |

**Peeking is expected, so the statistics must tolerate it.** Results are
monitored continuously using an **always-valid confidence sequence** and an
**e-value / e-process**, not a fixed-n p-value. Decision rule: reject H0 when the
e-value reaches `k / alpha`. An empirical-Bernstein confidence sequence supplies
the interval, which is valid at every stopping time including data-dependent
ones. A fixed-n p-value recomputed on every new signal is invalid and is not
used anywhere in this engine.

---

## 5. Two scores, kept strictly apart

A score used to cut a setup's validation slices must not contain that setup's
own performance, or the slice boundaries are chosen by the thing being measured.

| Score | Inputs | Used for |
|---|---|---|
| **Market Regime Score (MRS)** | price structure, ATR, volatility-of-volatility, cross-asset correlation, liquidity, spread, event/narrative density — **market observables only** | cutting regime windows and validation slices; timing re-evaluation |
| **Strategy Health Score (SHS)** | a setup's own recent performance, drift statistics, hit rate vs expectation | champion/challenger decisions, drift response |

**SHS never feeds MRS.** Not directly, not through a shared term.

> Note on `CLAUDE.md` §4: the mandate lists "ผลงานล่าสุด" (recent performance)
> among the Regime Stability Score inputs. That input is kept — in **SHS**. It is
> excluded from **MRS** because MRS defines the slices that SHS is measured on,
> and a score cannot define its own test set. Both signals exist; neither
> contaminates the other.

---

## 6. Paired comparison on a common timeline

Comparing two setups by their trades alone compares different moments and
different market paths. It is not a paired test.

The paired evaluator compares **per-bar (or per-session) R on the same
timeline**, with **no position = 0**:

- both arms produce a value for **every** bar in the window, position or not
- the statistic is the per-bar difference, so the market path cancels
- **exposure** is reported beside it (fraction of bars in a position)
- **opportunity cost** is reported: what the idle arm gave up over the same bars

Matching only the trades that each setup happened to take, at times that do not
coincide, is not permitted.

---

## 7. Adaptive policies are candidates, not defaults

The adaptive-expiry formula and the MRS-scaled rolling-window formula are
**candidate policies**. Before either is adopted it must be benchmarked against:

1. **fixed window / fixed expiry** (the null — simplest thing that works)
2. **exponentially-weighted** (decay, no explicit regime)
3. **change-point segmentation** (CUSUM or Bayesian online change-point)

Adopted only if it beats all three on out-of-window data by a margin larger than
the measurement error. Until then, the engine records the inputs a policy would
need and **applies none of them**.

---

## 8. Position sizing

**No Kelly, fractional or otherwise, at this stage.**

- fixed small risk percentage per setup
- a hard cap that nothing may exceed
- **min-lot feasibility check**: if the broker minimum lot forces risk above the
  cap, the answer is **NO TRADE** — never a rounded-up position

The existing `RiskManager::Size()` with `LOTFIT_REJECT` / cap check already
implements this and is not being changed.

---

## 9. Cost reporting — five numbers, never merged

Every result reports, separately:

| Field | Meaning |
|---|---|
| **gross expectancy** | before any cost |
| **spread** | measured, per hour bucket |
| **commission** | broker schedule |
| **slippage** | measured from live fills, not assumed |
| **net expectancy** | gross minus the three above, each counted **once** |

Plus **cost stress at 1.5× and 2×** of total cost.

**Double counting is a live hazard in this repo.** `RESEARCH_FINDINGS.md`
records why: at zero spread the break-even stop sits at entry rather than one
spread inside profit, so "adding the cost back" to a gross run credits a
break-even leg with a spread it never paid. Gross and net must come from **two
separate simulations**, never from one plus an adjustment.

---

## 10. Expiry and position management are different things

| Situation | Rule |
|---|---|
| Premise breaks, **no position open** | the pending signal is **cancelled**. Recorded with the reason |
| Premise breaks, **position already open** | the exit follows the **pre-declared position-management rules only** |

Exit rules are fixed before entry. They are not revised mid-position — not by
the engine and not by Claude. A premise break on an open position is recorded as
an observation and may inform the next signal; it does not authorise an ad-hoc
exit.

---

## 11. NO TRADE is a conclusion, not a default

`NO TRADE` is correct when evidence is absent. It is **not** acceptable as an
unexamined default. To be recorded as NO TRADE the engine must have evaluated
the candidate set and current market behaviour, and the log must show what was
evaluated and why each was rejected.

**Known gap (as of Track 1.2):** in the current EA the veto chain runs *before*
setups are evaluated, so on gate-blocked bars no candidate is evaluated at all.
The decision log records this honestly as `gate_blocked_before_evaluation`.
Reordering it would change trading behaviour and is therefore out of scope for
Track 1; it is scheduled for the track that introduces the shadow harness, where
evaluation can run without touching the live path.

---

## 12. Standing prohibitions

- no real-money orders without explicit confirmation, every time
- the sealed holdout stays sealed
- Setup B and Setup C are not enabled because their code exists; they enter as
  shadow challengers through the same pipeline as any new candidate
- no grid, no martingale, no risk increase after a loss
- no claim of guaranteed profit, ever
