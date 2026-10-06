#!/usr/bin/env python3
"""The 20-bar breakout on 22 years of REAL XAUUSD, priced at the REAL spread.

WHAT CHANGED SINCE THE LAST RUN
  `breakout_h1_dd_target.py` tested this rule on 2.4 years of GC=F futures and
  `breakout_h1_long_history.py` on six years of PAXG, a crypto token. Both used
  a CONSTANT cost assumption (0.36 base, 0.8525 high). `fetch_dukascopy.py` has
  now replaced all three compromises at once:

    instrument   spot XAUUSD, the thing actually traded - not a future, not a
                 token
    history      2004-2026, 130,310 clean H1 bars, validated at 0.877 daily
                 return correlation against GC=F
    cost         the MEASURED bid/ask spread of the entry bar, per trade, so a
                 2004 trade is priced at 2004's 10.3bp spread and a 2026 trade
                 at 2026's 1.5bp - a constant cannot represent both

THE QUESTION THIS ANSWERS
  The rule's skill cleared the bar on six years (t +3.25) but its money was
  concentrated: three losing years, then +48R of +51R arriving in 2025-2026,
  gold's strongest trend in a decade. Twenty-two years contains gold's 2011-2015
  BEAR MARKET and the 2015-2018 RANGE. If the rule survives those, it is a
  system; if it only prints in trends, it is a trend harvester and has to be
  sized and sold as one.

  Nothing is re-tuned here. Every parameter is imported from the frozen rule.

PRE-REGISTERED
  The rule is called regime-independent only if its skill is positive in BOTH
  the trending and the non-trending half of the years, each measured against
  its own matched control. Stated before the run.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
from breakout_h1_dd_target import (prep, signals, book, stats, skill_vs_control,
                                   equity_path, COST_BASE, COST_HIGH)

COMMISSION = 0.07      # per round trip, price units; a typical ECN gold fee

def main():
    print("20-bar H1 breakout, real XAUUSD, real spread, 2004-2026.\n")
    m = D.clean(D.mid(D.load_h1(2003, 2026)))
    years = (m.index[-1] - m.index[0]).days / 365.25
    days = (m.index[-1] - m.index[0]).days
    print(f"XAUUSD H1: {len(m):,} bars  {m.index[0].date()} -> {m.index[-1].date()}"
          f"  ({years:.1f} years)")
    print(f"measured spread: median {m.spread.median():.3f}, "
          f"2026 median {m.spread[m.index.year==2026].median():.3f}\n")

    P = prep(m)
    sig = signals(P)
    real = m.spread.to_numpy(float)                 # one full spread per round trip
    real_comm = real + COMMISSION

    print("COST MATTERS MORE THAN ANY PARAMETER HERE")
    print(f"  {'cost basis':<28}{'n':>6}{'win':>7}{'E(R)':>9}{'t':>7}"
          f"{'net R':>10}{'skill':>9}{'skill t':>9}")
    rows = {}
    for nm, cost in (("assumed 0.36 (old base)", COST_BASE),
                     ("assumed 0.8525 (old high)", COST_HIGH),
                     ("MEASURED spread", real),
                     ("MEASURED + 0.07 commission", real_comm)):
        rs, sk = skill_vs_control(P, sig, cost)
        if rs is None: continue
        rows[nm] = (rs, sk, cost)
        print(f"  {nm:<28}{rs['n']:>6}{rs['win']:>7.3f}{rs['E']:>+9.4f}"
              f"{rs['t']:>+7.2f}{rs['net']:>+10.2f}{sk['skill']:>+9.4f}"
              f"{sk['t']:>+9.2f}")

    rs, sk, cost = rows["MEASURED + 0.07 commission"]
    trades = book(P, sig, cost)
    print(f"\n  Honest basis = measured spread + commission.")
    print(f"  R per calendar day: {rs['net']/days:+.4f}  "
          f"(1R/day target needs {1.0/max(rs['net']/days,1e-9):.0f}x more)")

    print("\nYEAR BY YEAR - the regime question")
    print(f"  {'year':<7}{'n':>5}{'E(R)':>9}{'net R':>9}{'win':>7}   gold that year")
    yr = m.index[[i for i, _ in trades]].year
    close_y = m.close.groupby(m.index.year)
    ann = {}
    for y in sorted(set(m.index.year)):
        s = close_y.first().get(y); e = close_y.last().get(y)
        ann[y] = (e / s - 1) if s and e else float("nan")
    pos_years, neg_years = [], []
    for y in sorted(set(yr)):
        part = [t for t, yy in zip(trades, yr) if yy == y]
        st = stats(part)
        gold = ann.get(y, float("nan"))
        tag = "trend" if abs(gold) > 0.10 else "range"
        if st is None:
            print(f"  {y:<7}{len(part):>5}   too few"); continue
        (pos_years if tag == "trend" else neg_years).append(y)
        print(f"  {y:<7}{st['n']:>5}{st['E']:>+9.4f}{st['net']:>+9.2f}"
              f"{st['win']:>7.3f}   {gold:+7.1%}  {tag}")

    print("\nTHE PRE-REGISTERED TEST: skill in trending vs non-trending years,")
    print("each against its own matched control.")
    for label, ys in (("trending years (|gold| > 10%)", pos_years),
                      ("range years (|gold| <= 10%)", neg_years)):
        mask = np.isin(P["idx"].year, ys)
        sub = sig.copy(); sub[~mask] = 0
        rs2, sk2 = skill_vs_control(P, sub, cost)
        if rs2 is None or sk2 is None:
            print(f"  {label:<32} too few trades"); continue
        verdict = "positive" if sk2["skill"] > 0 else "NEGATIVE"
        print(f"  {label:<32} n={rs2['n']:>4}  E={rs2['E']:+.4f}  "
              f"net={rs2['net']:+8.2f}R  skill={sk2['skill']:+.4f} "
              f"(t {sk2['t']:+.2f})  {verdict}")

    print(f"\nSIZING AGAINST THE 35% CEILING, 22 years, honest cost")
    print(f"  {'risk/trade':<12}{'final':>11}{'CAGR':>9}{'max DD':>9}{'<=35%?':>8}")
    best = None
    for f in (0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04):
        eq, dd = equity_path(trades, f)
        cagr = eq ** (1 / years) - 1 if eq > 0 else -1
        fits = dd <= 0.35
        if fits and (best is None or cagr > best[1]): best = (f, cagr, dd)
        print(f"  {f:<12.3f}{eq:>11.2f}{cagr:>+9.2%}{dd:>9.2%}"
              f"{'yes' if fits else 'NO':>8}")
    if best:
        print(f"\n  Best inside 35%: risk {best[0]:.1%} -> {best[1]:+.2%} a year, "
              f"DD {best[2]:.2%}")

    c = m.close.to_numpy(float)
    eqh = c / c[0]
    bh_dd = float(np.max(1.0 - eqh / np.maximum.accumulate(eqh)))
    print(f"  buy & hold 2004-2026: {(c[-1]/c[0])**(1/years)-1:+.2%} a year, "
          f"max DD {bh_dd:.2%}")

if __name__ == "__main__":
    main()
