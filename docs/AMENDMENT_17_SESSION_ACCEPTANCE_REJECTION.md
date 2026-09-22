# Protocol Amendment 17 — session-level acceptance and rejection

**Written 2026-09-22. Committed alone, before the code described here produces a
single result.**

Amends: nothing already on the record. This is the bounded B2 experiment from
`docs/BACKLOG.md`: visible session levels, acceptance versus rejection, and touch
count as one ordinal variable.

Does not amend: any closure, W1's frozen rule or cost protocol, the measured cost
model, the protected 120-day slice, the prohibition on real-money orders, or the
prohibition on Grid and Martingale.

---

## 1. The question

Everything searched so far has transformed OHLC into an oscillator, moving
average, range statistic or combination of those quantities. This experiment
asks a different question:

> Does an entry at a visible structural level carry less directional information
> after that level has already been touched?

The mechanism is declared before the result. Resting orders and stops accumulate
at session extremes; the first interaction consumes some of that liquidity, so a
later interaction should contain less information. The primary hypothesis is
therefore **one ordered hypothesis**, not a separate candidate for every level,
side, response and touch count:

```
effect(first touch) >= effect(second touch) >= effect(third-or-later touch)
```

The null is a flat or increasing profile. A decline in either acceptance or
rejection is consistent with the mechanism. A flat profile says touch freshness
is not the variable.

## 2. Data and the boundary that may not move

- instrument: the existing MT5 **XAUUSD M5** series, whose metadata records UTC
  server time (`server_offset_hours = 0`)
- the last **120 calendar days are excluded** and may not be used for selection,
  interpretation or promotion; no result from that slice is printed
- all timestamps and session definitions below are UTC; no DST adjustment is
  introduced after the fact
- M15 ATR(14) is built only from complete groups of three M5 bars. At any M5
  decision, the ATR is taken from the latest M15 bar that had already closed
- warm-up: 60 completed M15 bars

The experiment is a pre-registered test on the non-holdout history, but the same
history has supported other research in this repository. A success may therefore
earn **forward-shadow status only**, never a live order and never confirmation.

## 3. The six visible levels, fixed now

Each family contributes a high and a low. A level is constant during its eligible
window and is computed before that window opens.

| family | construction window | eligible interaction window |
|---|---|---|
| Asia high / low | 00:00–05:59:59 of the same UTC calendar day | 06:00–20:59:59 |
| pre-London high / low | 06:00–06:59:59 of the same UTC calendar day | 07:00–20:59:59 |
| prior-day high / low | high and low of the preceding UTC calendar day, matching the prior-day definition already used by `inverse_search.py` | 00:00–20:59:59 |

A construction window is valid only if it has every expected contiguous M5 bar:
72 bars for Asia and 12 for pre-London. A prior day is valid only if it has at
least 200 M5 bars; this admits the normal daily maintenance break but rejects
weekends and materially incomplete days. Invalid levels produce no events.

The 21:00–23:59 UTC interval is excluded. It contains the maintenance/reopen
environment whose cost is still awaiting the dedicated W1 measurement and is not
allowed to contaminate this experiment.

## 4. Touch episodes, without a tolerance parameter

There is no ATR band, tick tolerance or distance grid around a level. A high is
touched when an M5 bar's high is at or above it; a low is touched when the bar's
low is at or below it.

Touches are counted as **episodes**, not as every bar that remains near a level:

- a high-side episode can start only when the preceding contiguous M5 bar closed
  below the level; a low-side episode mirrors this and requires the preceding
  close above the level
- after an episode, another touch is counted only after at least one completed
  contiguous M5 bar is wholly clear of the level on the interior side (its high
  is below a high level, or its low is above a low level). The rejection bar
  itself does not reset the episode, so consecutive touching bars cannot inflate
  the count
- the count is maintained separately for every `(UTC day, level family, side)`
- the ordinal value is `0, 1, 2` for first, second and third-or-later. No fourth,
  fifth or other category is created after seeing the counts

An episode that does not meet either response definition below still consumes its
touch number. Silently counting only episodes that become trades would condition
freshness on the outcome.

## 5. The two responses and their directions

### Rejection

The initiating touch bar closes on the interior side of the level.

- high rejection: touch the high, close below it, then **short**
- low rejection: touch the low, close above it, then **long**
- decision is known at that M5 close; entry is the next contiguous M5 open

### Acceptance

The initiating touch bar closes outside the level and the next contiguous M5 bar
also closes outside it. “Holds outside” means the confirming bar's **close**, not
its full range; no discretionary tolerance is added.

- high acceptance: two closes above the high, then **long**
- low acceptance: two closes below the low, then **short**
- entry is the open of the M5 bar immediately after the confirming bar

Equality is interior for neither response: a close exactly on the level is
unclassified, but its initiating episode still consumes the touch number.
Missing or non-contiguous confirmation/entry bars invalidate the event.

If one bar interacts with more than one named level, every interaction remains in
the event table because the estimand is about visible levels, not unique bars.
Their dependence is handled by calendar-day clustering. The overlap count is
reported and may not be removed after the result is seen.

## 6. Exit geometry and costs

No exit search is permitted. Every accepted event uses the project-standard
geometry:

```
entry       specified in section 5
stop        1.5 x the last fully known M15 ATR(14)
target      1.5 x ATR, RR 1:1
time stop   72 M5 bars
resolution  stop before target when both occur in one bar
```

Events are resolved independently for the primary information test. Overlapping
paths are not called independent: inference clusters all events on a UTC calendar
day together. A secondary deployable-policy readout applies one-position-at-a-time
in chronological order, with ties ordered by `prior-day`, `Asia`, `pre-London`,
then rejection before acceptance; that readout is descriptive and cannot replace
the primary result.

Per-trade net R charges the entry bar's recorded spread plus the Amendment 08
round-turn commission of `0.140` and slippage of `0.0165` per fill. Missing or
non-positive spread falls back to `0.090`. Results are printed at cost multipliers
`1.0, 1.5, 3.0, 7.0`. Financing is charged if a path crosses the account's daily
swap boundary, using the measured side-specific values; its exact count is
reported. Matched excess is gross because candidate and control share geometry
and cost environment; absolute tradeability is always judged on net R.

## 7. The control

Each event is compared with the Amendment 10 leave-one-day-out conditional mean:

- same direction
- same calendar quarter
- same Asia / London / NY session bucket
- same ATR tercile, formed from prior bars only
- same inside/outside 30 minutes of a USD HIGH release
- same hourly spread bucket
- identical stop, target and time stop
- the focal event's entire UTC calendar day removed from its pool
- at least 30 eligible control bars after that removal

The control bar also needs enough forward M5 data to resolve its path without
crossing the non-holdout boundary. An unmatched event is reported and excluded
from matched excess, never rematched on fewer variables.

## 8. The single primary statistic

For every matched event let `y` be its gross R minus its leave-one-day-out control
mean and let `x = 0, 1, 2` be the ordinal touch value. Fit

```
y = alpha[level family x side x response] + beta*x + error
```

with twelve fixed intercepts and one common slope. The primary statistic is the
calendar-day-clustered t statistic for **`beta < 0`**. Calendar days are the wild
clusters; one random sign per day is applied to that day's score contribution.
The reported one-sided p-value uses 10,000 draws and seed `20260922`. This is the
same wild-cluster approximation limitation recorded in Amendment 10: R outcomes
are not exactly symmetric, so it is not described as an exact randomisation test.

There is **one primary test at alpha 0.05**. The twelve stratum slopes, all pairwise
touch-count comparisons and separate p-values by level are forbidden. Reported
descriptively, without significance claims:

- matched excess and net R for touch 1, 2 and 3+
- the same three rows by level family and by response, with confidence intervals
  but no p-values
- counts, active days, directions, overlaps, unmatched events and swap crossings
- the secondary one-position policy

The clustered standard error and the 80% minimum detectable slope
`(1.645 + 0.842) * SE(beta)` are printed before the p-value is interpreted.

## 9. Gates and the only success rights

The monotone mechanism is supported only if all of these hold:

1. `beta < 0` and the one-sided wild-cluster p-value is at most 0.05
2. the three pooled matched-excess means are observed in the declared order:
   first `>=` second `>=` third-or-later
3. every touch category has at least **50 matched events and 30 active days**;
   otherwise the primary question is **NOT ASSESSED**, not failed

Support for the mechanism does not by itself create a trade. The pooled
first-touch policy earns forward-shadow status only if it additionally has:

4. at least 100 trades and 50 active days
5. matched excess above zero
6. net expectancy at least `+0.05 R` at both 1.0x and 1.5x cost
7. a day-clustered 95% lower confidence bound on 1.0x net R above zero

These are conjunctive gates, not seven opportunities to pass. A favourable
subgroup cannot be selected from the descriptive table. Any level family or
response deserves its own later amendment only if named from mechanism, not
because it is the best row here.

## 10. What failure looks like

- adequate counts but non-negative or non-significant `beta` → **touch freshness
  is not established** for these session levels
- ordered matched excess but no net edge after cost → **structural information
  exists but is not tradeable at this account's friction**
- first touch is profitable but the ordinal test fails → **an unregistered pooled
  first-touch observation**, reported but not promoted
- insufficient events or an MDE larger than plausible effects → **the sample
  cannot answer the question**
- only one descriptive subgroup looks favourable → **no candidate**, because
  selecting it would create the zoo this amendment was written to avoid

None licenses changing a session boundary, tolerating a near-touch, redefining a
hold, dropping a level, splitting third from later touches, changing geometry or
opening the 120-day slice.

## 11. Verification required before interpretation

The implementation must have tests that fail under each of these mutations:

1. a level uses one bar from after its construction window
2. an acceptance enters before its confirming bar has closed
3. consecutive bars in one episode are counted as separate touches
4. an unclassified episode does not consume a touch number
5. a control pool includes the focal calendar day
6. the M15 ATR mapped to an M5 decision has not yet closed
7. a trade or control path crosses the non-holdout boundary

The run is interpreted only after all tests pass. Code and result are committed
after this amendment's standalone commit.

## 12. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order is authorised,
no position is open, and no pull request is opened.
