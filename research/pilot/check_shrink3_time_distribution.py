"""Part 27 follow-up: do the weeks that survive champion_challenger_v1.py's
shrink=3.0 bar cluster in the same recent trending period (2024-2025)
already shown to fake a positive edge via drift (Parts 18-22), or are they
spread across the full 2021-2026 history? Read-only."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import historical_regime_walkforward as hist
import walk_forward as wf
from weekly_evolution_grid import DAY, SELECT_DAYS, FORWARD_DAYS, _week_boundary, _forward
from champion_challenger_v1 import _score_universe_at, _unique_ranking

SHRINK = 3.00


def main() -> int:
    b5 = hist.load_history()
    last = int(b5.t[-1] + b5.step)
    first = int(b5.t[0])
    uni, meta = wf.build_universe(b5, last)

    cut = _week_boundary(first)
    if cut <= first + SELECT_DAYS * DAY:
        cut += 7 * DAY
    while cut < first + SELECT_DAYS * DAY:
        cut += 7 * DAY

    active_dates, active_years = [], []
    while cut < last:
        end = min(cut + FORWARD_DAYS * DAY, last)
        scores, signature, _ = _score_universe_at(uni, cut - SELECT_DAYS * DAY, cut, SHRINK)
        ranked, _ = _unique_ranking(scores, signature)
        eligible = [t for t in ranked if scores[t] > 0]
        if eligible:
            d = datetime.fromtimestamp(cut, timezone.utc)
            active_dates.append(d)
            active_years.append(d.year)
        cut += 7 * DAY

    print(f"shrink={SHRINK}: {len(active_dates)} active weeks total\n")
    years, counts = np.unique(active_years, return_counts=True)
    print("active weeks by year:")
    for y, c in zip(years, counts):
        print(f"  {y}: {c}")
    print(f"\nfirst active week: {active_dates[0]:%Y-%m-%d}" if active_dates else "none")
    print(f"last active week:  {active_dates[-1]:%Y-%m-%d}" if active_dates else "")
    share_2024_2025 = sum(1 for y in active_years if y in (2024, 2025)) / max(len(active_years), 1)
    print(f"\nshare of active weeks in 2024-2025: {100*share_2024_2025:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
