"""Re-run the setup survey (Part 22's methodology) restricted to the POOLED
'similar regime' weeks found by find_similar_regime_periods.py - 145 weeks
spread across 2021-2026, matching today's ATR-percentile/efficiency-ratio
reading, NOT one arbitrary contiguous window. This fixes Part 20's small-n
problem (n=82-88 in one 2-month window) with a much larger, time-robust
pooled sample, directly answering the user's point: measure a setup
designed for the current regime against data from the SAME regime type,
not an unrelated period, and not just one narrow slice of it either.

Pre-registered here, before running: same success criterion as Part 22 -
a candidate must beat its own random baseline consistently across multiple
targets at a given stop, by a margin clearly larger than what the
continuation-setup controls (breakout/pullback) show. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import core as C5
import historical_regime_walkforward as hist
from check_setup_survey import (load_setup_entries, dedupe_by_bar_dir,
                                precompute_paths, eval_net_r)
import mtf_engine as E

SETUPS = ("vwap", "failed", "breakout", "pullback", "expansion")
STOPS = (0.75, 1.0, 1.5, 2.0, 3.0)
TARGETS = (0.5, 1.0, 1.5, 2.0, 3.0)
TIME_STOP = E.TIME_STOP_M5
WEEK_BARS_M5 = 7 * 24 * 12  # 7 days of M5 bars, upper bound (weekends have fewer)


def build_similar_regime_mask(b5, weeks_csv: str) -> np.ndarray:
    wk = pd.read_csv(weeks_csv)
    mask = np.zeros(len(b5), dtype=bool)
    for _, row in wk.iterrows():
        i0 = int(row["m5_idx"])
        i1 = min(i0 + WEEK_BARS_M5, len(b5))
        mask[i0:i1] = True
    return mask


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    atr5 = C5.atr(b5, 14)
    rng = np.random.default_rng(0)

    mask = build_similar_regime_mask(b5, "data/similar_regime_weeks.csv")
    valid_idx = np.flatnonzero(mask & (np.arange(len(b5)) < len(b5) - TIME_STOP))
    print(f"similar-regime bars available as entry/random-draw universe: "
          f"{len(valid_idx):,} ({100*len(valid_idx)/len(b5):.1f}% of all bars)\n")

    rows = []
    for setup in SETUPS:
        for st in STOPS:
            entry_k, atr, entries, at_open, direction = load_setup_entries(
                b5, streams, meta, setup, st, 1.0)
            if len(entry_k) == 0:
                continue
            keep = mask[np.clip(entry_k, 0, len(b5) - 1)] & (entry_k < len(b5) - TIME_STOP)
            entry_k, atr, entries, at_open, direction = (
                entry_k[keep], atr[keep], entries[keep], at_open[keep], direction[keep])
            entry_k, atr, entries, at_open, direction = dedupe_by_bar_dir(
                entry_k, atr, entries, at_open, direction)
            n_dedup = len(entry_k)
            if n_dedup == 0:
                continue

            rand_k = rng.choice(valid_idx, size=n_dedup, replace=(n_dedup > len(valid_idx)))
            rand_k = np.sort(rand_k)
            rand_atr = atr5[rand_k]
            rand_entries = b5.c[rand_k]
            rand_at_open = np.ones(n_dedup, dtype=bool)
            rand_dir = rng.choice([-1, 1], size=n_dedup).astype(np.int8)

            paths_real = precompute_paths(b5, entry_k, atr, entries, at_open, direction, st)
            paths_rand = precompute_paths(b5, rand_k, rand_atr, rand_entries,
                                          rand_at_open, rand_dir, st)

            for tg in TARGETS:
                w_r, n_r = eval_net_r(paths_real, st, tg, fee)
                w_x, n_x = eval_net_r(paths_rand, st, tg, fee)
                rows.append(dict(setup=setup, stop=st, target=tg, n=n_dedup,
                                 win_real=w_r, net_real=n_r, win_rand=w_x, net_rand=n_x,
                                 gap=n_r - n_x))

    df = pd.DataFrame(rows)
    pd.set_option("display.width", 140)
    for setup in SETUPS:
        sub = df[df.setup == setup]
        if sub.empty:
            print(f"=== {setup} === (no signals in similar-regime weeks)\n")
            continue
        print(f"=== {setup} ===")
        print(sub.pivot(index="stop", columns="target", values="gap")
              .round(3).to_string())
        print(f"  n per stop: {sub.groupby('stop')['n'].first().to_dict()}")
        print()

    print("gap = net_R(real) - net_R(random baseline), both restricted to the")
    print("145 pooled similar-regime weeks (53.3% of full history, all years).")
    out_path = Path("data/setup_survey_similar_regime.csv")
    df.to_csv(out_path, index=False)
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
