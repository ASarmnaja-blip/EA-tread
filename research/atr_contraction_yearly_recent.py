#!/usr/bin/env python3
"""Year-by-year breakdown of the surviving setup, plus the last 3 and 6 months
specifically.

THE SETUP BEING BROKEN DOWN
  20-bar H1 breakout, LONG only, only when ATR(14) is at or below its own
  50-period average, RSI(14) agreeing with the direction - the combination
  `combinatorial_filter_search.py` found and `atr_contraction_long_validation.
  py` stress-tested (skill +0.1636, t +6.18 over 22.7 years; positive in both
  halves of the record; profitable in 19/23 years).

WHY THE RECENT WINDOWS USE A DIFFERENT SOURCE THAN THE YEARLY TABLE
  The yearly table uses Dukascopy's hourly endpoint directly (2004-08-31
  2026), the same series validated earlier at 0.877 daily-return correlation
  against GC=F. That endpoint was last pulled through 2026-08-31. The last
  3 and 6 months need data through TODAY, so those two windows are built by
  resampling the M1 cache instead (spread and volume both carried through the
  resample), which extends to 2026-09-11. Same instrument, same decoder,
  different assembly - stated rather than left implicit, because mixing
  sources silently is exactly the kind of thing this repo checks for.

WHAT n THIS SMALL MEANS
  A recent window this short was never going to produce a significant result
  on its own - the arithmetic in `target_feasibility_2m.py` already showed
  that confirming or refuting an edge this size needs thousands of trades.
  These two windows are reported as a CONSISTENCY CHECK (does recent live
  activity look like an obvious departure from the 22-year distribution),
  not as new evidence for or against the rule.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
from breakout_h1_dd_target import prep, signals, book, stats
from atr_contraction_long_validation import make_signal

COMMISSION = 0.07

def load_recent_h1():
    """H1 built from the M1 cache, through whatever the cache's most recent
    day is - extends past the hourly endpoint's last pull."""
    parts = sorted((pathlib.Path(__file__).parent / ".cache_duka").glob("XAUUSD_M1_*.parquet"))
    parts = [p for p in parts if "recent" not in p.name]
    frames = [D.mid(pd.read_parquet(p)) for p in parts]
    m1 = pd.concat(frames).sort_index()
    m1 = m1[~m1.index.duplicated(keep="first")]
    m1 = m1[(m1.volume > 0) & (m1.spread > 0)]
    return D.resample(m1, "1h")

def report(m, label):
    P = prep(m)
    cost = m.spread.to_numpy(float) + COMMISSION
    sig = make_signal(P, m, side="long", use_rsi=True)
    trades = book(P, sig, cost)
    if not trades:
        print(f"  {label}: no trades"); return None
    r = np.array([x for _, x in trades], float)
    print(f"\n{label}  ({m.index[0].date()} -> {m.index[-1].date()}, "
          f"{len(m):,} H1 bars)")
    if len(r) >= 2:
        e, sd = r.mean(), r.std(ddof=1)
        t = e / (sd / math.sqrt(len(r))) if len(r) > 1 and sd > 0 else float("nan")
        print(f"  n={len(r)}  E(R)={e:+.4f}  t={t:+.2f}  net={r.sum():+.2f}R  "
              f"win={float((r>0).mean()):.3f}")
    else:
        print(f"  n={len(r)}  net={r.sum():+.2f}R  (too few for t)")
    return trades

def main():
    print("SETUP: 20-bar H1 breakout, LONG only, ATR(14) <= its 50-bar average,")
    print("RSI(14) agreeing with direction. Frozen - nothing tuned here.\n")

    # ---- year by year on the full validated H1 series --------------------
    m_full = D.clean(D.mid(D.load_h1(2003, 2026)))
    P = prep(m_full)
    cost = m_full.spread.to_numpy(float) + COMMISSION
    sig = make_signal(P, m_full, side="long", use_rsi=True)
    trades = book(P, sig, cost)
    yr = P["idx"][[i for i, _ in trades]].year

    print("YEAR BY YEAR (Dukascopy hourly endpoint, 2004 -> 2026-08-31)")
    print(f"  {'year':<7}{'n':>5}{'E(R)':>9}{'t':>7}{'net R':>9}{'win':>7}")
    pos = tot = 0
    for y in sorted(set(yr)):
        part = [t for t, yy in zip(trades, yr) if yy == y]
        a = np.array([r for _, r in part], float)
        if len(a) == 0: continue
        tot += 1
        if len(a) >= 20:
            st = stats(part)
            print(f"  {y:<7}{st['n']:>5}{st['E']:>+9.4f}{st['t']:>+7.2f}"
                  f"{st['net']:>+9.2f}{st['win']:>7.3f}")
            pos += int(st["net"] > 0)
        else:
            t = a.mean()/(a.std(ddof=1)/math.sqrt(len(a))) if len(a) > 1 and a.std(ddof=1) > 0 else float("nan")
            print(f"  {y:<7}{len(a):>5}{a.mean():>+9.4f}{t:>+7.2f}"
                  f"{a.sum():>+9.2f}{(a>0).mean():>7.3f}   (n<20)")
            pos += int(a.sum() > 0)
    print(f"\n  profitable in {pos}/{tot} years")

    # ---- last 3 and 6 months, built fresh through today -------------------
    print("\nRECENT WINDOWS (H1 resampled from the M1 cache, through "
          f"{load_recent_h1().index[-1].date()})")
    m_recent = load_recent_h1()
    end = m_recent.index[-1]
    for months, label in ((3, "last 3 months"), (6, "last 6 months")):
        start = end - pd.DateOffset(months=months)
        window = m_recent[m_recent.index >= start]
        report(window, f"{label} ({start.date()} -> {end.date()})")

    print("\nHOW TO READ THE RECENT WINDOWS")
    print("  n this small cannot confirm or refute a +0.10R/trade edge on its")
    print("  own - it is a consistency check against the 22-year distribution,")
    print("  not new evidence. A single losing quarter here would not refute")
    print("  the rule any more than a single losing year did in the table")
    print("  above; a large, sustained departure would be worth investigating.")

if __name__ == "__main__":
    main()
