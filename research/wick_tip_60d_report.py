#!/usr/bin/env python3
"""The wick-tip setup on 60 days of XAUUSD. Full statistics, nothing else.

This file reports ONE thing: what the tuned wick-tip rule did over the 60 days
Yahoo serves, in full. The tuning window and the held-out window are shown
separately and then together, at both measured spreads, with a random control
beside each so the numbers have something to be compared against.

THE RULE, COMPLETE
  Rest a limit LOOK bars' extreme, offset OFF x ATR beyond it:
      buy  limit at  min(low[i-LOOK..i-1])  -  OFF x ATR
      sell limit at  max(high[i-LOOK..i-1]) +  OFF x ATR
  ATR is the value known BEFORE the bar opens. A wick that pierces the level
  fills you there. Stop is SL x ATR from the fill, target is TP x the stop.
  One position at a time. The fill bar is tested for the stop only.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from wick_tip_tuner import fetch, prep, trades_limit, score, control, TUNE_FRAC

# CORRECTED: wick_min was a look-ahead bug (see RESEARCH_FINDINGS.md and the
# docstring on trades_limit() in wick_tip_tuner.py) - it gated a fill priced
# off the bar's LOW on that same bar's CLOSE, which is only known after the
# fact. It is now disabled (raises if non-zero). The "+0.528R vs -0.182R"
# comparison this comment used to cite was the bug, not a filter earning its
# keep.
CFG = dict(look=24, off_atr=1.0, sl_atr=1.0, tp_mult=1.5, wick_min=0.0)
TF, IV = "M5", "5m"
SPREADS = (0.26, 0.7525)

def streaks(R):
    cur = mx = 0
    for r in R:
        cur = cur + 1 if r <= 0 else 0
        mx = max(mx, cur)
    curw = mxw = 0
    for r in R:
        curw = curw + 1 if r > 0 else 0
        mxw = max(mxw, curw)
    return mx, mxw

def report(tr, label, risk_usd=None):
    if len(tr) < 5:
        print(f"{label}: only {len(tr)} trades"); return None
    R = np.array([t[2]/t[3] for t in tr])
    D = np.array([t[2] for t in tr])
    SL = np.array([t[3] for t in tr])
    w, l = R[R > 0], R[R <= 0]
    ml, mw = streaks(R)
    days = (tr[-1][0] - tr[0][0]).days or 1
    print(f"\n{label}")
    print(f"  trades                {len(R):>12,}")
    print(f"  per week              {len(R)/(days/7):>12.3f}")
    print(f"  win rate              {len(w)/len(R):>12.3f}")
    print(f"  average win           {w.mean():>+12.3f} R")
    print(f"  average loss          {-l.mean():>12.3f} R")
    print(f"  realised R:R          {w.mean()/-l.mean():>12.3f}")
    print(f"  profit factor         {w.sum()/-l.sum():>12.3f}")
    print(f"  expectancy            {R.mean():>+12.3f} R")
    print(f"  expectancy            {'$'+format(D.mean(),'+.3f'):>12}  per trade")
    print(f"  total                 {R.sum():>+12.3f} R")
    print(f"  t-statistic           {R.mean()/(R.std(ddof=1)/math.sqrt(len(R))):>+12.3f}")
    print(f"  longest losing run    {ml:>12}")
    print(f"  longest winning run   {mw:>12}")
    print(f"  average stop size     {'$'+format(SL.mean(),'.3f'):>12}")
    if risk_usd:
        eq, peak, dd = 1.0, 1.0, 0.0
        for r in R:
            eq *= (1 + risk_usd*r)
            peak = max(peak, eq); dd = max(dd, 1-eq/peak)
        print(f"  $100 at {risk_usd:.1%} risk    {'$'+format(100*eq,',.2f'):>12}"
              f"   (worst drawdown {dd:.1%})")
    return R

def main():
    df = fetch("GC=F", "60d", IV)
    cut = df.index[int(len(df)*TUNE_FRAC)]
    print("WICK-TIP SETUP - 60 DAY BACKTEST, XAUUSD " + TF)
    print("="*70)
    print(f"data        {len(df):,} bars   {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"rule        limit at {CFG['look']}-bar extreme -/+ {CFG['off_atr']} x ATR")
    print(f"            stop {CFG['sl_atr']} x ATR, target {CFG['tp_mult']} x stop")
    print(f"            one position at a time, fill bar tested for the stop only")
    print(f"split       tune {df.index[0].date()} -> {cut.date()}  |  "
          f"held out {cut.date()} -> {df.index[-1].date()}")

    P_all  = prep(df)
    P_tune = prep(df[df.index < cut])
    P_test = prep(df[df.index >= cut])

    for sp in SPREADS:
        print("\n" + "="*70)
        print(f"SPREAD ${sp}")
        print("="*70)
        for nm, P in (("TUNING WINDOW (parameters chosen here)", P_tune),
                      ("HELD-OUT WINDOW (touched once)", P_test),
                      ("ALL 60 DAYS", P_all)):
            tr = trades_limit(P, spread=sp, **CFG)
            report(tr, nm, risk_usd=0.01)
            cs = control(P, tr, CFG["sl_atr"], CFG["tp_mult"], sp, reps=8)
            if cs:
                print(f"  --- random control, same count/direction/stop/target:")
                print(f"      win {cs['win']:.3f}  RR {cs['rr']:.3f}  "
                      f"PF {cs['pf']:.3f}  E {cs['E']:+.3f} R  t {cs['t']:+.3f}")

if __name__ == "__main__":
    main()
