#!/usr/bin/env python3
"""The 20-bar H1 breakout on six years of gold instead of two and a half.

WHY
  `breakout_h1_dd_target.py` replicated the one setup an externally-supplied
  workbook found promising, and the result was genuinely the best this program
  has produced: E +0.104R on 377 trades, stable across a chronological split
  (first half +0.112, second half +0.096), and at a matched 30% drawdown it
  returned +77% a year against buy-and-hold gold's +29%.

  But it rests on 2.4 years, because that is all Yahoo will serve at H1. Two
  and a half years of gold is ONE regime - a historic bull run. The cross-
  market test already said the rule is adverse on average elsewhere (mean
  skill -0.033, t -2.87, positive in 6 of 26 markets), which means gold's
  number is either a gold-specific effect or a window. Only more gold history
  separates those two.

THE DATA
  PAXG/USDT M15 from `fetch_m15_gold.py`'s cache, resampled to H1, weekends
  dropped so the session structure matches the metal. That file validated the
  proxy against GC=F (H1 return correlation 0.9041) and documents what it is
  not: a crypto-venue instrument with its own spread and premium, NOT the
  user's XAUUSD broker feed. It buys roughly 2.5x the history at the cost of
  some fidelity - a trade this repo has made before and labelled every time.

WHAT IS FROZEN
  Every rule parameter is imported from `breakout_h1_dd_target.py` unchanged.
  Nothing is re-tuned for this data. If the numbers fall apart here, that is
  the answer, not an invitation to search for parameters that survive.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from breakout_h1_dd_target import (prep, signals, book, stats, skill_vs_control,
                                   equity_path, COST_BASE, COST_HIGH)
from fetch_m15_gold import fetch_paxg_m15, drop_weekend

def to_h1(m15):
    h = m15.resample("1h").agg({"open": "first", "high": "max",
                                "low": "min", "close": "last"}).dropna()
    return h

def main():
    print("20-bar H1 breakout, six years of gold (PAXG proxy).\n")
    m15 = drop_weekend(fetch_paxg_m15())
    df = to_h1(m15)
    years = (df.index[-1] - df.index[0]).days / 365.25
    days = (df.index[-1] - df.index[0]).days
    print(f"PAXG H1: {len(df):,} bars  {df.index[0].date()} -> "
          f"{df.index[-1].date()}  ({years:.2f} years)\n")

    P = prep(df)
    sig = signals(P)

    print(f"  {'cost':<14}{'n':>6}{'win':>7}{'PF':>7}{'E(R)':>9}{'t':>7}"
          f"{'net R':>10}{'ctrlE':>9}{'skill':>9}{'skill t':>9}")
    ref = None
    for nm, cost in (("base 0.36", COST_BASE), ("high 0.8525", COST_HIGH)):
        rs, sk = skill_vs_control(P, sig, cost)
        if rs is None: continue
        if ref is None: ref = cost
        print(f"  {nm:<14}{rs['n']:>6}{rs['win']:>7.3f}{rs['pf']:>7.2f}"
              f"{rs['E']:>+9.4f}{rs['t']:>+7.2f}{rs['net']:>+10.2f}"
              f"{sk['ctrlE']:>+9.4f}{sk['skill']:>+9.4f}{sk['t']:>+9.2f}")

    trades = book(P, sig, ref)
    rs = stats(trades)
    print(f"\n  2.4-year GC=F reference: n=377, E +0.1037, skill +0.0707 (t +1.59)")
    print(f"  R per calendar day here: {rs['net']/days:+.4f} "
          f"(the 1R/day target needs {1.0/max(rs['net']/days,1e-9):.0f}x more)")

    print("\nSTABILITY BY YEAR - an edge that is one regime shows up as one")
    print("good year carrying the rest.")
    print(f"  {'year':<8}{'n':>6}{'E(R)':>9}{'t':>7}{'net R':>10}{'win':>7}")
    yr = df.index[[i for i, _ in trades]].year
    for y in sorted(set(yr)):
        part = [t for t, yy in zip(trades, yr) if yy == y]
        st = stats(part)
        if st is None:
            print(f"  {y:<8}{len(part):>6}   too few"); continue
        print(f"  {y:<8}{st['n']:>6}{st['E']:>+9.4f}{st['t']:>+7.2f}"
              f"{st['net']:>+10.2f}{st['win']:>7.3f}")

    print(f"\nSIZING AGAINST THE 35% DRAWDOWN CEILING, six-year path")
    print(f"  {'risk/trade':<12}{'final':>10}{'CAGR':>9}{'max DD':>9}{'<=35%?':>8}")
    best = None
    for f in (0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04):
        eq, dd = equity_path(trades, f)
        cagr = eq ** (1 / years) - 1 if eq > 0 else -1
        fits = dd <= 0.35
        if fits and (best is None or cagr > best[1]): best = (f, cagr, dd)
        print(f"  {f:<12.3f}{eq:>10.3f}{cagr:>+9.2%}{dd:>9.2%}"
              f"{'yes' if fits else 'NO':>8}")
    if best:
        print(f"\n  Best inside 35%: risk {best[0]:.1%} -> {best[1]:+.2%} a year, "
              f"DD {best[2]:.2%}")

    c = df.close.to_numpy(float)
    eqh = c / c[0]
    bh_dd = float(np.max(1.0 - eqh / np.maximum.accumulate(eqh)))
    print(f"\n  buy & hold over the same six years: "
          f"{(c[-1]/c[0])**(1/years)-1:+.2%} a year, max DD {bh_dd:.2%}")

    print("\nDOES THE EXIT WASTE THE ENTRY? Same signal, same planned risk,")
    print("same 24-bar cap - only the exit changes. Three pre-registered")
    print("designs, so the bar is |t| > 2.39 (Bonferroni, 3 comparisons).")
    print("  (b) is this repo's already-validated trail-2xATR + BE-at-1R shape,")
    print("  re-expressed against the breakout's own planned risk, not a search.")
    print(f"\n  {'exit':<26}{'n':>6}{'E(R)':>9}{'t':>7}{'net R':>10}"
          f"{'skill':>9}{'skill t':>9}{'CAGR@35%':>10}")
    for label, ex in (("(a) fixed 2R target", "target"),
                      ("(b) trail 1R + BE at 1R", "trail"),
                      ("(c) no target, hold 24", "hold")):
        tr = book(P, sig, ref, exit_mode=ex)
        st = stats(tr)
        if st is None:
            print(f"  {label:<26}  too few trades"); continue
        _, sk2 = skill_vs_control(P, sig, ref, exit_mode=ex)
        bc = None
        for f in (0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05):
            eq, dd = equity_path(tr, f)
            if dd <= 0.35 and eq > 0:
                cg = eq ** (1 / years) - 1
                if bc is None or cg > bc: bc = cg
        print(f"  {label:<26}{st['n']:>6}{st['E']:>+9.4f}{st['t']:>+7.2f}"
              f"{st['net']:>+10.2f}{sk2['skill']:>+9.4f}{sk2['t']:>+9.2f}"
              f"{(f'{bc:+.2%}' if bc is not None else 'n/a'):>10}")

if __name__ == "__main__":
    main()
