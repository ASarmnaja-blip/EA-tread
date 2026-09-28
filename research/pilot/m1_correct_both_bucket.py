"""The true, M1-corrected values for BOTH numbers the operator asked about:
the real LONG entries in expansion/M5/stop=0.75/target=1.0 (-0.53 R
original), and the artificial FLIPPED-direction recomputation of those same
entries (-0.77 R original). Both restricted to the M1-covered subset so the
before/after comparison is apples to apples on the identical trades.
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

STOP, TARGET = 0.75, 1.0


def first_cross(cum, level):
    idx = np.flatnonzero(cum >= level)
    return int(idx[0]) if len(idx) else len(cum)


def resolve_and_correct(b5, m1, m1_t, m1_start_t, entry_k, atr, entries,
                        at_open, direction, fee, label):
    n_total = len(entry_k)
    keep = b5.t[entry_k] >= m1_start_t
    n_m1 = int(keep.sum())
    print(f"\n=== {label}: {n_total:,} trades total, {n_m1:,} "
          f"({100*n_m1/max(n_total,1):.1f}%) inside M1 coverage ===")

    orig_all, orig_m1, corr_m1 = [], [], []
    n_ties = n_stop1 = n_tgt1 = n_tied1 = 0
    for i in range(n_total):
        k = int(entry_k[i]); a = float(atr[i]); e = float(entries[i])
        d = int(direction[i]); ao = bool(at_open[i])
        risk = STOP * a
        end = min(k + E.TIME_STOP_M5, len(b5))
        hi, lo = b5.h[k:end], b5.l[k:end]
        if d > 0:
            fav = (hi - e) / a; adv = (e - lo) / a
            stop_price = e - STOP * a; target_price = e + STOP * TARGET * a
        else:
            sp = np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)
            fav = (e - (lo + sp)) / a; adv = ((hi + sp) - e) / a
            stop_price = e + STOP * a; target_price = e - STOP * TARGET * a
        if not ao and len(fav):
            fav = fav.copy(); fav[0] = -np.inf
        fav_c = np.maximum.accumulate(fav)
        adv_c = np.maximum.accumulate(adv)
        j_stop = first_cross(adv_c, STOP)
        j_tgt = first_cross(fav_c, STOP * TARGET)

        if j_stop < len(adv_c) and j_stop <= j_tgt:
            gross = -1.0
        elif j_tgt < len(fav_c):
            gross = float(TARGET)
        else:
            last_c = float(b5.c[end - 1] if d > 0 else b5.c[end - 1] + E.SPREAD_FALLBACK)
            gross = d * (last_c - e) / risk
        orig_net = gross - fee / risk
        orig_all.append(orig_net)

        if not (b5.t[k] >= m1_start_t):
            continue
        orig_m1.append(orig_net)
        corr_net = orig_net
        if j_stop < len(adv_c) and j_stop == j_tgt:
            n_ties += 1
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
                if js1 == jt1:
                    n_tied1 += 1
                elif js1 < jt1:
                    n_stop1 += 1
                else:
                    n_tgt1 += 1
                    corr_net = float(TARGET) - fee / risk
        corr_m1.append(corr_net)

    orig_all = np.array(orig_all); orig_m1 = np.array(orig_m1); corr_m1 = np.array(corr_m1)
    print(f"  ORIGINAL, full period (all {n_total:,}):      "
          f"net/tr {orig_all.mean():+.4f}  win {100*np.mean(orig_all>0):.1f}%")
    print(f"  ORIGINAL, M1-covered subset only ({n_m1:,}):  "
          f"net/tr {orig_m1.mean():+.4f}  win {100*np.mean(orig_m1>0):.1f}%")
    print(f"  M1-CORRECTED, same subset ({n_m1:,}):         "
          f"net/tr {corr_m1.mean():+.4f}  win {100*np.mean(corr_m1>0):.1f}%")
    print(f"  ties in subset: {n_ties:,} ({100*n_ties/max(n_m1,1):.1f}%)  "
          f"of which stop-first {n_stop1}  target-first {n_tgt1}  "
          f"still tied@M1 {n_tied1}")
    return orig_all.mean(), orig_m1.mean(), corr_m1.mean()


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    m1 = D.load_csv("data/XAUUSD_M1.csv")
    m1_t = m1.t.astype(np.int64)
    m1_start_t = int(m1.t[0])

    long_parts = []
    for tag, m in meta.items():
        if m["setup"] != "expansion" or m["tf"] != "M5" or float(m["stop"]) != STOP \
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
        long_parts.append((s["entry_k"][idx].astype(np.int64), s["atr"][idx],
                          s["entry"][idx], s["at_open"][idx], s["direction"][idx]))
    entry_k = np.concatenate([p[0] for p in long_parts])
    atr = np.concatenate([p[1] for p in long_parts])
    entries = np.concatenate([p[2] for p in long_parts])
    at_open = np.concatenate([p[3] for p in long_parts])
    direction = np.concatenate([p[4] for p in long_parts])
    print(f"real LONG entries assembled: {len(entry_k):,} (expect 14,213)")

    full1, sub1, corr1 = resolve_and_correct(
        b5, m1, m1_t, m1_start_t, entry_k, atr, entries, at_open, direction,
        fee, "REAL LONG entries (original direction)")

    flipped_direction = -direction
    full2, sub2, corr2 = resolve_and_correct(
        b5, m1, m1_t, m1_start_t, entry_k, atr, entries, at_open, flipped_direction,
        fee, "FLIPPED (same entries, reversed direction)")

    print("\n=== FINAL ANSWER ===")
    print(f"{'':45s}{'full period':>13s}{'M1-subset orig':>16s}{'M1-corrected':>14s}")
    print(f"{'LONG (real)':45s}{full1:13.4f}{sub1:16.4f}{corr1:14.4f}")
    print(f"{'SHORT (flipped, same entries)':45s}{full2:13.4f}{sub2:16.4f}{corr2:14.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
