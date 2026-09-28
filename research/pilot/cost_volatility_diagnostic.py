"""Amendment 30 exploratory diagnostic (pre-registration support ONLY).

NOT a pre-registered test and NOT a decisive result. Read-only. This exists
to answer one narrow question before docs/AMENDMENT_30_COST_VOLATILITY_GATE_
DESIGN.md's gate is frozen: in this project's own Demo90 cost model and its
own canonical XAUUSD history, does the same fixed dollar execution cost
actually become a materially larger fraction of R in low-ATR-percentile
regimes than in high-ATR-percentile regimes, at the exact stop multiples
Amendment 14/24 already use -- and by how much? That is a premise check, not
a strategy backtest: it has no entries, no setups, no P&L, and it decides
nothing about whether any setup has edge.

Two independent parts:

  PART A -- closed-form / algebraic. Needs NO market data. Amendment 24's own
  gate formula (docs/AMENDMENT_24_COST_TO_R_GATE.md section 3) is:

      execution_friction_price = max(spread, 0.090) + 0.140 commission
                                  + 2 * 0.0165 slippage        (= $0.263)
      cost_to_R = execution_friction_price / (stop_ATR_multiple * ATR)

  This is evaluated over a grid of ATR-in-price-units, at each of Amendment
  14's five frozen stop multiples (0.75/1.0/1.5/2.0/3.0), at base and 1.5x
  stress cost, against both Amendment 24's frozen flat gate (<=1/12 base,
  <=1/8 stress) and Amendment 30's proposed regime-conditioned step gate.
  This part always runs; it is arithmetic on frozen constants imported
  directly from research/pilot/mtf_engine.py, not a re-derivation.

  PART B -- empirical bucketing on the real canonical history, reusing
  Amendment 28's already-audited causal regime measure exactly
  (research/pilot/regime_standaside.py: build_regime_series /
  regime_percentile_at -- median H1 ATR over the trailing 20 trading days,
  ranked within the trailing 365-day H1 ATR distribution). For a fast
  EXPLORATORY look only, this part evaluates that percentile once per
  calendar day (forward-filled causally to every M5 bar in the following
  day) rather than continuously -- a deliberate resolution/cost tradeoff for
  a diagnostic, NOT the cadence proposed for the frozen decisive test (see
  the design doc, which specifies per-trade/per-signal cadence using the
  same regime_percentile_at function called at the signal's own timestamp).

  PART B requires data/canonical_XAUUSD_M5.npz, which is Amendment 20's
  frozen, gitignored research snapshot. If that file is not present in this
  environment, PART B prints NOT ASSESSED and exits 0 rather than fabricating
  numbers or substituting a different data source.

No MT5 connection. No order-sending path. No look-ahead: PART B only ever
reads bars strictly before the cutoff it is scoring, via the same
regime_percentile_at causality already audited for Amendment 28.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtf_engine as E                      # frozen Demo90 cost constants
import core as C5                           # atr()

STOPS = E.STOPS                             # (0.75, 1.0, 1.5, 2.0, 3.0)
A24_BASE_MAX = 1.0 / 12.0                   # frozen, Amendment 24 section 3
A24_STRESS_MAX = 1.0 / 8.0                  # frozen, Amendment 24 section 3

# Amendment 30 candidate step-gate multiplier applied to the A24 ceiling
# below the regime_percentile cutoff. THRESHOLD reuses Amendment 28's own
# frozen, not-tuned-to-this-result cutoff (0.40) rather than searching for a
# new one. MULT is a round, pre-declared number, not fit to any outcome --
# see the design doc section on candidate functional forms for why 0.5 was
# picked over the alternatives that were also considered and rejected here.
A30_THRESHOLD = 0.40
A30_MULT_BELOW = 0.5


def gate_friction_price(spread: float = E.SPREAD_FALLBACK) -> float:
    """Amendment 24 section 3's execution_friction_price, at the measured or
    floor spread."""
    return max(spread, E.SPREAD_FALLBACK) + E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL


def cost_to_r(atr_price: float, stop_mult: float, stress: bool = False) -> float:
    friction = gate_friction_price()
    base = friction / (stop_mult * atr_price)
    return 1.5 * base if stress else base


def a30_ceiling(regime_percentile: float | None, stress: bool = False) -> float:
    """Amendment 30's proposed step-gate ceiling: the A24 ceiling, halved
    when the causal regime_percentile is below 0.40 (or unknown -- treated
    as unfavourable, same convention as Amendment 28)."""
    base_ceiling = A24_STRESS_MAX if stress else A24_BASE_MAX
    if regime_percentile is None or regime_percentile < A30_THRESHOLD:
        return base_ceiling * A30_MULT_BELOW
    return base_ceiling


# ============================================================== PART A
def part_a() -> None:
    print("=" * 78)
    print("PART A -- closed-form cost/R vs ATR, Demo90 costs (always runs, no data)")
    print("=" * 78)
    friction_base = gate_friction_price()
    print(f"execution_friction_price (base) = ${friction_base:.3f}  "
          f"(spread floor {E.SPREAD_FALLBACK} + commission {E.COMMISSION_RT} "
          f"+ 2x slippage {E.SLIP_PER_FILL})")
    print(f"execution_friction_price (1.5x stress) = ${1.5 * friction_base:.3f}")
    print(f"Amendment 24 frozen ceiling: base <= {A24_BASE_MAX:.4f}  "
          f"({1/A24_BASE_MAX:.0f}x), stress <= {A24_STRESS_MAX:.4f} "
          f"({1/A24_STRESS_MAX:.0f}x)")
    print()
    print("Reference points already published in this project (NOT fitted "
          "here, cited for scale): Amendment 24's gate widened the median "
          "ACCEPTED stop to $4.68 in the low-active/high-cost-share 44-month "
          "window vs $6.00 in the trailing 12 months (docs/AMENDMENT_24_"
          "RESULT.md section 4) -- a ~22% smaller typical stop in the window "
          "that failed. The ATR grid below deliberately spans below and "
          "above both figures.")
    print()

    atr_grid = [0.5 * i for i in range(2, 17)]   # $1.00 .. $8.00
    header = (f"{'ATR $':>7s}" +
              "".join(f"{'s='+format(s, 'g'):>10s}" for s in STOPS))
    for label, stress in (("base", False), ("1.5x stress", True)):
        print(f"-- cost/R, {label} --")
        print(header)
        for atr_price in atr_grid:
            row = f"{atr_price:7.2f}"
            for s in STOPS:
                ratio = cost_to_r(atr_price, s, stress=stress)
                ceiling = A24_STRESS_MAX if stress else A24_BASE_MAX
                mark = "" if ratio <= ceiling else "*"
                row += f"{ratio:9.4f}{mark}"
            print(row)
        print("  (* = fails Amendment 24's frozen flat gate at this cost level)")
        print()

    print("Same grid under Amendment 30's proposed step gate, shown at two "
          "illustrative regime_percentile readings (p=0.20 < 0.40 threshold, "
          "p=0.80 >= threshold) -- this is the mechanism this design adds:")
    for p in (0.20, 0.80):
        print(f"\n  regime_percentile = {p}")
        for label, stress in (("base", False), ("1.5x stress", True)):
            ceiling = a30_ceiling(p, stress=stress)
            print(f"    {label} ceiling = {ceiling:.4f} "
                  f"({'HALVED vs A24' if p < A30_THRESHOLD else 'same as A24'})")
            fails = [atr_price for atr_price in atr_grid
                     if any(cost_to_r(atr_price, s, stress=stress) > ceiling
                            for s in STOPS)]
            print(f"    ATR levels in ${atr_grid[0]:.2f}-${atr_grid[-1]:.2f} "
                  f"grid where at least one stop multiple would now fail: "
                  f"{len(fails)}/{len(atr_grid)}")
    print()
    print("Reading: this part is pure arithmetic on frozen constants -- it "
          "shows the MECHANISM is well-defined and does what it claims (more "
          "rejections at the same ATR when regime_percentile is low), not "
          "that the mechanism finds real edge. Only Part B (real data) and "
          "the pre-registered real-vs-random test in the design doc can "
          "speak to that.")
    print()


# ============================================================== PART B
def part_b() -> None:
    print("=" * 78)
    print("PART B -- empirical regime_percentile vs cost/R bucketing (needs data)")
    print("=" * 78)
    canonical_path = Path("data/canonical_XAUUSD_M5.npz")
    if not canonical_path.exists():
        print(f"NOT ASSESSED -- {canonical_path} not found in this "
              f"environment.")
        print("Re-run this script on a machine where the canonical snapshot "
              "is present and paste the resulting table into the design "
              "doc's diagnostic section before Amendment 30 proceeds to "
              "review.")
        return

    import historical_regime_walkforward as hist
    import regime_standaside as RS

    b5 = hist.load_history()
    print(f"loaded canonical M5: {len(b5):,} bars, "
          f"{b5.t[0]} .. {b5.t[-1]}")

    atr5 = C5.atr(b5, 14)
    h1_t, atr_h1 = RS.build_regime_series(b5)

    # Daily cutoffs (exploratory cadence only -- see module docstring for why
    # this differs from the per-trade cadence proposed for the frozen test).
    day = b5.t // 86_400
    day_change = np.flatnonzero(np.diff(day) != 0) + 1
    cutoffs_idx = np.concatenate(([0], day_change))
    cutoffs_t = b5.t[cutoffs_idx]

    pct_by_day: dict[int, float | None] = {}
    for t in cutoffs_t:
        d = int(t // 86_400)
        pct, _ = RS.regime_percentile_at(h1_t, atr_h1, int(t))
        pct_by_day[d] = pct

    # Forward-fill each bar's day to the most recently computed (strictly
    # causal -- computed AT the start of that calendar day, using only prior
    # H1 bars) percentile.
    bar_pct = np.array([pct_by_day.get(int(t // 86_400)) for t in b5.t],
                       dtype=object)

    buckets = [(-1.0, 0.0, "no-history"), (0.0, A30_THRESHOLD, "< 0.40 (A30 tightens)"),
               (A30_THRESHOLD, 1.01, ">= 0.40 (unchanged from A24)")]

    print(f"\n{'bucket':>28s}{'n_bars':>10s}" +
          "".join(f"{'s='+format(s, 'g')+' base':>14s}" for s in STOPS))
    for lo, hi, label in buckets:
        if label == "no-history":
            mask = np.array([p is None for p in bar_pct])
        else:
            mask = np.array([p is not None and lo <= p < hi for p in bar_pct])
        n = int(mask.sum())
        row = f"{label:>28s}{n:10,d}"
        atr_bucket = atr5[mask]
        atr_bucket = atr_bucket[np.isfinite(atr_bucket) & (atr_bucket > 0)]
        for s in STOPS:
            if len(atr_bucket) == 0:
                row += f"{'n/a':>14s}"
                continue
            ratios = gate_friction_price() / (s * atr_bucket)
            row += f"{np.median(ratios):14.4f}"
        print(row)
    print("\nmedian ATR(14), $, by bucket:")
    for lo, hi, label in buckets:
        if label == "no-history":
            mask = np.array([p is None for p in bar_pct])
        else:
            mask = np.array([p is not None and lo <= p < hi for p in bar_pct])
        atr_bucket = atr5[mask]
        atr_bucket = atr_bucket[np.isfinite(atr_bucket) & (atr_bucket > 0)]
        med = np.median(atr_bucket) if len(atr_bucket) else float("nan")
        print(f"  {label:>28s}: n={int(mask.sum()):>10,d}  median ATR=${med:.3f}")


def main() -> int:
    part_a()
    part_b()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
