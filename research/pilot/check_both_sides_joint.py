"""RR=1:1, stop=0.75, expansion/M5: for each of the SAME entries, tally the
JOINT outcome of buy vs flipped-sell (both win / both lose / one-each) to
show exactly why win%(LONG) + win%(SHORT*) != 100%. Read-only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rr_sweep_finance import load_long_entries, precompute_paths, first_cross
import basket_gate as A24
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

ST, TG = 0.75, 1.0


def outcome(paths, st, tg):
    out = np.empty(len(paths), dtype=np.int8)  # 1=win, 0=loss
    for i, (k, a, e, d, end, fav_c, adv_c, j_stop, last_c) in enumerate(paths):
        j_tgt = first_cross(fav_c, st * tg)
        if j_stop < len(adv_c) and j_stop <= j_tgt:
            out[i] = 0
        elif j_tgt < len(fav_c):
            out[i] = 1
        else:
            out[i] = 1 if (last_c - e) > 0 else 0  # rare, full-period timeout
    return out


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    entry_k, atr, entries, at_open = load_long_entries(b5, streams, meta, ST)
    n = len(entry_k)

    paths_long = precompute_paths(b5, entry_k, atr, entries, at_open,
                                   np.ones(n, np.int8), ST)
    paths_short = precompute_paths(b5, entry_k, atr, entries, at_open,
                                    -np.ones(n, np.int8), ST)
    win_long = outcome(paths_long, ST, TG)
    win_short = outcome(paths_short, ST, TG)

    both_win = int(np.sum((win_long == 1) & (win_short == 1)))
    both_lose = int(np.sum((win_long == 0) & (win_short == 0)))
    long_only = int(np.sum((win_long == 1) & (win_short == 0)))
    short_only = int(np.sum((win_long == 0) & (win_short == 1)))

    print(f"stop={ST} RR=1:{TG:g}, full period, n={n:,}")
    print(f"  both WIN            : {both_win:6,d}  ({100*both_win/n:5.2f}%)")
    print(f"  buy win / sell lose : {long_only:6,d}  ({100*long_only/n:5.2f}%)")
    print(f"  buy lose / sell win : {short_only:6,d}  ({100*short_only/n:5.2f}%)")
    print(f"  both LOSE           : {both_lose:6,d}  ({100*both_lose/n:5.2f}%)")
    print(f"  sum                 : {both_win+long_only+short_only+both_lose:6,d}  (100.00%)")
    print()
    print(f"  win%(LONG)  = {100*(both_win+long_only)/n:.2f}%")
    print(f"  win%(SHORT*)= {100*(both_win+short_only)/n:.2f}%")
    print(f"  sum of the two win%%  = {100*(2*both_win+long_only+short_only)/n:.2f}%")
    print(f"  'missing' = both-lose share = {100*both_lose/n:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
