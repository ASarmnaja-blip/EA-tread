#!/usr/bin/env python3
"""Bit-identity between the vectorised engine and the verified one.

NOT "AGREES TO FOUR DECIMALS"

  The reference engine is itself verified against run_e01 trade for trade, and
  every measured quantity in this project flows through it. A rewrite that
  agreed to four decimals would be a second engine, and the project would then
  have two answers to every question and no way to say which was the result.

  So the assertion is exact equality of three arrays - the R of every trade,
  the signal bar of every trade, and the holding period of every trade - on
  real data, across the whole market panel, every setup family, both stop
  widths, and the exit variants that open up the bracket.
"""
import math
import pathlib
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import engine_fast as F
import xauusd_1000_setups as X
from bracket_bias import engine as ref
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal, reversion_signal
from value_area_setups import breakout_signal, prior_value_areas, rotation_signal

FAIL = []


def main():
    t0 = time.time()
    print("VECTORISED ENGINE - identical, not similar")
    print("=" * 96)
    print(__doc__.split('NOT "AGREES TO FOUR DECIMALS"')[1])
    print(f"  {'market':<9}{'family':<11}{'variant':<22}{'ref n':>8}"
          f"{'fast n':>8}{'identical':>11}{'speedup':>9}")

    variants = (("stop 1.0x TP 1R", dict(stop_mult=1.0)),
                ("stop 2.0x TP 1R", dict(stop_mult=2.0)),
                ("stop 2.0x TP 2R", dict(stop_mult=2.0, tp_R=2.0)),
                ("stop only", dict(stop_mult=2.0, use_target=False)),
                ("time exit only", dict(stop_mult=2.0, use_stop=False,
                                        use_target=False)))
    tot_ref = tot_fast = 0.0
    checked = 0
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        tick = TICKS.get(sym, 0.00001)
        lo, hi, poc, _ = prior_value_areas(P)
        fams = (("momentum", lambda: momentum_signal(P)),
                ("reversion", lambda: reversion_signal(P)),
                ("va-rotate", lambda: rotation_signal(P, lo, hi, poc)),
                ("va-break", lambda: breakout_signal(P, lo, hi, poc)))
        for lab, fn in fams:
            d, I = fn()
            if int((d != 0).sum()) < 300:
                continue
            for vlab, kw in variants:
                ta = time.perf_counter()
                a = ref(P, d, I, tick, **kw)
                tb = time.perf_counter()
                b = F.engine(P, d, I, tick, **kw)
                tc = time.perf_counter()
                tot_ref += tb - ta
                tot_fast += tc - tb
                checked += 1
                if a is None or b is None:
                    ok = a is None and b is None
                    detail = "both empty" if ok else "one empty"
                    if not ok:
                        FAIL.append(f"{sym}/{lab}/{vlab}: {detail}")
                    continue
                ok = (len(a[0]) == len(b[0])
                      and np.array_equal(a[0], b[0])
                      and np.array_equal(a[1], b[1])
                      and np.array_equal(a[2], b[2]))
                if not ok:
                    FAIL.append(f"{sym}/{lab}/{vlab}")
                if vlab == "stop 2.0x TP 1R":
                    print(f"  {sym:<9}{lab:<11}{vlab:<22}{len(a[0]):>8,}"
                          f"{len(b[0]):>8,}{'yes' if ok else 'NO':>11}"
                          f"{(tb-ta)/max(tc-tb, 1e-9):>8.0f}x", flush=True)

    print("\n" + "=" * 96)
    print(f"  {checked} books compared across {len(MARKETS)} markets, "
          f"4 families, 5 exit variants")
    print(f"  reference {tot_ref:.1f}s   vectorised {tot_fast:.1f}s   "
          f"speedup {tot_ref/max(tot_fast, 1e-9):.0f}x")
    if FAIL:
        print(f"\n  {len(FAIL)} books DIFFER: {FAIL[:6]}")
        sys.exit(1)
    print("  every trade, every R, every holding period identical")


if __name__ == "__main__":
    main()
