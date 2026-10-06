#!/usr/bin/env python3
"""What edge would actually hit the target, and does anything on the last two
months have it?

TWO PARTS, BECAUSE THE SEARCH IS ONLY MEANINGFUL AGAINST THE ARITHMETIC

PART 1 - WHAT THE TARGET REQUIRES
  The targets are 1R per calendar day, or 10-50%+ a year inside a 50-75%
  drawdown ceiling. Those convert into a required edge per trade once the trade
  frequency is fixed, and the conversion is not negotiable:

      R per day = trades per day x E(R per trade)

  Printed against what has actually been measured on real XAUUSD: the frozen
  20-bar breakout's edge over 22.7 years is E +0.0284R per trade at the real
  spread, with skill +0.1096 at t +7.12. That edge is REAL - it is the
  strongest result this program has produced, positive in both trending and
  ranging years - and it is also SMALL.

  The same arithmetic sets how much data it takes to see an edge that size. At
  a per-trade standard deviation near 1.2R, detecting E = +0.028R at t = 2
  needs roughly (2 x 1.2 / 0.028)^2 trades. That number is why a two-month
  window cannot settle anything about this rule in either direction, and it is
  computed below rather than asserted.

PART 2 - THE SEARCH
  A bounded grid on the last two months of real M1: four timeframes x four
  lookbacks x both directions (break out of the range, or fade back into it).
  32 cells, so the bar the best cell must clear is the expected maximum of 32
  noise draws, sqrt(2 ln 32) = 2.63, stated before the run rather than after.

  Every cell is priced at the MEASURED bid/ask spread of its own entry bar plus
  commission, and every cell is scored against its own matched random control -
  same trade count, same long/short mix, same exit, random timing.

  This repo's record on two-month windows is on file: the wick-tip setup, the
  VWAP lead and the GC=F breakout's +77%/year all looked strong on a window
  this size and all shrank or died on longer data. The grid is run anyway
  because the request was to work from this window - but the noise bar is what
  decides, not the top of the table.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
import breakout_h1_dd_target as B
from breakout_h1_dd_target import prep, plan, book, stats, skill_vs_control, equity_path
from frequency_scan_2m import load_recent, risk_for_dd, COMMISSION

TFS = ("5min", "15min", "30min", "1h")
LOOKBACKS = (10, 20, 40, 80)
DIRS = ("breakout", "fade")
MEASURED_E, MEASURED_SD = 0.0284, 1.2      # 22.7-year real-XAUUSD figures

def part1(days):
    print("PART 1 - WHAT THE TARGET REQUIRES\n")
    print("  1R per calendar day, by how often you trade:")
    print(f"    {'trades/day':>12}{'E(R) needed':>14}{'vs measured +0.0284':>22}")
    for tpd in (0.5, 2, 6, 20, 50):
        need = 1.0 / tpd
        print(f"    {tpd:>12.1f}{need:>14.3f}{need/MEASURED_E:>18.0f}x")
    print("\n  The measured edge is +0.0284R. Even at 50 trades a day - one")
    print("  every ten minutes, all session - it yields 1.42R/day only if the")
    print("  edge survives at that frequency, and the frequency scan found it")
    print("  does not: every timeframe was negative over these two months.\n")

    n_need = (2 * MEASURED_SD / MEASURED_E) ** 2
    print(f"  To SEE an edge of +0.0284R at t=2 takes ~{n_need:,.0f} trades.")
    for tf, tpd in (("H1", 0.47), ("M15", 2.08), ("M5", 6.15)):
        yrs = n_need / max(tpd, 1e-9) / 365.25
        print(f"    at {tf}'s {tpd} trades/day that is {yrs:.1f} years")
    print(f"\n  Two months at M5 gives ~{6.15*days:,.0f} trades - about "
          f"{6.15*days/n_need*100:.0f}% of what is needed.")
    print("  A two-month window cannot confirm OR refute an edge this size.")
    print("  It can only be fitted to.\n")

def ranged_signal(P, look, mode):
    """Break out of the prior `look`-bar range, or fade back into it. The fade
    is the same information read with the opposite sign, which is why it costs
    a grid cell rather than a new hypothesis."""
    c, A = P["c"], P["A"]
    h = pd.Series(P["h"]).rolling(look).max().shift(1).to_numpy()
    l = pd.Series(P["l"]).rolling(look).min().shift(1).to_numpy()
    s = np.zeros(P["N"], np.int8)
    with np.errstate(invalid="ignore"):
        up = c > h + B.BUF_ATR * A
        dn = c < l - B.BUF_ATR * A
    up = np.nan_to_num(up, nan=0).astype(bool)
    dn = np.nan_to_num(dn, nan=0).astype(bool)
    if mode == "breakout":
        s[up], s[dn] = 1, -1
    else:
        s[up], s[dn] = -1, 1
    return s, h, l

def main():
    m1 = load_recent()
    m1 = m1[m1.index >= pd.Timestamp("2026-07-12", tz="UTC")]
    days = (m1.index[-1] - m1.index[0]).days
    years = days / 365.25
    print(f"Real XAUUSD M1, {len(m1):,} minutes, {m1.index[0].date()} -> "
          f"{m1.index[-1].date()} ({days} days)")
    print(f"measured spread median {m1.spread.median():.3f}\n")

    part1(days)

    k = len(TFS) * len(LOOKBACKS) * len(DIRS)
    bar = math.sqrt(2 * math.log(k))
    print(f"PART 2 - THE SEARCH: {k} cells, noise bar |t| > {bar:.2f}\n")
    print(f"  {'TF':<7}{'look':>5}{'dir':>10}{'n':>6}{'E(R)':>9}"
          f"{'net R':>9}{'R/day':>8}{'skill':>9}{'skill t':>9}")
    rows = []
    for tf in TFS:
        bars = D.resample(m1, tf)
        if len(bars) < 250: continue
        P = prep(bars)
        cost = bars.spread.to_numpy(float) + COMMISSION
        for look in LOOKBACKS:
            for mode in DIRS:
                sig, hh, ll = ranged_signal(P, look, mode)
                # the frozen plan uses the 20-bar edges; re-point it at this
                # cell's own lookback so stop and target stay consistent
                P2 = dict(P); P2["ph"], P2["pl"] = hh, ll
                P2["fade_stop"] = (mode == "fade")
                rs, sk = skill_vs_control(P2, sig, cost)
                if rs is None or sk is None: continue
                tr = book(P2, sig, cost)
                rows.append((tf, look, mode, rs, sk, tr))
                print(f"  {tf:<7}{look:>5}{mode:>10}{rs['n']:>6}{rs['E']:>+9.4f}"
                      f"{rs['net']:>+9.2f}{rs['net']/days:>+8.3f}"
                      f"{sk['skill']:>+9.4f}{sk['t']:>+9.2f}")

    if not rows:
        print("  nothing produced enough trades"); return
    best = max(rows, key=lambda r: r[4]["t"])
    tf, look, mode, rs, sk, tr = best
    print(f"\n  Best cell by skill t: {tf} {look}-bar {mode}, "
          f"skill {sk['skill']:+.4f} at t {sk['t']:+.2f}")
    print(f"  Noise bar for {k} cells: {bar:.2f}  ->  "
          f"{'CLEARS' if abs(sk['t']) > bar else 'does NOT clear'}")

    best_money = max(rows, key=lambda r: r[3]["net"])
    tf2, look2, mode2, rs2, sk2, tr2 = best_money
    print(f"\n  Best cell by money: {tf2} {look2}-bar {mode2}, "
          f"{rs2['net']:+.2f}R over {days} days = {rs2['net']/days:+.3f} R/day")
    print(f"  {'ceiling':>9}{'risk':>8}{'window ret':>12}{'annualised':>12}{'max DD':>9}")
    for ceiling in (0.50, 0.75):
        b = risk_for_dd(tr2, ceiling, years)
        if b is None:
            print(f"  {ceiling:>9.0%}   no positive sizing"); continue
        f, cagr, dd = b
        eq, _ = equity_path(tr2, f)
        print(f"  {ceiling:>9.0%}{f:>8.1%}{eq-1:>+12.2%}{cagr:>+12.2%}{dd:>9.2%}")
    print(f"\n  That cell's skill t is {sk2['t']:+.2f} against a {bar:.2f} bar.")
    print("  If it does not clear, the money in it is this window's, not the")
    print("  rule's, and sizing it up raises the variance, not the expectancy.")

if __name__ == "__main__":
    main()
