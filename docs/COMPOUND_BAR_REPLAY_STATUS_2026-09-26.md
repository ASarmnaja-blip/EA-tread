# compound_bar_replay.py — status check, 2026-09-26

The operator asked about the bar-by-bar portfolio simulation Codex had started.
This is a technical status check, run by Claude on Codex's uncommitted work, not
a new research result of Claude's own.

## What it is

`research/pilot/compound_bar_replay.py` walks the M5 series one bar at a time,
marking every open position to Bid/Ask on every close, so overlapping positions
and floating drawdown are visible rather than summarized after the fact. It
compounds position size from monthly cash deposits and a first-year drawdown
calibration. This is the kind of simulation the operator asked for; nothing
before it in the project walked bars this way.

## State found

Not committed by Codex as its own work: it and five supporting files
(`evolution_portfolio_audit.py`, `evolution_candidate_validation.py`,
`canonical_history.py`, `minute_timeframe_extension.py`,
`m1_candidate_validation.py`, `weekly_macro_context.py`) appear in git history
only inside Claude's broad `git add -A` commits, never with a Codex commit
message or an amendment document. No test file exists for any of them.

## What runs

The pipeline executes end to end without error, using the existing
`--profile cent260` cache (`data/weekly_evolution_universe_v10_sp260_co000.pkl`,
built by Codex). It has **never been run with the project's standard Demo cost
model** (spread 0.090 + commission 0.140); that cache does not exist and would
require a full rebuild of the 8,250-cell universe.

## The finding that matters, from the run itself

The script's own built-in comparison — exclude the most recent 365 days versus
include everything — exposes the same concentration problem Amendment 20 already
found by a different method:

```
EXCLUDE_LATEST_365D  2022-01-01..2025-09-21 (44mo)  deposits $4,500  final $4,317-4,382   NET LOSS  -$118 to -$183
ALL_FORWARD          2022-01-01..2026-09-21 (56mo)  deposits $5,700  final $26,816-74,104 NET GAIN  +$21,116 to +$68,404
```

Adding twelve months and $1,200 of deposits turns a loss into a gain of five to
six figures. The entire profit is concentrated in the trailing year, consistent
with Amendment 20's own result (2022-2025 all lost; only 2026-to-date was
positive, and only thinly, +0.0051 R/trade).

**Compounding position size amplifies this rather than revealing it.** Max cent
lot grows from 1.36 to 42.97 across the "all forward" run as equity compounds, so
the one good year is sized far more heavily than the years that lost. The dollar
total is not evidence the strategy improved; it is largely a sizing artifact
riding one favourable year.

## What is required before this can be trusted

1. A test suite, on the pattern of `test_mtf_engine.py` — no-look-ahead trap,
   resampling correctness, cost monotonicity, at minimum.
2. A run against the standard Demo cost model, not only `cent260`.
3. Per-era reporting, exactly as Amendment 21 already committed to doing before
   any promotion, and exactly as this run's own before/after-365-days split
   shows is necessary.
4. The underlying weekly selector (`weekly_evolution_grid.py`) still uses the
   flat 56-day window Amendment 22 section 3.1 already flagged as non-compliant
   with the operator's decay-weighting rule. Fixing that comes first; a
   portfolio simulation on top of an unfixed selector inherits its defect.
5. An amendment written before any further run, per every other module in this
   project.

## Ownership

`weekly_evolution_grid.py` and everything downstream of it, including this file,
are Codex's per `docs/OWNERSHIP.md`. This document records a status check;
Claude has not modified or extended the code.

## Status

No real-money order sent. No live Demo parameter changed. NO TRADE.
