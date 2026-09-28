"""Pre-registered survey (see LOGIC_LEDGER.md 'Pre-registration - setup
survey vs random baseline, current (flat) regime'): does any of vwap /
failed / breakout / pullback beat an unconditional random-entry baseline,
on the ALREADY-DECLARED M5 grid (stop 0.75-3.0 x target 0.5-3.0R, 24h time
stop - no extension), over the trailing 180 days (measured flat in Part 21).

Hypothesis, stated before running: vwap/failed (mean-reversion) should beat
random in this flat window; breakout/pullback (continuation) should not.
Both real and random entries keep their OWN direction (real: the setup's
actual signal direction, not forced long; random: an unbiased coin flip),
since these setups trade both sides. Read-only.
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

SETUPS = ("vwap", "failed", "breakout", "pullback")
STOPS = (0.75, 1.0, 1.5, 2.0, 3.0)
TARGETS = (0.5, 1.0, 1.5, 2.0, 3.0)
TIME_STOP = E.TIME_STOP_M5  # 288 = 24h, the grid's own default, no extension
WINDOW_DAYS = 180


def first_cross(cum, level):
    idx = np.flatnonzero(cum >= level)
    return int(idx[0]) if len(idx) else len(cum)


def load_setup_entries(b5, streams, meta, setup, st, tg):
    parts = []
    for tag, m in meta.items():
        if m["setup"] != setup or m["tf"] != "M5" or float(m["stop"]) != st \
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


def dedupe_by_bar_dir(entry_k, atr, entries, at_open, direction):
    key = entry_k.astype(np.int64) * 4 + (direction > 0).astype(np.int64)
    _, first_idx = np.unique(key, return_index=True)
    first_idx = np.sort(first_idx)
    return (entry_k[first_idx], atr[first_idx], entries[first_idx],
            at_open[first_idx], direction[first_idx])


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


def eval_net_r(paths, st, tg, fee):
    n = len(paths)
    if n == 0:
        return np.nan, np.nan
    net_sum = 0.0
    wins = 0
    for (k, a, e, d, fav_c, adv_c, j_stop, last_c) in paths:
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
    atr5 = C5.atr(b5, 14)
    rng = np.random.default_rng(0)

    t = pd.to_datetime(b5.t, unit="s", utc=True)
    win_start_idx = int(np.searchsorted(t.values, t.values[-1] - np.timedelta64(WINDOW_DAYS, "D")))
    win_end_idx = len(b5) - TIME_STOP  # leave room to resolve every path

    print(f"window: last {WINDOW_DAYS}d, bars [{win_start_idx}:{win_end_idx}] "
          f"({t[win_start_idx]} .. {t[win_end_idx-1]})\n")

    rows = []
    for setup in SETUPS:
        for st in STOPS:
            # union of real entries across all 5 targets at this stop (same entries,
            # target only changes resolution) - use target=1.0 rows to get the entry set
            entry_k, atr, entries, at_open, direction = load_setup_entries(
                b5, streams, meta, setup, st, 1.0)
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
        print(f"=== {setup} ===")
        print(sub.pivot(index="stop", columns="target", values="gap")
              .round(3).to_string())
        print(f"  n per stop: {sub.groupby('stop')['n'].first().to_dict()}")
        print()

    print("gap = net_R(real) - net_R(random baseline). Positive and consistent")
    print("across multiple targets at a stop = candidate. One-off positive cells")
    print("or gaps similar in size to the continuation setups = noise, not edge.")

    out_path = Path("data/setup_survey.csv")
    df.to_csv(out_path, index=False)
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
