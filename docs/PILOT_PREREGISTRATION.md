# Setup-First Research Track — Pilot Pre-Registration

**Status: DRAFT, awaiting approval. Nothing has been run.**

Written before any result is seen, so the rules cannot be chosen after the
fact. Protocol v2 (`ENGINE_PROTOCOL.md`) governs; this file fills in what that
document left open for the first pilot.

The MQL5/EA work of Tracks 1.1–1.2 is paused, not reverted. Commits `a373bcd`,
`f3bcf4a` and `3be4542` and their 40 passing checks stand untouched.

---

## 1. What data actually exists in this container

Probed 2026-09-19. Outbound HTTPS works through the agent proxy.

### There is no XAUUSD spot data here

| Symbol | Exists | What it is | Currency | Exchange TZ |
|---|---|---|---|---|
| `XAUUSD=X` | **no** (HTTP 404) | — | — | — |
| `XAU=X` | **no** (HTTP 404) | — | — | — |
| `GC=F` | yes | **COMEX gold futures, Dec-2026 contract** | USD | America/New_York |
| `MGC=F` | yes | **COMEX micro gold futures, Dec-2026** | USD | America/New_York |
| `GLD` | yes | SPDR Gold Shares **ETF** | USD | America/New_York |

**Everything below is measured on COMEX gold futures, not on XAUUSD spot.**
No result from this pilot may be reported as an XAUUSD result. `GC=F` and
`MGC=F` were checked and are genuinely different series (57 of 200 closes
identical), so `MGC=F` is usable as an independent cross-check rather than an
alias.

### Resolution and span actually available (`GC=F`)

| Interval | Max span reachable | Raw bars | Usable (non-null) |
|---|---|---|---|
| 1m | **8 days** | 10,073 | 7,905 |
| 5m | **71 days** (`range=60d`) | 17,280 | ~13,660 |
| 15m | **71 days** (`range=60d`) | 5,760 | **4,554** |
| 1h | 184 days | 3,672 | 2,911 |
| 1d | 729 days | 505 | 503 |

90 days at 15m and 2 months at 5m are both rejected with HTTP 422, so 71 days
is the hard ceiling for intraday.

Window covered: **2026-07-10 to 2026-09-18**, 64 usable 15m bars per calendar
day.

### Data quality

- **Nulls are session closures, not corruption.** 21:00–22:00 UTC is 311/312
  null — the CME daily maintenance break. Every other hour is ~48/312 null,
  which is the weekend. Nothing suggests missing bars inside a live session.
- **No contract roll discontinuity** in the 71-day window: zero 15-minute moves
  above 25× the median absolute return. Median |15m return| 0.0724 %, max
  1.70 %.
- **Timezone**: timestamps are epoch seconds, converted to UTC throughout. The
  exchange reports America/New_York; no local-time arithmetic is used anywhere.
- **Prices are trades, not quotes. There is no bid, no ask, no spread.**

### What this makes impossible

| Requirement | Status |
|---|---|
| XAUUSD spot | **unavailable** — futures proxy only, labelled as such |
| Measured spread | **impossible** — no quote data. Cost is an assumption |
| Measured slippage | **impossible** — no fills. Cost is an assumption |
| M1-resolved exits over the whole window | **impossible** — 1m covers 8 of 71 days |
| Economic calendar / news state | not available here |
| Sealed holdout | untouched, and not used by this pilot |

---

## 2. The M1 problem, and what is proposed instead

Step 5 asks for M1-resolved exits. M1 reaches back 8 days; the study window is
71. Resolving exits on the signal bar is the error `RESEARCH_FINDINGS.md`
already documents: it inflated earlier work by +0.06R at 1.5R and +0.20R at 3R.

Three options, and the one proposed:

| Option | Cost |
|---|---|
| (a) restrict everything to the 8-day M1 window | sample so small that nothing is resolvable |
| (b) resolve on 5m across 71 days, assume the bias is small | an unmeasured bias in the headline number |
| **(c) resolve on 5m across 71 days, then re-run the 8-day overlap at M1 and report the difference** | one extra run, and the bias becomes a measured quantity |

**Proposed: (c).** Signals form on 15m, exits resolve on 5m for the full
window, and the last 8 days are re-resolved on 1m so the resolution bias is
reported as a number beside every result rather than assumed away. If the
measured bias is larger than the effect being claimed, the result is reported
as unresolvable at this data resolution.

---

## 3. Windows

All fixed in advance. Dates are the actual boundaries of the available data.

| Window | Length | Purpose |
|---|---|---|
| Context | 45 days | ATR percentiles, volatility regime, structure reference |
| Regime | 15 days | regime classification for the split-by-regime readout |
| Setup selection | 6 days | — see note |
| Validation | the most recent 15 days, never used for selection | the readout |

**Note on "selection": there is nothing to select.** Every rule in §4 is fixed
before the first run, with no parameter search. In the parameter sense the
entire 71 days is out of sample. The walk-forward folds below therefore measure
**stability across slices**, not out-of-sample performance after fitting — a
distinction worth keeping straight, because it is the one place a
pre-registered study is genuinely stronger than a tuned one.

**Walk-forward folds** (rolling, non-overlapping validation):

```
fold 1   train/context 2026-07-10..2026-08-09   validate 2026-08-10..2026-08-24
fold 2   train/context 2026-07-25..2026-08-24   validate 2026-08-25..2026-09-08
fold 3   train/context 2026-08-09..2026-09-08   validate 2026-09-09..2026-09-18
```

Three folds. Fold 3's validation slice is 10 days, not 15, because that is
where the data ends; it is reported with its own smaller n rather than padded.

---

## 4. Candidate setups

Six families. **One primary definition each, plus at most two variations.**
Every field below is fixed before the first run. Changing any of them after
seeing a result creates a **new registered configuration**; it does not edit an
existing one.

Common to all:
- Signals form on **15m closed bars**. No intrabar decisions.
- Entry is at the **open of the next bar** after the trigger bar closes.
- `ATR` means ATR(14) on 15m unless stated.
- **R = the stop distance.** Every setup risks exactly 1R by construction.
- Time stop: 24 bars (6 hours) unless stated.
- Sessions in UTC: Asia 00:00–06:00, London 07:00–12:00, NY 13:00–20:00.
  **21:00–22:00 UTC is never traded** (CME maintenance break).

### S1 — Breakout continuation
- **Premise**: price clearing a 20-bar extreme triggers resting stops and
  momentum orders, and the resulting flow carries it further.
- **Entry**: close > max(high, prior 20 bars) → long at next open. Mirror short.
- **Invalidation**: close back inside the 20-bar range.
- **Stop**: 1.5 × ATR.
- **Exit**: 2R target, or time stop.
- **Expiry**: must trigger on the bar immediately after the signal bar; 2 bars.
- **Session**: London + NY.
- **NO TRADE**: ATR percentile (200-bar) < 30.
- **Variations**: V1 lookback 40; V2 target 3R.

### S2 — Trend pullback
- **Premise**: in an established trend, a shallow retracement into value is
  where trend followers add, so the trend resumes from it.
- **Entry**: EMA50 > EMA200; price trades within 0.5 × ATR of EMA50 and then
  closes back above EMA50 → long at next open. Mirror short.
- **Invalidation**: close beyond EMA200 against the trade.
- **Stop**: 1.5 × ATR.
- **Exit**: 2R, or time stop.
- **Expiry**: 3 bars.
- **Session**: London + NY.
- **NO TRADE**: |EMA50 − EMA200| < 0.3 × ATR (no trend to pull back within).
- **Variations**: V1 pullback to EMA20; V2 target 3R.

### S3 — Liquidity sweep reversal
- **Premise**: a wick through a prior extreme that closes back inside took stops
  without follow-through, leaving the initiating side trapped.
- **Entry**: bar low < min(low, prior 20 bars) **and** close > that prior min →
  long at next open. Mirror short.
- **Invalidation**: a new extreme beyond the sweep extreme.
- **Stop**: sweep extreme ± 0.2 × ATR.
- **Exit**: 2R, or time stop.
- **Expiry**: 2 bars.
- **Session**: all except the break.
- **NO TRADE**: sweep depth > 1.5 × ATR.
- **Variations**: V1 lookback 40; V2 require the close in the far third of the
  bar's range.
- **Prior, stated up front**: this family was measured at **−0.202R on n =
  43,353** on XAUUSD 15m, and its full inversion also lost, which is the
  signature of a series with no directional information left. It is included
  because the mandate asks for it and because that measurement was on a
  different instrument and a different era — but the prior is strongly negative
  and a positive reading here needs correspondingly strong evidence.

### S4 — Failed breakout
- **Premise**: a breakout that fails traps the momentum buyers who chased it,
  and their exits push price the other way.
- **Entry**: a close beyond the 20-bar high occurred within the last 3 bars, and
  the current bar closes back inside the range → short at next open. Mirror long.
- **Invalidation**: a new high beyond the failed extreme.
- **Stop**: failed extreme ± 0.2 × ATR.
- **Exit**: 2R, or time stop.
- **Expiry**: 2 bars.
- **Session**: London + NY.
- **NO TRADE**: ATR percentile > 90.
- **Variations**: V1 lookback 40; V2 target = range midpoint instead of 2R.

### S5 — VWAP / value-area reversion
- **Premise**: in balance, price displaced far from the session's volume-weighted
  average is returned to it by two-sided flow.
- **Entry**: price > session VWAP + 2σ → short at next open. Mirror long.
- **Invalidation**: close beyond VWAP + 3σ.
- **Stop**: 1.2 × ATR.
- **Exit**: target = VWAP; time stop 24 bars.
- **Expiry**: 2 bars.
- **Session**: VWAP anchored to the CME session open, 22:00 UTC.
- **NO TRADE**: |EMA50 − EMA200| > 1.0 × ATR (trending, not balanced).
- **Variations**: V1 2.5σ; V2 target = VWAP ± 0.5σ.
- **Note**: futures carry **real traded volume**, unlike XAUUSD spot where the
  EA's own `VolumeProfile.mqh` discloses that it is one broker's tick count.
  VWAP is better founded on this proxy than it would be on the target
  instrument — which cuts both ways, and is recorded as a transfer risk in §8.

### S6 — Volatility expansion
- **Premise**: compressed ranges store energy, and the first decisive expansion
  out of compression continues in its own direction.
- **Entry**: ATR(14) in the bottom 25th percentile of the last 200 bars, then a
  bar whose range > 2 × ATR closes in the top (bottom) 25 % of its own range →
  long (short) at next open.
- **Invalidation**: close back inside the pre-expansion range.
- **Stop**: 1.5 × pre-expansion ATR.
- **Exit**: 2R, or time stop.
- **Expiry**: 1 bar — it triggers immediately or not at all.
- **Session**: all except the break.
- **NO TRADE**: expansion bar range > 4 × ATR (the move is already spent).
- **Variations**: V1 percentile 15; V2 target 3R.

### Configuration count

**6 primary + 12 variations = 18 registered configurations.** Each is assigned
a permanent id (`S1`, `S1V1`, `S1V2`, …) and written to a ledger before the run.
Per protocol v2 §3, the evidence required scales with the number of candidates
tested in the same regime window, so the multiplicity term for this pilot is
**k = 18**.

---

## 5. Cost model

Costs are **assumptions**, not measurements, because this data has no quotes.
They are reported as separate columns and never merged.

| Component | Value | Basis |
|---|---|---|
| spread | **$0.48 / oz** | OANDA measured 2023–2026 mean for spot, from `RESEARCH_FINDINGS.md` |
| commission | $0.00 | spot CFD convention; a futures column at $0.025/oz is reported beside it |
| slippage | **$0.10 / oz per fill** | one COMEX tick, assumed |
| **round-turn total** | **$0.68 / oz** | one spread + two fills of slippage |

At the current 15m ATR of **$6.33** and a 1.5 × ATR stop of $9.50, that is
**0.072 R per round turn**.

**Cost stress**: 1.5× → $1.02 (0.107 R); 2× → $1.36 (0.143 R). Both reported
for every configuration.

**No double counting.** Gross and net come from **two separate simulations**,
not from one plus an adjustment — at zero spread the break-even stop sits at
entry rather than one spread inside profit, and adding cost back afterwards
credits a break-even leg with a spread it never paid. That error is recorded in
`RESEARCH_FINDINGS.md` and is not repeated.

---

## 6. Evaluation

For every configuration, in every fold:

- **matched random control**: same trade count, same direction mix, same
  session distribution, random entry bars, identical exit logic. **Skill =
  setup − control.** No control, no reported number.
- **gross expectancy** (R), **net expectancy** (R), and the three cost
  components separately.
- **cost stress** at 1.5× and 2×.
- **trade count**, **MDE**, and an **uncertainty interval** from a 12-bar block
  bootstrap rather than a normal approximation, which is unreliable at these n.
- **split by regime** (trend / range / high-vol, from the context window) and
  **by session** (Asia / London / NY).

`MDE ≈ 2.8 × sd / √n` at 5 % two-sided and 80 % power. `sd` is **measured in the
pilot, not assumed** — it depends heavily on the target, and a 2R system and an
8R system have very different R-distributions.

---

## 7. Pilot pass/fail

**The pilot is a test of the pipeline, not a search for an edge.** It passes or
fails on whether the measuring instrument works.

| # | Criterion | Pass condition |
|---|---|---|
| P1 | **Calibration on a driftless random walk**, run before any real data is read | every one of the 18 configurations returns skill within ±0.02R of zero with \|t\| < 2 |
| P2 | **Look-ahead probe** | shifting entry one bar later degrades results in the expected direction; a result that does not move is a leak |
| P3 | **Completeness** | every configuration reports n, CI, MDE, and all five cost columns |
| P4 | **Cost reconciliation** | gross − (spread + commission + slippage) = net exactly, from two independent runs |
| P5 | **Resolution bias measured** | the 5m-vs-1m difference is reported as a number on the 8-day overlap |

**If P1 fails, no market result is read at all.** The instrument is fixed first.

### What a setup can earn from this pilot

At most **RESEARCH WATCH** (protocol v2 §3, `0.60 ≤ P < 0.75`). Nothing here can
reach SHADOW CANDIDATE, because that band requires the actual instrument and a
measured cost, and this pilot has neither.

---

## 8. What this can and cannot prove

### Can
- whether the pipeline is free of look-ahead, leakage and cost double-counting
- whether each setup family **fires at all** on current data, and how often
- the **shape** of each family's R-distribution, hence the sd needed to size
  every later test
- whether any family's skill-vs-control interval excludes zero on COMEX gold
  futures over 2026-07-10 to 2026-09-18, at an assumed cost
- how much the 5m-vs-1m exit resolution is worth, as a measured number

### Cannot
- **anything about XAUUSD spot.** Different instrument, different microstructure,
  different cost. A futures result is a hypothesis about spot, not evidence
  about it.
- **anything about real cost.** No quotes, no fills. Every cost figure is an
  assumption, and the 2× stress column exists because of that.
- **anything durable.** 71 days is one regime, possibly less.
- **S5 transfer.** Its premise rests on real traded volume, which the target
  instrument does not have.
- **statistical significance at small n.** At 2R targets an sd near 1.0R is
  plausible; a 15-day validation slice yielding ~30 trades then carries an MDE
  near **0.5 R**, larger than any plausible edge. Most configurations are
  therefore expected to return INCONCLUSIVE, and that is the correct outcome,
  not a failure of the setups.

### Standing prohibitions for this track
- no real-money orders, and none proposed
- the sealed holdout is not opened
- no confidence number is reported for anything that has not been fitted to
  realised outcomes
- results on `GC=F` are never labelled XAUUSD
