# Backlog — everything waiting, designed-but-unrun, and never touched

Built from the repository, not from memory. Each item says what it would test,
what it costs to do, and where the result would land. Both tails are reported
throughout: a losing tail is as informative as a winning one, and in this project
it has usually been the more honest of the two.

Last rebuilt 2026-09-22.

---

## A. Archived by operator decision

| # | item | blocked on | when |
|---|---|---|---|
| A1 | **W1 rollover slippage** | no longer active | operator decision on 2026-09-22: do not measure W1 rollover cost |
| A2 | **W1 forward shadow** | no longer active | operator decision on 2026-09-22: do not run W1 shadow |

Nothing else in this file is blocked. Everything below can run today.

---

## B. Designed and argued for — completion status inline

### B1 — Geometry-neutral path diagnostic — **COMPLETED, Amendment 13**

**What it tests.** Every search so far fixed RR at 1:1 and the stop at 1.5 ATR.
A setup with real directional information but the wrong barrier geometry looks
*identical* to a setup with no information, and nothing built so far can tell
those apart. This separates them without a combinatorial sweep.

**How.** For each entry, instead of one pass/fail outcome, measure the whole path
against the same matched placebo: signed return at fixed horizons, maximum
favourable excursion, maximum adverse excursion, time to the favourable extreme,
and the probability the favourable barrier is touched before the adverse one. One
simultaneous day-block permutation band across horizons.

**Both tails, and what each would mean.**

| what comes back | reading |
|---|---|
| path excess flat at every horizon, both tails | exit geometry cannot rescue anything — the five closures are about information, not barriers, and they get stronger |
| early favourable excursion that decays | the holding period or the target is wrong, not the signal |
| terminal return positive but adverse excursion large | **the stop was too tight all along** |
| favourable extreme large, terminal return zero | a target or trailing rule matters |
| candidate and placebo paths identical | changing RR only ever optimised noise |

**Cost.** One run on existing data. No new data, no orders.

**Why it is first.** It is retrospective on everything already closed. If it says
the stop was too tight, five closures need re-reading. If it says the paths are
flat, five closures become much harder to argue with.

### B2 — Session-level acceptance and rejection — **COMPLETED, Amendment 17**

**What it tests.** Whether price behaves differently at a *fresh* structural
level than at a *used* one. Everything tested so far is a transformation of OHLC
into an oscillator; this is a different information channel — where price sits
relative to structure other participants can see.

**The rule, as Codex framed it.** Levels: Asia high/low, pre-London high/low,
prior-day high/low. Touch state: first, second, third-or-later. Entry decisions:
rejection (an M5 close back inside after touching) or acceptance (close outside
and the next bar holds outside). Entry at the next bar's open.

**The multiplicity discipline that makes it affordable.** Touch count enters as an
**ordinal variable** with one pre-registered hypothesis — *the effect declines
monotonically with touch count* — rather than as dozens of separate candidates.
One test, not a zoo.

**Mechanism, nameable in advance.** Orders and stops accumulate at visible
session extremes; participation changes at session transitions; a first
interaction consumes resting liquidity that a fifth cannot.

**Both tails.** A monotone decline in either direction is a result. A flat
profile across touch counts says the level is not the variable.

**Cost.** One run on existing M5 and M15 data.

**Result.** Adequately measured and negative for the registered mechanism:
7,665 matched events over 681 days, common ordinal slope `+0.00008 R` per touch
step (SE `0.01408`, one-sided p `0.4990`; 80% MDE `0.03503 R`). The touch means
were not monotone. First touch itself had excess `−0.0158 R` and net `−0.0716 R`
at 1x cost. **No candidate and no shadow status.** Positive descriptive subgroups
may not be selected from the table.

### B3 — VWAP and value-area interaction — **COMPLETED, Amendment 18**

`core.s5_vwap` and `core.session_vwap` have existed since early in the project
and appear in **no search at all**. VWAP has a nameable mechanism (an execution
benchmark that real desks are measured against).

**Caveat, stated up front:** broker tick volume is a weak proxy for value area in
a decentralised market, so a value-area result would be about this broker's feed
as much as about gold. VWAP itself is less exposed to that than the value area is.

**Cost.** Low — the code exists.

**Result.** Adequately measured and negative under the registered gates. VWAP
reversion had matched excess `-0.0241 R`, Holm p `0.8937`, and net `-0.0801 R`.
Value-area continuation had a small positive gross excess `+0.0284 R`, but Holm
p `0.1312` and net `-0.0251 R`; it earns no candidate and no shadow status. The
best descriptive side row may not be selected.

### B4 — Current FOLLOW/FLIP edge scanner — **COMPLETED, Amendment 19**

This is an operational selector, not another permanent-edge claim. It re-scores
the 18 registered setups and six crowded-entry patterns in both their stated and
independently simulated opposite directions using only the latest 90 days. A
FLIP is eligible only when its FOLLOW source is currently losing. Recent-window,
shrinkage, real-cost, cost-stress, freshness and current-event gates are fixed in
Amendment 19.

**First result:** 48 arms evaluated and 10 READY. No READY event fired on the
latest closed M15 bar, so the actionable output was **NO_TRADE**. The scanner is
implemented in `research/pilot/current_edge.py`; this item is complete and is now
an operational tool rather than pending research.

Operational reports are implemented in `research/pilot/current_edge_ops.py`.
Run `--mode wednesday` for midweek observation and `--mode weekend` for
market-closed rebuild review. Supporting diagnostics live in
`research/pilot/current_edge_backtest.py` and
`research/pilot/current_edge_lead_traces.py`.

---

## C. Never touched at all

| # | item | why it might matter | what it needs |
|---|---|---|---|
| C1 | **CFTC positioning** | `calendar_feed.positioning_series` and `positioning_at` were written, and **no data file exists** — `data/` has no CFTC file. The code has never been fed. Weekly net positioning is the only crowding measure available and CLAUDE.md section 2 asks for it explicitly | a weekly CFTC gold series; until then every positioning field in `decide.py` and `current_signal.py` correctly reads NOT ASSESSED |
| C2 | **The M1 series, for anything but DXY** | `data/XAUUSD_M1.csv` is 65 MB and is used only for news reaction timing. W1 is a rollover-gap trade and M1 is where a gap's first minute actually lives — the M5 open hides it | nothing; the data is on disk |
| C3 | **H1/H4 state construction** | Amendment 11 varied how long a position is *held*. It never varied the timeframe the state is *computed on*. Those are different things, and a slower state has a structurally better cost-to-ATR ratio | nothing; resample existing data |
| C4 | **Real yields / DXY as a state, not a reaction** | DXY M1 and M5 are on disk and used only inside the news desk. Gold's relationship to the dollar is the single most cited mechanism in the instrument and it has never been a regime input | nothing for DXY. US yields: `NOT ASSESSED — no bond symbol on this account` |
| C5 | **Partial exits, trailing stops** | every result assumes one entry, one exit. Codex's ordering puts this *after* B1, because there is no point designing an exit for a path that has no structure | B1 first |
| C6 | **Entry timing inside the signal bar** | entry has always been the next bar's open. A limit a fraction of an ATR better, or worse, changes the cost arithmetic directly | nothing |
| C7 | **The other five setup families in `core.py`** | `s3_sweep`, `s4_failed`, `s6_expansion` exist in `core.py` and appear in **no search**. `s1_breakout` and `s2_pullback` were used; these three never were | nothing |
| C8 | **News acceptance/rejection as a setup** | CLAUDE.md section 2 asks for eight news scenarios. `newsdesk.py` assesses them descriptively; `news_acceptance` appears in **zero files** as a tradeable setup | the calendar is on disk |
| C9 | **Cross-timeframe agreement** | every tool is computed on M15 only. Nothing tests M5 structure against M15 state | nothing |
| C10 | **Weekly and monthly levels** | only prior-*day* levels were ever used, inside one Amendment 07 pattern | nothing |

---

## D. Closed, with both tails, for completeness

Recorded so nothing here is re-searched by accident. Full detail in
`docs/STATUS.md` and the amendments.

| what | losing tail | winning tail |
|---|---|---|
| **ORDERLY_TREND v2**, 6 assets | dev +0.0853 → holdout **−0.1359 R** | cross-asset pooled +0.1693 R, but the interval straddles zero → **failed replication** |
| **24 hand-built patterns**, direction-neutral | worst excess **−0.1848** (p 0.74, fails) | **`gap_continuation/short` +0.3483, t +3.18, p 0.033** → became W1 |
| **150 junk configurations** | worst **−0.2278** (p 0.80, fails); two kept sign on the untouched slice with mirror nets +0.18/+0.14 but failed on n=33/47 | nothing significant |
| **6,480 wide, 40 tools** | tier A worst **−0.2389**; nominal discoveries **0.60x** what chance produces | max\|t\| 2.425 vs critical 3.697 (p 0.854); **all five CONFIRM winners flipped sign** |
| **7 holding horizons, 1 h to 48 h** | no horizon shows family-level signal (p 0.58–0.85) | same — closure **strengthened** to "nothing at any horizon" |
| **horizon-mismatch mechanism** | fails on the two cases it was written for (99.7 %, 99.1 % of magnitude retained) | holds across the family: ρ **+0.10**, p 0.015 — real but explains ~1 % of variance |

---

## D2. Walk-forward — running, with the power limit accepted

**Corrected 2026-09-22.** An earlier note here said this line was paused. That was
a misreading of the operator, who said to run it with whatever data exists rather
than decline on grounds of low power. It is running.

Where they stopped: Amendment 14's grid and engine are built and verified (35
checks, all passing, including a mutated-engine look-ahead trap and a fast
resolver agreeing with `core.resolve` on 10,000 cases with zero differences).
Amendment 15 declared the walk-forward design. Codex reviewed it before execution,
**declined to run it**, and found ten protocol defects. All ten are accepted and
recorded as Amendment 16. **The code implementing those eleven corrections was not
written.**

Anyone resuming this should start from Amendment 16's numbered list, not from
Amendment 15, and should expect the corrected design to leave roughly **15 largely
independent six-roll blocks** from ~90 rolls — which may not be enough power to
answer the question at all. Amendment 16 section 13 requires the roll-level minimum
detectable effect to be reported before any null result is interpreted, precisely
so that outcome is reported as a finding rather than dressed up as one.

The correction in Amendment 15 section 1 stands regardless and applies to
everything above: the five closures were fitted to 2023–2024 and tested on 2025, so
they say "this did not work then", not "this does not work now". **W1 is the
exception**, being mechanical and unfitted to any window.

## E. The standing rules that shape this list

- **No more widening of the indicator grid.** Amendments 10 and 11 closed it. B2
  and B3 are admitted because they test a *different channel*, not more
  oscillators.
- **No timeframe, instrument or account change to rescue a failed candidate.** A
  cheaper account helps only if a gross advantage already exists. C3 is admitted
  as a state-construction question, not as a rescue.
- **Position sizing is never a substitute for edge.** Grid and Martingale stay
  prohibited.
- **Every item above needs its own amendment before it runs**, with its
  thresholds, its multiplicity accounting and its failure definitions fixed in
  advance.
