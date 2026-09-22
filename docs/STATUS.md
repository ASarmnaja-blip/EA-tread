# Research status — 2026-09-22

What has been tested, what is open, and what has not been touched. Written after
a status review with Codex. Kept short enough to stay true; the amendments hold
the detail.

---

## The honest headline

> **No persistent edge of economically useful size has been demonstrated in the
> tested XAUUSD M15 indicator-state space or in the bounded session-level
> acceptance/rejection experiment at this account's execution cost.**

That is narrower than "gold has no edge". The indicator results apply to the
tested entry definitions, M15 signal construction, next-bar execution, measured
cost model, and holding horizons from one hour to two days. Amendment 17 adds one
bounded M5-close experiment at three families of visible session levels; it does
not turn that result into a claim about all price structure.

**The five closures are not five independent replications.** They reuse the same
data and overlapping candidate families. The weight sits on Amendment 10, because
it was powered, and on Amendment 11, which removed the one fixed parameter that
could have hidden a time scale.

---

## 1. Closed

| # | what | verdict |
|---|---|---|
| 05/06 | `ORDERLY_TREND v2` — scale-aware regime, pullback, 1.5 ATR stop, 2R | dev +0.0853 R, holdout −0.1359 R. Cross-asset pooled +0.1693 R with HK interval [−0.2158, +0.5545] and prediction interval [−0.5468, +0.8855]. 6 of 7 criteria pass, the lower bound fails. **FAILED REPLICATION**, rare shadow candidate, never promoted |
| 07/08 | inverse search on 24 hand-built patterns, then re-scored direction-neutral | raw expectancies were a reading of gold's 126 % rise. Random long +0.0656 R, random short −0.0507 R, a gap of +0.1163 R wider than any pattern's own. On matched excess the family collapses to zero. **CLOSED** |
| 09 | junk-tool inversion, 150 configurations | median excess −0.0026, best p(maxT) 0.799. **CLOSED**. Two survivors went to the watchlist |
| 10 | wide two-tailed screen, 6,480 configurations, 40 tools | tier A max\|t\| 2.425 vs critical 3.697 (p 0.854), Berk–Jones p 0.900, nominal discoveries 0.60x chance. Tier B 0.62x chance. CONFIRM 0 of 10, and **all five winners flipped sign**. **CLOSED**, and powered: detectable effect 0.092 R at the 25th-percentile SE |
| 11 | holding horizon, 12 → 576 M5 bars | no horizon shows family-level signal (max\|t\| p 0.58–0.85 against Bonferroni α 0.0071). Closure strengthens to **nothing at any horizon from 1 h to 48 h**. Horizon mismatch is real but small (ρ +0.10, p 0.015 under a tool-clustered null) and **does not** explain the two watchlist entries it was written for |
| 17 | session-level acceptance/rejection at Asia, pre-London and prior-day levels | 7,665 matched events, 681 days. Ordinal touch slope **+0.00008 R** (SE 0.01408, one-sided p 0.4990; MDE 0.03503), and the touch means are not monotone. First touch excess −0.0158 R, net −0.0716 R at 1x. **MECHANISM NOT ESTABLISHED; NO CANDIDATE** |

## 2. Archived watchlist

| id | what | why it is not a candidate |
|---|---|---|
| **W1** | `gap_continuation/short` — excess **+0.3483 R** over a stratum-matched placebo, n=75, t +3.18, p(maxT) 0.0330 | found in a run pre-registered as exploratory; operator decision on 2026-09-22: **do not pursue W1 further**. No rollover measurement, no forward shadow, no promotion |
| **W2** | `rsi:40/short`, `emax:50-200/long` — mirror nets +0.1838 and +0.1424 R alive to 7x cost | fail at n=33 and n=47 against 50, and step-down maxT p 0.961 and 0.899. Their loss is now **unexplained** — Amendment 11 rejected horizon mismatch for both |

W1 was the only thing in this project that ever cleared a family-wise threshold,
but it is no longer an active work item.

## 3. Not tested

### Structure and levels — the real gap
Tested: round numbers (5/10/50), Donchian extremes (10/20/55), Bill Williams
fractals (2/3/5), prior-day high/low inside one Amendment 07 pattern.

**Now tested and closed as one bounded pooled mechanism:** session ranges (Asia
box, pre-London), prior-day levels, the **first-touch versus repeated-touch**
distinction, and acceptance versus rejection. Amendment 17 did not establish the
declared monotone decline and found no tradeable first-touch policy.

**Never tested:** VWAP and value-area bands (`core.s5_vwap` exists and was in none
of the three searches), volume-profile levels, weekly and monthly levels, classic
floor pivots, Camarilla, Fibonacci retracements.

Codex's ranking: **session-derived fresh levels first**, because the mechanism is
nameable — orders and stops accumulate at visible session extremes, participation
changes at session transitions, and a first interaction consumes resting
liquidity that a fifth does not. Static Fibonacci, pivots and Camarilla are low
priority. VWAP has a mechanism but broker tick volume is a weak proxy for value
area in a decentralised market.

### Barrier geometry
RR was **1:1 in every search** and 2R in `ORDERLY_TREND`. The stop was **always
1.5 ATR**. Entry was always the next bar's open. No partial exits, no trailing
stops, no position sizing of any kind.

This matters because a setup with real directional information but the wrong
barrier geometry looks identical to one with no information, and nothing built so
far can tell those apart.

### Other absences
The M1 series is used only for DXY news reactions. The CFTC positioning series
has never entered a search. Every tool is computed on M15 only — no cross-
timeframe state. H1/H4 **state construction** has never been tried; Amendment 11
varied how long a position is held, which is a different thing.

---

## 4. The next four steps, in this order

1. **A geometry-neutral path diagnostic**, for W2 and the strongest closed
   families. For each entry, measure the signed return at fixed horizons plus
   maximum favourable excursion, maximum adverse excursion, time to MFE, and the
   probability the favourable barrier is reached first — each against the same
   matched placebo, under one simultaneous day-block permutation band. This
   separates *no information* from *information at the wrong geometry* without a
   combinatorial RR-by-stop sweep, and it tells us whether a stop is too tight or
   a target wrong.
2. **Completed: the bounded session-level experiment is a powered global
   negative.** Do not rescue it by selecting the best descriptive subgroup.
3. **Start the next distinct untested channel: VWAP/value-area interaction.**
   This needs its own amendment before any run, with thresholds, multiplicity
   accounting and failure definitions frozen in advance.
4. **Stop the old indicator/state rescue loop.** Moving to H1/H4 state
   construction or another instrument is a separate research programme, not a
   rescue.

## 5. What this program will not do

- **No more widening of the indicator grid.** Amendments 10 and 11 close it.
  Adding oscillators, pairs or parameter variants now has a poor prior and only
  creates more chances to select noise.
- **No timeframe, instrument or account change to rescue a failed candidate.**
  Cost is not the whole story: the matched placebo pays the same cost, so an
  excess collapsing to zero means the tools are not selecting better price paths.
  A cheaper account helps only if a gross advantage already exists. Require the
  gross path advantage first.
- **No position sizing scheme, ever, as a substitute for edge.** Sizing cannot
  create or destroy per-trade expectancy. Grid and Martingale stay prohibited.

## 6. Standing state

17 amendments. No real-money order has ever been sent. No position is open. No
pull request is open. The engine's answer is **NO TRADE**.
