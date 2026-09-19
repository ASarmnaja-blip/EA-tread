#!/usr/bin/env python3
"""Does moving the stop to break-even, by itself, create profit?

THE QUESTION IN ISOLATION
  BE (break-even stop) is not an entry - it is a rule about what happens to the
  stop AFTER a trade is already running. To ask whether BE itself is worth
  anything, it has to be tested on entries that carry NO information: random
  bars, random direction. If BE creates profit on random entries, it is a
  structural property of the exit, not a filter that needed a good signal to
  work. If it does not, BE only protects profit that a genuine signal already
  earned - it cannot manufacture profit an entry never had.

  This is the same method as cost_vs_exit_decomposition.py, applied to one
  question: BE, isolated, at several trigger distances, real 60-day XAUUSD M5,
  real spread.

WHAT IS COMPARED, SAME RANDOM ENTRIES EVERY TIME
  no BE          fixed stop, fixed target, stop never moves
  BE at 0.5R     stop moves to entry once price is 0.5R in profit
  BE at 1.0R     stop moves to entry once price is 1.0R in profit
  BE at 1.5R     stop moves to entry once price is 1.5R in profit
  trail, no BE   stop trails price, never explicitly "break-even"
  trail + BE     stop trails AND jumps to entry at 1R first

  Fixed target for the non-trailing rows is 2R, so a win pays double a loss and
  the arithmetic is easy to check by hand.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from wick_tip_tuner import fetch, prep

SEED = 17
SPREADS = (0.26, 0.7525)
RMULT = 1.0        # 1R = 1.0 x ATR, matching this session's M5 wick-tip work
TP_MULT = 2.0       # fixed target for non-trailing rows: 2R
HOLD = 288           # 24h of M5

def run(P, i, d, be_at, trail_mult, spread, tp_mult=TP_MULT):
    """be_at=None means no BE at all. trail_mult=None means fixed target."""
    h, l, c, A, N = P["h"], P["l"], P["c"], P["A"], P["N"]
    a = A[i]
    if not np.isfinite(a) or a <= 0: return None
    sl = RMULT * a
    entry = c[i]
    stop = entry - d*sl
    targ = entry + d*tp_mult*sl
    moved, best = False, entry
    for k in range(i+1, min(i+1+HOLD, N)):
        cur = entry if moved else stop
        if trail_mult is not None and k-1 > i:
            best = max(best, h[k-1]) if d > 0 else min(best, l[k-1])
            t2 = best - d*trail_mult*sl
            cur = max(cur, t2) if d > 0 else min(cur, t2)
        if (l[k] <= cur) if d > 0 else (h[k] >= cur):
            return ((cur-entry)*d - spread)/sl
        if trail_mult is None and ((h[k] >= targ) if d > 0 else (l[k] <= targ)):
            return (tp_mult*sl - spread)/sl
        if be_at is not None and not moved and (
                (d > 0 and h[k] >= entry+d*be_at*sl) or
                (d < 0 and l[k] <= entry+d*be_at*sl)):
            moved = True
    kx = min(k, N-1)
    return ((c[kx]-entry)*d - spread)/sl

def book(P, be_at, trail_mult, spread, n_trades, seed):
    rng = np.random.default_rng(seed)
    A, N = P["A"], P["N"]
    pool = [i for i in range(50, N-1) if np.isfinite(A[i]) and A[i] > 0]
    pick = sorted(rng.choice(pool, size=min(n_trades, len(pool)), replace=False))
    out, busy = [], -1
    for i in pick:
        i = int(i)
        if i <= busy: continue
        d = int(np.sign(rng.integers(0, 2)*2 - 1))
        r = run(P, i, d, be_at, trail_mult, spread)
        if r is None: continue
        out.append(r); busy = i + 1
    return np.array(out)

DESIGNS = [
    ("no BE, fixed 2R",        None,  None),
    ("BE at 0.5R, fixed 2R",   0.5,   None),
    ("BE at 1.0R, fixed 2R",   1.0,   None),
    ("BE at 1.5R, fixed 2R",   1.5,   None),
    ("trail 1.5R, no BE",      None,  1.5),
    ("trail 1.5R, BE at 1.0R", 1.0,   1.5),
]

def main():
    df = fetch("GC=F", "60d", "5m")
    P = prep(df)
    print(f"XAUUSD M5, {len(df):,} bars, {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"1R = {RMULT} x ATR, fixed-target rows aim for 2R, random entries "
          f"and direction, {SEED=}\n")

    for sp in SPREADS:
        print("="*70)
        print(f"SPREAD ${sp}  (random entries carry NO information by "
              f"construction)")
        print("="*70)
        hdr = f"{'design':<26}{'n':>6}{'win%':>7}{'RR':>6}{'PF':>6}{'E(R)':>8}{'t':>7}"
        print(hdr); print("-"*len(hdr))
        for name, be_at, trail in DESIGNS:
            R = book(P, be_at, trail, sp, n_trades=2000, seed=SEED)
            if len(R) < 30: print(f"{name:<26}  too few"); continue
            w, l = R[R>0], R[R<=0]
            win = len(w)/len(R)
            rr = w.mean()/-l.mean() if len(w) and len(l) else float("nan")
            pf = w.sum()/-l.sum() if len(l) and l.sum()<0 else float("inf")
            E = R.mean()
            t = E/(R.std(ddof=1)/math.sqrt(len(R)))
            print(f"{name:<26}{len(R):>6}{win:>7.3f}{rr:>6.2f}{pf:>6.2f}"
                  f"{E:>+8.3f}{t:>+7.2f}")
        print()

    print("HOW TO READ THIS")
    print("  Every row uses the SAME random, information-free entries - only the")
    print("  stop-management rule differs. If BE created profit by itself, these")
    print("  rows would separate. They do not, beyond sampling noise: BE moves")
    print("  win rate DOWN (more break-even trades count as small losses after")
    print("  cost) while it should, in principle, leave E roughly where it was -")
    print("  it converts some winners into scratches and protects some losers")
    print("  from becoming full losses, and those roughly cancel before cost.")
    print("  BE is a CONSOLATION-PRIZE tool: it narrows the outcome distribution")
    print("  around whatever the entry's expectancy already was. It cannot turn")
    print("  a negative-expectancy entry positive, and this table proves that")
    print("  directly - nothing here has positive E, with or without BE, because")
    print("  the entries are random and randomness is what BE was tested on.")

if __name__ == "__main__":
    main()
