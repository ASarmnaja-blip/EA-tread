#!/usr/bin/env python3
"""Golden Area / Fibonacci OTE entry, Version 1 of the Backtest Matrix from
`docs/GOLDEN_AREA_RULEBOOK.md`.

WHERE THIS CAME FROM
  The user manually broke down 13 NIFTY 50 5-minute chart-replay clips and
  found a recurring structure: after an impulsive leg, price retraces into a
  "Golden Area" (Fibonacci 62-79% retracement of that leg) inside the
  Premium (short) or Discount (long) half of the range, then reverses toward
  the opposite Day High/Day Low. The rulebook ranks this as High-Probability
  (75-80% confidence from the clips), one tier below the Confirmed
  Premium/Discount bias itself.

MARKET TRANSFER CAVEAT - READ BEFORE THE RESULT
  The 13 clips are NIFTY 50. Everything in this repo, including this file,
  is gold (XAUUSD / GC=F) - there is no NIFTY intraday feed here. This test
  answers "does the Fibonacci-OTE-zone structural idea transfer to a
  different, liquid, trending-capable market," not "is the NIFTY rule
  correct." A dead result here does not refute the NIFTY reading; a live one
  does not confirm it either - it is evidence about gold specifically.

THE RULE, VERSION 1 ONLY (no Sweep/CHoCH-confirm/FVG/confirmation-candle
filters - those are speculative-tier per the rulebook and belong in Version
2, layered on whichever level survives V1, so a filter's contribution can be
judged against its own parent rather than assumed to help)
  1. Swing pivots via a 5-bar fractal, confirmed (lagged) 5 bars after the
     fact - no look-ahead, same pattern already used in `smc_entry_test.py`.
  2. A leg starts when price closes beyond the last confirmed opposite pivot
     (a BOS/CHoCH event). Its extreme is tracked bar-by-bar as the running
     high (bullish leg) or low (bearish leg) since the break - this can only
     use information known up to that bar.
  3. Once the leg stops making new extremes and pulls back, the Golden Area
     level for a given fraction f is measured from the leg's extreme back
     toward its origin: price(f) = extreme - f*(extreme-origin) for a
     bullish leg (SHORT there, betting on reversal down), and the mirror for
     a bearish leg (LONG, betting on reversal up).
  4. Three separate entries, tested independently: A f=0.62, B f=0.705 (the
     user's own estimated midpoint - not a standard Fibonacci number, kept
     because it is what the clips were read as clustering around), C f=0.79.
     Each fires at most once per leg, on the first bar whose range touches
     that exact price.
  5. Exit: NOT the clips' literal dynamic-liquidity target. This repo's
     already-validated trail-2xATR + BE-at-1R exit (`deep_research_signals.
     run_trade`) is reused instead, on purpose - the same reason
     `cost_vs_exit_decomposition.py` exists: an entry's skill has to be
     measured against a fixed, known exit, not a bespoke target that could
     hide entry weakness behind exit engineering. If A/B/C/D shows a lead,
     testing the literal dynamic-target money management is the natural V1.5.

CALIBRATION FIRST
  All three signal builders + evaluate() are run on a driftless zero-cost
  random walk before touching real data. This repo has already found five
  look-ahead bugs this way (see docs/RESEARCH_FINDINGS.md) and the standing
  rule is to check every new signal, including this one, the same way.

PRE-REGISTERED
  skill > +0.10R at t > 2.39 (Bonferroni bar for 3 pre-registered levels,
  two-sided) is a result for any of A/B/C. Stated before the run.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from deep_research_signals import evaluate, HDR, line, atr
from intermarket_signals_60d import fetch

HOLD = 96
LEVELS = {"A 62%": 0.62, "B 70.5%": 0.705, "C 79%": 0.79}
BUF_ATR = 0.10      # break-of-structure buffer, matches smc_entry_test.py

def find_pivots(h, l, side=5):
    """5-bar fractal, confirmed (lagged) `side` bars after the fact."""
    hs, ls = pd.Series(h), pd.Series(l)
    ph = (hs > hs.rolling(side).max().shift(1)) & \
         (hs > hs.rolling(side).max().shift(-side))
    pl = (ls < ls.rolling(side).min().shift(1)) & \
         (ls < ls.rolling(side).min().shift(-side))
    sh = pd.Series(np.where(ph.fillna(False), h, np.nan)).shift(side).ffill().to_numpy()
    sl = pd.Series(np.where(pl.fillna(False), l, np.nan)).shift(side).ffill().to_numpy()
    return sh, sl

def golden_area_signals(df, levels=LEVELS, buf_atr=BUF_ATR):
    """One signal array per level: +1 long / -1 short / 0 nothing, at most
    one fire per leg per level, on the first bar the price range touches
    that level's retracement price."""
    h = df.high.to_numpy(float); l = df.low.to_numpy(float)
    c = df.close.to_numpy(float)
    N = len(df)
    A = atr(df)
    sh, sl = find_pivots(h, l)
    sig = {name: np.zeros(N, np.int8) for name in levels}
    state, origin, extreme = 0, np.nan, np.nan
    fired = {name: False for name in levels}
    for i in range(N):
        a = A[i]
        if not np.isfinite(a) or a <= 0:
            continue
        brk = buf_atr * a
        new_leg = False
        if np.isfinite(sh[i]) and c[i] > sh[i] + brk and state <= 0:
            state, origin = 1, (sl[i] if np.isfinite(sl[i]) else l[i])
            extreme = h[i]; new_leg = True
        elif np.isfinite(sl[i]) and c[i] < sl[i] - brk and state >= 0:
            state, origin = -1, (sh[i] if np.isfinite(sh[i]) else h[i])
            extreme = l[i]; new_leg = True
        if new_leg:
            fired = {name: False for name in levels}
        if state == 0 or not np.isfinite(origin) or not np.isfinite(extreme):
            continue
        if state == 1:
            extreme = max(extreme, h[i])
            rng = extreme - origin
            if rng <= 0: continue
            for name, f in levels.items():
                if fired[name]: continue
                price = extreme - f * rng
                if l[i] <= price <= h[i]:
                    sig[name][i] = -1
                    fired[name] = True
        else:
            extreme = min(extreme, l[i])
            rng = origin - extreme
            if rng <= 0: continue
            for name, f in levels.items():
                if fired[name]: continue
                price = extreme + f * rng
                if l[i] <= price <= h[i]:
                    sig[name][i] = 1
                    fired[name] = True
    return sig

# ------------------------------------------------------------ calibration --
def synth_walk(n_bars, seed, sub_steps=6, sigma=0.0009):
    """Driftless GBM built from sub-bar steps, aggregated to OHLC bars, zero
    cost, zero drift - a signal that is real should still read ~0 skill
    here, since there is nothing to know."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, sigma, size=(n_bars, sub_steps))
    price = 2000.0
    o = np.empty(n_bars); h = np.empty(n_bars)
    lo = np.empty(n_bars); c = np.empty(n_bars)
    for i in range(n_bars):
        path = price * np.exp(np.cumsum(steps[i]))
        o[i] = price; h[i] = max(price, path.max()); lo[i] = min(price, path.min())
        c[i] = path[-1]; price = path[-1]
    idx = pd.date_range("2020-01-01", periods=n_bars, freq="5min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)

def run_calibration():
    print("CALIBRATION: driftless random walk, zero cost - skill should be")
    print("~0 for all three levels before any real number is trusted.\n")
    walk = synth_walk(9000, seed=99)
    sig = golden_area_signals(walk)
    print(HDR); print("  " + "-"*(len(HDR)-2))
    ok = True
    for name in LEVELS:
        n_fired = int((sig[name] != 0).sum())
        r = evaluate(walk, sig[name], hold=HOLD)
        if r is None:
            print(f"  {name:<40}  {n_fired} raw events - too few to calibrate")
            continue
        line(name, r)
        if abs(r["t"]) > 2.39:
            ok = False
    print()
    if ok:
        print("  calibration clean - no level shows fake skill on pure noise.\n")
    else:
        print("  *** a level cleared the bar on RANDOM DATA - stop, this is a")
        print("  *** bug, not a finding. Do not run on real data until fixed.\n")
    return ok

def main():
    print("Golden Area / Fibonacci OTE, Version 1 - three entries, no filters.")
    print("Rulebook: docs/GOLDEN_AREA_RULEBOOK.md\n")

    if not run_calibration():
        sys.exit(1)

    gold = fetch("GC=F")
    print(f"gold M5 {len(gold):,} bars  {gold.index[0].date()} -> "
          f"{gold.index[-1].date()}\n")
    sig = golden_area_signals(gold)

    print(HDR); print("  " + "-"*(len(HDR)-2))
    results = {}
    for name in LEVELS:
        n_fired = int((sig[name] != 0).sum())
        r = evaluate(gold, sig[name], hold=HOLD)
        results[name] = r
        if r is None:
            print(f"  {name:<40}  {n_fired} raw events - too few trades")
        else:
            line(name, r)

    bar = 2.39
    print(f"\n  Bonferroni bar for 3 pre-registered levels, two-sided: |t| > {bar}")
    any_clear = False
    for name, r in results.items():
        if r is None: continue
        v = "CLEARS the bar" if abs(r["t"]) > bar else "does not clear"
        any_clear = any_clear or abs(r["t"]) > bar
        print(f"  {name}: skill t = {r['t']:+.2f}  -  {v}")
    if not any_clear:
        print("\n  None of A/B/C cleared the bar - Version 2 (Sweep/CHoCH/FVG/")
        print("  confirmation filters) has no surviving level to be layered on.")

    print("\nHOW TO READ THIS")
    print("  skill = the level's entry minus a matched random entry (same n,")
    print("  same long/short mix, same exit). This tests ONLY the Fibonacci")
    print("  zone as an entry filter - not the clips' dynamic-liquidity TP,")
    print("  and not on the market the clips were read from (NIFTY vs gold).")

if __name__ == "__main__":
    main()
