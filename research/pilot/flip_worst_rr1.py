"""Find the worst-losing RR=1:1 (target R = 1.0) corner on XAUUSD, causal
chain, then test flipping its direction, and investigate why it loses.

RR 1:1 means target R = 1.0 (target distance = stop distance). This breaks
that corner down by (family, timeframe, direction) to find the single worst
losing bucket, then recomputes with direction reversed (same entry bar,
stop/target distance, everything else identical) to see whether the loser is
also a strong flipped winner. Read-only.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import causal_chain as C
import core
import historical_regime_walkforward as hist
import mtf_engine as E

TARGET = 1.0


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL

    by_bucket = defaultdict(lambda: [0, 0.0, 0])  # n, net_sum, wins
    cell_of_bucket = defaultdict(list)  # key -> list of (tag, m, chosen_idx)
    for tag, m in meta.items():
        if float(m["target"]) != TARGET:
            continue
        s = streams[m["stream"]]
        held = s["held"][:, int(m["plane"])]
        chosen, _ = C.causal_indices(s["entry_k"], s["order_k"], held)
        if not len(chosen):
            continue
        risk = float(m["stop"]) * s["atr"][chosen]
        gross = s["gross"][chosen, int(m["plane"])]
        net = gross - fee / risk
        direction = s["direction"][chosen]
        for d in (1, -1):
            mask = direction == d
            if not np.any(mask):
                continue
            key = (m["setup"], m["tf"], float(m["stop"]), d)
            b = by_bucket[key]
            b[0] += int(mask.sum())
            b[1] += float(net[mask].sum())
            b[2] += int(np.sum(net[mask] > 0))
            cell_of_bucket[key].append((tag, m, chosen[mask]))

    print("worst RR=1:1 (family, timeframe, stop, direction) buckets, "
          "min 200 trades:")
    rows = [(k, v[0], v[1] / v[0], v[2] / v[0]) for k, v in by_bucket.items()
            if v[0] >= 200]
    rows.sort(key=lambda r: r[2])
    for k, n, net_tr, win in rows[:10]:
        setup, tf, stop, d = k
        print(f"  {setup:10s} {tf:4s} stop={stop:.2f} dir={'LONG' if d>0 else 'SHORT':5s} "
              f"n={n:7,d} net/tr={net_tr:+.4f} win={100*win:.1f}%")

    worst_key = rows[0][0]
    variants = cell_of_bucket[worst_key]
    setup, tf, stop, d = worst_key
    print(f"\n=== worst bucket: {setup}/{tf} stop={stop} dir={'LONG' if d>0 else 'SHORT'} "
          f"n={rows[0][1]} net/tr={rows[0][2]:+.4f} "
          f"(aggregated across {len(variants)} entry-mode variants) ===")

    entry_k_parts, atr_parts, entries_parts, orig_net_parts = [], [], [], []
    for tag, m, idx in variants:
        s = streams[m["stream"]]
        entry_k_parts.append(s["entry_k"][idx].astype(np.int64))
        atr_parts.append(s["atr"][idx])
        entries_parts.append(s["entry"][idx])
        risk_v = stop * s["atr"][idx]
        orig_net_parts.append(s["gross"][idx, int(m["plane"])] - fee / risk_v)
    entry_k = np.concatenate(entry_k_parts)
    atr = np.concatenate(atr_parts)
    entries = np.concatenate(entries_parts)
    orig_net = np.concatenate(orig_net_parts)
    risk = stop * atr

    # FLIP: recompute resolve_plane with direction reversed, same entry/atr,
    # across every one of these trades (all entry-mode variants combined)
    flip_gross = np.empty(len(entry_k))
    for i, k in enumerate(entry_k):
        plane = E.resolve_plane(b5, int(k), -d, float(entries[i]), float(atr[i]),
                                (stop,), (TARGET,), E.TIME_STOP_M5)
        g, _why, nb = plane[(stop, TARGET)]
        flip_gross[i] = g
    flip_net = flip_gross - fee / risk
    print(f"ORIGINAL: n={len(entry_k):,}  mean net/tr {np.mean(orig_net):+.4f}  "
          f"win {100*np.mean(orig_net>0):.1f}%")
    print(f"FLIPPED:  n={len(entry_k):,}  mean net/tr {np.mean(flip_net):+.4f}  "
          f"win {100*np.mean(flip_net>0):.1f}%")
    print("(flip recomputes resolve_plane with reversed direction on the SAME "
          "entry bar/price/ATR - not a sign-negation of the old result, since "
          "which barrier is 'stop' vs 'target' swaps too)")

    # WHY: timing pattern of the original losing signals
    hrs = np.array([datetime.fromtimestamp(int(b5.t[k]), timezone.utc).hour
                    for k in entry_k])
    dows = np.array([datetime.fromtimestamp(int(b5.t[k]), timezone.utc).weekday()
                     for k in entry_k])
    print("\nby entry hour (UTC), original direction net/tr:")
    for h in range(0, 24, 3):
        sel = (hrs >= h) & (hrs < h + 3)
        if sel.sum() >= 30:
            print(f"  {h:02d}-{h+3:02d}h  n={sel.sum():6,d}  net/tr={orig_net[sel].mean():+.4f}")
    print("\nby weekday, original direction net/tr:")
    for wd, name in enumerate(("Mon","Tue","Wed","Thu","Fri","Sat","Sun")):
        sel = dows == wd
        if sel.sum() >= 30:
            print(f"  {name}  n={sel.sum():6,d}  net/tr={orig_net[sel].mean():+.4f}")

    # is this "chasing" per ledger Part 8's finding - same-direction signal
    # while the cell was already busy in a wider sense? Check MFE/MAE shape.
    print("\npath shape (does price touch stop before target more/less than 50%?):")
    stop_first = 0
    for i, k in enumerate(entry_k):
        plane = E.resolve_plane(b5, int(k), int(d), float(entries[i]), float(atr[i]),
                                (stop,), (TARGET,), E.TIME_STOP_M5)
        g, why, _nb = plane[(stop, TARGET)]
        if g < 0:
            stop_first += 1
    print(f"  stop hit (incl. time-stop losses) in {stop_first}/{len(entry_k)} "
          f"= {100*stop_first/len(entry_k):.1f}% of original-direction trades")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
