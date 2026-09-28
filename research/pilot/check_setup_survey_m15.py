"""Same pre-registered survey as check_setup_survey.py, moved to the M15
timeframe per user request ("ขยับไปเป็น tf m15") after discussing whether
cost (spread/commission/slippage as a fraction of R) explains why all 7
setup ideas failed (Part 25). M15's own ATR is naturally larger than M5's,
so the SAME fixed-dollar cost is automatically a smaller fraction of R here
- a more natural way to test the cost-vs-volatility idea than artificially
widening the ATR multiplier on M5, which Parts 18-22 already showed helps
real and random entries equally (no edge created, just less cost drag).

Time stop is scaled by M15's mult=3 (3 x the M5 default = 864 M5 bars = 3
calendar days), matching the multi-timeframe convention already used
elsewhere in this codebase (entry_fill_detail's `expiry_bars * mult`) - a
flat 24h window would unfairly cut off M15-scale targets before they have
a fair chance to resolve.

IMPORTANT correctness fix vs the M5 version: the M5 script's random
baseline used the M5 ATR(14) array for BOTH real and random entries, which
was fine because the real M5 setups also use M5-scale ATR. Real M15 setups
use M15-scale ATR (larger), so the random baseline here is built on an
M15-ATR-aligned-to-M5-bar-index array (via mtf_engine.resample + core.atr),
not the M5 ATR array - otherwise the random baseline's stop distance would
be artificially smaller, unfairly inflating its cost drag as a fraction of
R relative to the real M15 setups. A quick sanity check against real streams'
own atr values confirms this construction matches.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import causal_chain as C
import core as C5
import historical_regime_walkforward as hist
import mtf_engine as E
from check_setup_survey import (load_setup_entries, dedupe_by_bar_dir,
                                precompute_paths as _precompute_paths_m5tpl,
                                first_cross, eval_net_r)

SETUPS = ("vwap", "failed", "breakout", "pullback")
STOPS = (0.75, 1.0, 1.5, 2.0, 3.0)
TARGETS = (0.5, 1.0, 1.5, 2.0, 3.0)
TF = "M15"
MULT = 3
TIME_STOP = E.TIME_STOP_M5 * MULT  # 864 M5 bars = 3 calendar days
WINDOW_DAYS = 180


def load_setup_entries_tf(b5, streams, meta, setup, st, tg, tf):
    parts = []
    for tag, m in meta.items():
        if m["setup"] != setup or m["tf"] != tf or float(m["stop"]) != st \
                or float(m["target"]) != tg:
            continue
        s = streams[m["stream"]]
        held = s["held"][:, int(m["plane"])]
        chosen, _ = C.causal_indices(s["entry_k"], s["order_k"], held)
        if not len(chosen):
            continue
        parts.append((s["entry_k"][chosen].astype(np.int64), s["atr"][chosen],
                     s["entry"][chosen], s["at_open"][chosen], s["direction"][chosen]))
    if not parts:
        return (np.array([], np.int64),) * 5
    entry_k = np.concatenate([p[0] for p in parts])
    atr = np.concatenate([p[1] for p in parts])
    entries = np.concatenate([p[2] for p in parts])
    at_open = np.concatenate([p[3] for p in parts])
    direction = np.concatenate([p[4] for p in parts]).astype(np.int8)
    return entry_k, atr, entries, at_open, direction


def build_m15_atr_aligned(b5) -> np.ndarray:
    """M15 ATR(14), broadcast back so index k (an M5-bar index) gives the
    M15 ATR of the M15 candle covering k."""
    b15, nxt_or_idx = E.resample(b5, MULT)
    atr15 = C5.atr(b15, 14)
    aligned = np.full(len(b5), np.nan)
    for i in range(len(b15)):
        t0 = int(b15.t[i])
        k0 = int(np.searchsorted(b5.t, t0))
        k1 = min(k0 + MULT, len(b5))
        aligned[k0:k1] = atr15[i]
    # forward-fill any leading gap
    first_valid = np.flatnonzero(~np.isnan(aligned))
    if len(first_valid):
        aligned[:first_valid[0]] = aligned[first_valid[0]]
    return aligned


def precompute_paths(b5, entry_k, atr, entries, at_open, direction, st):
    out = []
    for i in range(len(entry_k)):
        k = int(entry_k[i]); a = float(atr[i]); e = float(entries[i])
        ao = bool(at_open[i]); d = int(direction[i])
        end = min(k + TIME_STOP, len(b5))
        hi, lo = b5.h[k:end], b5.l[k:end]
        if d > 0:
            fav = (hi - e) / a; adv = (e - lo) / a
        else:
            sp = np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)
            fav = (e - (lo + sp)) / a; adv = ((hi + sp) - e) / a
        if not ao and len(fav):
            fav = fav.copy(); fav[0] = -np.inf
        fav_c = np.maximum.accumulate(fav)
        adv_c = np.maximum.accumulate(adv)
        j_stop = first_cross(adv_c, st)
        last_c = float(b5.c[end - 1] if d > 0 else b5.c[end - 1] + E.SPREAD_FALLBACK)
        out.append((k, a, e, d, fav_c, adv_c, j_stop, last_c))
    return out


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    rng = np.random.default_rng(0)

    atr15_aligned = build_m15_atr_aligned(b5)

    # sanity check: compare against a handful of real M15 entries' own atr
    check_k, check_atr, *_ = load_setup_entries_tf(b5, streams, meta, "vwap", 1.0, 1.0, TF)
    if len(check_k):
        sample = np.random.default_rng(1).choice(len(check_k), size=min(10, len(check_k)), replace=False)
        diffs = [abs(atr15_aligned[check_k[i]] - check_atr[i]) / check_atr[i] for i in sample]
        print(f"sanity check (10 samples): mean relative diff between constructed "
              f"M15-aligned ATR and streams' own atr = {np.mean(diffs)*100:.2f}%\n")

    t = pd.to_datetime(b5.t, unit="s", utc=True)
    win_start_idx = int(np.searchsorted(t.values, t.values[-1] - np.timedelta64(WINDOW_DAYS, "D")))
    win_end_idx = len(b5) - TIME_STOP

    print(f"tf={TF} time_stop={TIME_STOP} M5-bars ({TIME_STOP*5/60:.0f}h)  "
          f"window: last {WINDOW_DAYS}d [{t[win_start_idx]} .. {t[win_end_idx-1]}]\n")

    rows = []
    for setup in SETUPS:
        for st in STOPS:
            entry_k, atr, entries, at_open, direction = load_setup_entries_tf(
                b5, streams, meta, setup, st, 1.0, TF)
            if len(entry_k) == 0:
                continue
            keep = (entry_k >= win_start_idx) & (entry_k < win_end_idx)
            entry_k, atr, entries, at_open, direction = (
                entry_k[keep], atr[keep], entries[keep], at_open[keep], direction[keep])
            entry_k, atr, entries, at_open, direction = dedupe_by_bar_dir(
                entry_k, atr, entries, at_open, direction)
            n_dedup = len(entry_k)
            if n_dedup == 0:
                continue

            rand_k = rng.choice(np.arange(win_start_idx, win_end_idx),
                                size=n_dedup, replace=False)
            rand_k = np.sort(rand_k)
            rand_atr = atr15_aligned[rand_k]
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
            print(f"=== {setup} === (no signals in window)\n")
            continue
        print(f"=== {setup} ===")
        print(sub.pivot(index="stop", columns="target", values="gap")
              .round(3).to_string())
        print(f"  n per stop: {sub.groupby('stop')['n'].first().to_dict()}")
        print()

    print("gap = net_R(real) - net_R(random baseline), both on M15-scale ATR.")
    out_path = Path("data/setup_survey_m15.csv")
    df.to_csv(out_path, index=False)
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
