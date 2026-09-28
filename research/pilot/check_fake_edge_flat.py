"""Same fake-edge test as check_fake_edge.py, but entries restricted to a
genuinely flat/ranging gold window instead of the trending M1-covered
period. If the RR>=4-7 'edge' was pure directional drift (Part 19), it
should NOT reappear here - real setup entries and random entries should
both look flat/negative, with no separation between them.

Window chosen from find_flat_period.py's efficiency-ratio ranking, filtered
to MT5's actually-reliable M5 history (2021-01 onward, confirmed by probing
the live terminal): 2025-05 and 2025-06, two CONSECUTIVE months with
efficiency ~0.001 (near-zero net drift), good bar coverage, and inside the
window where MT5 also has real M1 tick data (from 2023-11-27), so this
window is realistically re-testable in MT5's Strategy Tester too, unlike
the pre-2021 sparse-data era. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rr_sweep_finance import load_long_entries, precompute_paths, first_cross, TIME_STOP
from check_fake_edge import dedupe_by_bar, eval_net_r
import basket_gate as A24
import core as C5
import historical_regime_walkforward as hist
import mtf_engine as E

STOPS = (1.0, 1.5)
TARGETS = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)
WINDOW_START = "2025-05-01"
WINDOW_END = "2025-07-01"  # exclusive


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    rng = np.random.default_rng(0)

    t = pd.to_datetime(b5.t, unit="s", utc=True)
    win_start_idx = int(np.searchsorted(t.values, np.datetime64(WINDOW_START)))
    win_end_idx = int(np.searchsorted(t.values, np.datetime64(WINDOW_END)))
    net_move = abs(b5.c[win_end_idx - 1] - b5.c[win_start_idx])
    path_len = np.abs(np.diff(b5.c[win_start_idx:win_end_idx])).sum()
    print(f"window: {WINDOW_START} .. {WINDOW_END}  "
          f"({win_end_idx - win_start_idx:,} M5 bars)")
    print(f"efficiency ratio in this window: {net_move / path_len:.4f}  "
          f"(0=pure chop, 1=one-way trend)\n")

    atr5 = C5.atr(b5, 14)
    usable_end = len(b5) - TIME_STOP

    print(f"{'':6s}{'n_real':>8s}{'n_dedup':>9s}  | {'RR':>6s}"
          f"{'win%_real':>10s}{'net_real':>10s} || {'win%_rand':>10s}{'net_rand':>10s}")

    for st in STOPS:
        entry_k, atr, entries, at_open = load_long_entries(b5, streams, meta, st)
        n_real = len(entry_k)
        keep = (entry_k >= win_start_idx) & (entry_k < win_end_idx) & (entry_k < usable_end)
        entry_k, atr, entries, at_open = entry_k[keep], atr[keep], entries[keep], at_open[keep]
        entry_k, atr, entries, at_open = dedupe_by_bar(entry_k, atr, entries, at_open)
        n_dedup = len(entry_k)
        if n_dedup == 0:
            print(f"stop={st:<4g}  no signals in this window")
            continue

        rand_k = rng.choice(np.arange(win_start_idx, min(win_end_idx, usable_end)),
                            size=n_dedup, replace=False)
        rand_k = np.sort(rand_k)
        rand_atr = atr5[rand_k]
        rand_entries = b5.c[rand_k]
        rand_at_open = np.ones(n_dedup, dtype=bool)

        d = np.ones(n_dedup, np.int8)
        paths_real = precompute_paths(b5, entry_k, atr, entries, at_open, d, st)
        paths_rand = precompute_paths(b5, rand_k, rand_atr, rand_entries, rand_at_open, d, st)

        print(f"stop={st:<4g}  {n_real:8,d}{n_dedup:9,d}")
        for tg in TARGETS:
            w_r, n_r = eval_net_r(b5, paths_real, st, tg, fee)
            w_x, n_x = eval_net_r(b5, paths_rand, st, tg, fee)
            print(f"{'':6s}{'':8s}{'':9s}  | 1:{tg:<4.0f}"
                  f"{w_r:9.1f}%{n_r:10.4f} || {w_x:9.1f}%{n_x:10.4f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
