# Handover to Codex — 2026-09-22

The operator is near his weekly limit and has asked that the work pass to Codex.
This is the complete state. It is written to be acted on without me.

---

## 1. The one thing that is alive

**W1 — `gap_continuation/short`.** The only candidate in this project that ever
passed a pre-registered test.

```
rule (FROZEN, docs/AMENDMENT_12): on M15, open[i] - close[i-1] <= -0.5 * ATR(14)
     -> SHORT at the next M5 open, stop 1.5 ATR above, target 1.5 ATR below
     (RR 1:1), time stop 72 M5 bars, one position at a time

cost mult   net R     se      t    95% lower
    1.0    0.2573  0.1090   2.36     0.0437
    1.5    0.2346  0.1089   2.15     0.0212
    3.0    0.1665  0.1088   1.53    -0.0468
    7.0   -0.0152  0.1101  -0.14    -0.2309   <- dies here
```

76 trades over 3 years, 64 % wins, matched excess +0.3505 R (t +3.16) under the
leave-one-day-out control. Holdout, caveated and not confirmation: 10 events,
net +0.3797 R.

### What blocks it, and it is one measurement

W1 is **not a general gap trade**. 66 % of its entries are at 22:00 UTC, 33 % at
23:00, 47 of 76 on Mondays, and 75 of 76 follow a time gap over four hours. It is
a **rollover-gap trade**. The slippage floor the whole project charges — 0.0165
per fill — **was measured in liquid hours**, and W1 dies at 7x cost.

**A one-time scheduled task was set to measure it at 21:52–22:03 UTC on
2026-09-22.** `tools/rollover_cost_probe.py --seconds 600 --probes 4 --orders`.
Phase 1 watches quotes and sends nothing; phase 2 sends four minimum-volume demo
round trips at the reopen. If the operator's app was closed the task fires on next
launch — **check `data/rollover_cost.json` before re-running it, and only run it in
that UTC window.** Running it at any other hour is not the measurement.

**The verdict arithmetic, to be computed and not asserted:** W1's gross is
+0.3027 R. `net = 0.3027 - (measured round-turn cost / R)` with `R = 1.5 * ATR`.
If that falls below +0.05 R, W1 is dead and gets recorded dead on
`docs/WATCHLIST.md`. **Amendment 12 section 7 forbids proposing any change to the
gap threshold, stop, target or time stop to save it.**

### Also running

`research/pilot/w1_shadow.py`, 5x daily via the app scheduler, read-only, never
sends an order. Stopping rule frozen in `data/w1_shadow_protocol.json`: 26 weeks
from the first forward signal **or** 30 events, whichever comes **second**. It has
zero events so far, which is expected at ~25 a year.

---

## 2. The walk-forward result, and why it is the most important number here

Ran today with all eleven of your corrections. **Your refusal to run the first
version was correct twice over:** two corrections turned out to be quantitatively
enormous.

```
89 rolls, 15 independent six-roll blocks, 8,240 of 8,250 cells had enough trades

embargo purged       139,454 trades, 1,567 per roll
duplicates collapsed 1,274 cells per roll
```

Without correction 1 those 1,567 trades per roll would have leaked forward
information into every ranking. Without correction 7 the top five would have been
stuffed with copies of one realised strategy.

### The MDE, which is the finding

```
sd per roll              0.8325 R
block-level SE           0.2150 R
MDE at 80 % power        0.5342 R
```

**Nothing in this project is remotely 0.53 R.** W1's entire edge is +0.26 R. So:

```
to detect an effect of 0.05 R  ->  ~281 years of data
                       0.10 R  ->  ~70 years
                       0.26 R  ->  ~10 years
```

> **The recorded finding is NOT "adaptive selection does not work". It is "this
> sample cannot answer the question", per Amendment 16 section 15.2.** Reading the
> non-significant numbers below as evidence against transfer is the specific error
> that section forbids.

### The numbers, for the record

```
PRIMARY  D = mean(Top5 fwd) - mean(Bottom5 fwd)
  mean +0.0762 R   median -0.0054   48 % of rolls positive   p = 0.1982

U = Top5 - Mid5      +0.0261 R   joint p 0.8845
L = Bottom5 - Mid5   -0.0501 R   joint p 0.6421

decay, days      1        3        5       10       20
  D         -0.0261  -0.1273  +0.0706  +0.0762  +0.0433
  p          0.5834   0.8591   0.2368   0.2248   0.3227
```

### Your correction 9 was right, and my own check initially misread it

```
selection-window trades:  Top5 28.0   Mid5 135.9   Bottom5 38.9
the middle holds 4.8x more trades than the winning tail, 3.5x more than the losing
```

**The tails are low-count, high-variance cells. This experiment measured variance
hunting, not edge selection**, exactly as you warned. My first automated check
compared the tails to the 15-trade *floor* instead of to the *middle* and printed
"not clustered"; that reading is wrong and the code and commit both say so now.

A shrinkage or lower-confidence-bound selector is the obvious next selector and
**requires its own amendment written before it runs**. It must not be substituted
retroactively into this result.

---

## 3. What is closed, and the correction that reframes all of it

Five closures: `ORDERLY_TREND v2` cross-asset (failed replication), 24 hand-built
inverse patterns, 150 junk configurations, 6,480 wide two-tailed cells, seven
holding horizons. Detail in `docs/STATUS.md`.

**Amendment 15 section 1 requalifies every one of them.** They were fitted to the
**first** 730 days and tested on 2025, with the most recent 120 days withheld. So
they say *"this did not work in 2023–2024"*, not *"this does not work now"* — which
is a materially weaker claim than how they were originally written. No closure is
withdrawn; all are requalified.

**W1 is the exception and it matters:** it is mechanical and unfitted to any
window, so its cost test does not carry this defect.

Two results worth not losing:

- **all five CONFIRM winners of the 6,480-cell search flipped sign** on the
  untouched slice. The top of a large grid regresses *through* zero, not toward it.
- the wide search's nominal discoveries came in at **0.60x what chance produces** —
  the family is quieter than noise.

---

## 4. The backlog, ranked

`docs/BACKLOG.md` has all of it. The order I would keep:

1. **W1's rollover cost measurement** — blocks a live candidate, one measurement.
2. **Session-level acceptance/rejection** (B2). Asia / pre-London / prior-day
   levels, **touch count as an ORDINAL variable** with one pre-registered
   hypothesis that the effect declines monotonically with touch count. This is a
   different information channel from everything tested so far, which has all been
   OHLC-to-oscillator. You ranked it first among untested hypothesis classes.
3. **VWAP** (B3) — `core.s5_vwap` has existed since early on and appears in **no
   search at all**.
4. The M1 series for W1's first minute (C2) — 65 MB on disk, used only for DXY news
   timing, and a gap's first minute lives on M1 where the M5 open hides it.

Explicitly **not** recommended: more indicator grid. Amendments 10, 11 and 13
closed it, and the path diagnostic found the tier-A aggregate flat.

---

## 5. Rules that do not change

- **no real-money order, ever, without the operator's explicit confirmation**
- demo orders only under `data/DEMO_ORDER_PERMISSION.md`, verified at runtime:
  demo account, minimum volume, stop loss attached to the order, one position,
  closed within seconds, labelled `EXECUTION TEST ONLY`, P&L never counted as
  strategy performance
- **no PR** until there is evidence ready to inspect
- no Grid, no Martingale, no averaging. Position sizing cannot create or destroy
  per-trade expectancy
- **NOT ASSESSED rather than a guess** — the CFTC positioning code exists with no
  data file, and every positioning field correctly says so
- every search gets **its own amendment, written before it runs**, with its
  thresholds, multiplicity accounting and failure definitions fixed in advance
- the 120-day holdout is spent for diagnosis and **may never be used for
  promotion**

## 6. Tooling notes

- Python: `C:\Users\66985\AppData\Local\Programs\Python\Python312\python.exe`, and
  `PYTHONIOENCODING=utf-8` is required or Thai output mojibakes
- git is at `C:\Program Files\Git\cmd` and not on PATH
- `core.autocrlf` must stay `false` — with it true the mutation harness reports a
  false pass
- `research/pilot/test_mtf_engine.py` — 35 checks, all passing. Run it after any
  change to `mtf_engine`. Check 1 mutates the engine to peek one bar ahead and
  requires the mutant to be CAUGHT; check 9 verifies the fast resolver against
  `core.resolve` on 10,000 cases with zero tolerance
- 100+ commits, working tree clean, no PR, no open position, no real-money order
  ever sent

## 7. The honest summary

One mechanical candidate is alive and blocked on a single measurement that can only
be taken in a one-hour window. Five fitted candidates are closed, and all five
closures are about 2023–2024 rather than about now. The adaptive-selection question
turned out to need decades of data to answer at the effect sizes that matter, which
is itself the most useful thing learned today.

The engine's answer remains **NO TRADE**.
