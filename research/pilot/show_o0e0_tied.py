"""Show the actual M1 bars for the o0e0 (market-entry) trades that are still
'tied' even at 1-minute resolution, to see concretely why."""
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
from zoom_m1_ties import find_ties, M1_PATH, STOP, TARGET

def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    ties = find_ties(b5, streams, meta)
    m1 = D.load_csv(M1_PATH)
    m1_t = m1.t.astype(np.int64)
    m1_start_t = int(m1.t[0])

    shown = 0
    for (k, tie_k, d, e, a, stop_price, target_price, mode) in ties:
        if mode != "o0e0":
            continue
        bar_t0 = int(b5.t[tie_k])
        if bar_t0 < m1_start_t:
            continue
        bar_t1 = bar_t0 + 300
        i0 = int(np.searchsorted(m1_t, bar_t0))
        i1 = int(np.searchsorted(m1_t, bar_t1))
        if i1 - i0 < 1:
            continue
        hi1, lo1 = m1.h[i0:i1], m1.l[i0:i1]
        if d > 0:
            hit_stop = np.flatnonzero(lo1 <= stop_price)
            hit_tgt = np.flatnonzero(hi1 >= target_price)
        else:
            sp1 = np.maximum(m1.sp[i0:i1], E.SPREAD_FALLBACK)
            hit_stop = np.flatnonzero((hi1 + sp1) >= stop_price)
            hit_tgt = np.flatnonzero((lo1 + sp1) <= target_price)
        js = int(hit_stop[0]) if len(hit_stop) else 10**9
        jt = int(hit_tgt[0]) if len(hit_tgt) else 10**9
        if js != jt:
            continue  # only want the TIED ones
        import datetime as dt
        print(f"\n=== tied example: {dt.datetime.fromtimestamp(bar_t0, dt.timezone.utc)} "
              f"dir={'LONG' if d>0 else 'SHORT'} stop={stop_price:.3f} target={target_price:.3f} "
              f"(js={js if js<10**9 else 'never'}, jt={jt if jt<10**9 else 'never'}) ===")
        for j in range(i1 - i0):
            t = dt.datetime.fromtimestamp(int(m1.t[i0+j]), dt.timezone.utc)
            print(f"  min{j} {t:%H:%M}  O={m1.o[i0+j]:.3f} H={m1.h[i0+j]:.3f} "
                  f"L={m1.l[i0+j]:.3f} C={m1.c[i0+j]:.3f}")
        shown += 1
        if shown >= 4:
            break
    if shown == 0:
        print("no o0e0 tied examples found within M1 coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
