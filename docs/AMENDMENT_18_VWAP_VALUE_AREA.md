# Protocol Amendment 18 - VWAP and value-area interaction

**Written 2026-09-22. Committed alone, before the code described here produces a
single result.**

Amends: nothing already on the record. This is the B3 experiment from
`docs/BACKLOG.md`: VWAP and value-area interaction as the next distinct
untested channel after Amendment 17 closed the bounded session-level question.

Does not amend: any closure, W1's archived status, the measured cost model, the
protected 120-day slice, the prohibition on real-money orders, or the prohibition
on Grid and Martingale.

---

## 1. The question

VWAP is not another oscillator. It is an execution benchmark and a public
reference for whether price is rich or cheap versus the day's traded flow.
Value-area bands ask a related but weaker question: whether price is inside or
outside the part of the session where most broker tick volume has traded.

This experiment asks:

> Does price carry directional information when it is far from session VWAP or
> outside the session value area, after controlling for direction, time, volatility,
> news proximity and spread?

The answer can point three ways:

- reversion: distance from value is overextended and price tends to move back
- continuation: leaving value is acceptance and price tends to keep moving
- neither: VWAP/value-area state adds no information beyond the controls

No one of these is assumed after seeing the result. The test declares both tails
up front and treats them symmetrically.

## 2. Data and protected boundary

- instrument: existing MT5 **XAUUSD M5** and M15 bars, UTC server time
- the last **120 calendar days are excluded physically** before feature
  construction, control construction, path resolution or reporting
- all timestamps and session definitions are UTC
- warm-up: 60 completed M15 bars after the session features become available
- no real-money order, demo order or shadow order is authorised by this amendment

The same pre-holdout history has supported prior research in this repository. A
success may therefore earn only a later forward-shadow amendment, never live
promotion.

## 3. Session VWAP and value area, fixed now

The session anchor is the existing project convention: **22:00 UTC**, matching
`core.session_vwap`.

At each completed M15 decision bar, construct the session-to-date distribution
from completed M5 bars only. The current incomplete M15 group may not enter the
feature. The first 12 completed M5 bars of a new anchored session are warm-up and
produce no event.

VWAP:

- typical price is `(high + low + close) / 3`
- volume is broker tick volume; if a bar has non-positive volume, use weight 1
- VWAP and weighted standard deviation are computed from bars already completed
  in the anchored session

Value area:

- use the same completed M5 bars as VWAP
- bin typical prices to the instrument's observed M5 tick grid rounded to 0.01
- accumulate broker tick volume by bin
- begin at the highest-volume bin, then add the neighbouring bin with larger
  volume until at least 70% of session-to-date volume is covered
- the lower and upper selected bin edges are VAL and VAH
- ties expand both sides if needed; if fewer than 12 completed M5 bars exist or
  total volume is zero, the value area is missing

The value-area caveat is part of the hypothesis, not an excuse after the fact:
XAUUSD is decentralised, so this is this broker's tick-volume value area, not a
central exchange volume profile.

## 4. Event families

Events are formed on completed M15 decision bars and enter at the next contiguous
M5 open. The M15 bar's close is the decision price.

There are four pre-declared families:

| family | condition at the completed M15 close | direction |
|---|---|---|
| VWAP reversion | close is at least `2.0 * session_vwap_sd` above VWAP | short |
| VWAP reversion | close is at least `2.0 * session_vwap_sd` below VWAP | long |
| value-area continuation | close is above VAH after the previous completed M15 close was inside or below VAH | long |
| value-area continuation | close is below VAL after the previous completed M15 close was inside or above VAL | short |

The VWAP threshold is fixed at `2.0` standard deviations because that is the
registered `S5` value already present in `core.s5_vwap`. No 2.5-sigma variant,
half-target variant, or value-area width threshold is added here.

One completed M15 bar may generate at most one event. If both a VWAP and a
value-area condition fire on the same bar, VWAP reversion takes precedence. If
both sides are somehow true because of malformed features, the bar is invalid and
is counted in diagnostics, not traded.

Events are not deduplicated across nearby bars unless they occur on the same
completed M15 bar. Dependence is handled by UTC calendar-day clustering.

## 5. Exit geometry and costs

No exit search is permitted. Every event uses one common geometry:

```
entry       next contiguous M5 open after the completed M15 decision bar
stop        1.5 x the last fully known M15 ATR(14)
target      1.5 x ATR, RR 1:1
time stop   72 M5 bars
resolution  stop before target when both occur in one bar
```

This deliberately does not use VWAP itself as a moving target. A moving VWAP
target would create a second question about target mechanics and make controls
harder to interpret.

Per-trade net R charges the entry bar's recorded spread plus Amendment 08
round-turn commission of `0.140` and slippage of `0.0165` per fill. Missing or
non-positive spread falls back to `0.090`. Financing is charged if a path crosses
the account's daily swap boundary, skipping closed weekend days and charging the
Wednesday triple rollover. Net is reported at cost multipliers `1.0, 1.5, 3.0,
7.0`.

The primary matched-excess statistic is gross R because event and control share
the same geometry and cost environment. Absolute tradeability is judged only on
net R.

## 6. The control

Each event is compared with the Amendment 10 leave-one-day-out conditional mean:

- same direction
- same calendar quarter
- same Asia / London / NY session bucket
- same prior-only M15 ATR tercile
- same inside/outside 30 minutes of a USD HIGH release
- same hourly spread bucket
- identical stop, target and time stop
- the focal event's entire UTC calendar day removed from the pool
- at least 30 eligible control bars after that removal

The control bar must have enough forward M5 data to resolve its path without
crossing the non-holdout boundary. An unmatched event is reported and excluded
from matched excess, never rematched on fewer variables.

## 7. Primary statistics

There are two primary family-level tests, one for each mechanism:

1. VWAP reversion: mean matched excess of VWAP reversion events is greater than
   zero.
2. Value-area continuation: mean matched excess of value-area continuation
   events is greater than zero.

Each uses a UTC calendar-day clustered t statistic and a one-sided wild sign-flip
p-value with 10,000 draws and seed `20260922`. The two p-values are interpreted
with Holm correction at family alpha `0.05`.

The following are descriptive only and carry no selection rights:

- long versus short
- Asia, London and NY session rows
- distance-from-VWAP terciles
- inside-to-outside versus already-outside state
- net R at each cost multiplier
- one-position-at-a-time chronological policy

For each primary family, print the clustered standard error and the 80% minimum
detectable effect `(1.645 + 0.842) * SE` before interpreting the p-value.

## 8. Gates and rights

A mechanism is established only if all of these hold for its primary family:

1. at least 100 matched events and 50 active UTC days
2. matched excess above zero
3. Holm-adjusted one-sided p-value at most 0.05
4. net expectancy at 1.0x and 1.5x cost is at least `+0.05 R`
5. day-clustered 95% lower confidence bound on 1.0x net R is above zero

If VWAP reversion passes, it earns a later forward-shadow protocol for the exact
pooled VWAP reversion family. If value-area continuation passes, it earns the
same right for the exact pooled value-area continuation family. A side, session,
distance bucket or other descriptive subgroup cannot be promoted from this run.

If both pass, both may be written up as separate shadow protocols, but neither
may be combined into a portfolio rule without a new amendment.

## 9. What failure looks like

- adequate counts but non-significant matched excess -> the mechanism is not
  established
- positive gross excess but net below the gate -> the information, if any, is
  not tradeable at this account's friction
- counts below the gate or MDE too large for plausible effects -> NOT ASSESSED
- only one descriptive subgroup looks good -> no candidate
- VWAP passes and value area fails, or the reverse -> only the passing primary
  family may be discussed further

None licenses changing the VWAP anchor, sigma threshold, value-area percentage,
bin size, sessions, controls, geometry, cost model or holdout boundary.

## 10. Verification required before interpretation

The implementation must have tests that fail under each of these mutations:

1. VWAP or value area uses an M5 bar whose close is after the M15 decision time
2. a new 22:00 UTC anchored session carries volume or VWAP state from the prior
   session
3. a value-area calculation omits the highest-volume bin
4. entry occurs before the completed M15 decision bar is known
5. the M15 ATR mapped to the event has not yet closed
6. a control pool includes the focal UTC calendar day
7. a trade or control path crosses the non-holdout boundary
8. a descriptive subgroup is used to change the primary family result

The run is interpreted only after all tests pass. Code and result are committed
after this amendment's standalone commit.

## 11. Status while this runs

Unchanged. The engine's answer is **NO TRADE**. No real-money order is
authorised, no position is open, and no pull request is opened.

---

## 12. Result

Not run yet. This amendment is the protocol freeze.
