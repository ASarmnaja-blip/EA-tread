"""Percentage table: for expansion/M5, RR=1:1 (target R=1.0), LONG direction,
across every stop ATR multiple in the declared grid (0.75, 1.0, 1.5, 2.0,
3.0) - what share of trades are same-bar ties at M5 resolution, and of
those, what share resolve as stop-first / target-first / still-tied once
checked against real M1 data (restricted to the period M1 covers).
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


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
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
            rows.append((st, 0, 0, 0, 0, 0, 0))
            continue
        entry_k = np.concatenate([p[0] for p in parts])
        atr = np.concatenate([p[1] for p in parts])
        entries = np.concatenate([p[2] for p in parts])
        at_open = np.concatenate([p[3] for p in parts])
        n_total = len(entry_k)

        n_ties_all = 0
        n_ties_m1 = n_stop1 = n_tgt1 = n_tied1 = 0
        for i in range(n_total):
            k = int(entry_k[i]); a = float(atr[i]); e = float(entries[i])
            ao = bool(at_open[i])
            end = min(k + E.TIME_STOP_M5, len(b5))
            hi, lo = b5.h[k:end], b5.l[k:end]
            fav = (hi - e) / a
            adv = (e - lo) / a
            stop_price = e - st * a
            target_price = e + st * TARGET * a
            if not ao and len(fav):
                fav = fav.copy(); fav[0] = -np.inf
            fav_c = np.maximum.accumulate(fav)
            adv_c = np.maximum.accumulate(adv)
            j_stop = first_cross(adv_c, st)
            j_tgt = first_cross(fav_c, st * TARGET)
            if not (j_stop < len(adv_c) and j_stop == j_tgt):
                continue
            n_ties_all += 1
            if b5.t[k] < m1_start_t:
                continue
            tie_bar_k = k + j_stop
            bar_t0 = int(b5.t[tie_bar_k]); bar_t1 = bar_t0 + 300
            i0 = int(np.searchsorted(m1_t, bar_t0))
            i1 = int(np.searchsorted(m1_t, bar_t1))
            if i1 - i0 < 1:
                continue
            n_ties_m1 += 1
            hi1, lo1 = m1.h[i0:i1], m1.l[i0:i1]
            hit_s = np.flatnonzero(lo1 <= stop_price)
            hit_t = np.flatnonzero(hi1 >= target_price)
            js1 = int(hit_s[0]) if len(hit_s) else 10**9
            jt1 = int(hit_t[0]) if len(hit_t) else 10**9
            if js1 == jt1:
                n_tied1 += 1
            elif js1 < jt1:
                n_stop1 += 1
            else:
                n_tgt1 += 1
        rows.append((st, n_total, n_ties_all, n_ties_m1, n_stop1, n_tgt1, n_tied1))

    print("expansion/M5, target R = 1.0 (RR 1:1), LONG direction, by stop ATR\n")
    print(f"{'stop ATR':>9s}{'trades':>9s}{'tie % (M5)':>12s}{'ties w/ M1':>11s}"
          f"{'stop-first %':>13s}{'target-first %':>16s}{'tied@M1 %':>11s}")
    for (st, n_total, n_ties_all, n_ties_m1, n_stop1, n_tgt1, n_tied1) in rows:
        tie_pct = 100 * n_ties_all / n_total if n_total else float("nan")
        if n_ties_m1:
            sp = 100 * n_stop1 / n_ties_m1
            tp = 100 * n_tgt1 / n_ties_m1
            tip = 100 * n_tied1 / n_ties_m1
        else:
            sp = tp = tip = float("nan")
        print(f"{st:9.2f}{n_total:9,d}{tie_pct:11.2f}%{n_ties_m1:11,d}"
              f"{sp:12.1f}%{tp:15.1f}%{tip:10.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
