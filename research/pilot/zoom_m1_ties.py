"""Zoom into M1 data for the exact M5 bars that resolve_plane calls a 'tie'
(both stop and target level crossed within one M5 bar) for the worst RR=1:1
bucket, and determine which level was actually touched first.

For every tie found in expansion/M5, stop=0.75, target=1.0, this locates the
exact M5 bar (not just the entry bar - the bar where the tie occurs, which
can be several bars after entry) and its absolute stop/target PRICE levels,
then walks the M1 bars inside that 5-minute window in order to see which
price level is touched on an earlier minute. Falls back honestly to
NOT RESOLVABLE where M1 coverage does not reach that bar (before
2023-11-20) or where even M1 itself ties (both levels in the same minute).
Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import causal_chain as C
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

STOP, TARGET = 0.75, 1.0
M1_PATH = "data/XAUUSD_M1.csv"


def first_cross(cum, level):
    idx = np.flatnonzero(cum >= level)
    return int(idx[0]) if len(idx) else len(cum)


def find_ties(b5, streams, meta):
    """Every tie trade in this bucket: (entry_k, tie_bar_k, direction, entry,
    atr, stop_price_level, target_price_level, entry_mode_tag)."""
    out = []
    for tag, m in meta.items():
        if m["setup"] != "expansion" or m["tf"] != "M5" or float(m["stop"]) != STOP \
                or float(m["target"]) != TARGET:
            continue
        s = streams[m["stream"]]
        held = s["held"][:, int(m["plane"])]
        chosen, _ = C.causal_indices(s["entry_k"], s["order_k"], held)
        if not len(chosen):
            continue
        entry_k = s["entry_k"][chosen].astype(np.int64)
        atr = s["atr"][chosen]
        entries = s["entry"][chosen]
        direction = s["direction"][chosen]
        for i in range(len(chosen)):
            k = int(entry_k[i]); a = float(atr[i]); e = float(entries[i])
            d = int(direction[i])
            end = min(k + E.TIME_STOP_M5, len(b5))
            hi, lo = b5.h[k:end], b5.l[k:end]
            if d > 0:
                fav = (hi - e) / a
                adv = (e - lo) / a
                stop_price = e - STOP * a
                target_price = e + STOP * TARGET * a
            else:
                sp = np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)
                fav = (e - (lo + sp)) / a
                adv = ((hi + sp) - e) / a
                stop_price = e + STOP * a
                target_price = e - STOP * TARGET * a
            fav_c = np.maximum.accumulate(fav)
            adv_c = np.maximum.accumulate(adv)
            j_stop = first_cross(adv_c, STOP)
            j_tgt = first_cross(fav_c, STOP * TARGET)
            if j_stop < len(adv_c) and j_stop == j_tgt:
                out.append((k, k + j_stop, d, e, a, stop_price, target_price,
                           f"o{m['off']:g}e{m['exp']}"))
    return out


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    ties = find_ties(b5, streams, meta)
    print(f"total ties found: {len(ties):,}")

    m1_start_t = D.load_csv(M1_PATH).t[0]
    resolvable = [t for t in ties if b5.t[t[1]] >= int(m1_start_t)]
    print(f"ties with an M5 bar inside M1 coverage (>= "
          f"{__import__('datetime').datetime.fromtimestamp(int(m1_start_t), __import__('datetime').timezone.utc)}): "
          f"{len(resolvable):,} ({100*len(resolvable)/max(len(ties),1):.1f}%)")

    if not resolvable:
        print("nothing resolvable with the M1 file on disk.")
        return 0

    m1 = D.load_csv(M1_PATH)
    m1_t = m1.t.astype(np.int64)

    stop_first = target_first = still_tied = 0
    by_mode = defaultdict(lambda: [0, 0, 0])  # stop_first, target_first, tied
    examples = []
    rng = np.random.default_rng(0)
    order = rng.permutation(len(resolvable))
    for oi in order:
        (k, tie_k, d, e, a, stop_price, target_price, mode) = resolvable[oi]
        bar_t0 = int(b5.t[tie_k])
        bar_t1 = bar_t0 + 300
        i0 = int(np.searchsorted(m1_t, bar_t0))
        i1 = int(np.searchsorted(m1_t, bar_t1))
        if i1 - i0 < 1:
            continue  # no M1 bars found for this window either
        hi1 = m1.h[i0:i1]; lo1 = m1.l[i0:i1]
        if d > 0:
            hit_stop = np.flatnonzero(lo1 <= stop_price)
            hit_tgt = np.flatnonzero(hi1 >= target_price)
        else:
            sp1 = (np.maximum(m1.sp[i0:i1], E.SPREAD_FALLBACK) if m1.sp is not None
                  else np.full(i1 - i0, E.SPREAD_FALLBACK))
            hit_stop = np.flatnonzero((hi1 + sp1) >= stop_price)
            hit_tgt = np.flatnonzero((lo1 + sp1) <= target_price)
        js = int(hit_stop[0]) if len(hit_stop) else 10**9
        jt = int(hit_tgt[0]) if len(hit_tgt) else 10**9
        if js == jt:
            if js == 10**9:
                continue  # neither level actually touched at M1 res either - odd, skip
            still_tied += 1
            label = "TIED"
            by_mode[mode][2] += 1
        elif js < jt:
            stop_first += 1
            label = "STOP_FIRST"
            by_mode[mode][0] += 1
        else:
            target_first += 1
            label = "TARGET_FIRST"
            by_mode[mode][1] += 1
        if len(examples) < 30:
            examples.append((bar_t0, d, stop_price, target_price, js, jt, label,
                             i1 - i0, len(hit_stop), len(hit_tgt), mode))

    n_checked = stop_first + target_first + still_tied
    print(f"\nof {n_checked:,} ties actually re-examinable at 1-minute resolution "
          f"(RANDOM order, not iteration order):")
    print(f"  stop level truly touched FIRST:   {stop_first:6,d} "
          f"({100*stop_first/max(n_checked,1):.1f}%)  <- what resolve_plane assumed")
    print(f"  target level truly touched FIRST: {target_first:6,d} "
          f"({100*target_first/max(n_checked,1):.1f}%)  <- resolve_plane called this a loss too")
    print(f"  still tied even at 1-minute bars:  {still_tied:6,d} "
          f"({100*still_tied/max(n_checked,1):.1f}%)")

    print(f"\nbroken down by entry mode (offset/expiry) - is one mode driving the result?")
    for mode, (sf, tf, ti) in sorted(by_mode.items(), key=lambda x: -sum(x[1])):
        n = sf + tf + ti
        print(f"  {mode:8s} n={n:5,d}  stop_first={100*sf/max(n,1):5.1f}%  "
              f"target_first={100*tf/max(n,1):5.1f}%  tied={100*ti/max(n,1):5.1f}%")

    print(f"\n(first {len(examples)} examples, RANDOM order, with "
          f"label and how many M1 bars/touches were in the window)")
    import datetime as dt
    for (t0, d, sp_, tp_, js, jt, label, nbars, nstop, ntgt, mode) in examples:
        print(f"  {dt.datetime.fromtimestamp(t0, dt.timezone.utc)}  "
              f"dir={'LONG' if d>0 else 'SHORT'}  mode={mode:8s} "
              f"stop={sp_:.3f} target={tp_:.3f}  "
              f"stop@min{js if js<10**9 else 'never'}({nstop}x)  "
              f"target@min{jt if jt<10**9 else 'never'}({ntgt}x)  "
              f"m1_bars_in_window={nbars}  -> {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
