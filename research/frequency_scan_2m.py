#!/usr/bin/env python3
"""Does raising the trade frequency reach 1R/day, on the last two months, at a
50-75% drawdown budget?

THE ARITHMETIC THAT MOTIVATES THIS
  `breakout_real_xauusd.py` measured the frozen 20-bar breakout on 22.7 years
  of real XAUUSD at the real spread. Its entry carries genuine, regime-
  independent information: skill +0.1096 at t +7.12 on 3,570 trades, positive
  in trending years (t +5.01) AND range years (t +3.80).

  It still misses the target, and the reason is arithmetic rather than
  statistical. The rule fires ~157 times a year on H1 and harvests ~4.5R a
  year, which is +0.0122R per calendar day - 82x short of 1R/day. Raising the
  drawdown ceiling does not close that: on the 22-year record even a 72.8%
  drawdown only buys +9.21% a year, still under the 10% floor.

  If the edge per trade survives at a lower timeframe, frequency multiplies it.
  M5 offers roughly twelve times H1's bar count. That is the one lever left,
  and real M1 data now makes it testable on the real instrument at the real
  spread for the first time.

THE WINDOW, AND WHAT IT COSTS TO USE IT
  The user asked to work from the last two months and not to backtest far.
  That is honoured here, and the price has to be stated plainly: two months of
  M15 is a few hundred trades and two months of H1 is a few dozen. This repo's
  own record is that two-month windows are exactly where false positives come
  from - the wick-tip setup, the VWAP lead, and the GC=F breakout's +77%/year
  all looked strong on a window this size and all shrank or died on longer
  data. So every row below carries its matched-control skill and its t, and
  the H1 row is printed next to the 22-year number for the same rule, which is
  the only honest way to show how much a two-month reading can flatter.

  Nothing is tuned. The rule is the same frozen breakout, imported unchanged.
  The only thing that varies across rows is the bar size.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
from breakout_h1_dd_target import (prep, signals, book, stats, skill_vs_control,
                                   equity_path)

COMMISSION = 0.07
CACHE = pathlib.Path(__file__).parent / ".cache_duka" / "XAUUSD_M1_recent.parquet"
TFS = ("5min", "15min", "30min", "1h")
WINDOW_START = "2026-07-12"

def load_recent():
    m1 = pd.read_parquet(CACHE)
    # market-closed bars carry no volume and would otherwise become flat
    # synthetic bars that a breakout rule happily trades
    return m1[(m1.volume > 0) & (m1.spread > 0)]

def risk_for_dd(trades, ceiling, years):
    """Largest risk fraction whose realised drawdown stays under the ceiling,
    and what it returns. Drawdown is measured on trade-exit equity marks, so
    the true intrabar figure is worse than the number printed."""
    best = None
    for f in np.arange(0.002, 0.121, 0.002):
        eq, dd = equity_path(trades, float(f))
        if eq <= 0 or dd > ceiling: continue
        cagr = eq ** (1 / years) - 1
        if best is None or cagr > best[1]:
            best = (float(f), cagr, dd)
    return best

def main():
    m1 = load_recent()
    m1 = m1[m1.index >= pd.Timestamp(WINDOW_START, tz="UTC")]
    days = (m1.index[-1] - m1.index[0]).days
    years = days / 365.25
    print(f"XAUUSD real M1, {len(m1):,} minutes  {m1.index[0].date()} -> "
          f"{m1.index[-1].date()}  ({days} calendar days)")
    print(f"real spread over the window: median {m1.spread.median():.3f}, "
          f"mean {m1.spread.mean():.3f}\n")

    print("FREQUENCY SCAN - same frozen 20-bar breakout, only the bar size changes")
    print(f"  {'TF':<7}{'bars':>8}{'n':>6}{'/day':>7}{'E(R)':>9}{'t':>7}"
          f"{'net R':>9}{'R/day':>8}{'skill':>9}{'skill t':>9}")
    results = {}
    for tf in TFS:
        bars = D.resample(m1, tf)
        if len(bars) < 200: continue
        P = prep(bars)
        cost = bars.spread.to_numpy(float) + COMMISSION
        sig = signals(P)
        rs, sk = skill_vs_control(P, sig, cost)
        if rs is None:
            print(f"  {tf:<7}{len(bars):>8}   too few trades"); continue
        trades = book(P, sig, cost)
        results[tf] = (trades, rs, sk, years)
        print(f"  {tf:<7}{len(bars):>8}{rs['n']:>6}{rs['n']/days:>7.2f}"
              f"{rs['E']:>+9.4f}{rs['t']:>+7.2f}{rs['net']:>+9.2f}"
              f"{rs['net']/days:>+8.3f}{sk['skill']:>+9.4f}"
              f"{sk['t'] if sk else float('nan'):>+9.2f}")

    print("\n  22-year reference for the H1 row: E +0.0284, skill +0.1096")
    print("  (t +7.12), +0.0122 R/day. Anything far above that on two months")
    print("  is the window talking, not a better rule.\n")

    print("TARGET 1: 1R PER CALENDAR DAY")
    for tf, (trades, rs, sk, yy) in results.items():
        rpd = rs["net"] / days
        gap = 1.0 / rpd if rpd > 0 else float("inf")
        verdict = "HITS IT" if rpd >= 1.0 else f"{gap:.0f}x short" if rpd > 0 else "negative"
        print(f"  {tf:<7} {rpd:+.3f} R/day   {verdict}")

    print("\nTARGET 2: RETURN INSIDE A 50% AND A 75% DRAWDOWN CEILING")
    print(f"  {'TF':<7}{'ceiling':>9}{'risk':>8}{'window ret':>12}"
          f"{'annualised':>12}{'max DD':>9}")
    for tf, (trades, rs, sk, yy) in results.items():
        for ceiling in (0.50, 0.75):
            b = risk_for_dd(trades, ceiling, years)
            if b is None:
                print(f"  {tf:<7}{ceiling:>9.0%}     no positive sizing"); continue
            f, cagr, dd = b
            eq, _ = equity_path(trades, f)
            print(f"  {tf:<7}{ceiling:>9.0%}{f:>8.1%}{eq-1:>+12.2%}"
                  f"{cagr:>+12.2%}{dd:>9.2%}")

    print("\nHOW TO READ THE ANNUALISED COLUMN")
    print("  It extrapolates a two-month result to a year. That is what the")
    print("  target is stated in, so it is printed - but two months of gold")
    print("  is one regime, and annualising it assumes the next ten months")
    print("  look like these two. The skill t column is the only defence")
    print("  against that, and on a sample this size it is weak by construction.")

if __name__ == "__main__":
    main()
