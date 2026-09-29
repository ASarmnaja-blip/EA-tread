# Long-history H1 edge search on Dukascopy 2003-2015 — pre-registration v1 (2026-09-29)

Operator approved 2026-09-29: "ทำเลย ผมตกลง ถ้าไม่ได้ให้หาแผนถัดไปด้วย".
Committed BEFORE `research/pilot/edge_search_h1.py` is run on real data.
Codex has not reviewed it; it audits afterwards.

## Why this is the first test that can mean something
Part 47/48 arithmetic: years needed to detect an edge = (2.8 / Sharpe)². The
5.2 years the project could measure see only Sharpe ≳ 1.2. Dukascopy gold
H1 (bid and ask OHLC) reaches 2003-05. The period **2003-05 .. 2015-12 has
never been used by any project result** (all earlier work is 2016-08 or
later; the Yahoo daily check compared 2016+ only). It gives 12.6 years,
smallest detectable Sharpe ≈ 0.79.

## Design (frozen)
- **Data:** Dukascopy XAUUSD H1 bid OHLC, zero-volume bars dropped (candles
  through `research/history/build_all_tf.py`). Run only after the cache reaches
  2015-12. The SHA-256 of the assembled arrays is printed and recorded.
- **Eras:** DEV 2003-05-05 .. 2012-12-31 (9.7 y); **CONFIRM 2013-01-01 ..
  2015-12-31 (3 y, untouched)**. 2016 onward is excluded from this test.
- **Signals:** the six families (breakout, pullback, sweep, failed, vwap,
  expansion) from `core.Ctx` with **unchanged code and parameters, applied to
  H1 bars**. This tests the same logic at 4× the time scale (a 20-bar high is
  20 hours, not 5); it does not test the M15 result and no parameter was tuned.
  Sessions use the fixed UTC hours of `core.session_of` (DST not modelled).
- **Outcome:** forward return in bp from the open of bar i+1 to the close of
  bar i+H, **H ∈ {1, 4} H1 bars**. Windows with a gap, a broken signal-to-entry
  step, an exit outside the era, or a 21:00 UTC rollover crossing are excluded.
  One position at a time per family (skip a signal within H bars of the last).
- **Cost for tradability:** **today's** Demo90 round trip, 0.80 bp — the
  question is whether an old edge would survive now, not in 2005 when spreads
  were wider. Actual historical Dukascopy spreads are reported descriptively.
- **Control (descriptive, ex-post — per Codex Round 7):** expected outcome of a
  random entry in the same ATR-decile × session bin in the same era, same
  direction. diff = d·(r − bin mean); cost cancels in diff.
- **Statistics:** week-clustered bootstrap, **10,000** resamples, add-one
  two-sided p (weeks = Unix-epoch 7-day blocks).

## Tests (54) — α = 0.05 / 54 = 0.000926
- **A1 (24):** family × H × {all ATR, top ATR third}: diff > 0 in DEV.
- **A2 (30):** the 15 chart instruments of Part 47 (atr_pct, dist_vwap_atr,
  dist_ema50_atr, dist_ema200_atr, dist_hh20_atr, dist_ll20_atr, ret1_atr,
  ret4_atr, ret16_atr, range_ratio, efficiency20, trend_sep, hour_utc,
  weekday, session) × H ∈ {1, 4}: out-of-era transfer, bins fitted on DEV,
  ρ measured on CONFIRM (and the reverse as a consistency check).
- **A1 PASS in DEV:** diff > 0, p < α, and mean net at 0.80 bp > 0.
  **CONFIRMED** needs DEV PASS **and** in the untouched CONFIRM era diff > 0,
  two-sided p < 0.05 and net > 0.
- **A2 LEAD:** DEV→CONFIRM p < α, same sign CONFIRM→DEV with p < 0.05, and
  implied gross edge 0.8·ρ·SD > 0.80 bp. A lead is a hypothesis for a *new*
  pre-registered rule, never itself a strategy.
- Self-check before the real run: random signals must reject at 1%-10%
  (100 draws), a planted +3 bp must be found. It validates the machinery
  coarsely only.

## Decision tree, fixed now
1. **Any CONFIRMED or LEAD →** freeze the rule in a new pre-registration, run it
   on 2016-2026 (descriptive) and log it forward with the ledger.
2. **Nothing → Plan B: daily-scale, drift-controlled, 26 years.** Yahoo GC=F
   daily 2000-2026 (already on disk) + Dukascopy D1 spot 2003-2026. Cost is
   negligible at daily horizons, so the question is pure information: time-
   series momentum / reversal of gold at 1-20 day horizons, volatility-managed
   exposure, calendar effects — each judged against an exposure-matched
   always-long control, since gold's +1,500% drift would otherwise fake any
   long-biased rule. Own pre-registration before running.
3. **Plan B nothing → Plan C: panel.** The same mechanism measured on many
   instruments (silver, indices, FX, other metals) at D1/H1 to multiply
   independent samples; only a mechanism that is general *and* present in gold
   is used. Own pre-registration.
4. **Plan C nothing → the honest conclusion:** on public data at 1 hour to 1
   week the gold market gives no detectable retail-implementable directional
   edge; WPWB stays a risk instrument and the search moves to non-price
   information the project does not have (positioning with real vintages,
   options data, order flow), which needs new data sources and the operator.

## Expected outcome, stated in advance
Prior: 0 of 54. The value is that a null on 12 years is decisive where a null
on 5 years was not.
