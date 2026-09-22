# Amendment 21 — Weekly evolutionary baseline

**Run 2026-09-22.  Exploratory baseline; not a live promotion.**

## Objective

Replay the operator's intended weekly evolution: at the post-close weekly
boundary, choose the currently strongest available tool from a broad, fixed
menu; hold that choice for the next seven calendar days; then repeat from the
first continuous XAUUSD history to the present.

## Candidate menu and timing

The menu is Amendment 14's pre-existing 8,250 cells: six signal families,
M5/M15/M30/H1/H4 state, five stops, five targets, and market or limit entry with
five expiry choices.  Thus the selector can change signal, timeframe, entry,
stop, target and expiry; it cannot invent an after-the-fact rule.

At each Friday 22:15 UTC / Saturday 05:15 Bangkok boundary, only trades entered
in the preceding 56 calendar days **and fully resolved before the boundary**
are rankable.  A cell requires 20 trades on eight active days.  The score is its
mean net R minus 0.75 standard errors.  The next seven days are forward-only.
Each realised entry signature receives one ranking seat, so barrier variants
with the same entry set cannot multiply their chances of selection.

Costs use the Demo raw-account floor: 90 points (`0.090`) spread, `0.140`
round-turn commission, `0.033` slippage, and existing swap accounting.

## Baseline result

From 2021-03-05 to 2026-09-21, the replay made 290 weekly decisions with no
idle week.  It changed the champion 212 times.  The forward trades were:

| trades | net R | mean R | win rate | PF | trade-sequence max DD | max losing streak |
|---:|---:|---:|---:|---:|---:|---:|
| 1,757 | +248.785 | +0.1416 | 45.8% | 1.242 | -46.198R | 19 |

The same-week median unique cell returned `+0.0148 R` per week; the selected
top cell returned `+0.0716 R`, a difference of `+0.0568 R` in 52.8% of weeks.

## What the result does and does not show

There is no future outcome in a weekly ranking: 476,508 candidate outcomes that
had not resolved before their selection boundary were purged.  The underlying
execution/resampling engine also passes its 35 checks, including a deliberately
mutated look-ahead trap.

This is nevertheless not ready to promote.  A 73% weekly champion-change rate
is churn, not yet an intelligible regime transition.  The reported drawdown is a
trade-sequence drawdown, not a portfolio drawdown with simultaneous positions
across a weekly boundary.  The full period has now been inspected, so the next
work must report performance by era and run a separately specified
price/DXY/COT/news-context challenger against this baseline; it may not quietly
tune the baseline after reading this result.  Scheduled news is a known
catalyst/risk input before release; actual-versus-forecast and the price reaction
become usable only after release.

## Reproduction

```powershell
python research/pilot/weekly_evolution_grid.py
```
