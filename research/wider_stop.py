#!/usr/bin/env python3
"""The same entries through a bracket that is not bleeding.

WHY THE STOP WIDTH IS THE VARIABLE

  bracket_bias.py measured, on random timing at zero cost with an engine
  verified to reproduce run_e01 exactly, that this project's standard bracket
  loses 0.09R to 0.12R per trade before any entry is chosen. Widening the stop
  from 1x to 2x cuts that to 0.03R, in the same direction on every market.

  The 2x width was chosen from the random-timing table alone. That table never
  sees the real entries, which is what keeps this from being the tweak-and-
  retest pattern the ledger exists to stop.

WHAT DOUBLING THE STOP DOES MECHANICALLY, STATED BEFORE THE RESULT

  R is (exit - entry) / dist. Doubling dist halves every R, including the
  skill and including the cost. So this is not a free improvement: the
  bracket penalty falls, and so does everything measured against it. The
  question is only whether the penalty falls FASTER than the skill does.

  Reporting the three terms separately rather than as one net number is the
  point of this file - a single expectancy would hide which of them moved.
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
from bracket_bias import engine, random_like, zero_cost
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal, reversion_signal

SEED = 17


def measure(P, fn, tick, stop_mult):
    d, I = fn(P)
    real = engine(P, d, I, tick, stop_mult=stop_mult)
    rd, rI = random_like(P, d, np.random.default_rng(SEED))
    ctrl = engine(P, rd, rI, tick, stop_mult=stop_mult)
    if real is None or ctrl is None:
        return None
    return dict(n=len(real[0]), E=float(real[0].mean()),
                ctrl=float(ctrl[0].mean()),
                skill=float(real[0].mean() - ctrl[0].mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("WIDER STOP - the three terms kept apart")
    print("=" * 104)
    print(__doc__.split("WHAT DOUBLING THE STOP DOES MECHANICALLY")[1])
    print("=" * 104)
    print(f"  {'market':<9}{'entry':<6}"
          f"{'--------- stop 1.0x ---------':^30}"
          f"{'--------- stop 2.0x ---------':^30}")
    print(f"  {'':<9}{'':<6}{'net E':>10}{'bracket':>10}{'skill':>10}"
          f"{'net E':>10}{'bracket':>10}{'skill':>10}")

    rows = []
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        tick = TICKS.get(sym, 0.00001)
        Pr = X.prep(df, 60)             # real cost
        for lab, fn in (("mom", momentum_signal), ("rev", reversion_signal)):
            out = {}
            for sm in (1.0, 2.0):
                out[sm] = measure(Pr, fn, tick, sm)
            if not all(out.values()):
                continue
            rows.append(dict(symbol=sym, entry=lab,
                             e1=out[1.0]["E"], c1=out[1.0]["ctrl"],
                             s1=out[1.0]["skill"], n1=out[1.0]["n"],
                             e2=out[2.0]["E"], c2=out[2.0]["ctrl"],
                             s2=out[2.0]["skill"], n2=out[2.0]["n"]))
            r = rows[-1]
            print(f"  {sym:<9}{lab:<6}{r['e1']:>+10.4f}{r['c1']:>+10.4f}"
                  f"{r['s1']:>+10.4f}{r['e2']:>+10.4f}{r['c2']:>+10.4f}"
                  f"{r['s2']:>+10.4f}", flush=True)

    if not rows:
        print("\n  nothing produced a comparison")
        return
    D = pd.DataFrame(rows)
    print("\n" + "=" * 104)
    print("THE THREE TERMS, POOLED")
    print("=" * 104)
    print(f"  {'':<22}{'stop 1.0x':>12}{'stop 2.0x':>12}{'change':>12}")
    for lab, k1, k2 in (("net expectancy", "e1", "e2"),
                        ("bracket (random)", "c1", "c2"),
                        ("entry skill", "s1", "s2")):
        v1, v2 = float(D[k1].mean()), float(D[k2].mean())
        print(f"  {lab:<22}{v1:>+12.4f}{v2:>+12.4f}{v2-v1:>+12.4f}")

    d = D.e2 - D.e1
    se = float(d.std(ddof=1) / math.sqrt(len(d)))
    t = float(d.mean() / se) if se > 0 else np.nan
    print(f"\n  improvement in net E   {d.mean():+.4f}R   "
          f"across-market t {t:+.2f}   positive on "
          f"{int((d > 0).sum())} of {len(d)}")
    e2 = float(D.e2.mean())
    print(f"  net expectancy at 2x   {e2:+.4f}R   "
          f"{'NON-NEGATIVE' if e2 >= 0 else 'still negative'}")
    print(f"  books positive at 2x   {int((D.e2 > 0).sum())} of {len(D)}")

    print(f"\n  Read the bracket row first. If it improved by more than the")
    print(f"  skill row lost, the widening paid for itself; if both halved")
    print(f"  together, the R denominator did all the work and nothing real")
    print(f"  changed. A single net figure cannot tell those apart, which is")
    print(f"  why they are not summed here.")
    D.to_csv(HERE / "wider_stop.csv", index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
