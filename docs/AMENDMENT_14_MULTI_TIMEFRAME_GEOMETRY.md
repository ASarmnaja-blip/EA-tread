
# Protocol Amendment 14 — timeframe, barrier geometry and entry expiry

**Written 2026-09-22. Committed alone, before the code it describes produces a
single number.** The operator asked for every timeframe, varied entry / TP / SL,
and entry expiry at 5, 8, 10, 12, 15 bars, with both tails reported. The design
below is that request, constrained so the result can be believed, and it will be
**verified by a test suite before it is handed to Codex to run**.

Amends: nothing. Does not amend any closure (05–11, 13), W1's protocol (12), the
measured cost model (08), the prohibition on real-money orders, or the prohibition
on Grid and Martingale.

---

## 1. What is deliberately NOT re-opened

Two dimensions are closed and stay closed:

- **the indicator zoo.** Amendments 10 and 11 tested 6,480 configurations of 40
  tools across seven holding horizons and found the family quieter than chance.
  Re-opening it inside a larger grid would guarantee a result made of noise.
- **the pass/fail barrier question at family level.** Amendment 13 measured the
  path directly and found the tier-A aggregate flat, which eliminated barrier
  geometry as an explanation for the closures.

So the tool set here is **small and pre-declared**, and the sweep is over the
dimensions that genuinely have never been varied.

**One honest qualification on the second point.** Amendment 13's aggregate was
well powered at short horizons (detectable effect ~0.08 ATR at 15 minutes) and
poorly powered at long ones (~0.87 ATR at 24 hours), on 644 non-overlapping
entries. A direct geometry sweep is therefore still informative at the longer
horizons, and it is included for that reason rather than in spite of Amendment 13.

## 2. The four dimensions, and why each is new

| dimension | values | never tested because |
|---|---|---|
| **signal timeframe** | M5, M15, M30, H1, H4 | every tool in this project is computed on M15. Amendment 11 varied how long a position is *held*, which is a different thing from the timeframe the state is *computed on* |
| **stop distance** | 0.75, 1.0, 1.5, 2.0, 3.0 ATR | always 1.5 ATR, in every file, every search |
| **target** | 0.5R, 1.0R, 1.5R, 2.0R, 3.0R | always 1:1 in the searches, 2R in `ORDERLY_TREND` |
| **entry expiry** | market, 5, 8, 10, 12, 15 bars | entry has **always** been the next bar's open. A signal has never been allowed to wait |

### Entry expiry, defined exactly

A market entry is the next bar's open, as before. An **expiry of N bars** means a
**limit** order at the signal bar's close, valid for N bars of the signal
timeframe:

- long: a buy limit at the signal close, filled if any of the next N bars trades
  down to it
- short: a sell limit at the signal close, filled if any of the next N bars trades
  up to it
- not touched within N bars → **no trade at all**, and the signal is recorded as
  expired

This is a real strategy variant, not a technicality: it asks the signal to wait
for a better price and accepts missing the move as the cost. It changes fills,
cost and the sample size at once, which is why it has to be swept rather than
assumed.

## 3. The setup families, fixed now

Six, and **five of them have never appeared in any search in this project** —
they exist in `core.py` and were never wired in:

| family | source | used before? |
|---|---|---|
| breakout continuation | `core.s1_breakout` | yes |
| trend pullback | `core.s2_pullback` | yes |
| liquidity sweep reversal | `core.s3_sweep` | **no** |
| failed breakout | `core.s4_failed` | **no** |
| VWAP / value-area reversion | `core.s5_vwap` | **no** |
| volatility expansion | `core.s6_expansion` | **no** |

These six are exactly the families `CLAUDE.md` section 3 asks for. Each keeps its
own parameters at the values already in `core.py`; **the parameters are not swept**,
because that is the closed dimension.

## 4. The grid, counted before any result

```
6 setups x 5 timeframes x 5 stops x 5 targets x 6 expiries  =  4,500 cells
```

**N = 4,500, recorded here.** The time stop is held at **288 M5 bars (24 hours)**
for every cell, deliberately generous so it rarely binds and cannot become the
hidden explanation. **The share of exits caused by the time stop is reported per
cell**; a cell where it binds often is reported as horizon-limited rather than
quietly averaged in.

## 5. What makes a 4,500-cell search readable rather than data mining

Identical machinery to Amendment 10, which is the only reason this is worth
running:

- **three-way split.** SELECT = first 730 days. CONFIRM = the next ~245,
  untouched by selection. HOLDOUT = the last 120 days, **not read**.
- **scored on matched excess**, never raw expectancy, using the stratified
  direction-matched placebo with the leave-one-day-out control (Amendment 08 §6.5,
  Amendment 10 §4). Raw expectancy on this sample is a reading of gold's drift.
- **gates:** 40 trades and 20 active days on SELECT; 50 trades and 20 active days
  on CONFIRM.
- **the primary result is the pair of global statistics**: `max|t|` and
  permutation-calibrated Berk–Jones, with day-level sign flips shared across all
  cells. "Does this grid contain more than chance produces" has an answer at this
  N; "which cell is real" does not.
- **both tails**, with **K = 5 per tail** carried to CONFIRM, **blinded** to
  `L1..L5` / `W1..W5`, with a manifest frozen to disk before CONFIRM runs. A name
  is revealed only after it passes CONFIRM.
- **Westfall–Young step-down maxT** on the 2K CONFIRM hypotheses.
- BH q-values reported as **descriptive only**, never as formal FDR, because the
  cells share setups and timeframes and are heavily dependent.

### The power table is printed before the results are interpreted

As in Amendment 11: the empirical distribution of day-clustered standard errors,
and the effect detectable at 80 % power at the permutation critical value, at the
25th, 50th and 75th percentile. **If the detectable effect is far above anything
plausible, that is the finding** and it is reported as such rather than buried
under 4,500 numbers.

## 6. Verification before the run — the operator's condition

The operator required the work be checked for errors before it is handed over.
`research/pilot/test_mtf_engine.py` must pass, and it must include:

1. **no look-ahead.** Signals use closed bars only. A deliberately mutated version
   that peeks one bar ahead must be **CAUGHT** by the test, not merely produce a
   different number.
2. **resampling correctness.** M15/M30/H1/H4 built from M5 must reproduce the
   right open, high, low, close and bar boundaries on a synthetic series whose
   correct answer is known by construction.
3. **limit-fill and expiry logic.** On synthetic bars: a limit that is touched
   fills at the limit price; one that is not touched within N bars produces **no
   trade**; a fill on bar N is accepted and on bar N+1 is not.
4. **worst-case intrabar.** A bar spanning both stop and target must be booked as
   a **loss**, on both sides, so an inversion cannot harvest ambiguity.
5. **cost monotonicity.** Net must fall as the cost multiplier rises, and the
   per-trade charge must equal spread + commission + slippage exactly.
6. **the control excludes the focal day.** A stratum's leave-one-day-out mean must
   differ from its full-pool mean by exactly the removed day's contribution.
7. **the permutation reduction is exact.** The matrix form over per-day sums must
   equal the direct per-trade computation on random data, to floating-point
   tolerance.
8. **the grid is the declared size.** The builder must emit exactly 4,500 cells.

**The test output is part of the handover.** If any test fails, the search is not
run and the failure is reported instead.

## 6a. Addendum — a defect found by the verification, and the corrected grid

**The verification required by section 6 did its job and killed the first design.**
Recorded here before the search runs, because this is precisely what the check was
for.

### The defect

Section 2 defined an expiry of N bars as a limit **at the signal bar's close**. The
test suite's expiry check passed on synthetic data, but with a suspicious reading:
the expiry rate was 0 % at every N. Measured on real XAUUSD M5:

```
breakout / M15    e=5      e=8     e=10     e=12     e=15
trades          2590     2591     2591     2592     2592
expired           1%       1%       1%       1%       1%
```

A limit at the signal bar's close sits a hair from the next bar's open, so price
trades back through it almost immediately. **The five expiry values produced
identical cells.** The declared grid of 4,500 was really 750 distinct cells with
six near-copies of each, and `N = 4,500` would have been a fiction — a larger
multiplicity penalty applied to a search that had not actually been made larger.

### The measurement that fixed it

The limit has to sit a meaningful distance away for waiting to mean anything.
Measured, on the same setup and timeframe:

```
limit offset      e=5      e=8     e=10     e=12     e=15
  0.00 ATR      1% exp   1%       1%       1%       1%      <- degenerate
  0.10 ATR      5%       5%       4%       4%       4%
  0.25 ATR     12%      10%       9%       8%       8%
  0.50 ATR     24%      20%      19%      17%      16%      <- discriminates
  1.00 ATR     48%      41%      37%      35%      32%      <- discriminates
```

### The corrected entry dimension, and the corrected count

The entry dimension is **(limit offset, expiry)**, not expiry alone:

```
market                                    1 mode
offset 0.50 ATR x expiry {5,8,10,12,15}  5 modes
offset 1.00 ATR x expiry {5,8,10,12,15}  5 modes
                                     = 11 entry modes
```

```
6 setups x 5 timeframes x 5 stops x 5 targets x 11 entry modes = 8,250 cells
```

**N = 8,250 replaces N = 4,500**, and the offsets {0.50, 1.00} are fixed here
before any result. A deeper limit is a real strategy: it asks for a better price
and pays by missing 24 % to 48 % of the signals outright, which is now a measured
cost rather than an invisible one.

**The expiry rate is reported per cell.** A cell whose signals expire most of the
time is reported as such rather than presented as though it traded a full sample.

### What did not change

Every gate, split, statistic, blinding and failure definition in section 5 and
sections 7 and 8 stands. Raising N raises the permutation critical value slightly,
which is the honest consequence of a larger search and is not compensated for
anywhere.

## 7. What this amendment may not do

- may not name a candidate that has not passed CONFIRM
- may not sweep the setups' own internal parameters — that is the closed dimension
- may not change W1's frozen geometry, whatever a neighbouring cell shows
- may not read the 120-day HOLDOUT
- may not add a dimension, a value, or a K after a result is seen

## 8. What failure looks like, so it cannot be argued away later

- both global statistics non-significant → **the grid contains nothing beyond
  chance**, and no cell may be named however large its t
- the power table shows the detectable effect far above plausible values → **the
  sample cannot support a 4,500-cell search**, reported as the result
- a CONFIRM candidate flips sign → **the extreme of 4,500 draws**
- excess survives but net is below +0.05 R → **not tradeable**
- net dies at 1.5x cost → **a cost artefact**

## 9. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order has been sent,
no position is open, and no pull request is opened.
