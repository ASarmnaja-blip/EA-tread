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

ADDENDUM (2026-09-12) - a second, independent read of the same 13 clips
disagreed on DIRECTION, not just parameters
  An independently-produced rulebook (`docs/GOLDEN_AREA_RULEBOOK.md`'s
  companion audit, "Nonnor Setup Separation V3") labels the Golden Area
  entry as a CONTINUATION: bullish impulse -> retrace into the zone -> LONG,
  continuing the original direction - the standard ICT-OTE reading. This
  file's original V1 tested the opposite: bullish impulse -> retrace into
  the zone -> SHORT, fading it, which is what "Premium -> Short 95%" in the
  rulebook's own confidence table implies. Since these are literally
  opposite trade directions at the identical touch price, both are now
  tested (`mode="fade"` and `mode="continuation"`) rather than picking one
  by argument - this is exactly the kind of ambiguity a backtest resolves
  cheaper than a debate does.
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

def golden_area_signals(df, levels=LEVELS, buf_atr=BUF_ATR, mode="fade"):
    """One signal array per level: +1 long / -1 short / 0 nothing, at most
    one fire per leg per level, on the first bar the price range touches
    that level's retracement price.

    mode="fade": the original 13-clip reading ("Premium -> Short 95%") -
      a bullish leg's retracement into the zone is SHORT (betting on
      reversal away from the impulse).
    mode="continuation": the independent Nonnor S5/S6 reading (standard
      ICT OTE) - a bullish leg's retracement into the zone is LONG
      (betting on resumption of the impulse). Same touch prices, opposite
      direction at every fire - a pure sign flip, isolated here as its own
      argument rather than a second copy of the loop, so both readings are
      guaranteed to fire on the exact same bars."""
    if mode not in ("fade", "continuation"):
        raise ValueError(f"mode must be 'fade' or 'continuation', got {mode!r}")
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
        # fade: bullish leg -> short (-state); continuation: bullish leg -> long (+state)
        d = -state if mode == "fade" else state
        if state == 1:
            extreme = max(extreme, h[i])
            rng = extreme - origin
            if rng <= 0: continue
            for name, f in levels.items():
                if fired[name]: continue
                price = extreme - f * rng
                if l[i] <= price <= h[i]:
                    sig[name][i] = d
                    fired[name] = True
        else:
            extreme = min(extreme, l[i])
            rng = origin - extreme
            if rng <= 0: continue
            for name, f in levels.items():
                if fired[name]: continue
                price = extreme + f * rng
                if l[i] <= price <= h[i]:
                    sig[name][i] = d
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

MODES = ("fade", "continuation")
BAR = 2.39   # Bonferroni bar for 3 levels x 2 modes tested together, two-sided

def run_calibration():
    print("CALIBRATION: driftless random walk, zero cost - skill should be")
    print("~0 for all levels, both modes, before any real number is trusted.\n")
    walk = synth_walk(9000, seed=99)
    print(HDR); print("  " + "-"*(len(HDR)-2))
    ok = True
    for mode in MODES:
        sig = golden_area_signals(walk, mode=mode)
        for name in LEVELS:
            n_fired = int((sig[name] != 0).sum())
            r = evaluate(walk, sig[name], hold=HOLD)
            label = f"{name} ({mode})"
            if r is None:
                print(f"  {label:<40}  {n_fired} raw events - too few to calibrate")
                continue
            line(label, r)
            if abs(r["t"]) > BAR:
                ok = False
    print()
    if ok:
        print("  calibration clean - no level/mode shows fake skill on pure noise.\n")
    else:
        print("  *** a level cleared the bar on RANDOM DATA - stop, this is a")
        print("  *** bug, not a finding. Do not run on real data until fixed.\n")
    return ok

def main():
    print("Golden Area / Fibonacci OTE, Version 1 - three levels, two directions,")
    print("no other filters. Rulebook: docs/GOLDEN_AREA_RULEBOOK.md\n")
    print("Testing BOTH directions because two independent readings of the same")
    print("13 clips disagree on which one the Golden Area actually is:")
    print("  fade         - bullish leg retrace -> SHORT (this repo's original")
    print("                 reading: 'Premium -> Short 95%' in the rulebook)")
    print("  continuation - bullish leg retrace -> LONG (the Nonnor Setup")
    print("                 Separation V3 reading: standard ICT OTE)\n")

    if not run_calibration():
        sys.exit(1)

    gold = fetch("GC=F")
    print(f"gold M5 {len(gold):,} bars  {gold.index[0].date()} -> "
          f"{gold.index[-1].date()}\n")

    print(HDR); print("  " + "-"*(len(HDR)-2))
    results = {}
    for mode in MODES:
        sig = golden_area_signals(gold, mode=mode)
        for name in LEVELS:
            n_fired = int((sig[name] != 0).sum())
            r = evaluate(gold, sig[name], hold=HOLD)
            label = f"{name} ({mode})"
            results[label] = r
            if r is None:
                print(f"  {label:<40}  {n_fired} raw events - too few trades")
            else:
                line(label, r)

    print(f"\n  Bonferroni bar for 3 levels x 2 modes, two-sided: |t| > {BAR}")
    any_clear = False
    for label, r in results.items():
        if r is None: continue
        v = "CLEARS the bar" if abs(r["t"]) > BAR else "does not clear"
        any_clear = any_clear or abs(r["t"]) > BAR
        print(f"  {label}: skill t = {r['t']:+.2f}  -  {v}")
    if not any_clear:
        print("\n  Neither direction, at any level, cleared the bar - the Golden")
        print("  Area disagreement is moot on gold M5: both readings are dead.")

    print("\nHOW TO READ THIS")
    print("  skill = the level's entry minus a matched random entry (same n,")
    print("  same long/short mix, same exit). This tests ONLY the Fibonacci")
    print("  zone as an entry filter - not the clips' dynamic-liquidity TP,")
    print("  and not on the market the clips were read from (NIFTY vs gold).")

if __name__ == "__main__":
    main()
