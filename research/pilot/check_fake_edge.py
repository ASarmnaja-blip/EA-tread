"""Is the positive net-R found in the RR sweep (stop=1.0/1.5, LONG, RR>=1:4-6)
a real setup-specific effect, or just 'gold trended up, so any long entry
with a wide enough target makes money in this window'?

Dedupes the real expansion/M5 LONG entries to one row per unique entry bar
(the earlier concentration check found up to 6 duplicate rows per bar from
different entry-mode variants - not independent events), then builds an
UNCONDITIONAL random-entry baseline of the same size in the same M1-covered
window (any M5 bar, ATR(14) computed directly on M5, always LONG, treated
as a market fill). Runs the identical stop/RR grid on both and compares.
If the random baseline is ALSO positive at the same RR levels with similar
magnitude, the setup adds nothing here - it would be pure directional drift
dressed up as a signal. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rr_sweep_finance import load_long_entries, precompute_paths, first_cross, TIME_STOP
import basket_gate as A24
import core as C5
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

STOPS = (1.0, 1.5)
TARGETS = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)


def dedupe_by_bar(entry_k, atr, entries, at_open):
    _, first_idx = np.unique(entry_k, return_index=True)
    first_idx = np.sort(first_idx)
    return entry_k[first_idx], atr[first_idx], entries[first_idx], at_open[first_idx]


def eval_net_r(b5, paths, st, tg, fee):
    n = len(paths)
    net_sum = 0.0
    wins = 0
    for (k, a, e, d, end, fav_c, adv_c, j_stop, last_c) in paths:
        risk = st * a
        j_tgt = first_cross(fav_c, st * tg)
        if j_stop < len(adv_c) and j_stop <= j_tgt:
            gross = -1.0
        elif j_tgt < len(fav_c):
            gross = float(tg)
        else:
            gross = d * (last_c - e) / risk
        net = gross - fee / risk
        net_sum += net
        wins += net > 0
    return 100 * wins / n, net_sum / n


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    rng = np.random.default_rng(0)

    atr5 = C5.atr(b5, 14)
    m1 = D.load_csv("data/XAUUSD_M1.csv")
    m1_start_t = int(m1.t[0])
    m1_start_idx = int(np.searchsorted(b5.t.astype(np.int64), m1_start_t))
    usable_end = len(b5) - TIME_STOP  # so every sampled path has a full window

    print(f"{'':6s}{'':8s}{'n_real':>8s}{'n_dedup':>9s}  | {'RR':>6s}"
          f"{'win%_real':>10s}{'net_real':>10s} || {'win%_rand':>10s}{'net_rand':>10s}")

    for st in STOPS:
        entry_k, atr, entries, at_open = load_long_entries(b5, streams, meta, st)
        n_real = len(entry_k)
        # restrict to the M1-covered, fully-resolvable window for a fair compare
        keep = (entry_k >= m1_start_idx) & (entry_k < usable_end)
        entry_k, atr, entries, at_open = entry_k[keep], atr[keep], entries[keep], at_open[keep]
        entry_k, atr, entries, at_open = dedupe_by_bar(entry_k, atr, entries, at_open)
        n_dedup = len(entry_k)

        rand_k = rng.choice(np.arange(m1_start_idx, usable_end), size=n_dedup, replace=False)
        rand_k = np.sort(rand_k)
        rand_atr = atr5[rand_k]
        rand_entries = b5.c[rand_k]
        rand_at_open = np.ones(n_dedup, dtype=bool)

        d_real = np.ones(n_dedup, np.int8)
        d_rand = np.ones(n_dedup, np.int8)
        paths_real = precompute_paths(b5, entry_k, atr, entries, at_open, d_real, st)
        paths_rand = precompute_paths(b5, rand_k, rand_atr, rand_entries, rand_at_open, d_rand, st)

        print(f"stop={st:<4g}          {n_real:8,d}{n_dedup:9,d}")
        for tg in TARGETS:
            w_r, n_r = eval_net_r(b5, paths_real, st, tg, fee)
            w_x, n_x = eval_net_r(b5, paths_rand, st, tg, fee)
            print(f"{'':6s}{'':8s}{'':8s}{'':9s}  | 1:{tg:<4.0f}"
                  f"{w_r:9.1f}%{n_r:10.4f} || {w_x:9.1f}%{n_x:10.4f}")
        print()

    print("real = expansion/M5 LONG signals, deduped to one row per unique entry bar.")
    print("rand = same count of UNCONDITIONAL random M5 bars in the same window,")
    print("  same stop, ATR(14) computed directly on M5, always LONG, market fill.")
    print("If rand's net_R also turns positive at the same RR as real's, the")
    print("apparent edge is directional drift, not the setup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
