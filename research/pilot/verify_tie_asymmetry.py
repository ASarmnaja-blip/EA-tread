"""Verify the mechanism: how often does the worst RR=1:1 bucket's bar hit both
the stop and target level within the SAME M5 bar (a genuine tie), and does
resolve_plane's "tie goes to stop" convention charge a loss to both the
original direction and the mirrored flip on those same bars?

If ties are common for this bucket (expansion/M5/stop=0.75), that is the
mechanism: a same-bar tie makes BOTH directions lose independently, which is
why flipping a heavy loser at RR 1:1 does not produce a mirror-image winner.
Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import causal_chain as C
import historical_regime_walkforward as hist
import mtf_engine as E

STOP, TARGET = 0.75, 1.0


def first_cross(cum, level):
    idx = np.flatnonzero(cum >= level)
    return int(idx[0]) if len(idx) else len(cum)


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL

    n_tie = n_long_stop_short_stop = n_total = 0
    net_on_tie_long, net_on_tie_short = [], []
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
            else:
                sp = np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)
                fav = (e - (lo + sp)) / a
                adv = ((hi + sp) - e) / a
            fav_c = np.maximum.accumulate(fav)
            adv_c = np.maximum.accumulate(adv)
            j_stop = first_cross(adv_c, STOP)
            j_tgt = first_cross(fav_c, STOP * TARGET)
            n_total += 1
            if j_stop < len(adv_c) and j_stop == j_tgt:
                n_tie += 1
                # what would the OTHER direction's own resolve_plane call
                # (mirrored, same bar) say happens on this exact tie bar?
                if d > 0:
                    fav_m = (e - (lo + np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK))) / a
                    adv_m = ((hi + np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)) - e) / a
                else:
                    fav_m = (hi - e) / a
                    adv_m = (e - lo) / a
                fav_mc = np.maximum.accumulate(fav_m)
                adv_mc = np.maximum.accumulate(adv_m)
                j_stop_m = first_cross(adv_mc, STOP)
                j_tgt_m = first_cross(fav_mc, STOP * TARGET)
                mirrored_also_stops = j_stop_m < len(adv_mc) and j_stop_m <= j_tgt_m
                if mirrored_also_stops:
                    n_long_stop_short_stop += 1

    print(f"bucket: expansion/M5 stop={STOP} target={TARGET}, total trades checked={n_total:,}")
    print(f"trades where stop-index == target-index (genuine same-bar tie): "
          f"{n_tie:,} ({100*n_tie/max(n_total,1):.1f}%)")
    print(f"of those ties, the mirrored opposite direction ALSO resolves as "
          f"'its own stop hit first': {n_long_stop_short_stop:,} "
          f"({100*n_long_stop_short_stop/max(n_tie,1):.1f}% of ties)")
    print("\nthis is the mechanism: on a tie bar, BOTH directions' resolver "
          "independently assume their own stop was hit first, so both are "
          "charged a loss on the same bar - breaking the RR 1:1 mirror.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
