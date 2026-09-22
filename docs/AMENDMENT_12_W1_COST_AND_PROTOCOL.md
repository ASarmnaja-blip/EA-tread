
# Protocol Amendment 12 — W1's cost test and prospective protocol

**Written 2026-09-22. Committed alone, before the code it describes produces a
single number.**

Amends: nothing. It fixes the protocol for the one observation in this project
that ever cleared a family-wise threshold.

Does not amend: any closure (05–11), the measured cost model (08), the
prohibition on real-money orders, or the prohibition on Grid and Martingale.

---

## 1. What W1 is, frozen exactly

Found in the Amendment 08 section 4 re-score, on the development period only:

```
n = 75    own gross +0.2934 R    matched control -0.0549 R
excess +0.3483 R    t +3.18    p(maxT) 0.0330 against a critical 3.052
```

The rule, stated with no remaining freedom:

| element | value |
|---|---|
| series | XAUUSD, signals on M15, execution on M5 |
| trigger | `open[i] - close[i-1] <= -0.5 x ATR(14)` on M15 |
| direction | **short** — with the gap, not against it |
| entry | the open of the next M5 bar |
| stop | 1.5 x ATR(14) above entry |
| target | 1.5 x ATR(14) below entry (**RR 1:1**) |
| time stop | 72 M5 bars |
| overlap | one position at a time |

**No parameter here may move for the rest of this amendment.** Not the 0.5 ATR
gap threshold, not the stop, not the target, not the time stop.

**The mechanism, stated before the cost numbers are read:** a down-gap in a
rising market is a liquidation print rather than a re-pricing, and liquidations
run because the seller is not choosing the price. That is why the candidate goes
*with* the gap.

## 2. The thing most likely to kill it, named in advance

**Gold gaps where the book is thinnest.** An M15 gap on this instrument arises at
the Sunday open, at the 21:00 UTC rollover break, and after data holes — exactly
the moments when the spread is widest and a market order is filled worst.

The project's cost model uses a **median** spread of 0.090. If W1's own signal
times carry a spread several times that, its +0.2934 R gross is being charged a
cost it never paid in the measurement.

**So the primary output of this run is not the net expectancy. It is the spread
distribution at W1's own entry bars, set beside the distribution everywhere
else.** That comparison is reported first, before any P&L.

Also reported, because it decides whether n = 75 means anything:

- the **hour-of-day and day-of-week** histogram of the 75 entries
- the **number of distinct calendar days and distinct weeks** they fall on
- how many are the **first bar after a weekend or a rollover break**

If the 75 turn out to be 75 Sunday opens, they are closer to 75 observations of
one recurring event than to 75 independent trades, and that is stated plainly.

## 3. Costs charged, fixed now

Per trade, in gold dollars per ounce, from the measured model in Amendment 08:

```
spread        the per-bar measured spread AT THE ENTRY BAR, not the median
commission    0.140 round turn   (measured: $7.00 per lot per side)
slippage      0.033 round turn   (measured floor 0.0165 per fill)
swap          0.000             (measured swap_short on XAUUSD is zero)
```

Reported at multipliers **1x, 1.5x, 3x, 7x** on the whole cost, as every other
result in this project is.

A short pays no financing on this instrument, which is the one structural
advantage W1 has and it is stated rather than quietly enjoyed.

## 4. Pass criteria for the cost test, fixed now

All of:

1. net expectancy per trade **≥ +0.05 R at 1x** measured cost
2. still **≥ +0.05 R at 1.5x**
3. at least **50 trades** and **30 distinct active days**
4. the day-clustered interval's **lower bound above zero**
5. the **matched excess stays positive** when the control is rebuilt with the
   leave-one-day-out stratum mean from Amendment 10 section 4

**Surviving all five is a PREREQUISITE, not confirmation.** Amendment 12 does not
promote W1 and cannot. The discovery p-value of 0.0330 is **not reused** as
evidence here; it belongs to the search that found it.

## 5. The 120-day holdout, and why it is a weak check here

The holdout was never seen by W1's discovery, which ran on the development period
only. But Amendment 05 section 5 already spent it diagnosing the
`ORDERLY_TREND` failure, so it is not a clean slice.

It is therefore read here as a **secondary, explicitly caveated check** and
**never as confirmation**. Whatever it shows, the sentence on the record will be
"consistent with" or "inconsistent with", not "confirmed".

Expected there: roughly 8 to 10 events at 25 a year, which is too few to decide
anything. That is stated now so a favourable number cannot be presented as more
than it is.

## 6. The prospective shadow, fixed now

If the cost test passes, a forward shadow begins, with its stopping rule fixed
**before** any forward data exists:

- **length: 26 weeks** from the first forward signal, or **30 non-overlapping
  events**, whichever comes second
- it does **not** stop early because the result became favourable, and it does
  not extend because the result became unfavourable
- every signal is logged whether or not it would have been taken
- costs charged from the measured model, re-measured at least monthly
- **no parameter changes during the run**, which Amendment 05 section 5 already
  requires of any shadow
- promotion afterwards needs the net expectancy positive with a clustered lower
  bound above zero, and **no real-money order** regardless

If the cost test fails, W1 is **recorded as dead on the watchlist** and the next
step is the geometry-neutral path diagnostic, not a rescue of W1.

## 7. What failure looks like, so it cannot be argued away later

- spread at W1's entries is several times the median and net falls below
  +0.05 R → **a cost artefact of trading the thinnest book of the week**
- the 75 entries sit on very few distinct weeks → **not 75 observations**, and
  the discovery t of +3.18 was overstated by dependence
- net positive at 1x but dead at 1.5x → **cost-fragile**, same verdict
  `UNSTABLE_HIGH_VOL` received
- matched excess turns negative under the leave-one-day-out control → **the
  original control was contaminated**

Any of these closes W1. None of them is a reason to move the gap threshold, the
stop, the target, the time stop, or to exclude the worst-spread entries after
seeing them.

## 8. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order has been
sent, no position is open, and no pull request is opened.
