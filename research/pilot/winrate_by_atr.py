"""Win rate for ALL trades (not just ties) in expansion/M5, RR=1:1, LONG,
across every stop ATR in the grid - original (conservative tie-break) vs
M1-corrected, restricted to the M1-covered subset for a fair comparison,
plus the full-period original for context. Table with percentages.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import causal_chain as C
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

TARGET = 1.0
STOPS = (0.75, 1.0, 1.5, 2.0, 3.0)


def first_cross(cum, level):
    idx = np.flatnonzero(cum >= level)
    return int(idx[0]) if len(idx) else len(cum)


def eval_side(b5, m1, m1_t, m1_start_t, entry_k, atr, entries, at_open,
             direction, st, fee):
    n_total = len(entry_k)
    full_wins = full_net = 0.0
    m1_orig_wins = m1_orig_net = 0.0
    m1_corr_wins = m1_corr_net = 0.0
    n_m1 = 0
    for i in range(n_total):
        k = int(entry_k[i]); a = float(atr[i]); e = float(entries[i])
        ao = bool(at_open[i]); d = int(direction[i]); risk = st * a
        end = min(k + E.TIME_STOP_M5, len(b5))
        hi, lo = b5.h[k:end], b5.l[k:end]
        if d > 0:
            fav = (hi - e) / a; adv = (e - lo) / a
            stop_price = e - st * a; target_price = e + st * TARGET * a
        else:
            sp = np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)
            fav = (e - (lo + sp)) / a; adv = ((hi + sp) - e) / a
            stop_price = e + st * a; target_price = e - st * TARGET * a
        if not ao and len(fav):
            fav = fav.copy(); fav[0] = -np.inf
        fav_c = np.maximum.accumulate(fav)
        adv_c = np.maximum.accumulate(adv)
        j_stop = first_cross(adv_c, st)
        j_tgt = first_cross(fav_c, st * TARGET)

        if j_stop < len(adv_c) and j_stop <= j_tgt:
            gross = -1.0
        elif j_tgt < len(fav_c):
            gross = float(TARGET)
        else:
            last_c = float(b5.c[end - 1] if d > 0 else b5.c[end - 1] + E.SPREAD_FALLBACK)
            gross = d * (last_c - e) / risk
        net = gross - fee / risk
        full_wins += net > 0
        full_net += net

        if b5.t[k] < m1_start_t:
            continue
        n_m1 += 1
        m1_orig_wins += net > 0
        m1_orig_net += net
        corr_net = net
        if j_stop < len(adv_c) and j_stop == j_tgt:
            tie_bar_k = k + j_stop
            bar_t0 = int(b5.t[tie_bar_k]); bar_t1 = bar_t0 + 300
            i0 = int(np.searchsorted(m1_t, bar_t0))
            i1 = int(np.searchsorted(m1_t, bar_t1))
            if i1 - i0 >= 1:
                hi1, lo1 = m1.h[i0:i1], m1.l[i0:i1]
                if d > 0:
                    hit_s = np.flatnonzero(lo1 <= stop_price)
                    hit_t = np.flatnonzero(hi1 >= target_price)
                else:
                    sp1 = np.maximum(m1.sp[i0:i1], E.SPREAD_FALLBACK)
                    hit_s = np.flatnonzero((hi1 + sp1) >= stop_price)
                    hit_t = np.flatnonzero((lo1 + sp1) <= target_price)
                js1 = int(hit_s[0]) if len(hit_s) else 10**9
                jt1 = int(hit_t[0]) if len(hit_t) else 10**9
                if js1 > jt1:
                    corr_net = float(TARGET) - fee / risk
        m1_corr_wins += corr_net > 0
        m1_corr_net += corr_net
    return (n_total, full_wins, full_net, n_m1,
           m1_orig_wins, m1_orig_net, m1_corr_wins, m1_corr_net)


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    m1 = D.load_csv("data/XAUUSD_M1.csv")
    m1_t = m1.t.astype(np.int64)
    m1_start_t = int(m1.t[0])

    rows = []
    for st in STOPS:
        parts = []
        for tag, m in meta.items():
            if m["setup"] != "expansion" or m["tf"] != "M5" or float(m["stop"]) != st \
                    or float(m["target"]) != TARGET:
                continue
            s = streams[m["stream"]]
            held = s["held"][:, int(m["plane"])]
            chosen, _ = C.causal_indices(s["entry_k"], s["order_k"], held)
            if not len(chosen):
                continue
            d = s["direction"][chosen]
            keep = d > 0
            if not np.any(keep):
                continue
            idx = chosen[keep]
            parts.append((s["entry_k"][idx].astype(np.int64), s["atr"][idx],
                         s["entry"][idx], s["at_open"][idx]))
        if not parts:
            rows.append((st, 0, 0, 0.0, 0.0, 0, 0.0, 0.0, 0))
            continue
        entry_k = np.concatenate([p[0] for p in parts])
        atr = np.concatenate([p[1] for p in parts])
        entries = np.concatenate([p[2] for p in parts])
        at_open = np.concatenate([p[3] for p in parts])
        direction_long = np.ones(len(entry_k), np.int8)
        direction_short = -direction_long

        long_r = eval_side(b5, m1, m1_t, m1_start_t, entry_k, atr, entries,
                           at_open, direction_long, st, fee)
        short_r = eval_side(b5, m1, m1_t, m1_start_t, entry_k, atr, entries,
                            at_open, direction_short, st, fee)
        rows.append((st, long_r, short_r))

    print("expansion/M5, target R = 1.0 (RR 1:1), by stop ATR - "
          "REAL long entries vs FLIPPED (same entries, reversed)\n")
    hdr = (f"{'stop':>6s}{'side':>6s}{'trades':>8s}{'winrate':>9s}{'net/tr':>9s}  |"
          f"{'M1 n':>7s}{'win% orig':>11s}{'net/tr orig':>13s}"
          f"{'win% M1-fix':>13s}{'net/tr M1-fix':>15s}")
    print(hdr)
    for (st, long_r, short_r) in rows:
        for label, r in (("LONG", long_r), ("SHORT*", short_r)):
            (n, fw, fn, nm1, ow, on, cw, cn) = r
            if n == 0:
                print(f"{st:6.2f}{label:>6s}   no trades")
                continue
            print(f"{st:6.2f}{label:>6s}{n:8,d}{100*fw/n:8.1f}%{fn/n:9.4f}  |"
                  f"{nm1:7,d}{100*ow/max(nm1,1):10.1f}%{on/max(nm1,1):13.4f}"
                  f"{100*cw/max(nm1,1):12.1f}%{cn/max(nm1,1):15.4f}")
    print("\n*SHORT is the flipped simulation: same entry bar/ATR as the real LONG")
    print("trade above it, resolved with direction reversed - not a real signal.")
    print("'winrate'/'net per trade' = full period, original conservative rule.")
    print("'M1 n' = trades inside M1 coverage (2023-11-20 onward), used for both")
    print("orig and M1-fix columns so the before/after comparison is apples to apples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
