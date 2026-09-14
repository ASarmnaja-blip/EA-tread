#!/usr/bin/env python3
"""When a bar touches both the stop and the target, which came first?

THE ASSUMPTION AND WHAT IT COSTS

  run_e01 resolves those bars as losses. The code says why, plainly: "both in
  one bar with no intrabar order known: the spec's own G12 rule - assume
  stop-first, the conservative read". That is a deliberate modelling choice
  made in the absence of intrabar data, not a defect.

  Nobody measured its price. On random timing at zero cost:

      stop width   ambiguous bars   E as scored   E if resolved 50/50
        1.0x          8.5-10.5%     -0.093 to -0.118   -0.008 to -0.013
        2.0x           2.1-4.5%     -0.017 to -0.042   +0.002 to +0.004

  The assumption accounts for essentially the whole bracket penalty. Corrected
  to a coin flip, a random-timing control returns almost exactly zero, which
  is what a random control through a symmetric bracket should return.

WHY THAT MATTERS MORE THAN IT SOUNDS

  At the 1x stop the gap between the pessimistic reading and the neutral one
  is about 0.10R per trade. The largest drift-adjusted skill ever measured in
  this repo is +0.073R. So at that stop width the modelling assumption is
  worth more than any edge the project has ever found, and no result measured
  through it can distinguish a profitable rule from an unprofitable one - the
  answer is set by the assumption before the data is consulted.

  That is the argument for a wider stop, and it is not "wider stops make more
  money". It is that at 2x the ambiguity band narrows to about 0.03R, which
  is comparable to the edges rather than dominant over them.

WHAT THIS FILE DOES ABOUT IT

  For gold, the ambiguity is not unresolvable. XAUUSD minute data covers
  2019-2026, so for every H1 bar that touched both levels the minute path
  inside it says which was reached first. That turns an assumption into a
  measurement - for one market, over seven years.

  The result is a FREQUENCY, not a licence. If the true split is far from
  50/50 in either direction, every R in this repo needs restating; if it is
  near 50/50, the conservative rule has been costing 0.10R per trade for
  nothing. Either way the number replaces a guess.
"""
import argparse
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import xauusd_1000_setups as X
from bracket_bias import random_like, zero_cost
from p01_cross_market import TICKS, load_bidask_h1
from profile_setups import momentum_signal

SEED = 17


def minute_frame():
    import fetch_dukascopy as D
    m = D.load("2019-01-01", None, verbose=False)
    if m is None or len(m) == 0:
        return None
    for k in ("open", "high", "low", "close"):
        m[k] = (m[f"bid_{k}"] + m[f"ask_{k}"]) / 2
    return m


def resolve(P, dvec, Ivec, tick, stop_mult, m1, idx):
    """Walk the H1 book; for every ambiguous bar, ask the minute data."""
    N, A, spread = P["N"], P["A"], P["spread"]
    first_stop = first_tp = unresolved = 0
    amb_rows = []
    busy = -1
    for t in range(300, N - 1):
        d = dvec[t]
        if d == 0 or t <= busy:
            continue
        a = A[t]
        if not np.isfinite(a) or a <= 0:
            continue
        e = t + 1
        entry = P["ask_o"][e] if d > 0 else P["bid_o"][e]
        inval = Ivec[t]
        if not np.isfinite(entry) or not np.isfinite(inval):
            continue
        b = max(0.10 * a, spread[t] if np.isfinite(spread[t]) else 0, 2 * tick)
        raw = (X.tick_round(inval - b, False, tick) if d > 0
               else X.tick_round(inval + b, True, tick))
        dist = abs(entry - raw) * stop_mult
        if dist <= 0:
            continue
        stop = entry - d * dist
        sp = spread[e] if np.isfinite(spread[e]) else spread[t]
        if not np.isfinite(sp) or sp > 0.10 * a:
            continue
        if not (max(0.30 * a, 5 * sp) <= abs(entry - raw) <= 3 * a):
            continue
        if (entry <= raw) if d > 0 else (entry >= raw):
            continue
        target = entry + d * dist
        ex_lo = P["bid_l"] if d > 0 else P["ask_l"]
        ex_hi = P["bid_h"] if d > 0 else P["ask_h"]
        bar = None
        for k in range(e, min(e + X.HOLD_BARS, N)):
            hs = (ex_lo[k] <= stop) if d > 0 else (ex_hi[k] >= stop)
            ht = (ex_hi[k] >= target) if d > 0 else (ex_lo[k] <= target)
            if hs and ht:
                bar = k
                break
            if hs or ht:
                bar = None
                break
        if bar is None:
            busy = min(e + X.HOLD_BARS - 1, N - 1)
            continue
        # the ambiguous bar: ask the minutes inside it
        t0 = idx[bar]
        t1 = t0 + pd.Timedelta(hours=1)
        w = m1.loc[(m1.index >= t0) & (m1.index < t1)]
        busy = bar
        if len(w) < 5:
            unresolved += 1
            continue
        lo = (w["bid_low"] if d > 0 else w["ask_low"]).to_numpy()
        hi = (w["bid_high"] if d > 0 else w["ask_high"]).to_numpy()
        s_at = np.where((lo <= stop) if d > 0 else (hi >= stop))[0]
        t_at = np.where((hi >= target) if d > 0 else (lo <= target))[0]
        if len(s_at) == 0 and len(t_at) == 0:
            unresolved += 1
            continue
        si = s_at[0] if len(s_at) else 10 ** 9
        ti = t_at[0] if len(t_at) else 10 ** 9
        if si == ti:
            unresolved += 1          # same MINUTE - still ambiguous, honestly
            continue
        if si < ti:
            first_stop += 1
        else:
            first_tp += 1
        amb_rows.append(dict(bar=int(bar), stop_first=bool(si < ti),
                             minute_gap=int(abs(si - ti))))
    return dict(stop_first=first_stop, tp_first=first_tp,
                unresolved=unresolved, rows=amb_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stops", default="1.0,2.0")
    a = ap.parse_args()
    t0 = time.time()
    stops = [float(x) for x in a.stops.split(",")]

    print("AMBIGUOUS BARS - resolved with minute data, for gold")
    print("=" * 92)
    print(__doc__.split("WHAT THIS FILE DOES ABOUT IT")[1])

    m1 = minute_frame()
    if m1 is None:
        print("  no minute data")
        return
    print(f"  minute bars available: {len(m1):,} "
          f"({m1.index[0].date()} -> {m1.index[-1].date()})")

    df = load_bidask_h1("XAUUSD")
    df = df[df.index >= m1.index[0]]
    P = X.prep(zero_cost(df), 60)
    idx = P["idx"]
    d, I = momentum_signal(P)
    print(f"  H1 bars in the same window: {P['N']:,}\n")

    print(f"  {'stop':<7}{'ambiguous':>11}{'stop first':>12}{'target first':>14}"
          f"{'unresolved':>12}{'stop-first share':>18}")
    for sm in stops:
        rd, rI = random_like(P, d, np.random.default_rng(SEED))
        r = resolve(P, rd, rI, 0.001, sm, m1, idx)
        tot = r["stop_first"] + r["tp_first"]
        if tot == 0:
            print(f"  {sm:<7.1f}  none resolved")
            continue
        share = r["stop_first"] / tot
        se = math.sqrt(share * (1 - share) / tot)
        print(f"  {sm:<7.1f}{tot + r['unresolved']:>11,}{r['stop_first']:>12,}"
              f"{r['tp_first']:>14,}{r['unresolved']:>12,}"
              f"{share*100:>16.1f}%")
        print(f"  {'':<7}95% CI on that share: "
              f"[{(share-1.96*se)*100:.1f}%, {(share+1.96*se)*100:.1f}%]"
              f"   (50% would mean the coin flip is right)")

    print(f"\n  Read the share against 50%. Far above and the conservative rule")
    print(f"  is roughly correct and every R here stands. Far below and the")
    print(f"  rule has been charging losses that did not happen. Near 50% and")
    print(f"  the assumption has cost about 0.10R a trade at the 1x stop for")
    print(f"  no reason - which is more than any edge this project has found.")
    print(f"\n  Gold only, 2019-2026. Nothing here transfers to the other eight")
    print(f"  markets, whose minute data this repo does not hold.")
    print(f"  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
