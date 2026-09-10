#!/usr/bin/env python3
"""A finer grid around the wick-tip winner, same discipline as before.

CORRECTION (see RESEARCH_FINDINGS.md)
  This file's grid originally included `wick_min`, a filter requiring the fill
  bar's own tail-to-range ratio to clear a threshold. That is a look-ahead bug:
  the ratio needs the bar's CLOSE, which is only known after the bar the limit
  was filled on has finished, so every accepted trade had already enjoyed that
  bar's own recovery from low to close before the "entry" was even evaluated
  going forward. Calibrated on a driftless random walk at zero cost, wick_min=0
  returns E near zero as it must; wick_min>0 alone was worth +0.4R to +1.1R of
  pure fiction, growing with the threshold - which is exactly the shape this
  file's first run showed, and which was reported, uncaught, as a real result.
  `wick_min` is now fixed at 0.0 (disabled) and the finer grid runs on the
  parameters that ARE legitimate: look, offset, stop and target.

WHY THIS IS A SEPARATE FILE AND NOT JUST A BIGGER GRID
  wick_tip_tuner.py already searched 306 configurations and reported the
  honest result: expected max of noise for that many draws is 3.383. Widening
  the same search to more parameters makes the multiple-comparison problem
  WORSE, not better, unless the bar widens with it.

  So this file is explicit about what it is: a local refinement around one
  already-identified region (look~24, off~1.0, sl~1.0, tp~1.5), not a fresh
  global search. The expected-max bar is recomputed for the actual grid size
  searched, and the tuning/holdout split and random control are unchanged from
  wick_tip_tuner.py.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from wick_tip_tuner import fetch, prep, trades_limit, score, control, TUNE_FRAC

SPREADS = (0.26, 0.7525)

def main():
    df = fetch("GC=F", "60d", "5m")
    cut = df.index[int(len(df)*TUNE_FRAC)]
    Ptune = prep(df[df.index < cut])
    Ptest = prep(df[df.index >= cut])
    print(f"data {len(df):,} bars {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"tune {df.index[0].date()} -> {cut.date()}  |  "
          f"held out {cut.date()} -> {df.index[-1].date()}\n")

    grid = []
    for look in (12, 16, 20, 24, 28, 32, 40, 48, 64):
        for off in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            for sl in (0.8, 1.0, 1.2, 1.5):
                for tp in (0.7, 1.0, 1.2, 1.5, 1.8, 2.0):
                    grid.append(dict(look=look, off_atr=off, sl_atr=sl,
                                     tp_mult=tp, wick_min=0.0))
    print(f"grid size: {len(grid)} configurations (wick_min fixed at 0.0 - "
          f"disabled, see the correction note above)\n")

    rows = []
    for kw in grid:
        s = score(trades_limit(Ptune, spread=SPREADS[0], **kw), floor=40)
        if s is None: continue
        rows.append(dict(kw=kw, **s))
    R = pd.DataFrame(rows)
    k = len(R)
    bar = math.sqrt(2*math.log(k)) if k > 1 else float("nan")
    print(f"{k} configs cleared the 40-trade tuning floor")
    print(f"expected max of {k} noise draws: sqrt(2*ln {k}) = {bar:.3f}\n")

    hdr = (f"{'look':>5}{'off':>6}{'sl':>5}{'tp':>5}{'wick':>6}{'|':>2}"
           f"{'n':>5}{'win':>7}{'RR':>6}{'PF':>6}{'E(R)':>7}{'t':>7}")
    print("TOP 15 BY TUNING E, tuning window")
    print(hdr); print("-"*len(hdr))
    top = R.sort_values("E", ascending=False).head(15)
    for _, x in top.iterrows():
        kw = x.kw
        print(f"{kw['look']:>5}{kw['off_atr']:>6.2f}{kw['sl_atr']:>5.1f}"
              f"{kw['tp_mult']:>5.1f}{kw['wick_min']:>6.2f}{'|':>2}"
              f"{x.n:>5}{x.win:>7.3f}{x.rr:>6.2f}{x.pf:>6.2f}"
              f"{x.E:>+7.3f}{x.t:>7.2f}")

    print(f"\n{'='*74}")
    print("HELD-OUT CONFIRMATION - top 15, touched once, both spreads")
    print(f"{'='*74}")
    hdr2 = (f"{'config':<42}{'n':>5}{'win':>7}{'PF':>6}{'E(R)':>7}{'t':>7}  ctrl E")
    print(hdr2); print("-"*len(hdr2))
    survivors = []
    for _, x in top.iterrows():
        kw = x.kw
        tag = (f"L{kw['look']} o{kw['off_atr']} sl{kw['sl_atr']} "
               f"tp{kw['tp_mult']} w{kw['wick_min']}")
        for sp in SPREADS:
            tr = trades_limit(Ptest, spread=sp, **kw)
            s = score(tr, floor=15)
            if s is None:
                print(f"{tag+f' sp{sp}':<42}   too few"); continue
            cs = control(Ptest, tr, kw["sl_atr"], kw["tp_mult"], sp, reps=8)
            print(f"{tag+f' sp{sp}':<42}{s['n']:>5}{s['win']:>7.3f}"
                  f"{s['pf']:>6.2f}{s['E']:>+7.3f}{s['t']:>7.2f}"
                  f"  {cs['E']:+.3f}" if cs else "  n/a")
            if s['E'] > 0 and cs and s['E'] > cs['E'] and s['t'] > 2.0:
                survivors.append((tag, sp, s, cs))
        print()

    print(f"{'='*74}")
    print(f"{len(survivors)} config/spread combination(s) beat their control "
          f"at t > 2.0 in the holdout.")
    if survivors:
        print("Still measured on the same one 24-day holdout as the original")
        print("306-config search - this is refinement, not new confirmation.")
    print(f"{'='*74}")

if __name__ == "__main__":
    main()
