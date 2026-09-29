# Edge search in basis points, with an ATR gate — pre-registration v1 (2026-09-29)

Written and committed BEFORE the script `research/pilot/edge_search_bp.py` is
run on the real signals. Operator request: test "fire only when ATR is not
low" together with the edge search. Codex has not reviewed this draft; it will
audit the code and result afterwards, and any change it causes is a new
version with its own test count.

## Why this replaces the R-based searches
Part 45: the six families fire at very different ATR levels (expansion 78% in
the bottom ATR third, breakout 59% in the top third), so R = move / (k × ATR)
is biased between −12% and +36% by family. Here every quantity is in **bp of
entry price** (1 bp = 0.01%), with **no stop bracket** and an **ATR-matched
control**.

## Design (all frozen)
- Data: canonical M5 → M15 (the engine's own `core.Ctx` signals for breakout,
  pullback, sweep, failed, vwap, expansion). Signals are from CLOSED bars;
  entry at the next bar's open.
- Outcome: signed forward return in bp from that open to the close of bar
  i+H, **H ∈ {4, 16} M15 bars (1 h, 4 h)**. Positions crossing the 21:00 UTC
  rollover or a gap are excluded, so swap never enters. One position at a
  time per family (a signal within H bars of the previous kept one is skipped).
- Cost: Demo90 round trip $0.263/oz (spread floor 0.09 + commission 0.14 +
  slippage 2 × 0.0165), converted to bp at entry price.
- **Control (removes drift and the ATR geometry):** for every signal in bin b
  the expected outcome of a random entry in the same bin, same direction,
  same era. Bin = ATR percentile decile (causal 200-bar rank) × session. So
  diff = d·(r − mean r in bin). Cost cancels in diff; net profitability is
  therefore also required.
- Eras: DEV 2021-07..2023-12; LATER 2024-01..2026-09. Both were already mined
  by earlier project work, so **neither is a clean holdout**. LATER is a
  consistency check only. Confirmation needs the 2009–2021 Dukascopy era (H1
  only, so it requires an H1 re-implementation) and forward weeks.
- Statistics: week-clustered bootstrap (4,000 resamples) of the mean diff;
  add-one two-sided p.

## Hypotheses (24, Bonferroni α = 0.05 / 24 = 0.00208)
- **A (12):** family × H, all ATR levels: diff > 0.
- **B (12):** family × H, **only signals in the top ATR third** (the
  operator's gate): diff > 0.
- A test PASSES in DEV iff diff > 0, p < 0.00208 **and** mean net bp > 0.
- A passing test is reported as *candidate* only if LATER also has diff > 0
  and mean net bp > 0. Nothing else is called an edge.
- The tercile table (bottom / middle / top ATR) is descriptive: it answers
  whether the edge grows with ATR, but is not a hypothesis test.
- Pipeline self-check before reading results: 30 random-signal draws must
  reject at about 5% (null), and a planted +4 bp must be detected.

## Expected outcome, stated in advance
Every earlier family failed a real-versus-random test. The prior is that all
24 fail. The value of this run is the measurement itself: how large the
family-vs-matched-control difference is, and whether it grows with ATR.
