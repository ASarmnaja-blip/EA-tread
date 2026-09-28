"""Champion/Challenger v1 (CLAUDE.md gap #1, first cut).

Part 24 found weekly_evolution_grid.py's weekly "champion" beats the
median-ranked cell in only 49.7% of weeks (a coin flip) - the selector
always finds SOMETHING (idle=0 across 290 rolls) because its LCB score
(mean - 0.75*SE) is a very loose bar applied independently to ~8,250
candidates every week. With that many simultaneous comparisons, some cell
clears a 0.75-SE bar almost every week by pure chance even with zero real
edge anywhere in the pool - classic multiple-comparisons false-positive
inflation, not a sign of a real winner.

This script reruns the identical selection loop (same universe, same
56-day select / 7-day forward cadence, same purge/dedup rules - reuses
weekly_evolution_grid.py's own functions, not a reimplementation) at
SEVERAL shrinkage multipliers, from the original 0.75 up through an
approximate Bonferroni correction for ~8,250 simultaneous comparisons
(two-sided alpha=0.05 => z ~ 4.87), to show how often the pool would have
produced NO_TOOL once multiple-comparisons is accounted for, and whether
whatever still clears the higher bar performs any better forward.

This is a selection-mechanism fix, not a new source of edge: if every
candidate in the pool is truly edgeless (Parts 18-25), even a perfectly
corrected selector should mostly output NO_TOOL - which is the CORRECT
behaviour per CLAUDE.md section 6 ("Claude must be able to answer NO
TRADE"), not a failure of this script. Read-only, no MT5, no order.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge_backtest as bt
import historical_regime_walkforward as hist
import walk_forward as wf
from weekly_evolution_grid import (DAY, SELECT_DAYS, FORWARD_DAYS, MIN_TRADES,
                                   MIN_DAYS, _week_boundary, _unique_ranking,
                                   _forward)

# Bonferroni for ~8,250 simultaneous one-sided tests at alpha=0.05:
# z = Phi^-1(1 - 0.05/8250) ~ 4.65. Report a spread of levels either side.
SHRINK_LEVELS = (0.75, 2.0, 3.0, 4.0, 4.65, 5.5)


def _score_universe_at(uni: dict, lo: int, cut: int, shrink: float):
    out, signature, purged = {}, {}, 0
    for tag, a in uni.items():
        entered = (a["t_order"] >= lo) & (a["t_order"] < cut)
        complete = entered & (a["t_out"] < cut)
        purged += int(entered.sum() - complete.sum())
        x = a["net"][complete]
        if len(x) < MIN_TRADES or len(np.unique(a["t_order"][complete] // DAY)) < MIN_DAYS:
            continue
        score = float(x.mean() - shrink * x.std(ddof=1) / np.sqrt(len(x)))
        out[tag] = score
        signature[tag] = a["sigk"][complete].tobytes()
    return out, signature, purged


def run_at_shrink(uni: dict, first: int, last: int, shrink: float) -> dict:
    cut = _week_boundary(first)
    if cut <= first + SELECT_DAYS * DAY:
        cut += 7 * DAY
    while cut < first + SELECT_DAYS * DAY:
        cut += 7 * DAY

    rolls = idle = transitions = 0
    all_net = []
    while cut < last:
        end = min(cut + FORWARD_DAYS * DAY, last)
        scores, signature, _ = _score_universe_at(uni, cut - SELECT_DAYS * DAY, cut, shrink)
        rolls += 1
        ranked, _ = _unique_ranking(scores, signature)
        eligible = [t for t in ranked if scores[t] > 0]  # must clear zero at this shrink level
        if not eligible:
            idle += 1
            cut += 7 * DAY
            continue
        chosen = eligible[0]
        vals = _forward(uni[chosen], cut, end)
        all_net.extend(vals)
        transitions += 1
        cut += 7 * DAY

    m = bt._metrics(all_net)
    return dict(shrink=shrink, rolls=rolls, idle=idle, active_weeks=rolls - idle,
               idle_pct=100 * idle / rolls if rolls else np.nan,
               trades=m["trades"] if m else 0,
               net_R=m["net_R"] if m else 0.0,
               mean_R=m["mean_R"] if m else np.nan,
               win_pct=m["win_pct"] if m else np.nan)


def main() -> int:
    b5 = hist.load_history()
    last = int(b5.t[-1] + b5.step)
    first = int(b5.t[0])
    print("building fixed 8,250-cell universe once (shared across all shrink levels)...")
    uni, meta = wf.build_universe(b5, last)
    print(f"eligible_cells={len(uni):,} declared_cells={len(meta):,}\n")

    print(f"{'shrink':>7s}{'active%':>9s}{'idle%':>8s}{'trades':>8s}"
          f"{'net_R':>10s}{'mean_R':>9s}{'win%':>7s}")
    for shrink in SHRINK_LEVELS:
        r = run_at_shrink(uni, first, last, shrink)
        active_pct = 100 - r["idle_pct"]
        print(f"{shrink:7.2f}{active_pct:8.1f}%{r['idle_pct']:7.1f}%{r['trades']:8d}"
              f"{r['net_R']:+10.3f}{r['mean_R']:+9.4f}{r['win_pct']:6.1f}%")

    print("\nshrink=0.75 is weekly_evolution_grid.py's current (uncorrected) bar.")
    print("shrink~4.65 approximates a Bonferroni correction for ~8,250 simultaneous")
    print("weekly comparisons at alpha=0.05. If active% collapses toward 0 and net_R")
    print("does not turn positive even then, the pool has nothing to select - NO_TOOL")
    print("becomes the historically correct answer most weeks, not a defect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
