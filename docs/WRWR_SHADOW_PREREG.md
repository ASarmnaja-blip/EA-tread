# WRWR SHADOW record 1 — pre-registration (2026-09-30, before the first record)

Purpose: the WRWR gates (docs/WRWR_MANIFEST.md) are backtest-only. Family 2 passed endpoint 2 (Reality Check p = 0.003) but failed PBO and
the cost gate, so nothing is promoted. A SHADOW record collects real forward weeks for the configurations that showed selection skill,
spends NO alpha, places NO order, and produces the weekly WRWR champions the operator asked for. Paper only.

## What is recorded (frozen now)
- Configurations (fixed; indices of the frozen 144-configuration family, data/wrwr/family_XAUUSD_f2.npz / family_XAUUSD.npz):
  F2-66 (Family 2: 52w LCB z1, H1, m 2 = the BASE-equivalent), F2-78 (52w z1, H1+H4+D1, m 2), F2-134 (78w z2, H4, m 2),
  F2-86 (52w z2, H4, m 2), and the zoo BASE (52w z1, H1, m 2) as the reference.
- At every Friday 22:15 UTC cut (first: 2026-10-02): the WRWR regime cell, the forward vol_scale (frozen B_REF, contract C3 forward mode),
  and for each configuration the champions (up to 2) with candidate hash, description, score and eligibility, computed only from bars
  closed by the cut and trades exited by the cut. Written to the append-only hash-chained file data/wrwr/forward/champions.csv
  (canonical float formatting, previous-row hash) BEFORE the week's outcome exists; the record stores the code / data / cut digests.
- Weekly paper outcome: the frozen champion history is replayed through the C2 event-driven simulator (f = 1 %, $10,000, causal
  rules, C4 costs with Exness recorded spreads for Exness bars) -> weekly R, trades, skips, equity; appended to
  data/wrwr/forward/weekly_scores.csv once every trade of the week has exited or the data ends.
- Integrity: every run recomputes the whole champion history from the spliced bars and must reproduce the frozen rows bit for bit; a
  mismatch, a failed C5 check (including the splice validator with the v8 charged-cost rule), a code digest different from
  docs/WRWR_SHADOW_MANIFEST.md, or missing data closes the run (fail closed, logged, no row written).

## Reading rules (no alpha, no promotion)
- Reported per configuration: cumulative net R, weekly mean with a stationary-bootstrap 95% interval (block 10) once >= 26 weeks exist,
  drawdown, share of weeks traded, and the mean weekly R of the historical random-router benchmark of that configuration as a reference
  (forward d = weekly R - that mean; an approximation, stated as such).
- Nothing here changes any pre-registered gate. A forward mean whose 95% lower bound is > 0 after >= 52 weeks would be a reason to ask the
  operator about a formal alpha allocation (H-WRWR-*) with a fresh registration; it is not itself a confirmation.
- Roles: the champion file (strategist) is written before the week; scoring (auditor) is a separate step of the same script run the next
  Saturday; the Risk Manager rules are the frozen C2 rules.
