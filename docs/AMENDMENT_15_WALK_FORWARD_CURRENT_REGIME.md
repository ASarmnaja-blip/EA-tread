
# Protocol Amendment 15 — walk-forward, and a correction to the whole programme

**Written 2026-09-22. Committed alone, before the code it describes produces a
single number.**

Amends: **the evaluation design of Amendment 14, and the way every closure in this
project should be read.** It does not withdraw any closure; it states what they
actually measured.

---

## 1. The drift, named

The operator's objective, from `CLAUDE.md` section 1, is a signal engine fitted to
**the current market**, continuously re-evaluated, which abandons a rule when
present evidence says its edge has decayed. Section 1 says explicitly that long
history is for catching gross errors, **not** a requirement that today's signal
must have been profitable in every past year.

Every recent search in this repository did the opposite:

```
SELECT   first 730 days (2023-2025)   <- the search happened HERE
CONFIRM  the next ~245 days
HOLDOUT  the last 120 days            <- the most recent data, never touched
```

**The searching was done on the oldest data available and the newest was
deliberately withheld.** So the five closures on the record do not say "this does
not work now". They say **"this did not work in 2023–2024"**, which is a different
and much less interesting claim.

This was not a shortcut. The standard machinery against overfitting — fit on old,
validate on new — pushes exactly this way, and it was followed without checking it
against the stated objective. Statistical hygiene was put ahead of the question.

## 2. Why the obvious fix is also wrong

| approach | what breaks |
|---|---|
| fit on the last 30–60 days only | nothing is left to validate on. Whatever comes back is a description of the window it was fitted to, and cannot be distinguished from noise |
| fit on old, validate on new (the status quo) | finds what worked two years ago, which is not what was asked for |

Neither serves the objective, so the design changes rather than the target.

## 3. Walk-forward — the question changes

```
select on the trailing 60 days  ->  trade the next 10 days  ->  roll  ->  repeat
```

Over roughly three years of M5 this gives about **100 rolls**. Two properties the
status quo cannot have at the same time:

- **every selection is made on recent data.** No roll ever chooses a rule using
  information older than 60 days.
- **every measurement is genuinely out of sample.** Performance is scored only on
  the 10 days after the window that chose the rule.

And the quantity being estimated changes, which is the real point:

> **not "does rule X have an edge", but "does re-selecting a rule from the last 60
> days beat what a matched placebo does over the following 10 days".**

That is the thing the operator would actually run. A rule that decays after two
weeks is not a failure under this framing; it is a rule with a two-week half-life,
and the walk-forward measures whether re-selection keeps up with the decay.

### What it measures that nothing here has measured

- **whether the ranking transfers.** Does the best cell of the last 60 days beat
  the median cell over the next 10? If not, the adaptive procedure does not work,
  and that is a more useful finding than any single closure.
- **edge half-life.** Scoring the chosen rule at 1, 3, 5, 10 and 20 days forward
  gives the decay curve directly.
- **regime dependence**, because each roll carries its own regime labels.

## 4. Design, fixed now

| element | value |
|---|---|
| grid | unchanged from Amendment 14: **8,250 cells**, verified by 35 checks |
| selection window | **60 days**, trailing, ending at the roll boundary |
| forward window | **10 days**, immediately after |
| step | **10 days**, so forward windows tile the sample without overlap |
| scoring | **matched excess** against the stratified leave-one-day-out placebo, computed **inside each roll** so no control ever reaches across a boundary |
| ranking | the **top 5 and bottom 5** cells by selection-window excess, both tails, carried forward — the operator asked for both tails throughout |
| gate | a cell needs **15 trades and 8 active days inside the selection window** to be rankable, and the count of rolls where nothing qualifies is reported |
| aggregation | the forward excesses of the chosen cells, **pooled across rolls**, clustered by calendar day |
| null | **the median cell of the same roll**, and a **matched placebo**, so the comparison is "did choosing help" rather than "did gold go up" |
| holdout | the last **120 days are still excluded** from the rolls, and remain unread |

### The pre-registered primary statistic

> **the day-clustered mean forward excess of the selected cells, pooled over all
> rolls, against the same statistic for the median cell of each roll.**

One number per tail, with a day-level sign-flip permutation p-value. Not 8,250
numbers: the grid is the menu, and what is being tested is whether choosing from
the menu on recent evidence works.

### Decay curve, reported alongside

The selected cells scored at forward horizons of **1, 3, 5, 10 and 20 days**, as
one curve with one simultaneous permutation band, exactly as Amendment 13 handled
its nested horizons.

## 5. Predictions, recorded before the run

1. **The winning tail does not transfer.** The top-5 cells of a 60-day window are
   the maximum of 8,250 noisy estimates on about 8 weeks of data, and Amendment 10
   already showed every one of five CONFIRM winners flipping sign. Expected forward
   excess near zero or negative.
2. **The losing tail does not transfer either**, for the mirror-image reason.
3. **The decay curve is expected to be flat rather than declining** — a declining
   curve would mean there was something to decay from.
4. **If 1 and 2 hold, the finding is that adaptive re-selection over this grid does
   not work**, and that closes the adaptive-selection route on this instrument at
   this cost rather than closing another rule.

Being wrong about any of these is a genuine result, and the first question asked of
it will be which defect produced it.

## 6. How the existing closures should now be read

No closure is withdrawn. Their wording is corrected:

| was recorded as | should be read as |
|---|---|
| "nothing beyond chance in the indicator family" | nothing beyond chance **when fitted to 2023–2024 and tested on 2025** |
| "nothing at any holding horizon 1 h to 48 h" | same qualification |
| "the tier-A aggregate path is flat" | measured on the development period only |

W1 is the exception and it matters: it is a **mechanical, unfitted** rule — a
rollover gap — with nothing tuned to any window, so its cost test does not carry
this defect. That is a point in its favour that was not previously stated.

## 7. What this amendment may not do

- may not use the 120-day holdout
- may not shorten the forward window or lengthen the selection window after seeing a
  result, since both are now fixed
- may not report a single named cell as a candidate: the unit under test is the
  **procedure**, and a cell that looks good in one roll is one roll out of a hundred
- may not drop rolls that produced no qualifying cell

## 8. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order has been sent,
no position is open, and no pull request is opened.
