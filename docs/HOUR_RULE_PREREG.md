# Frozen hour-of-day rule tested on unseen eras — pre-registration v1 (2026-09-29)

Follows the decision tree of `docs/H1_LONG_HISTORY_PREREG.md` (a LEAD becomes a
frozen rule). Part 49 found one lead: the UTC hour of the signal bar predicts
the drift-removed 4-hour forward return (ρ = 0.040 DEV → CONFIRM). Committed
BEFORE `research/pilot/hour_rule.py` is run. Codex audits afterwards.

## The rule (frozen from 2003-05..2015-12 only)
- Fit era: all clean Dukascopy H1 2003-05-05 .. 2015-12-31. For each signal
  hour h (UTC hour of the bar whose close is known), take the mean 4-bar forward
  return (open of bar i+1 → close of bar i+4), overall mean removed, over valid
  windows (no gap, no 21:00 UTC rollover crossing). Hours with fewer than 300
  valid windows get no signal.
- **R24:** direction = sign of that mean, for every hour that has a signal.
- **Rt2:** only hours with |t| ≥ 2, t = mean / (SD / √(n/4)) (the /4 accounts for
  overlapping windows); direction as above.
- Trade at the open of the next bar, hold 4 bars, one position at a time (a
  signal within 4 bars of the last kept one is skipped). No stop, no target, no
  filter, no parameter beyond those above. The 24-sign map and the Rt2 hour set
  are printed and hashed by the script before any test data is read.

## Eras the rule has never seen
- **E1:** Exness H1 (built from the canonical + fresh M5, the operational feed),
  2021-07 .. 2026-09-28.
- **E2:** Dukascopy H1, 2016-01 .. 2020-12, **run only when the cache covers it**
  (the download is continuing). 2016 onward was used by the project for daily/
  weekly volatility and momentum tests, but never for this rule.
- Both are reported separately; they are not pooled.

## Statistics
- **Drift-controlled difference:** with q the long share of taken trades and fwd
  the raw 4-bar return of each taken trade, diff_i = fwd_i·(d_i − (2q − 1));
  mean(diff) removes any benefit from being long in a rising market.
- **Net:** mean(d·fwd) − 0.80 bp (today's Demo90 round trip).
- Week-clustered bootstrap (Unix-epoch weeks), 10,000 resamples, add-one
  two-sided p for diff; 95% interval for net. Year-by-year table and a per-hour
  contribution table for diagnosis only.
- Tests: 2 variants × 2 eras = 4.

## Pass rule
A variant **REPLICATES** in an era iff diff > 0, two-sided p < 0.05 **and**
net > 0. The rule counts as **alive** only if it replicates in **both** E1 and
E2. Replicating in one era only = **partly alive, unproven**. Replicating in
neither = **decayed**: an edge that existed in 2003-2015 and is gone, which is
itself the finding.

## Expected outcome, stated in advance
Part 47 measured this instrument at ρ < 0.01 in 2021-2026. Prior: decayed in E1
(probability ~ 75%). If it replicates, the size will still be small: ~0.6 bp net
per 4 h trade, about 1,000-1,500 trades a year, Sharpe of order 0.5, which is
undetectable forward in under ~30 years — so it could never earn ledger alpha by
forward observation alone; only more independent history can confirm it.
