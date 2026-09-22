# Protocol Amendment 11 — the holding horizon, and a mechanism with a prediction

**Written 2026-09-22. Committed alone, before the code it describes produces a
single number.**

Amends: nothing. It audits a parameter that has been fixed at one value under
every result this project has ever produced, and it tests a stated mechanism by
its prediction rather than by searching again.

Does not amend: `ORDERLY_TREND` (05), the failed cross-asset replication (06),
the measured cost model or matched-control strata (08), the closed inverse
routes (07, 09), the closed wide screen (10), the watchlist, the prohibition on
real-money orders, or the prohibition on Grid and Martingale.

---

## 1. The defect this exists to address

```
adaptive.py:76        TIME_STOP_M5 = 72
engine2.py:59         TIME_STOP_M5 = 72
inverse_search.py:52  TIME_STOP_M5 = 72
junk_search.py:48     TIME_STOP_M5 = 72
wide_search.py:53     TIME_STOP_M5 = 72
```

**Seventy-two M5 bars — six hours — in every file, every search, every result.**
It was chosen once and never varied. Every conclusion in this repository,
including four recorded closures, is therefore a statement about *what happens
when a position is abandoned after six hours*, and not about the setups
themselves.

That is not a small caveat. It is a single arbitrary number sitting underneath
the whole program, and until it is varied nobody knows which conclusions are
about the market and which are about the number.

## 2. Why this is a mechanism test and not another grid search

Amendment 09 recorded an explanation for its own negative result:

> the negative tail is dominated by the deliberately SLOW settings — `rsi:40`,
> `emax:50-200`, `boll:50`. The plausible reading is **horizon mismatch** rather
> than anti-information: a 200-period signal on M15 speaks to a move far longer
> than a 72-bar time stop can hold, so the trade is closed before the thesis
> resolves.

That was written as an aside. It is in fact a **falsifiable prediction**, and the
two configurations that keep reappearing on the watchlist are the two slowest
tools in the library. If the explanation is right, giving a tool a horizon
proportionate to its own lookback should change its measured excess in a
specific direction. If the explanation is wrong, it should not.

**This amendment tests the prediction. It does not search for a winner.**

## 3. The horizon grid, fixed now

```
12, 24, 48, 72, 144, 288, 576 M5 bars
=  1h,  2h,  4h,  6h,  12h,  24h,  48h
```

Seven values, including the incumbent 72 so the old results sit inside the new
table rather than beside it. **RR stays at 1:1 and the stop stays at 1.5 ATR** —
one variable moves at a time, or the result cannot be attributed.

Longer horizons mean fewer non-overlapping trades and more overnight financing.
Both are charged: the swap is already per-night in the cost model, and trade
counts are reported per horizon with the same gates as Amendment 10 (40 trades
and 20 active days on SELECT).

## 4. The three pre-registered results, in order

### P1 — the mechanism prediction, and its declared direction

For each tool, its **lookback** is the period in its own name, converted to M5
bars by multiplying by three. Define

```
slack = log2( horizon_M5 / lookback_M5 )
```

so `slack < 0` means the trade is closed before the tool's own lookback has
elapsed, and `slack > 0` means it is given more room than the tool looks back.

> **PREDICTION P1, recorded before the run: the Spearman correlation between
> `slack` and matched excess is POSITIVE.** Giving a tool more time relative to
> its own lookback improves its excess, because the loss attributed to horizon
> mismatch is a loss from closing before the thesis resolves.

Tested once, on the pooled tier-A set across all seven horizons, with the
permutation calibrated by shuffling `slack` within horizon so the correlation is
judged against the same clustering. **One test, one p-value.**

If P1 fails, horizon mismatch is not the explanation for Amendment 09's negative
tail, and that aside is withdrawn rather than left standing.

### P2 — is the "nothing beyond chance" conclusion conditional on 72?

The two global statistics from Amendment 10 section 5 — `max|t|` and
permutation-calibrated Berk–Jones — are recomputed **at each of the seven
horizons**, on the 240 tier-A singles, on SELECT only. Judged at Bonferroni for
**7** horizon-level tests, which is the honest count because seven pre-specified
global tests are run.

Two outcomes, both informative:

- **no horizon shows family-level signal** → the closure recorded in Amendment
  10 is strengthened from "nothing at six hours" to "nothing at any holding
  horizon from one hour to two days", which is a much stronger statement than
  the one currently on the record
- **some horizon does** → every conclusion in this repository is conditional on
  a number nobody tested, and that is the finding, reported as such

### P3 — a falsification test of watchlist entry W2

`rsi:40/short` and `emax:50-200/long` are on the watchlist because their mirrors
looked tradeable. Their lookbacks are 40 and 200 M15 bars, i.e. 120 and 600 M5
bars, so at the incumbent 72 they were being closed at 0.6 and 0.12 of their own
lookback.

> **PREDICTION P3, recorded before the run: at a horizon matched to their own
> lookback (144 and 576), the matched excess of both moves TOWARD ZERO.**

If it does, their negative excess was horizon mismatch — a non-invertible cause —
and **they are removed from the watchlist as inversion candidates**, not kept.
This is written down so the test can retire them rather than only ever promote.

If their excess stays negative at a matched horizon, horizon mismatch is not the
explanation for these two and they stay exactly where they are, still failing
their trade-count and significance gates.

Two pre-specified tests, judged at Bonferroni for 2.

## 5. What this amendment may NOT do

- **It may not name a new candidate.** Any configuration that looks good at a
  new horizon is the extreme of 240 x 7 = 1,680 cells, and this amendment
  declares no CONFIRM stage for them. A candidate arising here requires its own
  amendment with its own untouched slice.
- **It may not change the incumbent horizon for any other tool.** If 72 turns
  out to be a poor default, that is recorded; changing `ORDERLY_TREND`'s geometry
  on the strength of it would be re-tuning a frozen rule.
- **It may not touch the 120-day HOLDOUT**, which is not read here.

## 6. What failure looks like, so it cannot be argued away later

- P1 non-significant or the wrong sign → **horizon mismatch is withdrawn as an
  explanation**, and Amendment 09's aside comes off the record
- P2 finds nothing at any horizon → the wide closure becomes stronger, and
  **that is the result**, not a licence to search elsewhere
- P2 finds something at one horizon only → treated as **one cell out of seven**,
  reported with its multiplicity, and not pursued without a new amendment
- P3 shows the excess moving toward zero → **W2 is retired from the watchlist**
- P3 shows it unchanged → W2 stays, still failing, and the mechanism note on it
  is corrected

None of these is a reason to add a horizon to the grid, vary RR as well, or
lower a gate.

## 7. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order has been
sent, no position is open, and no pull request is opened.
