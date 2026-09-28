"""Is the standout cell's positive average driven by a few outlier wins?
stop=1.5 ATR, RR=1:7, LONG, M1-covered subset. Read-only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rr_sweep_finance import (load_long_entries, precompute_paths, first_cross,
                              TIME_STOP)
import basket_gate as A24
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

ST, TG = 1.5, 7.0


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    m1 = D.load_csv("data/XAUUSD_M1.csv")
    m1_t = m1.t.astype(np.int64)
    m1_start_t = int(m1.t[0])

    entry_k, atr, entries, at_open = load_long_entries(b5, streams, meta, ST)
    n = len(entry_k)
    d_arr = np.ones(n, np.int8)
    paths = precompute_paths(b5, entry_k, atr, entries, at_open, d_arr, ST)

    dollars, dates = [], []
    for (k, a, e, d, end, fav_c, adv_c, j_stop, last_c) in paths:
        if b5.t[k] < m1_start_t:
            continue
        risk = ST * a
        stop_price = e - ST * a
        target_price = e + ST * TG * a
        j_tgt = first_cross(fav_c, ST * TG)
        if j_stop < len(adv_c) and j_stop <= j_tgt:
            gross = -1.0
        elif j_tgt < len(fav_c):
            gross = float(TG)
        else:
            gross = (last_c - e) / risk
        net = gross - fee / risk
        # M1 tie correction
        if j_stop < len(adv_c) and j_stop == j_tgt:
            tie_bar_k = k + j_stop
            bar_t0 = int(b5.t[tie_bar_k]); bar_t1 = bar_t0 + 300
            i0 = int(np.searchsorted(m1_t, bar_t0))
            i1 = int(np.searchsorted(m1_t, bar_t1))
            if i1 - i0 >= 1:
                hi1, lo1 = m1.h[i0:i1], m1.l[i0:i1]
                hit_s = np.flatnonzero(lo1 <= stop_price)
                hit_t = np.flatnonzero(hi1 >= target_price)
                js1 = int(hit_s[0]) if len(hit_s) else 10**9
                jt1 = int(hit_t[0]) if len(hit_t) else 10**9
                if js1 > jt1:
                    net = float(TG) - fee / risk
        dollars.append(net * risk)  # $ at 0.01 lot (value/unit = 1.0)
        import datetime as dt
        dates.append(dt.datetime.fromtimestamp(int(b5.t[k]), dt.timezone.utc))

    dollars = np.array(dollars)
    total = dollars.sum()
    order = np.argsort(-dollars)
    print(f"stop={ST} RR=1:{TG:g} LONG, M1-covered subset: n={len(dollars):,}")
    print(f"total $ (0.01 lot): {total:,.2f}")
    for topn in (1, 3, 5, 10, 20):
        top_sum = dollars[order[:topn]].sum()
        print(f"  top {topn:2d} winning trade(s) contribute {top_sum:,.2f} "
              f"({100*top_sum/total:.1f}% of total)")
    print(f"\nbiggest 10 individual trades:")
    for i in order[:10]:
        print(f"  {dates[i]:%Y-%m-%d %H:%M}  ${dollars[i]:+,.2f}")
    print(f"\nwins: {int(np.sum(dollars>0)):,}  losses: {int(np.sum(dollars<=0)):,}")
    print(f"mean win $ {dollars[dollars>0].mean():,.2f}  "
          f"mean loss $ {dollars[dollars<=0].mean():,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
