# Hypothesis batch 4 — regime-conditional champion selection (F1) — pre-registration (2026-10-01, before any statistic below is computed)

CLAUDE.md asks for champions that fit the CURRENT regime. WRWR v2 scores every candidate on its trailing shadow trades regardless of the
regime they happened in. Batch 4 tests whether scoring each candidate only on its shadow trades that were ENTERED in weeks of the same
regime class as the coming week improves out-of-sample results. Research only, paper only, no alpha.

## Construction (Family 2 candidate tables, gold and silver; everything else frozen as WRWR v2)
- Regime classes from the WRWR cell of each week (engine.regimes, known at the cut): variant **V** = volatility class (CALM / NORMAL / HIGH),
  variant **T** = trend class (DOWN / FLAT / UP).
- Shadow statistics by class: each candidate one-position shadow trade is binned by the cut at which its exit is known (as v2) AND by the
  class of its entry week. At cut k the score of a candidate = window LCB (same L, z, min 10 trades) over its trades whose entry week had
  the class of week k. Champions, pools, m, equity filter, C2 portfolio, costs, vol_scale: unchanged (run_family.run with these scores).
- 144 configurations per variant, f = 1 %, weekly R as v2.

## Out-of-sample procedure (no look-ahead in the configuration choice; identical for the conditional and the v2 family)
At the first cut of each year Y (gold 2010..2026, silver 2012..2026) adopt the configuration with the largest t-statistic of weekly net R over
the active weeks already known (R of week k is known at cut k+1); trade year Y (complete active weeks only).

## Endpoints
- **Primary (per variant):** the weekly OOS R of the conditional procedure minus the v2 procedure (same weeks), mean over gold 2010..2026,
  one-sided stationary-bootstrap p (mean block 10, K = 999, seed 20261001). Holm over the two variants (V, T).
- **PASS** = gold improvement Holm p <= 0.05, AND silver improvement > 0 with p <= 0.10, AND the conditional procedure mean weekly R > 0
  on both metals.
- Reported: totals, per-year R, compounded growth at 1 %, full-sample totals of the four SHADOW configuration indices under each variant.
