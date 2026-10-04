#!/usr/bin/env python3
"""Stress-testing the one combination that cleared the combinatorial bar.

WHAT WAS FOUND
  `combinatorial_filter_search.py` swept 67,338 filter subsets over 22.7 years
  of real XAUUSD H1 and several cleared the noise bar that search created
  (|t| > 4.72). Stripped of decoration they are one rule:

      take the 20-bar breakout LONG, only when ATR(14) is BELOW its own
      50-period average - a breakout out of quiet, not out of noise.

  atr_contracting + long_side          skill +0.1467, t +5.46, n=1272
  + rsi_agrees                         skill +0.1598, t +6.01, n=1216
  + rsi_agrees + rsi_not_extreme       skill +0.1678, t +6.25, n=1205

WHY THIS FILE EXISTS
  Clearing a multiple-comparison bar on the data that selected you is the
  weakest form of evidence that still counts as evidence. This repo has
  retracted results at exactly this stage before. Three specific ways this
  could still be false, each tested here rather than argued about:

  1. IT COULD BE GOLD'S BULL MARKET. The rule is long-only and gold went from
     ~400 to ~4500 across the window. The matched control is direction-matched
     so drift is already subtracted - but the honest check is whether the rule
     beats holding, and whether the long-only edge has a short-side mirror that
     also works (it should, if the mechanism is real and not just beta).

  2. IT COULD LIVE IN ONE ERA. Split the 22 years and require both halves to
     work. A rule that only works after 2015 is a regime, not a rule.

  3. IT COULD BE A SAMPLE-SIZE ILLUSION. n=1205 of 3570 candidates is a third
     of the data; the subset was chosen because it looked good. Year-by-year
     consistency is what separates a real subpopulation from a lucky slice.

  Passing all three still does not make it tradeable - the money question is
  asked at the end, separately, because a real edge and a target-hitting return
  are different claims.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
from breakout_h1_dd_target import (prep, signals, book, stats, skill_vs_control,
                                   equity_path)

COMMISSION = 0.07

def atr_contracting_mask(P, m):
    A = P["A"]
    slow = pd.Series(A).rolling(50).mean().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(A <= slow, nan=0).astype(bool)

def rsi_series(P):
    d = pd.Series(P["c"]).diff()
    up = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    return (100 - 100/(1 + up/dn.replace(0, np.nan))).shift(1).to_numpy()

def make_signal(P, m, side=None, use_rsi=False):
    """The frozen breakout, gated on contracting ATR, optionally one side only
    and optionally requiring RSI to agree."""
    base = signals(P)
    quiet = atr_contracting_mask(P, m)
    s = np.where(quiet, base, 0).astype(np.int8)
    if side == "long":  s = np.where(s > 0, s, 0).astype(np.int8)
    if side == "short": s = np.where(s < 0, s, 0).astype(np.int8)
    if use_rsi:
        r = rsi_series(P)
        ok = ((r > 50) & (s > 0)) | ((r < 50) & (s < 0)) | (s == 0)
        s = np.where(np.nan_to_num(ok, nan=0).astype(bool), s, 0).astype(np.int8)
    return s

def row(label, P, sig, cost, bar):
    rs, sk = skill_vs_control(P, sig, cost)
    if rs is None or sk is None:
        print(f"  {label:<38}  too few trades"); return None
    flag = "CLEARS" if abs(sk["t"]) > bar else ""
    print(f"  {label:<38}{rs['n']:>6}{rs['E']:>+9.4f}{rs['t']:>+7.2f}"
          f"{sk['skill']:>+9.4f}{sk['t']:>+9.2f}  {flag}")
    return rs, sk

def main():
    m = D.clean(D.mid(D.load_h1(2003, 2026)))
    P = prep(m)
    cost = m.spread.to_numpy(float) + COMMISSION
    years = (m.index[-1] - m.index[0]).days / 365.25
    days = (m.index[-1] - m.index[0]).days
    BAR = 4.72      # the bar the 67,338-subset search created
    print(f"Real XAUUSD H1, {len(m):,} bars, {m.index[0].date()} -> "
          f"{m.index[-1].date()}")
    print(f"bar to beat, inherited from the search that found this: "
          f"|t| > {BAR}\n")

    print("TEST 1 - IS IT THE LONG SIDE, OR IS IT THE QUIET?")
    print("If contracting ATR is the mechanism it should help the SHORT side")
    print("too. If only the long side works on a market that rose 11x, that")
    print("points at beta rather than at a breakout effect.")
    print(f"  {'variant':<38}{'n':>6}{'E(R)':>9}{'t':>7}{'skill':>9}{'skill t':>9}")
    row("all breakouts, no filter", P, signals(P), cost, BAR)
    row("quiet ATR, both sides", P, make_signal(P, m), cost, BAR)
    long_res = row("quiet ATR, LONG only", P, make_signal(P, m, "long"), cost, BAR)
    row("quiet ATR, SHORT only", P, make_signal(P, m, "short"), cost, BAR)
    row("quiet ATR, LONG + RSI agrees", P,
        make_signal(P, m, "long", True), cost, BAR)
    row("noisy ATR, LONG only (the mirror)", P,
        np.where(~atr_contracting_mask(P, m), np.where(signals(P) > 0,
                 signals(P), 0), 0).astype(np.int8), cost, BAR)

    print("\nTEST 2 - DOES IT LIVE IN ONE ERA?")
    sig = make_signal(P, m, "long", True)
    half = P["N"] // 2
    cut = P["idx"][half]
    print(f"  split at {cut.date()}")
    print(f"  {'period':<38}{'n':>6}{'E(R)':>9}{'t':>7}{'skill':>9}{'skill t':>9}")
    for label, lo, hi in (("first half", 0, half), ("second half", half, P["N"])):
        s2 = sig.copy()
        s2[:lo] = 0; s2[hi:] = 0
        row(label, P, s2, cost, BAR)

    print("\nTEST 3 - YEAR BY YEAR")
    trades = book(P, sig, cost)
    yr = P["idx"][[i for i, _ in trades]].year
    print(f"  {'year':<8}{'n':>5}{'E(R)':>10}{'net R':>10}{'win':>8}")
    pos = 0; tot = 0
    for y in sorted(set(yr)):
        part = [t for t, yy in zip(trades, yr) if yy == y]
        st = stats(part)
        if st is None:
            a = np.array([r for _, r in part], float)
            if len(a) == 0: continue
            print(f"  {y:<8}{len(a):>5}{a.mean():>+10.4f}{a.sum():>+10.2f}"
                  f"{(a>0).mean():>8.3f}   (n<20)")
            tot += 1; pos += int(a.sum() > 0)
            continue
        tot += 1; pos += int(st["net"] > 0)
        print(f"  {y:<8}{st['n']:>5}{st['E']:>+10.4f}{st['net']:>+10.2f}"
              f"{st['win']:>8.3f}")
    print(f"\n  profitable in {pos}/{tot} years")

    print("\nTEST 4 - THE MONEY QUESTION, ASKED SEPARATELY")
    rs = stats(trades)
    print(f"  {rs['n']} trades over {days} days = {rs['n']/days:.2f}/day, "
          f"{rs['net']:+.2f}R total = {rs['net']/days:+.4f} R/day")
    print(f"  {'risk':>6}{'final':>10}{'CAGR':>9}{'max DD':>9}")
    for f in (0.01, 0.02, 0.03, 0.05, 0.08, 0.10):
        eq, dd = equity_path(trades, f)
        cagr = eq ** (1/years) - 1 if eq > 0 else -1
        print(f"  {f:>6.0%}{eq:>10.2f}{cagr:>+9.2%}{dd:>9.1%}")
    c = m.close.to_numpy(float); e = c/c[0]
    print(f"  buy & hold: {(c[-1]/c[0])**(1/years)-1:+.2%}/yr at "
          f"DD {np.max(1-e/np.maximum.accumulate(e)):.1%}")

if __name__ == "__main__":
    main()
